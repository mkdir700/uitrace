"""Merge raw events into higher-level trace events.

The main entry point is :func:`merge_mouse_events` which consumes an iterable
of normalised raw events and yields merged trace-level dicts (click, scroll).
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Iterator

logger = logging.getLogger(__name__)

# Timing thresholds (seconds)
_CLICK_TIMEOUT = 0.5  # max gap between mouse_down and mouse_up
_DOUBLE_CLICK_TIMEOUT = 0.3  # max gap between two clicks for double-click
_SCROLL_COALESCE_WINDOW = 0.05  # max gap between consecutive scroll events


def merge_mouse_events(raw_events: Iterable[dict]) -> Iterator[dict]:
    """Merge raw mouse / scroll events into trace events.

    Yields dicts with the following shapes:

    * **click** – ``{"kind": "click", "ts": …, "x": …, "y": …, "button": …, "count": 1|2}``
    * **scroll** – ``{"kind": "scroll", "ts": …, "x": …, "y": …, "delta_y": …}``

    Rules
    -----
    1. A ``mouse_down`` followed by a ``mouse_up`` on the same button within
       500 ms produces a *click*.
    2. An orphaned ``mouse_down`` (no matching ``mouse_up`` within 500 ms) is
       discarded with a debug log message.
    3. Two clicks at the same position within 300 ms are merged into a single
       click with ``count=2``.
    4. Consecutive ``scroll`` events within a 50 ms window are coalesced –
       their ``delta_y`` values are accumulated.
    """
    # We buffer events so we can look-ahead for matching mouse_up / scroll
    # coalescing.  Because the input is finite and typically small, we
    # materialise to a list for simpler index-based access.
    events = list(raw_events)
    n = len(events)
    i = 0

    # Buffer the last emitted click so we can detect double-clicks.
    pending_click: dict | None = None

    def _flush_click() -> dict | None:
        """Return the pending click (if any) and clear the buffer."""
        nonlocal pending_click
        click = pending_click
        pending_click = None
        return click

    while i < n:
        evt = events[i]
        kind = evt.get("kind")

        # -- scroll coalescing ------------------------------------------
        if kind == "scroll":
            # Flush any pending click first.
            flushed = _flush_click()
            if flushed is not None:
                yield flushed

            # Gather consecutive scroll events within the coalesce window.
            group = [evt]
            j = i + 1
            while j < n:
                nxt = events[j]
                if nxt.get("kind") != "scroll":
                    break
                if nxt["ts"] - events[j - 1]["ts"] > _SCROLL_COALESCE_WINDOW:
                    break
                group.append(nxt)
                j += 1

            # Determine if any event carries high-fidelity phase info.
            has_phase = any(
                (e.get("phase") is not None and e.get("phase") != 0)
                or (e.get("momentum_phase") is not None and e.get("momentum_phase") != 0)
                for e in group
            )

            if has_phase:
                # High-fidelity: yield each event individually.
                for e in group:
                    yield dict(e)
            else:
                # Legacy path: coalesce into a single event.
                first = group[0]
                acc_dy = sum(e.get("delta_y", 0) for e in group)
                acc_dx = sum(e.get("delta_x", 0) for e in group)
                merged: dict = {
                    "kind": "scroll",
                    "ts": first["ts"],
                    "x": first["x"],
                    "y": first["y"],
                    "delta_y": acc_dy,
                    "delta_x": acc_dx,
                }
                # Pass through optional fields from the first event.
                for key in ("phase", "momentum_phase", "is_continuous"):
                    if key in first:
                        merged[key] = first[key]
                yield merged

            i = j
            continue

        # -- mouse_down → look for matching mouse_up -------------------
        if kind == "mouse_down":
            button = evt.get("button", "left")
            down_ts = evt["ts"]
            matched = False
            j = i + 1
            while j < n:
                candidate = events[j]
                # Only consider mouse_up with matching button.
                if (
                    candidate.get("kind") == "mouse_up"
                    and candidate.get("button", "left") == button
                ):
                    if candidate["ts"] - down_ts <= _CLICK_TIMEOUT:
                        # Successful click.
                        new_click: dict = {
                            "kind": "click",
                            "ts": down_ts,
                            "x": evt["x"],
                            "y": evt["y"],
                            "button": button,
                            "count": 1,
                        }
                        # Double-click detection: merge with pending_click
                        # if same position and within threshold.
                        if (
                            pending_click is not None
                            and pending_click["x"] == new_click["x"]
                            and pending_click["y"] == new_click["y"]
                            and pending_click["button"] == new_click["button"]
                            and new_click["ts"] - pending_click["ts"] <= _DOUBLE_CLICK_TIMEOUT
                        ):
                            pending_click["count"] = 2
                            # Don't buffer new_click; the merged result
                            # stays in pending_click.
                        else:
                            # Flush previous pending click.
                            flushed = _flush_click()
                            if flushed is not None:
                                yield flushed
                            pending_click = new_click
                        i = j + 1
                        matched = True
                        break
                    else:
                        # mouse_up too late → this mouse_down is orphan.
                        break
                # If we encounter another mouse_down for the same button
                # before a mouse_up, the original mouse_down is orphaned
                # when the timestamp exceeds the timeout.
                if (
                    candidate.get("kind") == "mouse_down"
                    and candidate.get("button", "left") == button
                ):
                    if candidate["ts"] - down_ts > _CLICK_TIMEOUT:
                        break
                j += 1

            if not matched:
                logger.debug("orphan mouse_down at ts=%.3f discarded", down_ts)
                i += 1
            continue

        # -- mouse_up without preceding mouse_down → skip ---------------
        if kind == "mouse_up":
            i += 1
            continue

        # -- unknown kind → skip ----------------------------------------
        i += 1

    # Flush any remaining pending click.
    flushed = _flush_click()
    if flushed is not None:
        yield flushed
