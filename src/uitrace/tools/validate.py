"""Validate command for trace files."""

from pathlib import Path


def cmd_validate(path: Path) -> None:
    """Validate a trace JSONL file.

    Reads all events and validates them.
    Prints summary to stdout on success.

    Raises:
        UitError: If validation fails
    """
    from uitrace.core.jsonl import read_events

    count = 0
    for event in read_events(path):
        count += 1

    print(f"Validated {count} events from {path.name}")
