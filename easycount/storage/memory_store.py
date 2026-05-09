"""In-memory store for real-time count state. Thread-safe via threading.Lock."""

from __future__ import annotations

import threading
from typing import Any


class MemoryStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        # {stream_id: {"counts": {...}, "fps": float, "online": bool}}
        self._data: dict[str, dict[str, Any]] = {}

    _MAX_RECENT = 30

    def update_counts(self, stream_id: str, counts: dict[str, Any]) -> None:
        with self._lock:
            entry = self._data.setdefault(stream_id, {"counts": {}, "fps": 0.0, "online": False, "recent_events": []})
            entry["counts"] = counts
            entry["online"] = True

    def add_event(self, stream_id: str, event: dict[str, Any]) -> None:
        with self._lock:
            entry = self._data.setdefault(stream_id, {"counts": {}, "fps": 0.0, "online": False, "recent_events": []})
            recent = entry.setdefault("recent_events", [])
            recent.append(event)
            if len(recent) > self._MAX_RECENT:
                recent.pop(0)

    def update_fps(self, stream_id: str, fps: float) -> None:
        with self._lock:
            self._data.setdefault(stream_id, {"counts": {}, "fps": 0.0, "online": False})
            self._data[stream_id]["fps"] = fps

    def mark_offline(self, stream_id: str) -> None:
        with self._lock:
            if stream_id in self._data:
                self._data[stream_id]["online"] = False

    def get_stream(self, stream_id: str) -> dict[str, Any] | None:
        with self._lock:
            return dict(self._data.get(stream_id, {}))

    def get_all(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            return {sid: dict(v) for sid, v in self._data.items()}

    def reset_counts(self, stream_id: str) -> None:
        with self._lock:
            if stream_id in self._data:
                self._data[stream_id]["counts"] = {}

    def remove(self, stream_id: str) -> None:
        with self._lock:
            self._data.pop(stream_id, None)
