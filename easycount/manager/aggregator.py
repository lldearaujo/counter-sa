"""Drains the result_queue and updates MemoryStore + triggers DB writes."""

from __future__ import annotations

import asyncio
import multiprocessing as mp
import threading
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Callable

from easycount.utils.logging import setup_logging

if TYPE_CHECKING:
    from easycount.storage.memory_store import MemoryStore

log = setup_logging()


class Aggregator(threading.Thread):
    """
    Runs in the main process as a background thread.
    Reads result dicts from result_queue and updates MemoryStore.
    Fires an async callback for DB writes when crossing events are present.
    """

    def __init__(
        self,
        result_queue: mp.Queue,
        memory_store: "MemoryStore",
        event_callback: Callable[[list[dict[str, Any]]], None] | None = None,
        loop: asyncio.AbstractEventLoop | None = None,
    ) -> None:
        super().__init__(daemon=True, name="aggregator")
        self._queue = result_queue
        self._store = memory_store
        self._event_callback = event_callback
        self._loop = loop
        self._stop_event = threading.Event()

    def run(self) -> None:
        log.info("Aggregator iniciado")
        while not self._stop_event.is_set():
            try:
                result = self._queue.get(timeout=0.1)
                self._process(result)
            except Exception:
                pass  # queue.Empty é esperado — timeout normal

    def _process(self, result: dict[str, Any]) -> None:
        from datetime import datetime, timezone
        sid = result["stream_id"]
        self._store.update_counts(
            sid,
            result.get("counts", {}),
            det_count=result.get("det_count", 0),
            track_count=result.get("track_count", 0),
        )
        self._store.update_fps(sid, result.get("fps", 0.0))

        events = result.get("events", [])
        if events:
            now = datetime.now(tz=timezone.utc).isoformat()
            enriched = [{**ev, "stream_id": sid, "occurred_at": now} for ev in events]
            for ev in enriched:
                self._store.add_event(sid, ev)
            if self._event_callback and self._loop:
                asyncio.run_coroutine_threadsafe(
                    self._async_callback(enriched),
                    self._loop,
                )

    async def _async_callback(self, events: list[dict[str, Any]]) -> None:
        try:
            await self._event_callback(events)
        except Exception as exc:
            log.error("Erro no callback de eventos: %s", exc)

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def set_event_callback(self, cb: Callable) -> None:
        self._event_callback = cb

    def stop(self) -> None:
        self._stop_event.set()
