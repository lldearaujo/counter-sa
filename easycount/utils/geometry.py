"""Geometric primitives for counting zones."""

from __future__ import annotations

from typing import Sequence


Point = tuple[float, float]
Line = tuple[Point, Point]


def side_of_line(point: Point, p1: Point, p2: Point) -> float:
    """
    Signed 2-D cross product of (p2-p1) × (point-p1).

    Positive → point is on the LEFT of the directed line p1→p2.
    Negative → point is on the RIGHT.
    Zero     → point is collinear with p1 and p2.
    """
    return (p2[0] - p1[0]) * (point[1] - p1[1]) - (p2[1] - p1[1]) * (point[0] - p1[0])


def sign(value: float) -> int:
    if value > 0:
        return 1
    if value < 0:
        return -1
    return 0


def centroid(bbox: Sequence[float]) -> Point:
    """Return centroid (cx, cy) of an axis-aligned bounding box [x1, y1, x2, y2]."""
    return ((bbox[0] + bbox[2]) / 2.0, (bbox[1] + bbox[3]) / 2.0)


def point_in_polygon(point: Point, polygon: list[Point]) -> bool:
    """
    Ray-casting algorithm for point-in-polygon test.
    Polygon must be a closed list of (x, y) points.
    """
    x, y = point
    n = len(polygon)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


def smooth_point(prev: Point | None, curr: Point, alpha: float = 0.7) -> Point:
    """Exponential moving average smoothing for centroid jitter reduction."""
    if prev is None:
        return curr
    return (
        alpha * curr[0] + (1 - alpha) * prev[0],
        alpha * curr[1] + (1 - alpha) * prev[1],
    )
