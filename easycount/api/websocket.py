"""WebSocket endpoint — pushes current counts to all connected clients every 500ms."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter(tags=["websocket"])
log = logging.getLogger("easycount.ws")


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: list[WebSocket] = []

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._connections.append(ws)

    def disconnect(self, ws: WebSocket) -> None:
        self._connections.remove(ws)

    async def broadcast(self, data: dict[str, Any]) -> None:
        payload = json.dumps(data, default=str)
        dead: list[WebSocket] = []
        for ws in self._connections:
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._connections.remove(ws)

    @property
    def count(self) -> int:
        return len(self._connections)


manager = ConnectionManager()


@router.websocket("/ws/counts")
async def websocket_counts(ws: WebSocket):
    await manager.connect(ws)
    store = ws.app.state.memory_store
    try:
        while True:
            data = store.get_all()
            await ws.send_text(json.dumps(data, default=str))
            await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        manager.disconnect(ws)
    except Exception as exc:
        log.warning("WebSocket encerrado com erro: %s", exc)
        manager.disconnect(ws)
