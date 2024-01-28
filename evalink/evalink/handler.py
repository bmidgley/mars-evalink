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

    if message['type'] == 'position':
        lat = payload['latitude_i'] / 10000000
        lon = payload['longitude_i']  / 10000000
        position_log = PositionLog(
            station=station,
            latitude=lat,
            longitude=lon,
            altitude=payload.get('altitude'),
            ground_speed=payload.get('ground_speed'),
            ground_track=payload.get('ground_track'),
            updated_at=time)
        position_log.save()
        return

    if message['type'] == 'telemetry':
        telemetry_log = TelemetryLog(
            station=station,
            battery_level=payload.get('battery_level'),
            temperature=payload.get('temperature'),
            humidity=payload.get('relative_humidity'),
            current=payload.get('current'),
            voltage=payload.get('voltage'),
            barometric_pressure=payload.get('barometric_pressure'),
            updated_at=time)
        telemetry_log.save()
        return

    if message['type'] == 'text':
        text_log = TextLog(
            station=station,
            text=payload.get('text'),
            updated_at=time)
        text_log.save()
        return

def iso_time(seconds):
    tm = datetime.fromtimestamp(seconds)
    tm = tm.astimezone(pytz.utc)
    tm = tm.isoformat()
    return tm
