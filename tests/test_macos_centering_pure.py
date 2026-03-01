"""Pure tests for macOS centering helper behavior."""

from __future__ import annotations

import sys
from types import SimpleNamespace

from uitrace.core.models import Rect
from uitrace.platform.base import WindowRef
from uitrace.platform.macos import MacOSPlatform


class _Point:
    def __init__(self, x: float, y: float) -> None:
        self.x = x
        self.y = y


class _Size:
    def __init__(self, width: float, height: float) -> None:
        self.width = width
        self.height = height


class _Origin:
    def __init__(self, x: float, y: float) -> None:
        self.x = x
        self.y = y


class _Frame:
    def __init__(self, *, x: float, y: float, width: float, height: float) -> None:
        self.origin = _Origin(x, y)
        self.size = _Size(width, height)


class _Screen:
    def frame(self) -> _Frame:
        return _Frame(x=0, y=0, width=1000, height=800)


class _NSScreen:
    @staticmethod
    def mainScreen() -> _Screen:
        return _Screen()


def test_center_ax_window_supports_axvalue_size(monkeypatch) -> None:
    """When AXSize is an AXValue-like object, centering still succeeds."""
    set_calls: list[tuple[object, str, object]] = []
    size_token = object()

    def _copy_attr(_ax_win: object, attr: str, _unused: object):
        if attr == "AXSize":
            return 0, size_token
        return 1, None

    def _ax_value_get_value(value: object, value_type: str, ptr: object):
        assert ptr is None
        if value is size_token and value_type == "cgsize":
            return True, _Size(300, 200)
        return False, None

    def _ax_value_create(value_type: str, point: _Point):
        return {"type": value_type, "point": point}

    def _set_attr(ax_win: object, attr: str, value: object):
        set_calls.append((ax_win, attr, value))
        return 0

    monkeypatch.setitem(
        sys.modules,
        "AppKit",
        SimpleNamespace(NSScreen=_NSScreen),
    )
    monkeypatch.setitem(
        sys.modules,
        "CoreFoundation",
        SimpleNamespace(CGPoint=_Point),
    )
    monkeypatch.setitem(
        sys.modules,
        "ApplicationServices",
        SimpleNamespace(
            AXUIElementSetAttributeValue=_set_attr,
            AXValueCreate=_ax_value_create,
            AXValueGetValue=_ax_value_get_value,
            kAXValueTypeCGPoint="cgpoint",
            kAXValueTypeCGSize="cgsize",
        ),
    )

    win = WindowRef(
        handle="1",
        title="T",
        pid=123,
        owner_name="App",
        bounds=Rect(x=0, y=0, w=800, h=600),
        window_number=1,
    )

    MacOSPlatform._center_ax_window("ax-window", win, _copy_attr)

    assert len(set_calls) == 1
    _, attr, value = set_calls[0]
    assert attr == "AXPosition"
    assert value["type"] == "cgpoint"
    assert value["point"].x == 350
    assert value["point"].y == 300
