# Aware Agent — Personal Intelligence PWA

A Progressive Web App that monitors news, weather, traffic, and local events for Faridabad / NCR and tells you how they impact your daily life. Installable on your phone like a native app.

## What it tracks

- Traffic disruptions on your commute (Faridabad → Badarpur → Noida via NH-44)
- Weather alerts and AQI for Faridabad
- CBSE exam schedules and school closures
- Strikes, protests, and bandhs in NCR / Haryana
- Government policy changes affecting daily life
- Power cuts and water supply issues
- Metro and rail disruptions
- Local Faridabad news

## Quick Start

```bash
cd aware-agent

# Install dependencies
pip install -r requirements.txt

# Copy and fill in optional API keys
cp .env.example .env
# Edit .env — all keys are optional, the app works without them

# Run the FastAPI PWA server
uvicorn server:app --host 0.0.0.0 --port 8502
```

Opens at: http://localhost:8502

To install as a PWA on your phone: open in mobile browser → "Add to Home Screen".

## Architecture

```
server.py           — FastAPI backend + API endpoints
news_fetcher.py     — Fetches from Google News RSS, NDTV, HT, TOI, AQICN
analyzer.py         — Claude API analysis (falls back to keyword scoring)
knowledge_base.py   — Loads/saves user_profile.yaml
config.py           — Settings and API keys

static/
  index.html        — PWA shell (single page app)
  style.css         — Mobile-first responsive design
  app.js            — Frontend: API calls, card rendering, tabs, pull-to-refresh
  manifest.json     — PWA manifest (installable)
  sw.js             — Service worker (offline, caching, background sync)
  icons/            — App icons (auto-generated on first run)
```

## API Keys (all optional)

| Key | Source | What it unlocks |
|-----|--------|-----------------|
| `ANTHROPIC_API_KEY` | [console.anthropic.com](https://console.anthropic.com/) | AI-powered impact analysis and briefing |
| `OPENWEATHER_API_KEY` | [openweathermap.org/api](https://openweathermap.org/api) | Weather + AQI data |
| `AQICN_TOKEN` | [aqicn.org/data-platform/token](https://aqicn.org/data-platform/token/) | Better AQI data (default `demo` works for most cities) |

**Without any keys:** App uses Google News RSS (no key needed) + keyword-based scoring for impact analysis. Fully functional.

## Customizing Your Profile

Edit `user_profile.yaml` directly or use the sidebar in the app:

```yaml
name: Deepak
location:
  city: Faridabad
  neighborhood: "Sector 16"
commute:
  works_in: "Noida"
  route: "Faridabad → Badarpur Border → Noida via NH-44"
family:
  has_school_children: true
  school_board: "CBSE"
```

## Architecture

```
app.py              — Streamlit UI
news_fetcher.py     — Fetches from Google News RSS, NDTV, HT, TOI, OpenWeatherMap, AQICN
analyzer.py         — Claude API analysis (falls back to keyword scoring)
knowledge_base.py   — Loads/saves user_profile.yaml
config.py           — Settings and API keys
```

## Data Sources

- **Google News RSS** — no key needed, real-time
- **NDTV / HT / TOI** — RSS feeds, no key needed
- **OpenWeatherMap** — weather and AQI (optional key)
- **AQICN** — air quality index (demo token works)
- **Claude AI** — impact analysis and daily briefing (optional key)

News is cached for 15 minutes. Auto-refreshes every 15 minutes.
