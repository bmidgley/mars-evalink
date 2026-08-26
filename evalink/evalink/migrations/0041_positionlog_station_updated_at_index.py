from django.contrib.postgres.operations import AddIndexConcurrently
from django.db import migrations, models


class Migration(migrations.Migration):

    atomic = False

    dependencies = [
        ('evalink', '0040_aircraftpositionlog_aircraft_lat_lon_minute_unique'),
    ]

    operations = [
        AddIndexConcurrently(
            model_name='positionlog',
            index=models.Index(fields=['station', '-updated_at'], name='poslog_station_updated_at'),
        ),
    ]
