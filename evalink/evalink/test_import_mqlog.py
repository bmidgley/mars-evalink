import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase

from evalink.management.commands.import_mqlog import parse_mqlog_tst as parse_tst
from evalink.models import (
    Campus,
    Geofence,
    Hardware,
    PositionLog,
    Station,
    StationProfile,
    TelemetryLog,
    TextLog,
)


class ParseMqlogTstTestCase(TestCase):
    def test_parses_z_plus_offset(self):
        dt = parse_tst('2023-09-23T08:54:37.468522Z-0600')
        self.assertEqual(dt, datetime(2023, 9, 23, 14, 54, 37, 468522, tzinfo=timezone.utc))

    def test_parses_plain_offset(self):
        dt = parse_tst('2023-09-23T08:54:37-06:00')
        self.assertEqual(dt, datetime(2023, 9, 23, 14, 54, 37, tzinfo=timezone.utc))


class ImportMqlogCommandTestCase(TestCase):
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
            hardware_type=4,
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
            hardware_node='!node1',
            hardware_number=2513867698,
            station_type='rover',
            station_profile=self.station_profile,
            features={'type': 'Feature', 'properties': {'name': 'Rover 1'}, 'geometry': {'type': 'Point'}},
        )
        self.original_features = dict(self.station.features)

    def _envelope(self, msg_type, payload, msg_id, from_node=2513867698, tst='2023-09-23T10:00:00.000000Z-0600', ts=1695481200):
        return {
            'tst': tst,
            'topic': 'msh/2/json/LongFast/!a3fb59b8',
            'qos': 0,
            'retain': 0,
            'payloadlen': 100,
            'payload': {
                'channel': 0,
                'from': from_node,
                'id': msg_id,
                'payload': payload,
                'sender': '!a3fb59b8',
                'timestamp': ts,
                'to': 4294967295,
                'type': msg_type,
            },
        }

    def test_imports_positions_telemetry_text_with_historical_times(self):
        # Inside-fence positions would normally be skipped after the first of the day;
        # import should keep all of them.
        lines = [
            self._envelope(
                'position',
                {'altitude': 1376, 'latitude_i': 400000000, 'longitude_i': -1050000000, 'time': 1695481200},
                msg_id=1,
                tst='2023-09-23T10:00:00.000000Z-0600',
            ),
            self._envelope(
                'position',
                {'altitude': 1377, 'latitude_i': 400000100, 'longitude_i': -1050000100, 'time': 1695481260},
                msg_id=2,
                tst='2023-09-23T10:01:00.000000Z-0600',
                ts=1695481260,
            ),
            self._envelope(
                'telemetry',
                {'temperature': 21.5, 'voltage': 4.1, 'battery_level': 90},
                msg_id=1001,
                tst='2023-09-23T10:01:30.000000Z-0600',
                ts=1695481290,
            ),
            self._envelope(
                'text',
                {'text': 'hello from mqlog'},
                msg_id=2001,
                tst='2023-09-23T10:02:00.000000Z-0600',
                ts=1695481320,
            ),
            # neighborinfo / empty type are ignored by handler
            self._envelope('neighborinfo', {'neighbors': []}, msg_id=3),
            self._envelope('', {}, msg_id=4),
        ]

        with tempfile.TemporaryDirectory() as tmp:
            day_path = Path(tmp) / '2023-09-23'
            with open(day_path, 'w') as fh:
                for env in lines:
                    fh.write(json.dumps(env) + '\n')
            # Snapshot file must be ignored
            with open(Path(tmp) / '2023-09-23.json', 'w') as fh:
                json.dump({'Meshtastic x': {'battery': 1}}, fh)

            with patch.dict(os.environ, {'CAMPUS': 'Test Campus'}):
                call_command('import_mqlog', tmp)

        self.assertEqual(PositionLog.objects.count(), 2)
        positions = list(PositionLog.objects.order_by('updated_at'))
        self.assertEqual(positions[0].updated_on.isoformat(), '2023-09-23')
        self.assertEqual(
            positions[0].updated_at,
            datetime(2023, 9, 23, 16, 0, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(
            positions[1].updated_at,
            datetime(2023, 9, 23, 16, 1, 0, tzinfo=timezone.utc),
        )

        self.assertEqual(TelemetryLog.objects.count(), 1)
        tel = TelemetryLog.objects.get()
        self.assertEqual(tel.message_id, 1001)
        self.assertEqual(tel.temperature, 21.5)
        self.assertEqual(tel.position_log_id, positions[1].id)
        self.assertEqual(tel.updated_on.isoformat(), '2023-09-23')

        self.assertEqual(TextLog.objects.count(), 1)
        text = TextLog.objects.get()
        self.assertEqual(text.text, 'hello from mqlog')
        self.assertEqual(text.serial_number, 2001)
        self.assertEqual(text.updated_on.isoformat(), '2023-09-23')

        # Live station state must not be overwritten by historical import
        self.station.refresh_from_db()
        self.assertEqual(self.station.features, self.original_features)
        self.assertIsNone(self.station.last_position)

        # neighborinfo + empty type are skipped (not persisted by handler)

    def test_dry_run_writes_nothing(self):
        env = self._envelope(
            'position',
            {'altitude': 1376, 'latitude_i': 400000000, 'longitude_i': -1050000000, 'time': 1695481200},
            msg_id=9,
        )
        with tempfile.TemporaryDirectory() as tmp:
            with open(Path(tmp) / '2023-09-23', 'w') as fh:
                fh.write(json.dumps(env) + '\n')
            with patch.dict(os.environ, {'CAMPUS': 'Test Campus'}):
                call_command('import_mqlog', tmp, dry_run=True)

        self.assertEqual(PositionLog.objects.count(), 0)

    def test_creates_station_from_nodeinfo_without_clobbering_later(self):
        unknown = 2751158712
        env = self._envelope(
            'nodeinfo',
            {
                'hardware': 4,
                'id': '!a3fb59b8',
                'longname': 'Meshtastic 59b8',
                'shortname': '59b8',
            },
            msg_id=50,
            from_node=unknown,
        )
        with tempfile.TemporaryDirectory() as tmp:
            with open(Path(tmp) / '2023-09-23', 'w') as fh:
                fh.write(json.dumps(env) + '\n')
            with patch.dict(os.environ, {'CAMPUS': 'Test Campus'}):
                call_command('import_mqlog', tmp)

        created = Station.objects.get(hardware_number=unknown)
        self.assertEqual(created.name, 'Meshtastic 59b8')
        self.assertEqual(created.short_name, '59b8')
