"""Pure tests for window hit-testing helpers.

These tests exercise _rect_contains_point and the window-selection
logic without requiring macOS Quartz (no CGWindowListCopyWindowInfo).
"""

from uitrace.core.models import Rect
from uitrace.platform.macos import _rect_contains_point

# ---------------------------------------------------------------------------
# _rect_contains_point
# ---------------------------------------------------------------------------


def test_rect_contains_point_inside():
    """Point clearly inside the bounds returns True."""
    bounds = Rect(x=100, y=200, w=400, h=300)
    assert _rect_contains_point(bounds, 250, 350) is True


def test_rect_contains_point_edge():
    """Points exactly on each edge (inclusive) return True."""
    bounds = Rect(x=100, y=200, w=400, h=300)
    # top-left corner
    assert _rect_contains_point(bounds, 100, 200) is True
    # top-right corner
    assert _rect_contains_point(bounds, 500, 200) is True
    # bottom-left corner
    assert _rect_contains_point(bounds, 100, 500) is True
    # bottom-right corner
    assert _rect_contains_point(bounds, 500, 500) is True
    # mid-top edge
    assert _rect_contains_point(bounds, 300, 200) is True
    # mid-left edge
    assert _rect_contains_point(bounds, 100, 350) is True


def test_rect_contains_point_outside():
    """Points outside bounds return False."""
    bounds = Rect(x=100, y=200, w=400, h=300)
    # left of bounds
    assert _rect_contains_point(bounds, 99, 350) is False
    # right of bounds
    assert _rect_contains_point(bounds, 501, 350) is False
    # above bounds
    assert _rect_contains_point(bounds, 250, 199) is False
    # below bounds
    assert _rect_contains_point(bounds, 250, 501) is False


# ---------------------------------------------------------------------------
# Window selection logic (pure, no Quartz)
# ---------------------------------------------------------------------------


def _select_window_from_synthetic(windows: list[dict], x: int, y: int):
    """Replicate the selection logic from MacOSPlatform.window_from_point
    using synthetic window dicts.  Returns a dict or None."""
    for info in windows:
        if int(info.get("kCGWindowLayer", -1)) != 0:
            continue
        bounds_dict = info.get("kCGWindowBounds")
        if bounds_dict is None:
            continue
        bounds = Rect(
            x=int(bounds_dict.get("X", 0)),
            y=int(bounds_dict.get("Y", 0)),
            w=int(bounds_dict.get("Width", 0)),
            h=int(bounds_dict.get("Height", 0)),
        )
        if bounds.w <= 1 or bounds.h <= 1:
            continue
        if not _rect_contains_point(bounds, x, y):
            continue
        return info
    return None


def _make_window(
    *,
    number: int,
    x: int,
    y: int,
    w: int,
    h: int,
    layer: int = 0,
    name: str = "",
    owner: str = "TestApp",
    pid: int = 100,
) -> dict:
    """Build a synthetic CGWindowListCopyWindowInfo entry."""
    return {
        "kCGWindowNumber": number,
        "kCGWindowBounds": {"X": x, "Y": y, "Width": w, "Height": h},
        "kCGWindowLayer": layer,
        "kCGWindowName": name,
        "kCGWindowOwnerName": owner,
        "kCGWindowOwnerPID": pid,
    }


def test_topmost_window_selected():
    """When windows overlap, the first in list (front-to-back) wins."""
    front = _make_window(number=1, x=0, y=0, w=800, h=600, name="Front")
    back = _make_window(number=2, x=0, y=0, w=800, h=600, name="Back")
    windows = [front, back]

    result = _select_window_from_synthetic(windows, 400, 300)
    assert result is not None
    assert result["kCGWindowNumber"] == 1
    assert result["kCGWindowName"] == "Front"


def test_point_outside_all_windows_returns_none():
    """A point that falls outside every window returns None."""
    w1 = _make_window(number=1, x=0, y=0, w=100, h=100, name="Small")
    w2 = _make_window(number=2, x=200, y=200, w=100, h=100, name="Other")
    windows = [w1, w2]

    result = _select_window_from_synthetic(windows, 500, 500)
    assert result is None


def test_overlay_layer_skipped():
    """Windows with kCGWindowLayer != 0 are ignored."""
    overlay = _make_window(number=1, x=0, y=0, w=800, h=600, layer=25, name="Menu")
    normal = _make_window(number=2, x=0, y=0, w=800, h=600, name="App")
    windows = [overlay, normal]

    result = _select_window_from_synthetic(windows, 400, 300)
    assert result is not None
    assert result["kCGWindowNumber"] == 2


def test_tiny_window_skipped():
    """Windows with w<=1 or h<=1 are skipped."""
    tiny = _make_window(number=1, x=0, y=0, w=1, h=1, name="Tiny")
    normal = _make_window(number=2, x=0, y=0, w=800, h=600, name="Normal")
    windows = [tiny, normal]

    result = _select_window_from_synthetic(windows, 0, 0)
    assert result is not None
    assert result["kCGWindowNumber"] == 2
