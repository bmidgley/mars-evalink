# Generated by Django 4.2.9 on 2024-01-29 01:59

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('evalink', '0006_station_features'),
    ]

    operations = [
        migrations.RenameField(
            model_name='telemetrylog',
            old_name='humidity',
            new_name='relative_humidity',
        ),
    ]
