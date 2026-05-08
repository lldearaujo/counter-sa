"""Unit tests for counting logic (no hardware required)."""

import pytest
from easycount.core.counter import Counter
from easycount.core.tracker import Track


def make_track(tid: int, x1: float, y1: float, x2: float, y2: float, cls: str = "car") -> Track:
    return Track(track_id=tid, bbox=(x1, y1, x2, y2), class_name=cls, confidence=0.9)


VERTICAL_LINE_ZONE = {
    "type": "line",
    "name": "linha_teste",
    "points": [[500, 0], [500, 1000]],
    "direction": "both",
    "track_classes": None,
}


class TestLineCrossing:
    def test_no_crossing_same_side(self):
        counter = Counter([VERTICAL_LINE_ZONE])
        # Carro no lado esquerdo (x=200)
        t1 = make_track(1, 100, 100, 300, 300)
        events = counter.update([t1])
        assert events == []
        # Permanece no lado esquerdo
        t1 = make_track(1, 150, 100, 350, 300)
        events = counter.update([t1])
        assert events == []

    def test_crossing_left_to_right(self):
        counter = Counter([VERTICAL_LINE_ZONE])
        # Começa à esquerda da linha x=500
        events = counter.update([make_track(1, 100, 400, 300, 600)])
        assert events == []
        # Cruza para a direita (bbox centroid x > 500)
        events = counter.update([make_track(1, 600, 400, 800, 600)])
        assert len(events) == 1
        assert events[0].direction == "out"
        assert events[0].zone_name == "linha_teste"

    def test_crossing_right_to_left(self):
        counter = Counter([VERTICAL_LINE_ZONE])
        events = counter.update([make_track(1, 600, 400, 800, 600)])
        assert events == []
        events = counter.update([make_track(1, 100, 400, 300, 600)])
        assert len(events) == 1
        assert events[0].direction == "in"

    def test_counts_accumulate(self):
        counter = Counter([VERTICAL_LINE_ZONE])
        # Primeiro cruzamento
        counter.update([make_track(1, 100, 400, 300, 600)])
        counter.update([make_track(1, 600, 400, 800, 600)])
        # Volta
        counter.update([make_track(1, 100, 400, 300, 600)])

        counts = counter.get_counts()["linha_teste"].counts
        assert counts["car"]["out"] == 1
        assert counts["car"]["in"] == 1

    def test_class_filter(self):
        zone = dict(VERTICAL_LINE_ZONE)
        zone["track_classes"] = ["car"]
        counter = Counter([zone])

        # Pedestrian não deve ser contado nesta zona
        counter.update([make_track(1, 100, 400, 300, 600, cls="pedestrian")])
        events = counter.update([make_track(1, 600, 400, 800, 600, cls="pedestrian")])
        assert events == []

    def test_direction_in_only(self):
        zone = dict(VERTICAL_LINE_ZONE)
        zone["direction"] = "in"
        counter = Counter([zone])

        # "out" (left→right) não deve ser registrado
        counter.update([make_track(1, 100, 400, 300, 600)])
        events = counter.update([make_track(1, 600, 400, 800, 600)])
        assert events == []

        # "in" (right→left) deve ser registrado
        counter.update([make_track(1, 600, 400, 800, 600)])
        events = counter.update([make_track(1, 100, 400, 300, 600)])
        assert len(events) == 1
        assert events[0].direction == "in"

    def test_track_purge_on_disappear(self):
        counter = Counter([VERTICAL_LINE_ZONE])
        counter.update([make_track(1, 100, 400, 300, 600)])
        # Track some — estado deve ser limpo
        counter.update([])
        # Track reaparece: first frame não gera evento
        events = counter.update([make_track(1, 600, 400, 800, 600)])
        assert events == []


POLYGON_ZONE = {
    "type": "polygon",
    "name": "zona_teste",
    "points": [[100, 100], [400, 100], [400, 400], [100, 400]],
    "direction": "both",
    "track_classes": None,
}


class TestPolygonZone:
    def test_enter_polygon(self):
        counter = Counter([POLYGON_ZONE])
        # Fora do polígono
        counter.update([make_track(1, 10, 10, 50, 50)])
        # Entra no polígono (centroid em ~250, 250)
        events = counter.update([make_track(1, 200, 200, 300, 300)])
        assert len(events) == 1
        assert events[0].direction == "in"

    def test_exit_polygon(self):
        counter = Counter([POLYGON_ZONE])
        counter.update([make_track(1, 200, 200, 300, 300)])   # dentro
        counter.update([make_track(1, 200, 200, 300, 300)])   # permanece — sem evento
        events = counter.update([make_track(1, 10, 10, 50, 50)])  # sai
        assert len(events) == 1
        assert events[0].direction == "out"
