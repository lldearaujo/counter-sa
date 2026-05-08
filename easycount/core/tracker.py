"""ByteTrack wrapper via supervision library."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import supervision as sv

from easycount.core.detector import Detection


@dataclass
class Track:
    track_id: int
    bbox: tuple[float, float, float, float]  # x1, y1, x2, y2
    class_name: str
    confidence: float


class Tracker:
    def __init__(
        self,
        max_age: int = 30,
        min_hits: int = 3,
        iou_threshold: float = 0.3,
    ) -> None:
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            self._tracker = sv.ByteTrack(
                track_activation_threshold=0.25,
                lost_track_buffer=max_age,
                minimum_matching_threshold=iou_threshold,
                minimum_consecutive_frames=min_hits,
            )

    def update(self, detections: list[Detection]) -> list[Track]:
        if not detections:
            sv_dets = sv.Detections.empty()
        else:
            bboxes = np.array([d.bbox for d in detections], dtype=np.float32)
            confs = np.array([d.confidence for d in detections], dtype=np.float32)
            class_ids = np.array([d.class_id for d in detections], dtype=int)
            sv_dets = sv.Detections(
                xyxy=bboxes,
                confidence=confs,
                class_id=class_ids,
            )

        tracked = self._tracker.update_with_detections(sv_dets)

        tracks: list[Track] = []
        if len(tracked) == 0:
            return tracks

        for i in range(len(tracked)):
            bbox = tuple(tracked.xyxy[i].tolist())
            cid = int(tracked.class_id[i])
            tid = int(tracked.tracker_id[i])
            conf = float(tracked.confidence[i]) if tracked.confidence is not None else 0.0

            # Map class_id back to name using the same mapping as detector
            from easycount.core.detector import TRACKED_CLASSES
            class_name = TRACKED_CLASSES.get(cid, str(cid))

            tracks.append(Track(track_id=tid, bbox=bbox, class_name=class_name, confidence=conf))

        return tracks

    def reset(self) -> None:
        self._tracker.reset()
