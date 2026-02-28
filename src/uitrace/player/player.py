"""Minimal play behavior for MVP acceptance."""

from pathlib import Path
from typing import Iterator

from uitrace.core.jsonl import read_events
from uitrace.core.models import StepResult
from uitrace.errors import ErrorCode, UitError

PLAYABLE_EVENT_TYPES = {"window_bounds", "assert", "wait_until", "click", "scroll"}


def cmd_play(path: Path, dry_run: bool) -> Iterator[StepResult]:
    """Generate step_result rows for play command."""
    step = 0
    for event_idx, event in enumerate(read_events(path), start=1):
        event_type = event.type
        if event_type not in PLAYABLE_EVENT_TYPES:
            continue

        step += 1

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
