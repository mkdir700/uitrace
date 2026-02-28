"""JSONL IO for trace events."""
import json
from pathlib import Path
from typing import Any, Generator, Iterator

from uitrace.core.models import TraceEvent
from uitrace.errors import ErrorCode, UitError


def iter_json_objects(path: Path) -> Generator[tuple[int, dict[str, Any]], None, None]:
    """Iterate JSON objects from a JSONL file.
    
    Yields: (line_number, parsed_object)
    """
    with open(path, "r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as e:
                raise UitError(
                    code=ErrorCode.SCHEMA_INVALID,
                    message=f"Invalid JSON at line {line_no}: {e}",
                )
            yield line_no, obj


def read_events(path: Path) -> Iterator[TraceEvent]:
    """Read and validate trace events from a JSONL file.
    
    Yields: TraceEvent objects
    
    Raises:
        UitError: If any line is invalid
    """
    for line_no, obj in iter_json_objects(path):
        try:
            # Try to find the right model based on 'type' field
            event_type = obj.get("type")
            if event_type == "session_start":
                from uitrace.core.models import SessionStart
                yield SessionStart.model_validate(obj)
            elif event_type == "window_selector":
                from uitrace.core.models import WindowSelectorEvent
                yield WindowSelectorEvent.model_validate(obj)
            elif event_type == "window_bounds":
                from uitrace.core.models import WindowBounds
                yield WindowBounds.model_validate(obj)
            elif event_type == "click":
                from uitrace.core.models import Click
                yield Click.model_validate(obj)
            elif event_type == "scroll":
                from uitrace.core.models import Scroll
                yield Scroll.model_validate(obj)
            elif event_type == "assert":
                from uitrace.core.models import Assert
                yield Assert.model_validate(obj)
            elif event_type == "wait_until":
                from uitrace.core.models import WaitUntil
                yield WaitUntil.model_validate(obj)
            elif event_type == "session_end":
                from uitrace.core.models import SessionEnd
                yield SessionEnd.model_validate(obj)
            else:
                raise UitError(
                    code=ErrorCode.SCHEMA_INVALID,
                    message=f"Unknown event type at line {line_no}: {event_type}",
                )
        except Exception as e:
            if isinstance(e, UitError):
                raise
            raise UitError(
                code=ErrorCode.SCHEMA_INVALID,
                message=f"Validation error at line {line_no}: {e}",
                details={"line": line_no, "error": str(e)},
            )


def write_event(path: Path, event: TraceEvent) -> None:
    """Write a single trace event to a JSONL file."""
    with open(path, "a", encoding="utf-8") as f:
        json.dump(event.model_dump(), f, separators=(",", ":"), ensure_ascii=False)
        f.write("\n")
