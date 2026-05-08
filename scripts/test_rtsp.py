"""
Validate RTSP stream connectivity and display basic stream info.
Usage: python scripts/test_rtsp.py rtsp://user:pass@ip:554/stream
"""

from __future__ import annotations

import sys
import time

import cv2


def test_stream(url: str) -> None:
    print(f"Testando: {url}")
    cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    if not cap.isOpened():
        print("ERRO: Não foi possível conectar ao stream.")
        sys.exit(1)

    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    native_fps = cap.get(cv2.CAP_PROP_FPS)
    print(f"Resolução  : {w}x{h}")
    print(f"FPS nativo : {native_fps:.1f}")

    t0 = time.monotonic()
    for i in range(10):
        ret, frame = cap.read()
        if not ret:
            print(f"ERRO: falha na leitura do frame {i+1}")
            break
        print(f"  Frame {i+1:2d} OK — shape={frame.shape}")

    elapsed = time.monotonic() - t0
    print(f"\n10 frames em {elapsed:.2f}s ({10/elapsed:.1f} fps efetivo)")
    cap.release()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python scripts/test_rtsp.py <rtsp_url>")
        sys.exit(1)
    test_stream(sys.argv[1])
