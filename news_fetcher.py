"""
news_fetcher.py — Fetches news from multiple sources.

Sources:
1. Google News RSS (no API key needed)
2. Curated RSS feeds (NDTV, HT, TOI)
3. OpenWeatherMap (weather + AQI) — optional
4. AQICN (AQI) — optional, 'demo' token works for basic use

Each item returned as:
{
    "title": str,
    "summary": str,
    "source": str,
    "url": str,
    "timestamp": datetime (IST),
    "category": str,
    "raw_score": int,   # 0 = unscored
}
"""

from __future__ import annotations

import hashlib
import time
import urllib.parse
from datetime import datetime, timezone, timedelta
from typing import Any

import feedparser
import requests
import pytz

import config

IST = pytz.timezone("Asia/Kolkata")

# ── Simple in-memory cache ────────────────────────────────────────────────────
_cache: dict[str, dict] = {}  # key → {"data": ..., "fetched_at": float}


def _cache_get(key: str) -> Any | None:
    entry = _cache.get(key)
    if not entry:
        return None
    age_minutes = (time.time() - entry["fetched_at"]) / 60
    if age_minutes > config.CACHE_TTL_MINUTES:
        del _cache[key]
        return None
    return entry["data"]


def _cache_set(key: str, data: Any) -> None:
    _cache[key] = {"data": data, "fetched_at": time.time()}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _to_ist(dt: datetime | None) -> datetime:
    """Convert any datetime to IST. If None, return now."""
    if dt is None:
        return datetime.now(IST)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(IST)


def _parse_feed_time(entry: Any) -> datetime:
    """Extract published time from feedparser entry."""
    for attr in ("published_parsed", "updated_parsed"):
        t = getattr(entry, attr, None)
        if t:
            dt = datetime(*t[:6], tzinfo=timezone.utc)
            return _to_ist(dt)
    return datetime.now(IST)


def _clean_html(text: str) -> str:
    """Strip basic HTML tags from a string."""
    import re
    return re.sub(r"<[^>]+>", "", text or "").strip()


def _deduplicate(items: list[dict]) -> list[dict]:
    """Remove items with identical titles (case-insensitive)."""
    seen: set[str] = set()
    result = []
    for item in items:
        key = item["title"].lower().strip()
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


# ── Google News RSS ───────────────────────────────────────────────────────────

def _fetch_google_news(query: str, category: str) -> list[dict]:
    """Fetch Google News RSS for a given query."""
    cache_key = f"gnews:{query}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    encoded = urllib.parse.quote(query)
    url = f"https://news.google.com/rss/search?q={encoded}&hl=en-IN&gl=IN&ceid=IN:en"

    try:
        feed = feedparser.parse(url)
        items = []
        for entry in feed.entries[:8]:  # limit to 8 per query
            title = _clean_html(entry.get("title", ""))
            summary = _clean_html(entry.get("summary", entry.get("description", "")))
            items.append({
                "title": title,
                "summary": summary[:400],
                "source": entry.get("source", {}).get("title", "Google News"),
                "url": entry.get("link", ""),
                "timestamp": _parse_feed_time(entry),
                "category": category,
                "raw_score": 0,
            })
        _cache_set(cache_key, items)
        return items
    except Exception as e:
        return []


def fetch_google_news_all() -> list[dict]:
    """Fetch all configured Google News queries."""
    all_items = []
    for q in config.GOOGLE_NEWS_QUERIES:
        items = _fetch_google_news(q["query"], q["category"])
        all_items.extend(items)
    return _deduplicate(all_items)


# ── RSS Feeds ─────────────────────────────────────────────────────────────────

def fetch_rss_feeds() -> list[dict]:
    """Fetch all configured RSS feeds."""
    all_items = []
    for feed_config in config.RSS_FEEDS:
        cache_key = f"rss:{feed_config['url']}"
        cached = _cache_get(cache_key)
        if cached is not None:
            all_items.extend(cached)
            continue
        try:
            feed = feedparser.parse(feed_config["url"])
            items = []
            for entry in feed.entries[:10]:
                title = _clean_html(entry.get("title", ""))
                summary = _clean_html(entry.get("summary", entry.get("description", "")))
                items.append({
                    "title": title,
                    "summary": summary[:400],
                    "source": feed_config["name"],
                    "url": entry.get("link", ""),
                    "timestamp": _parse_feed_time(entry),
                    "category": feed_config["category"],
                    "raw_score": 0,
                })
            _cache_set(cache_key, items)
            all_items.extend(items)
        except Exception:
            continue
    return _deduplicate(all_items)


# ── Weather (OpenWeatherMap) ──────────────────────────────────────────────────

def fetch_weather() -> dict | None:
    """Fetch weather. Tries OpenWeatherMap first, falls back to Open-Meteo (no key needed)."""
    cache_key = "weather:faridabad"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    result = None

    # Try OpenWeatherMap first (if key available)
    if config.OPENWEATHER_API_KEY:
        result = _fetch_weather_openweathermap()

    # Fallback to Open-Meteo (always free, no key)
    if result is None:
        result = _fetch_weather_open_meteo()

    if result:
        _cache_set(cache_key, result)
    return result


def _fetch_weather_openweathermap() -> dict | None:
    """Fetch from OpenWeatherMap (needs API key)."""
    try:
        resp = requests.get(
            f"{config.WEATHER_BASE_URL}/weather",
            params={"q": config.WEATHER_CITY, "appid": config.OPENWEATHER_API_KEY, "units": "metric"},
            timeout=10,
        )
        resp.raise_for_status()
        current = resp.json()

        forecast_resp = requests.get(
            f"{config.WEATHER_BASE_URL}/forecast",
            params={"q": config.WEATHER_CITY, "appid": config.OPENWEATHER_API_KEY, "units": "metric", "cnt": 8},
            timeout=10,
        )
        forecast_resp.raise_for_status()
        forecast = forecast_resp.json()

        return {
            "city": current.get("name", "Faridabad"),
            "temp_c": round(current["main"]["temp"], 1),
            "feels_like_c": round(current["main"]["feels_like"], 1),
            "temp_min_c": round(current["main"]["temp_min"], 1),
            "temp_max_c": round(current["main"]["temp_max"], 1),
            "humidity_pct": current["main"]["humidity"],
            "description": current["weather"][0]["description"].title(),
            "icon": current["weather"][0]["icon"],
            "wind_speed_kmh": round(current["wind"]["speed"] * 3.6, 1),
            "visibility_km": round(current.get("visibility", 10000) / 1000, 1),
            "forecast": [
                {
                    "time": _to_ist(datetime.fromtimestamp(item["dt"], tz=timezone.utc)).strftime("%I:%M %p"),
                    "temp_c": round(item["main"]["temp"], 1),
                    "description": item["weather"][0]["description"].title(),
                    "rain_mm": item.get("rain", {}).get("3h", 0),
                }
                for item in forecast.get("list", [])[:4]
            ],
            "alerts": _extract_weather_alerts(current),
            "source": "OpenWeatherMap",
            "fetched_at": datetime.now(IST),
        }
    except Exception:
        return None


# Faridabad coordinates
_FARIDABAD_LAT = 28.4089
_FARIDABAD_LNG = 77.3178

# WMO weather code descriptions
_WMO_CODES = {
    0: "Clear Sky", 1: "Mainly Clear", 2: "Partly Cloudy", 3: "Overcast",
    45: "Fog", 48: "Depositing Rime Fog",
    51: "Light Drizzle", 53: "Moderate Drizzle", 55: "Dense Drizzle",
    61: "Slight Rain", 63: "Moderate Rain", 65: "Heavy Rain",
    71: "Slight Snow", 73: "Moderate Snow", 75: "Heavy Snow",
    80: "Slight Showers", 81: "Moderate Showers", 82: "Violent Showers",
    95: "Thunderstorm", 96: "Thunderstorm With Hail", 99: "Thunderstorm With Heavy Hail",
}


def _fetch_weather_open_meteo() -> dict | None:
    """Fetch from Open-Meteo — completely free, no API key needed."""
    try:
        # Current weather + hourly forecast
        resp = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": _FARIDABAD_LAT,
                "longitude": _FARIDABAD_LNG,
                "current": "temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m,visibility",
                "hourly": "temperature_2m,weather_code,precipitation_probability,precipitation",
                "daily": "temperature_2m_max,temperature_2m_min,weather_code,precipitation_sum",
                "timezone": "Asia/Kolkata",
                "forecast_days": 2,
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

        current = data.get("current", {})
        hourly = data.get("hourly", {})
        daily = data.get("daily", {})

        weather_code = current.get("weather_code", 0)
        description = _WMO_CODES.get(weather_code, "Unknown")
        temp = current.get("temperature_2m", 0)
        humidity = current.get("relative_humidity_2m", 0)
        wind = current.get("wind_speed_10m", 0)
        visibility = current.get("visibility", 10000)

        # Build forecast from hourly (next 4 x 3-hour slots)
        forecast = []
        hourly_times = hourly.get("time", [])
        hourly_temps = hourly.get("temperature_2m", [])
        hourly_codes = hourly.get("weather_code", [])
        hourly_rain = hourly.get("precipitation", [])
        hourly_rain_prob = hourly.get("precipitation_probability", [])

        # Find current hour index
        now_hour = datetime.now(IST).strftime("%Y-%m-%dT%H:00")
        start_idx = 0
        for i, t in enumerate(hourly_times):
            if t >= now_hour:
                start_idx = i
                break

        for offset in [1, 3, 6, 9]:
            idx = start_idx + offset
            if idx < len(hourly_times):
                t = hourly_times[idx]
                forecast.append({
                    "time": datetime.fromisoformat(t).strftime("%I:%M %p"),
                    "temp_c": round(hourly_temps[idx], 1) if idx < len(hourly_temps) else None,
                    "description": _WMO_CODES.get(hourly_codes[idx], "") if idx < len(hourly_codes) else "",
                    "rain_mm": round(hourly_rain[idx], 1) if idx < len(hourly_rain) else 0,
                    "rain_prob_pct": hourly_rain_prob[idx] if idx < len(hourly_rain_prob) else 0,
                })

        # Build alerts
        alerts = []
        if weather_code >= 95:
            alerts.append("Thunderstorm — drive carefully, avoid flooded underpasses.")
        elif weather_code in (63, 65, 81, 82):
            alerts.append("Heavy rain — expect waterlogging, add 20+ mins to commute.")
        elif weather_code in (61, 80):
            alerts.append("Rain — wet roads, reduced visibility. Drive carefully.")
        elif weather_code in (45, 48):
            if visibility < 1000:
                alerts.append(f"Dense fog (visibility {int(visibility)}m) — drive with fog lights, leave early.")
            else:
                alerts.append("Foggy conditions — reduced visibility, drive carefully.")
        if temp > 42:
            alerts.append(f"Heat wave ({temp}°C) — stay hydrated, avoid outdoor exertion 12-4 PM.")
        if temp < 5:
            alerts.append(f"Cold wave ({temp}°C) — wrap up, check for fog on expressway.")

        # Check if rain coming in next 6 hours
        upcoming_rain = []
        for offset in range(1, 7):
            idx = start_idx + offset
            if idx < len(hourly_rain) and hourly_rain[idx] > 0.5:
                rain_time = datetime.fromisoformat(hourly_times[idx]).strftime("%I:%M %p")
                upcoming_rain.append((rain_time, round(hourly_rain[idx], 1)))
        if upcoming_rain and not any("rain" in a.lower() for a in alerts):
            first = upcoming_rain[0]
            alerts.append(f"Rain expected at {first[0]} ({first[1]}mm) — carry umbrella, plan commute accordingly.")

        return {
            "city": "Faridabad",
            "temp_c": round(temp, 1),
            "feels_like_c": round(current.get("apparent_temperature", temp), 1),
            "temp_min_c": round(daily.get("temperature_2m_min", [temp])[0], 1),
            "temp_max_c": round(daily.get("temperature_2m_max", [temp])[0], 1),
            "humidity_pct": humidity,
            "description": description,
            "icon": None,
            "wind_speed_kmh": round(wind, 1),
            "visibility_km": round(visibility / 1000, 1),
            "forecast": forecast,
            "alerts": alerts,
            "source": "Open-Meteo",
            "fetched_at": datetime.now(IST),
        }
    except Exception:
        return None


def _extract_weather_alerts(data: dict) -> list[str]:
    """Extract weather warnings from OpenWeatherMap data."""
    alerts = []
    weather_id = data.get("weather", [{}])[0].get("id", 0)
    description = data.get("weather", [{}])[0].get("description", "").lower()

    # Thunderstorm
    if 200 <= weather_id < 300:
        alerts.append("Thunderstorm — drive carefully, avoid flooded underpasses.")
    # Heavy rain
    elif 500 <= weather_id < 600:
        rain = data.get("rain", {}).get("1h", 0)
        if rain > 10:
            alerts.append(f"Heavy rain ({rain} mm/hr) — expect waterlogging, add 20+ mins to commute.")
        elif rain > 2:
            alerts.append("Rain — wet roads, reduced visibility. Drive carefully.")
    # Fog / mist
    elif weather_id in (701, 741):
        visibility = data.get("visibility", 10000)
        if visibility < 1000:
            alerts.append(f"Dense fog (visibility {visibility}m) — drive with fog lights, leave early.")
        else:
            alerts.append("Misty conditions — reduced visibility on NH-44, drive carefully.")
    # Extreme heat
    temp = data.get("main", {}).get("temp", 25)
    if temp > 42:
        alerts.append(f"Heat wave ({temp}°C) — stay hydrated, avoid outdoor exertion during 12-4 PM.")

    return alerts


# ── AQI ───────────────────────────────────────────────────────────────────────

def fetch_aqi() -> dict | None:
    """Fetch AQI from AQICN. Works with 'demo' token for basic cities."""
    cache_key = "aqi:faridabad"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    try:
        resp = requests.get(
            config.AQI_CITY_URL,
            params={"token": config.AQICN_TOKEN},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

        if data.get("status") != "ok":
            # Try Delhi as fallback
            resp2 = requests.get(
                "https://api.waqi.info/feed/delhi/",
                params={"token": config.AQICN_TOKEN},
                timeout=10,
            )
            resp2.raise_for_status()
            data = resp2.json()

        if data.get("status") != "ok":
            return None

        aqi_value = data["data"]["aqi"]
        dominants = data["data"].get("dominentpol", "pm25")
        iaqi = data["data"].get("iaqi", {})

        level = _aqi_level(aqi_value)
        result = {
            "aqi": aqi_value,
            "level": level["label"],
            "color": level["color"],
            "advice": level["advice"],
            "dominant_pollutant": dominants.upper(),
            "pm25": iaqi.get("pm25", {}).get("v"),
            "pm10": iaqi.get("pm10", {}).get("v"),
            "no2": iaqi.get("no2", {}).get("v"),
            "o3": iaqi.get("o3", {}).get("v"),
            "station": data["data"].get("city", {}).get("name", "Faridabad"),
            "fetched_at": datetime.now(IST),
        }
        _cache_set(cache_key, result)
        return result
    except Exception:
        return None


def _aqi_level(aqi: int) -> dict:
    levels = [
        (50,  "Good",         "#46A758", "Air quality is good. No precautions needed."),
        (100, "Satisfactory", "#84CC16", "Air quality is acceptable. Sensitive individuals should reduce prolonged outdoor exertion."),
        (200, "Moderate",     "#D97706", "Members of sensitive groups may experience health effects. Consider wearing N95 mask outdoors."),
        (300, "Poor",         "#F97316", "Everyone may begin to experience health effects. Wear N95 mask outdoors. Avoid strenuous activity."),
        (400, "Very Poor",    "#E42828", "Health alert: everyone may experience serious health effects. Stay indoors, use air purifier."),
        (500, "Severe",       "#7C3AED", "Health emergency. Avoid all outdoor activity. Keep windows closed. Use air purifier."),
    ]
    for threshold, label, color, advice in levels:
        if aqi <= threshold:
            return {"label": label, "color": color, "advice": advice}
    return {"label": "Hazardous", "color": "#1E1B4B", "advice": "Extreme health risk. Do not go outside."}


# ── AQI via OpenWeatherMap (fallback) ─────────────────────────────────────────

def fetch_aqi_owm() -> dict | None:
    """Fetch AQI from OpenWeatherMap Air Pollution API (requires API key)."""
    if not config.OPENWEATHER_API_KEY:
        return None

    cache_key = "aqi:owm:faridabad"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    # Faridabad coordinates
    lat, lon = 28.4089, 77.3178

    try:
        resp = requests.get(
            f"{config.WEATHER_BASE_URL}/air_pollution",
            params={"lat": lat, "lon": lon, "appid": config.OPENWEATHER_API_KEY},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        item = data["list"][0]
        components = item["components"]

        # OWM AQI is 1-5 scale; convert to 0-500 approximate
        owm_aqi = item["main"]["aqi"]
        aqi_map = {1: 30, 2: 75, 3: 150, 4: 250, 5: 350}
        approx_aqi = aqi_map.get(owm_aqi, 150)
        level = _aqi_level(approx_aqi)

        result = {
            "aqi": approx_aqi,
            "level": level["label"],
            "color": level["color"],
            "advice": level["advice"],
            "dominant_pollutant": "PM2.5",
            "pm25": round(components.get("pm2_5", 0), 1),
            "pm10": round(components.get("pm10", 0), 1),
            "no2": round(components.get("no2", 0), 1),
            "o3": round(components.get("o3", 0), 1),
            "station": "Faridabad (OWM)",
            "fetched_at": datetime.now(IST),
        }
        _cache_set(cache_key, result)
        return result
    except Exception:
        return None


# ── Master fetch ──────────────────────────────────────────────────────────────

def fetch_all_news() -> list[dict]:
    """Fetch news from all sources, deduplicate, sort by time."""
    items: list[dict] = []

    # Google News (primary — no API key needed)
    try:
        items.extend(fetch_google_news_all())
    except Exception:
        pass

    # RSS feeds
    try:
        items.extend(fetch_rss_feeds())
    except Exception:
        pass

    # Deduplicate and sort (newest first)
    items = _deduplicate(items)
    items.sort(key=lambda x: x["timestamp"], reverse=True)

    # Cap at 150 items for performance
    return items[:150]


def fetch_weather_and_aqi() -> dict:
    """Fetch weather and AQI. Returns dict with 'weather' and 'aqi' keys."""
    weather = fetch_weather()
    aqi = fetch_aqi()

    # If AQICN fails and OWM key exists, try OWM AQI
    if aqi is None and config.OPENWEATHER_API_KEY:
        aqi = fetch_aqi_owm()

    return {"weather": weather, "aqi": aqi}
