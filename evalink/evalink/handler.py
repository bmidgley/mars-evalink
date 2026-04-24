import django
django.setup()

from evalink.models import *
from django.db import IntegrityError
from datetime import datetime, timezone, timedelta
from django.utils import timezone as django_timezone
import pytz
import os

def process_message(message):
    number = message['from']
    payload = message['payload']
    campus = Campus.objects.get(name=os.getenv('CAMPUS'))
    tz = pytz.timezone(campus.time_zone)
    current_time = datetime.now(timezone.utc)
    today = datetime.now(tz).date()
    station = Station.objects.filter(hardware_number=number).first()

    if message['type'] == 'nodeinfo':
        # print(message)
        if station == None:
            station_profile = StationProfile.objects.first()
            if station_profile == None:
                station_profile = StationProfile(name="default", configuration={"firmware": "2.2.17"}, compatible_firmwares=["2.2.17"])
                station_profile.save()
            hardware = Hardware.objects.filter(hardware_type=payload['hardware']).first()
            if hardware == None:
                hardware = Hardware(hardware_type=payload['hardware'], name='tbeam', station_type='infrastructure')
                try:
                    hardware.save()
                except django.db.utils.IntegrityError as e:
                    return
            station = Station(
                hardware=hardware,
                station_profile=station_profile,
                hardware_number=number,
                hardware_node=payload['id'],
                station_type=hardware.station_type,
                short_name=(payload['shortname'] or 'blank!').replace('\x00', ''))
            station.updated_at = current_time
            try:
                print(f'adding new station {station} at {current_time} number {number}')
                station.save()
            except django.db.utils.IntegrityError as e:
                print(e)
                return
        station.updated_at = current_time
        station.name = payload['longname'] or 'blank'
        station.name = station.name.replace("\x00", "")
        if station.features == None: station.features = {}
        if "properties" not in station.features: station.features["properties"] = {}
        station.features["properties"]["name"] = station.name
        station.features["properties"]["time"] = iso_time(message['timestamp'])
        station.save()
        return

    if station == None:
        # print(f'skipping this message because we do not know the station: {message}')
        return

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
            "wind_direction": None,
            "wind_speed": None,
            "wind_gust": None,
            "wind_lull": None,
            "battery_level": None,
            "voltage": None,
            "current": None,
            "texts": [],
        },
        "geometry": { "type": "Point" },
        "id": str(station.id)
    }
    if "texts" not in station.features["properties"]: station.features["properties"]["texts"] = [] # remove
    station.features["properties"]["node_type"] = station.station_type

    if message['type'] == 'position':
        timestamp = payload.get('timestamp', payload.get('time'))
        if timestamp:
            timestamp = datetime.fromtimestamp(timestamp)
            timestamp = tz.localize(timestamp)
        lat = payload['latitude_i'] / 10000000
        lon = payload['longitude_i']  / 10000000
        if round(lat, 3) == 0 and round(lon, 3) == 0: return
        ground_track = payload.get('ground_track')
        if ground_track: ground_track = ground_track / 100000
        fence = campus.inner_geofence
        position_log = PositionLog(
            station=station,
            latitude=lat,
            longitude=lon,
            altitude=payload.get('altitude'),
            ground_speed=payload.get('ground_speed'),
            ground_track=ground_track,
            timestamp=timestamp or current_time,
            updated_on=today,
            updated_at=current_time)
        # log this location if it's away from the hab, or if it represents returning to the hab, or position was blank
        if fence.outside(lat, lon) or station.last_position == None or station.outside(fence) or station.last_position.updated_on != today:
            position_log.save()
            station.last_position = position_log
        if "geometry" not in station.features: station.features["geometry"] = {"type": "Point"}
        station.features["type"] = "Feature"
        station.features["geometry"]["type"] = "Point"
        station.features["geometry"]["coordinates"] = [lon, lat]
        station.features["properties"]["altitude"] = position_log.altitude or station.features["properties"].get("altitude")
        station.features["properties"]["ground_speed"] = position_log.ground_speed or station.features["properties"].get("ground_speed")
        station.features["properties"]["ground_track"] = position_log.ground_track or station.features["properties"].get("ground_track")
        station.features["properties"]["node_type"] = station.hardware.station_type
        station.features["properties"]["time"] = iso_time(message['timestamp'])
        station.updated_at = current_time
        station.save()
        log_measurements(station, station.features, current_time)
        return

    if message['type'] == 'telemetry':
        telemetry_log = TelemetryLog(
            message_id=message['id'],
            station=station,
            position_log=station.last_position,
            temperature=payload.get('temperature'),
            relative_humidity=payload.get('relative_humidity'),
            barometric_pressure=payload.get('barometric_pressure'),
            wind_direction=payload.get('wind_direction'),
            wind_speed=payload.get('wind_speed'),
            wind_gust=payload.get('wind_gust'),
            wind_lull=payload.get('wind_lull'),
            battery_level=payload.get('battery_level'),
            voltage=payload.get('voltage'),
            current=payload.get('current'),
            updated_on=today,
            updated_at=current_time)
        try:
            telemetry_log.save()
        except IntegrityError as e:
            return
        station.features["properties"]["temperature"] = telemetry_log.temperature or station.features["properties"].get("temperature")
        station.features["properties"]["relative_humidity"] = telemetry_log.relative_humidity or station.features["properties"].get("relative_humidity")
        station.features["properties"]["barometric_pressure"] = telemetry_log.barometric_pressure or station.features["properties"].get("barometric_pressure")
        station.features["properties"]["wind_direction"] = telemetry_log.wind_direction or station.features["properties"].get("wind_direction")
        station.features["properties"]["wind_speed"] = telemetry_log.wind_speed or station.features["properties"].get("wind_speed")
        station.features["properties"]["wind_gust"] = telemetry_log.wind_gust or station.features["properties"].get("wind_gust")
        station.features["properties"]["wind_lull"] = telemetry_log.wind_lull or station.features["properties"].get("wind_lull")
        station.features["properties"]["battery_level"] = telemetry_log.battery_level or station.features["properties"].get("battery_level")
        station.features["properties"]["voltage"] = telemetry_log.voltage or station.features["properties"].get("voltage")
        station.features["properties"]["current"] = telemetry_log.current or station.features["properties"].get("current")
        station.features["properties"]["node_type"] = station.hardware.station_type
        station.features["properties"]["time"] = iso_time(message['timestamp'])
        station.updated_at = current_time
        station.save()
        log_measurements(station, station.features, current_time)
        return

    if message['type'] == 'text':
        text = payload.get('text').replace("\x00", "")
        print(f'@@text "{text}"')
        text_log = TextLog(
            station=station,
            position_log=station.last_position,
            serial_number=message.get("id"), # + (hash(text) % 100000),
            text=text,
            updated_at=current_time,
            updated_on=current_time.astimezone(tz).date())
        text_log.save()

        if "texts" not in station.features["properties"]: station.features["properties"]["texts"] = [] # remove
        station.features["properties"]["texts"].append({
            "text": text_log.text,
            "coordinates": station.features["geometry"].get("coordinates"),
            "updated_at": iso_time(message['timestamp']) })
        station.updated_at = current_time
        station.save()
        log_measurements(station, station.features, current_time)
        return

def log_measurements(station, features, current_time):
    measure = StationMeasure(station=station, features=features, updated_at=current_time)
    measure.save()

def iso_time(_seconds):
    # nodes are reporting current time incorrectly, so disregard and return now in iso
    return datetime.now().isoformat()

# ADS-B barometric/geometric altitudes (dump1090/readsb style) are in feet; store meters in DB.
FEET_TO_METERS = 0.3048

def process_aircraft(hex_code, message):
    def _as_float(value):
        try:
            if value is None:
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    def _parse_timestamp(value, fallback):
        if not value or not isinstance(value, str):
            return fallback
        try:
            parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        except ValueError:
            return fallback
        if parsed.tzinfo is None:
            return django_timezone.make_aware(parsed, django_timezone.utc)
        return parsed

    def _altitude_meters_from_message(msg, is_remoteid):
        if not isinstance(msg, dict):
            return None

        def _raw_value(key):
            raw = msg.get(key)
            if raw is None:
                return None
            if isinstance(raw, str):
                lowered = raw.strip().lower()
                if lowered in ('', 'ground'):
                    return None
            return _as_float(raw)

        if is_remoteid:
            for key in ('alt', 'altitude'):
                value = _raw_value(key)
                if value is not None:
                    return int(round(value))
            return None

        for key in ('alt_baro', 'alt_geom', 'altitude', 'alt'):
            feet = _raw_value(key)
            if feet is not None:
                return int(round(feet * FEET_TO_METERS))
        return None

    is_remoteid = isinstance(message, dict) and 'ID' in message

    # Accept lat/lon or latitude/longitude from aircraft / drone feeds
    lat = _as_float(message.get('lat', message.get('latitude')))
    lon = _as_float(message.get('lon', message.get('long', message.get('longitude'))))
    
    # Skip if no position data
    if lat is None or lon is None:
        # print(f'skipping aircraft {hex_code} because it has no position data')
        return
    
    def _save_aircraft_for_campus(campus):
        tz = pytz.timezone(campus.time_zone)
        current_time = datetime.now(timezone.utc)
        current_time_tz = current_time.astimezone(tz)
        today = current_time_tz.date()
        timestamp = _parse_timestamp(message.get('iso'), current_time)

        aircraft, created = Aircraft.objects.get_or_create(
            hex=hex_code,
            defaults={
                'campus': campus,
                'features': message,
                'updated_at': current_time,
                'updated_on': today,
            }
        )

        prev_features = aircraft.features if isinstance(aircraft.features, dict) else {}
        if isinstance(message, dict):
            merged_features = {**prev_features, **message}
        else:
            merged_features = message

        if not created:
            aircraft.campus = campus
            aircraft.features = merged_features
            aircraft.updated_at = current_time
            aircraft.updated_on = today
            aircraft.save()

        mf = merged_features if isinstance(merged_features, dict) else {}
        altitude_for_log = _altitude_meters_from_message(
            merged_features if isinstance(merged_features, dict) else message,
            is_remoteid,
        )

        ts_for_minute = timestamp
        if django_timezone.is_naive(ts_for_minute):
            ts_for_minute = django_timezone.make_aware(ts_for_minute, timezone.utc)
        minute_start = ts_for_minute.replace(second=0, microsecond=0)
        minute_end = minute_start + timedelta(minutes=1)
        existing = (
            AircraftPositionLog.objects.filter(
                aircraft=aircraft,
                latitude=lat,
                longitude=lon,
                timestamp__gte=minute_start,
                timestamp__lt=minute_end,
            )
            .order_by('-timestamp')
            .first()
        )

        try:
            if existing:
                existing.campus = campus
                existing.altitude = altitude_for_log
                existing.ground_speed = _as_float(mf.get('speed', mf.get('gs')))
                existing.ground_track = _as_float(mf.get('course', mf.get('track')))
                existing.timestamp = timestamp
                existing.timestamp_minute = minute_start
                existing.updated_on = today
                existing.updated_at = current_time
                existing.save(
                    update_fields=[
                        'campus',
                        'altitude',
                        'ground_speed',
                        'ground_track',
                        'timestamp',
                        'timestamp_minute',
                        'updated_on',
                        'updated_at',
                    ]
                )
                return

            AircraftPositionLog.objects.create(
                aircraft=aircraft,
                campus=campus,
                latitude=lat,
                longitude=lon,
                altitude=altitude_for_log,
                ground_speed=_as_float(mf.get('speed', mf.get('gs'))),
                ground_track=_as_float(mf.get('course', mf.get('track'))),
                timestamp=timestamp,
                timestamp_minute=minute_start,
                updated_on=today,
                updated_at=current_time,
            )
        except IntegrityError:
            # Concurrent listener inserted an equivalent row first.
            return

    # RemoteID messages should use explicit CAMPUS routing (previous run_remoteid_feed behavior)
    if 'ID' in message:
        campus_name = (os.getenv('CAMPUS') or '').strip()
        if not campus_name:
            return
        campus = Campus.objects.filter(name=campus_name).first()
        if campus is None:
            return
        _save_aircraft_for_campus(campus)
        return

    # ADS-B style messages remain geofence-gated
    campuses = Campus.objects.filter(outer_geofence__isnull=False).select_related('outer_geofence')
    for campus in campuses:
        if campus.outer_geofence and not campus.outer_geofence.outside(lat, lon):
            _save_aircraft_for_campus(campus)
            return