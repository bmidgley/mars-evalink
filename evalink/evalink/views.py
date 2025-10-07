from django.http import JsonResponse, HttpResponseNotFound, HttpResponse
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from evalink.models import *
from datetime import date, timedelta, datetime
from django.utils.dateparse import parse_date
from django.shortcuts import render
from django.db.models import Q
from dotenv import load_dotenv
from .forms import ChatForm
import paho.mqtt.client as mqtt
import pytz
import os
import json
import zoneinfo
from . import handler

load_dotenv()

@login_required
def index(request):
    return render(request, "map.html")

@login_required
def features(request):
    campus = Campus.objects.get(name=os.getenv('CAMPUS'))
    fence = campus.inner_geofence
    data = {
        "type": "FeatureCollection",
        "features": [],
    }
    tz = pytz.timezone(campus.time_zone)
    timezone.now()
    now = datetime.now(tz)
    # Create timezone-aware datetime for past date
    past_date = date.today() - timedelta(days = 30)
    past = datetime.combine(past_date, datetime.min.time())
    past = tz.localize(past)
    if request.user.groups.filter(name='full-history').exists():
        top_stations = Station.objects.order_by('-updated_at').all()
    else:
        top_stations = Station.objects.filter(updated_at__gt = past).filter(~Q(station_type="ignore")).order_by('-updated_at').all()[:45]
    for station in sorted(top_stations, key=lambda x: x.name.lower(), reverse=False):
        if fully_populated(station.features):
            station.features['properties']['hardware_number'] = station.hardware_number
            station.features['properties']['hardware_node'] = station.hardware_node
            station.features['properties']['id'] = station.id
            station.features['properties']['days_old'] = (now - station.updated_at).days
            station.features['properties']['hours_old'] = (now - station.updated_at).total_seconds() / 3600.0
            
            # Special handling for planner stations
            if station.station_type == 'planner':
                # Get text messages for today using updated_on field
                local_date = now.date()
                text_logs = TextLog.objects.filter(
                    station=station,
                    updated_on=local_date
                ).order_by('updated_at')
                
                # Add text messages to features
                texts = []
                for text_log in text_logs:
                    if text_log.position_log:
                        text_data = {
                            'text': text_log.text,
                            'time': text_log.updated_at.isoformat(),
                            'position': [text_log.position_log.longitude, text_log.position_log.latitude],
                            'position_log_id': text_log.position_log.id,
                            'text_log_id': text_log.id
                        }
                        texts.append(text_data)
                
                station.features['properties']['texts'] = texts
                
                # Calculate position based on current time
                # Use updated_on field which is already timezone-adjusted
                local_date = now.date()
                position_logs = PositionLog.objects.filter(
                    station=station,
                    updated_on=local_date
                ).order_by('timestamp')
                
                if position_logs.exists():
                    current_time = now.time()
                    first_log = position_logs.first()
                    last_log = position_logs.last()
                    
                    # Convert log timestamps to local time for comparison
                    first_log_local_time = first_log.timestamp.astimezone(tz).time()
                    last_log_local_time = last_log.timestamp.astimezone(tz).time()
                    
                    if current_time < first_log_local_time:
                        # Before first time - use first point
                        station.features['geometry']['coordinates'] = [first_log.longitude, first_log.latitude]
                        station.features['properties']['time'] = first_log.timestamp.isoformat()
                    elif current_time > last_log_local_time:
                        # After last time - use last point
                        station.features['geometry']['coordinates'] = [last_log.longitude, last_log.latitude]
                        station.features['properties']['time'] = last_log.timestamp.isoformat()
                    else:
                        # Between times - interpolate between closest points
                        prev_log = None
                        next_log = None
                        
                        for log in position_logs:
                            log_local_time = log.timestamp.astimezone(tz).time()
                            if log_local_time <= current_time:
                                prev_log = log
                            elif log_local_time > current_time and next_log is None:
                                next_log = log
                                break
                        
                        if prev_log and next_log:
                            # Interpolate between prev_log and next_log
                            prev_time = prev_log.timestamp.astimezone(tz).time()
                            next_time = next_log.timestamp.astimezone(tz).time()
                            
                            # Calculate interpolation factor
                            total_diff = (datetime.combine(date.today(), next_time) - datetime.combine(date.today(), prev_time)).total_seconds()
                            current_diff = (datetime.combine(date.today(), current_time) - datetime.combine(date.today(), prev_time)).total_seconds()
                            factor = current_diff / total_diff if total_diff > 0 else 0
                            
                            # Interpolate coordinates
                            interp_lon = prev_log.longitude + (next_log.longitude - prev_log.longitude) * factor
                            interp_lat = prev_log.latitude + (next_log.latitude - prev_log.latitude) * factor
                            
                            station.features['geometry']['coordinates'] = [interp_lon, interp_lat]
                            station.features['properties']['time'] = now.isoformat()
                        elif prev_log:
                            # Only previous log available
                            station.features['geometry']['coordinates'] = [prev_log.longitude, prev_log.latitude]
                            station.features['properties']['time'] = prev_log.timestamp.isoformat()
                        else:
                            # Only next log available
                            station.features['geometry']['coordinates'] = [next_log.longitude, next_log.latitude]
                            station.features['properties']['time'] = next_log.timestamp.isoformat()
                else:
                    # No position logs for today - keep default position
                    pass
            
            if fence:
                coordinates = station.features['geometry'].get('coordinates')
                if coordinates:
                    distance = 1
                    longitude = coordinates[0]
                    latitude = coordinates[1]
                    if longitude > fence.longitude1 and longitude < fence.longitude2 and latitude > fence.latitude1 and latitude < fence.latitude2:
                        distance = 0
                    station.features['properties']['distance'] = distance
            data["features"].append(station.features)
    return JsonResponse(data, json_dumps_params={'indent': 2})

def fully_populated(features):
    if not features: return False
    if not 'geometry' in features: return False
    if not 'type' in features: return False
    if not 'coordinates' in features['geometry']: return False
    if not 'type' in features['geometry']: return False
    if features['geometry']['coordinates'] == [0, 0]: return False
    return True

@login_required
def texts(request):
    text_messages = TextLog.objects.all().order_by('-updated_at')[:5:-1]
    show_all = request.user.groups.filter(name='full-history').exists()
    return JsonResponse([text_message.serialize(show_all=show_all) for text_message in text_messages], safe=False, json_dumps_params={'indent': 2})

@login_required
def path(request):
    id = request.GET.get('id')
    station = Station.objects.filter(id=id).first()
    if station == None: return HttpResponseNotFound("not found")
    campus = Campus.objects.get(name=os.getenv('CAMPUS'))
    g = campus.inner_geofence
    
    # For planner stations, default to showing future planned locations
    if station.station_type == 'planner':
        current = date.today() - timedelta(days = 1)  # Look for future dates
        # For planner stations, don't use before_date when showing future planned locations
        # Only use it if explicitly provided in the URL
        if request.GET.get('before_date'):
            before_date = localdate("before", request.GET.get('before_date'), current)
        else:
            before_date = None  # Don't limit by before_date for future planned locations
    else:
        current = date.today() + timedelta(days = 1)  # Look for past dates
        before_date = localdate("before", request.GET.get('before_date'), current)
    
    after_date = localdate("after", request.GET.get('after_date'), None)
    models = {0: 'UNSET', 1: 'TLORA_V2', 2: 'TLORA_V1', 3: 'TLORA_V2_1_1P6', 4: 'TBEAM', 5: 'HELTEC_V2_0', 6: 'TBEAM_V0P7', 7: 'T_ECHO', 8: 'TLORA_V1_1P3', 9: 'RAK4631', 10: 'HELTEC_V2_1', 11: 'HELTEC_V1', 12: 'LILYGO_TBEAM_S3_CORE', 13: 'RAK11200', 14: 'NANO_G1', 15: 'TLORA_V2_1_1P8', 16: 'TLORA_T3_S3', 17: 'NANO_G1_EXPLORER', 18: 'NANO_G2_ULTRA', 19: 'LORA_TYPE', 20: 'WIPHONE', 21: 'WIO_WM1110', 22: 'RAK2560', 23: 'HELTEC_HRU_3601', 24: 'HELTEC_WIRELESS_BRIDGE', 25: 'STATION_G1', 26: 'RAK11310', 27: 'SENSELORA_RP2040', 28: 'SENSELORA_S3', 29: 'CANARYONE', 30: 'RP2040_LORA', 31: 'STATION_G2', 32: 'LORA_RELAY_V1', 33: 'NRF52840DK', 34: 'PPR', 35: 'GENIEBLOCKS', 36: 'NRF52_UNKNOWN', 37: 'PORTDUINO', 38: 'ANDROID_SIM', 39: 'DIY_V1', 40: 'NRF52840_PCA10059', 41: 'DR_DEV', 42: 'M5STACK', 43: 'HELTEC_V3', 44: 'HELTEC_WSL_V3', 45: 'BETAFPV_2400_TX', 46: 'BETAFPV_900_NANO_TX', 47: 'RPI_PICO', 48: 'HELTEC_WIRELESS_TRACKER', 49: 'HELTEC_WIRELESS_PAPER', 50: 'T_DECK', 51: 'T_WATCH_S3', 52: 'PICOMPUTER_S3', 53: 'HELTEC_HT62', 54: 'EBYTE_ESP32_S3', 55: 'ESP32_S3_PICO', 56: 'CHATTER_2', 57: 'HELTEC_WIRELESS_PAPER_V1_0', 58: 'HELTEC_WIRELESS_TRACKER_V1_0', 59: 'UNPHONE', 60: 'TD_LORAC', 61: 'CDEBYTE_EORA_S3', 62: 'TWC_MESH_V4', 63: 'NRF52_PROMICRO_DIY', 64: 'RADIOMASTER_900_BANDIT_NANO', 65: 'HELTEC_CAPSULE_SENSOR_V3', 66: 'HELTEC_VISION_MASTER_T190', 67: 'HELTEC_VISION_MASTER_E213', 68: 'HELTEC_VISION_MASTER_E290', 69: 'HELTEC_MESH_NODE_T114', 70: 'SENSECAP_INDICATOR', 71: 'TRACKER_T1000_E', 72: 'RAK3172', 73: 'WIO_E5', 74: 'RADIOMASTER_900_BANDIT', 75: 'ME25LS01_4Y10TD', 76: 'RP2040_FEATHER_RFM95', 77: 'M5STACK_COREBASIC', 78: 'M5STACK_CORE2', 79: 'RPI_PICO2', 80: 'M5STACK_CORES3', 81: 'SEEED_XIAO_S3', 82: 'MS24SF1', 83: 'TLORA_C6'}
    hardware_name = models.get(station.hardware.hardware_type, station.hardware.hardware_type) if station.hardware else 'UNSET'
    result = {'id': station.id, 'name': station.name, 'date': None, 'waypoints': [], 'points': [], 'hardware_name': hardware_name}
    
    if after_date:
        # For planner stations, look for future planned locations using updated_on field
        if station.station_type == 'planner':
            after_date_only = after_date.date()
            position_log = PositionLog.objects.filter(station=station, updated_on__gt=after_date_only).filter(
                                                      Q(latitude__gt=g.latitude2) | Q(latitude__lt=g.latitude1) | Q(longitude__gt=g.longitude2) | Q(longitude__lt=g.longitude1)).order_by('updated_on').first()
        else:
            position_log = PositionLog.objects.filter(station=station,updated_on__gt=after_date).filter(
                                                      Q(latitude__gt=g.latitude2) | Q(latitude__lt=g.latitude1) | Q(longitude__gt=g.longitude2) | Q(longitude__lt=g.longitude1)).order_by('updated_at').first()
    elif before_date:
        # For planner stations, look for planned locations before the specified date
        if station.station_type == 'planner':
            before_date_only = before_date.date()
            position_log = PositionLog.objects.filter(station=station, updated_on__lt=before_date_only).filter(
                                                      Q(latitude__gt=g.latitude2) | Q(latitude__lt=g.latitude1) | Q(longitude__gt=g.longitude2) | Q(longitude__lt=g.longitude1)).order_by('-updated_on').first()
        else:
            position_log = PositionLog.objects.filter(station=station,updated_on__lt=before_date).filter(
                                                      Q(latitude__gt=g.latitude2) | Q(latitude__lt=g.latitude1) | Q(longitude__gt=g.longitude2) | Q(longitude__lt=g.longitude1)).order_by('-updated_at').first()
    else:
        # For planner stations, look for future planned locations using updated_on field
        if station.station_type == 'planner':
            # Look for the earliest future planned location (updated_on > today)
            today = date.today()
            position_log = PositionLog.objects.filter(station=station, updated_on__gt=today).filter(
                                                      Q(latitude__gt=g.latitude2) | Q(latitude__lt=g.latitude1) | Q(longitude__gt=g.longitude2) | Q(longitude__lt=g.longitude1)).order_by('updated_on').first()
        else:
            position_log = PositionLog.objects.filter(station=station,updated_on__lt=before_date).filter(
                                                      Q(latitude__gt=g.latitude2) | Q(latitude__lt=g.latitude1) | Q(longitude__gt=g.longitude2) | Q(longitude__lt=g.longitude1)).order_by('-updated_at').first()
    
    if position_log:
        # For planner stations, handle navigation correctly
        if station.station_type == 'planner':
            if before_date:
                # When before_date is provided (navigation), use the date from the found position_log
                found_date = position_log.updated_on if position_log.updated_on else position_log.updated_at.date()
                result['date'] = found_date
                
                # Get planned locations for the specific date found
                position_logs = list(PositionLog.objects.filter(station=station, updated_on=found_date).filter(
                                                          Q(latitude__gt=g.latitude2) | Q(latitude__lt=g.latitude1) | Q(longitude__gt=g.longitude2) | Q(longitude__lt=g.longitude1)).order_by('timestamp', 'updated_at').all())
                # For planner stations, we don't have weather data for future dates
                weather_logs = []
            else:
                # When no before_date (default view), find the farthest future planned date
                latest_future_log = PositionLog.objects.filter(station=station, updated_on__gt=today).filter(
                                                      Q(latitude__gt=g.latitude2) | Q(latitude__lt=g.latitude1) | Q(longitude__gt=g.longitude2) | Q(longitude__lt=g.longitude1)).order_by('-updated_on').first()
                
                if latest_future_log and latest_future_log.updated_on:
                    found_date = latest_future_log.updated_on
                    result['date'] = found_date
                    
                    # Get only the planned locations for the farthest future date
                    position_logs = list(PositionLog.objects.filter(station=station, updated_on=found_date).filter(
                                                              Q(latitude__gt=g.latitude2) | Q(latitude__lt=g.latitude1) | Q(longitude__gt=g.longitude2) | Q(longitude__lt=g.longitude1)).order_by('timestamp', 'updated_at').all())
                    # For planner stations, we don't have weather data for future dates
                    weather_logs = []
                else:
                    # Fallback to the original position_log if no future logs found
                    found_date = position_log.updated_on if position_log.updated_on else position_log.updated_at.date()
                    result['date'] = found_date
                    
                    # Get planned locations for the fallback date
                    position_logs = list(PositionLog.objects.filter(station=station, updated_on=found_date).filter(
                                                              Q(latitude__gt=g.latitude2) | Q(latitude__lt=g.latitude1) | Q(longitude__gt=g.longitude2) | Q(longitude__lt=g.longitude1)).order_by('timestamp', 'updated_at').all())
                    # For planner stations, we don't have weather data for future dates
                    weather_logs = []
        else:
            # For regular stations, use timestamp date; for others use updated_at date
            campus_tz = pytz.timezone(campus.time_zone)
            if position_log.timestamp:
                found_date = position_log.timestamp.astimezone(campus_tz).date()
            else:
                found_date = position_log.updated_at.astimezone(campus_tz).date()
            
            result['date'] = found_date
            
            position_logs = list(PositionLog.objects.filter(station=station, updated_on=found_date).filter(
                                                      Q(latitude__gt=g.latitude2) | Q(latitude__lt=g.latitude1) | Q(longitude__gt=g.longitude2) | Q(longitude__lt=g.longitude1)).order_by('timestamp', 'updated_at').all())
            weather_logs = list(TelemetryLog.objects.filter(station=station, updated_on=found_date, temperature__isnull=False).order_by('updated_at').all())
        
        wind_weather_logs = [sample for sample in weather_logs if sample.wind_speed != None]
        if wind_weather_logs != []: weather_logs = wind_weather_logs

        for log in position_logs:
            sample = closest(log.updated_at, weather_logs)
            # For planner stations, use timestamp if available; otherwise use updated_at
            timestamp = log.timestamp if station.station_type == 'planner' and log.timestamp else log.updated_at
            event = {'latitude': log.latitude, 'longitude': log.longitude, 'altitude': log.altitude, 'updated_at': timestamp}
            if sample:
                if(sample.wind_speed != None): event['wind_speed'] = sample.wind_speed
                if(sample.wind_direction != None): event['wind_direction'] = sample.wind_direction
                event['temperature'] = sample.temperature
            result['points'].append(event)

        # For planner stations, get text logs for the farthest future date; for others use specific date
        if station.station_type == 'planner':
            text_logs = TextLog.objects.filter(station=station, updated_on=found_date).order_by('updated_at').all()
        else:
            text_logs = TextLog.objects.filter(station=station, updated_at__date=found_date).order_by('updated_at').all()
        
        for text in text_logs:
            if text.position_log:
                # Use position_log timestamp if available (for planned locations), otherwise use text.updated_at
                timestamp = text.updated_at
                if text.position_log.timestamp:
                    timestamp = text.position_log.timestamp
                
                waypoint_data = {
                    'latitude': text.position_log.latitude, 
                    'longitude': text.position_log.longitude, 
                    'altitude': text.position_log.altitude, 
                    'updated_at': timestamp, 
                    'text': text.text
                }
                
                # Add IDs for planner stations to enable deletion
                if station.station_type == 'planner':
                    waypoint_data['position_log_id'] = text.position_log.id
                    waypoint_data['text_log_id'] = text.id
                
                result['waypoints'].append(waypoint_data)
    else:
        result['date'] = before_date.isoformat()[0:10]
    return JsonResponse(result, json_dumps_params={'indent': 2})

def closest(time, samples):
    if samples == []: return None
    last_delta = abs(samples[0].updated_at - time)
    last_sample = samples[0]
    for sample in samples[1:]:
        delta = abs(sample.updated_at - time)
        if delta > last_delta:
            return last_sample
        last_sample = sample
        last_delta = delta

    return samples[-1]

def localdate(label, my_date, default):
    if my_date == None:
        # print(f'{label} blankinput: using {default}')
        return default
    if isinstance(my_date, str): my_date = parse_date(my_date)
    my_naive_datetime = datetime.combine(my_date, datetime.min.time())
    tz = timezone.get_current_timezone()
    my_aware_datetime = timezone.make_aware(my_naive_datetime, timezone=tz)
    return my_aware_datetime

def create_heard_messages(text, message_id, current_time):
    """Create 'heard' TextLog entries for stations outside campus inner geofence"""
    from django.db import IntegrityError
    
    campus = Campus.objects.get(name=os.getenv('CAMPUS'))
    inner_fence = campus.inner_geofence
    tz = pytz.timezone(campus.time_zone)
    
    if inner_fence:
        outside_stations = Station.objects.filter(
            last_position__isnull=False
        ).exclude(hardware_number=int(os.getenv('MQTT_NODE_NUMBER')))  # Exclude the gateway station

        for outside_station in outside_stations:
            if outside_station.outside(inner_fence):
                heard_text = f"heard: {text}"
                heard_log = TextLog(
                    station=outside_station,
                    position_log=outside_station.last_position,
                    serial_number=message_id + outside_station.id,  # Make unique by adding station id
                    text=heard_text,
                    updated_at=current_time,
                    updated_on=current_time.astimezone(tz).date())
                try:
                    heard_log.save()
                except IntegrityError:
                    # Skip if duplicate serial number
                    continue

@login_required
def chat(request):
    gateway_node_number = int(os.getenv('MQTT_NODE_NUMBER'))

    message = request.GET.get('message')
    if message:
        message = request.user.username + ': ' + message
        send_message = {'channel': 0, 'from': gateway_node_number, 'payload': message, 'type': 'sendtext'}
        data = json.dumps(send_message)
        topic = f'{os.getenv("MQTT_TOPIC")}/2/json/mqtt/'
        client = mqtt.Client()
        if os.getenv('MQTT_TLS'): client.tls_set()
        client.username_pw_set(username=os.getenv('MQTT_USER'), password=os.getenv('MQTT_PASSWORD'))
        client.connect(os.getenv('MQTT_SERVER'), int(os.getenv('MQTT_PORT')), 60)
        client.publish(topic, data)
        print("\n", topic, data)
        client.disconnect()
        
        # Create "heard" messages for stations outside campus inner geofence
        current_time = datetime.now(timezone.utc)
        message_id = int(current_time.timestamp() * 1000000)  # Generate unique message ID
        create_heard_messages(message, message_id, current_time)
        
        return JsonResponse({"sent": "ok"}, json_dumps_params={'indent': 2})

    if request.method == "POST":
        form = ChatForm(request.POST)
        if form.is_valid():
            message = request.user.username + ': '
            message += form.cleaned_data['message']
            send_message = {'channel': 0, 'from': gateway_node_number, 'payload': message, 'type': 'sendtext'}
            data = json.dumps(send_message)
            topic = f'{os.getenv("MQTT_TOPIC")}/2/json/mqtt/'
            client = mqtt.Client()
            if os.getenv('MQTT_TLS'): client.tls_set()
            client.username_pw_set(username=os.getenv('MQTT_USER'), password=os.getenv('MQTT_PASSWORD'))
            client.connect(os.getenv('MQTT_SERVER'), int(os.getenv('MQTT_PORT')), 60)
            client.publish(topic, data)
            client.disconnect()
            
            # Create "heard" messages for stations outside campus inner geofence
            current_time = datetime.now(timezone.utc)
            message_id = int(current_time.timestamp() * 1000000)  # Generate unique message ID
            create_heard_messages(message, message_id, current_time)

    form = ChatForm()
    texts = TextLog.objects.all().order_by('-updated_at')[:20:1]
    return render(request, "chat.html", {"form": form, "texts": texts, "name": request.user.username})

@login_required
def point(request):
    if request.method != 'POST': return HttpResponseNotFound("not found")
    user_id = request.user.id
    username = request.user.username
    tz = pytz.timezone("US/Mountain")
    timezone.now()
    time = datetime.now(tz)
    json_content = json.loads(request.body)
    latitude = json_content['latitude']
    longitude = json_content['longitude']
    altitude = json_content.get('altitude', None)
    _color = json_content.get('color', "#ff0000")
    station = Station.objects.filter(hardware_number=user_id).first()
    if station == None:
        station_profile = StationProfile.objects.first()
        if station_profile == None:
            station_profile = StationProfile(name="default", configuration={"firmware": "2.2.17"}, compatible_firmwares=["2.2.17"])
            station_profile.save()
        hardware = Hardware.objects.filter(hardware_type=6).first()
        if hardware == None:
            hardware = Hardware(hardware_type=6, name='tbeam', station_type='infrastructure')
            hardware.save()
        station = Station(
            hardware=hardware,
            station_profile=station_profile,
            hardware_number=user_id,
            hardware_node='na',
            station_type=hardware.station_type,
            updated_at=time,
            features = {
                "type": "Feature",
                "properties": {
                    "name": username,
                    "label": username,
                    "time": time.isoformat(),
                    "hardware": hardware.hardware_type,
                    "node_type": hardware.station_type,
                    "altitude": altitude,
                    "coordinates": [longitude, latitude],
                    "ground_speed": 0,
                    "ground_track": 0,
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
            },
            short_name=username)
        station.save()
    position_log = PositionLog(
        station=station,
        latitude=latitude,
        longitude=longitude,
        altitude=altitude,
        ground_speed=0,
        ground_track=0,
        updated_at=time)
    position_log.save()
    station.features["geometry"]["coordinates"] = [longitude, latitude]
    station.features["properties"]["altitude"] = altitude
    station.last_position = position_log
    station.updated_at = time
    station.save()
    return JsonResponse({"stored": "ok"}, json_dumps_params={'indent': 2})

@login_required
def inventory(request):
    items = []
    # Create timezone-aware datetime for past date
    past_date = date.today() - timedelta(days = 30)
    past = datetime.combine(past_date, datetime.min.time())
    past = timezone.make_aware(past, timezone.get_current_timezone())
    stations = Station.objects.filter(updated_at__gt = past).filter(~Q(station_type="ignore")).order_by('name').all()
    for station in stations:
        if station.features == None: continue
        coordinates = station.features.get('geometry', {}).get('coordinates', [])
        if coordinates == []: continue
        items.append({'name': station.name,
                      'firmware': station.firmware,
                      'updated': station.updated_at,
                      'coordinates': coordinates,
                      'battery': station.features.get('properties', {}).get('battery_level', None)})
    return JsonResponse({'items': items}, json_dumps_params={'indent': 2})

@login_required
def campuses(request):
    """API endpoint to list all campuses with id, name, latitude, longitude, and elevation"""
    campuses = Campus.objects.all().order_by('name')
    campus_data = []
    
    for campus in campuses:
        campus_data.append({
            'id': campus.id,
            'name': campus.name,
            'latitude': campus.latitude,
            'longitude': campus.longitude,
            'elevation': campus.altitude
        })
    
    return JsonResponse({'campuses': campus_data}, json_dumps_params={'indent': 2})

@login_required
def add_location_to_plan(request):
    """API endpoint to add a location to the planning station"""
    if request.method != 'POST':
        return HttpResponseNotFound("not found")
    
    try:
        json_content = json.loads(request.body)
        latitude = float(json_content['latitude'])
        longitude = float(json_content['longitude'])
        plan_date = json_content['date']  # YYYY-MM-DD format
        plan_time = json_content['time']  # HH:MM format
        
        # Parse the datetime
        datetime_str = f"{plan_date}T{plan_time}:00"
        target_datetime = datetime.fromisoformat(datetime_str)
        
        # Make it timezone aware
        campus = Campus.objects.get(name=os.getenv('CAMPUS'))
        tz = pytz.timezone(campus.time_zone)
        target_datetime = tz.localize(target_datetime)
        
        # Convert to UTC for storage in timestamp field
        target_datetime_utc = target_datetime.astimezone(pytz.UTC)
        
        # Find the planning station
        planner_station = Station.objects.filter(station_type='planner').first()
        if not planner_station:
            return JsonResponse({"error": "Planning station not found"}, status=404)
        
        # Create PositionLog for the target time
        position_log = PositionLog(
            station=planner_station,
            latitude=latitude,
            longitude=longitude,
            altitude=None,
            ground_speed=0,
            ground_track=0,
            timestamp=target_datetime_utc,
            updated_at=target_datetime_utc,
            updated_on=target_datetime.date()
        )
        position_log.save()
        
        # Create TextLog 1 second after the target time
        text_datetime = target_datetime + timedelta(seconds=1)
        text_datetime_utc = text_datetime.astimezone(pytz.UTC)
        text_log = TextLog(
            station=planner_station,
            position_log=position_log,
            text="Objective",
            serial_number=int(timezone.now().timestamp() * 1000000),  # Generate unique serial number
            updated_at=text_datetime_utc,
            updated_on=text_datetime.date()
        )
        text_log.save()
        
        # Calculate the day after the point was saved for before_date
        next_day = target_datetime.date() + timedelta(days=1)
        
        # Create redirect URL with planner name, ID, and before_date
        redirect_url = f"/?name={planner_station.name}&id={planner_station.id}&before_date={next_day.strftime('%Y-%m-%d')}"
        
        return JsonResponse({
            "success": True,
            "message": "Location added to plan successfully",
            "position_log_id": position_log.id,
            "text_log_id": text_log.id,
            "target_datetime": target_datetime.isoformat(),
            "redirect_url": redirect_url
        }, json_dumps_params={'indent': 2})
        
    except Exception as e:
        return JsonResponse({
            "error": f"Failed to add location to plan: {str(e)}"
        }, status=500)

@login_required
def delete_planner_point(request):
    """API endpoint to delete a planner point (both position_log and text_log)"""
    if request.method != 'POST':
        return HttpResponseNotFound("not found")
    
    try:
        json_content = json.loads(request.body)
        position_log_id = json_content.get('position_log_id')
        
        if not position_log_id:
            return JsonResponse({"error": "position_log_id is required"}, status=400)
        
        # Find the position log
        position_log = PositionLog.objects.filter(id=position_log_id).first()
        if not position_log:
            return JsonResponse({"error": "Position log not found"}, status=404)
        
        # Verify it's from a planner station
        if position_log.station.station_type != 'planner':
            return JsonResponse({"error": "Only planner points can be deleted"}, status=400)
        
        # Find the associated text log
        text_log = TextLog.objects.filter(position_log=position_log).first()
        
        # Get the date of the point for redirect calculation
        point_date = position_log.timestamp.date() if position_log.timestamp else position_log.updated_on
        
        # Delete the text log first (due to foreign key constraints)
        if text_log:
            text_log.delete()
        
        # Delete the position log
        position_log.delete()
        
        # Calculate the day after the deleted point for before_date redirect
        next_day = point_date + timedelta(days=1)
        
        # Find the planner station for redirect
        planner_station = position_log.station
        
        # Create redirect URL with planner name, ID, and before_date
        redirect_url = f"/?name={planner_station.name}&id={planner_station.id}&before_date={next_day.strftime('%Y-%m-%d')}"
        
        return JsonResponse({
            "success": True,
            "message": "Planner point deleted successfully",
            "redirect_url": redirect_url
        }, json_dumps_params={'indent': 2})
        
    except Exception as e:
        return JsonResponse({
            "error": f"Failed to delete planner point: {str(e)}"
        }, status=500)

@login_required
def search(request):
    campus = Campus.objects.get(name=os.getenv('CAMPUS'))
    fence = campus.inner_geofence
    tz = pytz.timezone(campus.time_zone)
    latitude1 = request.GET.get('latitude1')
    latitude2 = request.GET.get('latitude2')
    longitude1 = request.GET.get('longitude1')
    longitude2 = request.GET.get('longitude2')
    date = request.GET.get('date')
    endDate = request.GET.get('endDate')
    download = request.GET.get('download')
    
    infra_station_ids = Station.objects.filter(station_type='infrastructure').values_list('pk', flat=True)
    planner_station_ids = Station.objects.filter(station_type='planner').values_list('pk', flat=True)
    position_logs = PositionLog.objects.exclude(station_id__in=infra_station_ids)
    
    if latitude1 and latitude2 and longitude1 and longitude2:
        latitude1 = float(latitude1)
        latitude2 = float(latitude2)
        longitude1 = float(longitude1)
        longitude2 = float(longitude2)
        latitude1, latitude2 = sorted([latitude1, latitude2])
        longitude1, longitude2 = sorted([longitude1, longitude2])
        position_logs = position_logs.filter(
            Q(latitude__gt=latitude1) & Q(latitude__lt=latitude2) & Q(longitude__gt=longitude1) & Q(longitude__lt=longitude2))
    
    if fence:
        # Include planner stations regardless of geofence, but apply geofence filter to other stations
        position_logs = position_logs.filter(
            Q(station_id__in=planner_station_ids) |  # Include all planner stations
            Q(latitude__lt=fence.latitude1) | Q(latitude__gt=fence.latitude2) | Q(longitude__lt=fence.longitude1) | Q(longitude__gt=fence.longitude2))
    if date and date != '' and endDate and endDate != '':
        parsed_date = parse_date(date)
        parsed_end_date = parse_date(endDate)
        if parsed_date is not None and parsed_end_date is not None:
            position_logs = position_logs.filter(updated_on__gte=parsed_date, updated_on__lte=parsed_end_date)
    elif date and date != '':
        parsed_date = parse_date(date)
        if parsed_date is not None:
            position_logs = position_logs.filter(updated_on=parsed_date)
    
    # If download is requested, generate GPX file
    if download == 'true':
        from .export_gpx import ExportGpx
        import xmltodict
        from io import StringIO
        
        # Group position logs by station
        station_hash = {}
        points_hash = {}
        waypoints_list = []
        
        for position_log in position_logs.order_by('updated_at')[:1000000]:
            station = station_hash.get(position_log.station_id)
            if station == None:
                station = Station.objects.get(pk=position_log.station_id)
                if station:
                    station_hash[position_log.station_id] = station
            if station and station.station_type != 'ignore':
                station_name = station.name
                if station_name not in points_hash:
                    points_hash[station_name] = []
                
                # Format timestamp for GPX
                timestamp = position_log.timestamp or position_log.updated_at
                iso_timestamp = timestamp.astimezone(tz).strftime("%Y-%m-%dT%H:%M:%SZ")
                
                entry = {
                    '@lat': str(position_log.latitude),
                    '@lon': str(position_log.longitude),
                    'ele': str(position_log.altitude) if position_log.altitude else '0',
                    'time': iso_timestamp,
                }
                points_hash[station_name].append(entry)
        
        # Generate GPX content
        station_names = list(points_hash.keys())
        tracks = []
        for station_name in station_names:
            tracks.append({
                'name': station_name,
                'trkseg': {
                    'trkpt': points_hash[station_name]
                }
            })

        gpx = {
            'gpx': {
                '@xmlns': "http://www.topografix.com/GPX/1/1", 
                '@xmlns:gpxx': "http://www.garmin.com/xmlschemas/GpxExtensions/v3", 
                '@xmlns:gpxtpx': "http://www.garmin.com/xmlschemas/TrackPointExtension/v1", 
                '@creator': "Mars Evalink", 
                '@version': "1.1", 
                '@xmlns:xsi': "http://www.w3.org/2001/XMLSchema-instance", 
                '@xsi:schemaLocation': "http://www.topografix.com/GPX/1/1 http://www.topografix.com/GPX/1/1/gpx.xsd http://www.garmin.com/xmlschemas/GpxExtensions/v3 http://www.garmin.com/xmlschemas/GpxExtensionsv3.xsd http://www.garmin.com/xmlschemas/TrackPointExtension/v1 http://www.garmin.com/xmlschemas/TrackPointExtensionv1.xsd",
                'trk': tracks
            }
        }

        # Generate filename with date range
        filename = "mars_evalink_export"
        if date and endDate:
            filename += f"_{date}_to_{endDate}"
        elif date:
            filename += f"_{date}"
        filename += ".gpx"
        
        # Create GPX content
        gpx_content = xmltodict.unparse(gpx, pretty=True)
        
        # Return as downloadable file
        response = HttpResponse(gpx_content, content_type='application/gpx+xml')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
    
    # Regular search functionality
    results = []
    paths = []
    for position_log in position_logs.order_by('-updated_at')[:100000]:
        # Use updated_on field if available (already timezone-adjusted), otherwise convert timestamp
        if position_log.updated_on:
            date = position_log.updated_on.strftime("%Y-%m-%d")
            # For after_date, we need to calculate from updated_on
            after_date = (position_log.updated_on - timedelta(days=1)).strftime("%Y-%m-%d")
        else:
            timestamp = position_log.timestamp or position_log.updated_at
            date = timestamp.astimezone(tz).strftime("%Y-%m-%d")
            after_date = (timestamp - timedelta(days = 1)).astimezone(tz).strftime("%Y-%m-%d")
        entry = (position_log.station_id, date, after_date)
        if entry not in results: results.append(entry)
    for (id, date, after_date) in results:
        station = Station.objects.get(pk=id)
        if station and station.station_type != 'ignore':
            url = f'/?history=1&name={station.name}&after_date={after_date}'
            name = f'{station.name} on {date}'
            paths.append({'name': name, 'url': url})
    return JsonResponse({'items': paths}, json_dumps_params={'indent': 2})
