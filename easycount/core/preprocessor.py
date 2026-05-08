"""Frame preprocessing: letterbox resize and normalization for YOLOv8."""

from __future__ import annotations

import cv2
import numpy as np


def letterbox(
    frame: np.ndarray,
    target_size: tuple[int, int] = (640, 640),
    color: tuple[int, int, int] = (114, 114, 114),
) -> tuple[np.ndarray, float, tuple[int, int]]:
    """
    Resize frame to target_size preserving aspect ratio (letterbox padding).

    Returns:
        img     — preprocessed image as float32 [1, 3, H, W] NCHW, normalized [0, 1]
        scale   — scale factor applied to the original image
        padding — (pad_w, pad_h) pixels of padding added on each side
    """
    h, w = frame.shape[:2]
    th, tw = target_size

    scale = min(tw / w, th / h)
    new_w, new_h = int(w * scale), int(h * scale)

    resized = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_LINEAR)

    pad_w = (tw - new_w) // 2
    pad_h = (th - new_h) // 2

    padded = cv2.copyMakeBorder(
        resized, pad_h, th - new_h - pad_h, pad_w, tw - new_w - pad_w,
        cv2.BORDER_CONSTANT, value=color
    )

    # BGR → RGB, HWC → NCHW, uint8 → float32 [0, 1]
    img = cv2.cvtColor(padded, cv2.COLOR_BGR2RGB)
    img = img.transpose(2, 0, 1).astype(np.float32) / 255.0
    img = np.expand_dims(img, axis=0)

    return img, scale, (pad_w, pad_h)


def scale_boxes(
    boxes: np.ndarray,
    scale: float,
    padding: tuple[int, int],
    orig_shape: tuple[int, int],
) -> np.ndarray:
    """
    Map bounding boxes from letterboxed space back to original frame coordinates.

    boxes: [N, 4] in [x1, y1, x2, y2] format (letterboxed coordinates).
    """
    pad_w, pad_h = padding
    h, w = orig_shape[:2]

    boxes = boxes.copy().astype(np.float32)
    boxes[:, 0] = np.clip((boxes[:, 0] - pad_w) / scale, 0, w)
    boxes[:, 1] = np.clip((boxes[:, 1] - pad_h) / scale, 0, h)
    boxes[:, 2] = np.clip((boxes[:, 2] - pad_w) / scale, 0, w)
    boxes[:, 3] = np.clip((boxes[:, 3] - pad_h) / scale, 0, h)

    return boxes
