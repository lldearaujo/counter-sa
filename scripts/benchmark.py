"""
Single-stream FPS benchmark.
Usage: python scripts/benchmark.py --stream rtsp://... [--model models/yolov8n_int8.onnx] [--seconds 30]
"""

from __future__ import annotations

import argparse
import time
from collections import deque

import cv2
import numpy as np

from easycount.core.detector import Detector
from easycount.core.preprocessor import letterbox


def run_benchmark(stream_url: str, model_path: str, duration: int) -> None:
    detector = Detector(
        model_path=model_path,
        input_size=(640, 640),
        intra_op_threads=2,
        stream_id="benchmark",
    )

    cap = cv2.VideoCapture(stream_url, cv2.CAP_FFMPEG)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    if not cap.isOpened():
        print(f"Não foi possível abrir: {stream_url}")
        return

    frame_times: deque = deque(maxlen=100)
    frame_count = 0
    start = time.monotonic()

    print(f"Benchmark iniciado — {duration}s | fonte: {stream_url}")
    print(f"Modelo: {model_path}")
    print("-" * 50)

    while time.monotonic() - start < duration:
        ret, frame = cap.read()
        if not ret:
            break

        t0 = time.monotonic()
        dets = detector.infer(frame)
        elapsed = time.monotonic() - t0

        frame_times.append(elapsed)
        frame_count += 1

        if frame_count % 30 == 0:
            avg_ms = np.mean(frame_times) * 1000
            fps = 1.0 / np.mean(frame_times)
            print(
                f"Frame {frame_count:5d} | {fps:5.1f} fps | "
                f"{avg_ms:6.1f}ms/frame | {len(dets)} detecções"
            )

    cap.release()

    total_time = time.monotonic() - start
    avg_fps = frame_count / total_time
    avg_ms = np.mean(frame_times) * 1000 if frame_times else 0

    print("\n=== RESULTADO FINAL ===")
    print(f"Frames processados : {frame_count}")
    print(f"Duração            : {total_time:.1f}s")
    print(f"FPS médio          : {avg_fps:.2f}")
    print(f"Latência média     : {avg_ms:.1f}ms/frame")
    print(f"Latência p95       : {np.percentile(list(frame_times), 95)*1000:.1f}ms")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--stream", required=True)
    parser.add_argument("--model", default="models/yolov8n_int8.onnx")
    parser.add_argument("--seconds", type=int, default=30)
    args = parser.parse_args()

    run_benchmark(args.stream, args.model, args.seconds)
