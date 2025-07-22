from django.db import models
from django.contrib.auth.models import User

from django.utils import timezone
from django.contrib.postgres.fields import ArrayField
from django.db.models.query import QuerySet

class StationProfile(models.Model):
    name = models.CharField(max_length=255, db_index=True)
    configuration = models.JSONField()
    compatible_firmwares = ArrayField(
        models.CharField(null=False, max_length=100),
        null=False,
        default=list,
    )

class Hardware(models.Model):
    name = models.CharField(max_length=255, db_index=True)
    hardware_type = models.IntegerField(unique=False)
    station_type = models.CharField(max_length=255)
    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['station_type', 'hardware_type'], name='unique_station_type_hardware_type'),
        ]
class Station(models.Model):
    station_profile = models.ForeignKey(StationProfile, on_delete=models.SET_NULL, null=True, db_index=True)
    last_position = models.ForeignKey("PositionLog", related_name='last_position', on_delete=models.SET_NULL, null=True, db_index=True)
    firmware = models.CharField(null=True, blank=True, max_length=100)
    hardware = models.ForeignKey(Hardware, on_delete=models.SET_NULL, null=True, db_index=True)
    name = models.CharField(max_length=255, db_index=True)
    short_name = models.CharField(max_length=255)
    configuration = models.JSONField(null=True, blank=True)
    features = models.JSONField(null=True, blank=True)
    hardware_node = models.CharField(max_length=64, db_index=True, null=False)
    hardware_number = models.BigIntegerField(db_index=True, unique=True)
    updated_at = models.DateTimeField(null=False, db_index=True, auto_now=True)
    station_type = models.CharField(max_length=255)
    def outside(self, fence):
        return self.last_position and fence.outside(self.last_position.latitude, self.last_position.longitude)

class StationMeasure(models.Model):
    station = models.ForeignKey(Station, on_delete=models.CASCADE, null=False, db_index=True)
    features = models.JSONField(null=False, blank=False)
    updated_at = models.DateTimeField(null=False, db_index=True, auto_now=True)

class PositionLog(models.Model):
    message_id = models.BigIntegerField(db_index=True, null=True)
    station = models.ForeignKey(Station, on_delete=models.CASCADE, db_index=True)
    latitude = models.FloatField(db_index=True)
    longitude = models.FloatField(db_index=True)
    altitude = models.FloatField(null=True)
    ground_speed = models.FloatField(null=True)
    ground_track = models.FloatField(null=True)
    timestamp = models.DateTimeField(null=True, db_index=True)
    updated_at = models.DateTimeField(null=False, db_index=True, auto_now=True)
    updated_on = models.DateField(null=True, db_index=True)

class TelemetryLog(models.Model):
    message_id = models.BigIntegerField(db_index=True, null=True, unique=True)
    station = models.ForeignKey(Station, on_delete=models.CASCADE, db_index=True)
    position_log = models.ForeignKey(PositionLog, on_delete=models.CASCADE, null=True, db_index=True)
    temperature = models.FloatField(null=True)
    relative_humidity = models.FloatField(null=True)
    barometric_pressure = models.FloatField(null=True)
    wind_direction = models.FloatField(null=True)
    wind_speed = models.FloatField(null=True)
    wind_gust = models.FloatField(null=True)
    wind_lull = models.FloatField(null=True)
    current = models.FloatField(null=True)
    voltage = models.FloatField(null=True)
    battery_level = models.FloatField(null=True)
    updated_at = models.DateTimeField(null=False, db_index=True, auto_now=True)
    updated_on = models.DateField(null=True, db_index=True)

class TextLog(models.Model):
    station = models.ForeignKey(Station, on_delete=models.CASCADE, db_index=True)
    position_log = models.ForeignKey(PositionLog, on_delete=models.RESTRICT, null=True, db_index=True)
    destination = models.ForeignKey(Station, related_name='destination', on_delete=models.SET_NULL, db_index=True, null=True, blank=True)
    text = models.TextField(db_index=True)
    serial_number = models.BigIntegerField(db_index=True, unique=True)
    updated_at = models.DateTimeField(null=False, db_index=True, auto_now=True)
    def serialize(self, show_all=False):
        station_type = self.station.station_type
        if station_type == 'ignore' and show_all: station_type = 'infrastructure'
        return {
            "id": self.id,
            "stataion_id": self.station_id,
            "station": self.station.name,
            "station_type": station_type,
            "text": self.text,
            "position": [getattr(self.position_log, 'latitude', None),getattr(self.position_log, 'longitude', None)],
            "updated_at": self.updated_at
        }

class NeighborLog(models.Model):
    station = models.ForeignKey(Station, on_delete=models.CASCADE, db_index=True)
    neighbor = models.ForeignKey(Station, related_name='neighbor', on_delete=models.CASCADE, db_index=True)
    position_log = models.ForeignKey(PositionLog, on_delete=models.CASCADE, null=True, db_index=True)
    rssi = models.FloatField()
    updated_at = models.DateTimeField(null=False, db_index=True, auto_now=True)

class Geofence(models.Model):
    latitude1 = models.FloatField()
    longitude1 = models.FloatField()
    latitude2 = models.FloatField()
    longitude2 = models.FloatField()
    def outside(self, lat, lon):
        return lat < self.latitude1 or lat > self.latitude2 or lon < self.longitude1 or lon > self.longitude2

class Campus(models.Model):
    name = models.CharField(max_length=64, db_index=True, null=False)
    latitude = models.FloatField()
    longitude = models.FloatField()
    altitude = models.FloatField(null=True, blank=True)
    mailing_address = models.TextField(null=True, blank=True)
    inner_geofence = models.ForeignKey(Geofence, related_name='inner_campus_set', on_delete=models.SET_NULL, null=True, db_index=True, blank=True)
    outer_geofence = models.ForeignKey(Geofence, related_name='outer_campus_set', on_delete=models.SET_NULL, null=True, db_index=True, blank=True)
    time_zone = models.TextField(null=False, default='America/Denver')
    updated_at = models.DateTimeField(null=False, db_index=True, auto_now=True)

class Vehicle(models.Model):
    name = models.CharField(max_length=64, db_index=True, null=False)
    campus = models.ForeignKey(Campus, on_delete=models.CASCADE, db_index=True)
    station = models.ForeignKey(Station, on_delete=models.CASCADE, db_index=True)

class Crew(models.Model):
    campus = models.ForeignKey(Campus, on_delete=models.CASCADE, db_index=True)
    name = models.CharField(max_length=64, db_index=True, null=False)
    start_date = models.DateField(null=False)
    end_date = models.DateField(null=False)
    updated_at = models.DateTimeField(null=False, db_index=True, auto_now=True)

class Crewmember(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, db_index=True)
    crew = models.ForeignKey(Crew, on_delete=models.CASCADE, db_index=True)
    role = models.CharField(max_length=64, db_index=True, null=False)
    updated_at = models.DateTimeField(null=False, db_index=True, auto_now=True)

class CrewmemberVitals(models.Model):
    crewmember = models.ForeignKey(Crewmember, on_delete=models.CASCADE, db_index=True)
    vitals = models.JSONField(null=False, blank=False)
    updated_at = models.DateTimeField(null=False, db_index=True, auto_now=True)

class Eva(models.Model):
    name = models.CharField(max_length=64, db_index=True, null=False)
    crew = models.ForeignKey(Crew, on_delete=models.CASCADE, db_index=True)
    start_at = models.DateTimeField(null=False, db_index=True)
    end_at = models.DateTimeField(null=False, db_index=True)
    updated_at = models.DateTimeField(null=False, db_index=True, auto_now=True)

class EvaCrewmember(models.Model):
    eva = models.ForeignKey(Eva, on_delete=models.CASCADE, db_index=True)
    crewmember = models.ForeignKey(Crewmember, on_delete=models.CASCADE, db_index=True)

class EvaVehicle(models.Model):
    eva = models.ForeignKey(Eva, on_delete=models.CASCADE, db_index=True)
    vehicle = models.ForeignKey(Vehicle, on_delete=models.CASCADE, db_index=True)

class EvaStation(models.Model):
    eva = models.ForeignKey(Eva, on_delete=models.CASCADE, db_index=True)
    station = models.ForeignKey(Station, on_delete=models.CASCADE, db_index=True)
    eva_vehicle = models.ForeignKey(EvaVehicle, on_delete=models.SET_NULL, null=True)
    eva_crewmember = models.ForeignKey(EvaCrewmember, on_delete=models.SET_NULL, null=True)
