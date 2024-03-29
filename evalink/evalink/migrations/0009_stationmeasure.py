# Generated by Django 4.2.9 on 2024-02-05 06:14

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('evalink', '0008_stationprofile_station_firmware_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='StationMeasure',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('features', models.JSONField()),
                ('updated_at', models.DateTimeField(db_index=True)),
                ('station', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='evalink.station')),
            ],
        ),
    ]
