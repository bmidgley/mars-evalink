import django
django.setup()

from evalink.models import *
from datetime import datetime
import pytz

def process_message(message):
    number = message['from']
    payload = message['payload']
    tz = pytz.timezone("US/Mountain")
    time = datetime.fromtimestamp(message['timestamp'], tz)

    station = Station.objects.filter(hardware_number=number).first()

    if message['type'] == 'nodeinfo':
        if station == None:
            hardware = Hardware.objects.filter(hardware_type=payload['hardware']).first()
            if hardware == None:
                hardware = Hardware(hardware_type=payload['hardware'], name='tbeam', station_type='infrastructure')
                hardware.save()
            station = Station(
                hardware=hardware,
                hardware_number=number,
                hardware_node=payload['id'],
                station_type=hardware.station_type,
                short_name=payload['shortname'])
        station.updated_at = time
        station.name = payload['longname']
        station.save()
        return

    if station == None: return
    if station.features == None: station.features = {
        "type": "Feature",
        "properties": {
            "name": station.name,
            "label": station.name,
            "time": iso_time(message['timestamp']),
            "hardware": station.hardware.hardware_type,
            "node_type": station.station_type,
            "altitude": None,
            "ground_speed": None,
            "ground_track": None,
            "temperature": None,
            "relative_humidity": None,
            "barometric_pressure": None,
            "battery_level": None,
            "voltage": None,
            "current": None,
        },
        "geometry": { "type": "Point" },
        "id": str(station.id)
    }

    if message['type'] == 'position':
        lat = payload['latitude_i'] / 10000000
        lon = payload['longitude_i']  / 10000000
        ground_track = payload.get('ground_track')
        if ground_track: ground_track = ground_track / 100000
        position_log = PositionLog(
            station=station,
            latitude=lat,
            longitude=lon,
            altitude=payload.get('altitude'),
            ground_speed=payload.get('ground_speed'),
            ground_track=ground_track,
            updated_at=time)
        position_log.save()
        station.features["geometry"]["coordinates"] = [lat, lon]
        station.features["properties"]["altitude"] = position_log.altitude or station.features["properties"]["altitude"]
        station.features["properties"]["ground_speed"] = position_log.ground_speed or station.features["properties"]["ground_speed"]
        station.features["properties"]["ground_track"] = position_log.ground_track or station.features["properties"]["ground_track"]
        station.save()
        log_measurements(station, station.features, time)
        return

    if message['type'] == 'telemetry':
        telemetry_log = TelemetryLog(
            station=station,
            temperature=payload.get('temperature'),
            relative_humidity=payload.get('relative_humidity'),
            barometric_pressure=payload.get('barometric_pressure'),
            battery_level=payload.get('battery_level'),
            voltage=payload.get('voltage'),
            current=payload.get('current'),
            updated_at=time)
        telemetry_log.save()
        station.features["properties"]["temperature"] = telemetry_log.temperature or station.features["properties"]["temperature"]
        station.features["properties"]["relative_humidity"] = telemetry_log.relative_humidity or station.features["properties"]["relative_humidity"]
        station.features["properties"]["barometric_pressure"] = telemetry_log.barometric_pressure or station.features["properties"]["barometric_pressure"]
        station.features["properties"]["battery_level"] = telemetry_log.battery_level or station.features["properties"]["battery_level"]
        station.features["properties"]["voltage"] = telemetry_log.voltage or station.features["properties"]["voltage"]
        station.features["properties"]["current"] = telemetry_log.current or station.features["properties"]["current"]
        station.save()
        log_measurements(station, station.features, time)
        return

    if message['type'] == 'text':
        text_log = TextLog(
            station=station,
            text=payload.get('text'),
            updated_at=time)
        text_log.save()
        return

def log_measurements(station, features, time):
    measure = StationMeasure(station=station, features=features, updated_at=time).save()
    print(f'logging: {measure}')

def iso_time(seconds):
    tm = datetime.fromtimestamp(seconds)
    tm = tm.astimezone(pytz.utc)
    tm = tm.isoformat()
    return tm