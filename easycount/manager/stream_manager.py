"""Spawns, monitors, and restarts StreamWorker processes."""

from __future__ import annotations

import multiprocessing as mp
import time
from pathlib import Path
from typing import Any

import yaml

from easycount.core.stream_worker import StreamWorker
from easycount.utils.logging import setup_logging

log = setup_logging()


class StreamManager:
    def __init__(
        self,
        streams_dir: str,
        app_config: dict[str, Any],
        result_queue: mp.Queue,
        restart_backoff: float = 5.0,
    ) -> None:
        self._streams_dir = Path(streams_dir)
        self._app_config = app_config
        self._result_queue = result_queue
        self._restart_backoff = restart_backoff

        self._workers: dict[str, StreamWorker] = {}
        self._stream_configs: dict[str, dict[str, Any]] = {}
        self._running = False

    def load_streams(self) -> None:
        """Load all enabled stream configs from YAML files."""
        for path in self._streams_dir.glob("*.yaml"):
            if path.name.startswith("_"):
                continue
            try:
                cfg = yaml.safe_load(path.read_text(encoding="utf-8"))
                if cfg.get("enabled", True):
                    sid = cfg["stream_id"]
                    self._stream_configs[sid] = cfg
                    log.info("Stream carregado: %s (%s)", sid, cfg.get("name"))
            except Exception as exc:
                log.error("Erro ao carregar %s: %s", path, exc)

    def start(self) -> None:
        self._running = True
        self.load_streams()
        for sid, cfg in self._stream_configs.items():
            self._spawn(sid, cfg)

    def stop(self) -> None:
        self._running = False
        for sid, worker in list(self._workers.items()):
            self._kill(sid, worker)

    def add_stream(self, cfg: dict[str, Any]) -> None:
        sid = cfg["stream_id"]
        self._stream_configs[sid] = cfg
        self._write_yaml(sid, cfg)
        self._spawn(sid, cfg)

    def remove_stream(self, stream_id: str) -> bool:
        if stream_id not in self._workers:
            return False
        self._kill(stream_id, self._workers[stream_id])
        self._stream_configs.pop(stream_id, None)
        self._delete_yaml(stream_id)
        return True

    def update_stream(self, stream_id: str, cfg: dict[str, Any]) -> None:
        if stream_id in self._workers:
            self._kill(stream_id, self._workers[stream_id])
        self._stream_configs[stream_id] = cfg
        self._write_yaml(stream_id, cfg)
        self._spawn(stream_id, cfg)

    def get_config(self, stream_id: str) -> dict[str, Any] | None:
        cfg = self._stream_configs.get(stream_id)
        return dict(cfg) if cfg else None

    def get_status(self) -> dict[str, dict[str, Any]]:
        status = {}
        for sid, worker in self._workers.items():
            status[sid] = {
                "alive": worker.is_alive(),
                "pid": worker.pid,
                "name": self._stream_configs.get(sid, {}).get("name", sid),
            }
        return status

    def health_check(self) -> None:
        """Call periodically to restart dead workers."""
        if not self._running:
            return
        for sid, worker in list(self._workers.items()):
            if not worker.is_alive():
                log.warning("Worker %s morto — reiniciando em %ss", sid, self._restart_backoff)
                time.sleep(self._restart_backoff)
                cfg = self._stream_configs.get(sid)
                if cfg:
                    self._spawn(sid, cfg)

    def _spawn(self, sid: str, cfg: dict[str, Any]) -> None:
        worker = StreamWorker(
            stream_config=cfg,
            app_config=self._app_config,
            result_queue=self._result_queue,
        )
        worker.start()
        self._workers[sid] = worker
        log.info("Worker spawned: %s (pid=%s)", sid, worker.pid)

    def _kill(self, sid: str, worker: StreamWorker) -> None:
        worker.stop()
        worker.join(timeout=5.0)
        if worker.is_alive():
            worker.kill()
        self._workers.pop(sid, None)
        log.info("Worker encerrado: %s", sid)

    def _write_yaml(self, stream_id: str, cfg: dict[str, Any]) -> None:
        path = self._streams_dir / f"{stream_id}.yaml"
        path.write_text(
            yaml.dump(cfg, allow_unicode=True, default_flow_style=False),
            encoding="utf-8",
        )
        log.info("YAML salvo: %s", path)

    def _delete_yaml(self, stream_id: str) -> None:
        path = self._streams_dir / f"{stream_id}.yaml"
        if path.exists():
            path.unlink()
            log.info("YAML removido: %s", path)
