"""
Print geofence bounds for a campus and check if coordinates are inside.

Usage:
  python manage.py show_geofence MDRS
  python manage.py show_geofence MDRS --lat 41.00566666666667 --lon -111.93066666666667

Coordinates are (latitude, longitude) in decimal degrees.
"""
import os
from django.core.management.base import BaseCommand
from evalink.models import Campus


def box_bounds(fence):
    """Return (min_lat, max_lat, min_lon, max_lon) for the geofence box."""
    if not fence:
        return None
    min_lat = min(fence.latitude1, fence.latitude2)
    max_lat = max(fence.latitude1, fence.latitude2)
    min_lon = min(fence.longitude1, fence.longitude2)
    max_lon = max(fence.longitude1, fence.longitude2)
    return (min_lat, max_lat, min_lon, max_lon)


def inside_box(lat, lon, bounds):
    if bounds is None:
        return None
    min_lat, max_lat, min_lon, max_lon = bounds
    return min_lat <= lat <= max_lat and min_lon <= lon <= max_lon


class Command(BaseCommand):
    help = "Print campus geofence bounds and optionally check if (lat, lon) is inside."

    def add_arguments(self, parser):
        parser.add_argument("campus_name", nargs="?", default=None, help="Campus name (default: CAMPUS env)")
        parser.add_argument("--lat", type=float, default=None, help="Latitude to check")
        parser.add_argument("--lon", type=float, default=None, help="Longitude to check")

    def handle(self, *args, **options):
        name = options["campus_name"] or os.getenv("CAMPUS")
        if not name:
            self.stderr.write("Provide campus name or set CAMPUS in environment.")
            return
        try:
            campus = Campus.objects.get(name=name)
        except Campus.DoesNotExist:
            self.stderr.write("Campus not found: %s" % name)
            return

        lat = options.get("lat")
        lon = options.get("lon")

        self.stdout.write("Campus: %s" % campus.name)
        self.stdout.write("")

        for label, fence in (("inner_geofence", campus.inner_geofence), ("outer_geofence", campus.outer_geofence)):
            self.stdout.write("%s:" % label)
            if not fence:
                self.stdout.write("  (not set)")
                continue
            bounds = box_bounds(fence)
            min_lat, max_lat, min_lon, max_lon = bounds
            self.stdout.write("  latitude1=%s longitude1=%s latitude2=%s longitude2=%s" % (
                fence.latitude1, fence.longitude1, fence.latitude2, fence.longitude2))
            self.stdout.write("  box: lat [%s, %s]  lon [%s, %s]" % (min_lat, max_lat, min_lon, max_lon))
            if lat is not None and lon is not None:
                inside = inside_box(lat, lon, bounds)
                self.stdout.write("  point (%s, %s) inside: %s" % (lat, lon, inside))
            self.stdout.write("")

        if lat is not None and lon is not None and not (campus.inner_geofence or campus.outer_geofence):
            self.stdout.write("Point (%s, %s) not checked (no geofences set)." % (lat, lon))
