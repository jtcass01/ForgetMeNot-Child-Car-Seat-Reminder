# main.py -- put your code here!

"""

MICROPYTHON CLASS MODULE CODE
Taken from https://github.com/inmcm/micropyGPS/blob/master/micropyGPS.py

"""

from math import floor, modf, sin, cos, atan2, pi, sqrt, radians

# Assume running on MicroPython
import utime

import time
import _thread

class MicropyGPS(object):
    """GPS NMEA Sentence Parser. Creates object that stores all relevant GPS data and statistics.
    Parses sentences one character at a time using update(). """

    # Max Number of Characters a valid sentence can be (based on GGA sentence)
    SENTENCE_LIMIT = 90
    __HEMISPHERES = ('N', 'S', 'E', 'W')
    __NO_FIX = 1
    __FIX_2D = 2
    __FIX_3D = 3
    __DIRECTIONS = ('N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE', 'S', 'SSW', 'SW', 'WSW', 'W',
                    'WNW', 'NW', 'NNW')
    __MONTHS = ('January', 'February', 'March', 'April', 'May',
                'June', 'July', 'August', 'September', 'October',
                'November', 'December')

    def __init__(self, local_offset=0, location_formatting='ddm'):
        """
        Setup GPS Object Status Flags, Internal Data Registers, etc
            local_offset (int): Timzone Difference to UTC
            location_formatting (str): Style For Presenting Longitude/Latitude:
                                       Decimal Degree Minute (ddm) - 40° 26.767′ N
                                       Degrees Minutes Seconds (dms) - 40° 26′ 46″ N
                                       Decimal Degrees (dd) - 40.446° N
        """

        #####################
        # Object Status Flags
        self.sentence_active = False
        self.active_segment = 0
        self.process_crc = False
        self.gps_segments = []
        self.crc_xor = 0
        self.char_count = 0
        self.fix_time = 0

        #####################
        # Sentence Statistics
        self.crc_fails = 0
        self.clean_sentences = 0
        self.parsed_sentences = 0

        #####################
        # Logging Related
        self.log_handle = None
        self.log_en = False

        #####################
        # Data From Sentences
        # Time
        self.timestamp = [0, 0, 0]
        self.date = [0, 0, 0]
        self.local_offset = local_offset

        # Position/Motion
        self._latitude = [0, 0.0, 'N']
        self._longitude = [0, 0.0, 'W']
        self.coord_format = location_formatting
        self.speed = [0.0, 0.0, 0.0]
        self.course = 0.0
        self.altitude = 0.0
        self.geoid_height = 0.0

        # GPS Info
        self.satellites_in_view = 0
        self.satellites_in_use = 0
        self.satellites_used = []
        self.last_sv_sentence = 0
        self.total_sv_sentences = 0
        self.satellite_data = dict()
        self.hdop = 0.0
        self.pdop = 0.0
        self.vdop = 0.0
        self.valid = False
        self.fix_stat = 0
        self.fix_type = 1

    ########################################
    # Coordinates Translation Functions
    ########################################
    @property
    def latitude(self):
        """Format Latitude Data Correctly"""
        if self.coord_format == 'dd':
            decimal_degrees = self._latitude[0] + (self._latitude[1] / 60)
            return [decimal_degrees, self._latitude[2]]
        elif self.coord_format == 'dms':
            minute_parts = modf(self._latitude[1])
            seconds = round(minute_parts[0] * 60)
            return [self._latitude[0], int(minute_parts[1]), seconds, self._latitude[2]]
        else:
            return self._latitude

    @property
    def longitude(self):
        """Format Longitude Data Correctly"""
        if self.coord_format == 'dd':
            decimal_degrees = self._longitude[0] + (self._longitude[1] / 60)
            return [decimal_degrees, self._longitude[2]]
        elif self.coord_format == 'dms':
            minute_parts = modf(self._longitude[1])
            seconds = round(minute_parts[0] * 60)
            return [self._longitude[0], int(minute_parts[1]), seconds, self._longitude[2]]
        else:
            return self._longitude

    ########################################
    # Logging Related Functions
    ########################################
    def start_logging(self, target_file, mode="append"):
        """
        Create GPS data log object
        """
        # Set Write Mode Overwrite or Append
        mode_code = 'w' if mode == 'new' else 'a'

        try:
            self.log_handle = open(target_file, mode_code)
        except AttributeError:
            print("Invalid FileName")
            return False

        self.log_en = True
        return True

    def stop_logging(self):
        """
        Closes the log file handler and disables further logging
        """
        try:
            self.log_handle.close()
        except AttributeError:
            print("Invalid Handle")
            return False

        self.log_en = False
        return True

    def write_log(self, log_string):
        """Attempts to write the last valid NMEA sentence character to the active file handler
        """
        try:
            self.log_handle.write(log_string)
        except TypeError:
            return False
        return True

    ########################################
    # Sentence Parsers
    ########################################
    def gprmc(self):
        """Parse Recommended Minimum Specific GPS/Transit data (RMC)Sentence.
        Updates UTC timestamp, latitude, longitude, Course, Speed, Date, and fix status
        """

        # UTC Timestamp
        try:
            utc_string = self.gps_segments[1]

            if utc_string:  # Possible timestamp found
                hours = (int(utc_string[0:2]) + self.local_offset) % 24
                minutes = int(utc_string[2:4])
                seconds = float(utc_string[4:])
                self.timestamp = (hours, minutes, seconds)
            else:  # No Time stamp yet
                self.timestamp = (0, 0, 0)

        except ValueError:  # Bad Timestamp value present
            return False

        # Date stamp
        try:
            date_string = self.gps_segments[9]

            # Date string printer function assumes to be year >=2000,
            # date_string() must be supplied with the correct century argument to display correctly
            if date_string:  # Possible date stamp found
                day = int(date_string[0:2])
                month = int(date_string[2:4])
                year = int(date_string[4:6])
                self.date = (day, month, year)
            else:  # No Date stamp yet
                self.date = (0, 0, 0)

        except ValueError:  # Bad Date stamp value present
            return False

        # Check Receiver Data Valid Flag
        if self.gps_segments[2] == 'A':  # Data from Receiver is Valid/Has Fix

            # Longitude / Latitude
            try:
                # Latitude
                l_string = self.gps_segments[3]
                lat_degs = int(l_string[0:2])
                lat_mins = float(l_string[2:])
                lat_hemi = self.gps_segments[4]

                # Longitude
                l_string = self.gps_segments[5]
                lon_degs = int(l_string[0:3])
                lon_mins = float(l_string[3:])
                lon_hemi = self.gps_segments[6]
            except ValueError:
                return False

            if lat_hemi not in self.__HEMISPHERES:
                return False

            if lon_hemi not in self.__HEMISPHERES:
                return False

            # Speed
            try:
                spd_knt = float(self.gps_segments[7])
            except ValueError:
                return False

            # Course
            try:
                if self.gps_segments[8]:
                    course = float(self.gps_segments[8])
                else:
                    course = 0.0
            except ValueError:
                return False

            # TODO - Add Magnetic Variation

            # Update Object Data
            self._latitude = [lat_degs, lat_mins, lat_hemi]
            self._longitude = [lon_degs, lon_mins, lon_hemi]
            # Include mph and hm/h
            self.speed = [spd_knt, spd_knt * 1.151, spd_knt * 1.852]
            self.course = course
            self.valid = True

            # Update Last Fix Time
            self.new_fix_time()

        else:  # Clear Position Data if Sentence is 'Invalid'
            self._latitude = [0, 0.0, 'N']
            self._longitude = [0, 0.0, 'W']
            self.speed = [0.0, 0.0, 0.0]
            self.course = 0.0
            self.valid = False

        return True

    def gpgll(self):
        """Parse Geographic Latitude and Longitude (GLL)Sentence. Updates UTC timestamp, latitude,
        longitude, and fix status"""

        # UTC Timestamp
        try:
            utc_string = self.gps_segments[5]

            if utc_string:  # Possible timestamp found
                hours = (int(utc_string[0:2]) + self.local_offset) % 24
                minutes = int(utc_string[2:4])
                seconds = float(utc_string[4:])
                self.timestamp = (hours, minutes, seconds)
            else:  # No Time stamp yet
                self.timestamp = (0, 0, 0)

        except ValueError:  # Bad Timestamp value present
            return False

        # Check Receiver Data Valid Flag
        if self.gps_segments[6] == 'A':  # Data from Receiver is Valid/Has Fix

            # Longitude / Latitude
            try:
                # Latitude
                l_string = self.gps_segments[1]
                lat_degs = int(l_string[0:2])
                lat_mins = float(l_string[2:])
                lat_hemi = self.gps_segments[2]

                # Longitude
                l_string = self.gps_segments[3]
                lon_degs = int(l_string[0:3])
                lon_mins = float(l_string[3:])
                lon_hemi = self.gps_segments[4]
            except ValueError:
                return False

            if lat_hemi not in self.__HEMISPHERES:
                return False

            if lon_hemi not in self.__HEMISPHERES:
                return False

            # Update Object Data
            self._latitude = [lat_degs, lat_mins, lat_hemi]
            self._longitude = [lon_degs, lon_mins, lon_hemi]
            self.valid = True

            # Update Last Fix Time
            self.new_fix_time()

        else:  # Clear Position Data if Sentence is 'Invalid'
            self._latitude = [0, 0.0, 'N']
            self._longitude = [0, 0.0, 'W']
            self.valid = False

        return True

    def gpvtg(self):
        """Parse Track Made Good and Ground Speed (VTG) Sentence. Updates speed and course"""
        try:
            course = float(self.gps_segments[1])
            spd_knt = float(self.gps_segments[5])
        except ValueError:
            return False

        # Include mph and km/h
        self.speed = (spd_knt, spd_knt * 1.151, spd_knt * 1.852)
        self.course = course
        return True

    def gpgga(self):
        """Parse Global Positioning System Fix Data (GGA) Sentence. Updates UTC timestamp, latitude, longitude,
        fix status, satellites in use, Horizontal Dilution of Precision (HDOP), altitude, geoid height and fix status"""

        try:
            # UTC Timestamp
            utc_string = self.gps_segments[1]

            # Skip timestamp if receiver doesn't have on yet
            if utc_string:
                hours = (int(utc_string[0:2]) + self.local_offset) % 24
                minutes = int(utc_string[2:4])
                seconds = float(utc_string[4:])
            else:
                hours = 0
                minutes = 0
                seconds = 0.0

            # Number of Satellites in Use
            satellites_in_use = int(self.gps_segments[7])

            # Get Fix Status
            fix_stat = int(self.gps_segments[6])

        except (ValueError, IndexError):
            return False

        try:
            # Horizontal Dilution of Precision
            hdop = float(self.gps_segments[8])
        except (ValueError, IndexError):
            hdop = 0.0

        # Process Location and Speed Data if Fix is GOOD
        if fix_stat:

            # Longitude / Latitude
            try:
                # Latitude
                l_string = self.gps_segments[2]
                lat_degs = int(l_string[0:2])
                lat_mins = float(l_string[2:])
                lat_hemi = self.gps_segments[3]

                # Longitude
                l_string = self.gps_segments[4]
                lon_degs = int(l_string[0:3])
                lon_mins = float(l_string[3:])
                lon_hemi = self.gps_segments[5]
            except ValueError:
                return False

            if lat_hemi not in self.__HEMISPHERES:
                return False

            if lon_hemi not in self.__HEMISPHERES:
                return False

            # Altitude / Height Above Geoid
            try:
                altitude = float(self.gps_segments[9])
                geoid_height = float(self.gps_segments[11])
            except ValueError:
                altitude = 0
                geoid_height = 0

            # Update Object Data
            self._latitude = [lat_degs, lat_mins, lat_hemi]
            self._longitude = [lon_degs, lon_mins, lon_hemi]
            self.altitude = altitude
            self.geoid_height = geoid_height

        # Update Object Data
        self.timestamp = [hours, minutes, seconds]
        self.satellites_in_use = satellites_in_use
        self.hdop = hdop
        self.fix_stat = fix_stat

        # If Fix is GOOD, update fix timestamp
        if fix_stat:
            self.new_fix_time()

        return True

    def gpgsa(self):
        """Parse GNSS DOP and Active Satellites (GSA) sentence. Updates GPS fix type, list of satellites used in
        fix calculation, Position Dilution of Precision (PDOP), Horizontal Dilution of Precision (HDOP), Vertical
        Dilution of Precision, and fix status"""

        # Fix Type (None,2D or 3D)
        try:
            fix_type = int(self.gps_segments[2])
        except ValueError:
            return False

        # Read All (up to 12) Available PRN Satellite Numbers
        sats_used = []
        for sats in range(12):
            sat_number_str = self.gps_segments[3 + sats]
            if sat_number_str:
                try:
                    sat_number = int(sat_number_str)
                    sats_used.append(sat_number)
                except ValueError:
                    return False
            else:
                break

        # PDOP,HDOP,VDOP
        try:
            pdop = float(self.gps_segments[15])
            hdop = float(self.gps_segments[16])
            vdop = float(self.gps_segments[17])
        except ValueError:
            return False

        # Update Object Data
        self.fix_type = fix_type

        # If Fix is GOOD, update fix timestamp
        if fix_type > self.__NO_FIX:
            self.new_fix_time()

        self.satellites_used = sats_used
        self.hdop = hdop
        self.vdop = vdop
        self.pdop = pdop

        return True

    def gpgsv(self):
        """Parse Satellites in View (GSV) sentence. Updates number of SV Sentences,the number of the last SV sentence
        parsed, and data on each satellite present in the sentence"""
        try:
            num_sv_sentences = int(self.gps_segments[1])
            current_sv_sentence = int(self.gps_segments[2])
            sats_in_view = int(self.gps_segments[3])
        except ValueError:
            return False

        # Create a blank dict to store all the satellite data from this sentence in:
        # satellite PRN is key, tuple containing telemetry is value
        satellite_dict = dict()

        # Calculate  Number of Satelites to pull data for and thus how many segment positions to read
        if num_sv_sentences == current_sv_sentence:
            # Last sentence may have 1-4 satellites; 5 - 20 positions
            sat_segment_limit = (sats_in_view - ((num_sv_sentences - 1) * 4)) * 5
        else:
            sat_segment_limit = 20  # Non-last sentences have 4 satellites and thus read up to position 20

        # Try to recover data for up to 4 satellites in sentence
        for sats in range(4, sat_segment_limit, 4):

            # If a PRN is present, grab satellite data
            if self.gps_segments[sats]:
                try:
                    sat_id = int(self.gps_segments[sats])
                except (ValueError,IndexError):
                    return False

                try:  # elevation can be null (no value) when not tracking
                    elevation = int(self.gps_segments[sats+1])
                except (ValueError,IndexError):
                    elevation = None

                try:  # azimuth can be null (no value) when not tracking
                    azimuth = int(self.gps_segments[sats+2])
                except (ValueError,IndexError):
                    azimuth = None

                try:  # SNR can be null (no value) when not tracking
                    snr = int(self.gps_segments[sats+3])
                except (ValueError,IndexError):
                    snr = None
            # If no PRN is found, then the sentence has no more satellites to read
            else:
                break

            # Add Satellite Data to Sentence Dict
            satellite_dict[sat_id] = (elevation, azimuth, snr)

        # Update Object Data
        self.total_sv_sentences = num_sv_sentences
        self.last_sv_sentence = current_sv_sentence
        self.satellites_in_view = sats_in_view

        # For a new set of sentences, we either clear out the existing sat data or
        # update it as additional SV sentences are parsed
        if current_sv_sentence == 1:
            self.satellite_data = satellite_dict
        else:
            self.satellite_data.update(satellite_dict)

        return True

    ##########################################
    # Data Stream Handler Functions
    ##########################################

    def new_sentence(self):
        """Adjust Object Flags in Preparation for a New Sentence"""
        self.gps_segments = ['']
        self.active_segment = 0
        self.crc_xor = 0
        self.sentence_active = True
        self.process_crc = True
        self.char_count = 0

    def update(self, new_char):
        """Process a new input char and updates GPS object if necessary based on special characters ('$', ',', '*')
        Function builds a list of received string that are validate by CRC prior to parsing by the  appropriate
        sentence function. Returns sentence type on successful parse, None otherwise"""

        valid_sentence = False

        # Validate new_char is a printable char
        ascii_char = ord(new_char)

        if 10 <= ascii_char <= 126:
            self.char_count += 1

            # Write Character to log file if enabled
            if self.log_en:
                self.write_log(new_char)

            # Check if a new string is starting ($)
            if new_char == '$':
                self.new_sentence()
                return None

            elif self.sentence_active:

                # Check if sentence is ending (*)
                if new_char == '*':
                    self.process_crc = False
                    self.active_segment += 1
                    self.gps_segments.append('')
                    return None

                # Check if a section is ended (,), Create a new substring to feed
                # characters to
                elif new_char == ',':
                    self.active_segment += 1
                    self.gps_segments.append('')

                # Store All Other printable character and check CRC when ready
                else:
                    self.gps_segments[self.active_segment] += new_char

                    # When CRC input is disabled, sentence is nearly complete
                    if not self.process_crc:

                        if len(self.gps_segments[self.active_segment]) == 2:
                            try:
                                final_crc = int(self.gps_segments[self.active_segment], 16)
                                if self.crc_xor == final_crc:
                                    valid_sentence = True
                                else:
                                    self.crc_fails += 1
                            except ValueError:
                                pass  # CRC Value was deformed and could not have been correct

                # Update CRC
                if self.process_crc:
                    self.crc_xor ^= ascii_char

                # If a Valid Sentence Was received and it's a supported sentence, then parse it!!
                if valid_sentence:
                    self.clean_sentences += 1  # Increment clean sentences received
                    self.sentence_active = False  # Clear Active Processing Flag

                    if self.gps_segments[0] in self.supported_sentences:

                        # parse the Sentence Based on the message type, return True if parse is clean
                        if self.supported_sentences[self.gps_segments[0]](self):

                            # Let host know that the GPS object was updated by returning parsed sentence type
                            self.parsed_sentences += 1
                            return self.gps_segments[0]

                # Check that the sentence buffer isn't filling up with Garage waiting for the sentence to complete
                if self.char_count > self.SENTENCE_LIMIT:
                    self.sentence_active = False

        # Tell Host no new sentence was parsed
        return None

    def new_fix_time(self):
        """Updates a high resolution counter with current time when fix is updated. Currently only triggered from
        GGA, GSA and RMC sentences"""
        try:
            self.fix_time = utime.ticks_ms()
        except NameError:
            self.fix_time = time.time()

    #########################################
    # User Helper Functions
    # These functions make working with the GPS object data easier
    #########################################

    def satellite_data_updated(self):
        """
        Checks if the all the GSV sentences in a group have been read, making satellite data complete
        :return: boolean
        """
        if self.total_sv_sentences > 0 and self.total_sv_sentences == self.last_sv_sentence:
            return True
        else:
            return False

    def satellites_visible(self):
        """
        Returns a list of of the satellite PRNs currently visible to the receiver
        :return: list
        """
        return list(self.satellite_data.keys())

    def time_since_fix(self):
        """Returns number of millisecond since the last sentence with a valid fix was parsed. Returns 0 if
        no fix has been found"""

        # Test if a Fix has been found
        if self.fix_time == 0:
            return -1

        # Try calculating fix time using utime; if not running MicroPython
        # time.time() returns a floating point value in secs
        try:
            current = utime.ticks_diff(utime.ticks_ms(), self.fix_time)
        except NameError:
            current = (time.time() - self.fix_time) * 1000  # ms

        return current

    def compass_direction(self):
        """
        Determine a cardinal or inter-cardinal direction based on current course.
        :return: string
        """
        # Calculate the offset for a rotated compass
        if self.course >= 348.75:
            offset_course = 360 - self.course
        else:
            offset_course = self.course + 11.25

        # Each compass point is separated by 22.5 degrees, divide to find lookup value
        dir_index = floor(offset_course / 22.5)

        final_dir = self.__DIRECTIONS[dir_index]

        return final_dir

    def latitude_string(self):
        """
        Create a readable string of the current latitude data
        :return: string
        """
        if self.coord_format == 'dd':
            formatted_latitude = self.latitude
            lat_string = str(formatted_latitude[0]) + '° ' + str(self._latitude[2])
        elif self.coord_format == 'dms':
            formatted_latitude = self.latitude
            lat_string = str(formatted_latitude[0]) + '° ' + str(formatted_latitude[1]) + "' " + str(formatted_latitude[2]) + '" ' + str(formatted_latitude[3])
        else:
            lat_string = str(self._latitude[0]) + '° ' + str(self._latitude[1]) + "' " + str(self._latitude[2])
        return lat_string

    def longitude_string(self):
        """
        Create a readable string of the current longitude data
        :return: string
        """
        if self.coord_format == 'dd':
            formatted_longitude = self.longitude
            lon_string = str(formatted_longitude[0]) + '° ' + str(self._longitude[2])
        elif self.coord_format == 'dms':
            formatted_longitude = self.longitude
            lon_string = str(formatted_longitude[0]) + '° ' + str(formatted_longitude[1]) + "' " + str(formatted_longitude[2]) + '" ' + str(formatted_longitude[3])
        else:
            lon_string = str(self._longitude[0]) + '° ' + str(self._longitude[1]) + "' " + str(self._longitude[2])
        return lon_string

    def speed_string(self, unit='kph'):
        """
        Creates a readable string of the current speed data in one of three units
        :param unit: string of 'kph','mph, or 'knot'
        :return:
        """
        if unit == 'mph':
            speed_string = str(self.speed[1]) + ' mph'

        elif unit == 'knot':
            if self.speed[0] == 1:
                unit_str = ' knot'
            else:
                unit_str = ' knots'
            speed_string = str(self.speed[0]) + unit_str

        else:
            speed_string = str(self.speed[2]) + ' km/h'

        return speed_string

    def date_string(self, formatting='s_mdy', century='20'):
        """
        Creates a readable string of the current date.
        Can select between long format: Januray 1st, 2014
        or two short formats:
        11/01/2014 (MM/DD/YYYY)
        01/11/2014 (DD/MM/YYYY)
        :param formatting: string 's_mdy', 's_dmy', or 'long'
        :param century: int delineating the century the GPS data is from (19 for 19XX, 20 for 20XX)
        :return: date_string  string with long or short format date
        """

        # Long Format Januray 1st, 2014
        if formatting == 'long':
            # Retrieve Month string from private set
            month = self.__MONTHS[self.date[1] - 1]

            # Determine Date Suffix
            if self.date[0] in (1, 21, 31):
                suffix = 'st'
            elif self.date[0] in (2, 22):
                suffix = 'nd'
            elif self.date[0] == (3, 23):
                suffix = 'rd'
            else:
                suffix = 'th'

            day = str(self.date[0]) + suffix  # Create Day String

            year = century + str(self.date[2])  # Create Year String

            date_string = month + ' ' + day + ', ' + year  # Put it all together

        else:
            # Add leading zeros to day string if necessary
            if self.date[0] < 10:
                day = '0' + str(self.date[0])
            else:
                day = str(self.date[0])

            # Add leading zeros to month string if necessary
            if self.date[1] < 10:
                month = '0' + str(self.date[1])
            else:
                month = str(self.date[1])

            # Add leading zeros to year string if necessary
            if self.date[2] < 10:
                year = '0' + str(self.date[2])
            else:
                year = str(self.date[2])

            # Build final string based on desired formatting
            if formatting == 's_dmy':
                date_string = day + '/' + month + '/' + year

            else:  # Default date format
                date_string = month + '/' + day + '/' + year

        return date_string

    # All the currently supported NMEA sentences
    supported_sentences = {'GPRMC': gprmc, 'GLRMC': gprmc,
                           'GPGGA': gpgga, 'GLGGA': gpgga,
                           'GPVTG': gpvtg, 'GLVTG': gpvtg,
                           'GPGSA': gpgsa, 'GLGSA': gpgsa,
                           'GPGSV': gpgsv, 'GLGSV': gpgsv,
                           'GPGLL': gpgll, 'GLGLL': gpgll,
                           'GNGGA': gpgga, 'GNRMC': gprmc,
                           'GNVTG': gpvtg, 'GNGLL': gpgll,
                           'GNGSA': gpgsa,
                          }


"""

MICROPYTHON CLASS MODULE CODE
Taken from https://github.com/inmcm/micropyGPS/blob/master/micropyGPS.py

"""

class Subsystem(object):
    def __init__(self, subsystem_type, power_estimator_adc_pin_name, power_estimator_adc_gpio_pin_name, telemetry_module_uart_pin_number, gps_module_uart_number, vibration_motor_pin_name, buzzer_pin_name):
        self.subsystem_type = subsystem_type
        self.power_estimator = Subsystem.PowerEstimator(adc_pin_name=power_estimator_adc_pin_name, gpio_pin_name=power_estimator_adc_gpio_pin_name)
        self.telemetry_module = Subsystem.TelemetryModule(uart_number=telemetry_module_uart_pin_number)
        self.gps_module = Subsystem.GPS_Module(uart_number=gps_module_uart_number)
        self.buzzer_pin = pyb.Pin(buzzer_pin_name, pyb.Pin.OUT_PP)
        self.vibration_motor_pin = pyb.Pin(vibration_motor_pin_name, pyb.Pin.OUT_PP)
        self.stop_flag = 0
        self.armed = 0
        self.time_since_disarm = 0

        if self.subsystem_type == 'key_fob':
            # Set up alarm off button
            pyb.Switch().callback(lambda: self.disarm_alarm())
        elif self.subsystem_type == 'car_seat':
            # TODO UPDATE!!
            # Set up alarm off button
            pyb.Switch().callback(lambda: self.disarm_alarm())

    def run(self):
        distance_threshold = 10 # 10 meters
        max_communication_wait_time = 15 # max communication wait time is 15 seconds
        rearm_time = 900 # rearm in 15 minutes after disarming
        percent_power_remaining = self.power_estimator.get_power_estimate()

        while True:
            # IF there is enough power, run gps and telemetry threads
            if percent_power_remaining > 15:
                if self.subsystem_type == 'key_fob':
                    _thread.start_new_thread( update_gps_thread, ("Update GPS Location Thread", self, 0.1) )
                    _thread.start_new_thread( telemetry_listen_thread, ("Telemetry Listen Thread", self, 0.1) )
                elif self.subsystem_type == 'car_seat':
                    _thread.start_new_thread( update_gps_thread, ("Update GPS Location Thread", self, 0.1) )
                    _thread.start_new_thread( transmit_location_thread, ("Transmit Location Thread", self, 0.2) )

            if self.subsystem_type == "key_fob":
                # While there is enough power
                while percent_power_remaining > 15:
                    print(self.subsystem_type, " is running.  Current location", self.gps_module.get_location())

                    # If there has been a message recent enough
                    if self.telemetry_module.time_since_last_message < max_communication_wait_time:
                        if self.telemetry_module.time_since_disarm < rearm_time:
                            self.armed = 0
                        else:
                            # Calculate the distance between subsystems
                            distance_between_subsystems = self.calculate_distance_between_subsystems()

                            # If alarm is armed
                            if self.armed:
                                # If distance is greater than threshold
                                if distance_between_subsystems > distance_threshold:
                                    # Sound alarm
                                    self.sound_alarm()
                                else:
                                    # Ensure alarm is quiet
                                    self.quiet_alarm()
                            else:
                                # If distance is less than threshold, make sure alarm is armed.
                                if distance_between_subsystems < distance_threshold:
                                    self.armed = 1
                    # IF it has been too long since a message
                    else:
                        # And alarm is armed. Sound alarm.
                        if self.armed:
                            self.sound_alarm()
                        # Else alarm is not armed, ensure it is quiet.
                        else:
                            self.quiet_alarm()

                    # Get updated power estimate.
                    percent_power_remaining = self.power_estimator.get_power_estimate()

                    time.sleep(1)
            elif self.subsystem_type == 'car_seat':
                # While there is enough power
                while percent_power_remaining > 15:
                    # Get updated power estimate.
                    percent_power_remaining = self.power_estimator.get_power_estimate()

                    time.sleep(5)

            pyb.LED(1).on()
            self.stop_flag = 1

            while percent_power_remaining <= 15:
                print("Power is low running on reserves")
                percent_power_remaining = self.power_estimator.get_power_estimate()
                pyb.LED(1).toggle()
                time.sleep(1)
            pyb.LED(1).off()

    def sound_alarm(self):
        self.buzzer_pin.high()
        self.vibration_motor_pin.high()

    def quiet_alarm(self):
        self.buzzer_pin.low()
        self.vibration_motor_pin.low()

    def disarm_alarm(self):
        self.armed = 0
        self.time_since_disarm = 0
        self.quiet_alarm()

    def calculate_distance_between_subsystems(self):
        my_latitude, my_longitude = self.gps_module.get_location()
        other_latitude = Subsystem.TelemetryModule.last_latitude
        other_longitude = Subsystem.TelemetryModule.last_longitude

        a = sin( radians(other_latitude - my_latitude) / 2 )**2 + cos(radians(my_latitude)) * cos(radians(other_latitude)) + sin( radians(other_longitude - my_longitude) / 2)**2
        c = 2 * atan2( sqrt(a), sqrt(1-a) )
        # the earth's radius is 6,371 km
        return 6371000 * c

    class PowerEstimator(object):
        def __init__(self, adc_pin_name, gpio_pin_name):
            self.adc_pin = pyb.ADC(pyb.Pin(adc_pin_name))
            self.gpio_pin = pyb.Pin(gpio_pin_name)
            self.starting_counts = None
            self.percent_power_remaining = None

        def get_power_estimate(self):
            self.gpio_pin.high()

            adc_counts = self.adc_pin.read()

            self.gpio_pin.low()

            if self.starting_counts is None:
                if adc_counts == 0:
                    self.starting_counts = 1
                else:
                    self.starting_counts = adc_counts
                self.percent_power_remaining = 100.0
            else:
                self.percent_power_remaining = adc_counts / self.starting_counts * 100


            return self.percent_power_remaining

    class TelemetryModule(object):
        def __init__(self, uart_number):
            self.uart = pyb.UART(uart_number, 9600)
            self.last_longitude = None
            self.last_latitude = None
            self.time_since_disarm = 0
            self.time_since_last_message = 15

        def send_message(self, message):
            self.uart.write(message)

        @staticmethod
        def decode_message(message):
            message = message.split(",")
            armed = int(message[0][1:])
            latitude = float(message[1])
            longitude = float(message[3][:-2])

            return armed, latitude, longitude

    class GPS_Module(object):
        def __init__(self, uart_number):
            self.uart = pyb.UART(uart_number, 9600)
            self.gps = MicropyGPS()

        def get_location(self):
            return (Subsystem.GPS_Module.convert_coordinate_to_decimal(self.gps.latitude), Subsystem.GPS_Module.convert_coordinate_to_decimal(self.gps.longitude))

        @staticmethod
        def convert_coordinate_to_decimal(coordinate_list):
            degrees = float(coordinate_list[0])
            minutes = float(coordinate_list[1])
            return degrees + minutes / 60

def telemetry_listen_thread(threadName, subsystem, delay):
    print("Starting thread ", threadName)

    while not subsystem.stop_flag:
        if subsystem.telemetry_module.uart.any():
            armed_state, subsystem.telemetry_module.last_longitude, subsystem.telemetry_module.last_latitude = subsystem.TelemetryModule.decode_message(subsystem.telemetry_module.uart.read_line())
            subsystem.telemetry_module.time_since_last_message = 0

            if not armed_state:
                subsystem.armed = 0
                subsystem.telemetry_module.time_since_disarm = 0
            else:
                subsystem.telemetry_module.time_since_disarm += delay
                time.sleep(delay)
        else:
            subsystem.telemetry_module.time_since_last_message += delay
            time.sleep(delay)

def update_gps_thread(threadName, subsystem, delay):
    print("Starting thread ", threadName)

    while not subsystem.stop_flag:
        if subsystem.gps_module.uart.any():
            subsystem.gps_module.gps.update(chr(subsystem.gps_module.uart.readchar()))
        else:
            time.sleep(delay)

def transmit_location_thread(threadName, subsystem, delay):
    print("Starting thread ", threadName)
    time_to_rearm = 180  # 3 minutes

    while not subsystem.stop_flag:
        subsystem_latitude, subsystem_longitude = subsystem.gps_module.get_location()

        if subsystem.time_since_disarm < time_to_rearm:
            subsystem.time_since_disarm += delay
        else:
            subsystem.armed = 1
            subsystem.time_since_disarm += delay

        subsystem.telemetry_module.send_message("(" + str(subsystem.armed) + "," str(subsystem_latitude) + "," + str(subsystem_longitude) + ")\n")

        time.sleep(delay)


#car_seat_subsystem = Subsystem(subsystem_type='car_seat', power_estimator_adc_pin_name='X1', power_estimator_adc_gpio_pin_name='X3', telemetry_module_uart_pin_number=1, gps_module_uart_number=3, vibration_motor_pin_name='X5', buzzer_pin_name='X2')
key_fob_subsystem = Subsystem(subsystem_type='key_fob', power_estimator_adc_pin_name='X2', power_estimator_adc_gpio_pin_name='X1', telemetry_module_uart_pin_number=3, gps_module_uart_number=1, vibration_motor_pin_name='Y8', buzzer_pin_name='X4')
key_fob_subsystem.run()
