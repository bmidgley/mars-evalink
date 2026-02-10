"""
Keep a single APRS-IS connection open and cache last-seen positions in APRSPosition.
Run this in the background (e.g. systemd or screen) so aprs.json can serve from cache.

  python manage.py run_aprs_feed

Uses APRS_CALLSIGN, APRS_PASSCODE, APRS_IS_HOST, APRS_IS_PORT, and CAMPUS (for area filter on 14580).
"""
import os
import time

import aprslib
from django.core.management.base import BaseCommand
from django.utils import timezone

from evalink.models import Campus, APRSPosition


def _clean_text(s):
    """Remove NUL bytes; PostgreSQL text fields cannot contain 0x00."""
    if s is None:
        return None
    if isinstance(s, bytes):
        s = s.replace(b'\x00', b'').decode('utf-8', errors='replace')
    elif not isinstance(s, str):
        s = str(s)
    return s.replace('\x00', '')


class Command(BaseCommand):
    help = 'Keep APRS-IS connection open and cache last-seen positions for aprs.json'

    def handle(self, *args, **options):
        from dotenv import load_dotenv
        load_dotenv()

        callsign = os.getenv('APRS_CALLSIGN', 'N0CALL')
        passwd = os.getenv('APRS_PASSCODE', '-1')
        host = os.getenv('APRS_IS_HOST', 'rotate.aprs.net')
        port_cfg = os.getenv('APRS_IS_PORT', '').strip()
        port = int(port_cfg) if port_cfg else (14580 if passwd != '-1' else 10152)

        if port != 14580:
            self.stderr.write(self.style.ERROR(
                'This command must run on port 14580 (filter port). '
                'Current: port=%s. Set APRS_IS_PORT=14580 and a valid APRS_PASSCODE in .env, then restart.' % port
            ))
            return

        area_filter = ''
        if port == 14580 and passwd != '-1':
            try:
                campus = Campus.objects.get(name=os.getenv('CAMPUS'))
                if campus.outer_geofence:
                    g = campus.outer_geofence
                    lat_n = max(g.latitude1, g.latitude2)
                    lat_s = min(g.latitude1, g.latitude2)
                    lon_w = min(g.longitude1, g.longitude2)
                    lon_e = max(g.longitude1, g.longitude2)
                    area_filter = 'a/%s/%s/%s/%s t/po' % (lat_n, lon_w, lat_s, lon_e)
            except Exception:
                pass

        debug_callsign = (os.getenv('APRS_DEBUG_CALLSIGN') or '').strip().upper()
        backoff = 5
        ais = None
        while True:
            try:
                ais = aprslib.IS(callsign, passwd=passwd, host=host, port=port)
                if area_filter:
                    ais.set_filter(area_filter)
                ais.connect()
                backoff = 5
                for line in ais._socket_readlines(blocking=True):
                    try:
                        s = line.decode('utf-8', errors='replace').strip() if isinstance(line, bytes) else str(line).strip()
                        if not s or s.startswith('#'):
                            continue
                        is_debug = debug_callsign and debug_callsign in s.upper()
                        try:
                            pkt = aprslib.parse(s)
                        except Exception as e:
                            if is_debug:
                                self.stdout.write(self.style.WARNING('Parse failed for %s: %s' % (debug_callsign, e)))
                                self.stdout.write('  Raw: %s' % (s.replace('\x00', '')[:200]))
                            continue
                        if not isinstance(pkt, dict):
                            if is_debug:
                                self.stdout.write(self.style.WARNING('Parse returned non-dict for %s' % debug_callsign))
                            continue
                        lat = pkt.get('latitude')
                        lon = pkt.get('longitude')
                        if lat is None or lon is None:
                            if is_debug:
                                self.stdout.write(self.style.WARNING('No lat/lon for %s (format may be unsupported)' % debug_callsign))
                                self.stdout.write('  Raw: %s' % (s.replace('\x00', '')[:200]))
                            continue
                    except Exception:
                        continue
                    try:
                        lat = float(lat)
                        lon = float(lon)
                    except (TypeError, ValueError):
                        continue
                    name = _clean_text((pkt.get('from') or '').strip())
                    if not name:
                        continue
                    alt = pkt.get('altitude')
                    if alt is not None:
                        try:
                            alt = float(alt)
                        except (TypeError, ValueError):
                            alt = None
                    sym = pkt.get('symbol')
                    st = pkt.get('symbol_table', '')
                    symbol = _clean_text((st + sym) if (sym and st) else (sym or None))
                    comment = _clean_text(pkt.get('comment'))
                    path = pkt.get('path', [])
                    if isinstance(path, (list, tuple)):
                        path_str = _clean_text(','.join(_clean_text(p) or '' for p in path)) or None
                    else:
                        path_str = _clean_text(path) if path else None
                    course = pkt.get('course')
                    speed = pkt.get('speed')
                    now = timezone.now()
                    APRSPosition.objects.update_or_create(
                        callsign=name,
                        defaults={
                            'latitude': lat,
                            'longitude': lon,
                            'altitude': alt,
                            'symbol': symbol,
                            'comment': comment,
                            'path': path_str,
                            'course': course,
                            'speed': speed,
                            'updated_at': now,
                        },
                    )
            except (aprslib.ConnectionError, aprslib.LoginError, aprslib.ConnectionDrop, OSError) as e:
                if ais is not None:
                    try:
                        ais.close()
                    except Exception:
                        pass
                    ais = None
                self.stdout.write('APRS-IS disconnect: %s; reconnecting in %s s' % (e, backoff))
                time.sleep(backoff)
                backoff = min(60, backoff * 2)
            except KeyboardInterrupt:
                if ais is not None:
                    try:
                        ais.close()
                    except Exception:
                        pass
                break
