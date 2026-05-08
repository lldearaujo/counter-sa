"""
Download YOLOv8n weights and export to ONNX FP32.
Usage: python models/download_model.py
Requires: pip install ultralytics (optional dependency group 'export')
"""

from __future__ import annotations

import sys
from pathlib import Path

OUTPUT_DIR = Path(__file__).parent


def main() -> None:
    try:
        from ultralytics import YOLO
    except ImportError:
        print("Instale o grupo 'export': pip install easycount[export]")
        sys.exit(1)

    onnx_path = OUTPUT_DIR / "yolov8n.onnx"
    if onnx_path.exists():
        print(f"Modelo já existe: {onnx_path}")
        return

    print("Baixando YOLOv8n e exportando para ONNX...")
    model = YOLO("yolov8n.pt")
    model.export(
        format="onnx",
        opset=17,
        simplify=True,
        imgsz=640,
        dynamic=False,
    )

    # Ultralytics salva como yolov8n.onnx no CWD
    exported = Path("yolov8n.onnx")
    if exported.exists() and not onnx_path.exists():
        exported.rename(onnx_path)

    print(f"Modelo ONNX salvo em: {onnx_path}")
    print("Execute scripts/quantize_model.py para gerar a versão INT8.")


if __name__ == "__main__":
    main()
