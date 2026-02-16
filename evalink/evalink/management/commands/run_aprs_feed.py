"""
Poll aprs.fi API and cache last-seen positions in APRSPosition for devices
inside the campus outer geofence. Run in the background (e.g. systemd or screen)
so aprs.json can serve from cache.

  python manage.py run_aprs_feed

Uses APRS_FI_API_KEY and CAMPUS from .env. Polls every 5 minutes.
Data from aprs.fi (https://aprs.fi).
"""
import math
import os
import time
import urllib.error
import urllib.parse
import urllib.request

from django.core.management.base import BaseCommand
from django.utils import timezone

from evalink.models import Campus, APRSPosition

POLL_INTERVAL_SECONDS = 300  # 5 minutes
USER_AGENT = "evalink-aprs-feed/1.0 (+https://github.com/mars-society/evalink)"


def _clean_text(s):
    """Remove NUL bytes; PostgreSQL text fields cannot contain 0x00."""
    if s is None:
        return None
    if isinstance(s, bytes):
        s = s.replace(b'\x00', b'').decode('utf-8', errors='replace')
    elif not isinstance(s, str):
        s = str(s)
    return s.replace('\x00', '')


def _bbox_center_and_radius_km(lat_n, lat_s, lon_w, lon_e):
    """Return (center_lat, center_lng, radius_km) for a bounding box."""
    center_lat = (lat_n + lat_s) / 2.0
    center_lon = (lon_w + lon_e) / 2.0
    # Approximate radius as half the diagonal; 1 degree ~ 111 km at mid latitudes
    dlat_km = abs(lat_n - lat_s) * 111.0
    dlon_km = abs(lon_e - lon_w) * 111.0 * max(0.3, math.cos(math.radians(center_lat)))
    radius_km = math.ceil(math.sqrt(dlat_km ** 2 + dlon_km ** 2) / 2.0)
    radius_km = max(10, min(500, radius_km))
    return center_lat, center_lon, radius_km


def _fetch_aprs_fi_area(api_key, lat, lng, radius_km):
    """Request aprs.fi API for stations in area. Returns list of entry dicts or None on error."""
    params = {
        'what': 'loc',
        'apikey': api_key,
        'format': 'json',
        'lat': lat,
        'lng': lng,
        'radius': radius_km,
    }
    url = 'https://api.aprs.fi/api/get?' + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read().decode('utf-8', errors='replace')
    except urllib.error.HTTPError as e:
        return None, 'HTTP %s' % e.code
    except urllib.error.URLError as e:
        return None, str(e.reason) if getattr(e, 'reason', None) else str(e)
    except Exception as e:
        return None, str(e)
    try:
        import json
        out = json.loads(data)
    except Exception as e:
        return None, 'JSON decode: %s' % e
    if out.get('result') != 'ok':
        return None, out.get('description', 'unknown error')
    return out.get('entries') or [], None


def _fetch_aprs_fi_callsigns(api_key, callsigns):
    """Request aprs.fi API for specific callsigns (up to 20). Returns list of entry dicts or (None, error)."""
    if not callsigns:
        return [], None
    name_param = ','.join(c.strip().upper() for c in callsigns if c and c.strip())[:500]
    if not name_param:
        return [], None
    params = {
        'what': 'loc',
        'apikey': api_key,
        'format': 'json',
        'name': name_param,
    }
    url = 'https://api.aprs.fi/api/get?' + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read().decode('utf-8', errors='replace')
    except urllib.error.HTTPError as e:
        return None, 'HTTP %s' % e.code
    except urllib.error.URLError as e:
        return None, str(e.reason) if getattr(e, 'reason', None) else str(e)
    except Exception as e:
        return None, str(e)
    try:
        import json
        out = json.loads(data)
    except Exception as e:
        return None, 'JSON decode: %s' % e
    if out.get('result') != 'ok':
        return None, out.get('description', 'unknown error')
    return out.get('entries') or [], None


class Command(BaseCommand):
    help = 'Poll aprs.fi and cache APRS positions inside campus outer geofence (every 5 minutes)'

    def handle(self, *args, **options):
        from dotenv import load_dotenv
        load_dotenv()

        api_key = (os.getenv('APRS_FI_API_KEY') or '').strip()
        if not api_key:
            self.stderr.write(self.style.ERROR(
                'Set APRS_FI_API_KEY in .env (get a key from https://aprs.fi/account/).'
            ))
            return

        campus_name = (os.getenv('CAMPUS') or '').strip()
        if not campus_name:
            self.stderr.write(self.style.ERROR('Set CAMPUS in .env.'))
            return

        try:
            campus = Campus.objects.get(name=campus_name)
        except Campus.DoesNotExist:
            self.stderr.write(self.style.ERROR('Campus not found: %s' % campus_name))
            return

        outer = campus.outer_geofence
        if not outer:
            self.stderr.write(self.style.ERROR(
                'Campus "%s" has no outer geofence configured.' % campus_name
            ))
            return

        lat_n = max(outer.latitude1, outer.latitude2)
        lat_s = min(outer.latitude1, outer.latitude2)
        lon_w = min(outer.longitude1, outer.longitude2)
        lon_e = max(outer.longitude1, outer.longitude2)
        center_lat, center_lon, radius_km = _bbox_center_and_radius_km(lat_n, lat_s, lon_w, lon_e)

        callsigns_env = (os.getenv('APRS_CALLSIGNS') or '').strip()
        callsign_list = [c.strip() for c in callsigns_env.split(',') if c.strip()] if callsigns_env else None

        backoff = 60
        while True:
            entries = []
            err_msg = None

            # Try area/radius request first (may not be supported by aprs.fi)
            area_entries, area_err = _fetch_aprs_fi_area(api_key, center_lat, center_lon, radius_km)
            if area_err is None:
                entries = area_entries or []
            else:
                if callsign_list:
                    for i in range(0, len(callsign_list), 20):
                        batch = callsign_list[i:i + 20]
                        batch_entries, batch_err = _fetch_aprs_fi_callsigns(api_key, batch)
                        if batch_err:
                            err_msg = batch_err
                            break
                        entries.extend(batch_entries or [])
                else:
                    err_msg = area_err

            if err_msg and not entries:
                self.stdout.write(self.style.WARNING(
                    'aprs.fi request failed: %s (will retry in %ss)' % (err_msg, backoff)
                ))
                time.sleep(backoff)
                backoff = min(600, backoff + 60)
                continue

            backoff = 60
            now = timezone.now()
            count = 0
            for entry in entries:
                lat = entry.get('lat')
                lng = entry.get('lng')
                if lat is None or lng is None:
                    continue
                try:
                    lat = float(lat)
                    lng = float(lng)
                except (TypeError, ValueError):
                    continue
                if outer.outside(lat, lng):
                    continue
                name = _clean_text((entry.get('name') or entry.get('srccall') or '').strip())
                if not name:
                    continue
                alt = entry.get('altitude')
                if alt is not None:
                    try:
                        alt = float(alt)
                    except (TypeError, ValueError):
                        alt = None
                symbol = _clean_text(entry.get('symbol'))
                comment = _clean_text(entry.get('comment'))
                path = _clean_text(entry.get('path'))
                course = entry.get('course')
                if course is not None:
                    try:
                        course = float(course)
                    except (TypeError, ValueError):
                        course = None
                speed = entry.get('speed')
                if speed is not None:
                    try:
                        speed = float(speed)
                    except (TypeError, ValueError):
                        speed = None
                APRSPosition.objects.update_or_create(
                    callsign=name,
                    defaults={
                        'latitude': lat,
                        'longitude': lng,
                        'altitude': alt,
                        'symbol': symbol,
                        'comment': comment,
                        'path': path,
                        'course': course,
                        'speed': speed,
                        'updated_at': now,
                    },
                )
                count += 1
            self.stdout.write('Polled aprs.fi: %d devices inside geofence' % count)
            try:
                time.sleep(POLL_INTERVAL_SECONDS)
            except KeyboardInterrupt:
                break
