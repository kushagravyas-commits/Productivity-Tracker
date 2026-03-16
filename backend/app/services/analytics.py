from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from typing import Iterable


def parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value)


def format_seconds(seconds: int) -> str:
    hours, remainder = divmod(max(seconds, 0), 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m"
    return f"{secs}s"


def clamp_duration_seconds(started_at: str, ended_at: str) -> int:
    delta = parse_ts(ended_at) - parse_ts(started_at)
    return max(int(delta.total_seconds()), 0)


def rows_to_dicts(rows: Iterable) -> list[dict]:
    return [dict(row) for row in rows]


def split_by_day(events: list[dict], target_day: date) -> list[dict]:
    result: list[dict] = []
    for event in events:
        started = parse_ts(event["started_at"])
        if started.date() == target_day:
            result.append(event)
    return sorted(result, key=lambda row: row["started_at"])


def summarize_day(events: list[dict], idle_seconds: int) -> str:
    if not events:
        return "No tracked activity for this day yet."

    totals = productivity_totals(events)
    app_totals = top_apps(events)
    lead = app_totals[0][0] if app_totals else "unknown"
    productive_pct = 0
    tracked = sum(totals.values())
    if tracked:
        productive_pct = round((totals["productive"] / tracked) * 100)

    return (
        f"You tracked {format_seconds(tracked)} today. "
        f"Most of the day was spent in {lead}. "
        f"{productive_pct}% of tracked time was productive, and idle time was {format_seconds(idle_seconds)}."
    )


def productivity_totals(events: list[dict]) -> dict[str, int]:
    totals = defaultdict(int)
    for event in events:
        totals[event.get("productivity_label") or "neutral"] += clamp_duration_seconds(
            event["started_at"], event["ended_at"]
        )
    return {
        "productive": totals["productive"],
        "neutral": totals["neutral"],
        "distracting": totals["distracting"],
    }


def top_apps(events: list[dict], limit: int = 5) -> list[tuple[str, int]]:
    counter: Counter[str] = Counter()
    for event in events:
        counter[event["app_name"]] += clamp_duration_seconds(event["started_at"], event["ended_at"])
    return counter.most_common(limit)


def build_productivity_breakdown(events: list[dict], idle_seconds: int) -> dict[str, int]:
    totals = productivity_totals(events)
    return {
        "productive": totals["productive"] // 60,
        "neutral": totals["neutral"] // 60,
        "distracting": totals["distracting"] // 60,
        "idle": idle_seconds // 60,
    }


def build_kpis(events: list[dict], idle_seconds: int) -> list[dict]:
    totals = productivity_totals(events)
    tracked_seconds = sum(totals.values())
    kpis = [
        {"label": "Tracked", "value_seconds": tracked_seconds, "display": format_seconds(tracked_seconds)},
        {
            "label": "Productive",
            "value_seconds": totals["productive"],
            "display": format_seconds(totals["productive"]),
        },
        {"label": "Neutral", "value_seconds": totals["neutral"], "display": format_seconds(totals["neutral"])} ,
        {
            "label": "Distracting",
            "value_seconds": totals["distracting"],
            "display": format_seconds(totals["distracting"]),
        },
        {"label": "Idle", "value_seconds": idle_seconds, "display": format_seconds(idle_seconds)},
    ]
    return kpis


def build_timeline(events: list[dict], idle_periods: list[dict] = None) -> list[dict]:
    if idle_periods is None:
        idle_periods = []
    
    timeline_items = []
    
    for event in events:
        timeline_items.append({
            "started_at": parse_ts(event["started_at"]),
            "ended_at": parse_ts(event["ended_at"]),
            "app_name": event["app_name"],
            "window_title": event.get("window_title"),
            "productivity_label": event.get("productivity_label") or "neutral",
        })
        
    for period in idle_periods:
        timeline_items.append({
            "started_at": parse_ts(period["started_at"]),
            "ended_at": parse_ts(period["ended_at"]),
            "app_name": "Idle",
            "window_title": period.get("reason", "idle"),
            "productivity_label": "idle",
        })

    sorted_items = sorted(timeline_items, key=lambda row: row["started_at"])
    return merge_timeline(sorted_items)


def merge_timeline(items: list[dict]) -> list[dict]:
    if not items:
        return []
    
    merged = []
    current = items[0].copy()
    
    for next_item in items[1:]:
        # Define matching criteria for merging
        same_app = next_item["app_name"] == current["app_name"]
        same_title = next_item["window_title"] == current["window_title"]
        same_label = next_item["productivity_label"] == current["productivity_label"]
        
        # Also check for temporal continuity (small gaps allowed, e.g. < 1 min)
        # However, for simplicity and strictly following "consecutive same app", 
        # we'll merge if they are truly consecutive in the list.
        if same_app and same_title and same_label:
            current["ended_at"] = next_item["ended_at"]
        else:
            merged.append(current)
            current = next_item.copy()
            
    merged.append(current)
    return merged


def build_top_app_items(events: list[dict], limit: int = 5) -> list[dict]:
    return [
        {"app_name": app_name, "seconds": seconds, "display": format_seconds(seconds)}
        for app_name, seconds in top_apps(events, limit=limit)
    ]


def group_sessions(events: list[dict], gap_minutes: int = 15) -> list[list[dict]]:
    if not events:
        return []

    ordered = sorted(events, key=lambda row: row["started_at"])
    sessions: list[list[dict]] = [[ordered[0]]]
    gap = timedelta(minutes=gap_minutes)

    for event in ordered[1:]:
        prev = sessions[-1][-1]
        prev_end = parse_ts(prev["ended_at"])
        current_start = parse_ts(event["started_at"])
        if current_start - prev_end <= gap:
            sessions[-1].append(event)
        else:
            sessions.append([event])
    return sessions


def summarize_session(events: list[dict]) -> str:
    if not events:
        return "No activity in this session."
    top = top_apps(events, limit=2)
    titles = [event.get("window_title") for event in events if event.get("window_title")]
    title_preview = "; ".join(titles[:2]) if titles else "general work"
    apps_part = ", ".join(app for app, _ in top)
    return f"Worked mainly in {apps_part}. Focus areas included {title_preview}."


def build_sessions(events: list[dict]) -> list[dict]:
    sessions = []
    for chunk in group_sessions(events):
        started = parse_ts(chunk[0]["started_at"])
        ended = parse_ts(chunk[-1]["ended_at"])
        duration_seconds = int((ended - started).total_seconds())
        sessions.append(
            {
                "started_at": started,
                "ended_at": ended,
                "duration_seconds": duration_seconds,
                "summary": summarize_session(chunk),
                "top_apps": build_top_app_items(chunk, limit=3),
            }
        )
    return sessions
