"""
analyzer.py — Analyzes news items for personal impact using Claude or keyword fallback.

Each analyzed item returns:
{
    "title": str,
    "summary": str,
    "source": str,
    "url": str,
    "timestamp": datetime,
    "category": str,
    "impact_score": int,      # 1-10
    "severity": str,          # "high" | "medium" | "low" | "info"
    "impact_reason": str,     # Why it matters to the user
    "action": str,            # What the user should do
    "affects_commute": bool,
    "affects_family": bool,
}

Daily briefing:
{
    "bullets": list[str],     # 3-5 key points for today
    "tone": str,              # "alert" | "caution" | "normal"
    "generated_at": datetime,
}
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

import pytz

import config
import knowledge_base

IST = pytz.timezone("Asia/Kolkata")

# ── Claude-powered analysis ───────────────────────────────────────────────────

def _analyze_with_claude(
    news_items: list[dict],
    user_context: str,
    weather: dict | None,
    aqi: dict | None,
) -> tuple[list[dict], dict]:
    """Use Claude API to score and analyze news items."""
    try:
        import anthropic
    except ImportError:
        raise ImportError("anthropic package not installed")

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

    # Build news digest (top 30 items to stay within token limits)
    news_digest = []
    for i, item in enumerate(news_items[:30]):
        news_digest.append(
            f"[{i}] {item['title']}\n"
            f"    Source: {item['source']} | Category: {item['category']}\n"
            f"    Summary: {item['summary'][:200]}"
        )

    weather_text = ""
    if weather:
        weather_text = (
            f"\nCurrent Weather (Faridabad): {weather['temp_c']}°C, "
            f"{weather['description']}, Humidity: {weather['humidity_pct']}%, "
            f"Wind: {weather['wind_speed_kmh']} km/h"
        )
        if weather.get("alerts"):
            weather_text += f"\nWeather Alerts: {'; '.join(weather['alerts'])}"

    aqi_text = ""
    if aqi:
        aqi_text = (
            f"\nAQI (Faridabad): {aqi['aqi']} ({aqi['level']}) — "
            f"PM2.5: {aqi.get('pm25', 'N/A')}, PM10: {aqi.get('pm10', 'N/A')}"
        )

    prompt = f"""You are a personal intelligence assistant for an Indian professional.

USER CONTEXT:
{user_context}
{weather_text}
{aqi_text}

NEWS ITEMS TO ANALYZE:
{chr(10).join(news_digest)}

Your task:
1. For each news item, assess its personal impact on the user based on their profile.
2. Generate a daily briefing (3-5 bullet points of what the user needs to know TODAY).

Respond ONLY in valid JSON with this exact structure:
{{
  "items": [
    {{
      "index": 0,
      "impact_score": 7,
      "severity": "high",
      "impact_reason": "Road closure on Mathura Road affects your daily commute.",
      "action": "Take Kalindi Kunj route. Leave 30 mins early.",
      "affects_commute": true,
      "affects_family": false
    }}
  ],
  "daily_briefing": {{
    "bullets": [
      "Heavy rain expected — add 20 mins to morning commute.",
      "AQI is Moderate (152) — consider N95 mask for outdoor time.",
      "CBSE board exams start tomorrow — school traffic will be heavy near Sector 16."
    ],
    "tone": "caution"
  }}
}}

Rules:
- Only include items with impact_score >= 4 in the items array (skip irrelevant national news).
- severity: "high" (score 8-10), "medium" (score 5-7), "low" (score 3-4), "info" (score 1-2)
- Keep impact_reason to 1 sentence. Keep action to 1-2 short sentences.
- tone: "alert" if any score >= 8, "caution" if any score >= 5, else "normal"
- Daily briefing should include weather/AQI advice even if not in news items.
- Be specific — mention the user's route, neighborhood, family context where relevant.
- Write in direct, professional tone. No filler phrases.
"""

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text.strip()

    # Extract JSON from response (handle markdown code blocks)
    json_match = re.search(r"\{.*\}", raw, re.DOTALL)
    if json_match:
        raw = json_match.group(0)

    parsed = json.loads(raw)

    # Merge Claude scores back into news items
    score_map = {item["index"]: item for item in parsed.get("items", [])}
    analyzed = []
    for i, item in enumerate(news_items[:30]):
        scored = score_map.get(i)
        if scored and scored.get("impact_score", 0) >= 4:
            analyzed.append({
                **item,
                "impact_score": scored.get("impact_score", 3),
                "severity": scored.get("severity", "low"),
                "impact_reason": scored.get("impact_reason", ""),
                "action": scored.get("action", ""),
                "affects_commute": scored.get("affects_commute", False),
                "affects_family": scored.get("affects_family", False),
            })
        elif not scored:
            # Item not scored by Claude — apply keyword fallback
            analyzed.append(_score_with_keywords(item))

    # Sort by impact score descending
    analyzed.sort(key=lambda x: x.get("impact_score", 0), reverse=True)

    briefing_data = parsed.get("daily_briefing", {})
    briefing = {
        "bullets": briefing_data.get("bullets", []),
        "tone": briefing_data.get("tone", "normal"),
        "generated_at": datetime.now(IST),
    }

    return analyzed, briefing


# ── Keyword-based fallback ────────────────────────────────────────────────────

def _build_action(rule: dict, text: str) -> str:
    """Build a specific action from the rule template."""
    template = rule.get("action_template", "Stay informed.")
    # Pick alt route based on what's blocked
    if "{alt_route}" in template:
        if any(kw in text for kw in ["badarpur", "expressway", "nh-44", "nh44"]):
            template = template.replace("{alt_route}", config.ALT_ROUTES["alt_1"])
        elif any(kw in text for kw in ["mathura road", "south delhi", "ashram"]):
            template = template.replace("{alt_route}", config.ALT_ROUTES["alt_2"])
        else:
            template = template.replace("{alt_route}", config.ALT_ROUTES["alt_1"])
    if "{extra_time}" in template:
        template = template.replace("{extra_time}", "20-30 mins")
    return template


def _build_reason(rule: dict, text: str, item: dict) -> str:
    """Build a specific impact reason."""
    cat = rule["category"]
    matched_kws = [kw for kw in rule["keywords"] if kw in text]
    route_kws = [rk for rk in rule.get("route_keywords", []) if rk in text]

    if "Traffic" in cat:
        location = route_kws[0].title() if route_kws else "your commute route"
        event = matched_kws[0] if matched_kws else "disruption"
        return f"{event.title()} reported near {location} — may affect your Faridabad→Gurugram commute."
    elif "Education" in cat:
        return "Exam/school event — heavy traffic near schools 7-10:30 AM. Your kids' schedule may be affected."
    elif "Weather" in cat:
        event = matched_kws[0] if matched_kws else "weather change"
        return f"{event.title()} expected — will impact your commute and outdoor plans."
    elif "Safety & Utilities" in cat:
        if any(kw in text for kw in ["power", "electricity", "dhbvn"]):
            return "Power disruption in your area — charge devices, water supply may also be affected."
        elif any(kw in text for kw in ["water", "pipeline", "tanker"]):
            return "Water supply disruption — store water before the cutoff time."
        else:
            return "Utility or safety issue in your area."
    elif "Government" in cat:
        if any(kw in text for kw in ["petrol", "diesel", "fuel"]):
            return "Fuel price change — affects your daily commute cost."
        elif any(kw in text for kw in ["toll"]):
            return "Toll change on your expressway route — check FASTag balance."
        else:
            return "Policy change that may affect your daily life."
    else:
        return "News relevant to your area — stay informed."


def _score_with_keywords(item: dict) -> dict:
    """Score a news item using keyword rules. No API required."""
    text = (item.get("title", "") + " " + item.get("summary", "")).lower()

    best_score = 0
    best_reason = ""
    best_action = ""
    affects_commute = False
    affects_family = False
    matched_category = item.get("category", "Local News")
    best_rule = None

    for rule in config.KEYWORD_RULES:
        kw_match = any(kw in text for kw in rule["keywords"])
        if not kw_match:
            continue

        # Weather: require 2+ keyword hits or explicit weather terms
        if rule["category"] == "Weather & Air Quality":
            weather_kw_hits = sum(1 for kw in rule["keywords"] if kw in text)
            has_explicit = any(w in text for w in ["weather alert", "weather warning", "imd", "meteorolog",
                                                     "forecast", "aqi", "air quality", "temperature"])
            if weather_kw_hits < 2 and not has_explicit:
                continue

        route_match = any(rk in text for rk in rule["route_keywords"]) if rule["route_keywords"] else True
        score = rule["base_score"] if route_match else max(rule["base_score"] - 3, 1)

        if score > best_score:
            best_score = score
            best_rule = rule
            matched_category = rule["category"]

            if "Traffic" in rule["category"] or any(kw in text for kw in ["strike", "bandh", "protest"]):
                affects_commute = True
            if "Education" in rule["category"]:
                affects_family = True

    if best_score == 0:
        return {
            **item,
            "impact_score": 2,
            "severity": "info",
            "impact_reason": "General news — not directly affecting your routine.",
            "action": "",
            "affects_commute": False,
            "affects_family": False,
        }

    best_reason = _build_reason(best_rule, text, item)
    best_action = _build_action(best_rule, text)
    severity = "high" if best_score >= 8 else "medium" if best_score >= 5 else "low"

    return {
        **item,
        "category": matched_category,
        "impact_score": best_score,
        "severity": severity,
        "impact_reason": best_reason,
        "action": best_action,
        "affects_commute": affects_commute,
        "affects_family": affects_family,
    }


def _score_all_with_keywords(news_items: list[dict]) -> list[dict]:
    """Apply keyword scoring to all items."""
    scored = [_score_with_keywords(item) for item in news_items]
    scored.sort(key=lambda x: x.get("impact_score", 0), reverse=True)
    return scored


def _build_keyword_briefing(
    scored_items: list[dict],
    weather: dict | None,
    aqi: dict | None,
) -> dict:
    """Build a daily briefing with actionable to-dos from scored items."""
    bullets = []
    todos = []

    # High-impact items → briefing + to-do
    high_items = [i for i in scored_items if i.get("impact_score", 0) >= 7]
    for item in high_items[:3]:
        bullets.append(item["impact_reason"])
        if item.get("action"):
            todos.append(item["action"])

    # Medium items that affect commute → to-do
    commute_items = [i for i in scored_items if i.get("affects_commute") and i.get("impact_score", 0) >= 5]
    for item in commute_items[:2]:
        if item not in high_items:
            todos.append(item.get("action", "Check route before leaving."))

    # Weather
    if weather:
        temp = weather["temp_c"]
        desc = weather["description"]
        bullets.append(f"Weather: {temp}°C, {desc}")
        if weather.get("alerts"):
            bullets.append(f"Weather Alert: {weather['alerts'][0]}")
            todos.append("Check weather before leaving. Carry umbrella if rain.")
        if temp > 42:
            todos.append("Extreme heat — keep water in car, avoid 12-4 PM outdoors.")
        if temp < 5:
            todos.append("Very cold — warm clothes, check for fog on expressway.")

    # AQI
    if aqi:
        aqi_val = aqi["aqi"]
        bullets.append(f"AQI: {aqi_val} ({aqi['level']})")
        if aqi_val > 200:
            todos.append("AQI poor — keep car windows closed. Skip outdoor exercise. Use air purifier.")
        elif aqi_val > 100:
            todos.append("AQI moderate — limit outdoor time for kids.")

    # Day-of-week awareness
    now = datetime.now(IST)
    weekday = now.strftime("%A")
    if weekday == "Friday":
        bullets.append("Friday — expect heavier evening traffic on expressway.")
        todos.append("Leave office by 6:30 PM to beat Friday rush.")
    elif weekday == "Monday":
        bullets.append("Monday — morning traffic typically 15% heavier.")

    if not bullets:
        bullets.append("All clear — no major disruptions for your Faridabad→Gurugram commute today.")

    if not todos:
        todos.append("No special actions needed. Have a smooth day!")

    max_score = max((i.get("impact_score", 0) for i in scored_items), default=0)
    tone = "alert" if max_score >= 8 else "caution" if max_score >= 5 else "normal"

    return {
        "bullets": bullets[:5],
        "todos": todos[:5],
        "tone": tone,
        "generated_at": datetime.now(IST),
    }


# ── Public API ────────────────────────────────────────────────────────────────

def analyze(
    news_items: list[dict],
    profile: dict,
    weather: dict | None = None,
    aqi: dict | None = None,
) -> tuple[list[dict], dict]:
    """
    Analyze news items and build a daily briefing.

    Returns (analyzed_items, briefing).
    Falls back to keyword scoring if no Claude API key or on error.
    """
    user_context = knowledge_base.profile_to_context_string(profile)

    if config.ANTHROPIC_API_KEY:
        try:
            return _analyze_with_claude(news_items, user_context, weather, aqi)
        except Exception as e:
            # Fall through to keyword scoring
            pass

    # Keyword-based fallback
    scored = _score_all_with_keywords(news_items)
    briefing = _build_keyword_briefing(scored, weather, aqi)
    return scored, briefing
