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
    hardware_type = models.IntegerField()
    station_type = models.CharField(max_length=255)

class Station(models.Model):
    station_profile = models.ForeignKey(StationProfile, on_delete=models.SET_NULL, null=True, db_index=True)
    firmware = models.CharField(null=True, max_length=100)
    hardware = models.ForeignKey(Hardware, on_delete=models.SET_NULL, null=True, db_index=True)
    name = models.CharField(max_length=255, db_index=True)
    short_name = models.CharField(max_length=255)
    configuration = models.JSONField(null=True, blank=True)
    features = models.JSONField(null=True, blank=True)
    hardware_node = models.CharField(max_length=64, db_index=True, null=False)
    hardware_number = models.BigIntegerField(db_index=True)
    updated_at = models.DateTimeField(null=False, db_index=True)
    station_type = models.CharField(max_length=255)

class PositionLog(models.Model):
    station = models.ForeignKey(Station, on_delete=models.CASCADE, db_index=True)
    latitude = models.FloatField()
    longitude = models.FloatField()
    altitude = models.FloatField(null=True)
    ground_speed = models.FloatField(null=True)
    ground_track = models.FloatField(null=True)
    updated_at = models.DateTimeField(null=False, db_index=True)

class TelemetryLog(models.Model):
    station = models.ForeignKey(Station, on_delete=models.CASCADE, db_index=True)
    position_log = models.ForeignKey(PositionLog, on_delete=models.SET_NULL, null=True, db_index=True)
    temperature = models.FloatField(null=True)
    relative_humidity = models.FloatField(null=True)
    barometric_pressure = models.FloatField(null=True)
    current = models.FloatField(null=True)
    voltage = models.FloatField(null=True)
    battery_level = models.FloatField(null=True)
    updated_at = models.DateTimeField(null=False, db_index=True)

class TextLog(models.Model):
    station = models.ForeignKey(Station, on_delete=models.CASCADE, db_index=True)
    position_log = models.ForeignKey(PositionLog, on_delete=models.SET_NULL, null=True, db_index=True)
    destination = models.ForeignKey(Station, related_name='destination', on_delete=models.SET_NULL, db_index=True, null=True)
    text = models.TextField(db_index=True)
    updated_at = models.DateTimeField(null=False, db_index=True)

class NeighborLog(models.Model):
    station = models.ForeignKey(Station, on_delete=models.CASCADE, db_index=True)
    neighbor = models.ForeignKey(Station, related_name='neighbor', on_delete=models.CASCADE, db_index=True)
    position_log = models.ForeignKey(PositionLog, on_delete=models.SET_NULL, null=True, db_index=True)
    rssi = models.FloatField()
    updated_at = models.DateTimeField(null=False, db_index=True)
