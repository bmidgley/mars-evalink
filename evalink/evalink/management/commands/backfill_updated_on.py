from django.core.management.base import BaseCommand
from django.db import transaction
from evalink.models import PositionLog, TextLog, TelemetryLog, Campus
import pytz

BATCH_SIZE = 1000


class Command(BaseCommand):
    help = 'Backfill updated_on field for PositionLog, TextLog, and TelemetryLog using campus timezone'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be updated without actually updating',
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=1000,
            help='Number of records to update per batch (default: 1000)',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        batch_size = options['batch_size']

        # Get the first campus
        try:
            campus = Campus.objects.first()
            if not campus:
                self.stdout.write(
                    self.style.ERROR('No campus found in database')
                )
                return
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error getting campus: {e}')
            )
            return

        campus_tz = pytz.timezone(campus.time_zone)
        self.stdout.write(
            self.style.SUCCESS(f'Using campus "{campus.name}" with timezone "{campus.time_zone}"')
        )

        if dry_run:
            self.stdout.write(
                self.style.WARNING('DRY RUN MODE - No changes will be made')
            )

        # Process PositionLog
        self.stdout.write('\nProcessing PositionLog...')
        self.backfill_model(
            PositionLog,
            'updated_on',
            campus_tz,
            dry_run,
            batch_size
        )

        # Process TextLog
        self.stdout.write('\nProcessing TextLog...')
        self.backfill_model(
            TextLog,
            'updated_on',
            campus_tz,
            dry_run,
            batch_size
        )

        # Process TelemetryLog
        self.stdout.write('\nProcessing TelemetryLog...')
        self.backfill_model(
            TelemetryLog,
            'updated_on',
            campus_tz,
            dry_run,
            batch_size
        )

        self.stdout.write(
            self.style.SUCCESS('\nBackfill completed!')
        )

    def backfill_model(self, model_class, field_name, timezone, dry_run, batch_size):
        """Backfill updated_on field for a given model"""
        model_name = model_class.__name__
        
        # Get all records where updated_on is null
        qs = model_class.objects.filter(**{f'{field_name}__isnull': True}).order_by('id')
        total = qs.count()
        
        if total == 0:
            self.stdout.write(f'  No {model_name} records need updating')
            return

        self.stdout.write(f'  Found {total} {model_name} records to update')
        
        if dry_run:
            # In dry-run mode, just show a sample
            sample = list(qs[:10])
            self.stdout.write(f'  Sample records that would be updated:')
            for item in sample:
                if hasattr(item, 'updated_at') and item.updated_at:
                    updated_at_in_tz = item.updated_at.astimezone(timezone)
                    new_date = updated_at_in_tz.date()
                    self.stdout.write(
                        f'    ID {item.id}: updated_at={item.updated_at} -> updated_on={new_date}'
                    )
            if total > 10:
                self.stdout.write(f'    ... and {total - 10} more')
            return

        updated_count = 0
        offset = 0

        while offset < total:
            with transaction.atomic():
                batch = list(qs[offset:offset + batch_size])
                for item in batch:
                    if hasattr(item, 'updated_at') and item.updated_at:
                        # Convert updated_at to campus timezone
                        updated_at_in_tz = item.updated_at.astimezone(timezone)
                        # Set updated_on using the date in the correct timezone
                        setattr(item, field_name, updated_at_in_tz.date())

                model_class.objects.bulk_update(batch, [field_name])
                updated_count += len(batch)
                
            offset += batch_size
            self.stdout.write(f'  Updated {min(updated_count, total)} of {total} {model_name} records')

        self.stdout.write(
            self.style.SUCCESS(f'  Completed updating {updated_count} {model_name} records')
        )

