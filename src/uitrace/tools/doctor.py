"""Doctor command for permissions diagnostics."""

import json
import sys
from typing import Any


def _check_accessibility() -> dict[str, Any]:
    """Check Accessibility permission."""
    try:
        from ApplicationServices import AXIsProcessTrusted  # type: ignore[import-untyped]

        trusted = AXIsProcessTrusted()
        return {"status": "granted" if trusted else "denied"}
    except ImportError:
        pass
    try:
        from Quartz import AXIsProcessTrusted  # type: ignore[import-untyped]

        trusted = AXIsProcessTrusted()
        return {"status": "granted" if trusted else "denied"}
    except ImportError:
        pass
    return {"status": "unknown"}


def _check_input_monitoring() -> dict[str, Any]:
    """Check Input Monitoring permission via event tap probe."""
    try:
        from Quartz import (  # type: ignore[import-untyped]
            CGEventMaskBit,
            CGEventTapCreate,
            CGEventTapEnable,
            kCGEventLeftMouseDown,
            kCGEventTapOptionListenOnly,
            kCGHeadInsertEventTap,
            kCGHIDEventTap,
        )

        mask = CGEventMaskBit(kCGEventLeftMouseDown)
        tap = CGEventTapCreate(
            kCGHIDEventTap,
            kCGHeadInsertEventTap,
            kCGEventTapOptionListenOnly,
            mask,
            lambda *args: args[-1],  # minimal callback
            None,
        )
        if tap is None:
            return {"status": "denied"}
        CGEventTapEnable(tap, False)
        return {"status": "granted"}
    except ImportError:
        return {"status": "unknown"}
    except Exception:
        return {"status": "unknown"}


def _check_screen_recording() -> dict[str, Any]:
    """Check Screen Recording permission."""
    try:
        from Quartz import (  # type: ignore[import-untyped]
            CGWindowListCopyWindowInfo,
            kCGNullWindowID,
            kCGWindowListOptionOnScreenOnly,
        )

        windows = CGWindowListCopyWindowInfo(
            kCGWindowListOptionOnScreenOnly, kCGNullWindowID
        )
        if windows is None:
            return {"status": "denied"}
        for w in windows:
            name = w.get("kCGWindowOwnerName", "") or w.get("kCGWindowName", "")
            if name:
                return {"status": "granted"}
        return {"status": "denied"}
    except ImportError:
        return {"status": "unknown"}
    except Exception:
        return {"status": "unknown"}


def cmd_doctor(as_json: bool = False) -> dict[str, Any]:
    """Run doctor diagnostics and return report dict. Also prints output."""
    hints: list[str] = []

    accessibility = _check_accessibility()
    input_monitoring = _check_input_monitoring()
    screen_recording = _check_screen_recording()

    if accessibility["status"] == "denied":
        hints.append(
            "Accessibility not granted. Open: "
            'open "x-apple.systempreferences:'
            'com.apple.preference.security?Privacy_Accessibility"'
        )
    if input_monitoring["status"] == "denied":
        hints.append(
            "Input Monitoring not granted. Open: "
            'open "x-apple.systempreferences:'
            'com.apple.preference.security?Privacy_ListenEvent"'
        )
    if screen_recording["status"] == "denied":
        hints.append(
            "Screen Recording not granted. Open: "
            'open "x-apple.systempreferences:'
            'com.apple.preference.security?Privacy_ScreenCapture"'
        )

    if sys.platform != "darwin":
        hints.append("uitrace requires macOS for full functionality")

    report = {
        "platform": sys.platform,
        "executable": sys.executable,
        "permissions": {
            "accessibility": accessibility,
            "input_monitoring": input_monitoring,
            "screen_recording": screen_recording,
        },
        "hints": hints,
    }

    if as_json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        _print_rich(report)

    return report


def _print_rich(report: dict[str, Any]) -> None:
    """Print rich formatted doctor output."""
    from rich.console import Console
    from rich.table import Table

    console = Console()
    console.print(f"[bold]Platform:[/bold] {report['platform']}")
    console.print(f"[bold]Executable:[/bold] {report['executable']}")

    table = Table(title="Permissions")
    table.add_column("Permission")
    table.add_column("Status")

    for name, perm in report["permissions"].items():
        status = perm["status"]
        style = (
            "green"
            if status == "granted"
            else "red"
            if status == "denied"
            else "yellow"
        )
        table.add_row(name, f"[{style}]{status}[/{style}]")

    console.print(table)

    if report["hints"]:
        console.print("\n[bold yellow]Hints:[/bold yellow]")
        for hint in report["hints"]:
            console.print(f"  - {hint}")
