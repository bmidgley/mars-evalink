from datetime import date, datetime, timedelta

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from .models import Campus, Geofence, Hardware, PositionLog, Station, StationProfile


class ClearRedundantLogsCommandTestCase(TestCase):
    def setUp(self):
        self.campus = Campus.objects.create(
            name='Test Campus',
            latitude=40.0,
            longitude=-105.0,
            time_zone='America/Denver',
        )
        self.geofence = Geofence.objects.create(
            latitude1=39.9,
            longitude1=-105.1,
            latitude2=40.1,
            longitude2=-104.9,
        )
        self.campus.inner_geofence = self.geofence
        self.campus.save()

        self.hardware = Hardware.objects.create(
            name='Test Hardware',
            hardware_type=1,
            station_type='rover',
        )
        self.station_profile = StationProfile.objects.create(
            name='Test Profile',
            configuration={},
            compatible_firmwares=['1.0.0'],
        )
        self.station = Station.objects.create(
            name='Rover 1',
            short_name='R1',
            hardware=self.hardware,
            hardware_node='node1',
            hardware_number=90001,
            station_type='active',
            station_profile=self.station_profile,
        )

        self.day = date(2024, 6, 15)
        self.inside = (40.0, -105.0)
        self.outside = (40.5, -105.0)

    def _make_log(self, lat, lon, when):
        log = PositionLog.objects.create(
            station=self.station,
            campus=self.campus,
            latitude=lat,
            longitude=lon,
            timestamp=when,
            updated_on=self.day,
        )
        # auto_now would overwrite updated_at on create; set ordering explicitly
        PositionLog.objects.filter(pk=log.pk).update(updated_at=when, updated_on=self.day)
        log.refresh_from_db()
        return log

    def _seed_day(self):
        """
        One day for a station:
          outside (first of day),
          five consecutive inside (first/last of run kept; intermediates redundant),
          outside,
          outside (last of day).
        """
        base = timezone.make_aware(datetime(2024, 6, 15, 8, 0, 0))
        logs = {
            'first_of_day': self._make_log(*self.outside, base),
            'inside_first': self._make_log(*self.inside, base + timedelta(minutes=1)),
            'inside_mid_1': self._make_log(*self.inside, base + timedelta(minutes=2)),
            'inside_mid_2': self._make_log(*self.inside, base + timedelta(minutes=3)),
            'inside_mid_3': self._make_log(*self.inside, base + timedelta(minutes=4)),
            'inside_last': self._make_log(*self.inside, base + timedelta(minutes=5)),
            'outside_midday': self._make_log(*self.outside, base + timedelta(minutes=6)),
            'last_of_day': self._make_log(*self.outside, base + timedelta(minutes=7)),
        }
        return logs

    def test_destructive_removes_only_redundant_inside_intermediates(self):
        logs = self._seed_day()
        must_keep = {
            logs['first_of_day'].pk,
            logs['inside_first'].pk,
            logs['inside_last'].pk,
            logs['outside_midday'].pk,
            logs['last_of_day'].pk,
        }
        must_delete = {
            logs['inside_mid_1'].pk,
            logs['inside_mid_2'].pk,
            logs['inside_mid_3'].pk,
        }

        call_command(
            'clear_redundant_logs',
            '--destructive',
            campus=self.campus.name,
        )

        remaining = set(PositionLog.objects.values_list('pk', flat=True))
        self.assertTrue(must_keep.issubset(remaining))
        self.assertTrue(must_delete.isdisjoint(remaining))
        self.assertEqual(remaining, must_keep)

        ordered = list(PositionLog.objects.order_by('updated_at'))
        self.assertEqual(ordered[0].pk, logs['first_of_day'].pk)
        self.assertEqual(ordered[-1].pk, logs['last_of_day'].pk)

        for log in ordered:
            if (log.latitude, log.longitude) == self.outside:
                self.assertIn(log.pk, must_keep)

    def test_report_only_does_not_delete(self):
        logs = self._seed_day()
        before = set(PositionLog.objects.values_list('pk', flat=True))

        call_command('clear_redundant_logs', campus=self.campus.name)

        after = set(PositionLog.objects.values_list('pk', flat=True))
        self.assertEqual(before, after)
        self.assertEqual(len(after), len(logs))
