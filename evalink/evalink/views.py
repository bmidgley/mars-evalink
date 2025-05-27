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
    past = date.today() - timedelta(days = 30)
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
    current = date.today() + timedelta(days = 1)
    before_date = localdate("before", request.GET.get('before_date'), current)
    after_date = localdate("after", request.GET.get('after_date'), None)
    models = {0: 'UNSET', 1: 'TLORA_V2', 2: 'TLORA_V1', 3: 'TLORA_V2_1_1P6', 4: 'TBEAM', 5: 'HELTEC_V2_0', 6: 'TBEAM_V0P7', 7: 'T_ECHO', 8: 'TLORA_V1_1P3', 9: 'RAK4631', 10: 'HELTEC_V2_1', 11: 'HELTEC_V1', 12: 'LILYGO_TBEAM_S3_CORE', 13: 'RAK11200', 14: 'NANO_G1', 15: 'TLORA_V2_1_1P8', 16: 'TLORA_T3_S3', 17: 'NANO_G1_EXPLORER', 18: 'NANO_G2_ULTRA', 19: 'LORA_TYPE', 20: 'WIPHONE', 21: 'WIO_WM1110', 22: 'RAK2560', 23: 'HELTEC_HRU_3601', 24: 'HELTEC_WIRELESS_BRIDGE', 25: 'STATION_G1', 26: 'RAK11310', 27: 'SENSELORA_RP2040', 28: 'SENSELORA_S3', 29: 'CANARYONE', 30: 'RP2040_LORA', 31: 'STATION_G2', 32: 'LORA_RELAY_V1', 33: 'NRF52840DK', 34: 'PPR', 35: 'GENIEBLOCKS', 36: 'NRF52_UNKNOWN', 37: 'PORTDUINO', 38: 'ANDROID_SIM', 39: 'DIY_V1', 40: 'NRF52840_PCA10059', 41: 'DR_DEV', 42: 'M5STACK', 43: 'HELTEC_V3', 44: 'HELTEC_WSL_V3', 45: 'BETAFPV_2400_TX', 46: 'BETAFPV_900_NANO_TX', 47: 'RPI_PICO', 48: 'HELTEC_WIRELESS_TRACKER', 49: 'HELTEC_WIRELESS_PAPER', 50: 'T_DECK', 51: 'T_WATCH_S3', 52: 'PICOMPUTER_S3', 53: 'HELTEC_HT62', 54: 'EBYTE_ESP32_S3', 55: 'ESP32_S3_PICO', 56: 'CHATTER_2', 57: 'HELTEC_WIRELESS_PAPER_V1_0', 58: 'HELTEC_WIRELESS_TRACKER_V1_0', 59: 'UNPHONE', 60: 'TD_LORAC', 61: 'CDEBYTE_EORA_S3', 62: 'TWC_MESH_V4', 63: 'NRF52_PROMICRO_DIY', 64: 'RADIOMASTER_900_BANDIT_NANO', 65: 'HELTEC_CAPSULE_SENSOR_V3', 66: 'HELTEC_VISION_MASTER_T190', 67: 'HELTEC_VISION_MASTER_E213', 68: 'HELTEC_VISION_MASTER_E290', 69: 'HELTEC_MESH_NODE_T114', 70: 'SENSECAP_INDICATOR', 71: 'TRACKER_T1000_E', 72: 'RAK3172', 73: 'WIO_E5', 74: 'RADIOMASTER_900_BANDIT', 75: 'ME25LS01_4Y10TD', 76: 'RP2040_FEATHER_RFM95', 77: 'M5STACK_COREBASIC', 78: 'M5STACK_CORE2', 79: 'RPI_PICO2', 80: 'M5STACK_CORES3', 81: 'SEEED_XIAO_S3', 82: 'MS24SF1', 83: 'TLORA_C6'}
    result = {'id': station.id, 'name': station.name, 'date': None, 'waypoints': [], 'points': [], 'hardware_name': models.get(station.hardware.hardware_type, station.hardware.hardware_type)}
    if after_date:
        position_log = PositionLog.objects.filter(station=station,updated_on__gt=after_date).filter(
                                                  Q(latitude__gt=g.latitude2) | Q(latitude__lt=g.latitude1) | Q(longitude__gt=g.longitude2) | Q(longitude__lt=g.longitude1)).order_by('updated_at').first()
    else:
        position_log = PositionLog.objects.filter(station=station,updated_on__lt=before_date).filter(
                                                  Q(latitude__gt=g.latitude2) | Q(latitude__lt=g.latitude1) | Q(longitude__gt=g.longitude2) | Q(longitude__lt=g.longitude1)).order_by('-updated_at').first()
    if position_log:
        found_date = position_log.updated_at.astimezone(timezone.get_current_timezone()).date()
        result['date'] = found_date
        position_logs = list(PositionLog.objects.filter(station=station, updated_on=found_date).filter(
                                                  Q(latitude__gt=g.latitude2) | Q(latitude__lt=g.latitude1) | Q(longitude__gt=g.longitude2) | Q(longitude__lt=g.longitude1)).order_by('timestamp', 'updated_at').all())
        weather_logs = list(TelemetryLog.objects.filter(station=station, updated_on=found_date, temperature__isnull=False).order_by('updated_at').all())
        wind_weather_logs = [sample for sample in weather_logs if sample.wind_speed != None]
        if wind_weather_logs != []: weather_logs = wind_weather_logs

        for log in position_logs:
            sample = closest(log.updated_at, weather_logs)
            event = {'latitude': log.latitude, 'longitude': log.longitude, 'altitude': log.altitude, 'updated_at': log.updated_at}
            if sample:
                if(sample.wind_speed != None): event['wind_speed'] = sample.wind_speed
                if(sample.wind_direction != None): event['wind_direction'] = sample.wind_direction
                event['temperature'] = sample.temperature
            result['points'].append(event)

        text_logs = TextLog.objects.filter(station=station, updated_at__date=found_date).order_by('updated_at').all()
        for text in text_logs:
            if text.position_log:
                result['waypoints'].append({'latitude': text.position_log.latitude, 'longitude': text.position_log.longitude, 'altitude': text.position_log.altitude, 'updated_at': text.updated_at, 'text': text.text})
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
            # do not process the message now or it will appear as a duplicate when it's seen on the network
            # timestamp = int(datetime.timestamp(datetime.now()))
            # text_message = {'channel': 0, 'from': gateway_node_number, 'id': timestamp, 'payload': {'text': message}, 'timestamp': timestamp, 'type': 'text'}
            # handler.process_message(text_message)

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
    past = date.today() - timedelta(days = 30)
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
def search(request):
    campus = Campus.objects.get(name=os.getenv('CAMPUS'))
    tz = pytz.timezone(campus.time_zone)
    latitude1 = float(request.GET.get('latitude1'))
    latitude2 = float(request.GET.get('latitude2'))
    longitude1 = float(request.GET.get('longitude1'))
    longitude2 = float(request.GET.get('longitude2'))
    latitude1, latitude2 = sorted([latitude1, latitude2])
    longitude1, longitude2 = sorted([longitude1, longitude2])
    infra_station_ids = Station.objects.filter(station_type='infrastructure').values_list('pk', flat=True)
    position_logs = PositionLog.objects.exclude(station_id__in=infra_station_ids).filter(
            Q(latitude__gt=latitude1) & Q(latitude__lt=latitude2) & Q(longitude__gt=longitude1) & Q(longitude__lt=longitude2)).order_by('-updated_at')[:100000]
    results = []
    paths = []
    for position_log in position_logs:
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
