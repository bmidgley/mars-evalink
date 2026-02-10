"""
Generate APRS passcode for a callsign (for use with APRS-IS port 14580).

Usage:
  python manage.py aprs_passcode YOURCALL
  python manage.py aprs_passcode K6MARS-7

Then set in .env:
  APRS_CALLSIGN=YOURCALL
  APRS_PASSCODE=<number printed below>
"""
from django.core.management.base import BaseCommand

try:
    import aprslib
except ImportError:
    aprslib = None


class Command(BaseCommand):
    help = "Print APRS passcode for a callsign (for APRS_IS_PORT=14580)."

    def add_arguments(self, parser):
        parser.add_argument("callsign", help="Callsign (e.g. K6MARS or K6MARS-7)")

    def handle(self, *args, **options):
        if not aprslib:
            self.stderr.write("aprslib not installed.")
            return
        call = options["callsign"].strip().upper()
        if not call:
            self.stderr.write("Callsign required.")
            return
        try:
            code = aprslib.passcode(call)
        except Exception as e:
            self.stderr.write("Failed: %s" % e)
            return
        self.stdout.write("Callsign: %s" % call)
        self.stdout.write("Passcode: %s" % code)
        self.stdout.write("")
        self.stdout.write("Add to .env:")
        self.stdout.write("  APRS_CALLSIGN=%s" % call)
        self.stdout.write("  APRS_PASSCODE=%s" % code)
