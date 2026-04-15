"""
app.py — Aware Agent: Personal Intelligence Dashboard.

Streamlit dashboard showing news, weather, AQI and AI-analyzed impact
for a user in Faridabad, NCR.

Run:
    streamlit run app.py
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta
from typing import Any

import pytz
import streamlit as st
import yaml

import analyzer
import config
import knowledge_base
import news_fetcher

IST = pytz.timezone("Asia/Kolkata")

# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Aware Agent — Personal Intelligence",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS ───────────────────────────────────────────────────────────────────────

st.markdown(
    """
<style>
/* Font and base */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

/* Cards */
.alert-card {
    border-radius: 10px;
    padding: 14px 18px;
    margin-bottom: 12px;
    border-left: 5px solid;
}
.card-high   { background: #FEF2F2; border-color: #E42828; }
.card-medium { background: #FFFBEB; border-color: #D97706; }
.card-low    { background: #F0FFF4; border-color: #46A758; }
.card-info   { background: #F8FAFC; border-color: #94A3B8; }

/* Severity badges */
.badge {
    display: inline-block;
    padding: 2px 10px;
    border-radius: 999px;
    font-size: 0.72rem;
    font-weight: 600;
    letter-spacing: 0.04em;
    text-transform: uppercase;
}
.badge-high   { background: #FEE2E2; color: #991B1B; }
.badge-medium { background: #FEF3C7; color: #92400E; }
.badge-low    { background: #DCFCE7; color: #166534; }
.badge-info   { background: #F1F5F9; color: #475569; }

/* Impact score pill */
.score-pill {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 6px;
    font-size: 0.78rem;
    font-weight: 700;
    background: #1E293B;
    color: #F8FAFC;
    margin-left: 8px;
}

/* Daily briefing */
.briefing-box {
    background: linear-gradient(135deg, #1E293B 0%, #0F172A 100%);
    border-radius: 12px;
    padding: 20px 24px;
    color: #F8FAFC;
    margin-bottom: 20px;
}
.briefing-box h3 { color: #F8FAFC; margin-top: 0; font-size: 1.05rem; letter-spacing: 0.05em; text-transform: uppercase; }
.briefing-bullet { display: flex; align-items: flex-start; gap: 10px; margin-bottom: 8px; font-size: 0.92rem; }
.briefing-bullet .dot { color: #60A5FA; font-size: 1.1rem; line-height: 1.4; flex-shrink: 0; }

/* Weather card */
.weather-card {
    background: linear-gradient(135deg, #0EA5E9 0%, #0369A1 100%);
    color: white;
    border-radius: 12px;
    padding: 18px 20px;
}
.weather-temp { font-size: 2.4rem; font-weight: 700; line-height: 1; }
.weather-desc { font-size: 0.95rem; opacity: 0.88; }

/* AQI card */
.aqi-card {
    border-radius: 12px;
    padding: 18px 20px;
    color: white;
}
.aqi-value { font-size: 2.4rem; font-weight: 700; line-height: 1; }
.aqi-label { font-size: 0.95rem; opacity: 0.88; }

/* Section headers */
.section-header {
    font-size: 0.78rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: #64748B;
    margin: 18px 0 8px 0;
    padding-bottom: 4px;
    border-bottom: 1px solid #E2E8F0;
}

/* Action box */
.action-box {
    background: #EFF6FF;
    border-radius: 6px;
    padding: 6px 10px;
    font-size: 0.82rem;
    color: #1D4ED8;
    margin-top: 4px;
}

/* Tag */
.tag {
    display: inline-block;
    padding: 1px 7px;
    border-radius: 4px;
    font-size: 0.72rem;
    background: #E2E8F0;
    color: #475569;
    margin-right: 4px;
}
.tag-commute { background: #DBEAFE; color: #1D4ED8; }
.tag-family  { background: #FEE2E2; color: #991B1B; }

/* Time label */
.time-label { font-size: 0.75rem; color: #94A3B8; }

/* Divider */
.thin-hr { border: none; border-top: 1px solid #E2E8F0; margin: 6px 0; }

/* Tone banners */
.tone-alert   { background: #FEF2F2; color: #991B1B; border: 1px solid #FECACA; border-radius: 8px; padding: 8px 14px; font-weight: 600; }
.tone-caution { background: #FFFBEB; color: #92400E; border: 1px solid #FDE68A; border-radius: 8px; padding: 8px 14px; font-weight: 600; }
.tone-normal  { background: #F0FFF4; color: #166534; border: 1px solid #BBF7D0; border-radius: 8px; padding: 8px 14px; font-weight: 600; }

/* Sidebar profile form */
.sidebar-label { font-size: 0.8rem; font-weight: 600; color: #374151; margin-bottom: 2px; }

/* Refresh countdown */
.refresh-badge { font-size: 0.72rem; color: #94A3B8; float: right; }

/* No results */
.no-items { color: #94A3B8; font-size: 0.9rem; padding: 16px 0; }
</style>
""",
    unsafe_allow_html=True,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _relative_time(dt: datetime) -> str:
    """Return a human-friendly relative time string."""
    now = datetime.now(IST)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=IST)
    diff = now - dt
    total_mins = int(diff.total_seconds() / 60)
    if total_mins < 1:
        return "just now"
    if total_mins < 60:
        return f"{total_mins} min ago"
    hours = total_mins // 60
    if hours < 24:
        return f"{hours}h ago"
    return dt.strftime("%-d %b")


def _severity_class(severity: str) -> str:
    return {"high": "card-high", "medium": "card-medium", "low": "card-low"}.get(severity, "card-info")


def _badge_class(severity: str) -> str:
    return {"high": "badge-high", "medium": "badge-medium", "low": "badge-low"}.get(severity, "badge-info")


def _severity_emoji(severity: str) -> str:
    return {"high": "🔴", "medium": "🟡", "low": "🟢", "info": "⚪"}.get(severity, "⚪")


def _tone_icon(tone: str) -> str:
    return {"alert": "🚨", "caution": "⚠️", "normal": "✅"}.get(tone, "ℹ️")


# ── Data loading (cached) ─────────────────────────────────────────────────────

@st.cache_data(ttl=config.CACHE_TTL_MINUTES * 60, show_spinner=False)
def load_all_data(profile_hash: str):
    """Fetch all data. profile_hash triggers re-fetch when profile changes."""
    profile = knowledge_base.load_profile()
    raw_news = news_fetcher.fetch_all_news()
    env = news_fetcher.fetch_weather_and_aqi()
    weather = env.get("weather")
    aqi = env.get("aqi")
    analyzed_items, briefing = analyzer.analyze(raw_news, profile, weather, aqi)
    return {
        "items": analyzed_items,
        "briefing": briefing,
        "weather": weather,
        "aqi": aqi,
        "fetched_at": datetime.now(IST),
        "raw_count": len(raw_news),
    }


def _profile_hash(profile: dict) -> str:
    """Simple hash to detect profile changes."""
    import hashlib, json
    return hashlib.md5(json.dumps(profile, sort_keys=True, default=str).encode()).hexdigest()[:8]


# ── Sidebar ───────────────────────────────────────────────────────────────────

def render_sidebar(profile: dict) -> tuple[dict, bool]:
    """Render settings sidebar. Returns (updated_profile, refresh_requested)."""
    with st.sidebar:
        st.markdown("### ⚙️ Settings")
        st.markdown("---")

        st.markdown("**Profile**")
        name = st.text_input("Your Name", value=profile.get("name", "Deepak"))

        loc = profile.get("location", {})
        city = st.text_input("City", value=loc.get("city", "Faridabad"))
        neighborhood = st.text_input("Neighborhood / Sector", value=loc.get("neighborhood", "Sector 16"))
        pin_code = st.text_input("PIN Code", value=str(loc.get("pin_code", "121001")))

        st.markdown("**Commute**")
        commute = profile.get("commute", {})
        works_in = st.text_input("Works In", value=commute.get("works_in", "Noida"))
        mode = st.selectbox("Mode of Transport", ["car", "bike", "metro", "bus", "walking"],
                            index=["car", "bike", "metro", "bus", "walking"].index(commute.get("mode", "car")))
        route = st.text_input("Commute Route", value=commute.get("route", "Faridabad → Badarpur Border → Noida via NH-44"))
        typical_time = st.text_input("Typical Commute Time", value=commute.get("typical_time", "45 mins"))

        st.markdown("**Family**")
        family = profile.get("family", {})
        has_children = st.checkbox("Has School-Going Children", value=family.get("has_school_children", True))
        school_board = ""
        if has_children:
            school_board = st.text_input("School Board", value=family.get("school_board", "CBSE"))

        st.markdown("---")
        save_clicked = st.button("💾 Save Profile", use_container_width=True)
        refresh_clicked = st.button("🔄 Refresh Now", use_container_width=True)

        # API status indicators
        st.markdown("---")
        st.markdown("**API Status**")
        if config.ANTHROPIC_API_KEY:
            st.success("Claude AI: Connected")
        else:
            st.warning("Claude AI: Not configured (using keyword scoring)")
        if config.OPENWEATHER_API_KEY:
            st.success("OpenWeather: Connected")
        else:
            st.info("OpenWeather: Not configured (AQI from AQICN)")

        # Build updated profile
        updated = {
            "name": name,
            "location": {
                "city": city,
                "state": loc.get("state", "Haryana"),
                "country": "India",
                "pin_code": pin_code,
                "neighborhood": neighborhood,
            },
            "commute": {
                "works_in": works_in,
                "mode": mode,
                "route": route,
                "typical_time": typical_time,
            },
            "nearby_areas": profile.get("nearby_areas", ["Delhi NCR", "Noida", "Gurugram"]),
            "interests": profile.get("interests", []),
            "family": {
                "has_school_children": has_children,
                "school_board": school_board if has_children else "",
            },
        }

        if save_clicked:
            knowledge_base.save_profile(updated)
            st.success("Profile saved!")
            load_all_data.clear()

        return updated, refresh_clicked


# ── Render helpers ────────────────────────────────────────────────────────────

def render_briefing(briefing: dict, tone: str) -> None:
    """Render the daily briefing box at the top."""
    tone_label = {"alert": "ALERT DAY", "caution": "HEADS UP", "normal": "ALL CLEAR"}.get(tone, "TODAY")
    icon = _tone_icon(tone)

    bullets_html = "".join(
        f'<div class="briefing-bullet"><span class="dot">•</span><span>{b}</span></div>'
        for b in briefing.get("bullets", [])
    )

    generated = briefing.get("generated_at", datetime.now(IST))
    if isinstance(generated, datetime):
        time_str = generated.strftime("%-I:%M %p")
    else:
        time_str = ""

    st.markdown(
        f"""
<div class="briefing-box">
  <h3>{icon} Daily Briefing — {tone_label} <span style="float:right;font-size:0.75rem;opacity:0.6;font-weight:400">{time_str} IST</span></h3>
  {bullets_html}
</div>
""",
        unsafe_allow_html=True,
    )


def render_weather_aqi(weather: dict | None, aqi: dict | None) -> None:
    """Render weather and AQI cards side by side."""
    col1, col2 = st.columns(2)

    with col1:
        if weather:
            icon_url = f"https://openweathermap.org/img/wn/{weather['icon']}@2x.png"
            st.markdown(
                f"""
<div class="weather-card">
  <div style="display:flex;justify-content:space-between;align-items:center">
    <div>
      <div style="font-size:0.78rem;opacity:0.8;text-transform:uppercase;letter-spacing:0.05em">Weather · {weather.get('city','Faridabad')}</div>
      <div class="weather-temp">{weather['temp_c']}°C</div>
      <div class="weather-desc">{weather['description']} · Feels {weather['feels_like_c']}°C</div>
      <div style="font-size:0.8rem;margin-top:6px;opacity:0.85">
        💧 {weather['humidity_pct']}% · 💨 {weather['wind_speed_kmh']} km/h · 👁️ {weather['visibility_km']} km
      </div>
      <div style="font-size:0.78rem;margin-top:4px;opacity:0.8">
        Low: {weather['temp_min_c']}°C · High: {weather['temp_max_c']}°C
      </div>
    </div>
    <img src="{icon_url}" width="64" style="opacity:0.9">
  </div>
  {''.join(f'<div style="margin-top:8px;background:rgba(255,255,255,0.15);border-radius:6px;padding:6px 10px;font-size:0.8rem">⚠️ {a}</div>' for a in weather.get('alerts', []))}
</div>
""",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                '<div class="weather-card"><div class="weather-temp">N/A</div>'
                '<div class="weather-desc">Weather data unavailable.<br>Add OPENWEATHER_API_KEY to .env</div></div>',
                unsafe_allow_html=True,
            )

    with col2:
        if aqi:
            aqi_html = f"""
<div class="aqi-card" style="background:{aqi['color']}">
  <div style="font-size:0.78rem;opacity:0.85;text-transform:uppercase;letter-spacing:0.05em">Air Quality · {aqi.get('station','Faridabad')}</div>
  <div class="aqi-value">{aqi['aqi']}</div>
  <div class="aqi-label">{aqi['level']} (AQI)</div>
  <div style="font-size:0.78rem;margin-top:6px;opacity:0.9">
    PM2.5: {aqi.get('pm25','—')} · PM10: {aqi.get('pm10','—')} · NO₂: {aqi.get('no2','—')}
  </div>
  <div style="margin-top:8px;background:rgba(255,255,255,0.15);border-radius:6px;padding:6px 10px;font-size:0.8rem">{aqi['advice']}</div>
</div>
"""
            st.markdown(aqi_html, unsafe_allow_html=True)
        else:
            st.markdown(
                '<div class="aqi-card" style="background:#64748B"><div class="aqi-value">N/A</div>'
                '<div class="aqi-label">AQI data unavailable.</div></div>',
                unsafe_allow_html=True,
            )


def render_item_card(item: dict) -> None:
    """Render a single news/alert card."""
    severity = item.get("severity", "info")
    card_class = _severity_class(severity)
    badge_class = _badge_class(severity)
    score = item.get("impact_score", 0)

    # Tags
    tags = []
    if item.get("affects_commute"):
        tags.append('<span class="tag tag-commute">🚗 Commute</span>')
    if item.get("affects_family"):
        tags.append('<span class="tag tag-family">👨‍👩‍👧 Family</span>')

    tags_html = " ".join(tags)

    # Action
    action_html = ""
    if item.get("action"):
        action_html = f'<div class="action-box">→ {item["action"]}</div>'

    # Impact reason
    reason_html = ""
    if item.get("impact_reason"):
        reason_html = f'<div style="font-size:0.82rem;color:#374151;margin-top:4px">{item["impact_reason"]}</div>'

    # Summary
    summary = item.get("summary", "")
    if len(summary) > 200:
        summary = summary[:200] + "…"

    # URL
    url = item.get("url", "")
    title_html = (
        f'<a href="{url}" target="_blank" style="text-decoration:none;color:inherit">{item["title"]}</a>'
        if url
        else item["title"]
    )

    time_str = _relative_time(item.get("timestamp", datetime.now(IST)))

    st.markdown(
        f"""
<div class="alert-card {card_class}">
  <div style="display:flex;justify-content:space-between;align-items:flex-start">
    <div style="flex:1">
      <span class="badge {badge_class}">{severity}</span>
      <span class="score-pill">{score}/10</span>
      {tags_html}
      <div style="font-weight:600;font-size:0.92rem;margin-top:6px">{title_html}</div>
      {reason_html}
      <div style="font-size:0.8rem;color:#6B7280;margin-top:4px">{summary}</div>
      {action_html}
    </div>
  </div>
  <div style="margin-top:8px;display:flex;gap:16px">
    <span class="time-label">🕐 {time_str}</span>
    <span class="time-label">📰 {item.get('source','Unknown')}</span>
    <span class="time-label">🏷️ {item.get('category','')}</span>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )


def render_category_section(title: str, items: list[dict], empty_msg: str = "No items") -> None:
    """Render a list of cards for a category."""
    st.markdown(f'<div class="section-header">{title}</div>', unsafe_allow_html=True)
    visible = [i for i in items if i.get("impact_score", 0) >= 3]
    if not visible:
        st.markdown(f'<div class="no-items">{empty_msg}</div>', unsafe_allow_html=True)
        return
    for item in visible[:10]:
        render_item_card(item)


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    # Initialize session state
    if "last_refresh" not in st.session_state:
        st.session_state.last_refresh = time.time()
    if "auto_refresh" not in st.session_state:
        st.session_state.auto_refresh = True

    # Load profile
    profile = knowledge_base.load_profile()

    # Sidebar
    updated_profile, refresh_requested = render_sidebar(profile)
    if refresh_requested:
        load_all_data.clear()
        st.session_state.last_refresh = time.time()
        st.rerun()

    # Auto-refresh every 15 minutes
    if st.session_state.auto_refresh:
        elapsed = time.time() - st.session_state.last_refresh
        if elapsed > config.CACHE_TTL_MINUTES * 60:
            load_all_data.clear()
            st.session_state.last_refresh = time.time()
            st.rerun()

    # Header
    now_str = datetime.now(IST).strftime("%A, %-d %B %Y · %-I:%M %p IST")
    name = updated_profile.get("name", "Deepak")
    st.markdown(
        f"""
<div style="margin-bottom:6px">
  <h1 style="margin:0;font-size:1.6rem;font-weight:700">🛡️ Aware Agent</h1>
  <div style="font-size:0.85rem;color:#64748B">Personal intelligence for {name} · {now_str}</div>
</div>
""",
        unsafe_allow_html=True,
    )

    # Load data with spinner
    ph = _profile_hash(updated_profile)
    with st.spinner("Fetching latest news and alerts…"):
        data = load_all_data(ph)

    items: list[dict] = data.get("items", [])
    briefing: dict = data.get("briefing", {})
    weather: dict | None = data.get("weather")
    aqi: dict | None = data.get("aqi")
    fetched_at: datetime = data.get("fetched_at", datetime.now(IST))

    # Last updated
    st.markdown(
        f'<div style="font-size:0.75rem;color:#94A3B8;margin-bottom:12px">'
        f'Last updated: {fetched_at.strftime("%-I:%M %p IST")} · '
        f'{data.get("raw_count", 0)} news items fetched · '
        f'{"Claude AI" if config.ANTHROPIC_API_KEY else "Keyword scoring"} active</div>',
        unsafe_allow_html=True,
    )

    # Daily Briefing
    render_briefing(briefing, briefing.get("tone", "normal"))

    # Weather + AQI row
    render_weather_aqi(weather, aqi)

    st.markdown("<br>", unsafe_allow_html=True)

    # HIGH PRIORITY ALERTS (across all categories)
    high_items = [i for i in items if i.get("severity") in ("high",)]
    if high_items:
        st.markdown(
            '<div style="background:#FEF2F2;border:1px solid #FECACA;border-radius:8px;'
            'padding:10px 16px;margin-bottom:16px;font-weight:600;color:#991B1B;font-size:0.9rem">'
            f'🚨 {len(high_items)} High-Priority Alert{"s" if len(high_items) > 1 else ""} — Action Required</div>',
            unsafe_allow_html=True,
        )
        for item in high_items[:5]:
            render_item_card(item)

    # Tabbed sections
    tabs = st.tabs([
        "🚗 Traffic & Commute",
        "🌤️ Weather & Air",
        "📰 Local News",
        "🎓 Education",
        "🏛️ Govt & Policy",
        "🔧 Utilities",
        "📋 All Items",
    ])

    CATEGORIES = {
        "Traffic & Commute": "Traffic & Commute",
        "Weather & Air Quality": "Weather & Air Quality",
        "Local News": "Local News",
        "Education": "Education",
        "Government & Policy": "Government & Policy",
        "Safety & Utilities": "Safety & Utilities",
    }

    def _items_for_category(cat: str) -> list[dict]:
        return sorted(
            [i for i in items if i.get("category", "") == cat],
            key=lambda x: x.get("impact_score", 0),
            reverse=True,
        )

    with tabs[0]:
        render_category_section(
            "Traffic & Commute",
            _items_for_category("Traffic & Commute"),
            "No traffic disruptions detected on your route today.",
        )

    with tabs[1]:
        # Weather details
        if weather and weather.get("forecast"):
            st.markdown('<div class="section-header">Hourly Forecast</div>', unsafe_allow_html=True)
            fcols = st.columns(len(weather["forecast"]))
            for col, slot in zip(fcols, weather["forecast"]):
                with col:
                    rain_note = f"🌧 {slot['rain_mm']}mm" if slot.get("rain_mm", 0) > 0 else ""
                    st.markdown(
                        f"""
<div style="text-align:center;padding:10px;background:#F0F9FF;border-radius:8px">
  <div style="font-weight:600;font-size:0.85rem">{slot['time']}</div>
  <div style="font-size:1.3rem;font-weight:700">{slot['temp_c']}°</div>
  <div style="font-size:0.72rem;color:#64748B">{slot['description']}</div>
  <div style="font-size:0.72rem;color:#2563EB">{rain_note}</div>
</div>
""",
                        unsafe_allow_html=True,
                    )
        render_category_section(
            "Weather Alerts",
            _items_for_category("Weather & Air Quality"),
            "No weather alerts for your area.",
        )

    with tabs[2]:
        render_category_section(
            "Local News — Faridabad / NCR",
            _items_for_category("Local News"),
            "No significant local news.",
        )

    with tabs[3]:
        if profile.get("family", {}).get("has_school_children"):
            board = profile["family"].get("school_board", "CBSE")
            st.info(f"School children detected — showing {board} and school-related news.")
        render_category_section(
            "Education",
            _items_for_category("Education"),
            "No education alerts. No exam dates or school closures reported.",
        )

    with tabs[4]:
        render_category_section(
            "Government & Policy",
            _items_for_category("Government & Policy"),
            "No significant policy announcements today.",
        )

    with tabs[5]:
        render_category_section(
            "Safety & Utilities",
            _items_for_category("Safety & Utilities"),
            "No utility disruptions reported for your area.",
        )

    with tabs[6]:
        st.markdown('<div class="section-header">All Items (sorted by impact)</div>', unsafe_allow_html=True)

        # Filters
        col_f1, col_f2, col_f3 = st.columns([2, 2, 1])
        with col_f1:
            sev_filter = st.multiselect(
                "Severity",
                ["high", "medium", "low", "info"],
                default=["high", "medium", "low"],
                key="sev_filter",
            )
        with col_f2:
            cat_filter = st.multiselect(
                "Category",
                list(CATEGORIES.keys()),
                default=list(CATEGORIES.keys()),
                key="cat_filter",
            )
        with col_f3:
            min_score = st.slider("Min Score", 1, 10, 3, key="min_score")

        filtered = [
            i for i in items
            if i.get("severity", "info") in sev_filter
            and i.get("category", "") in cat_filter
            and i.get("impact_score", 0) >= min_score
        ]
        st.markdown(f"<div style='font-size:0.8rem;color:#94A3B8;margin-bottom:8px'>{len(filtered)} items matching filters</div>", unsafe_allow_html=True)
        for item in filtered[:30]:
            render_item_card(item)

    # Auto-refresh notice
    next_refresh = int((config.CACHE_TTL_MINUTES * 60 - (time.time() - st.session_state.last_refresh)) / 60)
    st.markdown(
        f"<div style='text-align:center;padding:20px 0;font-size:0.75rem;color:#CBD5E1'>"
        f"Auto-refreshes in ~{max(0, next_refresh)} minutes · Faridabad, Haryana, India</div>",
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
