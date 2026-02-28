from uitrace.core.models import Rect
from uitrace.recorder.recorder import _in_bounds, _screen_to_relative


def test_in_bounds_inside():
    b = Rect(x=100, y=200, w=800, h=600)
    assert _in_bounds(500, 400, b)


def test_in_bounds_outside():
    b = Rect(x=100, y=200, w=800, h=600)
    assert not _in_bounds(50, 400, b)
    assert not _in_bounds(500, 900, b)


def test_in_bounds_edge():
    b = Rect(x=100, y=200, w=800, h=600)
    assert _in_bounds(100, 200, b)  # top-left
    assert _in_bounds(900, 800, b)  # bottom-right


def test_screen_to_relative_center():
    b = Rect(x=100, y=200, w=800, h=600)
    pos = _screen_to_relative(500, 500, b)
    assert pos.rx == 0.5
    assert pos.ry == 0.5


def test_screen_to_relative_origin():
    b = Rect(x=100, y=200, w=800, h=600)
    pos = _screen_to_relative(100, 200, b)
    assert pos.rx == 0.0
    assert pos.ry == 0.0
