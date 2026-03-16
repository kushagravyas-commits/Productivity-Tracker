"""Simple stub agent.

This is NOT a real OS-level active window tracker.
It just rotates through sample events and posts them to the FastAPI backend.
Replace `sample_events` with real active-window capture logic later.
"""
from __future__ import annotations

import json
import time
import urllib.request
from datetime import datetime, timedelta

API_URL = "http://127.0.0.1:8000/api/v1/events"
INTERVAL_SECONDS = 10

sample_events = [
    {"app_name": "VS Code", "window_title": "backend/app/main.py", "category": "coding", "productivity_label": "productive"},
    {"app_name": "Chrome", "window_title": "PRD - Notion", "category": "planning", "productivity_label": "productive"},
    {"app_name": "Slack", "window_title": "#eng-team", "category": "communication", "productivity_label": "neutral"},
    {"app_name": "YouTube", "window_title": "Music playlist", "category": "break", "productivity_label": "distracting"},
]


def post_event(event: dict) -> None:
    started_at = datetime.now().replace(microsecond=0)
    ended_at = started_at + timedelta(seconds=INTERVAL_SECONDS)
    payload = {
        **event,
        "started_at": started_at.isoformat(),
        "ended_at": ended_at.isoformat(),
        "notes": "collector_stub",
        "source": "collector_stub",
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(API_URL, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as response:
        print(response.read().decode("utf-8"))

if __name__ == "__main__":
    idx = 0
    print("Starting stub collector. Press Ctrl+C to stop.")
    while True:
        post_event(sample_events[idx % len(sample_events)])
        idx += 1
        time.sleep(INTERVAL_SECONDS)
