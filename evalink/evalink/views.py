from django.http import JsonResponse, HttpResponseNotFound
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
    data = {
        "type": "FeatureCollection",
        "features": [],
    }
    past = date.today() - timedelta(days = 30)
    top_stations = Station.objects.filter(updated_at__gt = past).order_by('-updated_at').all()[:55]
    for station in sorted(top_stations, key=lambda x: x.name.lower(), reverse=False):
        if fully_populated(station.features):
            station.features['properties']['hardware_number'] = station.hardware_number
            station.features['properties']['hardware_node'] = station.hardware_node
            station.features['properties']['id'] = station.id
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
    return JsonResponse([text_message.serialize() for text_message in text_messages], safe=False, json_dumps_params={'indent': 2})

@login_required
def path(request):
    id = request.GET.get('id')
    station = Station.objects.filter(id=id).first()
    if station == None: return HttpResponseNotFound("not found")
    campus = Campus.objects.first()
    g = campus.inner_geofence
    current = date.today() + timedelta(days = 1)
    before_date = localdate("before", request.GET.get('before_date'), current)
    after_date = localdate("after", request.GET.get('after_date'), None)
    result = {'id': station.id, 'name': station.name, 'date': None, 'waypoints': [], 'points': []}
    if after_date:
        position_log = PositionLog.objects.filter(station=station,updated_at__date__gt=after_date).filter(
                                                  Q(latitude__gt=g.latitude2) | Q(latitude__lt=g.latitude1) | Q(longitude__gt=g.longitude2) | Q(longitude__lt=g.longitude1)).order_by('updated_at').first()
    else:
        position_log = PositionLog.objects.filter(station=station,updated_at__date__lt=before_date).filter(
                                                  Q(latitude__gt=g.latitude2) | Q(latitude__lt=g.latitude1) | Q(longitude__gt=g.longitude2) | Q(longitude__lt=g.longitude1)).order_by('-updated_at').first()
    if position_log:
        found_date = position_log.updated_at.astimezone(timezone.get_current_timezone()).date()
        result['date'] = found_date
        position_logs = PositionLog.objects.filter(station=station, updated_at__date=found_date).filter(
                                                  Q(latitude__gt=g.latitude2) | Q(latitude__lt=g.latitude1) | Q(longitude__gt=g.longitude2) | Q(longitude__lt=g.longitude1)).order_by('updated_at').all()
        for log in position_logs:
            result['points'].append({'latitude': log.latitude, 'longitude': log.longitude, 'altitude': log.altitude, 'updated_at': log.updated_at})
        text_logs = TextLog.objects.filter(station=station, updated_at__date=found_date).order_by('updated_at').all()
        for text in text_logs:
            if text.position_log:
                result['waypoints'].append({'latitude': text.position_log.latitude, 'longitude': text.position_log.longitude, 'altitude': text.position_log.altitude, 'updated_at': text.updated_at, 'text': text.text})
    else:
        result['date'] = before_date.isoformat()[0:10]
    return JsonResponse(result, json_dumps_params={'indent': 2})

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
