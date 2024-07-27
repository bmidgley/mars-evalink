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
class StationMeasureAdmin(admin.ModelAdmin):
    list_display = [f.name for f in StationMeasure._meta.fields]

class CampusAdmin(admin.ModelAdmin):
    list_display = [f.name for f in Campus._meta.fields]

class VehicleAdmin(admin.ModelAdmin):
    list_display = [f.name for f in Vehicle._meta.fields]

class CrewAdmin(admin.ModelAdmin):
    list_display = [f.name for f in Crew._meta.fields]

class CrewmemberAdmin(admin.ModelAdmin):
    list_display = [f.name for f in Crewmember._meta.fields]

class EvaAdmin(admin.ModelAdmin):
    list_display = [f.name for f in Eva._meta.fields]

class EvaCrewmemberAdmin(admin.ModelAdmin):
    list_display = [f.name for f in EvaCrewmember._meta.fields]

class EvaVehicleAdmin(admin.ModelAdmin):
    list_display = [f.name for f in EvaVehicle._meta.fields]

class EvaStationAdmin(admin.ModelAdmin):
    list_display = [f.name for f in EvaStation._meta.fields]

class GeofenceAdmin(admin.ModelAdmin):
    list_display = [f.name for f in Geofence._meta.fields]

admin.site.register(Hardware, HardwareAdmin)
admin.site.register(Station, StationAdmin)
admin.site.register(StationProfile, StationProfileAdmin)
admin.site.register(PositionLog, PositionLogAdmin)
admin.site.register(TelemetryLog, TelemetryLogAdmin)
admin.site.register(TextLog, TextLogAdmin)
admin.site.register(NeighborLog, NeighborLogAdmin)
admin.site.register(StationMeasure, StationMeasureAdmin)
admin.site.register(Campus, CampusAdmin)
admin.site.register(Vehicle, VehicleAdmin)
admin.site.register(Crew, CrewAdmin)
admin.site.register(Crewmember, CrewmemberAdmin)
admin.site.register(Eva, EvaAdmin)
admin.site.register(EvaCrewmember, EvaCrewmemberAdmin)
admin.site.register(EvaVehicle, EvaVehicleAdmin)
admin.site.register(EvaStation, EvaStationAdmin)
admin.site.register(Geofence, GeofenceAdmin)
