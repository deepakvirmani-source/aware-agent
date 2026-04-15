"""
knowledge_base.py — Loads and manages the user's personal context.
Reads user_profile.yaml and provides helper methods for the analyzer.
"""

from __future__ import annotations

import yaml
from pathlib import Path
from typing import Any

import config


def load_profile(path: str | None = None) -> dict[str, Any]:
    """Load the user profile from YAML. Returns a dict."""
    profile_path = Path(path or config.USER_PROFILE_PATH)
    if not profile_path.exists():
        return _default_profile()
    with open(profile_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data


def save_profile(profile: dict[str, Any], path: str | None = None) -> None:
    """Save the user profile to YAML."""
    profile_path = Path(path or config.USER_PROFILE_PATH)
    with open(profile_path, "w", encoding="utf-8") as f:
        yaml.dump(profile, f, default_flow_style=False, allow_unicode=True)


def _default_profile() -> dict[str, Any]:
    return {
        "name": "User",
        "location": {
            "city": "Faridabad",
            "state": "Haryana",
            "country": "India",
            "pin_code": "121001",
            "neighborhood": "Sector 16",
        },
        "commute": {
            "works_in": "Noida",
            "mode": "car",
            "route": "Faridabad → Badarpur Border → Noida via NH-44",
            "typical_time": "45 mins",
        },
        "nearby_areas": ["Delhi NCR", "Noida", "Gurugram"],
        "interests": ["traffic updates", "weather alerts", "air quality (AQI)"],
        "family": {"has_school_children": True, "school_board": "CBSE"},
    }


def profile_to_context_string(profile: dict[str, Any]) -> str:
    """Convert profile to a detailed context string for the LLM."""
    name = profile.get("name", "the user")
    loc = profile.get("location", {})
    work = profile.get("work", {})
    commute = profile.get("commute", {})
    nearby = profile.get("nearby_areas", [])
    interests = profile.get("interests", [])
    family = profile.get("family", {})
    routine = profile.get("daily_routine", {})
    health = profile.get("health", {})
    home = profile.get("home", {})
    vehicle = profile.get("vehicle", {})
    proactive = profile.get("proactive_rules", [])

    lines = [
        f"User: {name}",
        f"Lives in: {loc.get('neighborhood', 'Sector 16')}, {loc.get('city', 'Faridabad')}, {loc.get('state', 'Haryana')}",
        f"Works at: {work.get('company', '')} in {work.get('works_in', commute.get('works_in', 'Gurugram'))} ({work.get('office_area', '')})",
        f"Work hours: {work.get('work_hours', '10 AM - 7 PM')}, {work.get('work_days', 'Mon-Fri')}",
        f"Flexible hours: {'Yes' if work.get('flexible_hours') else 'No'}",
        "",
        "COMMUTE:",
        f"  Mode: {commute.get('mode', 'car')}",
        f"  Primary route: {commute.get('route_primary', 'Faridabad → Badarpur → FG Expressway → Gurugram')}",
        f"  Alt route 1: {commute.get('route_alt_1', '')}",
        f"  Alt route 2: {commute.get('route_alt_2', '')}",
        f"  Key junctions: {', '.join(commute.get('key_junctions', []))}",
        f"  Typical time: {commute.get('typical_time', '50 mins')} | Worst: {commute.get('worst_case_time', '2 hours')}",
        f"  Leaves home: {commute.get('leave_home_by', '9:00 AM')} | Returns: {commute.get('return_home_by', '7:30 PM')}",
        f"  Uses toll expressway: {'Yes' if commute.get('toll_route') else 'No'}",
        "",
        f"Nearby areas: {', '.join(nearby)}",
    ]

    if family.get("has_school_children"):
        lines.append(f"Kids: {family.get('school_board', 'CBSE')} board, school in {family.get('school_area', 'Faridabad')}, timing {family.get('school_timing', '7:30 AM - 2 PM')}")

    if routine:
        lines.append(f"Daily routine: wake {routine.get('wake_up', '7 AM')}, leave {routine.get('leave_home', '9 AM')}, exercise: {routine.get('exercise_type', 'outdoor')} in {routine.get('exercise', 'morning')}")

    if health.get("sensitive_to_aqi"):
        lines.append(f"Health: Sensitive to AQI — alert when AQI > {health.get('aqi_threshold', 200)}")

    if home:
        lines.append(f"Home: Power by {home.get('power_company', 'DHBVN')}, water: {home.get('water_source', 'municipal')}")

    if vehicle:
        lines.append(f"Vehicle: {vehicle.get('type', 'car')}, {vehicle.get('fuel', 'petrol')}, FASTag: {'Yes' if vehicle.get('fastag') else 'No'}")

    lines.append(f"\nInterests: {', '.join(interests)}")

    if proactive:
        lines.append("\nPROACTIVE RULES (generate to-dos based on these):")
        for rule in proactive:
            lines.append(f"  - {rule}")

    return "\n".join(lines)


def get_route_keywords(profile: dict[str, Any]) -> list[str]:
    """Return keywords derived from the user's route and location."""
    keywords = []
    loc = profile.get("location", {})
    commute = profile.get("commute", {})
    nearby = profile.get("nearby_areas", [])

    for field in [loc.get("city"), loc.get("state"), loc.get("neighborhood"),
                  commute.get("works_in")]:
        if field:
            keywords.append(field.lower())

    # Parse route for road names / landmarks
    route = commute.get("route", "")
    for token in route.replace("→", " ").replace(",", " ").split():
        if len(token) > 3:
            keywords.append(token.lower())

    for area in nearby:
        keywords.append(area.lower())

    # Hardcoded route-specific keywords
    keywords += ["nh-44", "nh44", "badarpur", "mathura road", "kalindi kunj",
                 "faridabad", "noida", "delhi", "haryana", "ncr"]

    return list(set(keywords))
