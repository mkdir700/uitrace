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

    def _handle_window_selector(self, event: object) -> tuple[WindowRef, Rect] | None:
        """Locate the target window from a window_selector event."""
        assert self._platform is not None
        selector = getattr(event, "selector", None)
        if selector is None:
            return None
        win = self._platform.locate(selector)
        if win is not None:
            baseline = self._platform.get_bounds(win) or win.bounds
            self._platform.focus(win)
            settled = self._wait_bounds_settle_after_focus(win, baseline)
            return (win, settled)
        else:
            raise UitError(
                code=ErrorCode.WINDOW_NOT_FOUND,
                message="Window not found for selector",
            )

    def _handle_window_bounds(
        self, event: object, win: WindowRef | None
    ) -> Rect:
        """Refresh window bounds. Falls back to event.bounds."""
        if win is not None and self._platform is not None:
            refreshed = self._platform.get_bounds(win)
            if refreshed is not None:
                return refreshed
        return getattr(event, "bounds", Rect(x=0, y=0, w=0, h=0))

    def _refresh_bounds(
        self, win: WindowRef | None, bounds: Rect
    ) -> Rect:
        """Best-effort refresh for current window bounds."""
        if win is not None and self._platform is not None:
            refreshed = self._platform.get_bounds(win)
            if refreshed is not None:
                return refreshed
        return bounds

    def _wait_bounds_settle_after_focus(
        self, win: "WindowRef", baseline: Rect
    ) -> Rect:
        """Wait for window bounds to change from *baseline* then stabilise.

        After a focus()+center, the system may take several frames to update
        the window position.  This helper polls ``get_bounds`` until it
        detects a *change* from *baseline* AND that the new value is stable
        (read identically ``STABLE_READS`` consecutive times).

        On timeout the last observed bounds are returned (or *baseline* if
        ``get_bounds`` keeps returning ``None``).
        """
        import math

        POLL_INTERVAL_S = 0.05
        TIMEOUT_MS = 1000
        STABLE_READS = 2

        assert self._platform is not None
        max_polls = math.ceil(TIMEOUT_MS / (POLL_INTERVAL_S * 1000))

        change_observed = False
        last_bounds: Rect = baseline
        stable_count = 0

        for _ in range(max_polls):
            current = self._platform.get_bounds(win)
            if current is None:
                self._sleep(POLL_INTERVAL_S)
                continue

            if not change_observed:
                if current != baseline:
                    change_observed = True
                    last_bounds = current
                    stable_count = 1
                else:
                    self._sleep(POLL_INTERVAL_S)
                    continue
            else:
                if current == last_bounds:
                    stable_count += 1
                else:
                    last_bounds = current
                    stable_count = 1

            if stable_count >= STABLE_READS:
                return last_bounds

            self._sleep(POLL_INTERVAL_S)

        return last_bounds

    def _handle_click(
        self, event: object, bounds: Rect
    ) -> Point:
        """Compute screen coords and inject a click. Returns final screen point."""
        assert self._platform is not None
        pos = getattr(event, "pos", None)
        button = getattr(event, "button", "left")
        count = getattr(event, "count", 1)
        if pos is None:
            raise UitError(
                code=ErrorCode.SCHEMA_INVALID,
                message="Click event missing 'pos' field",
            )
        rx = pos.rx
        ry = pos.ry
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
        if pos is None:
            raise UitError(
                code=ErrorCode.SCHEMA_INVALID,
                message="Scroll event missing 'pos' field",
            )
        rx = pos.rx
        ry = pos.ry
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
                    sel_result = self._handle_window_selector(event)
                    if sel_result is not None:
                        current_win, current_bounds = sel_result

                elif event_type == "window_bounds":
                    current_bounds = self._handle_window_bounds(
                        event, current_win
                    )

                elif event_type == "click":
                    current_bounds = self._refresh_bounds(current_win, current_bounds)
                    screen_final = self._handle_click(event, current_bounds)

                elif event_type == "scroll":
                    current_bounds = self._refresh_bounds(current_win, current_bounds)
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
                        current_bounds = self._refresh_bounds(current_win, current_bounds)
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

                        current_bounds = self._refresh_bounds(current_win, current_bounds)
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
                        assert self._platform is not None
                        from uitrace.core.models import WindowSelector as WS
                        selector = getattr(event, "selector", None)
                        if not isinstance(selector, WS):
                            selector = WS.model_validate(
                                selector
                            ) if selector else None
                        if selector is None or all(
                            v is None
                            for v in (
                                selector.pid,
                                selector.app,
                                selector.title,
                                selector.title_regex,
                                selector.bundle_id,
                            )
                        ):
                            raise UitError(
                                code=ErrorCode.SCHEMA_INVALID,
                                message="wait_until window_found requires a non-empty selector",
                            )
                        timeout_ms = getattr(event, "timeout_ms", 5000)
                        poll_interval = 0.05  # 50ms
                        deadline = (
                            self._clock_ns() + timeout_ms * 1_000_000
                        )
                        found_win = None
                        while self._clock_ns() < deadline:
                            found_win = self._platform.locate(selector)
                            if found_win is not None:
                                break
                            self._sleep(poll_interval)
                        elapsed = (self._clock_ns() - t0) // 1_000_000
                        if found_win is None:
                            msg = (
                                "wait_until window_found timed out"
                                f" after {timeout_ms}ms"
                            )
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
                                message=msg,
                            )
                            raise UitError(
                                code=ErrorCode.WINDOW_NOT_FOUND,
                                message=msg,
                            )
                        # Update current window state
                        current_win = found_win
                        baseline = self._platform.get_bounds(current_win) or current_win.bounds
                        self._platform.focus(current_win)
                        current_bounds = self._wait_bounds_settle_after_focus(current_win, baseline)
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
