"""Direction-aware line-crossing and polygon zone counter."""

from __future__ import annotations

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
    # counts[class_name]["in"] and counts[class_name]["out"]

    def increment(self, class_name: str, direction: str) -> None:
        if class_name not in self.counts:
            self.counts[class_name] = {"in": 0, "out": 0}
        self.counts[class_name][direction] += 1


class Counter:
    """
    Maintains per-track state and detects line/zone crossings.
    Must be called once per inference frame with the full list of active tracks.
    """

    def __init__(self, zones: list[dict[str, Any]]) -> None:
        self._zones: list[ZoneConfig] = [self._parse_zone(z) for z in zones]
        self._zone_counts: dict[str, ZoneCounts] = {
            z.name: ZoneCounts(zone_name=z.name) for z in self._zones
        }
        # Per-track, per-zone state
        # line zones: {track_id: {zone_name: last_side (int)}}
        # polygon zones: {track_id: {zone_name: bool}}
        self._track_state: dict[int, dict[str, Any]] = {}
        # Centroid smoothing history per track
        self._centroids: dict[int, Point] = {}

    def update(self, tracks: list[Track]) -> list[CrossingEvent]:
        active_ids = {t.track_id for t in tracks}

        # Purge state for tracks that disappeared
        for tid in list(self._track_state.keys()):
            if tid not in active_ids:
                del self._track_state[tid]
                self._centroids.pop(tid, None)

        events: list[CrossingEvent] = []

        for track in tracks:
            tid = track.track_id
            raw_c = centroid(track.bbox)
            smoothed = smooth_point(self._centroids.get(tid), raw_c)
            self._centroids[tid] = smoothed

            for zone in self._zones:
                if zone.track_classes and track.class_name not in zone.track_classes:
                    continue

                if zone.zone_type == "line":
                    ev = self._check_line(tid, track.class_name, smoothed, zone)
                else:
                    ev = self._check_polygon(tid, track.class_name, smoothed, zone)

                if ev:
                    events.append(ev)
                    self._zone_counts[zone.name].increment(ev.class_name, ev.direction)

        return events

    def _check_line(
        self, tid: int, class_name: str, pt: Point, zone: ZoneConfig
    ) -> CrossingEvent | None:
        p1, p2 = zone.points[0], zone.points[1]
        current_side = sign(side_of_line(pt, p1, p2))

        state = self._track_state.setdefault(tid, {})
        last_side = state.get(zone.name, 0)
        state[zone.name] = current_side

        if last_side == 0 or current_side == 0 or last_side == current_side:
            return None

        # Determine direction: left→right ("in") vs right→left ("out")
        direction = "in" if last_side > 0 else "out"

        if zone.direction != "both" and zone.direction != direction:
            return None

        return CrossingEvent(track_id=tid, class_name=class_name, zone_name=zone.name, direction=direction)

    def _check_polygon(
        self, tid: int, class_name: str, pt: Point, zone: ZoneConfig
    ) -> CrossingEvent | None:
        was_inside = self._track_state.setdefault(tid, {}).get(zone.name, False)
        is_inside = point_in_polygon(pt, zone.points)
        self._track_state[tid][zone.name] = is_inside

        if is_inside and not was_inside:
            return CrossingEvent(track_id=tid, class_name=class_name, zone_name=zone.name, direction="in")
        if not is_inside and was_inside:
            return CrossingEvent(track_id=tid, class_name=class_name, zone_name=zone.name, direction="out")
        return None

    def get_counts(self) -> dict[str, ZoneCounts]:
        return dict(self._zone_counts)

    def reset_counts(self) -> None:
        for zc in self._zone_counts.values():
            zc.counts.clear()

    @staticmethod
    def _parse_zone(raw: dict[str, Any]) -> ZoneConfig:
        return ZoneConfig(
            name=raw["name"],
            zone_type=raw.get("type", "line"),
            points=[tuple(p) for p in raw["points"]],
            direction=raw.get("direction", "both"),
            track_classes=raw.get("track_classes"),
        )
