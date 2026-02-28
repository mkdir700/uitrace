"""Show command for trace summaries."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from rich.console import Console
from rich.table import Table

from uitrace.core.jsonl import read_events

PLAYABLE_EVENT_TYPES = {"window_bounds", "assert", "wait_until", "click", "scroll"}


def build_summary(path: Path) -> dict:
    events = list(read_events(path))
    types = Counter(event.type for event in events)
    steps_total = sum(1 for event in events if event.type in PLAYABLE_EVENT_TYPES)
    ts_max = max((event.ts for event in events), default=0.0)
    return {
        "events_total": len(events),
        "steps_total": steps_total,
        "ts_max": ts_max,
        "types": dict(types),
    }


def cmd_show(path: Path, as_json: bool) -> None:
    summary = build_summary(path)
    if as_json:
        print(json.dumps(summary, ensure_ascii=False))
        return

    console = Console()
    table = Table(title=f"Trace Summary: {path.name}")
    table.add_column("Metric")
    table.add_column("Value")
    table.add_row("events_total", str(summary["events_total"]))
    table.add_row("steps_total", str(summary["steps_total"]))
    table.add_row("ts_max", str(summary["ts_max"]))
    table.add_row("types", json.dumps(summary["types"], ensure_ascii=False))
    console.print(table)
