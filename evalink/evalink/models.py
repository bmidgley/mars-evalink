from django.db import models
from django.contrib.auth.models import User

from django.utils import timezone
from django.contrib.postgres.fields import ArrayField
from django.db.models.query import QuerySet

class Hardware(models.Model):
    name = models.CharField(max_length=255, db_index=True)
    hardware_type = models.IntegerField()
    station_type = models.CharField(max_length=255)

class Station(models.Model):
    hardware = models.ForeignKey(Hardware, on_delete=models.SET_NULL, null=True, db_index=True)
    name = models.CharField(max_length=255, db_index=True)
    short_name = models.CharField(max_length=255)
    configuration = models.JSONField(null=True, blank=True)
    hardware_node = models.CharField(max_length=64, db_index=True, null=False)
    hardware_number = models.IntegerField(db_index=True)
    updated_at = models.DateTimeField(null=False, db_index=True)
    station_type = models.CharField(max_length=255)

class PositionLog(models.Model):
    station = models.ForeignKey(Station, on_delete=models.CASCADE, db_index=True)
    latitude = models.FloatField()
    longitude = models.FloatField()
    altitude = models.FloatField()
    ground_speed = models.FloatField()
    ground_track = models.FloatField()
    updated_at = models.DateTimeField(null=False, db_index=True)

class TelemetryLog(models.Model):
    station = models.ForeignKey(Station, on_delete=models.CASCADE, db_index=True)
    position_log = models.ForeignKey(PositionLog, on_delete=models.SET_NULL, null=True, db_index=True)
    temperature = models.FloatField()
    humidity = models.FloatField()
    current = models.FloatField()
    voltage = models.FloatField()
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
