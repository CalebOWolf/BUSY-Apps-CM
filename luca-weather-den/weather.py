"""
Fetches the weather from Open-Meteo (https://open-meteo.com): free, no account
or API key needed.

    place = find_place("Berlin")           # or Place("Home", 52.52, 13.41)
    report = fetch(place, fahrenheit=False)
"""

from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path

FORECAST_API = "https://api.open-meteo.com/v1/forecast"
GEOCODE_API = "https://geocoding-api.open-meteo.com/v1/search"
USER_AGENT = "luca-weather-den/1.0"
CACHE = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "luca-weather-den.json"


@dataclass
class Place:
    name: str
    lat: float
    lon: float
    region: str = ""


@dataclass
class Day:
    date: str              # "2026-11-19"
    condition: str
    high: float
    low: float
    rain_chance: float | None = None


@dataclass
class Report:
    place: Place
    temp: float
    feels: float | None
    condition: str        # see CONDITIONS
    is_day: bool
    humidity: float | None = None
    wind: float | None = None
    days: list[Day] = field(default_factory=list)
    fahrenheit: bool = False
    fetched: float = field(default_factory=time.time)

    @property
    def unit(self) -> str:
        return "°F" if self.fahrenheit else "°C"

    @property
    def celsius(self) -> float:
        return (self.temp - 32) * 5 / 9 if self.fahrenheit else self.temp


# Open-Meteo uses the WMO weather codes.
CONDITIONS = {
    "clear": ((0,), "Clear"),
    "partly": ((1, 2), "Partly cloudy"),
    "cloudy": ((3,), "Cloudy"),
    "fog": ((45, 48), "Fog"),
    "drizzle": ((51, 53, 55, 56, 57), "Drizzle"),
    "rain": ((61, 63, 65, 66, 67, 80, 81, 82), "Rain"),
    "snow": ((71, 73, 75, 77, 85, 86), "Snow"),
    "storm": ((95, 96, 99), "Thunderstorm"),
}


def condition(code: int | None) -> str:
    for name, (codes, _) in CONDITIONS.items():
        if code in codes:
            return name
    return "cloudy"


def describe(cond: str, is_day: bool = True) -> str:
    if cond == "clear":
        return "Sunny" if is_day else "Clear"
    return CONDITIONS.get(cond, ((), cond.title()))[1]


def _get(url: str, params: dict) -> dict:
    full = url + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(full, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def find_place(query: str) -> Place:
    """Look up a city by name: "Berlin", or "Portland, Oregon" to pick between
    places with the same name. The answer is cached, so it's looked up once."""
    cached = _read_cache().get("places", {}).get(query.lower())
    if cached:
        return Place(**cached)
    name, _, hint = (part.strip() for part in query.partition(","))
    data = _get(GEOCODE_API, {"name": name, "count": 10, "language": "en", "format": "json"})
    results = data.get("results") or []
    if hint:
        h = hint.lower()
        results = [r for r in results if h in (r.get("admin1", "") + " " + r.get("country", "")).lower()
                   or h == r.get("country_code", "").lower()] or results
    if not results:
        raise SystemExit(f"Couldn't find a place called '{query}'. Try a bigger city nearby, "
                         "or give --lat and --lon.")
    r = results[0]
    place = Place(r["name"], r["latitude"], r["longitude"],
                  ", ".join(x for x in (r.get("admin1"), r.get("country")) if x))
    cache = _read_cache()
    cache.setdefault("places", {})[query.lower()] = asdict(place)
    _write_cache(cache)
    return place


def fetch(place: Place, fahrenheit: bool = False) -> Report:
    params = {
        "latitude": place.lat, "longitude": place.lon, "timezone": "auto", "forecast_days": 4,
        "current": "temperature_2m,apparent_temperature,relative_humidity_2m,is_day,"
                   "weather_code,wind_speed_10m",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
    }
    if fahrenheit:
        params.update(temperature_unit="fahrenheit", wind_speed_unit="mph")
    data = _get(FORECAST_API, params)
    cur, daily = data["current"], data.get("daily", {})
    days = []
    for i, date in enumerate(daily.get("time", [])):
        rain = daily.get("precipitation_probability_max", [None] * 99)[i]
        days.append(Day(date, condition(daily["weather_code"][i]),
                        daily["temperature_2m_max"][i], daily["temperature_2m_min"][i], rain))
    report = Report(place, cur["temperature_2m"], cur.get("apparent_temperature"),
                    condition(cur.get("weather_code")), bool(cur.get("is_day", 1)),
                    cur.get("relative_humidity_2m"), cur.get("wind_speed_10m"), days, fahrenheit)
    return report


def _read_cache() -> dict:
    try:
        return json.loads(CACHE.read_text())
    except (OSError, ValueError):
        return {}


def _write_cache(data: dict) -> None:
    try:
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(json.dumps(data, indent=2))
    except OSError:
        pass


# --------------------------------------------------------------------------
# Demo: a tour through every kind of weather
# --------------------------------------------------------------------------
DEMO_TOUR = [
    ("clear", True, 24), ("partly", True, 17), ("cloudy", True, 12), ("rain", True, 9),
    ("storm", True, 19), ("fog", True, 6), ("snow", True, -3), ("clear", False, 8),
    ("partly", False, 11), ("clear", True, 33),
]


def demo(step: int, fahrenheit: bool = False) -> Report:
    cond, is_day, c = DEMO_TOUR[step % len(DEMO_TOUR)]
    conv = (lambda t: t * 9 / 5 + 32) if fahrenheit else (lambda t: t)
    days = [Day(f"2026-11-{19 + i:02d}", d, conv(c + dh), conv(c + dl), r)
            for i, (d, dh, dl, r) in enumerate([(cond, 3, -6, 40), ("partly", 2, -5, 10),
                                                ("rain", -1, -7, 70), ("clear", 4, -4, 0)])]
    return Report(Place("Den Valley", 0, 0, "Luca's Woods"), conv(c), conv(c - 2), cond, is_day,
                  64, 12, days, fahrenheit)
