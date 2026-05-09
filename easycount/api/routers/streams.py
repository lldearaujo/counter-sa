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


@router.get("/{stream_id}/snapshot/zones")
async def get_snapshot_with_zones(stream_id: str, request: Request):
    """Retorna snapshot com as zonas desenhadas para verificação visual."""
    import cv2, numpy as np
    manager = request.app.state.stream_manager
    cfg = manager.get_config(stream_id)
    if cfg is None:
        raise HTTPException(status_code=404, detail=f"Stream '{stream_id}' não encontrado")

    loop = asyncio.get_event_loop()
    try:
        jpeg_bytes = await asyncio.wait_for(
            loop.run_in_executor(None, _grab_snapshot_sync, cfg["rtsp_url"]),
            timeout=12.0,
        )
    except (asyncio.TimeoutError, RuntimeError) as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    # Decode, draw zones, re-encode
    img = cv2.imdecode(np.frombuffer(jpeg_bytes, np.uint8), cv2.IMREAD_COLOR)
    colors = [(255, 80, 80), (80, 255, 80), (80, 80, 255), (255, 255, 80)]
    for i, zone in enumerate(cfg.get("counting_zones", [])):
        pts = zone.get("points", [])
        color = colors[i % len(colors)]
        if zone.get("type", "line") == "line" and len(pts) >= 2:
            p1 = (int(pts[0][0]), int(pts[0][1]))
            p2 = (int(pts[1][0]), int(pts[1][1]))
            cv2.line(img, p1, p2, color, 4)
            cv2.circle(img, p1, 10, color, -1)
            cv2.circle(img, p2, 10, color, -1)
            mid = ((p1[0]+p2[0])//2, (p1[1]+p2[1])//2)
            cv2.putText(img, zone.get("name", f"zona_{i+1}"), (mid[0]+8, mid[1]-8),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.2, color, 3)
        elif len(pts) >= 3:
            poly = np.array([[int(p[0]), int(p[1])] for p in pts], np.int32)
            cv2.polylines(img, [poly], True, color, 4)

    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 85])
    if not ok:
        raise HTTPException(status_code=500, detail="Falha ao codificar imagem")
    return Response(content=buf.tobytes(), media_type="image/jpeg")
