"""PostgreSQL async operations via asyncpg + SQLAlchemy 2.0."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker | None = None


async def init_db(database_url: str, pool_min: int = 2, pool_max: int = 10) -> None:
    global _engine, _session_factory

    # asyncpg não aceita sslmode= na URL (é parâmetro do psycopg2).
    # Detecta e converte para connect_args={"ssl": False}.
    connect_args: dict = {}
    if "sslmode=disable" in database_url:
        database_url = database_url.split("?")[0]
        connect_args["ssl"] = False
    elif "ssl=false" in database_url.lower():
        database_url = database_url.split("?")[0]
        connect_args["ssl"] = False

    _engine = create_async_engine(
        database_url,
        pool_size=pool_min,
        max_overflow=pool_max - pool_min,
        pool_pre_ping=True,
        echo=False,
        connect_args=connect_args,
    )
    _session_factory = async_sessionmaker(_engine, expire_on_commit=False)


async def close_db() -> None:
    if _engine:
        await _engine.dispose()


def get_session() -> AsyncSession:
    if _session_factory is None:
        raise RuntimeError("DB não inicializado. Chame init_db() primeiro.")
    return _session_factory()


# ---------------------------------------------------------------------------
# Stream config persistence
# ---------------------------------------------------------------------------

async def upsert_stream(cfg: dict[str, Any]) -> None:
    async with get_session() as s:
        await s.execute(
            text("""
                INSERT INTO streams (id, name, rtsp_url, enabled, config_json, updated_at)
                VALUES (:id, :name, :url, :enabled, CAST(:cfg AS jsonb), NOW())
                ON CONFLICT (id) DO UPDATE SET
                    name       = EXCLUDED.name,
                    rtsp_url   = EXCLUDED.rtsp_url,
                    enabled    = EXCLUDED.enabled,
                    config_json= EXCLUDED.config_json,
                    updated_at = NOW()
            """),
            {
                "id": cfg["stream_id"],
                "name": cfg.get("name", cfg["stream_id"]),
                "url": cfg["rtsp_url"],
                "enabled": cfg.get("enabled", True),
                "cfg": __import__("json").dumps(cfg),
            },
        )
        await s.commit()


async def get_all_streams() -> list[dict[str, Any]]:
    async with get_session() as s:
        result = await s.execute(text("SELECT id, name, rtsp_url, enabled, config_json FROM streams"))
        return [dict(row._mapping) for row in result]


async def delete_stream(stream_id: str) -> None:
    async with get_session() as s:
        await s.execute(text("DELETE FROM streams WHERE id = :id"), {"id": stream_id})
        await s.commit()


# ---------------------------------------------------------------------------
# Crossing events
# ---------------------------------------------------------------------------

async def insert_crossing_events(events: list[dict[str, Any]]) -> None:
    if not events:
        return
    async with get_session() as s:
        for ev in events:
            await s.execute(
                text("""
                    INSERT INTO crossing_events
                        (stream_id, zone_name, class_name, direction, track_id, occurred_at)
                    VALUES (:sid, :zone, :cls, :dir, :tid, NOW())
                """),
                {
                    "sid": ev["stream_id"],
                    "zone": ev["zone_name"],
                    "cls": ev["class_name"],
                    "dir": ev["direction"],
                    "tid": ev["track_id"],
                },
            )
        await s.commit()


async def query_history(
    stream_id: str,
    from_dt: datetime | None = None,
    to_dt: datetime | None = None,
    class_name: str | None = None,
    limit: int = 1000,
) -> list[dict[str, Any]]:
    conditions = ["stream_id = :sid"]
    params: dict[str, Any] = {"sid": stream_id, "limit": limit}

    if from_dt:
        conditions.append("occurred_at >= :from_dt")
        params["from_dt"] = from_dt
    if to_dt:
        conditions.append("occurred_at <= :to_dt")
        params["to_dt"] = to_dt
    if class_name:
        conditions.append("class_name = :cls")
        params["cls"] = class_name

    where = " AND ".join(conditions)
    sql = f"""
        SELECT id, stream_id, zone_name, class_name, direction, track_id, occurred_at
        FROM crossing_events
        WHERE {where}
        ORDER BY occurred_at DESC
        LIMIT :limit
    """
    async with get_session() as s:
        result = await s.execute(text(sql), params)
        return [dict(row._mapping) for row in result]


# ---------------------------------------------------------------------------
# Count snapshots (aggregated, written periodically)
# ---------------------------------------------------------------------------

async def upsert_snapshots(stream_id: str, counts: dict[str, Any]) -> None:
    """
    Upsert aggregated counts into count_snapshots for the current minute bucket.
    counts: {zone_name: {class_name: {"in": N, "out": N}}}
    """
    bucket = datetime.now(tz=timezone.utc).replace(second=0, microsecond=0)
    async with get_session() as s:
        for zone_name, class_counts in counts.items():
            for class_name, dirs in class_counts.items():
                for direction, count in dirs.items():
                    await s.execute(
                        text("""
                            INSERT INTO count_snapshots
                                (stream_id, zone_name, class_name, direction, bucket_time, count)
                            VALUES (:sid, :zone, :cls, :dir, :bucket, :count)
                            ON CONFLICT (stream_id, zone_name, class_name, direction, bucket_time)
                            DO UPDATE SET count = EXCLUDED.count
                        """),
                        {
                            "sid": stream_id,
                            "zone": zone_name,
                            "cls": class_name,
                            "dir": direction,
                            "bucket": bucket,
                            "count": count,
                        },
                    )
        await s.commit()


async def query_snapshots(
    stream_id: str,
    from_dt: datetime | None = None,
    to_dt: datetime | None = None,
    class_name: str | None = None,
) -> list[dict[str, Any]]:
    conditions = ["stream_id = :sid"]
    params: dict[str, Any] = {"sid": stream_id}

    if from_dt:
        conditions.append("bucket_time >= :from_dt")
        params["from_dt"] = from_dt
    if to_dt:
        conditions.append("bucket_time <= :to_dt")
        params["to_dt"] = to_dt
    if class_name:
        conditions.append("class_name = :cls")
        params["cls"] = class_name

    where = " AND ".join(conditions)
    sql = f"""
        SELECT zone_name, class_name, direction, bucket_time, count
        FROM count_snapshots
        WHERE {where}
        ORDER BY bucket_time DESC
        LIMIT 10000
    """
    async with get_session() as s:
        result = await s.execute(text(sql), params)
        return [dict(row._mapping) for row in result]
