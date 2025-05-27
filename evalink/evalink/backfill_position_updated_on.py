import os
import pytz
from django.db import transaction
from evalink.models import PositionLog, Campus
from datetime import datetime

BATCH_SIZE = 1000

def update_updated_on_field():
    campus = Campus.objects.get(name=os.getenv('CAMPUS'))
    campus_tz = pytz.timezone(campus.time_zone)
    
    qs = PositionLog.objects.filter(updated_on__isnull=True).order_by('id')
    total = qs.count()
    print(f"Total to update: {total}")
    offset = 0

    while offset < total:
        with transaction.atomic():
            batch = list(qs[offset:offset + BATCH_SIZE])
            for item in batch:
                if item.updated_at:
                    # Convert updated_at to campus timezone
                    updated_at_in_tz = item.updated_at.astimezone(campus_tz)
                    # Set updated_on using the date in the correct timezone
                    item.updated_on = updated_at_in_tz.date()

            PositionLog.objects.bulk_update(batch, ['updated_on'])
        offset += BATCH_SIZE
        print(f"Updated {min(offset, total)} of {total}")

# Call the function
update_updated_on_field()
