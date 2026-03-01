"""Normalize raw platform events into a consistent format."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Fields expected on every normalized event.
_REQUIRED_FIELDS = ("kind", "ts", "x", "y")

# Known raw event kinds and their extra fields.
_KIND_EXTRAS: dict[str, list[str]] = {
    "mouse_down": ["button"],
    "mouse_up": ["button"],
    "scroll": ["delta_y", "delta_x", "phase", "momentum_phase", "is_continuous"],
}


def normalize_raw_event(raw: dict) -> dict:
    """Normalize a single raw platform event.

    - Coerces *x* / *y* coordinates to ``int``.
    - Ensures *button* is present for mouse events (defaults to ``"left"``).
    - Passes through *delta_y* for scroll events.

    Returns a new dict with normalized field names and types.

    Raises
    ------
    ValueError
        If the event is missing required fields or has an unknown *kind*.
    """
    kind = raw.get("kind")
    if kind is None:
        raise ValueError(f"raw event missing 'kind': {raw!r}")

    if kind not in _KIND_EXTRAS:
        raise ValueError(f"unknown raw event kind: {kind!r}")

    ts = raw.get("ts")
    if ts is None:
        raise ValueError(f"raw event missing 'ts': {raw!r}")

    x = raw.get("x")
    y = raw.get("y")
    if x is None or y is None:
        raise ValueError(f"raw event missing 'x' or 'y': {raw!r}")

    result: dict = {
        "kind": kind,
        "ts": float(ts),
        "x": int(x),
        "y": int(y),
    }

    if kind in ("mouse_down", "mouse_up"):
        result["button"] = raw.get("button", "left")
    elif kind == "scroll":
        delta_y = raw.get("delta_y", 0)
        result["delta_y"] = int(delta_y)
        result["delta_x"] = int(raw.get("delta_x", 0))

        phase = raw.get("phase")
        result["phase"] = int(phase) if phase is not None else None

        momentum_phase = raw.get("momentum_phase")
        result["momentum_phase"] = int(momentum_phase) if momentum_phase is not None else None

        is_cont = raw.get("is_continuous")
        result["is_continuous"] = bool(is_cont) if is_cont is not None else None

    return result
