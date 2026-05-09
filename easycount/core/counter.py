"""Direction-aware line-crossing and polygon zone counter."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from easycount.core.tracker import Track
from easycount.utils.geometry import (
    centroid,
    point_in_polygon,
    side_of_line,
    sign,
    smooth_point,
    Point,
)


@dataclass
class CrossingEvent:
    track_id: int
    class_name: str
    zone_name: str
    direction: str   # "in" | "out"


@dataclass
class ZoneConfig:
    name: str
    zone_type: str        # "line" | "polygon"
    points: list[Point]
    direction: str        # "in" | "out" | "both"
    track_classes: list[str] | None = None  # None = all classes


@dataclass
class ZoneCounts:
    zone_name: str
    counts: dict[str, dict[str, int]] = field(default_factory=dict)

    def increment(self, class_name: str, direction: str) -> None:
        if class_name not in self.counts:
            self.counts[class_name] = {"in": 0, "out": 0}
        self.counts[class_name][direction] += 1


class Counter:
    """
    Detects line/zone crossings frame by frame.

    Line zones use proximity-based matching between consecutive frames —
    each current detection is paired with the nearest same-class detection
    from the previous frame within MAX_MATCH_DIST pixels.  This avoids the
    track-ID discontinuity problem that arises when fast-moving objects get
    a new track_id every frame.

    Polygon zones keep the track-ID-based inside/outside state machine,
    which works well for slower region-entry events.
    """

    # Max pixel distance to match a detection to its previous-frame counterpart
    _MAX_MATCH_DIST: float = 250.0

    def __init__(self, zones: list[dict[str, Any]]) -> None:
        self._zones: list[ZoneConfig] = [self._parse_zone(z) for z in zones]
        self._zone_counts: dict[str, ZoneCounts] = {
            z.name: ZoneCounts(zone_name=z.name) for z in self._zones
        }
        # Centroid smoothing per track_id (best-effort; reduces jitter)
        self._centroids: dict[int, Point] = {}
        # Polygon zone inside/outside state per track_id
        self._track_state: dict[int, dict[str, Any]] = {}
        # Line zone: previous-frame list of (centroid, class_name, side) per zone
        self._prev_zone_pts: dict[str, list[tuple[Point, str, int]]] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update(self, tracks: list[Track]) -> list[CrossingEvent]:
        active_ids = {t.track_id for t in tracks}

        # Drop stale per-track state
        for tid in list(self._track_state.keys()):
            if tid not in active_ids:
                del self._track_state[tid]
                self._centroids.pop(tid, None)

        # Smooth centroids and build current-frame detection list
        curr: list[tuple[Point, str, int]] = []  # (smoothed_pt, class_name, track_id)
        for track in tracks:
            tid = track.track_id
            raw_c = centroid(track.bbox)
            smoothed = smooth_point(self._centroids.get(tid), raw_c)
            self._centroids[tid] = smoothed
            curr.append((smoothed, track.class_name, tid))

        events: list[CrossingEvent] = []
        for zone in self._zones:
            if zone.zone_type == "line":
                zone_events = self._check_line_zone(curr, zone)
            else:
                zone_events = self._check_polygon_zone(curr, zone)

            for ev in zone_events:
                events.append(ev)
                self._zone_counts[zone.name].increment(ev.class_name, ev.direction)

        return events

    def get_counts(self) -> dict[str, ZoneCounts]:
        return dict(self._zone_counts)

    def reset_counts(self) -> None:
        for zc in self._zone_counts.values():
            zc.counts.clear()

    # ------------------------------------------------------------------
    # Line-zone crossing via proximity matching
    # ------------------------------------------------------------------

    def _check_line_zone(
        self,
        curr: list[tuple[Point, str, int]],
        zone: ZoneConfig,
    ) -> list[CrossingEvent]:
        p1, p2 = zone.points[0], zone.points[1]

        # Compute side-of-line for each eligible detection in this frame
        curr_sides: list[tuple[Point, str, int, int]] = []  # (pt, cls, tid, side)
        for pt, cls, tid in curr:
            if zone.track_classes and cls not in zone.track_classes:
                continue
            s = sign(side_of_line(pt, p1, p2))
            curr_sides.append((pt, cls, tid, s))

        prev_pts = self._prev_zone_pts.get(zone.name, [])  # (pt, cls, side)

        events: list[CrossingEvent] = []
        used_prev: set[int] = set()

        for pt, cls, tid, curr_side in curr_sides:
            if curr_side == 0:
                continue

            # Greedy nearest-neighbour: same class, within radius, not yet matched
            best_dist = self._MAX_MATCH_DIST
            best_idx = -1
            for i, (prev_pt, prev_cls, _prev_side) in enumerate(prev_pts):
                if i in used_prev or prev_cls != cls:
                    continue
                d = math.hypot(pt[0] - prev_pt[0], pt[1] - prev_pt[1])
                if d < best_dist:
                    best_dist = d
                    best_idx = i

            if best_idx < 0:
                continue
            used_prev.add(best_idx)

            prev_side = prev_pts[best_idx][2]
            if prev_side == 0 or prev_side == curr_side:
                continue

            direction = "in" if prev_side > 0 else "out"
            if zone.direction != "both" and zone.direction != direction:
                continue

            events.append(
                CrossingEvent(track_id=tid, class_name=cls, zone_name=zone.name, direction=direction)
            )

        # Save this frame as the reference for the next frame
        self._prev_zone_pts[zone.name] = [
            (pt, cls, s) for pt, cls, tid, s in curr_sides
        ]

        return events

    # ------------------------------------------------------------------
    # Polygon-zone entry/exit via track-ID state
    # ------------------------------------------------------------------

    def _check_polygon_zone(
        self,
        curr: list[tuple[Point, str, int]],
        zone: ZoneConfig,
    ) -> list[CrossingEvent]:
        events: list[CrossingEvent] = []
        for pt, cls, tid in curr:
            if zone.track_classes and cls not in zone.track_classes:
                continue
            state = self._track_state.setdefault(tid, {})
            was_inside = state.get(zone.name, False)
            is_inside = point_in_polygon(pt, zone.points)
            state[zone.name] = is_inside
            if is_inside and not was_inside:
                events.append(CrossingEvent(track_id=tid, class_name=cls, zone_name=zone.name, direction="in"))
            elif not is_inside and was_inside:
                events.append(CrossingEvent(track_id=tid, class_name=cls, zone_name=zone.name, direction="out"))
        return events

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_zone(raw: dict[str, Any]) -> ZoneConfig:
        return ZoneConfig(
            name=raw["name"],
            zone_type=raw.get("type", "line"),
            points=[tuple(p) for p in raw["points"]],
            direction=raw.get("direction", "both"),
            track_classes=raw.get("track_classes"),
        )
