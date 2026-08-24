"""
Find and optionally clear redundant PositionLog rows inside the campus inner fence.

Same rules as the oldest-consecutive-inside UI: for each station on a day, keep only
the first and last point in each run of more than two consecutive positions inside
the fence. Rows referenced by TextLog are never deleted.

Usage:
  python manage.py clear_redundant_logs
  python manage.py clear_redundant_logs --destructive
  python manage.py clear_redundant_logs --destructive --continue
"""
import os
from collections import defaultdict

from django.core.management.base import BaseCommand

from evalink.models import Campus, PositionLog, Station, TextLog


class Command(BaseCommand):
    help = (
        'Find the oldest day with redundant inside-fence position logs and '
        'optionally delete intermediate points (keeps first and last per run)'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--destructive',
            action='store_true',
            help='Actually delete redundant logs (default is report only)',
        )
        parser.add_argument(
            '--continue',
            dest='keep_going',
            action='store_true',
            help='After processing one date, find and process the next affected date',
        )
        parser.add_argument(
            '--campus',
            type=str,
            default=os.getenv('CAMPUS'),
            help='Campus name (default: CAMPUS env)',
        )

    def handle(self, *args, **options):
        destructive = options['destructive']
        keep_going = options['keep_going']
        campus_name = options['campus']

        if not campus_name:
            self.stderr.write(self.style.ERROR('Campus name required (set CAMPUS or pass --campus)'))
            return

        try:
            campus = Campus.objects.get(name=campus_name)
        except Campus.DoesNotExist:
            self.stderr.write(self.style.ERROR(f'Campus "{campus_name}" not found'))
            return

        inner_fence = campus.inner_geofence
        if not inner_fence:
            self.stderr.write(self.style.ERROR(f'No inner geofence configured for campus "{campus.name}"'))
            return

        if not destructive:
            self.stdout.write(self.style.WARNING('Report only (pass --destructive to delete)'))

        excluded_station_ids = list(
            Station.objects.filter(station_type__in=['infrastructure', 'planner']).values_list('pk', flat=True)
        )

        dates_processed = 0
        total_deleted = 0
        total_would_delete = 0
        total_skipped_text = 0
        after_date = None

        while True:
            target_date = self.find_oldest_affected_date(
                excluded_station_ids, inner_fence, after_date=after_date
            )
            if target_date is None:
                if dates_processed == 0:
                    self.stdout.write(self.style.SUCCESS(
                        'No day found with more than two consecutive position logs inside the inner fence'
                    ))
                else:
                    self.stdout.write(self.style.SUCCESS(
                        f'Done. Processed {dates_processed} date(s); '
                        f'deleted={total_deleted} would_delete={total_would_delete} '
                        f'skipped_textlog={total_skipped_text}'
                    ))
                return

            devices, deletable_ids, skipped_text = self.analyze_date(
                target_date, excluded_station_ids, inner_fence
            )

            self.stdout.write('')
            self.stdout.write(self.style.NOTICE(f'Date: {target_date.isoformat()}'))
            self.stdout.write(f'  Devices with redundant runs: {len(devices)}')
            for device in devices:
                counts = ', '.join(str(c) for c in device['all_consecutive_counts'])
                self.stdout.write(
                    f"  - {device['device_name']} (id={device['device_id']}): "
                    f"max={device['consecutive_positions']} runs=[{counts}]"
                )
            self.stdout.write(
                f'  Intermediate logs: {len(deletable_ids)} deletable, '
                f'{skipped_text} skipped (TextLog reference)'
            )

            deleted = 0
            if destructive and deletable_ids:
                deleted = self.delete_logs(deletable_ids)
                self.stdout.write(self.style.WARNING(f'  Deleted {deleted} PositionLog row(s)'))
            elif not destructive:
                self.stdout.write(f'  Would delete {len(deletable_ids)} PositionLog row(s)')

            dates_processed += 1
            total_deleted += deleted
            total_would_delete += len(deletable_ids)
            total_skipped_text += skipped_text

            if not keep_going:
                if not destructive:
                    self.stdout.write(self.style.SUCCESS(
                        'Pass --destructive to delete, and/or --continue for later dates'
                    ))
                return

            # Always advance so --continue cannot re-process the same date forever
            # (e.g. when every intermediate row is TextLog-protected, or report-only mode).
            if destructive and deleted == 0:
                self.stdout.write(self.style.WARNING(
                    f'  Nothing deleted for {target_date.isoformat()}; continuing to later dates'
                ))
            after_date = target_date

    def excluded_qs(self, excluded_station_ids):
        return PositionLog.objects.exclude(station_id__in=excluded_station_ids)

    def is_inside_fence(self, lat, lon, inner_fence):
        return (
            lat >= inner_fence.latitude1 and lat <= inner_fence.latitude2 and
            lon >= inner_fence.longitude1 and lon <= inner_fence.longitude2
        )

    def consecutive_inside_runs(self, logs, inner_fence):
        """Return list of runs (each a list of PositionLog) with length > 2 inside the fence."""
        runs = []
        current_run = []
        for log in logs:
            if self.is_inside_fence(log.latitude, log.longitude, inner_fence):
                current_run.append(log)
            else:
                if len(current_run) > 2:
                    runs.append(current_run)
                current_run = []
        if len(current_run) > 2:
            runs.append(current_run)
        return runs

    def find_oldest_affected_date(self, excluded_station_ids, inner_fence, after_date=None):
        qs = self.excluded_qs(excluded_station_ids).filter(updated_on__isnull=False)
        if after_date is not None:
            qs = qs.filter(updated_on__gt=after_date)
        dates = qs.values_list('updated_on', flat=True).distinct().order_by('updated_on')
        for day_date in dates:
            if self.date_has_redundant_runs(day_date, excluded_station_ids, inner_fence):
                return day_date
        return None

    def date_has_redundant_runs(self, day_date, excluded_station_ids, inner_fence):
        logs_by_station = self.logs_by_station_for_date(day_date, excluded_station_ids)
        for logs in logs_by_station.values():
            if self.consecutive_inside_runs(logs, inner_fence):
                return True
        return False

    def logs_by_station_for_date(self, day_date, excluded_station_ids):
        position_logs = (
            self.excluded_qs(excluded_station_ids)
            .filter(updated_on=day_date)
            .order_by('station_id', 'updated_at')
        )
        logs_by_station = defaultdict(list)
        for log in position_logs:
            logs_by_station[log.station_id].append(log)
        for logs in logs_by_station.values():
            logs.sort(key=lambda x: x.updated_at)
        return logs_by_station

    def analyze_date(self, day_date, excluded_station_ids, inner_fence):
        logs_by_station = self.logs_by_station_for_date(day_date, excluded_station_ids)
        devices = []
        deletable_ids = []
        skipped_text = 0

        referenced_ids = set(
            TextLog.objects.filter(
                position_log__updated_on=day_date,
                position_log_id__isnull=False,
            ).values_list('position_log_id', flat=True)
        )

        for station_id, logs in logs_by_station.items():
            runs = self.consecutive_inside_runs(logs, inner_fence)
            if not runs:
                continue

            station = Station.objects.get(pk=station_id)
            run_lengths = [len(run) for run in runs]
            devices.append({
                'device_name': station.name,
                'device_id': station.id,
                'consecutive_positions': max(run_lengths),
                'all_consecutive_counts': run_lengths,
            })

            for run in runs:
                for log in run[1:-1]:
                    if log.id in referenced_ids:
                        skipped_text += 1
                        continue
                    deletable_ids.append(log.id)

        devices.sort(key=lambda x: x['consecutive_positions'], reverse=True)
        return devices, deletable_ids, skipped_text

    def delete_logs(self, log_ids):
        deleted = 0
        # Delete one-by-one so CASCADE to TelemetryLog/NeighborLog matches the UI path
        # and RESTRICT on TextLog cannot wipe a batch mid-flight.
        for log_id in log_ids:
            try:
                log = PositionLog.objects.get(pk=log_id)
            except PositionLog.DoesNotExist:
                continue
            if TextLog.objects.filter(position_log=log).exists():
                continue
            log.delete()
            deleted += 1
        return deleted
