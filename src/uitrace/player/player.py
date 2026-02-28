"""Player core scheduler for trace playback."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Callable, Iterator

from uitrace.core.jsonl import read_events
from uitrace.core.models import StepResult
from uitrace.errors import ErrorCode, UitError

PLAYABLE_EVENT_TYPES = {"window_bounds", "assert", "wait_until", "click", "scroll"}


class Player:
    """Trace player with injectable clock and sleep for testing."""

    def __init__(
        self,
        *,
        clock_ns: Callable[[], int] | None = None,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        self._clock_ns = clock_ns or time.monotonic_ns
        self._sleep = sleep or time.sleep

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
        effective_from = from_step if from_step is not None else 0
        # to_step None means no upper bound

        step = -1  # will be incremented to 0 on first playable event
        prev_ts: float | None = None  # ts of previous *in-range* step

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

            # Non-dry-run: permission denied until real injection (Task 13)
            yield StepResult(
                type="step_result",
                step=step,
                event_idx=event_idx,
                event_type=event_type,
                status="error",
                ok=False,
                elapsed_ms=0,
                dry_run=False,
                error_code=ErrorCode.PERMISSION_DENIED.name,
                message="Playback requires permissions",
            )
            raise UitError(
                code=ErrorCode.PERMISSION_DENIED,
                message="Playback requires permissions",
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
    player = Player()
    yield from player.run(
        read_events(path),
        dry_run=dry_run,
        speed=speed,
        from_step=from_step,
        to_step=to_step,
    )
