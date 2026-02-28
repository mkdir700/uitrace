"""CLI entry point for uitrace."""

import json
import sys
from pathlib import Path

import typer

from uitrace.errors import UitError, format_error
from uitrace.player import cmd_play
from uitrace.tools.show import cmd_show
from uitrace.tools.validate import cmd_validate

app = typer.Typer(add_completion=False, no_args_is_help=True)


@app.command("list")
def list_windows(
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """List available windows."""
    from uitrace.platform import get_platform

    try:
        platform = get_platform()
        windows = platform.list_windows()
    except UitError as e:
        if as_json:
            print(json.dumps([], ensure_ascii=False))
        print(format_error(e), file=sys.stderr)
        raise typer.Exit(code=int(e.code))

    result = []
    for idx, w in enumerate(windows):
        entry = {
            "id": idx,
            "window_number": w.window_number,
            "owner_name": w.owner_name,
            "pid": w.pid,
            "title": w.title,
            "bounds": {"x": w.bounds.x, "y": w.bounds.y, "w": w.bounds.w, "h": w.bounds.h},
        }
        result.append(entry)

    if as_json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        from rich.console import Console
        from rich.table import Table

        console = Console()
        table = Table(title="Windows")
        table.add_column("id", justify="right")
        table.add_column("owner_name")
        table.add_column("pid", justify="right")
        table.add_column("title")
        table.add_column("bounds")
        for entry in result:
            table.add_row(
                str(entry["id"]),
                entry["owner_name"] or "",
                str(entry["pid"] or ""),
                entry["title"] or "",
                f'{entry["bounds"]["x"]},{entry["bounds"]["y"]}'
                f' {entry["bounds"]["w"]}x{entry["bounds"]["h"]}',
            )
        console.print(table)


@app.command("record")
def record():
    """Record UI interactions."""
    raise typer.Exit(code=2)


@app.command("play")
def play(
    path: Path = typer.Argument(..., help="Path to trace JSONL file"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Simulate without injection"),
    speed: float = typer.Option(1.0, "--speed", help="Playback speed multiplier"),
    from_step: int | None = typer.Option(None, "--from-step", help="Start step (0-based)"),
    to_step: int | None = typer.Option(None, "--to-step", help="End step inclusive (0-based)"),
):
    """Play back recorded interactions."""
    try:
        for step_result in cmd_play(
            path,
            dry_run=dry_run,
            speed=speed,
            from_step=from_step,
            to_step=to_step,
        ):
            print(
                json.dumps(
                    step_result.model_dump(exclude_none=True),
                    separators=(",", ":"),
                    ensure_ascii=False,
                )
            )
    except UitError as e:
        raise typer.Exit(code=int(e.code))


@app.command("show")
def show(
    path: Path = typer.Argument(..., help="Path to trace JSONL file"),
    as_json: bool = typer.Option(False, "--json", help="Output summary as JSON"),
):
    """Show trace summary."""
    try:
        cmd_show(path, as_json=as_json)
    except UitError as e:
        print(format_error(e), file=sys.stderr)
        raise typer.Exit(code=int(e.code))


@app.command("validate")
def validate(path: Path = typer.Argument(..., help="Path to trace JSONL file")):
    """Validate trace file."""
    try:
        cmd_validate(path)
    except UitError as e:
        print(format_error(e), file=sys.stderr)
        raise typer.Exit(code=int(e.code))


@app.command("doctor")
def doctor(
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Diagnose permissions and environment."""
    from uitrace.tools.doctor import cmd_doctor

    report = cmd_doctor(as_json=as_json)
    all_granted = all(
        p["status"] == "granted" for p in report["permissions"].values()
    )
    if not all_granted:
        raise typer.Exit(code=11)


def main():
    """Entry point for console script."""
    try:
        app()
    except UitError as e:
        print(format_error(e), file=sys.stderr)
        sys.exit(e.code)
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        sys.exit(130)
