# Generated by Django 4.2.9 on 2024-02-24 03:52

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('evalink', '0013_station_last_position'),
    ]

    operations = [
        migrations.CreateModel(
            name='Campus',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(db_index=True, max_length=64)),
                ('latitude', models.FloatField()),
                ('longitude', models.FloatField()),
                ('altitude', models.FloatField(null=True)),
                ('mailing_address', models.TextField(null=True)),
                ('updated_at', models.DateTimeField(db_index=True)),
            ],
        ),
        migrations.CreateModel(
            name='Crew',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(db_index=True, max_length=64)),
                ('start_date', models.DateField()),
                ('end_date', models.DateField()),
                ('updated_at', models.DateTimeField(db_index=True)),
                ('campus', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='evalink.campus')),
            ],
        ),
        migrations.CreateModel(
            name='Crewmember',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('role', models.CharField(db_index=True, max_length=64)),
                ('updated_at', models.DateTimeField(db_index=True)),
                ('crew', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='evalink.crew')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='Eva',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(db_index=True, max_length=64)),
                ('start_at', models.DateTimeField(db_index=True)),
                ('end_at', models.DateTimeField(db_index=True)),
                ('updated_at', models.DateTimeField(db_index=True)),
                ('crew', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='evalink.crew')),
            ],
        ),
        migrations.CreateModel(
            name='EvaCrewmember',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('crewmember', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='evalink.crewmember')),
                ('eva', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='evalink.eva')),
            ],
        ),
        migrations.CreateModel(
            name='Vehicle',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(db_index=True, max_length=64)),
                ('campus', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='evalink.campus')),
                ('station', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='evalink.station')),
            ],
        ),
        migrations.CreateModel(
            name='EvaVehicle',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('eva', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='evalink.eva')),
                ('vehicle', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='evalink.vehicle')),
            ],
        ),
        migrations.CreateModel(
            name='EvaStation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('eva', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='evalink.eva')),
                ('eva_crewmember', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to='evalink.evacrewmember')),
                ('eva_vehicle', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to='evalink.evavehicle')),
                ('station', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='evalink.station')),
            ],
        ),
        migrations.CreateModel(
            name='CrewmemberVitals',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('vitals', models.JSONField()),
                ('updated_at', models.DateTimeField(db_index=True)),
                ('crewmember', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='evalink.crewmember')),
            ],
        ),
    ]
