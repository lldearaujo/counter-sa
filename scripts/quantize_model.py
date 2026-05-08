"""
INT8 static quantization of the YOLOv8n ONNX model.
Usage: python scripts/quantize_model.py [--source rtsp://... | --video path.mp4]

The script collects calibration frames from the source, then applies
onnxruntime static quantization. Requires ~100-200 frames for good calibration.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import numpy as np

INPUT_MODEL = Path("models/yolov8n.onnx")
OUTPUT_MODEL = Path("models/yolov8n_int8.onnx")
CALIB_FRAMES = 150
INPUT_SIZE = (640, 640)


class CalibrationReader:
    def __init__(self, frames: list[np.ndarray], input_name: str) -> None:
        self._frames = frames
        self._input_name = input_name
        self._idx = 0

    def get_next(self):
        if self._idx >= len(self._frames):
            return None
        frame = self._frames[self._idx]
        self._idx += 1

        from easycount.core.preprocessor import letterbox
        img, _, _ = letterbox(frame, INPUT_SIZE)
        return {self._input_name: img}


def collect_frames(source: str, n: int) -> list[np.ndarray]:
    cap = cv2.VideoCapture(source)
    frames = []
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    step = max(1, total // n) if total > 0 else 1

    idx = 0
    while len(frames) < n:
        ret, frame = cap.read()
        if not ret:
            break
        if idx % step == 0:
            frames.append(frame)
        idx += 1

    cap.release()
    print(f"Coletados {len(frames)} frames de calibração de: {source}")
    return frames


def quantize(frames: list[np.ndarray]) -> None:
    from onnxruntime.quantization import (
        CalibrationDataReader,
        QuantType,
        quantize_static,
    )
    import onnxruntime as ort

    session = ort.InferenceSession(str(INPUT_MODEL), providers=["CPUExecutionProvider"])
    input_name = session.get_inputs()[0].name

    class Reader(CalibrationDataReader):
        def __init__(self):
            self._inner = CalibrationReader(frames, input_name)

        def get_next(self):
            return self._inner.get_next()

    print(f"Quantizando {INPUT_MODEL} → {OUTPUT_MODEL} ...")
    quantize_static(
        model_input=str(INPUT_MODEL),
        model_output=str(OUTPUT_MODEL),
        calibration_data_reader=Reader(),
        quant_type=QuantType.QInt8,
        per_channel=False,
        reduce_range=True,
    )
    print(f"Modelo INT8 salvo em: {OUTPUT_MODEL}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default="data/samples/calibration.mp4",
                        help="Fonte de calibração: arquivo de vídeo ou URL RTSP")
    parser.add_argument("--frames", type=int, default=CALIB_FRAMES)
    args = parser.parse_args()

    if not INPUT_MODEL.exists():
        print(f"Modelo base não encontrado: {INPUT_MODEL}")
        print("Execute: python models/download_model.py")
        return

    frames = collect_frames(args.source, args.frames)
    if len(frames) < 20:
        print("Poucos frames para calibração. Verifique a fonte.")
        return

    quantize(frames)


if __name__ == "__main__":
    main()
