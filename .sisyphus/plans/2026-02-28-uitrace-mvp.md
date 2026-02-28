# uitrace MVP Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 在 macOS 上提供 `uitrace` CLI：列出窗口 → 选择窗口 → 录制 click/scroll → 生成 `trace.jsonl`；并可按 `--speed`/分段/`--dry-run` 可控回放，逐步输出 machine-readable `step_result`（JSONL）。

**Architecture:**
- **Core（可单测）**：Pydantic v2 schema + JSONL IO + 回放调度（speed/分段/dry-run/step_result）+ CLI glue。
- **Platform（macOS Quartz）**：窗口枚举、权限诊断（doctor）、event tap 录制、CGEvent 注入、可选像素采样。
- 关键护栏：`play --dry-run` **必须不依赖任何权限**，可用于 CI/自动验收；权限不足时必须输出“可诊断失败”（稳定退出码 + 结构化输出）。

**Tech Stack:** Python 3.12 (`.python-version`), `uv`, `typer`, `rich`, `pydantic>=2`, `pyobjc` (Quartz/Cocoa), `pytest`, `ruff`, `mypy`.

---

## TL;DR
> **Summary**: 先把“schema + validate/show + dry-run play + doctor/list”做成可自动验证闭环；再做 macOS 真实注入与录制（event tap）。
> **Deliverables**:
> - `uitrace` CLI：`list`, `record`, `play`, `show`, `validate`, `doctor`
> - `trace.jsonl` v1（Pydantic v2 严格校验，`extra='forbid'`）
> - `play` 每步输出 `step_result`（JSONL；含 `skipped`/`dry_run`）
> - pytest 覆盖核心层 + fixtures；macOS 平台层提供可诊断失败 + 手工 QA 清单
> - README：权限/故障排查
> **Effort**: Large
> **Parallel**: YES（core 与 platform 可并行）
> **Critical Path**: schema → jsonl IO → validate → dry-run play → doctor/list → inject play → event tap record → assertions

## Context
### Original Request
见 `draft.md`：定义 CLI 规格、退出码、JSONL 事件 DSL v1、平台抽象、Recorder/Player 行为、以及 macOS Quartz 的现实门槛与建议。

### Repo Reality (discovered)
- 当前仓库几乎为空：`main.py` 仅 hello world；`pyproject.toml` 仅包含 `[project]` 基础字段，尚无依赖/脚手架。

### Key Research (sources)
- Pydantic v2 unions/config/base model: https://docs.pydantic.dev/2.12/concepts/unions ; https://docs.pydantic.dev/2.12/api/config ; https://docs.pydantic.dev/2.12/api/base_model
- Typer commands/subcommands/terminating: https://typer.tiangolo.com/tutorial/commands/ ; https://typer.tiangolo.com/tutorial/subcommands/ ; https://typer.tiangolo.com/tutorial/terminating/
- PEP 621 scripts: https://peps.python.org/pep-0621/
- Apple docs: CGWindowListCopyWindowInfo / CGEventTapCreate / CGEventPost / AXIsProcessTrusted
- PyObjC notes: https://pyobjc.readthedocs.io/en/latest/apinotes/Quartz.html ; https://pyobjc.readthedocs.io/en/latest/apinotes/ApplicationServices.html

## Work Objectives
### Core Objective
实现一个“可被 Agent 稳定调用”的 UI trace 工具：输出结构化轨迹 + 可控回放 + 可诊断结果。

### Definition of Done (agent-verifiable)
在本机（macOS）可执行以下命令并满足断言：

1) 基础质量门禁
- `uv run ruff check .` 返回 0
- `uv run mypy src` 返回 0
- `uv run pytest -q` 返回 0

2) CLI 形态
- `uv run uitrace --help` 输出包含 `list`/`record`/`play`/`show`/`validate`/`doctor`

3) schema/validate
- `uv run uitrace validate tests/fixtures/trace_v1_valid.jsonl` 返回 0
- `uv run uitrace validate tests/fixtures/trace_v1_invalid.jsonl` 返回 40，stderr 包含 `line` + Pydantic 错误信息

4) dry-run 回放闭环（不依赖权限）
- `uv run uitrace play --dry-run --speed 4 --from-step 0 --to-step 2 tests/fixtures/trace_v1_valid.jsonl` 返回 0，stdout 为 JSONL；每行 `type == "step_result"` 且 `step` 覆盖 0..2。
  - **Step 语义锁定**：`step` 只对“可回放/可断言”的事件计数（`window_bounds`/`assert`/`wait_until`/`click`/`scroll`）。`session_start`/`window_selector`/`session_end` 不计入 step。

5) doctor/list 结构化输出（权限不足也必须有 JSON）
- `uv run uitrace doctor --json` 返回 0 或 11，但 stdout 必须是合法 JSON，并包含 keys：`platform`, `executable`, `permissions`
- `uv run uitrace list --json` 返回 0；stdout 为 JSON 数组，包含字段：`id`, `owner_name`, `pid`, `bounds`, `title`（若受限可为 null）

### Must Have
- `play --dry-run` 绝不触发任何注入
- 退出码固定：0/2/10/11/20/30/40/130
- 所有结构化输出都稳定可解析（JSON 或 JSONL）

### Must NOT Have (guardrails)
- MVP 不做：键盘录制/回放、OCR/模板匹配、AX 控件级操作、Wayland 完整支持、复杂跨平台实现
- 平台依赖不得泄漏到 core：`src/uitrace/core/*` 不能 import `Quartz`/`AppKit`

## Verification Strategy
- **Test decision**: tests-after-but-TDD-ish（对 core 层按 TDD 写单测；对平台层以“可诊断失败 + 手工 QA 清单”为主）
- **QA policy**: 每个 CLI 命令至少有一条可自动执行的 smoke；平台真实注入/录制提供脚本化手工 QA（可被 agent 执行但依赖权限）

## Trace v1 Spec (DECISION-COMPLETE)

### JSONL basics
- 每行一个 JSON object
- 所有事件都有：`v: 1`, `type: str`, `ts: float`（录制开始后相对秒）
- 事件字段严格：Pydantic v2 `extra='forbid'`

### Core event types (MVP)
1) `session_start`
   - fields: `meta`（tool/os/python/displays/coord_space）
2) `window_selector`
   - fields: `selector`（定位窗口用）
3) `window_bounds`
   - fields: `bounds`（x,y,w,h） + optional `client_inset`（l,t,r,b）
4) `assert`
   - `kind`: `window_title_contains` | `pixel`
5) `wait_until`
   - `kind`: `pixel` + `timeout_ms`
6) `click`
   - fields: `pos`（rx/ry 相对窗口） + `screen`（x/y 绝对，points） + `button` + `count`
7) `scroll`
   - fields: `pos` + `screen` + `delta`（y，单位 pixel）
8) `session_end`

### StepResult JSONL (stdout / --report)
- 每执行/跳过一个 step 都输出一条：`{"type":"step_result", ...}`
- 仅以下事件会产生 step：`window_bounds` / `assert` / `wait_until` / `click` / `scroll`
- 最小字段：`step`, `event_idx`（对应原始事件序号）, `event_type`, `ok`, `status`（ok|skipped|error）, `elapsed_ms`, `dry_run`
- 若涉及坐标：输出 `anchor_used`（window|abs），以及最终注入坐标 `screen_final`

## Execution Strategy

### Parallel Execution Waves
- Wave 1 (core foundation): packaging + schema + jsonl + validate/show + dry-run player
- Wave 2 (diagnostics + window list): doctor + list + window locate logic
- Wave 3 (platform runtime): inject + record + assertions (pixel/wait)

---

## TODOs (Implementation Plan)

> 约定：除文档任务外，每个 Task 尽量包含：测试 → 运行失败 → 最小实现 → 运行通过 → 提交（commit message 必须英文）。

### Task 1: 初始化打包/依赖/工具链（uv + src layout + scripts）

**Files:**
- Modify: `pyproject.toml`
- (Optional) Modify: `README.md`

**Decisions (locked):**
- Build backend 选 `hatchling`
- macOS 平台依赖直接用 `pyobjc`（单包覆盖 Quartz/Cocoa/ApplicationServices），用 marker 限制 Darwin
- CLI entrypoint：`[project.scripts] uitrace = "uitrace.cli:main"`

**Step 1: Add dependencies and build backend**

Commands (use ONE approach):
1) Preferred: use uv
   - Run: `uv add typer rich "pydantic>=2"`
   - Run: `uv add "pyobjc; platform_system == 'Darwin'"`
   - Run: `uv add --dev pytest ruff mypy`
   - Run: `uv add --dev types-requests` (only if mypy complains later; otherwise skip)
2) If uv add is unavailable: edit `pyproject.toml` manually with the same deps.

Then edit `pyproject.toml` to include:
- `[build-system]`:
  - `requires = ["hatchling"]`
  - `build-backend = "hatchling.build"`
- `[tool.hatch.build.targets.wheel]`:
  - `packages = ["src/uitrace"]`
- `[project.scripts]`:
  - `uitrace = "uitrace.cli:main"`

**Step 2: Add tool configs**
- Add `[tool.pytest.ini_options]` with `testpaths = ["tests"]`
- Add `[tool.ruff]` + `[tool.ruff.lint]` minimal config (select E,F,I; line-length 100)
- Add `[tool.mypy]` config (python_version=3.12, strict-ish but practical: disallow_untyped_defs=false initially)

**Acceptance Criteria:**
- [x] `python -c "import tomllib; tomllib.load(open('pyproject.toml','rb'))"` exits 0
- [x] `uv run python -c "import typer, pydantic"` exits 0

**Commit:** YES | Message: `chore: bootstrap uv project tooling`

---

### Task 2: 建立 src 包结构与 CLI 骨架（Typer）

**Files:**
- Create: `src/uitrace/__init__.py`
- Create: `src/uitrace/cli.py`
- Create: `src/uitrace/errors.py`

**Step 1: Write failing CLI smoke test**
- Create: `tests/test_cli_help.py`

```python
from typer.testing import CliRunner

from uitrace.cli import app


def test_cli_help_lists_commands():
    runner = CliRunner()
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for cmd in ["list", "record", "play", "show", "validate", "doctor"]:
        assert cmd in result.stdout
```

Run: `uv run pytest -q`
Expected: FAIL (cannot import uitrace.cli)

**Step 2: Minimal implementation**
- `src/uitrace/cli.py`:
  - define `app = typer.Typer(add_completion=False, no_args_is_help=True)`
  - add stub commands with `@app.command()` that raise `typer.Exit(code=2)` for now
  - provide `def main(): app()` for console_script entrypoint

**Step 3: Run tests**
Run: `uv run pytest -q`
Expected: PASS

**Commit:** YES | Message: `feat: add typer CLI skeleton`

---

### Task 3: 定义退出码与统一错误模型（errors）

**Files:**
- Modify: `src/uitrace/errors.py`
- Modify: `src/uitrace/cli.py`
- Test: `tests/test_errors.py`

**Decisions (locked):**
- Exit codes:
  - 0 success
  - 2 invalid usage (typer)
  - 10 window locate failure
  - 11 permission missing / platform blocked
  - 20 assertion failed
  - 30 injection failure
  - 40 schema validation failure
  - 130 interrupted

- `ErrorCode` enum members (names locked) and mapping:
  - `INVALID_USAGE` -> 2
  - `WINDOW_NOT_FOUND` -> 10
  - `PERMISSION_DENIED` -> 11
  - `ASSERTION_FAILED` -> 20
  - `INJECTION_FAILED` -> 30
  - `SCHEMA_INVALID` -> 40
  - `UNSUPPORTED_PLATFORM` -> 11
  - `INTERRUPTED` -> 130

**Step 1: Write failing test for error formatting**

```python
import pytest

from uitrace.errors import ErrorCode, UitError, format_error


def test_format_error_contains_code_and_message():
    err = UitError(code=ErrorCode.SCHEMA_INVALID, message="bad", hint="do x")
    s = format_error(err)
    assert "SCHEMA_INVALID" in s
    assert "bad" in s
    assert "do x" in s
```

Run: `uv run pytest -q`
Expected: FAIL

**Step 2: Minimal implementation**
- `ErrorCode` enum names must be stable and match mapping above
- `UitError` is a dataclass-like Exception with: `code`, `message`, `hint: str|None`, `details: dict|None`
- `format_error` renders one-line summary; when `details` present, append JSON on `--verbose` only (wire later)

**Step 3: Wire into CLI**
- In `cli.py` wrap command bodies with try/except `UitError` and `KeyboardInterrupt` and exit with correct code

**Acceptance Criteria:**
- [x] `uv run pytest -q` passes

**Commit:** YES | Message: `feat: add error codes and unified error handling`

---

### Task 4: 定义 Pydantic v2 轨迹 schema（trace v1）

**Files:**
- Create: `src/uitrace/core/__init__.py`
- Create: `src/uitrace/core/models.py`
- Test: `tests/test_models_roundtrip.py`

**Decisions (locked):**
- Discriminated union uses `type` as discriminator: `Field(discriminator="type")`
- `model_config = ConfigDict(extra="forbid")` on all models
- `v` is `Literal[1]`

**Step 1: Write failing tests**

```python
import json
import pytest

from uitrace.core.models import TraceEvent


def test_parse_valid_click_event():
    raw = {
        "v": 1,
        "type": "click",
        "ts": 1.0,
        "pos": {"rx": 0.5, "ry": 0.5},
        "screen": {"x": 100, "y": 200},
        "button": "left",
        "count": 1,
    }
    ev = TraceEvent.model_validate(raw)
    assert ev.type == "click"


def test_extra_fields_forbidden():
    raw = {"v": 1, "type": "session_end", "ts": 0.0, "nope": 1}
    with pytest.raises(Exception):
        TraceEvent.model_validate(raw)
```

Run: `uv run pytest -q`
Expected: FAIL

**Step 2: Implement models**
Implement in `src/uitrace/core/models.py`:
- `Rect`, `Inset`, `Pos`, `Point`, `WindowSelector`
- event models: `SessionStart`, `WindowSelectorEvent`, `WindowBounds`, `Click`, `Scroll`, `Assert`, `WaitUntil`, `SessionEnd`
- `TraceEvent = Annotated[Union[...], Field(discriminator="type")]`
- `StepResult` model (separate, also `extra='forbid'`) and helper `def step_result_line(...) -> str` (optional)

**Schema details to lock:**
- `SessionStart.meta`: `dict[str, Any]`（允许为空；测试 fixture 依赖 meta 可为空/最小 dict）
- `WindowSelector` fields (all optional):
  - `title_regex: str | None`
  - `title: str | None`
  - `pid: int | None`
  - `app: str | None` (macOS: owner/app name)
  - `bundle_id: str | None` (macOS preferred if available)
  - `platform: Literal["mac","win","x11"] | None`
- `Click.button`: `Literal["left","right","middle"]` ; `count: int` (>=1)
- `Scroll.delta`: object `{y: int}` (pixel units)
- `Assert.kind` values: `window_title_contains`, `pixel`
- `Assert` fields:
  - `kind: Literal[...]`
  - for title: `value: str`
  - for pixel: `pos: Pos`, `rgb: tuple[int,int,int]`, `tolerance: int = 0`
- `WaitUntil` fields:
  - `kind: Literal["pixel"]`
  - `pos`, `rgb`, `tolerance`, `timeout_ms: int`

- `StepResult` fields (JSONL output, not part of TraceEvent union):
  - `type: Literal["step_result"]`
  - `step: int` (0-based playable step index)
  - `event_idx: int` (0-based index in original TraceEvent stream)
  - `event_type: str` (same as event.type)
  - `status: Literal["ok","skipped","error"]`
  - `ok: bool` (status=="ok")
  - `elapsed_ms: int`
  - `dry_run: bool`
  - optional `error_code: str`, `message: str`, `observed: dict`, `anchor_used: str`, `screen_final: Point`

**Step 3: Run tests**
Run: `uv run pytest -q`

**Commit:** YES | Message: `feat: add pydantic v1 trace schema`

---

### Task 5: JSONL 读写与逐行校验（含行号定位）

**Files:**
- Create: `src/uitrace/core/jsonl.py`
- Modify: `src/uitrace/core/models.py` (only if needed)
- Test: `tests/test_jsonl_io.py`

**Step 1: Write failing tests**

```python
from pathlib import Path

import pytest

from uitrace.core.jsonl import read_events
from uitrace.errors import UitError, ErrorCode


def test_read_events_reports_line_number(tmp_path: Path):
    p = tmp_path / "bad.jsonl"
    p.write_text('{"v":1,"type":"session_end","ts":0}\nnot-json\n', encoding="utf-8")
    with pytest.raises(UitError) as e:
        list(read_events(p))
    assert e.value.code == ErrorCode.SCHEMA_INVALID
    assert "line 2" in e.value.message
```

Run: `uv run pytest -q`
Expected: FAIL

**Step 2: Implement jsonl reader/writer**
- `iter_json_objects(path)` yields `(line_no, obj)`
- `read_events(path)` validates each line as `TraceEvent` and yields events
- On JSON decode error or validation error: raise `UitError(SCHEMA_INVALID, message includes line number, details includes pydantic errors())`
- Writer uses `json.dumps(..., separators=(",", ":"), ensure_ascii=False)` for stable JSONL

**Acceptance Criteria:**
- [x] `uv run pytest -q` passes

**Commit:** YES | Message: `feat: add streaming JSONL IO with line errors`

---

### Task 6: `uitrace validate` 命令（严格校验 + 退出码 40）

**Files:**
- Create: `src/uitrace/tools/__init__.py`
- Create: `src/uitrace/tools/validate.py`
- Modify: `src/uitrace/cli.py`
- Test: `tests/test_validate_command.py`
- Add fixtures: `tests/fixtures/trace_v1_valid.jsonl`, `tests/fixtures/trace_v1_invalid.jsonl`

**Step 1: Write failing tests**

```python
from pathlib import Path

from typer.testing import CliRunner

from uitrace.cli import app


def test_validate_ok(tmp_path: Path):
    runner = CliRunner()
    p = Path("tests/fixtures/trace_v1_valid.jsonl")
    r = runner.invoke(app, ["validate", str(p)])
    assert r.exit_code == 0


def test_validate_bad_returns_40():
    runner = CliRunner()
    p = Path("tests/fixtures/trace_v1_invalid.jsonl")
    r = runner.invoke(app, ["validate", str(p)])
    assert r.exit_code == 40
```

Run: `uv run pytest -q`
Expected: FAIL

**Fixtures (locked contents)**

Create `tests/fixtures/trace_v1_valid.jsonl` with exactly:

```jsonl
{"v":1,"type":"session_start","ts":0.0,"meta":{"tool":"uitrace","os":"macos","python":"3.12"}}
{"v":1,"type":"window_selector","ts":0.0,"selector":{"title_regex":".*TextEdit.*","app":"TextEdit","pid":null,"platform":"mac"}}
{"v":1,"type":"window_bounds","ts":0.0,"bounds":{"x":100,"y":100,"w":800,"h":600},"client_inset":{"l":0,"t":0,"r":0,"b":0}}
{"v":1,"type":"assert","ts":0.1,"kind":"window_title_contains","value":"TextEdit"}
{"v":1,"type":"click","ts":0.5,"pos":{"rx":0.5,"ry":0.5},"screen":{"x":500,"y":400},"button":"left","count":1}
{"v":1,"type":"scroll","ts":0.8,"pos":{"rx":0.5,"ry":0.9},"screen":{"x":500,"y":640},"delta":{"y":-240}}
{"v":1,"type":"session_end","ts":1.0}
```

Create `tests/fixtures/trace_v1_invalid.jsonl` with exactly:

```jsonl
{"v":1,"type":"session_start","ts":0.0,"meta":{}}
{"v":1,"type":"click","ts":0.1,"pos":{"rx":0.5,"ry":0.5},"button":"left","count":1}
```

**Step 2: Implement validate tool**
- `validate.py` implements `def cmd_validate(path: Path) -> None` that fully consumes `read_events`
- On success: print short summary to stderr or stdout (your choice; lock it: stdout)
- On failure: raise `UitError(SCHEMA_INVALID, ...)` and CLI maps to 40

**Step 3: Wire CLI command**
- `cli.py`: `@app.command("validate")` calls tool

**Acceptance Criteria:**
- [x] `uv run pytest -q` passes

**Commit:** YES | Message: `feat: add validate command for trace files`

---

### Task 7: `uitrace show` 命令（人类可读摘要）

**Files:**
- Create: `src/uitrace/tools/show.py`
- Modify: `src/uitrace/cli.py`
- Test: `tests/test_show_command.py`

**Decision (locked):**
- `show` 默认输出 Rich Table + 统计（events count, duration, type histogram）；`--json` 输出摘要 JSON

**Step 1: Write failing test**

```python
from typer.testing import CliRunner

from uitrace.cli import app


def test_show_json_outputs_valid_json():
    runner = CliRunner()
    r = runner.invoke(app, ["show", "--json", "tests/fixtures/trace_v1_valid.jsonl"])
    assert r.exit_code == 0
    import json
    json.loads(r.stdout)
```

**Step 2: Implement show**
- parse events via `read_events`
- compute: `steps_total`, `ts_max`, counts per `type`
- if `--json`: print JSON
- else: print Rich formatted summary

**Commit:** YES | Message: `feat: add show command for trace summary`

---

### Task 8: 平台抽象接口（core 与 macOS 解耦）

**Files:**
- Create: `src/uitrace/platform/__init__.py`
- Create: `src/uitrace/platform/base.py`
- Create: `src/uitrace/platform/unsupported.py`
- Test: `tests/test_platform_unsupported.py`

**Decisions (locked):**
- core 不 import pyobjc；`platform/__init__.py` 负责选择实现
- 在非 darwin：`UnsupportedPlatform` 所有能力抛 `UitError(UNSUPPORTED_PLATFORM)` 并退出码 11

**Step 1: Write failing test**

```python
import sys
import pytest

from uitrace.platform.unsupported import UnsupportedPlatform
from uitrace.errors import UitError


def test_unsupported_platform_errors():
    p = UnsupportedPlatform()
    with pytest.raises(UitError):
        p.list_windows()
```

**Step 2: Implement base types**
- `Rect` reuse from models (import from core) OR duplicate minimal dataclass; lock it: reuse `uitrace.core.models.Rect` to avoid duplication.
- `WindowRef`: `handle: str`, `title: str|None`, `pid: int|None`, `owner_name: str|None`, `bounds: Rect`
  - include `window_number: int | None` (macOS: kCGWindowNumber)
- `PermissionStatus` enum: granted/denied/unknown
- `PermissionReport` model: `accessibility`, `input_monitoring`, `screen_recording`, plus `hints: list[str]`
- `Platform` protocol: `list_windows()`, `locate(selector)`, `focus(win)`, `get_bounds(win)`, `record_events(...)`, `inject_click(...)`, `inject_scroll(...)`, `get_pixel(...)` (optional)

**Commit:** YES | Message: `feat: add platform abstraction and unsupported stub`

---

### Task 9: `uitrace doctor`（权限/环境诊断，含 --json）

**Files:**
- Create: `src/uitrace/tools/doctor.py`
- Modify: `src/uitrace/cli.py`
- Test: `tests/test_doctor_json.py`

**Decisions (locked):**
- doctor 输出三类权限：Accessibility / Input Monitoring / Screen Recording
- Accessibility 检测：优先 `AXIsProcessTrusted()`；若 `--prompt` 则尝试 `AXIsProcessTrustedWithOptions({kAXTrustedCheckOptionPrompt: True})`，并兼容不同 pyobjc import 路径（try/fallback）
- Input Monitoring / Screen Recording：用 **best-effort 探测**（算法锁定如下），并给出明确指引 URL 打开设置页：
  - Accessibility settings: `open "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"`
  - Input Monitoring settings: `open "x-apple.systempreferences:com.apple.preference.security?Privacy_ListenEvent"`
  - Screen Recording settings: `open "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture"`
  - `input_monitoring` 探测：尝试创建一个 listen-only mouse event tap（不启动 RunLoop，仅创建）；若返回 NULL → status=denied；否则 status=granted（并立刻释放/disable）
  - `screen_recording` 探测：调用 `CGWindowListCopyWindowInfo`，若能获取到任意窗口的 `kCGWindowOwnerName` 或 `kCGWindowName` 非空 → status=granted；若全部为空 → status=denied（并提示授权后重启终端）
- doctor JSON schema 稳定，即使缺依赖也要返回 JSON（并把 `pyobjc_import` 标记为 false）

**Step 1: Write failing test**

```python
import json

from typer.testing import CliRunner

from uitrace.cli import app


def test_doctor_json_is_parseable():
    runner = CliRunner()
    r = runner.invoke(app, ["doctor", "--json"])
    assert r.exit_code in (0, 11)
    data = json.loads(r.stdout)
    assert "platform" in data
    assert "permissions" in data
```

**Step 2: Implement doctor**
- Output includes:
  - `platform` (`sys.platform`)
  - `executable` (`sys.executable`)
  - `parent_process` best-effort (`ps -p $PPID -o comm=`)
  - `permissions`: { accessibility: {status, prompt_supported}, input_monitoring: {status}, screen_recording: {status} }
  - `hints`: list[str]

**Commit:** YES | Message: `feat: add doctor command for permissions diagnostics`

---

### Task 10: macOS 窗口枚举（Quartz）+ `uitrace list`

**Files:**
- Create: `src/uitrace/platform/macos.py`
- Modify: `src/uitrace/platform/__init__.py`
- Modify: `src/uitrace/cli.py`
- Test: `tests/test_list_json_schema.py`

**Decisions (locked):**
- `list` 输出字段：`id`（递增 index，稳定于本次 list 结果）、`window_number`（kCGWindowNumber）、`owner_name`、`pid`、`title`（kCGWindowName；可能为 null）、`bounds`（x,y,w,h）
- `--json` 输出 JSON array；默认输出 Rich Table
- 若 Screen Recording 未授权导致 title/owner_name 缺失：`restricted: true` 并在 table 顶部提示

**Step 1: Write failing test (shape only)**

```python
import json

from typer.testing import CliRunner

from uitrace.cli import app


def test_list_json_shape():
    runner = CliRunner()
    r = runner.invoke(app, ["list", "--json"])
    assert r.exit_code in (0, 11)
    data = json.loads(r.stdout)
    assert isinstance(data, list)
    if data:
        w = data[0]
        for k in ["id", "pid", "bounds"]:
            assert k in w
```

**Step 2: Implement macOS provider**
- `MacOSPlatform.list_windows()` uses:
  - `Quartz.CGWindowListCopyWindowInfo(kCGWindowListOptionOnScreenOnly, kCGNullWindowID)`
  - map each entry into `WindowRef`
- In `platform/__init__.py`: return `MacOSPlatform()` when `sys.platform == "darwin"`

**Step 3: Implement CLI list**
- `uitrace list --json` prints JSON
- `uitrace list` prints Rich table

**Commit:** YES | Message: `feat: add macOS window listing and list command`

---

### Task 11: `play` 的核心调度器（分段 + speed + step_result；先 dry-run）

**Files:**
- Create: `src/uitrace/player/__init__.py`
- Create: `src/uitrace/player/player.py`
- Test: `tests/test_player_dry_run.py`

**Decisions (locked):**
- `play` 支持：`--speed`, `--from-step`, `--to-step`, `--dry-run`, `--report`
- `--from-step/--to-step` 按 **step 序号** 切段（0-based）。
  - step 序号仅对以下事件计数：`window_bounds` / `assert` / `wait_until` / `click` / `scroll`
  - `session_start` / `window_selector` / `session_end` 不计入 step，也不会输出 step_result
- 对不在区间的 steps：仍输出 `step_result`，`status="skipped"`（保证下游按 step 聚合时不会“缺行”）
- 注入坐标锚定策略：默认 `window`（rx/ry + 当前 bounds）；找不到窗口则直接 exit 10（不做 abs fallback，除非未来加 flag）
- `Player` 注入依赖：`clock_ns` + `sleep` 可注入（便于单测）
- **Dry-run hard rule**：`--dry-run` 路径不得 import/初始化任何 `pyobjc` 相关平台实现（保持“无权限/无依赖”可运行）。

**Step 1: Write failing unit test**

```python
import json
from pathlib import Path

from typer.testing import CliRunner

from uitrace.cli import app


def test_play_dry_run_emits_step_results_only():
    runner = CliRunner()
    r = runner.invoke(
        app,
        [
            "play",
            "--dry-run",
            "--from-step",
            "0",
            "--to-step",
            "2",
            "tests/fixtures/trace_v1_valid.jsonl",
        ],
    )
    assert r.exit_code == 0
    lines = [json.loads(x) for x in r.stdout.splitlines() if x.strip()]
    assert lines
    assert all(x["type"] == "step_result" for x in lines)
```

**Step 2: Implement player core**
- `Player.run(trace_path, ...)`:
  - read events via `read_events`
  - build `steps: list[tuple[event_idx, event]]` filtering types above
  - for each `step_idx, (event_idx, event)`:
    - if outside range: emit step_result skipped
    - else:
      - if dry-run: emit ok + no injection
      - else: execute (assert/wait/click/scroll) via platform
    - timing: sleep based on delta `event.ts` between consecutive **in-range** steps only
  - every emitted step_result includes both `step` and `event_idx`

**Step 3: Wire CLI play**
- In `cli.py`: add play command that streams `step_result` JSONL to stdout
- If `--report`: also append to report file (same JSON per line)

**Commit:** YES | Message: `feat: add dry-run player with step_result JSONL`

---

### Task 12: macOS 注入执行器（click/scroll）

**Files:**
- Create: `src/uitrace/player/executor.py`
- Modify: `src/uitrace/platform/macos.py`
- Test: `tests/test_executor_math.py`

**Decisions (locked):**
- 注入前置：`doctor` 检测 Accessibility；若不可信则 `play` 直接退出 11（fail-fast）
- click 注入：使用 `CGEventCreateMouseEvent`（down/up）+ `CGEventPost(kCGHIDEventTap, event)`
- scroll 注入：使用 `CGEventCreateScrollWheelEvent`（单位 pixel）
- executor 只负责“注入”，不做 locate/focus

**API details (locked)**
- Mouse button mapping:
  - left: `kCGMouseButtonLeft` + event types `kCGEventLeftMouseDown`/`kCGEventLeftMouseUp`
  - right: `kCGMouseButtonRight` + event types `kCGEventRightMouseDown`/`kCGEventRightMouseUp`
  - middle: `kCGMouseButtonCenter` + event types `kCGEventOtherMouseDown`/`kCGEventOtherMouseUp`
- Click count: set `kCGMouseEventClickState` to `count`
- Scroll: `CGEventCreateScrollWheelEvent(None, kCGScrollEventUnitPixel, 1, delta_y)`

**Step 1: Write unit test for coordinate conversion**

```python
from uitrace.core.models import Rect

from uitrace.player.executor import window_rel_to_screen


def test_window_rel_to_screen_clamps():
    b = Rect(x=100, y=200, w=1000, h=500)
    x, y = window_rel_to_screen(b, rx=1.5, ry=-0.5)
    assert x == 1100
    assert y == 200
```

**Step 2: Implement executor module**
- `window_rel_to_screen(bounds: Rect, rx: float, ry: float) -> tuple[int,int]`:
  - clamp rx/ry to [0,1]
  - x = bounds.x + round(bounds.w * rx)
  - y = bounds.y + round(bounds.h * ry)
- `MacOSExecutor.click(x,y,button,count)` posts down/up events
- `MacOSExecutor.scroll(x,y,delta_y)` posts scroll wheel event

**Commit:** YES | Message: `feat: add macOS Quartz executor for click/scroll`

---

### Task 13: `play` 真实注入（非 dry-run）+ 窗口定位/聚焦（最小可用）

**Files:**
- Modify: `src/uitrace/platform/macos.py`
- Modify: `src/uitrace/player/player.py`
- Modify: `src/uitrace/cli.py`

**Decisions (locked):**
- 回放开始必须读取 `window_selector` 并 locate；找不到则 exit 10
- `--focus`：只做 app-level focus（`NSRunningApplication.activateWithOptions_`），失败不致命但写入 step_result.observed

**Implementation steps (no stable automated test):**
1) `MacOSPlatform.locate(selector)`：根据 `pid`/`owner_name`/`title_regex` 过滤 `list_windows()` 候选
2) `MacOSPlatform.get_bounds(win)`：从当前 window list 中按 `window_number` 查 bounds
3) `Player` 在执行 click/scroll 前取 latest bounds，并用 rx/ry 转为 screen coords
4) 非 dry-run 时调用 executor 注入；异常映射为 exit 30

**Acceptance Criteria (agent-executable even without permissions):**
- [x] 当 Accessibility 未授权时：`uv run uitrace play tests/fixtures/trace_v1_valid.jsonl` 返回 11，stderr 明确提示去打开 Accessibility，并且仍输出至少一条 step_result（status=error, error_code=PERMISSION_DENIED）
- [x] `uv run uitrace play --dry-run tests/fixtures/trace_v1_valid.jsonl` 仍返回 0

**Commit:** YES | Message: `feat: enable real playback injection with window locate`

---

### Task 14: `record` 的纯逻辑层：事件归一化/合并/过滤（可单测）

**Files:**
- Create: `src/uitrace/recorder/__init__.py`
- Create: `src/uitrace/recorder/normalize.py`
- Create: `src/uitrace/recorder/merge.py`
- Test: `tests/test_recorder_merge.py`

**Decisions (locked):**
- recorder 内部接收 platform raw events（down/up/scroll），输出 trace 事件（click/scroll）
- click 合并规则：down+up（同 button）→ click；down 后 500ms 未见 up：丢弃并记录 debug（不写 trace）
- scroll 合并规则：50ms 内连续 scroll 合并（delta 累加）
- mouse move 默认不记录（MVP）

**Step 1: Write failing tests**

```python
from uitrace.recorder.merge import merge_mouse_events


def test_merge_down_up_to_click():
    raw = [
        {"kind": "mouse_down", "ts": 0.0, "x": 10, "y": 20, "button": "left"},
        {"kind": "mouse_up", "ts": 0.01, "x": 10, "y": 20, "button": "left"},
    ]
    out = list(merge_mouse_events(raw))
    assert out[0]["kind"] == "click"
```

**Step 2: Implement merge/normalize**
- keep pure-python dict pipeline for raw events
- final conversion to Pydantic TraceEvent happens in recorder runner

**Commit:** YES | Message: `feat: add recorder normalization and merge logic`

---

### Task 15: macOS event tap 录制（平台层）

**Files:**
- Modify: `src/uitrace/platform/macos.py`
- Create: `src/uitrace/recorder/capture_macos.py`

**Decisions (locked):**
- event tap 使用 listen-only：`kCGEventTapOptionListenOnly`
- 事件回调必须极轻：只提取字段并入队；写文件在主线程/worker
- 处理 tap disable：遇到 `kCGEventTapDisabledByTimeout`/`...ByUserInput` 自动 `CGEventTapEnable(..., True)` 并继续
- 权限不足时：`record` fail-fast exit 11，并提示同时检查 Input Monitoring + Accessibility

**Implementation steps:**
1) 在 `capture_macos.py` 实现 `iter_raw_events(stop_event)`：在 RunLoop 里运行，yield raw dicts（mouse_down/up/scroll）
2) event tap 创建参数（锁定）：
   - `tap`: `kCGHIDEventTap`
   - `place`: `kCGHeadInsertEventTap`
   - `options`: `kCGEventTapOptionListenOnly`
   - `eventsOfInterest` 覆盖：
     - `kCGEventLeftMouseDown`, `kCGEventLeftMouseUp`
     - `kCGEventRightMouseDown`, `kCGEventRightMouseUp`
     - `kCGEventOtherMouseDown`, `kCGEventOtherMouseUp`
     - `kCGEventScrollWheel`
3) 回调中处理 disable 事件（锁定）：
   - 若 `type` 是 `kCGEventTapDisabledByTimeout` 或 `kCGEventTapDisabledByUserInput`：立即 `CGEventTapEnable(tap, True)` 并 return event
4) 事件字段提取（锁定）：
   - 坐标：`loc = CGEventGetLocation(event)` → `x=round(loc.x)`, `y=round(loc.y)`（points）
   - scroll delta：`CGEventGetIntegerValueField(event, kCGScrollWheelEventPointDeltaAxis1)`（y）
   - button：
     - left/right 由 event type 决定
     - other：读取 `kCGMouseEventButtonNumber`
   - `ts`：用 `time.monotonic()`（秒）或 `time.monotonic_ns()`（建议 ns），最终转成 trace `ts`（相对 session_start）
5) stop_event 停止策略（锁定）：
   - recorder 主线程设置 stop_event 后，调用 `CFRunLoopStop(run_loop)` 退出；确保 finally 中 disable tap 并释放资源

**QA Scenarios (scripted manual):**
```
Scenario: record permission missing
  Tool: Bash
  Steps:
    1) uv run uitrace doctor
    2) uv run uitrace record --out /tmp/t.jsonl --window-id 0
  Expected:
    - exit code 11
    - stderr includes Accessibility/Input Monitoring instructions

Scenario: record emits JSONL
  Tool: Bash
  Steps:
    1) open -a TextEdit
    2) uv run uitrace list
    3) uv run uitrace record --countdown 2 --out /tmp/t.jsonl --window-id <TextEdit id>
    4) click and scroll inside TextEdit, then Ctrl+C
    5) uv run uitrace validate /tmp/t.jsonl
  Expected:
    - validate exit 0
    - trace includes session_start/window_selector/window_bounds/click/scroll/session_end
```

**Commit:** YES | Message: `feat: add macOS Quartz event tap capture`

---

### Task 16: `record` runner：窗口选择 + bounds 采样 + 写 trace.jsonl

**Files:**
- Create: `src/uitrace/recorder/recorder.py`
- Modify: `src/uitrace/cli.py`
- Test: `tests/test_record_pipeline_pure.py`

**Decisions (locked):**
- 录制前输出：`session_start`、`window_selector`、初始 `window_bounds`
- 事件过滤：只记录落在窗口 bounds 内的事件（用 event x/y 判断）
- bounds 采样：每 `--sample-window-ms` 刷新一次 bounds，变化则写 `window_bounds`
- 停止：MVP 用 Ctrl+C（SIGINT）；`session_end` 始终写入（用 finally）

**Step 1: Write failing test (pure pipeline)**
- Use FakePlatform + fake raw event stream to ensure filtering + JSONL writing

**Step 2: Implement runner**
- `Recorder.run(out_path, selector, countdown, sample_window_ms, merge)`
- CLI `record` 支持：`--out`, `--window-id`（从 list index 选择）, `--countdown`, `--sample-window-ms`, `--merge/--no-merge`

**Commit:** YES | Message: `feat: add record command writing trace jsonl`

---

### Task 17: 断言与等待（player 侧）：window_title_contains + pixel + wait_until(pixel)

**Files:**
- Modify: `src/uitrace/player/player.py`
- Create: `src/uitrace/player/observer.py`
- Modify: `src/uitrace/platform/macos.py`
- Test: `tests/test_assertions_pure.py`

**Decisions (locked):**
- `window_title_contains`：若无法读取 title（缺 Screen Recording）→ step_result error + exit 11（permission）
- `pixel`/`wait_until`：实现最小像素采样（1x1），缺 Screen Recording → exit 11
- `wait_until` 轮询间隔：50ms；超时 → exit 20（assertion failed）

**Implementation detail (locked):**
- 像素采样 macOS（锁定实现路径，避免 executor 现场“选库”）：
  1) 坐标空间：trace 与注入均使用 Quartz 全局坐标 **points**（与 `CGEventGetLocation` 一致）
  2) 采样时将 points → pixels：
     - `scale = AppKit.NSScreen.mainScreen().backingScaleFactor()`（MVP 仅支持主屏；多屏后续再扩展）
     - `px = int(round(x * scale))`, `py = int(round(y * scale))`
  3) 截图 1x1：`CGDisplayCreateImageForRect(CGMainDisplayID(), CGRectMake(px, py, 1, 1))`
  4) 取 RGB：用 `NSBitmapImageRep.alloc().initWithCGImage_(img)` + `colorAtX_y_(0,0)` 读 `redComponent/greenComponent/blueComponent`（0..1 → 0..255）
  5) 若任一步返回 None/异常：判定为 Screen Recording 缺失或不支持，exit 11 并在 stderr/step_result 给出 `open ...Privacy_ScreenCapture` 指引

**Commit:** YES | Message: `feat: add assertions and wait_until support`

---

### Task 18: README（权限、用法、故障排查）

**Files:**
- Modify: `README.md`

**Content (locked):**
- Quickstart: `uv sync`, `uv run uitrace --help`
- Permissions: Accessibility + Input Monitoring + Screen Recording（分别解释什么时候需要）
- Troubleshooting: “授权对象是 Terminal/iTerm/VS Code”等；授权后需要重启终端
- Examples: list/record/play/dry-run/validate/show

**Commit:** YES | Message: `docs: add usage and permissions guide`

---

## Final Verification Wave
- F1: `uv run ruff check .`
- F2: `uv run mypy src`
- F3: `uv run pytest -q`
- F4: Manual QA: record + play on TextEdit (permissions granted)

## Commit Strategy
- Keep commits small and in English.
- Suggested sequence:
  - `chore: bootstrap uv project tooling`
  - `feat: add typer CLI skeleton`
  - `feat: add pydantic v1 trace schema`
  - `feat: add streaming JSONL IO with line errors`
  - `feat: add validate command for trace files`
  - `feat: add dry-run player with step_result JSONL`
  - `feat: add macOS window listing and list command`
  - `feat: enable real playback injection with window locate`
  - `feat: add macOS Quartz event tap capture`
  - `feat: add record command writing trace jsonl`
  - `feat: add assertions and wait_until support`
  - `docs: add usage and permissions guide`
