"""Player core scheduler for trace playback."""

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Iterator

from uitrace.core.jsonl import read_events
from uitrace.core.models import Point, Rect, StepResult
from uitrace.errors import ErrorCode, UitError
from uitrace.player.executor import window_rel_to_screen

if TYPE_CHECKING:
    from uitrace.platform.base import Platform, WindowRef

PLAYABLE_EVENT_TYPES = {
    "window_selector",
    "window_bounds",
    "assert",
    "wait_until",
    "click",
    "scroll",
}


class Player:
    """Trace player with injectable clock and sleep for testing."""

    def __init__(
        self,
        *,
        platform: Platform | None = None,
        clock_ns: Callable[[], int] | None = None,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        self._platform = platform
        self._clock_ns = clock_ns or time.monotonic_ns
        self._sleep = sleep or time.sleep

    # ------------------------------------------------------------------
    # Internal helpers for real (non-dry-run) playback
    # ------------------------------------------------------------------

    def _check_permissions(self) -> None:
        """Fail-fast if accessibility permission is not granted."""
        assert self._platform is not None
        from uitrace.platform.base import PermissionStatus

        report = self._platform.check_permissions()
        if report.accessibility != PermissionStatus.granted:
            raise UitError(
                code=ErrorCode.PERMISSION_DENIED,
                message="Accessibility permission denied",
            )

    def _handle_window_selector(self, event: object) -> WindowRef | None:
        """Locate the target window from a window_selector event."""
        assert self._platform is not None
        selector = getattr(event, "selector", None)
        if selector is None:
            return None
        win = self._platform.locate(selector)
        if win is not None:
            self._platform.focus(win)
        else:
            raise UitError(
                code=ErrorCode.WINDOW_NOT_FOUND,
                message="Window not found for selector",
            )
        return win

    def _handle_window_bounds(
        self, event: object, win: WindowRef | None
    ) -> Rect:
        """Refresh window bounds. Falls back to event.bounds."""
        if win is not None and self._platform is not None:
            refreshed = self._platform.get_bounds(win)
            if refreshed is not None:
                return refreshed
        return getattr(event, "bounds", Rect(x=0, y=0, w=0, h=0))

    def _handle_click(
        self, event: object, bounds: Rect
    ) -> Point:
        """Compute screen coords and inject a click. Returns final screen point."""
        assert self._platform is not None
        pos = getattr(event, "pos", None)
        button = getattr(event, "button", "left")
        count = getattr(event, "count", 1)
        rx = pos.rx if pos else 0.5
        ry = pos.ry if pos else 0.5
        sx, sy = window_rel_to_screen(bounds, rx, ry)
        self._platform.inject_click(sx, sy, button, count)
        return Point(x=sx, y=sy)

    def _handle_scroll(
        self, event: object, bounds: Rect
    ) -> Point:
        """Compute screen coords and inject a scroll. Returns final screen point."""
        assert self._platform is not None
        pos = getattr(event, "pos", None)
        delta = getattr(event, "delta", {})
        rx = pos.rx if pos else 0.5
        ry = pos.ry if pos else 0.5
        delta_y: int = delta.get("y", 0) if isinstance(delta, dict) else 0
        sx, sy = window_rel_to_screen(bounds, rx, ry)
        self._platform.inject_scroll(sx, sy, delta_y)
        return Point(x=sx, y=sy)

    # ------------------------------------------------------------------

    def run(
        self,
        events: Iterator,
        *,
        dry_run: bool = False,
        speed: float = 1.0,
        from_step: int | None = None,
        to_step: int | None = None,
    ) -> Iterator[StepResult]:
        """Run playback over events, yielding StepResult for each playable step.

        Parameters
        ----------
        events:
            Iterator of TraceEvent objects (as returned by ``read_events``).
        dry_run:
            If True, emit ``status="ok"`` without performing injection.
        speed:
            Playback speed multiplier (e.g. 2.0 = twice as fast).
        from_step:
            First step (0-based, inclusive) to execute. ``None`` means 0.
        to_step:
            Last step (0-based, inclusive) to execute. ``None`` means unbounded.
        """
        # For real playback, check permissions up-front
        if not dry_run:
            if self._platform is None:
                raise UitError(
                    code=ErrorCode.PERMISSION_DENIED,
                    message="Platform required for real playback",
                )
            try:
                self._check_permissions()
            except UitError:
                # Emit a step_result so the CLI has at least one output line
                yield StepResult(
                    type="step_result",
                    step=0,
                    event_idx=0,
                    event_type="permission_check",
                    status="error",
                    ok=False,
                    elapsed_ms=0,
                    dry_run=False,
                    error_code=ErrorCode.PERMISSION_DENIED.name,
                    message="Accessibility permission denied",
                )
                raise

        effective_from = from_step if from_step is not None else 0
        # to_step None means no upper bound

        step = -1  # will be incremented to 0 on first playable event
        prev_ts: float | None = None  # ts of previous *in-range* step

        # State for real playback
        current_win: WindowRef | None = None
        current_bounds = Rect(x=0, y=0, w=0, h=0)

        for event_idx, event in enumerate(events):
            event_type = event.type
            if event_type not in PLAYABLE_EVENT_TYPES:
                continue

            step += 1

            in_range = step >= effective_from and (
                to_step is None or step <= to_step
            )

            if not in_range:
                yield StepResult(
                    type="step_result",
                    step=step,
                    event_idx=event_idx,
                    event_type=event_type,
                    status="skipped",
                    ok=True,
                    elapsed_ms=0,
                    dry_run=dry_run,
                )
                continue

            # Timing: sleep based on ts delta between consecutive in-range steps
            if prev_ts is not None and speed > 0:
                delta_s = event.ts - prev_ts
                if delta_s > 0:
                    self._sleep(delta_s / speed)
            prev_ts = event.ts

            if dry_run:
                yield StepResult(
                    type="step_result",
                    step=step,
                    event_idx=event_idx,
                    event_type=event_type,
                    status="ok",
                    ok=True,
                    elapsed_ms=0,
                    dry_run=True,
                )
                continue

            # --- Real playback ---
            t0 = self._clock_ns()
            screen_final: Point | None = None
            try:
                if event_type == "window_selector":
                    current_win = self._handle_window_selector(event)

                elif event_type == "window_bounds":
                    current_bounds = self._handle_window_bounds(
                        event, current_win
                    )

                elif event_type == "click":
                    screen_final = self._handle_click(event, current_bounds)

                elif event_type == "scroll":
                    screen_final = self._handle_scroll(event, current_bounds)

                elif event_type == "assert":
                    from uitrace.player.observer import (
                        check_pixel,
                        check_window_title_contains,
                    )

                    kind = getattr(event, "kind", None)
                    if kind == "window_title_contains":
                        result = check_window_title_contains(
                            self._platform,
                            current_win,
                            getattr(event, "value", "") or "",
                        )
                    elif kind == "pixel":
                        result = check_pixel(
                            self._platform,
                            current_bounds,
                            getattr(event, "pos").rx,
                            getattr(event, "pos").ry,
                            getattr(event, "rgb"),
                            getattr(event, "tolerance", 0) or 0,
                        )
                    else:
                        result = {
                            "ok": False,
                            "observed": {
                                "error": f"unknown assert kind: {kind}",
                            },
                        }

                    if not result["ok"]:
                        elapsed = (self._clock_ns() - t0) // 1_000_000
                        yield StepResult(
                            type="step_result",
                            step=step,
                            event_idx=event_idx,
                            event_type=event_type,
                            status="error",
                            ok=False,
                            elapsed_ms=int(elapsed),
                            dry_run=False,
                            error_code=ErrorCode.ASSERTION_FAILED.name,
                            message=f"Assertion failed: {kind}",
                            observed=result.get("observed"),
                        )
                        raise UitError(
                            code=ErrorCode.ASSERTION_FAILED,
                            message=f"Assertion failed: {kind}",
                        )

                elif event_type == "wait_until":
                    kind = getattr(event, "kind", None)
                    if kind == "pixel":
                        from uitrace.player.observer import wait_until_pixel

                        result = wait_until_pixel(
                            self._platform,
                            current_bounds,
                            getattr(event, "pos").rx,
                            getattr(event, "pos").ry,
                            getattr(event, "rgb"),
                            getattr(event, "tolerance", 0) or 0,
                            getattr(event, "timeout_ms", 5000),
                        )
                        elapsed = (self._clock_ns() - t0) // 1_000_000
                        if not result["ok"]:
                            yield StepResult(
                                type="step_result",
                                step=step,
                                event_idx=event_idx,
                                event_type=event_type,
                                status="error",
                                ok=False,
                                elapsed_ms=int(elapsed),
                                dry_run=False,
                                error_code=ErrorCode.ASSERTION_FAILED.name,
                                message="wait_until pixel timed out",
                                observed=result.get("observed"),
                            )
                            raise UitError(
                                code=ErrorCode.ASSERTION_FAILED,
                                message="wait_until pixel timed out",
                            )
                        # Fall through to success
                    elif kind == "window_found":
                        selector = getattr(event, "selector", None)
                        timeout_ms = getattr(event, "timeout_ms", 5000)
                        poll_interval = 0.05  # 50ms
                        deadline = self._clock_ns() + timeout_ms * 1_000_000
                        found_win = None
                        while self._clock_ns() < deadline:
                            found_win = self._platform.locate(selector)
                            if found_win is not None:
                                break
                            self._sleep(poll_interval)
                        elapsed = (self._clock_ns() - t0) // 1_000_000
                        if found_win is None:
                            yield StepResult(
                                type="step_result",
                                step=step,
                                event_idx=event_idx,
                                event_type=event_type,
                                status="error",
                                ok=False,
                                elapsed_ms=int(elapsed),
                                dry_run=False,
                                error_code=ErrorCode.WINDOW_NOT_FOUND.name,
                                message=f"wait_until window_found timed out after {timeout_ms}ms",
                            )
                            raise UitError(
                                code=ErrorCode.WINDOW_NOT_FOUND,
                                message=f"wait_until window_found timed out after {timeout_ms}ms",
                            )
                        # Update current window state
                        current_win = found_win
                        self._platform.focus(current_win)
                        # Fall through to success
                    else:
                        elapsed = (self._clock_ns() - t0) // 1_000_000
                        yield StepResult(
                            type="step_result",
                            step=step,
                            event_idx=event_idx,
                            event_type=event_type,
                            status="error",
                            ok=False,
                            elapsed_ms=int(elapsed),
                            dry_run=False,
                            error_code="NOT_IMPLEMENTED",
                            message=f"unknown wait_until kind: {kind}",
                        )
                        continue

            except UitError as exc:
                # assert and wait_until already yield their own error
                # StepResult before raising; avoid double-yield for those.
                if event_type in ("assert", "wait_until"):
                    raise
                elapsed = (self._clock_ns() - t0) // 1_000_000
                yield StepResult(
                    type="step_result",
                    step=step,
                    event_idx=event_idx,
                    event_type=event_type,
                    status="error",
                    ok=False,
                    elapsed_ms=int(elapsed),
                    dry_run=False,
                    error_code=ErrorCode.INJECTION_FAILED.name,
                    message=str(exc),
                )
                continue

            elapsed = (self._clock_ns() - t0) // 1_000_000
            yield StepResult(
                type="step_result",
                step=step,
                event_idx=event_idx,
                event_type=event_type,
                status="ok",
                ok=True,
                elapsed_ms=int(elapsed),
                dry_run=False,
                screen_final=screen_final,
            )


def cmd_play(
    path: Path,
    *,
    dry_run: bool = False,
    speed: float = 1.0,
    from_step: int | None = None,
    to_step: int | None = None,
) -> Iterator[StepResult]:
    """Convenience wrapper: read events from file and play them."""
    platform = None
    if not dry_run:
        from uitrace.platform import get_platform

        platform = get_platform()
    player = Player(platform=platform)
    yield from player.run(
        read_events(path),
        dry_run=dry_run,
        speed=speed,
        from_step=from_step,
        to_step=to_step,
    )
