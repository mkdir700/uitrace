from uitrace.core.models import Rect
from uitrace.player.executor import window_rel_to_screen


def test_window_rel_to_screen_center():
    b = Rect(x=100, y=200, w=1000, h=500)
    x, y = window_rel_to_screen(b, rx=0.5, ry=0.5)
    assert x == 600
    assert y == 450


def test_window_rel_to_screen_origin():
    b = Rect(x=100, y=200, w=1000, h=500)
    x, y = window_rel_to_screen(b, rx=0.0, ry=0.0)
    assert x == 100
    assert y == 200


def test_window_rel_to_screen_clamps():
    b = Rect(x=100, y=200, w=1000, h=500)
    x, y = window_rel_to_screen(b, rx=1.5, ry=-0.5)
    assert x == 1100
    assert y == 200


def test_window_rel_to_screen_bottom_right():
    b = Rect(x=0, y=0, w=800, h=600)
    x, y = window_rel_to_screen(b, rx=1.0, ry=1.0)
    assert x == 800
    assert y == 600
