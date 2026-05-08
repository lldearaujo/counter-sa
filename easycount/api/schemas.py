"""Pydantic models for API request/response validation."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Stream schemas
# ---------------------------------------------------------------------------

class CountingZone(BaseModel):
    type: str = "line"
    name: str
    points: list[list[float]]
    direction: str = "both"
    track_classes: list[str] | None = None


class StreamCreate(BaseModel):
    stream_id: str
    name: str
    rtsp_url: str
    enabled: bool = True
    cpu_cores: list[int] = Field(default_factory=list)
    counting_zones: list[CountingZone] = Field(default_factory=list)


class StreamStatus(BaseModel):
    stream_id: str
    name: str
    rtsp_url: str
    enabled: bool
    alive: bool
    fps: float
    pid: int | None = None


# ---------------------------------------------------------------------------
# Count schemas
# ---------------------------------------------------------------------------

class DirectionCounts(BaseModel):
    in_: int = Field(0, alias="in")
    out: int = 0

    class Config:
        populate_by_name = True


class ZoneCounts(BaseModel):
    zone_name: str
    counts: dict[str, dict[str, int]]  # {class_name: {"in": N, "out": N}}


class StreamCounts(BaseModel):
    stream_id: str
    fps: float
    online: bool
    zones: dict[str, dict[str, dict[str, int]]]  # {zone: {class: {dir: count}}}


# ---------------------------------------------------------------------------
# History schemas
# ---------------------------------------------------------------------------

class HistoryEntry(BaseModel):
    id: int | None = None
    stream_id: str
    zone_name: str
    class_name: str
    direction: str
    track_id: int | None = None
    occurred_at: datetime


class SnapshotEntry(BaseModel):
    zone_name: str
    class_name: str
    direction: str
    bucket_time: datetime
    count: int


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

class HealthResponse(BaseModel):
    status: str
    streams_active: int
    streams_total: int
    uptime_sec: float
