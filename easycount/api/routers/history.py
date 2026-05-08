"""History and snapshot query endpoints."""

from __future__ import annotations

import csv
import io
from datetime import datetime

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse

from easycount.storage import database as db

router = APIRouter(prefix="/api/history", tags=["history"])


@router.get("/{stream_id}")
async def get_history(
    stream_id: str,
    from_dt: datetime | None = Query(None, alias="from"),
    to_dt: datetime | None = Query(None, alias="to"),
    class_name: str | None = Query(None, alias="class"),
    limit: int = Query(1000, le=10000),
):
    rows = await db.query_history(stream_id, from_dt, to_dt, class_name, limit)
    return rows


@router.get("/{stream_id}/snapshots")
async def get_snapshots(
    stream_id: str,
    from_dt: datetime | None = Query(None, alias="from"),
    to_dt: datetime | None = Query(None, alias="to"),
    class_name: str | None = Query(None, alias="class"),
):
    rows = await db.query_snapshots(stream_id, from_dt, to_dt, class_name)
    return rows


@router.get("/{stream_id}/export")
async def export_history(
    stream_id: str,
    from_dt: datetime | None = Query(None, alias="from"),
    to_dt: datetime | None = Query(None, alias="to"),
    class_name: str | None = Query(None, alias="class"),
    format: str = Query("csv"),
):
    rows = await db.query_history(stream_id, from_dt, to_dt, class_name, limit=100_000)

    if format != "csv":
        return rows

    output = io.StringIO()
    if rows:
        writer = csv.DictWriter(output, fieldnames=rows[0].keys())
        writer.writeheader()
        for row in rows:
            writer.writerow({k: str(v) for k, v in row.items()})

    output.seek(0)
    filename = f"easycount_{stream_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        iter([output.read()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
