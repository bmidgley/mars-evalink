from django.http import JsonResponse, HttpResponse
from evalink.models import *
from datetime import date
from datetime import timedelta

def features(request):
    data = {
        "type": "FeatureCollection",
        "features": [],
    }
    past = date.today() - timedelta(days = 2)
    for station in Station.objects.filter(updated_at__gt = past).order_by('id').all():
        if station.features: data["features"].append(station.features)
    return JsonResponse(data, json_dumps_params={'indent': 2})
