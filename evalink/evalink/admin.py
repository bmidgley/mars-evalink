from django.contrib import admin

from .models import *

class HardwareAdmin(admin.ModelAdmin):
    list_display = [f.name for f in Hardware._meta.fields]
class StationAdmin(admin.ModelAdmin):
    list_display = [f.name for f in Station._meta.fields]
class StationProfileAdmin(admin.ModelAdmin):
    list_display = [f.name for f in StationProfile._meta.fields]
class PositionLogAdmin(admin.ModelAdmin):
    list_display = [f.name for f in PositionLog._meta.fields]
class TelemetryLogAdmin(admin.ModelAdmin):
    list_display = [f.name for f in TelemetryLog._meta.fields]
class TextLogAdmin(admin.ModelAdmin):
    list_display = [f.name for f in TextLog._meta.fields]
class NeighborLogAdmin(admin.ModelAdmin):
    list_display = [f.name for f in NeighborLog._meta.fields]

admin.site.register(Hardware, HardwareAdmin)
admin.site.register(Station, StationAdmin)
admin.site.register(StationProfile, StationProfileAdmin)
admin.site.register(PositionLog, PositionLogAdmin)
admin.site.register(TelemetryLog, TelemetryLogAdmin)
admin.site.register(TextLog, TextLogAdmin)
admin.site.register(NeighborLog, NeighborLogAdmin)
