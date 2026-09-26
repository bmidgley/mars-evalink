from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('evalink', '0041_positionlog_station_updated_at_index'),
    ]

    operations = [
        migrations.AddField(
            model_name='station',
            name='asset',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
    ]
