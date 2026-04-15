"""
config.py — Settings and API key management.
Loads from .env file if present.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from the project root
env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path)

# API Keys — all optional
OPENWEATHER_API_KEY: str = os.getenv("OPENWEATHER_API_KEY", "")

# Cache settings
CACHE_TTL_MINUTES: int = 15

# RSS Feed sources
RSS_FEEDS: list[dict] = [
    {"name": "NDTV Delhi", "url": "https://feeds.feedburner.com/ndtvnews-delhi-news", "category": "Local News"},
    {"name": "HT Delhi", "url": "https://www.hindustantimes.com/feeds/rss/cities/delhi/rssfeed.xml", "category": "Local News"},
    {"name": "TOI Delhi", "url": "https://timesofindia.indiatimes.com/rssfeeds/-2128936835.cms", "category": "Local News"},
    {"name": "NDTV India", "url": "https://feeds.feedburner.com/ndtvnews-india-news", "category": "Government & Policy"},
    {"name": "HT Gurugram", "url": "https://www.hindustantimes.com/feeds/rss/cities/gurugram/rssfeed.xml", "category": "Local News"},
]

# Google News RSS search queries — broad Delhi-NCR coverage
# Scoring and personalization happens client-side based on user profile
GOOGLE_NEWS_QUERIES: list[dict] = [
    # Local news
    {"query": "Faridabad today", "category": "Local News"},
    {"query": "Gurugram today", "category": "Local News"},
    {"query": "Delhi NCR news today", "category": "Local News"},
    # Traffic
    {"query": "Faridabad Gurugram traffic", "category": "Traffic & Commute"},
    {"query": "Badarpur border traffic today", "category": "Traffic & Commute"},
    {"query": "Delhi NCR traffic jam today", "category": "Traffic & Commute"},
    {"query": "Sohna Road traffic", "category": "Traffic & Commute"},
    {"query": "IFFCO Chowk traffic", "category": "Traffic & Commute"},
    {"query": "Golf Course Road Gurugram", "category": "Traffic & Commute"},
    {"query": "Faridabad Gurugram expressway", "category": "Traffic & Commute"},
    {"query": "Delhi metro disruption today", "category": "Traffic & Commute"},
    # Strikes / Protests
    {"query": "Haryana strike bandh today", "category": "Local News"},
    {"query": "Delhi NCR protest today", "category": "Local News"},
    {"query": "Gurugram protest today", "category": "Local News"},
    # Education
    {"query": "CBSE exam schedule 2026", "category": "Education"},
    {"query": "school closed Haryana Delhi", "category": "Education"},
    {"query": "CBSE result date", "category": "Education"},
    # Weather & AQI
    {"query": "Delhi NCR weather alert today", "category": "Weather & Air Quality"},
    {"query": "Faridabad rain today", "category": "Weather & Air Quality"},
    {"query": "Delhi AQI today", "category": "Weather & Air Quality"},
    # Utilities
    {"query": "Faridabad water supply today", "category": "Safety & Utilities"},
    {"query": "DHBVN power cut Faridabad", "category": "Safety & Utilities"},
    {"query": "Haryana power outage today", "category": "Safety & Utilities"},
    # Government / Economy
    {"query": "petrol diesel price today Delhi", "category": "Government & Policy"},
    {"query": "Haryana government announcement", "category": "Government & Policy"},
    {"query": "toll price Delhi NCR", "category": "Government & Policy"},
]

# OpenWeatherMap
WEATHER_CITY: str = "Faridabad,IN"
WEATHER_BASE_URL: str = "https://api.openweathermap.org/data/2.5"

# AQICN
AQI_CITY_URL: str = "https://api.waqi.info/feed/faridabad/"
AQICN_TOKEN: str = os.getenv("AQICN_TOKEN", "demo")

AQI_LEVELS: dict = {
    "Good":         (0, 50),
    "Satisfactory": (51, 100),
    "Moderate":     (101, 200),
    "Poor":         (201, 300),
    "Very Poor":    (301, 400),
    "Severe":       (401, 500),
}
