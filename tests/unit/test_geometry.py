"""Unit tests for geometry primitives."""

import pytest
from easycount.utils.geometry import (
    centroid,
    point_in_polygon,
    side_of_line,
    sign,
    smooth_point,
)


class TestSideOfLine:
    def test_left_of_line(self):
        # Linha vertical x=5; ponto à esquerda (x=3)
        assert side_of_line((3, 5), (5, 0), (5, 10)) > 0

    def test_right_of_line(self):
        assert side_of_line((7, 5), (5, 0), (5, 10)) < 0

    def test_on_line(self):
        assert side_of_line((5, 5), (5, 0), (5, 10)) == 0

    def test_horizontal_line_above(self):
        # Linha horizontal y=5; ponto acima (y=3)
        assert side_of_line((5, 3), (0, 5), (10, 5)) > 0

    def test_horizontal_line_below(self):
        assert side_of_line((5, 7), (0, 5), (10, 5)) < 0


class TestSign:
    def test_positive(self):
        assert sign(3.14) == 1

    def test_negative(self):
        assert sign(-0.001) == -1

    def test_zero(self):
        assert sign(0.0) == 0


class TestCentroid:
    def test_basic(self):
        cx, cy = centroid([100, 200, 300, 400])
        assert cx == 200.0
        assert cy == 300.0

    def test_square(self):
        cx, cy = centroid([0, 0, 10, 10])
        assert cx == 5.0
        assert cy == 5.0


class TestPointInPolygon:
    SQUARE = [(0, 0), (10, 0), (10, 10), (0, 10)]

    def test_inside(self):
        assert point_in_polygon((5, 5), self.SQUARE) is True

    def test_outside(self):
        assert point_in_polygon((15, 5), self.SQUARE) is False

    def test_on_boundary(self):
        # Ray-casting pode ser True ou False na fronteira — apenas verifica que não lança exceção
        result = point_in_polygon((10, 5), self.SQUARE)
        assert isinstance(result, bool)

    def test_triangle(self):
        triangle = [(0, 0), (5, 10), (10, 0)]
        assert point_in_polygon((5, 5), triangle) is True
        assert point_in_polygon((0, 10), triangle) is False


class TestSmoothPoint:
    def test_first_call_returns_current(self):
        result = smooth_point(None, (3.0, 4.0))
        assert result == (3.0, 4.0)

    def test_smoothing_alpha_one(self):
        # alpha=1.0 → resultado = current
        result = smooth_point((0.0, 0.0), (10.0, 10.0), alpha=1.0)
        assert result == (10.0, 10.0)

    def test_smoothing_alpha_zero(self):
        # alpha=0.0 → resultado = prev
        result = smooth_point((2.0, 3.0), (10.0, 10.0), alpha=0.0)
        assert result == (2.0, 3.0)

    def test_smoothing_partial(self):
        prev = (0.0, 0.0)
        curr = (10.0, 10.0)
        result = smooth_point(prev, curr, alpha=0.5)
        assert result == (5.0, 5.0)
