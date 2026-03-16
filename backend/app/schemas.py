from __future__ import annotations

from datetime import datetime, date
from typing import Any, Literal

from pydantic import BaseModel, Field


ProductivityLabel = Literal["productive", "neutral", "distracting", "idle"]


class EventIn(BaseModel):
    started_at: datetime
    ended_at: datetime
    app_name: str = Field(min_length=1)
    window_title: str | None = None
    url: str | None = None
    category: str | None = None
    productivity_label: ProductivityLabel = "neutral"
    notes: str | None = None
    source: str = "agent"


class IdlePeriodIn(BaseModel):
    started_at: datetime
    ended_at: datetime
    reason: str = "idle"


class SettingUpdate(BaseModel):
    key: str
    value: str


class KPI(BaseModel):
    label: str
    value_seconds: int
    display: str


class TopAppItem(BaseModel):
    app_name: str
    seconds: int
    display: str


class TimelineItem(BaseModel):
    started_at: datetime
    ended_at: datetime
    app_name: str
    window_title: str | None = None
    productivity_label: ProductivityLabel


class SessionItem(BaseModel):
    started_at: datetime
    ended_at: datetime
    duration_seconds: int
    summary: str
    top_apps: list[TopAppItem]


class DashboardResponse(BaseModel):
    day: date
    kpis: list[KPI]
    top_apps: list[TopAppItem]
    timeline: list[TimelineItem]
    productivity_breakdown: dict[str, int]
    summary: str


class HistoryResponse(BaseModel):
    day: date
    sessions: list[SessionItem]
    day_summary: str


class SeedResponse(BaseModel):
    inserted_events: int


class SettingsResponse(BaseModel):
    settings: dict[str, str]


class HealthResponse(BaseModel):
    status: str
    app_name: str


class MessageResponse(BaseModel):
    message: str
    detail: dict[str, Any] | None = None


class EditorContextIn(BaseModel):
    captured_at: datetime
    editor_app: str = "VS Code"
    workspace: str | None = None
    active_file: str | None = None
    active_file_path: str | None = None
    language: str | None = None
    open_files: list[str] = []
    terminal_count: int = 0
    git_branch: str | None = None
    debugger_active: bool = False


class EditorContextItem(BaseModel):
    id: int
    captured_at: datetime
    editor_app: str
    workspace: str | None
    active_file: str | None
    active_file_path: str | None
    language: str | None
    open_files: list[str]
    terminal_count: int
    git_branch: str | None
    debugger_active: bool


class BrowserContextIn(BaseModel):
    captured_at: datetime
    browser_app: str
    active_tab_url: str | None = None
    active_tab_title: str | None = None
    active_tab_domain: str | None = None
    tab_count: int = 0
    open_domains: list[str] = []
    youtube_video_title: str | None = None
    youtube_channel: str | None = None
    youtube_is_playing: bool | None = None
    youtube_progress_pct: int | None = None


class BrowserContextItem(BaseModel):
    id: int
    captured_at: datetime
    browser_app: str
    active_tab_url: str | None
    active_tab_title: str | None
    active_tab_domain: str | None
    tab_count: int
    open_domains: list[str]
    youtube_video_title: str | None
    youtube_channel: str | None
    youtube_is_playing: bool | None
    youtube_progress_pct: int | None
    productivity_label: ProductivityLabel = "neutral"
