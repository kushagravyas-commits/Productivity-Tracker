from __future__ import annotations

from datetime import datetime, timedelta

from app.db import get_connection


def seed_demo_events() -> int:
    conn = get_connection()
    cur = conn.cursor()

    now = datetime.now().replace(second=0, microsecond=0)
    base = now.replace(hour=9, minute=0)
    rows = [
        (base.isoformat(), (base + timedelta(minutes=35)).isoformat(), "VS Code", "tracker_service.py", None, "coding", "productive", "API work", "demo"),
        ((base + timedelta(minutes=40)).isoformat(), (base + timedelta(minutes=70)).isoformat(), "Chrome", "Product requirements - Notion", "https://notion.so", "planning", "productive", "Writing scope", "demo"),
        ((base + timedelta(minutes=80)).isoformat(), (base + timedelta(minutes=105)).isoformat(), "Slack", "#product-updates", None, "communication", "neutral", "Team sync", "demo"),
        ((base + timedelta(minutes=120)).isoformat(), (base + timedelta(minutes=165)).isoformat(), "Figma", "Dashboard redesign", None, "design", "productive", "UI pass", "demo"),
        ((base + timedelta(minutes=190)).isoformat(), (base + timedelta(minutes=215)).isoformat(), "YouTube", "Music mix", "https://youtube.com", "break", "distracting", "Break time", "demo"),
        ((base + timedelta(minutes=220)).isoformat(), (base + timedelta(minutes=270)).isoformat(), "Chrome", "Client research", "https://example.com", "research", "productive", "Competitive scan", "demo"),
        ((base + timedelta(minutes=280)).isoformat(), (base + timedelta(minutes=330)).isoformat(), "VS Code", "summary_service.py", None, "coding", "productive", "Summary logic", "demo"),
    ]

    cur.executemany(
        """
        INSERT INTO events (
            started_at, ended_at, app_name, window_title, url, category,
            productivity_label, notes, source
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )

    idle_rows = [
        ((base + timedelta(minutes=70)).isoformat(), (base + timedelta(minutes=80)).isoformat(), "coffee"),
        ((base + timedelta(minutes=165)).isoformat(), (base + timedelta(minutes=185)).isoformat(), "lunch"),
    ]
    cur.executemany(
        "INSERT INTO idle_periods (started_at, ended_at, reason) VALUES (?, ?, ?)",
        idle_rows,
    )

    conn.commit()
    conn.close()
    return len(rows)
