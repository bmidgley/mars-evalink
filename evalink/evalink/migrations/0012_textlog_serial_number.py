# Generated by Django 4.2.9 on 2024-02-12 16:24

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('evalink', '0011_alter_hardware_hardware_type'),
    ]

    operations = [
        migrations.AddField(
            model_name='textlog',
            name='serial_number',
            field=models.BigIntegerField(db_index=True, default=1, unique=True),
            preserve_default=False,
        ),
    ]
