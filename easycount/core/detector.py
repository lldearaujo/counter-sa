"""ONNX Runtime inference wrapper for YOLOv8 with per-class NMS."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import onnxruntime as ort

from easycount.core.preprocessor import letterbox, scale_boxes
from easycount.utils.logging import setup_logging

# COCO class IDs relevant to EasyCount → internal name
TRACKED_CLASSES: dict[int, str] = {
    0: "pedestrian",
    1: "bicycle",
    2: "car",
    3: "motorcycle",
    5: "bus",
    7: "truck",
}

DEFAULT_CLASS_THRESHOLDS: dict[str, float] = {
    "pedestrian": 0.35,
    "bicycle": 0.40,
    "car": 0.40,
    "motorcycle": 0.35,
    "bus": 0.50,
    "truck": 0.50,
}


@dataclass
class Detection:
    bbox: tuple[float, float, float, float]  # x1, y1, x2, y2 (original coords)
    class_id: int
    class_name: str
    confidence: float


class Detector:
    def __init__(
        self,
        model_path: str,
        input_size: tuple[int, int] = (640, 640),
        nms_threshold: float = 0.45,
        intra_op_threads: int = 2,
        inter_op_threads: int = 1,
        class_thresholds: dict[str, float] | None = None,
        max_detections: int = 50,
        stream_id: str = "default",
    ) -> None:
        self.input_size = input_size
        self.nms_threshold = nms_threshold
        self.class_thresholds = class_thresholds or DEFAULT_CLASS_THRESHOLDS
        self.max_detections = max_detections
        self._log = setup_logging(stream_id=stream_id)

        opts = ort.SessionOptions()
        opts.intra_op_num_threads = intra_op_threads
        opts.inter_op_num_threads = inter_op_threads
        opts.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        opts.enable_mem_pattern = True
        opts.enable_cpu_mem_arena = True

        self._session = ort.InferenceSession(
            model_path,
            sess_options=opts,
            providers=["CPUExecutionProvider"],
        )
        self._input_name = self._session.get_inputs()[0].name
        self._log.info("Modelo carregado: %s", model_path)

    def infer(self, frame: np.ndarray) -> list[Detection]:
        orig_shape = frame.shape
        img, scale, padding = letterbox(frame, self.input_size)

        outputs = self._session.run(None, {self._input_name: img})
        # YOLOv8 ONNX output: [1, 84, 8400] → transpose to [8400, 84]
        predictions = outputs[0][0].T  # shape: [8400, 84]

        return self._parse(predictions, scale, padding, orig_shape)

    def _parse(
        self,
        predictions: np.ndarray,
        scale: float,
        padding: tuple[int, int],
        orig_shape: tuple[int, int],
    ) -> list[Detection]:
        # predictions: [N, 4+num_classes] where [:4] = cx, cy, w, h
        cx, cy, w, h = predictions[:, 0], predictions[:, 1], predictions[:, 2], predictions[:, 3]
        class_scores = predictions[:, 4:]  # [N, 80]

        class_ids = class_scores.argmax(axis=1)
        confidences = class_scores.max(axis=1)

        # Keep only tracked classes
        relevant_mask = np.isin(class_ids, list(TRACKED_CLASSES.keys()))
        class_ids = class_ids[relevant_mask]
        confidences = confidences[relevant_mask]
        cx = cx[relevant_mask]
        cy = cy[relevant_mask]
        w = w[relevant_mask]
        h = h[relevant_mask]

        if len(class_ids) == 0:
            return []

        # Convert cx,cy,w,h → x1,y1,x2,y2
        x1 = cx - w / 2
        y1 = cy - h / 2
        x2 = cx + w / 2
        y2 = cy + h / 2
        boxes_lbs = np.stack([x1, y1, x2, y2], axis=1)

        # Per-class confidence threshold filter
        class_names = np.array([TRACKED_CLASSES[cid] for cid in class_ids])
        thresholds = np.array([self.class_thresholds.get(cn, 0.35) for cn in class_names])
        conf_mask = confidences >= thresholds
        class_ids = class_ids[conf_mask]
        class_names = class_names[conf_mask]
        confidences = confidences[conf_mask]
        boxes_lbs = boxes_lbs[conf_mask]

        if len(class_ids) == 0:
            return []

        # Limit to top-N by confidence before NMS (perf guard for dense scenes)
        if len(confidences) > self.max_detections:
            top_idx = np.argpartition(confidences, -self.max_detections)[-self.max_detections:]
            class_ids = class_ids[top_idx]
            class_names = class_names[top_idx]
            confidences = confidences[top_idx]
            boxes_lbs = boxes_lbs[top_idx]

        # NMS via OpenCV (works on letterboxed coords — faster than per-class loop)
        indices = cv2_nms(boxes_lbs, confidences, self.nms_threshold)
        if len(indices) == 0:
            return []

        boxes_orig = scale_boxes(boxes_lbs[indices], scale, padding, orig_shape)

        detections = []
        for i, idx in enumerate(indices):
            bbox = tuple(boxes_orig[i].tolist())
            detections.append(Detection(
                bbox=bbox,
                class_id=int(class_ids[idx]),
                class_name=class_names[idx],
                confidence=float(confidences[idx]),
            ))

        return detections


def cv2_nms(boxes: np.ndarray, scores: np.ndarray, iou_threshold: float) -> np.ndarray:
    """OpenCV NMS wrapper. boxes in [x1,y1,x2,y2]; returns kept indices."""
    import cv2
    # cv2.dnn.NMSBoxes expects [x,y,w,h]
    boxes_xywh = boxes.copy()
    boxes_xywh[:, 2] = boxes[:, 2] - boxes[:, 0]
    boxes_xywh[:, 3] = boxes[:, 3] - boxes[:, 1]

    kept = cv2.dnn.NMSBoxes(
        boxes_xywh.tolist(),
        scores.tolist(),
        score_threshold=0.0,   # already filtered above
        nms_threshold=iou_threshold,
    )
    if len(kept) == 0:
        return np.array([], dtype=int)
    return np.array(kept).flatten()
