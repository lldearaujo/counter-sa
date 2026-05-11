"""Worker process: owns the full capture → detect → track → count pipeline for one stream."""

from __future__ import annotations

import multiprocessing as mp
import time
from collections import deque
from typing import Any

import psutil

from easycount.core.capturer import Capturer
from easycount.core.counter import Counter
from easycount.core.detector import Detector
from easycount.core.tracker import Tracker
from easycount.utils.logging import setup_logging


class StreamWorker(mp.Process):
    """
    Runs as a separate process, isolating ONNX Runtime inference from the main process.
    Sends lightweight result dicts (no frames) to result_queue.
    """

    def __init__(
        self,
        stream_config: dict[str, Any],
        app_config: dict[str, Any],
        result_queue: mp.Queue,
    ) -> None:
        super().__init__(daemon=True, name=f"worker-{stream_config['stream_id']}")
        self._stream_cfg = stream_config
        self._app_cfg = app_config
        self._result_queue = result_queue
        self._stop_event = mp.Event()

    def run(self) -> None:
        sid = self._stream_cfg["stream_id"]
        log = setup_logging(stream_id=sid)

        # CPU affinity pinning
        cpu_cores = self._stream_cfg.get("cpu_cores", [])
        if cpu_cores:
            try:
                psutil.Process().cpu_affinity(cpu_cores)
                log.info("CPU affinity fixada nos cores: %s", cpu_cores)
            except Exception as exc:
                log.warning("Não foi possível fixar CPU affinity: %s", exc)

        inf_cfg = self._app_cfg.get("inference", {})
        cap_cfg = self._app_cfg.get("capture", {})
        trk_cfg = self._app_cfg.get("tracking", {})
        cnt_cfg = self._app_cfg.get("counting", {})

        # Frame buffer: capturer escreve, inference loop lê
        frame_buffer: deque = deque(maxlen=cap_cfg.get("frame_buffer_size", 2))

        capturer = Capturer(
            rtsp_url=self._stream_cfg["rtsp_url"],
            stream_id=sid,
            buffer=frame_buffer,
            reconnect_delay=cap_cfg.get("reconnect_delay_sec", 5.0),
        )

        model_path = inf_cfg.get("model_path", "models/yolov8n_int8.onnx")
        fallback = inf_cfg.get("model_path_fp32", "models/yolov8n.onnx")
        import os
        if not os.path.exists(model_path):
            if os.path.exists(fallback):
                log.warning("Modelo INT8 não encontrado, usando FP32: %s", fallback)
                model_path = fallback
            else:
                log.error(
                    "Nenhum modelo encontrado (%s ou %s). "
                    "Execute: python models/download_model.py",
                    model_path, fallback,
                )
                return

        detector = Detector(
            model_path=model_path,
            input_size=tuple(inf_cfg.get("input_size", [640, 640])),
            nms_threshold=inf_cfg.get("nms_threshold", 0.45),
            intra_op_threads=inf_cfg.get("intra_op_threads", 2),
            inter_op_threads=inf_cfg.get("inter_op_threads", 1),
            class_thresholds=self._app_cfg.get("class_thresholds"),
            max_detections=inf_cfg.get("max_detections", 50),
            stream_id=sid,
        )

        tracker = Tracker(
            max_age=trk_cfg.get("max_age", 30),
            min_hits=trk_cfg.get("min_hits", 3),
            iou_threshold=trk_cfg.get("iou_threshold", 0.3),
        )

        counting_zones = self._stream_cfg.get("counting_zones", [])
        counter = Counter(
            zones=counting_zones,
            max_match_dist=cnt_cfg.get("max_match_dist", 600.0),
        )

        capturer.start()
        log.info("Worker iniciado para stream: %s", sid)
        for z in counting_zones:
            log.info(
                "Zona configurada: nome=%s tipo=%s pontos=%s classes=%s",
                z.get("name"), z.get("type"), z.get("points"), z.get("track_classes"),
            )

        target_fps = cap_cfg.get("target_fps", 10)
        frame_interval = 1.0 / target_fps
        frame_num = 0

        while not self._stop_event.is_set():
            loop_start = time.monotonic()

            if not frame_buffer:
                time.sleep(0.01)
                continue

            frame = frame_buffer[-1]  # sempre o frame mais recente
            frame_num += 1

            try:
                detections = detector.infer(frame)
                tracks = tracker.update(detections)
                events = counter.update(tracks)

                # Log diagnóstico a cada 30 frames para visibilidade do pipeline
                if frame_num % 30 == 0:
                    log.info(
                        "Frame %d | detecções: %d | tracks: %d | fps: %.1f",
                        frame_num, len(detections), len(tracks), self._current_fps,
                    )
                    if tracks:
                        from easycount.utils.geometry import centroid as _centroid
                        centroids = [(t.class_name, _centroid(t.bbox)) for t in tracks]
                        log.info("Centroides: %s", centroids)

                if events:
                    for ev in events:
                        log.info(
                            "CRUZAMENTO: track=%d classe=%s zona=%s direção=%s",
                            ev.track_id, ev.class_name, ev.zone_name, ev.direction,
                        )

                # Envia resultado a cada 5 frames ou quando há evento
                if events or frame_num % 5 == 0:
                    counts_snapshot = {
                        zone_name: {
                            cls_name: dict(dirs)
                            for cls_name, dirs in zc.counts.items()
                        }
                        for zone_name, zc in counter.get_counts().items()
                    }
                    self._result_queue.put_nowait({
                        "stream_id": sid,
                        "frame_num": frame_num,
                        "fps": self._current_fps,
                        "online": True,
                        "counts": counts_snapshot,
                        "events": [
                            {
                                "track_id": e.track_id,
                                "class_name": e.class_name,
                                "zone_name": e.zone_name,
                                "direction": e.direction,
                            }
                            for e in events
                        ],
                    })

            except Exception as exc:
                log.error("Erro na inferência frame %d: %s", frame_num, exc, exc_info=True)

            elapsed = time.monotonic() - loop_start
            self._current_fps = 1.0 / max(elapsed, 1e-6)
            sleep_time = frame_interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

        capturer.stop()
        log.info("Worker encerrado: %s", sid)

    def stop(self) -> None:
        self._stop_event.set()

    # Valor inicial para evitar AttributeError antes do primeiro frame
    _current_fps: float = 0.0
