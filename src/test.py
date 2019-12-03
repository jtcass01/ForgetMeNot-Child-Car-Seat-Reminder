from math import cos, radians, sin, asin, sqrt
from haversine import haversine

def calculate_distance_between_subsystems():
    # convert all latitudes/longitudes from decimal degrees to radians
    lat1, lng1, lat2, lng2 = map(radians, (38.21273, 85.76018, 38.2126, 85.75976))

    # calculate haversine
    lat = lat2 - lat1
    lng = lng2 - lng1
    d = sin(lat * 0.5) ** 2 + cos(lat1) * cos(lat2) * sin(lng * 0.5) ** 2
    return 2 * 6371.0088 * asin(sqrt(d)) * 1000

def haversine2(lat1, lon1, lat2, lon2):
    R = 6372.8  # Earth radius in kilometers

    dLat = radians(lat2 - lat1)
    dLon = radians(lon2 - lon1)
    lat1 = radians(lat1)
    lat2 = radians(lat2)

    a = sin(dLat / 2)**2 + cos(lat1) * cos(lat2) * sin(dLon / 2)**2
    c = 2 * asin(sqrt(a))

    return R * c

def calculate_distance_between_subsystems2():
    my_latitude, my_longitude = (38.21273, 85.76018)
    other_latitude = 38.21232
    other_longitude = 85.76064

    if my_latitude == 0 or my_longitude == 0 or other_latitude == 0 or other_longitude == 0:
        return 0
    else:
        R = 6372.8  # Earth radius in kilometers

        dLat = radians(other_latitude - my_latitude)
        print("dLat", dLat)
        dLon = radians(other_longitude - my_longitude)
        print("dLon", dLon)
        lat1 = radians(my_latitude)
        print("lat1", lat1)
        lat2 = radians(other_latitude)
        print("lat2", lat2)

        a = sin(dLat / 2)**2 + cos(lat1) * cos(lat2) * sin(dLon / 2)**2
        print("a", a)
        c = 2 * asin(sqrt(a))
        print("c", c)

        return R * c * 1000

print("haversine", haversine((38.21273, 85.76018), (38.2126, 85.75976)))
print("haversine2", haversine2(38.21273, 85.76018, 38.21232, 85.76064))
print(calculate_distance_between_subsystems2())

38.21273, 85.76018
38.21232, 85.76064
