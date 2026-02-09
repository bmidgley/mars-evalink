from django.http import JsonResponse, HttpResponseNotFound, HttpResponse
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from evalink.models import *
from datetime import date, timedelta, datetime
from django.utils.dateparse import parse_date
from django.shortcuts import render, redirect
from django.db.models import Q
from dotenv import load_dotenv
from .forms import ChatForm
import paho.mqtt.client as mqtt
import pytz
import os
import json
import zoneinfo
from . import handler
import math
from collections import defaultdict
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

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
                # Get text messages for today and tomorrow using updated_on field
                # This accounts for timezone differences where messages created today
                # might have updated_on set to tomorrow
                local_date = now.date()
                tomorrow_date = local_date + timedelta(days=1)
                
                text_logs = TextLog.objects.filter(
                    station=station,
                    updated_on__in=[local_date, tomorrow_date]
                ).order_by('updated_at')
                
                # Add text messages to features
                texts = []
                for text_log in text_logs:
                    if text_log.position_log:
                        # Use position_log timestamp if available (for planned locations), otherwise use updated_at
                        timestamp = text_log.updated_at
                        if text_log.position_log.timestamp:
                            timestamp = text_log.position_log.timestamp
                        
                        text_data = {
                            'text': text_log.text,
                            'time': timestamp.isoformat(),
                            'position': [text_log.position_log.longitude, text_log.position_log.latitude],
                            'position_log_id': text_log.position_log.id,
                            'text_log_id': text_log.id
                        }
                        texts.append(text_data)
                
                station.features['properties']['texts'] = texts
                
                # Calculate position based on current time
                # Get all planned position logs ordered by timestamp (across all days)
                position_logs = PositionLog.objects.filter(
                    station=station,
                    timestamp__isnull=False  # Only get logs with planned timestamps
                ).order_by('timestamp')
                
                if position_logs.exists():
                    current_datetime = now
                    first_log = position_logs.first()
                    last_log = position_logs.last()
                    
                    # Convert log timestamps to local time for comparison
                    first_log_local_datetime = first_log.timestamp.astimezone(tz)
                    last_log_local_datetime = last_log.timestamp.astimezone(tz)
                    
                    if current_datetime < first_log_local_datetime:
                        # Before first planned time - use first point
                        station.features['geometry']['coordinates'] = [first_log.longitude, first_log.latitude]
                        station.features['properties']['time'] = first_log.timestamp.isoformat()
                    elif current_datetime > last_log_local_datetime:
                        # After last planned time - use last point
                        station.features['geometry']['coordinates'] = [last_log.longitude, last_log.latitude]
                        station.features['properties']['time'] = last_log.timestamp.isoformat()
                    else:
                        # Between planned times - interpolate between closest points
                        prev_log = None
                        next_log = None
                        
                        for log in position_logs:
                            log_local_datetime = log.timestamp.astimezone(tz)
                            if log_local_datetime <= current_datetime:
                                prev_log = log
                            elif log_local_datetime > current_datetime and next_log is None:
                                next_log = log
                                break
                        
                        if prev_log and next_log:
                            # Interpolate between prev_log and next_log
                            prev_datetime = prev_log.timestamp.astimezone(tz)
                            next_datetime = next_log.timestamp.astimezone(tz)
                            
                            # Calculate interpolation factor using total seconds
                            total_diff = (next_datetime - prev_datetime).total_seconds()
                            current_diff = (current_datetime - prev_datetime).total_seconds()
                            factor = current_diff / total_diff if total_diff > 0 else 0
                            
                            # Interpolate coordinates
                            interp_lon = prev_log.longitude + (next_log.longitude - prev_log.longitude) * factor
                            interp_lat = prev_log.latitude + (next_log.latitude - prev_log.latitude) * factor
                            
                            station.features['geometry']['coordinates'] = [interp_lon, interp_lat]
                            station.features['properties']['time'] = current_datetime.isoformat()
                        elif prev_log:
                            # Only previous log available
                            station.features['geometry']['coordinates'] = [prev_log.longitude, prev_log.latitude]
                            station.features['properties']['time'] = prev_log.timestamp.isoformat()
                        else:
                            # Only next log available
                            station.features['geometry']['coordinates'] = [next_log.longitude, next_log.latitude]
                            station.features['properties']['time'] = next_log.timestamp.isoformat()
                else:
                    # No planned position logs - keep default position
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
    today = date.today()
    
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
            # For planner stations, include all locations regardless of geofence
            position_log = PositionLog.objects.filter(station=station, updated_on__gt=after_date_only).order_by('updated_on').first()
        else:
            position_log = PositionLog.objects.filter(station=station,updated_on__gt=after_date).filter(
                                                      Q(latitude__gt=g.latitude2) | Q(latitude__lt=g.latitude1) | Q(longitude__gt=g.longitude2) | Q(longitude__lt=g.longitude1)).order_by('updated_at').first()
    elif before_date:
        # For planner stations, look for planned locations before the specified date
        if station.station_type == 'planner':
            before_date_only = before_date.date()
            # For planner stations, include all locations regardless of geofence
            position_log = PositionLog.objects.filter(station=station, updated_on__lt=before_date_only).order_by('-updated_on').first()
        else:
            position_log = PositionLog.objects.filter(station=station,updated_on__lt=before_date).filter(
                                                      Q(latitude__gt=g.latitude2) | Q(latitude__lt=g.latitude1) | Q(longitude__gt=g.longitude2) | Q(longitude__lt=g.longitude1)).order_by('-updated_at').first()
    else:
        # For planner stations, look for future planned locations using updated_on field
        if station.station_type == 'planner':
            # Look for the earliest future planned location (updated_on > today)
            # If no future plans exist, fall back to the most recent plan
            position_log = PositionLog.objects.filter(station=station, updated_on__gt=today).order_by('updated_on').first()
            if not position_log:
                # No future plans, get the most recent plan
                position_log = PositionLog.objects.filter(station=station).order_by('-updated_on').first()
        else:
            position_log = PositionLog.objects.filter(station=station,updated_on__lt=before_date).filter(
                                                      Q(latitude__gt=g.latitude2) | Q(latitude__lt=g.latitude1) | Q(longitude__gt=g.longitude2) | Q(longitude__lt=g.longitude1)).order_by('-updated_at').first()
    
    if position_log:
        # For planner stations, handle navigation correctly
        if station.station_type == 'planner':
            if before_date or after_date:
                # When before_date or after_date is provided (navigation), use the date from the found position_log
                found_date = position_log.updated_on if position_log.updated_on else position_log.updated_at.date()
                result['date'] = found_date
                
                # Get planned locations for the specific date found
                # For planner stations, include all locations regardless of geofence
                position_logs = list(PositionLog.objects.filter(station=station, updated_on=found_date).order_by('timestamp', 'updated_at').all())
                # For planner stations, we don't have weather data for future dates
                weather_logs = []
            else:
                # When no before_date (default view), find the farthest future planned date
                # For planner stations, include all locations regardless of geofence
                latest_future_log = PositionLog.objects.filter(station=station, updated_on__gt=today).order_by('-updated_on').first()
                
                if latest_future_log and latest_future_log.updated_on:
                    found_date = latest_future_log.updated_on
                    result['date'] = found_date
                    
                    # Get only the planned locations for the farthest future date
                    # For planner stations, include all locations regardless of geofence
                    position_logs = list(PositionLog.objects.filter(station=station, updated_on=found_date).order_by('timestamp', 'updated_at').all())
                    # For planner stations, we don't have weather data for future dates
                    weather_logs = []
                else:
                    # No future plans, use the most recent plan date
                    latest_log = PositionLog.objects.filter(station=station).order_by('-updated_on').first()
                    if latest_log and latest_log.updated_on:
                        found_date = latest_log.updated_on
                        result['date'] = found_date
                        
                        # Get planned locations for the most recent date
                        # For planner stations, include all locations regardless of geofence
                        position_logs = list(PositionLog.objects.filter(station=station, updated_on=found_date).order_by('timestamp', 'updated_at').all())
                        # For planner stations, we don't have weather data for future dates
                        weather_logs = []
                    else:
                        # Fallback to the original position_log if no logs found
                        found_date = position_log.updated_on if position_log.updated_on else position_log.updated_at.date()
                        result['date'] = found_date
                        
                        # Get planned locations for the fallback date
                        # For planner stations, include all locations regardless of geofence
                        position_logs = list(PositionLog.objects.filter(station=station, updated_on=found_date).order_by('timestamp', 'updated_at').all())
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
        if before_date:
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
    """Create 'heard' TextLog entries for stations outside campus inner geofence but inside outer geofence"""
    from django.db import IntegrityError
    
    campus = Campus.objects.get(name=os.getenv('CAMPUS'))
    inner_fence = campus.inner_geofence
    outer_fence = campus.outer_geofence
    tz = pytz.timezone(campus.time_zone)
    
    if inner_fence:
        outside_stations = Station.objects.filter(
            last_position__isnull=False
        ).exclude(hardware_number=int(os.getenv('MQTT_NODE_NUMBER'))).exclude(station_type='infrastructure').exclude(station_type='ignore')  # Exclude the gateway station, infrastructure, and ignore stations

        for outside_station in outside_stations:
            if outside_station.outside(inner_fence) and (not outer_fence or not outside_station.outside(outer_fence)):
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

def haversine_distance(lat1, lon1, lat2, lon2):
    """Calculate the great circle distance between two points on Earth in kilometers."""
    # Convert latitude and longitude from degrees to radians
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    
    # Haversine formula
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    c = 2 * math.asin(math.sqrt(a))
    
    # Radius of earth in kilometers
    r = 6371
    return c * r

@login_required
def aircraft(request):
    """Return aircraft data from database, limited to entries updated within the last 15 minutes"""
    # Get the cutoff time (15 minutes ago)
    cutoff_time = timezone.now() - timedelta(minutes=15)
    
    # Query aircraft updated within the last 15 minutes
    aircraft_list = Aircraft.objects.filter(updated_at__gte=cutoff_time).select_related('campus')
    
    # Build aircraft data from database records
    aircraft_data = []
    for aircraft in aircraft_list:
        if not aircraft.features:
            continue
        
        # Extract data from features JSONField
        features = aircraft.features
        lat = features.get('lat')
        lon = features.get('lon')
        
        # Skip if no position data
        if lat is None or lon is None:
            continue
        
        # Build aircraft object in expected format
        aircraft_obj = {
            'hex': aircraft.hex,
            'lat': lat,
            'lon': lon,
            'alt_baro': features.get('alt_baro'),
            'gs': features.get('gs'),
            'track': features.get('track'),
            'flight': features.get('flight'),
            'squawk': features.get('squawk'),
            'category': features.get('category'),
            'messages': features.get('messages'),
            'seen': features.get('seen'),
            'updated_at': aircraft.updated_at.isoformat() if aircraft.updated_at else None,
        }
        
        aircraft_data.append(aircraft_obj)
    
    # Return in expected format
    return JsonResponse({
        'now': int(timezone.now().timestamp()),
        'aircraft': aircraft_data
    }, json_dumps_params={'indent': 2})


@login_required
def aprs(request):
    """Fetch APRS stations from aprs.fi within the campus outer geofence and return as GeoJSON FeatureCollection like features.json."""
    campus = Campus.objects.get(name=os.getenv('CAMPUS'))
    outer_fence = campus.outer_geofence
    if not outer_fence:
        return JsonResponse({
            'type': 'FeatureCollection',
            'features': [],
            'error': 'No outer geofence configured for this campus',
        }, json_dumps_params={'indent': 2})

    minlat = min(outer_fence.latitude1, outer_fence.latitude2)
    maxlat = max(outer_fence.latitude1, outer_fence.latitude2)
    minlng = min(outer_fence.longitude1, outer_fence.longitude2)
    maxlng = max(outer_fence.longitude1, outer_fence.longitude2)

    api_key = os.getenv('APRS_FI_API_KEY', '')
    if not api_key:
        return JsonResponse({
            'type': 'FeatureCollection',
            'features': [],
            'error': 'APRS_FI_API_KEY not configured',
        }, json_dumps_params={'indent': 2})

    url = (
        'https://api.aprs.fi/api/get?'
        'what=loc&'
        'apikey={apikey}&'
        'minlat={minlat}&maxlat={maxlat}&minlng={minlng}&maxlng={maxlng}&'
        'format=json'
    ).format(
        apikey=api_key,
        minlat=minlat,
        maxlat=maxlat,
        minlng=minlng,
        maxlng=maxlng,
    )

    req = Request(
        url,
        headers={
            'User-Agent': 'evalink/1.0 (+https://github.com/mars-society/evalink)',
        },
    )
    try:
        with urlopen(req, timeout=10) as resp:
            raw = resp.read().decode()
    except (URLError, HTTPError, OSError) as e:
        return JsonResponse({
            'type': 'FeatureCollection',
            'features': [],
            'error': str(e),
        }, json_dumps_params={'indent': 2})

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        return JsonResponse({
            'type': 'FeatureCollection',
            'features': [],
            'error': 'Invalid JSON from aprs.fi: ' + str(e),
        }, json_dumps_params={'indent': 2})

    if data.get('result') != 'ok':
        return JsonResponse({
            'type': 'FeatureCollection',
            'features': [],
            'error': data.get('description', 'aprs.fi request failed'),
        }, json_dumps_params={'indent': 2})

    entries = data.get('entries', [])
    features = []
    for entry in entries:
        try:
            lat = float(entry.get('lat', 0))
            lng = float(entry.get('lng', 0))
        except (TypeError, ValueError):
            continue
        name = entry.get('name', '') or entry.get('srccall', '')
        lasttime = entry.get('lasttime')
        if lasttime is not None:
            try:
                dt = datetime.fromtimestamp(int(lasttime), tz=timezone.utc)
                time_str = dt.isoformat()
            except (TypeError, ValueError, OSError):
                time_str = None
        else:
            time_str = None
        altitude = entry.get('altitude')
        if altitude is not None:
            try:
                altitude = float(altitude)
            except (TypeError, ValueError):
                altitude = None
        prop = {
            'name': name,
            'label': name,
            'time': time_str,
            'altitude': altitude,
            'comment': entry.get('comment'),
            'symbol': entry.get('symbol'),
            'srccall': entry.get('srccall'),
            'dstcall': entry.get('dstcall'),
            'path': entry.get('path'),
            'course': entry.get('course'),
            'speed': entry.get('speed'),
        }
        feat = {
            'type': 'Feature',
            'geometry': {
                'type': 'Point',
                'coordinates': [lng, lat],
            },
            'properties': prop,
        }
        features.append(feat)

    return JsonResponse({
        'type': 'FeatureCollection',
        'features': features,
    }, json_dumps_params={'indent': 2})


@login_required
def oldest_consecutive_inside(request):
    """Find the oldest day with more than two consecutive position logs inside the inner fence"""
    campus = Campus.objects.get(name=os.getenv('CAMPUS'))
    inner_fence = campus.inner_geofence
    
    if not inner_fence:
        return render(request, 'oldest_consecutive_inside.html', {
            'error': 'No inner geofence configured for this campus',
            'campus_name': campus.name
        })
    
    def is_inside_fence(lat, lon):
        """Check if coordinates are inside the inner geofence"""
        return (lat >= inner_fence.latitude1 and lat <= inner_fence.latitude2 and 
                lon >= inner_fence.longitude1 and lon <= inner_fence.longitude2)
    
    # Get all position logs ordered by date (oldest first)
    # Exclude infrastructure and planner stations
    infra_station_ids = Station.objects.filter(station_type='infrastructure').values_list('pk', flat=True)
    planner_station_ids = Station.objects.filter(station_type='planner').values_list('pk', flat=True)
    
    position_logs = PositionLog.objects.exclude(
        station_id__in=list(infra_station_ids) + list(planner_station_ids)
    ).filter(updated_on__isnull=False).order_by('updated_on', 'updated_at')
    
    # Group position logs by day and station
    logs_by_day_station = defaultdict(list)
    for log in position_logs:
        if log.updated_on:
            key = (log.updated_on, log.station_id)
            logs_by_day_station[key].append(log)
    
    # Find the oldest day with >2 consecutive positions inside the fence
    oldest_date = None
    
    # Sort days from oldest to newest
    sorted_days = sorted(logs_by_day_station.keys(), key=lambda x: x[0])
    
    # First pass: find the oldest date with >2 consecutive positions inside
    for day_date, station_id in sorted_days:
        logs = logs_by_day_station[(day_date, station_id)]
        # Sort logs by time within the day
        logs.sort(key=lambda x: x.updated_at)
        
        # Find consecutive sequences inside the fence
        consecutive_inside = []
        current_sequence = []
        
        for log in logs:
            if is_inside_fence(log.latitude, log.longitude):
                current_sequence.append(log)
            else:
                if len(current_sequence) > 2:
                    consecutive_inside.append(len(current_sequence))
                current_sequence = []
        
        # Check if sequence continues to end of day
        if len(current_sequence) > 2:
            consecutive_inside.append(len(current_sequence))
        
        # If we found any sequence with >2 consecutive positions inside
        if consecutive_inside:
            oldest_date = day_date
            break
    
    if oldest_date is None:
        return render(request, 'oldest_consecutive_inside.html', {
            'message': 'No day found with more than two consecutive position logs inside the inner fence',
            'campus_name': campus.name
        })
    
    # Second pass: collect all devices on the oldest date
    devices_data = []
    for day_date, station_id in sorted_days:
        if day_date != oldest_date:
            continue
        
        logs = logs_by_day_station[(day_date, station_id)]
        # Sort logs by time within the day
        logs.sort(key=lambda x: x.updated_at)
        
        # Find consecutive sequences inside the fence
        consecutive_inside = []
        current_sequence = []
        
        for log in logs:
            if is_inside_fence(log.latitude, log.longitude):
                current_sequence.append(log)
            else:
                if len(current_sequence) > 2:
                    consecutive_inside.append(len(current_sequence))
                current_sequence = []
        
        # Check if sequence continues to end of day
        if len(current_sequence) > 2:
            consecutive_inside.append(len(current_sequence))
        
        # If we found any sequence with >2 consecutive positions inside
        if consecutive_inside:
            station = Station.objects.get(pk=station_id)
            # Get the maximum consecutive count for this device
            max_consecutive = max(consecutive_inside)
            devices_data.append({
                'device_name': station.name,
                'device_id': station.id,
                'consecutive_positions': max_consecutive,
                'all_consecutive_counts': consecutive_inside
            })
    
    # Sort devices by consecutive count (descending)
    devices_data.sort(key=lambda x: x['consecutive_positions'], reverse=True)
    
    # Count total position logs in the entire database (excluding infrastructure and planner stations)
    total_position_logs = PositionLog.objects.exclude(
        station_id__in=list(infra_station_ids) + list(planner_station_ids)
    ).count()
    
    return render(request, 'oldest_consecutive_inside.html', {
        'date': oldest_date.isoformat(),
        'devices': devices_data,
        'campus_name': campus.name,
        'total_position_logs': total_position_logs
    })

@login_required
def clear_redundant_logs(request):
    """Clear redundant position logs for a given date, keeping only first and last in each consecutive run"""
    if request.method != 'POST':
        return HttpResponseNotFound("not found")
    
    campus = Campus.objects.get(name=os.getenv('CAMPUS'))
    inner_fence = campus.inner_geofence
    
    if not inner_fence:
        return render(request, 'oldest_consecutive_inside.html', {
            'error': 'No inner geofence configured for this campus',
            'campus_name': campus.name
        })
    
    # Get the date from POST data
    date_str = request.POST.get('date')
    if not date_str:
        return render(request, 'oldest_consecutive_inside.html', {
            'error': 'Date parameter is required',
            'campus_name': campus.name
        })
    
    try:
        target_date = parse_date(date_str)
        if target_date is None:
            return render(request, 'oldest_consecutive_inside.html', {
                'error': 'Invalid date format',
                'campus_name': campus.name
            })
    except Exception as e:
        return render(request, 'oldest_consecutive_inside.html', {
            'error': f'Invalid date: {str(e)}',
            'campus_name': campus.name
        })
    
    def is_inside_fence(lat, lon):
        """Check if coordinates are inside the inner geofence"""
        return (lat >= inner_fence.latitude1 and lat <= inner_fence.latitude2 and 
                lon >= inner_fence.longitude1 and lon <= inner_fence.longitude2)
    
    # Get all position logs for the target date
    # Exclude infrastructure and planner stations
    infra_station_ids = Station.objects.filter(station_type='infrastructure').values_list('pk', flat=True)
    planner_station_ids = Station.objects.filter(station_type='planner').values_list('pk', flat=True)
    
    position_logs = PositionLog.objects.exclude(
        station_id__in=list(infra_station_ids) + list(planner_station_ids)
    ).filter(updated_on=target_date).order_by('station_id', 'updated_at')
    
    # Group position logs by station
    logs_by_station = defaultdict(list)
    for log in position_logs:
        logs_by_station[log.station_id].append(log)
    
    total_deleted = 0
    stations_processed = 0
    
    # Process each station
    for station_id, logs in logs_by_station.items():
        # Sort logs by time
        logs.sort(key=lambda x: x.updated_at)
        
        # Find consecutive sequences inside the fence
        consecutive_runs = []
        current_run = []
        
        for log in logs:
            if is_inside_fence(log.latitude, log.longitude):
                current_run.append(log)
            else:
                if len(current_run) > 2:
                    consecutive_runs.append(current_run)
                current_run = []
        
        # Check if sequence continues to end of day
        if len(current_run) > 2:
            consecutive_runs.append(current_run)
        
        # Process each consecutive run
        for run in consecutive_runs:
            if len(run) <= 2:
                continue
            
            # Keep first and last, delete intermediate ones
            first_log = run[0]
            last_log = run[-1]
            intermediate_logs = run[1:-1]
            
            # Delete intermediate logs, but skip those referenced by TextLog
            for log_to_delete in intermediate_logs:
                # Skip if this PositionLog is referenced by a TextLog
                if TextLog.objects.filter(position_log=log_to_delete).exists():
                    continue
                
                # Delete the PositionLog (this will cascade delete TelemetryLog and NeighborLog)
                log_to_delete.delete()
                total_deleted += 1
        
        if consecutive_runs:
            stations_processed += 1
    
    # Redirect back to the oldest_consecutive_inside page
    return redirect('oldest_consecutive_inside')

@login_required
def eva_statistics(request):
    """View to display EVA statistics in an HTML table"""
    campus = Campus.objects.get(name=os.getenv('CAMPUS'))
    inner_fence = campus.inner_geofence
    
    if not inner_fence:
        return render(request, 'eva_statistics.html', {
            'error': 'No inner geofence configured for this campus'
        })
    
    # Get all stations (excluding infrastructure and ignore types)
    stations = Station.objects.exclude(
        Q(station_type='infrastructure') | Q(station_type='ignore')
    ).all()
    
    # Statistics dictionaries
    stats_by_year = defaultdict(lambda: {'count': 0, 'total_distance': 0.0, 'distances': []})
    stats_by_month = defaultdict(lambda: {'count': 0, 'total_distance': 0.0, 'distances': []})
    total_stats = {'count': 0, 'total_distance': 0.0, 'distances': []}
    
    def is_outside_fence(lat, lon):
        """Check if coordinates are outside the inner geofence"""
        return (lat < inner_fence.latitude1 or lat > inner_fence.latitude2 or 
                lon < inner_fence.longitude1 or lon > inner_fence.longitude2)
    
    def detect_eva_trips(position_logs):
        """Detect EVA trips from position logs by finding sequences outside the geofence"""
        trips = []
        current_trip = []
        outside_fence = False
        
        for log in position_logs:
            is_outside = is_outside_fence(log.latitude, log.longitude)
            
            if is_outside and not outside_fence:
                # Starting a new trip outside the fence
                current_trip = [log]
                outside_fence = True
            elif is_outside and outside_fence:
                # Continuing current trip
                current_trip.append(log)
            elif not is_outside and outside_fence:
                # Ending current trip
                if len(current_trip) >= 2:  # Need at least 2 points to calculate distance
                    trips.append(current_trip)
                current_trip = []
                outside_fence = False
        
        # Handle case where trip ends while still outside fence
        if outside_fence and len(current_trip) >= 2:
            trips.append(current_trip)
        
        return trips
    
    def calculate_trip_distance(trip_logs):
        """Calculate total distance for a trip"""
        total_distance = 0.0
        for i in range(1, len(trip_logs)):
            prev_log = trip_logs[i-1]
            curr_log = trip_logs[i]
            distance = haversine_distance(
                prev_log.latitude, prev_log.longitude,
                curr_log.latitude, curr_log.longitude
            )
            total_distance += distance
        return total_distance
    
    # Process each station
    for station in stations:
        # Get all position logs for this station, ordered by time
        position_logs = PositionLog.objects.filter(
            station=station
        ).order_by('updated_at')
        
        if not position_logs.exists():
            continue
        
        # Detect EVA trips for this station
        eva_trips = detect_eva_trips(position_logs)
        
        # Process each detected trip
        for trip in eva_trips:
            if len(trip) < 2:
                continue
                
            trip_distance = calculate_trip_distance(trip)
            
            # Use the first log's timestamp for year/month classification
            first_log = trip[0]
            trip_date = first_log.updated_at
            year = trip_date.year
            month_key = f"{year}-{trip_date.month:02d}"
            
            # Update statistics
            stats_by_year[year]['count'] += 1
            stats_by_year[year]['total_distance'] += trip_distance
            stats_by_year[year]['distances'].append(trip_distance)
            
            stats_by_month[month_key]['count'] += 1
            stats_by_month[month_key]['total_distance'] += trip_distance
            stats_by_month[month_key]['distances'].append(trip_distance)
            
            total_stats['count'] += 1
            total_stats['total_distance'] += trip_distance
            total_stats['distances'].append(trip_distance)
    
    # Calculate averages
    for year_data in stats_by_year.values():
        if year_data['count'] > 0:
            year_data['average_distance'] = year_data['total_distance'] / year_data['count']
        else:
            year_data['average_distance'] = 0.0
    
    for month_data in stats_by_month.values():
        if month_data['count'] > 0:
            month_data['average_distance'] = month_data['total_distance'] / month_data['count']
        else:
            month_data['average_distance'] = 0.0
    
    if total_stats['count'] > 0:
        total_stats['average_distance'] = total_stats['total_distance'] / total_stats['count']
    else:
        total_stats['average_distance'] = 0.0
    
    # Sort data for display
    sorted_years = sorted(stats_by_year.items())
    sorted_months = sorted(stats_by_month.items())
    
    context = {
        'total_stats': total_stats,
        'stats_by_year': sorted_years,
        'stats_by_month': sorted_months,
        'campus_name': campus.name
    }
    
    return render(request, 'eva_statistics.html', context)
