"""Core models for uitrace trace events."""
from typing import Any, Literal, Union, Annotated

from pydantic import BaseModel, ConfigDict, Field, Discriminator
from typing import Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field


# Shared types
class Rect(BaseModel):
    """Rectangle with x, y, width, height."""
    model_config = ConfigDict(extra="forbid")
    x: int
    y: int
    w: int
    h: int


class Inset(BaseModel):
    """Client inset: left, top, right, bottom."""
    model_config = ConfigDict(extra="forbid")
    l: int
    t: int
    r: int
    b: int


class Pos(BaseModel):
    """Relative position (0-1) within a window."""
    model_config = ConfigDict(extra="forbid")
    rx: float
    ry: float


class Point(BaseModel):
    """Absolute screen position in points."""
    model_config = ConfigDict(extra="forbid")
    x: int
    y: int


class WindowSelector(BaseModel):
    """Selector to locate a window."""
    model_config = ConfigDict(extra="forbid")
    title_regex: str | None = None
    title: str | None = None
    pid: int | None = None
    app: str | None = None
    bundle_id: str | None = None
    platform: Literal["mac", "win", "x11"] | None = None


# Trace events
class SessionStart(BaseModel):
    """Session start event."""
    model_config = ConfigDict(extra="forbid")
    v: Literal[1]
    type: Literal["session_start"]
    ts: float
    meta: dict[str, Any]


class WindowSelectorEvent(BaseModel):
    """Window selector event."""
    model_config = ConfigDict(extra="forbid")
    v: Literal[1]
    type: Literal["window_selector"]
    ts: float
    selector: WindowSelector


class WindowBounds(BaseModel):
    """Window bounds event."""
    model_config = ConfigDict(extra="forbid")
    v: Literal[1]
    type: Literal["window_bounds"]
    ts: float
    bounds: Rect
    client_inset: Inset | None = None


class Click(BaseModel):
    """Click event."""
    model_config = ConfigDict(extra="forbid")
    v: Literal[1]
    type: Literal["click"]
    ts: float
    pos: Pos
    screen: Point
    button: Literal["left", "right", "middle"]
    count: int = Field(ge=1)


class Scroll(BaseModel):
    """Scroll event."""
    model_config = ConfigDict(extra="forbid")
    v: Literal[1]
    type: Literal["scroll"]
    ts: float
    pos: Pos
    screen: Point
    delta: dict[Literal["y"], int]


class Assert(BaseModel):
    """Assertion event."""
    model_config = ConfigDict(extra="forbid")
    v: Literal[1]
    type: Literal["assert"]
    ts: float
    kind: Literal["window_title_contains", "pixel"]
    # For window_title_contains
    value: str | None = None
    # For pixel
    pos: Pos | None = None
    rgb: tuple[int, int, int] | None = None
    tolerance: int | None = None


class WaitUntil(BaseModel):
    """Wait until event."""
    model_config = ConfigDict(extra="forbid")
    v: Literal[1]
    type: Literal["wait_until"]
    ts: float
    kind: Literal["pixel"]
    pos: Pos
    rgb: tuple[int, int, int]
    tolerance: int = 0
    timeout_ms: int


class SessionEnd(BaseModel):
    """Session end event."""
    model_config = ConfigDict(extra="forbid")
    v: Literal[1]
    type: Literal["session_end"]
    ts: float


# Union of all trace events using discriminated union
TraceEvent = Annotated[
    Union[
        SessionStart,
        WindowSelectorEvent,
        WindowBounds,
        Click,
        Scroll,
        Assert,
        WaitUntil,
        SessionEnd,
    ],
    Field(discriminator="type")
]
TraceEvent = Union[
    SessionStart,
    WindowSelectorEvent,
    WindowBounds,
    Click,
    Scroll,
    Assert,
    WaitUntil,
    SessionEnd,
]


# StepResult (output, not part of TraceEvent union)
class StepResult(BaseModel):
    """Result of executing a step."""
    model_config = ConfigDict(extra="forbid")
    type: Literal["step_result"]
    step: int
    event_idx: int
    event_type: str
    status: Literal["ok", "skipped", "error"]
    ok: bool
    elapsed_ms: int
    dry_run: bool
    error_code: str | None = None
    message: str | None = None
    observed: dict | None = None
    anchor_used: str | None = None
    screen_final: Point | None = None
