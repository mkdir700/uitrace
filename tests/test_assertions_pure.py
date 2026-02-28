"""Tests for assertion pure logic."""


class FakePlatform:
    """Fake platform for testing assertions."""

    def __init__(self, pixel_map: dict | None = None, windows: list | None = None):
        self._pixel_map = pixel_map or {}
        self._windows = windows or []

    def get_pixel(self, x: int, y: int) -> tuple[int, int, int] | None:
        return self._pixel_map.get((x, y))

    def list_windows(self):
        return self._windows


class FakeWindowRef:
    def __init__(self, window_number: int, title: str | None = None):
        self.window_number = window_number
        self.title = title


def test_check_pixel_exact_match():
    from uitrace.core.models import Rect
    from uitrace.player.observer import check_pixel

    platform = FakePlatform(pixel_map={(600, 450): (255, 0, 0)})
    bounds = Rect(x=100, y=200, w=1000, h=500)
    result = check_pixel(platform, bounds, 0.5, 0.5, (255, 0, 0))
    assert result["ok"]


def test_check_pixel_within_tolerance():
    from uitrace.core.models import Rect
    from uitrace.player.observer import check_pixel

    platform = FakePlatform(pixel_map={(600, 450): (253, 2, 1)})
    bounds = Rect(x=100, y=200, w=1000, h=500)
    result = check_pixel(platform, bounds, 0.5, 0.5, (255, 0, 0), tolerance=5)
    assert result["ok"]


def test_check_pixel_outside_tolerance():
    from uitrace.core.models import Rect
    from uitrace.player.observer import check_pixel

    platform = FakePlatform(pixel_map={(600, 450): (200, 0, 0)})
    bounds = Rect(x=100, y=200, w=1000, h=500)
    result = check_pixel(platform, bounds, 0.5, 0.5, (255, 0, 0), tolerance=5)
    assert not result["ok"]


def test_check_pixel_none_returns_not_ok():
    from uitrace.core.models import Rect
    from uitrace.player.observer import check_pixel

    platform = FakePlatform()  # no pixels
    bounds = Rect(x=100, y=200, w=1000, h=500)
    result = check_pixel(platform, bounds, 0.5, 0.5, (255, 0, 0))
    assert not result["ok"]


def test_check_window_title_contains():
    from uitrace.player.observer import check_window_title_contains

    win = FakeWindowRef(window_number=1, title="My TextEdit Document")
    platform = FakePlatform(windows=[win])
    result = check_window_title_contains(platform, win, "TextEdit")
    assert result["ok"]


def test_check_window_title_not_found():
    from uitrace.player.observer import check_window_title_contains

    win = FakeWindowRef(window_number=1, title="Safari")
    platform = FakePlatform(windows=[win])
    result = check_window_title_contains(platform, win, "TextEdit")
    assert not result["ok"]
