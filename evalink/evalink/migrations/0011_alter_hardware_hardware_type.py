# Generated by Django 4.2.9 on 2024-02-11 21:28

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('evalink', '0010_alter_station_hardware_number'),
    ]

    operations = [
        migrations.AlterField(
            model_name='hardware',
            name='hardware_type',
            field=models.IntegerField(unique=True),
        ),
    ]