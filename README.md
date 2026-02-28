## uitrace

UI trace tool for macOS: record and playback user interactions.

### Features

- Record mouse clicks and scrolls in any macOS window
- Play back recordings with speed control and step slicing
- Structured JSONL trace format with strict Pydantic v2 validation
- Dry-run mode for CI/automated testing (no permissions required)
- Permission diagnostics via `doctor` command

### Requirements

- macOS (Apple Silicon or Intel)
- Python 3.12+
- uv (recommended)

### Quick Start

```bash
uv sync
uv run uitrace --help
```

### Permissions

uitrace requires macOS system permissions depending on the command:

| Command | Accessibility | Input Monitoring | Screen Recording |
|---------|:---:|:---:|:---:|
| `list` | - | - | Optional (for window titles) |
| `doctor` | Check | Check | Check |
| `record` | Required | Required | `--follow any` mode |
| `play` | Required | - | - |
| `play --dry-run` | - | - | - |
| `validate` / `show` | - | - | - |

Grant permissions in: **System Settings > Privacy & Security**

Important: The permission target is your **terminal app** (Terminal.app, iTerm2, VS Code, Ghostty, etc.), not the Python binary. After granting, **restart the terminal**.

### Usage Examples

```bash
# Check permissions
uv run uitrace doctor
uv run uitrace doctor --json

# List windows
uv run uitrace list
uv run uitrace list --json

# Record interactions (Ctrl+C to stop)
uv run uitrace record --out trace.jsonl --window-id 0 --countdown 3

# Validate a trace file
uv run uitrace validate trace.jsonl

# Show trace summary
uv run uitrace show trace.jsonl
uv run uitrace show --json trace.jsonl

# Playback (dry-run, no permissions needed)
uv run uitrace play --dry-run trace.jsonl

# Playback with speed and step slicing
uv run uitrace play --dry-run --speed 2 --from-step 0 --to-step 5 trace.jsonl

# Real playback (requires Accessibility)
uv run uitrace play trace.jsonl
```

#### Multi-Window Recording

Record interactions across multiple windows:
```bash
uitrace record --follow any --out trace.jsonl
```

Screen Recording permission is required for `--follow any` mode.

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 2 | Invalid usage |
| 10 | Window not found |
| 11 | Permission denied / platform unsupported |
| 20 | Assertion failed |
| 30 | Injection failed |
| 40 | Schema validation failed |
| 130 | Interrupted (Ctrl+C) |

### Trace Format (v1)

JSONL file with one JSON object per line. All events have `v: 1`, `type`, and `ts` (seconds).

Event types: `session_start`, `window_selector`, `window_bounds`, `assert`, `wait_until`, `click`, `scroll`, `session_end`.

#### wait_until

- `kind="pixel"`: Wait until a pixel at a relative position matches an expected RGB color.
- `kind="window_found"`: Wait until a window matching a selector appears. Used in multi-window recording to wait for newly opened windows.

### Troubleshooting

- **"Cannot create event tap"**: Grant Input Monitoring permission to your terminal, then restart it.
- **Window titles show as null**: Grant Screen Recording permission to your terminal, then restart it.
- **`play` exits with code 11**: Grant Accessibility permission to your terminal, then restart it.
- **Permissions granted but still failing**: Make sure you granted to the correct app (e.g., Ghostty, not Python) and restarted the terminal.

### Development

```bash
uv run ruff check .     # Lint
uv run mypy src         # Type check
uv run pytest -q        # Tests
```
