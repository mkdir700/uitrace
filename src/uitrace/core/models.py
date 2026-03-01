"""Core models for uitrace trace events."""

from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator


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
    l: int  # noqa: E741
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
    delta: dict[str, int]
    phase: int | None = None
    momentum_phase: int | None = None
    is_continuous: bool | None = None


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
    kind: Literal["pixel", "window_found"]
    # pixel-specific fields
    pos: Pos | None = None
    rgb: tuple[int, int, int] | None = None
    tolerance: int | None = None
    # window_found-specific fields
    selector: WindowSelector | None = None
    # shared fields
    timeout_ms: int

    @model_validator(mode="after")
    def _check_kind_fields(self) -> "WaitUntil":
        if self.kind == "pixel":
            if self.pos is None or self.rgb is None:
                raise ValueError("kind='pixel' requires pos and rgb")
            if self.selector is not None:
                raise ValueError("kind='pixel' must not have selector")
        elif self.kind == "window_found":
            if self.selector is None:
                raise ValueError("kind='window_found' requires selector")
            if self.pos is not None or self.rgb is not None or self.tolerance is not None:
                raise ValueError("kind='window_found' must not have pos, rgb, or tolerance")
        return self


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
    Field(discriminator="type"),
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
