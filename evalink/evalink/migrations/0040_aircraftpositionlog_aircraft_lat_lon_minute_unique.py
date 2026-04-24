from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('evalink', '0039_aircraftpositionlog'),
    ]

    operations = [
        migrations.AddField(
            model_name='aircraftpositionlog',
            name='timestamp_minute',
            field=models.DateTimeField(db_index=True, null=True),
        ),
        migrations.RunSQL(
            sql="""
                UPDATE evalink_aircraftpositionlog
                SET timestamp_minute = date_trunc('minute', "timestamp")
                WHERE "timestamp" IS NOT NULL;
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunSQL(
            sql="""
                DELETE FROM evalink_aircraftpositionlog
                WHERE id IN (
                    SELECT id
                    FROM (
                        SELECT
                            id,
                            ROW_NUMBER() OVER (
                                PARTITION BY aircraft_id, latitude, longitude, timestamp_minute
                                ORDER BY updated_at DESC, id DESC
                            ) AS row_num
                        FROM evalink_aircraftpositionlog
                        WHERE timestamp_minute IS NOT NULL
                    ) ranked
                    WHERE ranked.row_num > 1
                );
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.AddConstraint(
            model_name='aircraftpositionlog',
            constraint=models.UniqueConstraint(
                fields=('aircraft', 'latitude', 'longitude', 'timestamp_minute'),
                name='unique_aircraftpositionlog_aircraft_lat_lon_minute',
            ),
        ),
    ]
