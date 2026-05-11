"""FastAPI application factory with lifespan events."""

from __future__ import annotations

import asyncio
import multiprocessing as mp
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import yaml
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from easycount.api.routers import counts, history, streams
from easycount.api.websocket import router as ws_router
from easycount.manager.aggregator import Aggregator
from easycount.manager.stream_manager import StreamManager
from easycount.storage import database as db
from easycount.storage.memory_store import MemoryStore
from easycount.utils.logging import setup_logging

log = setup_logging()

_start_time = time.monotonic()


def load_app_config(config_path: str = "config/settings.yaml") -> dict[str, Any]:
    return yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    from pydantic_settings import BaseSettings, SettingsConfigDict

    class Settings(BaseSettings):
        model_config = SettingsConfigDict(env_file=".env", extra="ignore")

        database_url: str = "postgresql+asyncpg://easycount:easycount@localhost:5432/easycount"
        app_log_level: str = "INFO"
        config_path: str = "config/settings.yaml"
        streams_dir: str = "config/streams"

    settings = Settings()
    app_config = load_app_config(settings.config_path)
    db_cfg = app_config.get("database", {})

    # Init PostgreSQL
    await db.init_db(
        settings.database_url,
        pool_min=db_cfg.get("pool_min_size", 2),
        pool_max=db_cfg.get("pool_max_size", 10),
    )

    memory_store = MemoryStore()
    result_queue: mp.Queue = mp.Queue(maxsize=500)

    # Aggregator runs in a thread inside the main process
    loop = asyncio.get_event_loop()
    snapshot_interval = db_cfg.get("snapshot_interval_sec", 60)

    async def on_events(events: list[dict]) -> None:
        try:
            await db.insert_crossing_events(events)
        except Exception as exc:
            log.error("Erro ao salvar eventos no DB: %s", exc)

    aggregator = Aggregator(
        result_queue=result_queue,
        memory_store=memory_store,
        event_callback=on_events,
        loop=loop,
    )
    aggregator.start()

    # Periodic snapshot writer task
    async def snapshot_task():
        while True:
            await asyncio.sleep(snapshot_interval)
            all_data = memory_store.get_all()
            for sid, data in all_data.items():
                counts_data = data.get("counts", {})
                if counts_data:
                    try:
                        await db.upsert_snapshots(sid, counts_data)
                    except Exception as exc:
                        log.error("Erro ao salvar snapshot %s: %s", sid, exc)

    snapshot_bg = asyncio.create_task(snapshot_task())

    stream_manager = StreamManager(
        streams_dir=settings.streams_dir,
        app_config=app_config,
        result_queue=result_queue,
    )
    stream_manager.start()

    # Health check task — restarts dead workers
    async def health_task():
        while True:
            await asyncio.sleep(10)
            stream_manager.health_check()

    health_bg = asyncio.create_task(health_task())

    app.state.memory_store = memory_store
    app.state.stream_manager = stream_manager
    app.state.aggregator = aggregator
    app.state.app_config = app_config
    app.state.start_time = _start_time

    log.info("EasyCount iniciado")
    yield

    # Shutdown
    health_bg.cancel()
    snapshot_bg.cancel()
    stream_manager.stop()
    aggregator.stop()
    await db.close_db()
    log.info("EasyCount encerrado")


def create_app() -> FastAPI:
    app = FastAPI(
        title="EasyCount",
        description="Vehicle and pedestrian counting from RTSP streams",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.include_router(counts.router)
    app.include_router(streams.router)
    app.include_router(history.router)
    app.include_router(ws_router)

    @app.get("/api/health")
    async def health(request: Request):
        manager = request.app.state.stream_manager
        status = manager.get_status()
        active = sum(1 for s in status.values() if s.get("alive"))
        return {
            "status": "ok",
            "streams_active": active,
            "streams_total": len(status),
            "uptime_sec": round(time.monotonic() - request.app.state.start_time, 1),
        }

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception):
        log.error("Unhandled exception: %s", exc, exc_info=True)
        return JSONResponse(status_code=500, content={"detail": "Erro interno do servidor"})

    @app.get("/config", include_in_schema=False)
    async def config_page():
        return FileResponse(str(Path("frontend") / "config.html"))

    # Frontend deve ser montado POR ÚLTIMO — StaticFiles em "/" captura tudo
    frontend_dir = Path("frontend")
    if frontend_dir.exists():
        app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")

    return app
