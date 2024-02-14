from django.http import JsonResponse, HttpResponse
from django.contrib.auth.decorators import login_required
from evalink.models import *
from datetime import date
from datetime import timedelta
from django.shortcuts import render
from .forms import ChatForm

@login_required
def features(request):
    data = {
        "type": "FeatureCollection",
        "features": [],
    }
    past = date.today() - timedelta(days = 1)
    for station in Station.objects.filter(updated_at__gt = past).order_by('id').all():
        if station.features and 'geometry' in station.features and 'coordinates' in station.features['geometry']:
            data["features"].append(station.features)
    return JsonResponse(data, json_dumps_params={'indent': 2})

@login_required
def chat(request):
    if request.method == "POST":
        form = ChatForm(request.POST)
        if form.is_valid():
            message = form.cleaned_data['message']
            print(message)

    form = ChatForm()
    return render(request, "chat.html", {"form": form})