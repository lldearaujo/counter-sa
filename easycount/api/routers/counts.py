"""GET /api/counts endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/api/counts", tags=["counts"])


@router.get("")
async def get_all_counts(request: Request):
    store = request.app.state.memory_store
    return store.get_all()


@router.get("/{stream_id}")
async def get_stream_counts(stream_id: str, request: Request):
    store = request.app.state.memory_store
    data = store.get_stream(stream_id)
    if data is None:
        raise HTTPException(status_code=404, detail=f"Stream '{stream_id}' não encontrado")
    return data


@router.post("/{stream_id}/reset")
async def reset_counts(stream_id: str, request: Request):
    store = request.app.state.memory_store
    store.reset_counts(stream_id)
    return {"ok": True, "stream_id": stream_id}
