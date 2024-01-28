from django.http import JsonResponse, HttpResponse

def features(request):
    data = {
        "type": "FeatureCollection",
        "features": [],
    }
    return JsonResponse(data)