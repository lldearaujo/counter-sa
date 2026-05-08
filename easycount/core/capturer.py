"""RTSP frame capture thread with auto-reconnect."""

from __future__ import annotations

import threading
import time
from collections import deque

import cv2

from easycount.utils.logging import setup_logging


class Capturer(threading.Thread):
    """
    Reads frames from an RTSP stream in a background thread.
    Always keeps the latest frame in a deque(maxlen=N) so the inference
    loop never blocks waiting for a frame and never processes stale ones.
    """

    def __init__(
        self,
        rtsp_url: str,
        stream_id: str,
        buffer: deque,
        reconnect_delay: float = 5.0,
    ) -> None:
        super().__init__(daemon=True, name=f"capturer-{stream_id}")
        self.rtsp_url = rtsp_url
        self.stream_id = stream_id
        self.buffer = buffer
        self.reconnect_delay = reconnect_delay
        self._stop_event = threading.Event()
        self._log = setup_logging(stream_id=stream_id)
        self.connected = False

    def run(self) -> None:
        while not self._stop_event.is_set():
            cap = self._open()
            if cap is None:
                time.sleep(self.reconnect_delay)
                continue

            self.connected = True
            self._log.info("Stream conectado: %s", self.rtsp_url)

            while not self._stop_event.is_set():
                ret, frame = cap.read()
                if not ret:
                    self._log.warning("Falha na leitura do frame — reconectando...")
                    break
                self.buffer.append(frame)

            cap.release()
            self.connected = False
            if not self._stop_event.is_set():
                self._log.info("Aguardando %ss para reconectar...", self.reconnect_delay)
                time.sleep(self.reconnect_delay)

    def _open(self) -> cv2.VideoCapture | None:
        cap = cv2.VideoCapture(self.rtsp_url, cv2.CAP_FFMPEG)
        # Minimiza buffer interno do OpenCV para reduzir latência
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        if not cap.isOpened():
            self._log.error("Não foi possível abrir: %s", self.rtsp_url)
            return None
        return cap

    def stop(self) -> None:
        self._stop_event.set()
