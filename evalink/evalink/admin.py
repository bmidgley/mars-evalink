from django.contrib import admin

from .models import *

admin.site.register(Hardware)
admin.site.register(Station)
admin.site.register(PositionLog)
admin.site.register(TelemetryLog)
admin.site.register(TextLog)