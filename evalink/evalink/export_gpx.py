import sys
import xmltodict
from datetime import datetime
# import dateutil.parser
# import pytz

class ExportGpx:
    def write_points(points_hash, waypoints_list):
        station_names = list(points_hash.keys())
        tracks = []
        for station_name in station_names:
            tracks.append({
                    'name': station_name,
                    'trkseg': {
                        'trkpt': points_hash[station_name]
                    }
            })
        waypoints = []
        for waypoint in waypoints_list:
            entry = {
                '@lat': waypoint['latitude'].toFixed(7),
                '@lon': waypoint['longitude'].toFixed(7),
                'time': waypoint['updated_at'],
                'name': waypoint['text'],
            }
            if waypoint['altitude']:
                entry['ele'] = waypoint['altitude'].toFixed(7)
            waypoints.append(entry)

        gpx = {
            'gpx': {
                '@xmlns': "http://www.topografix.com/GPX/1/1", 
                '@xmlns:gpxx': "http://www.garmin.com/xmlschemas/GpxExtensions/v3", 
                '@xmlns:gpxtpx': "http://www.garmin.com/xmlschemas/TrackPointExtension/v1", 
                '@creator': "Oregon 400t", 
                '@version': "1.1", 
                '@xmlns:xsi': "http://www.w3.org/2001/XMLSchema-instance", 
                '@xsi:schemaLocation': "http://www.topografix.com/GPX/1/1 http://www.topografix.com/GPX/1/1/gpx.xsd http://www.garmin.com/xmlschemas/GpxExtensions/v3 http://www.garmin.com/xmlschemas/GpxExtensionsv3.xsd http://www.garmin.com/xmlschemas/TrackPointExtension/v1 http://www.garmin.com/xmlschemas/TrackPointExtensionv1.xsd",
                'wpt': waypoints,
                'trk': tracks
            }
        }

        with open(f'file.gpx', 'w') as gpx_file:
            gpx_file.write(xmltodict.unparse(gpx, pretty=True))


        # record temperatures using 'extensions', 'gpxtpx:TrackPointExtension', 0, 'gpxtpx:atemp'
'''
# todo: move to unit tests
ines = [
    "station1,38.406372,-110.791542,1359.0,2024-05-08T18:47:40Z",
    "station2,38.406372,-110.791542,1359.0,2024-05-08T18:47:40Z",
]
points_hash = {}
for line in lines:
    message = line.strip().split(",")
    station_name = message[0]
    iso = message[4]
    entry = {
        '@lat': message[1],
        '@lon': message[2],
        'ele': message[3],
        'time': iso,
    }
    if station_name not in points_hash: points_hash[station_name] = []
    points_hash[station_name].append(entry)

ExportGpx.write_points(points_hash, [])
'''