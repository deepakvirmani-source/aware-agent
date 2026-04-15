"""
server.py — FastAPI backend for Aware PWA.

Dumb news proxy — no user profile, no scoring, no analysis.
Deployed on Render. Returns raw data only.

Endpoints:
  GET  /api/news     — raw news items (title, summary, source, url, timestamp, category)
  GET  /api/weather  — weather data
  GET  /api/aqi      — AQI data
  GET  /api/status   — server health

Run:
    uvicorn server:app --host 0.0.0.0 --port 8502
"""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import pytz
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

sys.path.insert(0, str(Path(__file__).parent))

import config
import news_fetcher

IST = pytz.timezone("Asia/Kolkata")

# ── App setup ─────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Aware News API",
    description="Stateless news proxy — weather, AQI, RSS. No user data.",
    version="3.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


# ── Serialization helper ──────────────────────────────────────────────────────

def _serialize(obj: Any) -> Any:
    """Recursively make an object JSON-serializable."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_serialize(i) for i in obj]
    return obj


# ── In-process cache ──────────────────────────────────────────────────────────

_data_cache: dict[str, Any] = {}
_cache_lock = asyncio.Lock()


async def _get_raw_news() -> dict:
    """Fetch raw news + weather + AQI, with 15-minute cache."""
    async with _cache_lock:
        cached = _data_cache.get("all")
        if cached:
            age_seconds = (datetime.now(IST) - cached["fetched_at"]).total_seconds()
            if age_seconds < config.CACHE_TTL_MINUTES * 60:
                return cached

        loop = asyncio.get_event_loop()
        raw_news = await loop.run_in_executor(None, news_fetcher.fetch_all_news)
        env = await loop.run_in_executor(None, news_fetcher.fetch_weather_and_aqi)

        result = {
            "items": raw_news,
            "weather": env.get("weather"),
            "aqi": env.get("aqi"),
            "fetched_at": datetime.now(IST),
            "item_count": len(raw_news),
        }
        _data_cache["all"] = result
        return result


def _invalidate_cache():
    _data_cache.clear()


# ── API routes ────────────────────────────────────────────────────────────────

@app.get("/api/news")
async def get_news(limit: int = 150):
    """Return raw news items — no scoring, no profile, no analysis."""
    data = await _get_raw_news()
    items = data["items"][:limit]

    # Return only safe, non-personal fields
    clean_items = [
        {
            "title":     item.get("title", ""),
            "summary":   item.get("summary", ""),
            "source":    item.get("source", ""),
            "url":       item.get("url", ""),
            "timestamp": item.get("timestamp"),
            "category":  item.get("category", "Local News"),
        }
        for item in items
    ]

    return JSONResponse(_serialize({
        "items":      clean_items,
        "total":      len(clean_items),
        "fetched_at": data["fetched_at"],
    }))


@app.get("/api/weather")
async def get_weather():
    """Return current weather and forecast."""
    data = await _get_raw_news()
    weather = data.get("weather")

    if not weather:
        return JSONResponse({
            "available": False,
            "message":   "Weather data unavailable. Add OPENWEATHER_API_KEY to environment.",
        })

    return JSONResponse(_serialize({"available": True, **weather}))


@app.get("/api/aqi")
async def get_aqi():
    """Return air quality index."""
    data = await _get_raw_news()
    aqi = data.get("aqi")

    if not aqi:
        return JSONResponse({
            "available": False,
            "message":   "AQI data unavailable.",
        })

    return JSONResponse(_serialize({"available": True, **aqi}))


@app.get("/api/status")
async def get_status():
    """Return server health info."""
    return JSONResponse({
        "status":             "ok",
        "version":            "3.0.0",
        "openweather_api":    bool(config.OPENWEATHER_API_KEY),
        "aqicn_token":        config.AQICN_TOKEN != "demo",
        "cache_ttl_minutes":  config.CACHE_TTL_MINUTES,
        "server_time_ist":    datetime.now(IST).isoformat(),
        "note":               "Stateless news proxy. No user data stored.",
    })


# ── Static files (PWA) ────────────────────────────────────────────────────────

static_dir = Path(__file__).resolve().parent / "static"


@app.get("/")
async def serve_index():
    from fastapi.responses import FileResponse
    index = static_dir / "index.html"
    return FileResponse(str(index))


@app.get("/manifest.json")
async def serve_manifest():
    from fastapi.responses import FileResponse
    return FileResponse(str(static_dir / "manifest.json"))


@app.get("/sw.js")
async def serve_sw():
    from fastapi.responses import FileResponse
    return FileResponse(str(static_dir / "sw.js"), media_type="application/javascript")


# Mount static AFTER explicit routes so / doesn't get swallowed
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


# ── Icon generation on startup ────────────────────────────────────────────────

def _generate_icons():
    """Generate simple PNG icons using Pillow."""
    try:
        from PIL import Image, ImageDraw, ImageFont
        icons_dir = Path(__file__).parent / "static" / "icons"
        icons_dir.mkdir(parents=True, exist_ok=True)

        for size in [192, 512]:
            icon_path = icons_dir / f"icon-{size}.png"
            if icon_path.exists():
                continue

            img = Image.new("RGB", (size, size), color=(0, 106, 220))
            draw = ImageDraw.Draw(img)
            font_size = int(size * 0.55)
            try:
                font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", font_size)
            except Exception:
                try:
                    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_size)
                except Exception:
                    font = ImageFont.load_default()

            text = "A"
            bbox = draw.textbbox((0, 0), text, font=font)
            text_w = bbox[2] - bbox[0]
            text_h = bbox[3] - bbox[1]
            x = (size - text_w) // 2 - bbox[0]
            y = (size - text_h) // 2 - bbox[1] - int(size * 0.03)
            draw.text((x, y), text, fill="white", font=font)
            img.save(str(icon_path), "PNG")
            print(f"  Generated icon: {icon_path}")

    except ImportError:
        _generate_icons_fallback()
    except Exception as e:
        print(f"  Icon generation warning: {e}")
        _generate_icons_fallback()


def _generate_icons_fallback():
    import struct, zlib
    icons_dir = Path(__file__).parent / "static" / "icons"
    icons_dir.mkdir(parents=True, exist_ok=True)

    def make_png(size: int, color: tuple) -> bytes:
        width, height = size, size
        r, g, b = color
        row = bytes([0]) + bytes([r, g, b] * width)
        raw = row * height
        compressed = zlib.compress(raw)

        def chunk(name: bytes, data: bytes) -> bytes:
            c = name + data
            return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

        ihdr_data = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
        png = b"\x89PNG\r\n\x1a\n"
        png += chunk(b"IHDR", ihdr_data)
        png += chunk(b"IDAT", compressed)
        png += chunk(b"IEND", b"")
        return png

    blue = (0, 106, 220)
    for size in [192, 512]:
        icon_path = icons_dir / f"icon-{size}.png"
        if not icon_path.exists():
            icon_path.write_bytes(make_png(size, blue))
            print(f"  Generated fallback icon: {icon_path}")


# ── Startup ───────────────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup_event():
    print("Aware News Server (v3 — stateless proxy) starting up...")
    print(f"  Weather API: {'enabled' if config.OPENWEATHER_API_KEY else 'disabled'}")
    print(f"  AQICN: {'custom token' if config.AQICN_TOKEN != 'demo' else 'demo token'}")
    print("  No user profile, no scoring, no personal data.")
    _generate_icons()
    print("  Icons ready.")
    print("  Server ready at http://0.0.0.0:8502")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=8502, reload=False)
