"""CRUD endpoints for stream management."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response

from easycount.api.schemas import StreamCreate
from easycount.storage import database as db

router = APIRouter(prefix="/api/streams", tags=["streams"])


# ---------------------------------------------------------------------------
# Snapshot helpers (sync — run in executor to not block event loop)
# ---------------------------------------------------------------------------

def _grab_snapshot_sync(rtsp_url: str) -> bytes:
    import cv2
    cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    try:
        if not cap.isOpened():
            raise RuntimeError("Não foi possível abrir o stream")
        frame = None
        for _ in range(5):
            ret, f = cap.read()
            if ret:
                frame = f
        if frame is None:
            raise RuntimeError("Nenhum frame disponível")
        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
        if not ok:
            raise RuntimeError("Falha ao codificar JPEG")
        return buf.tobytes()
    finally:
        cap.release()


async def _snapshot_response(rtsp_url: str) -> Response:
    loop = asyncio.get_event_loop()
    try:
        jpeg = await asyncio.wait_for(
            loop.run_in_executor(None, _grab_snapshot_sync, rtsp_url),
            timeout=12.0,
        )
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Timeout ao capturar frame do stream")
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return Response(content=jpeg, media_type="image/jpeg")


# ---------------------------------------------------------------------------
# IMPORTANT: static path segments must come before /{stream_id} parametric routes
# ---------------------------------------------------------------------------

@router.get("/snapshot/preview")
async def snapshot_preview(rtsp_url: str = Query(..., description="URL RTSP completa")):
    """Captura um frame de uma URL RTSP (sem precisar salvar o stream)."""
    return await _snapshot_response(rtsp_url)


# ---------------------------------------------------------------------------
# List / Create
# ---------------------------------------------------------------------------

@router.get("")
async def list_streams(request: Request):
    manager = request.app.state.stream_manager
    store = request.app.state.memory_store
    worker_status = manager.get_status()
    all_data = store.get_all()

    streams = []
    for sid, status in worker_status.items():
        stream_data = all_data.get(sid, {})
        cfg = manager.get_config(sid) or {}
        streams.append({
            "stream_id": sid,
            "name": status.get("name", sid),
            "rtsp_url": cfg.get("rtsp_url", ""),
            "enabled": cfg.get("enabled", True),
            "cpu_cores": cfg.get("cpu_cores", []),
            "counting_zones": cfg.get("counting_zones", []),
            "alive": status.get("alive", False),
            "pid": status.get("pid"),
            "fps": stream_data.get("fps", 0.0),
            "online": stream_data.get("online", False),
        })
    return streams


@router.post("", status_code=201)
async def create_stream(body: StreamCreate, request: Request):
    cfg = body.model_dump()
    cfg["counting_zones"] = [z.model_dump() for z in body.counting_zones]

    manager = request.app.state.stream_manager
    manager.add_stream(cfg)
    await db.upsert_stream(cfg)
    return {"ok": True, "stream_id": body.stream_id}


# ---------------------------------------------------------------------------
# Get / Update / Delete single stream
# ---------------------------------------------------------------------------

@router.get("/{stream_id}")
async def get_stream(stream_id: str, request: Request):
    manager = request.app.state.stream_manager
    cfg = manager.get_config(stream_id)
    if cfg is None:
        raise HTTPException(status_code=404, detail=f"Stream '{stream_id}' não encontrado")
    return cfg


@router.put("/{stream_id}")
async def update_stream(stream_id: str, body: StreamCreate, request: Request):
    manager = request.app.state.stream_manager
    if manager.get_config(stream_id) is None:
        raise HTTPException(status_code=404, detail=f"Stream '{stream_id}' não encontrado")

    cfg = body.model_dump()
    cfg["stream_id"] = stream_id  # path param wins
    cfg["counting_zones"] = [z.model_dump() for z in body.counting_zones]

    manager.update_stream(stream_id, cfg)
    await db.upsert_stream(cfg)
    return {"ok": True, "stream_id": stream_id}


@router.delete("/{stream_id}")
async def delete_stream(stream_id: str, request: Request):
    manager = request.app.state.stream_manager
    removed = manager.remove_stream(stream_id)
    if not removed:
        raise HTTPException(status_code=404, detail=f"Stream '{stream_id}' não encontrado")
    request.app.state.memory_store.remove(stream_id)
    await db.delete_stream(stream_id)
    return {"ok": True, "stream_id": stream_id}


@router.get("/{stream_id}/snapshot")
async def get_stream_snapshot(stream_id: str, request: Request):
    """Captura um frame ao vivo do stream já configurado."""
    manager = request.app.state.stream_manager
    cfg = manager.get_config(stream_id)
    if cfg is None:
        raise HTTPException(status_code=404, detail=f"Stream '{stream_id}' não encontrado")
    return await _snapshot_response(cfg["rtsp_url"])
