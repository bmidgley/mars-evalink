"""
Import legacy mosquitto/mqtt NDJSON bus logs (mqlog/) into the database.

Each day has two files:
  YYYY-MM-DD       NDJSON bus capture (one MQTT message per line) -- imported
  YYYY-MM-DD.json  station status snapshot dict -- ignored (different format)

Usage:
  python manage.py import_mqlog /path/to/mqlog
  python manage.py import_mqlog /path/to/mqlog --dry-run
  python manage.py import_mqlog /path/to/mqlog --from 2023-09-23 --to 2023-10-01
"""
import json
import os
import re
from datetime import date, datetime, timezone
from pathlib import Path

from django.core.management.base import BaseCommand

from evalink import handler

# mqlog tst looks like "2023-09-23T08:54:37.468522Z-0600" (Z plus numeric offset).
_TST_RE = re.compile(
    r'^(?P<dt>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?)'
    r'(?:Z)?(?P<off>[+-]\d{2}:?\d{2})?$'
)
_DAY_FILE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')


def parse_mqlog_tst(value):
    """Parse mqlog observation timestamp into an aware UTC datetime."""
    if not value or not isinstance(value, str):
        return None
    match = _TST_RE.match(value.strip())
    if not match:
        return None
    dt_part = match.group('dt')
    off = match.group('off')
    if off:
        if ':' not in off:
            off = f'{off[:3]}:{off[3:]}'
        parsed = datetime.fromisoformat(dt_part + off)
    else:
        parsed = datetime.fromisoformat(dt_part).replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


class Command(BaseCommand):
    help = (
        'Import mqlog NDJSON bus captures into PositionLog/TelemetryLog/TextLog '
        '(skips *.json station snapshots)'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            'folder',
            type=str,
            help='Path to mqlog folder (files named YYYY-MM-DD without .json)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Parse and count messages without writing to the database',
        )
        parser.add_argument(
            '--from',
            dest='from_date',
            type=str,
            default=None,
            help='Only import files on/after this date (YYYY-MM-DD)',
        )
        parser.add_argument(
            '--to',
            dest='to_date',
            type=str,
            default=None,
            help='Only import files on/before this date (YYYY-MM-DD)',
        )
        parser.add_argument(
            '--campus',
            type=str,
            default=os.getenv('CAMPUS'),
            help='Campus name (sets CAMPUS env for handler; default: CAMPUS env)',
        )

    def handle(self, *args, **options):
        folder = Path(options['folder'])
        dry_run = options['dry_run']
        campus_name = options['campus']
        from_date = self._parse_date(options['from_date'], '--from')
        to_date = self._parse_date(options['to_date'], '--to')

        if not campus_name:
            self.stderr.write(self.style.ERROR('Campus name required (set CAMPUS or pass --campus)'))
            return
        if not folder.is_dir():
            self.stderr.write(self.style.ERROR(f'Not a directory: {folder}'))
            return

        os.environ['CAMPUS'] = campus_name

        day_files = self._list_day_files(folder, from_date, to_date)
        if not day_files:
            self.stdout.write(self.style.WARNING('No YYYY-MM-DD bus log files found to import'))
            return

        self.stdout.write(
            f'Importing {len(day_files)} day file(s) from {folder} '
            f'(campus={campus_name}, dry_run={dry_run})'
        )
        self.stdout.write('Ignoring *.json snapshot files (not bus NDJSON)')

        totals = {
            'lines': 0,
            'ok': 0,
            'skipped': 0,
            'errors': 0,
            'by_type': {},
        }

        for path in day_files:
            self._import_file(path, dry_run, totals)

        type_summary = ', '.join(
            f'{name}={count}' for name, count in sorted(totals['by_type'].items())
        ) or 'none'
        self.stdout.write(self.style.SUCCESS(
            f"Done. lines={totals['lines']} processed={totals['ok']} "
            f"skipped={totals['skipped']} errors={totals['errors']} types=[{type_summary}]"
        ))

    def _parse_date(self, value, flag):
        if not value:
            return None
        try:
            return date.fromisoformat(value)
        except ValueError:
            raise SystemExit(f'Invalid {flag} date (want YYYY-MM-DD): {value}')

    def _list_day_files(self, folder, from_date, to_date):
        files = []
        for path in sorted(folder.iterdir()):
            if not path.is_file():
                continue
            # Bus capture: extensionless YYYY-MM-DD. Snapshots end in .json.
            if path.suffix:
                continue
            if not _DAY_FILE_RE.match(path.name):
                continue
            day = date.fromisoformat(path.name)
            if from_date and day < from_date:
                continue
            if to_date and day > to_date:
                continue
            files.append(path)
        return files

    def _import_file(self, path, dry_run, totals):
        self.stdout.write(f'  {path.name}...')
        file_lines = 0
        file_ok = 0
        file_skipped = 0
        file_errors = 0

        with open(path, 'r', encoding='utf-8', errors='replace') as handle:
            for line_no, raw in enumerate(handle, start=1):
                line = raw.strip()
                if not line:
                    continue
                file_lines += 1
                totals['lines'] += 1
                try:
                    envelope = json.loads(line)
                except json.JSONDecodeError as exc:
                    file_errors += 1
                    totals['errors'] += 1
                    self.stderr.write(f'    {path.name}:{line_no} JSON error: {exc}')
                    continue

                message = envelope.get('payload')
                if not isinstance(message, dict):
                    file_skipped += 1
                    totals['skipped'] += 1
                    continue
                if not all(key in message for key in ('type', 'payload', 'timestamp', 'from')):
                    file_skipped += 1
                    totals['skipped'] += 1
                    continue
                if not message.get('type'):
                    file_skipped += 1
                    totals['skipped'] += 1
                    continue

                msg_type = message['type']
                # Handler only persists these; neighborinfo/etc. are no-ops.
                if msg_type not in ('nodeinfo', 'position', 'telemetry', 'text'):
                    file_skipped += 1
                    totals['skipped'] += 1
                    continue

                totals['by_type'][msg_type] = totals['by_type'].get(msg_type, 0) + 1

                if dry_run:
                    file_ok += 1
                    totals['ok'] += 1
                    continue

                observed_at = parse_mqlog_tst(envelope.get('tst'))
                if observed_at is None and message.get('timestamp'):
                    try:
                        observed_at = datetime.fromtimestamp(
                            int(message['timestamp']), tz=timezone.utc
                        )
                    except (TypeError, ValueError, OSError):
                        observed_at = None
                if observed_at is None:
                    file_skipped += 1
                    totals['skipped'] += 1
                    continue

                try:
                    handler.process_message(
                        message,
                        observed_at=observed_at,
                        save_all_positions=True,
                        update_station=False,
                    )
                except Exception as exc:
                    file_errors += 1
                    totals['errors'] += 1
                    self.stderr.write(f'    {path.name}:{line_no} handler error: {exc}')
                    continue

                file_ok += 1
                totals['ok'] += 1

        self.stdout.write(
            f'    lines={file_lines} processed={file_ok} '
            f'skipped={file_skipped} errors={file_errors}'
        )
