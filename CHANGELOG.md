# Changelog

## 0.2.0 — High-Fidelity Scroll

Refactored scroll recording and playback pipeline for accurate reproduction of both trackpad and mouse wheel scrolling.

### New Features

- **Scroll phase capture**: Record scroll phase sequences (began → changed → ended → momentum) from trackpad events
- **Momentum phase support**: Capture and replay inertial scrolling after finger lift
- **Horizontal scroll**: Support `delta.x` alongside `delta.y` for two-axis scrolling
- **Device type detection**: Distinguish trackpad (`is_continuous: true`) from mouse wheel (`is_continuous: false`) via CGEvent field inspection
- **Phase-aware merge**: Phased scroll events are preserved individually (no coalescing); legacy events without phase data still coalesce as before
- **Phase-aware injection**: Replay sets scroll phase and momentum phase on injected CGEvents, with correct scroll unit selection (pixel for trackpad, line for mouse wheel)

### Backward Compatibility

- Trace format remains `v: 1` — no schema version bump
- All new Scroll fields (`phase`, `momentum_phase`, `is_continuous`) are optional with `None` defaults
- Old JSONL files (without new fields) validate and play back correctly
- New JSONL files will not work on uitrace < 0.2.0 (optional fields are silently rejected by `extra="forbid"`)

## 0.1.0 — Initial Release

First public release of **uitrace** — a macOS UI trace tool for recording and playing back user interactions.

### Highlights

- Record mouse clicks and scrolls in any macOS window via Quartz event tap
- Play back recordings with real injection or dry-run mode
- Multi-window recording with automatic window-switch detection
- Structured JSONL trace format with Pydantic v2 validation
- Built-in permission diagnostics

### Recording

- Capture mouse clicks and scroll events via macOS Quartz event tap
- `--follow any` mode: automatically follow focus across windows, inserting `wait_until(window_found)` steps at switch points
- `--countdown` option for timed start
- Graceful stop with Ctrl+C, writing `session_end` event
- Automatic detection of event tap enable failure on macOS 15+

### Playback

- Real playback: locate target window, center and settle bounds, then inject Quartz events
- Dry-run mode (`--dry-run`): validate trace execution without permissions — suitable for CI
- Speed control (`--speed`) and step slicing (`--from-step` / `--to-step`)
- Execute `assert` steps (pixel color validation)
- Execute `wait_until` steps (pixel match, window appearance)
- Step-level results emitted as JSONL for automation

### CLI Commands

| Command    | Description                          |
|------------|--------------------------------------|
| `record`   | Record user interactions             |
| `play`     | Play back a trace file               |
| `show`     | Display trace summary                |
| `validate` | Validate trace against schema        |
| `doctor`   | Check macOS permission status        |
| `list`     | List visible windows                 |

### Trace Format (v1)

- JSONL: one JSON object per line
- Event types: `session_start`, `window_selector`, `window_bounds`, `assert`, `wait_until`, `click`, `scroll`, `session_end`
- `wait_until` kinds: `pixel` (color match) and `window_found` (window appearance)
- All events carry schema version (`v: 1`) and timestamp (`ts`)

### Platform

- macOS support (Apple Silicon and Intel)
- Platform abstraction layer for future cross-platform expansion
- Requires Python 3.12+

### CI / Tooling

- PyPI publishing via GitHub Actions with OIDC Trusted Publishing
- Pre-commit hooks: ruff lint + format
- CI: ruff, mypy, pytest
