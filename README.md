## uitrace

Record real mouse clicks and scrolls in a macOS window,
and replay them deterministically from a structured JSONL trace.

Turn GUI interactions into a replayable execution log.

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

### Installation

<details open>
<summary><strong>Option 1: Run directly with <code>uvx</code> (recommended)</strong></summary>

No installation required. Runs in an isolated environment.

```bash
uvx uitrace --help
```

Specific version:

```bash
uvx uitrace@0.1.0 --help
```
</details>

<details>
<summary><strong>Option 2: Install with <code>pip</code></strong></summary>

Install globally:

```bash
pip install uitrace
```

Or install in a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate
pip install uitrace
```

Then run:

```bash
uitrace --help
```

Upgrade:

```bash
pip install -U uitrace
```
</details>

<details>
<summary><strong>Option 3: Install with <code>uv</code> (project-style install)</strong></summary>

If you prefer `uv`:

```bash
uv tool install uitrace
```

Then:

```bash
uitrace --help
```

Upgrade:

```bash
uv tool upgrade uitrace
```
</details>

<details>
<summary><strong>Option 4: Install from source</strong></summary>

```bash
git clone https://github.com/mkdir700/uitrace.git
cd uitrace
uv sync
uv run uitrace --help
```

Or install in editable mode:

```bash
uv pip install -e .
```
</details>

### Execution Modes Overview

| Mode | Installation Required | Permissions Needed | Recommended Use |
|------|------------------------|--------------------|-----------------|
| `uvx` | No | Depends on command | CI / quick runs |
| `pip install` | Yes | Depends on command | Local development |
| `uv tool install` | Yes | Depends on command | Clean CLI setup |
| `--dry-run` | No | None | CI validation |

### Versioning

Check installed version:

```bash
uitrace --version
```

Check version via `uvx`:

```bash
uvx uitrace --version
```

### Quick Start

#### Step 1: List Windows

```bash
uvx uitrace list
```

Pick a `window_id` (for example: browser, VS Code, Notes).

#### Step 2: Record Real Interaction

```bash
uvx uitrace record --window-id 0 --out demo.jsonl --countdown 3
```

After the countdown:

- Click somewhere
- Scroll
- Switch focus briefly (optional)
- Press `Ctrl+C` to stop

You now have:

- `demo.jsonl`
- A structured, machine-readable UI trace

#### Step 3: Inspect the Trace

```bash
uvx uitrace show demo.jsonl
```

You will see output similar to:

```json
{"v":1,"type":"session_start","...":"..."}
{"v":1,"type":"window_bounds","...":"..."}
{"v":1,"type":"click","x":312,"y":128}
{"v":1,"type":"scroll","dx":0,"dy":-120}
{"v":1,"type":"session_end","...":"..."}
```

This is not a screen recording. It is a deterministic execution log.

#### Step 4: Safe Replay (No Permissions Needed)

```bash
uvx uitrace play --dry-run demo.jsonl
```

This validates sequencing and timing without injecting events.

Good for:

- CI validation
- Agent verification
- Trace regression tests

#### Step 5: Real Replay

```bash
uvx uitrace play demo.jsonl
```

Clicks and scrolls are replayed exactly as recorded.

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
uitrace doctor
uitrace doctor --json

# List windows
uitrace list
uitrace list --json

# Record interactions (Ctrl+C to stop)
uitrace record --out trace.jsonl --window-id 0 --countdown 3

# Validate a trace file
uitrace validate trace.jsonl

# Show trace summary
uitrace show trace.jsonl
uitrace show --json trace.jsonl

# Playback (dry-run, no permissions needed)
uitrace play --dry-run trace.jsonl

# Playback with speed and step slicing
uitrace play --dry-run --speed 2 --from-step 0 --to-step 5 trace.jsonl

# Real playback (requires Accessibility)
uitrace play trace.jsonl
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

### Release

1. Bump version in `pyproject.toml`.
2. Run local checks and build:
   ```bash
   uv run ruff check . && uv run mypy src && uv run pytest -q
   uv build
   ```
3. Create and push a version tag:
   ```bash
   git tag vX.Y.Z
   git push origin vX.Y.Z
   ```
   **Important:** The tag `vX.Y.Z` must match the `project.version` in `pyproject.toml`.

#### PyPI Setup

This project uses [Trusted Publishing](https://docs.pypi.org/trusted-publishers/).
Configure the following on PyPI for the `uitrace` project:
- **Owner:** `mkdir700`
- **Repository:** `uitrace`
- **Workflow name:** `publish.yml`
