# Generated by Django 4.2.9 on 2024-02-11 19:34

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('evalink', '0009_stationmeasure'),
    ]

    operations = [
        migrations.AlterField(
            model_name='station',
            name='hardware_number',
            field=models.BigIntegerField(db_index=True, unique=True),
        ),
    ]
