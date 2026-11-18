"""
Where the sun is and what the moon looks like, worked out locally (no internet).

  sun_elevation(when, lat, lon)   degrees above the horizon
  sun_times(day, lat, lon)        today's sunrise and sunset (local datetimes)
  moon_phase(when)                0 = new, 0.5 = full, back to 1 = new
  guess_place()                   a location to use when none is given

Accurate to a few minutes, which is plenty for a desk clock.
"""

from __future__ import annotations

import json
import math
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

WEATHER_CACHE = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "luca-weather-den.json"


def sun_elevation(when: datetime, lat: float, lon: float) -> float:
    """The sun's height above the horizon in degrees (NOAA's approximation)."""
    utc = when.astimezone(timezone.utc)
    day_of_year = utc.timetuple().tm_yday
    hour = utc.hour + utc.minute / 60 + utc.second / 3600
    g = 2 * math.pi / 365 * (day_of_year - 1 + (hour - 12) / 24)  # fractional year
    decl = (0.006918 - 0.399912 * math.cos(g) + 0.070257 * math.sin(g)
            - 0.006758 * math.cos(2 * g) + 0.000907 * math.sin(2 * g)
            - 0.002697 * math.cos(3 * g) + 0.00148 * math.sin(3 * g))
    eqtime = 229.18 * (0.000075 + 0.001868 * math.cos(g) - 0.032077 * math.sin(g)
                       - 0.014615 * math.cos(2 * g) - 0.040849 * math.sin(2 * g))
    solar_minutes = hour * 60 + eqtime + 4 * lon
    hour_angle = math.radians(solar_minutes / 4 - 180)
    la = math.radians(lat)
    cos_zenith = (math.sin(la) * math.sin(decl)
                  + math.cos(la) * math.cos(decl) * math.cos(hour_angle))
    return 90 - math.degrees(math.acos(max(-1.0, min(1.0, cos_zenith))))


def sun_times(day: date, lat: float, lon: float, tz) -> tuple[datetime | None, datetime | None]:
    """Sunrise and sunset on this day, found by scanning it in 5-minute steps.
    None when the sun doesn't rise or set (polar days and nights)."""
    start = datetime(day.year, day.month, day.day, tzinfo=tz)
    rise = set_ = None
    prev = sun_elevation(start, lat, lon)
    for step in range(1, 289):
        t = start + timedelta(minutes=5 * step)
        e = sun_elevation(t, lat, lon)
        if prev < -0.833 <= e and rise is None:   # -0.833°: the sun's rim, with refraction
            rise = t
        if prev >= -0.833 > e:
            set_ = t
        prev = e
    return rise, set_


SYNODIC = 29.530588853
KNOWN_NEW_MOON = datetime(2000, 1, 6, 18, 14, tzinfo=timezone.utc)


def moon_phase(when: datetime) -> float:
    """0 new moon, 0.25 first quarter, 0.5 full, 0.75 last quarter."""
    days = (when.astimezone(timezone.utc) - KNOWN_NEW_MOON).total_seconds() / 86400
    return (days % SYNODIC) / SYNODIC


def guess_place() -> tuple[float, float, str]:
    """Use Luca Weather Den's saved place if there is one; otherwise guess from
    the time zone (longitude) and assume mid-latitudes."""
    try:
        places = json.loads(WEATHER_CACHE.read_text()).get("places", {})
        if places:
            p = next(iter(places.values()))
            return p["lat"], p["lon"], f"{p['name']} (from Weather Den)"
    except (OSError, ValueError, KeyError, StopIteration):
        pass
    offset = datetime.now().astimezone().utcoffset() or timedelta()
    lon = offset.total_seconds() / 3600 * 15
    return 45.0, lon, "a guess from your time zone"
