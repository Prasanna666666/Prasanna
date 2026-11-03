"""Live public information: weather, exchange rates, time.

Privacy design: arguments are validated to tiny fixed shapes (a place name, ISO currency codes), never free text
from the user's data, and every outbound request is written to `net_audit`. Time uses the local clock - no network.
"""

from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

from .. import netguard
from ..db import rows
from ..module import Module, S, Tool

MIGRATIONS = ("CREATE TABLE net_audit (id INTEGER PRIMARY KEY, ts TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, "
              "host TEXT NOT NULL, path TEXT NOT NULL, query TEXT NOT NULL);",)
PLACE = re.compile(r"^[A-Za-z][A-Za-z .'\-]{0,39}$")
CCY = re.compile(r"^[A-Z]{3}$")
_WMO = {0: "clear", 1: "mostly clear", 2: "partly cloudy", 3: "overcast", 45: "fog", 48: "fog", 51: "light drizzle",
        53: "drizzle", 55: "heavy drizzle", 61: "light rain", 63: "rain", 65: "heavy rain", 71: "light snow",
        73: "snow", 75: "heavy snow", 80: "rain showers", 81: "rain showers", 82: "violent showers",
        95: "thunderstorm", 96: "thunderstorm with hail", 99: "thunderstorm with hail"}


def _get(conn, host: str, path: str, params: dict[str, str]) -> dict:
    if host not in netguard.PUBLIC_ALLOW:
        raise ValueError(f"{host} is not an allowed public source")
    query = urllib.parse.urlencode(params)
    conn.execute("INSERT INTO net_audit (host, path, query) VALUES (?,?,?)", (host, path, query))
    conn.commit()
    with urllib.request.urlopen(f"https://{host}{path}?{query}", timeout=15) as r:  # noqa: S310 - https, allowlisted
        return json.load(r)


def weather(conn, a):
    place = a["place"].strip()
    if not PLACE.match(place):
        raise ValueError("place must be a plain city name (letters only, max 40 chars)")
    geo = _get(conn, "geocoding-api.open-meteo.com", "/v1/search", {"name": place, "count": "1"}).get("results")
    if not geo:
        raise ValueError(f"unknown place {place!r}")
    g = geo[0]
    w = _get(conn, "api.open-meteo.com", "/v1/forecast", {
        "latitude": f"{g['latitude']:.2f}", "longitude": f"{g['longitude']:.2f}", "timezone": "auto",
        "current": "temperature_2m,apparent_temperature,weather_code,wind_speed_10m,precipitation",
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max", "forecast_days": "3"})
    c, d = w["current"], w["daily"]
    return {"place": f"{g['name']}, {g.get('country', '')}", "now_c": c["temperature_2m"],
            "feels_like_c": c["apparent_temperature"], "sky": _WMO.get(c["weather_code"], "unknown"),
            "wind_kmh": c["wind_speed_10m"],
            "next_days": [{"date": d["time"][i], "max_c": d["temperature_2m_max"][i], "min_c": d["temperature_2m_min"][i],
                           "rain_chance_pct": d["precipitation_probability_max"][i]} for i in range(len(d["time"]))]}


def exchange_rate(conn, a):
    base, quote = a["base"].upper(), a["quote"].upper()
    if not (CCY.match(base) and CCY.match(quote)):
        raise ValueError("base and quote must be 3-letter currency codes")
    d = _get(conn, "api.frankfurter.app", "/latest", {"from": base, "to": quote})
    amount = float(a.get("amount", 1))
    return {"date": d["date"], "base": base, "quote": quote, "rate": d["rates"][quote],
            "converted": round(amount * d["rates"][quote], 4), "amount": amount, "source": "ECB via frankfurter.app"}


def current_time(conn, a):
    tz = a.get("timezone") or "Asia/Kolkata"
    try:
        now = datetime.now(ZoneInfo(tz))
    except Exception as e:
        raise ValueError(f"unknown timezone {tz!r} (use e.g. Asia/Kolkata, Europe/London)") from e
    return {"timezone": tz, "iso": now.isoformat(timespec="minutes"), "weekday": now.strftime("%A")}


def network_log(conn, a):
    return rows(conn.execute("SELECT ts, host, path, query FROM net_audit ORDER BY id DESC LIMIT ?",
                             (int(a.get("limit", 50)),)))


MODULE = Module("world", MIGRATIONS, (
    Tool("weather", "Current weather and 3-day forecast for a city (public data).",
         {"place": S("City name only, e.g. Bengaluru")}, weather, ("place",)),
    Tool("exchange_rate", "Latest official exchange rate / conversion between two currencies (public data).",
         {"base": S("3-letter code, e.g. USD"), "quote": S("3-letter code, e.g. INR"),
          "amount": {"type": "number", "description": "Amount of base to convert, default 1"}},
         exchange_rate, ("base", "quote")),
    Tool("current_time", "Current local time in an IANA timezone (no network).",
         {"timezone": S("e.g. Asia/Kolkata, America/New_York")}, current_time),
    Tool("network_log", "Show what this app has sent to the internet (for transparency).",
         {"limit": {"type": "integer", "description": "Max rows"}}, network_log),
))
