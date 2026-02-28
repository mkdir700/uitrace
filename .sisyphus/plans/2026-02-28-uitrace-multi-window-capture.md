# Multi-window Recording & Playback Correctness (A→B→C)

## TL;DR
> **Summary**: Add multi-window “follow any window” recording so A→B→C flows don’t drop clicks, and make playback reliably wait for new windows using explicit trace `wait_until` steps.
> **Deliverables**:
> - `record --follow any` mode: hit-test window under pointer, auto-insert window context switches.
> - Enforce Screen Recording (and other) permissions for recording.
> - Trace-level waits: new `wait_until.kind="window_found"` inserted on window switches.
> - Player real execution for `assert` + `wait_until` (no more NOT_IMPLEMENTED).
> - Pytest coverage + new multi-window fixture trace.
> **Effort**: Medium
> **Parallel**: YES — 3 waves
> **Critical Path**: Models (`wait_until window_found`) → Platform hit-test → Recorder follow-any → Player wait/assert → Tests

## Context

### Original Request
- 场景：点击 A 窗口弹出 B；在 B 点击又出现 C。
- 目标：设计一套机制，保证录制/回放时能捕获正确的操作流程（窗口切换不丢事件、不串窗口）。

### Interview Summary
- Follow scope: **Any window** (cross-app)
- Recording permissions: **Screen Recording REQUIRED** (for stable window titles/selectors)
- Playback waiting strategy: **Explicit waits/asserts in the trace** (not only implicit locate retries)

### Metis Review (gaps addressed)
- Defined what counts as “interaction”: mouse `click` and `scroll` only (no keyboard, no move capture).
- Guardrails added: filter system UI overlays by window layer; throttle hit-testing for scroll; don’t introduce new deps.
- Explicit failure semantics: window wait timeout → exit 10; assertion failure → exit 20.

## Work Objectives

### Core Objective
Make `uitrace` reliably record and replay multi-window flows (A→B→C) on macOS by:
1) capturing interactions across windows without dropping events, and
2) waiting for newly opened windows explicitly via trace steps.

### Deliverables
- Platform API: `Platform.window_from_point(x, y)` + macOS implementation.
- Trace schema: `wait_until.kind="window_found"` with a `WindowSelector` payload.
- Recorder: new follow mode `--follow any` that:
  - hit-tests each interaction to a window,
  - inserts `wait_until(window_found)` + `window_selector` + `window_bounds` on window switches,
  - keeps existing single-window mode unchanged.
- Player: implement real playback for:
  - `assert.kind in {window_title_contains, pixel}`
  - `wait_until.kind in {pixel, window_found}`
- Tests: unit tests for schema + recorder + player; plus a fixture trace for a multi-window flow.
- Docs: README usage note for multi-window recording + permissions.

### Definition of Done (verifiable)
- [ ] `uv run pytest -q`
- [ ] `uv run ruff check .`
- [ ] `uv run mypy src`
- [ ] `uv run uitrace validate tests/fixtures/trace_v1_multi_window.jsonl`
- [ ] `uv run uitrace play --dry-run tests/fixtures/trace_v1_multi_window.jsonl` emits JSON step_results containing (at minimum) `wait_until` + multiple `window_selector` steps.

### Must Have
- Multi-window recording does not drop B/C clicks (no single-window bounds filter in `--follow any`).
- Window context is explicit in trace via `window_selector`/`window_bounds` before actions.
- Recording enforces Screen Recording permission (and continues to enforce Accessibility + Input Monitoring).
- Playback supports trace-level waits/asserts and fails with correct exit codes.

### Must NOT Have (guardrails)
- No keyboard recording/playback.
- No OCR, template matching, or AX/UIA element-level automation.
- No new third-party dependencies.
- No broad refactors outside recorder/platform/player/models/tests/docs touched by this change.
- Do not attempt to perfectly model non-rectangular windows; bounds hit-testing only.

## Verification Strategy
- Test decision: **tests-after** with `pytest`
- Policy: every TODO includes at least one unit/integration test.
- Evidence naming (executor writes during implementation): `.sisyphus/evidence/task-{N}-{slug}.txt`

## Execution Strategy

### Parallel Execution Waves
Wave 1 (schema + platform contract)
- Tasks: 1–3

Wave 2 (recorder follow-any + waits)
- Tasks: 4–6

Wave 3 (player execution + fixture + docs)
- Tasks: 7–10

### Dependency Matrix
- 1 → blocks 6–9 (recorder/player must parse/execute new wait kind)
- 2 → blocks 6 (recorder must hit-test)
- 3 → blocks 6 (macOS hit-test implementation)
- 6–8 → blocks 9 (fixture relies on schema + player behavior)

### Agent Dispatch Summary
- Wave 1: 3 tasks (unspecified-high)
- Wave 2: 3 tasks (deep/unspecified-high)
- Wave 3: 4 tasks (unspecified-high + writing)

## TODOs

- [ ] 1. Extend `WaitUntil` schema with `window_found`

  **What to do**:
  - Update `src/uitrace/core/models.py:118` so `WaitUntil` supports:
    - `kind="pixel"` (existing fields)
    - `kind="window_found"` with fields:
      - `selector: WindowSelector`
      - `timeout_ms: int`
  - Keep `extra="forbid"` strictness.
  - Implementation decision (make this exact so there’s no judgment call):
    - Keep `WaitUntil` as a single `BaseModel` (so `WaitUntil.model_validate()` continues to work in `src/uitrace/core/jsonl.py:60`).
    - Add optional fields needed by both kinds:
      - `pos: Pos | None`, `rgb: tuple[int,int,int] | None`, `tolerance: int | None`
      - `selector: WindowSelector | None`
    - Add `@model_validator(mode="after")` enforcing:
      - if `kind=="pixel"`: `pos` + `rgb` + `timeout_ms` required; `selector` must be None
      - if `kind=="window_found"`: `selector` + `timeout_ms` required; `pos/rgb/tolerance` must be None
  - Update JSONL read path (`src/uitrace/core/jsonl.py:60`) only if needed (prefer keeping `WaitUntil.model_validate`).
  - Add tests in `tests/test_models_roundtrip.py:1`:
    - Parse a valid `wait_until window_found` line.
    - Ensure missing `selector` is rejected.
    - Ensure extra fields are rejected.

  **Must NOT do**:
  - Do not add new event `type`s; keep `type="wait_until"`.
  - Do not loosen schema validation.

  **Recommended Agent Profile**:
  - Category: `unspecified-high` — Pydantic v2 strict schema changes.
  - Skills: `test-driven-development` — ensures strict validation.
  - Omitted: `systematic-debugging` — not a failure-driven task.

  **Parallelization**: Can Parallel: YES | Wave 1 | Blocks: 6–9 | Blocked By: none

  **References**:
  - Model: `src/uitrace/core/models.py:118` — current `WaitUntil` definition.
  - JSONL reader: `src/uitrace/core/jsonl.py:60` — where `WaitUntil` is validated.
  - Existing fixture: `tests/fixtures/trace_v1_valid.jsonl:1` — style of JSONL lines.

  **Acceptance Criteria**:
  - [ ] `uv run pytest -q tests/test_models_roundtrip.py`

  **QA Scenarios**:
  ```
  Scenario: Validate new wait_until kind parses
    Tool: Bash
    Steps: uv run pytest -q tests/test_models_roundtrip.py
    Expected: Exit 0
    Evidence: .sisyphus/evidence/task-1-waituntil-window_found.txt

  Scenario: Missing selector rejected
    Tool: Pytest
    Steps: Add a test case asserting model_validate raises
    Expected: Test fails before fix; passes after
    Evidence: .sisyphus/evidence/task-1-waituntil-window_found-error.txt
  ```

  **Commit**: YES | Message: `feat(models): add wait_until window_found` | Files: `src/uitrace/core/models.py`, `tests/test_models_roundtrip.py`

- [ ] 2. Add `window_from_point` to platform protocol + unsupported stub

  **What to do**:
  - Update `src/uitrace/platform/base.py:42` `Platform` protocol with:
    - `window_from_point(self, x: int, y: int) -> WindowRef | None`
  - Implement it on `src/uitrace/platform/unsupported.py:17` to raise `_unsupported()`.
  - Ensure mypy passes with the protocol change.

  **Must NOT do**:
  - Do not change existing method signatures.

  **Recommended Agent Profile**:
  - Category: `quick` — small protocol/stub update.
  - Skills: none

  **Parallelization**: Can Parallel: YES | Wave 1 | Blocks: 6 | Blocked By: none

  **References**:
  - Protocol: `src/uitrace/platform/base.py:42`
  - Unsupported stub: `src/uitrace/platform/unsupported.py:17`

  **Acceptance Criteria**:
  - [ ] `uv run mypy src`

  **QA Scenarios**:
  ```
  Scenario: Type-check passes after protocol change
    Tool: Bash
    Steps: uv run mypy src
    Expected: Exit 0
    Evidence: .sisyphus/evidence/task-2-platform-window_from_point-mypy.txt
  
  Scenario: UnsupportedPlatform still exits 11 for CLI list
    Tool: Bash
    Steps: uv run pytest -q tests/test_platform_unsupported.py
    Expected: Exit 0
    Evidence: .sisyphus/evidence/task-2-platform-window_from_point-unsupported.txt
  ```

  **Commit**: YES | Message: `feat(platform): add window_from_point contract` | Files: `src/uitrace/platform/base.py`, `src/uitrace/platform/unsupported.py`

- [ ] 3. Implement `MacOSPlatform.window_from_point` hit-testing

  **What to do**:
  - Add `window_from_point` method to `src/uitrace/platform/macos.py:15`:
    - Use `CGWindowListCopyWindowInfo(kCGWindowListOptionOnScreenOnly, kCGNullWindowID)`.
    - Iterate windows in returned order (front-to-back) and choose the first window where:
      - bounds contains `(x, y)`
      - bounds size `w>1 && h>1`
      - `kCGWindowLayer == 0` (filter out overlays like menu/Dock popups)
    - Return a `WindowRef` constructed from that window info.
    - If none found, return `None`.
    - Performance decision (exact): add a simple in-instance cache for the window list:
      - Cache fields: `self._window_info_cache: tuple[float, list] | None`
      - TTL: 0.05s (50ms)
      - `window_from_point()` uses cached list when TTL not expired.
  - Add a pure helper inside `src/uitrace/platform/macos.py` for “rect contains point” and test it with synthetic `WindowRef` objects.
  - Create `tests/test_window_hit_test_pure.py` to cover:
    - topmost selection when windows overlap
    - edge inclusive bounds behavior
    - layer filtering behavior (if modeled)

  **Must NOT do**:
  - Do not require Accessibility for hit-testing; it must work with window list access.
  - Do not attempt pixel-accurate shapes; bounds only.

  **Recommended Agent Profile**:
  - Category: `unspecified-high` — platform/Quartz details + correctness pitfalls.
  - Skills: `systematic-debugging` — helpful for coordinate pitfalls.

  **Parallelization**: Can Parallel: YES | Wave 1 | Blocks: 6 | Blocked By: 2

  **References**:
  - Window listing: `src/uitrace/platform/macos.py:18` — how bounds/title/pid are extracted.
  - Recorder raw coordinates: `src/uitrace/recorder/capture_macos.py:16` — event tap yields screen point coordinates.
  - Apple docs: https://developer.apple.com/documentation/coregraphics/1454426-cgwindowlistcopywindowinfo

  **Acceptance Criteria**:
  - [ ] `uv run pytest -q tests/test_window_hit_test_pure.py`

  **QA Scenarios**:
  ```
  Scenario: Overlapping windows chooses topmost
    Tool: Pytest
    Steps: uv run pytest -q tests/test_window_hit_test_pure.py
    Expected: Exit 0
    Evidence: .sisyphus/evidence/task-3-macos-window_from_point.txt

  Scenario: Point outside any window returns None
    Tool: Pytest
    Steps: Add a test with no hit
    Expected: Pass
    Evidence: .sisyphus/evidence/task-3-macos-window_from_point-none.txt
  ```

  **Commit**: YES | Message: `feat(macos): hit-test window from point` | Files: `src/uitrace/platform/macos.py`, `tests/test_window_hit_test_pure.py`

- [ ] 4. Enforce Screen Recording + Input Monitoring for `record`

  **What to do**:
  - In `src/uitrace/cli.py:69` (record command), after `perms = platform.check_permissions()` enforce:
    - `accessibility == granted` (existing)
    - `input_monitoring == granted` (NEW)
    - `screen_recording == granted` (NEW; user requirement)
  - Use `UitError(code=ErrorCode.PERMISSION_DENIED, ...)` with **exact** messages/hints:
    - Input Monitoring denied:
      - message: `"Input Monitoring permission required for recording"`
      - hint: `"Open System Settings > Privacy & Security > Input Monitoring"`
    - Screen Recording denied:
      - message: `"Screen Recording permission required for recording"`
      - hint: `"Open System Settings > Privacy & Security > Screen Recording"`
  - Add a small pure helper function in `src/uitrace/recorder/recorder.py`:
    - `def validate_record_permissions(perms: PermissionReport, *, require_screen_recording: bool) -> None:`
    - It raises `UitError(PERMISSION_DENIED, ...)` with the exact messages/hints above.
  - Add unit tests in `tests/test_record_permissions_pure.py` covering denied/granted combinations.

  **Must NOT do**:
  - Do not change `doctor` behavior; only use its checks.

  **Recommended Agent Profile**:
  - Category: `unspecified-high` — permission UX + consistent exit semantics.
  - Skills: `test-driven-development`

  **Parallelization**: Can Parallel: YES | Wave 2 | Blocks: 5–6 (record mode relies on perms) | Blocked By: none

  **References**:
  - Current record permission check: `src/uitrace/cli.py:92`
  - Permission probing: `src/uitrace/tools/doctor.py:8`, `src/uitrace/platform/macos.py:108`
  - Exit codes table: `README.md:74`

  **Acceptance Criteria**:
  - [ ] `uv run pytest -q` includes new unit tests for permission validation

  **QA Scenarios**:
  ```
  Scenario: Missing Screen Recording fails fast
    Tool: Pytest
    Steps: Unit-test helper raises UitError(PERMISSION_DENIED)
    Expected: Pass
    Evidence: .sisyphus/evidence/task-4-record-permissions.txt

  Scenario: All required permissions allowed
    Tool: Pytest
    Steps: Unit-test helper returns without raising
    Expected: Pass
    Evidence: .sisyphus/evidence/task-4-record-permissions-ok.txt
  ```

  **Commit**: YES | Message: `fix(record): require screen recording and input monitoring` | Files: `src/uitrace/cli.py`, `src/uitrace/recorder/recorder.py`, `tests/...`

- [ ] 5. Add `--follow` mode to `record` CLI

  **What to do**:
  - Add option to `uitrace record` in `src/uitrace/cli.py:70`:
    - `--follow` with choices: `single` (default), `any`
  - For `single`: keep existing behavior.
  - For `any`: invoke the new recorder mode (Task 6).
  - Add option `--window-wait-timeout-ms` (default 5000) used only when `--follow any`.

  **Must NOT do**:
  - Do not change default behavior (must remain single-window capture unless `--follow any`).

  **Recommended Agent Profile**:
  - Category: `quick` — CLI options plumbing.
  - Skills: none

  **Parallelization (corrected)**: Can Parallel: YES | Wave 2 | Blocks: none | Blocked By: none

  **References**:
  - Existing options: `src/uitrace/cli.py:70`
  - Recorder entrypoint: `src/uitrace/recorder/recorder.py:45`

  **Acceptance Criteria**:
  - [ ] `uv run pytest -q tests/test_cli_help.py`

  **QA Scenarios**:
  ```
  Scenario: --help shows new options
    Tool: Pytest
    Steps: uv run pytest -q tests/test_cli_help.py
    Expected: Exit 0
    Evidence: .sisyphus/evidence/task-5-cli-follow-help.txt
  ```

  **Commit**: YES | Message: `feat(cli): add record follow mode` | Files: `src/uitrace/cli.py`, `tests/test_cli_help.py`

- [ ] 6. Implement recorder multi-window capture (`--follow any`) with trace waits

  **What to do**:
  - Update `src/uitrace/recorder/recorder.py:48` to support `follow="any"` behavior:
    1) Stop filtering by a single `current_bounds`.
    2) For each interaction event (click/scroll) determine the target window via `platform.window_from_point(x, y)`.
       - Window identity rule (exact): use `win.window_number` when available; otherwise fall back to `(win.pid, win.owner_name, win.title)`.
       - Skip rule (exact): if `win is None` OR `win.pid is None` OR `win.owner_name is None`, treat as “no target window” and do not record the event.
    3) On window switch (identity changes), insert **in this exact order** before writing the interaction:
       - `wait_until` (`kind="window_found"`, selector=new window selector, timeout from CLI)
       - `window_selector` (same selector)
       - `window_bounds` (bounds of that window)
    4) Then write the click/scroll using that window’s bounds to compute `pos`.
  - Window-wait insertion rule (exact):
    - Do NOT emit `wait_until window_found` for the initial window context (the one written at session start).
    - Emit it for every subsequent context switch (A→B, B→C, etc.).
    - Set `wait_until.ts` equal to the current interaction event’s `ts` (so timing remains monotonic).
  - Selector construction rule (exact):
    - `selector.platform = "mac"`
    - `selector.app = win.owner_name`
    - `selector.pid = win.pid`
    - `selector.title = win.title` (only if not None)
    - `selector.title_regex = None` (do not guess regex)
  - Define “interaction events” as:
    - `click` written on `mouse_down` only (because follow-any forces no-merge)
    - `scroll`
  - For correctness and simplicity, **force `merge=False` when `follow=="any"`** (follow-any implies `--no-merge`) to avoid cross-window scroll coalescing.
  - Keep bounds sampling behavior:
    - In follow-any mode, periodically refresh bounds for the *current* window only (using existing `sample_window_ms` interval), and write `window_bounds` when changed.
  - Add a new pure function (recommended) in `src/uitrace/recorder/recorder.py`:
    - Input: list/iterator of normalized raw events + fake platform
    - Output: list of TraceEvent models (or dicts) for tests
    - `Recorder.run()` remains the file IO wrapper.
  - Add tests `tests/test_record_multi_window_pure.py` that feed synthetic raw events for:
    - A click in window A, then click in window B, then click in window C.
    - Assert trace contains two `wait_until window_found` inserts and three window contexts.

  **Must NOT do**:
  - Do not change `follow=single` behavior.
  - Do not attempt automatic “window creation detection” beyond waiting when the user first interacts with that window.

  **Recommended Agent Profile**:
  - Category: `deep` — non-trivial recorder state machine + strict trace output.
  - Skills: `test-driven-development`

  **Parallelization**: Can Parallel: NO | Wave 2 | Blocks: 9 | Blocked By: 1, 2, 3

  **References**:
  - Current bounds filter: `src/uitrace/recorder/recorder.py:152`
  - Raw event stream: `src/uitrace/recorder/capture_macos.py:16`
  - Click/scroll event writing: `src/uitrace/recorder/recorder.py:225`
  - Window selector/bounds event writing: `src/uitrace/recorder/recorder.py:102`

  **Acceptance Criteria**:
  - [ ] `uv run pytest -q tests/test_record_multi_window_pure.py`

  **QA Scenarios**:
  ```
  Scenario: A→B→C produces window switches and waits
    Tool: Pytest
    Steps: uv run pytest -q tests/test_record_multi_window_pure.py
    Expected: Exit 0
    Evidence: .sisyphus/evidence/task-6-record-follow-any.txt

  Scenario: follow=single unchanged
    Tool: Pytest
    Steps: Ensure existing tests like tests/test_record_pipeline_pure.py still pass
    Expected: Exit 0
    Evidence: .sisyphus/evidence/task-6-record-follow-any-regression.txt
  ```

  **Commit**: YES | Message: `feat(record): follow any window and insert window waits` | Files: `src/uitrace/recorder/recorder.py`, `tests/test_record_multi_window_pure.py`

- [ ] 7. Implement real playback for `assert` (pixel + window_title_contains)

  **What to do**:
  - In `src/uitrace/player/player.py:229`, replace NOT_IMPLEMENTED with real logic:
    - `assert.kind == "window_title_contains"` → call `uitrace.player.observer.check_window_title_contains`
    - `assert.kind == "pixel"` → call `uitrace.player.observer.check_pixel`
  - On assert failure:
    - Yield a `StepResult(status="error", ok=False, error_code=ASSERTION_FAILED, observed=...)`
    - Raise `UitError(code=ErrorCode.ASSERTION_FAILED, message=...)` so CLI exits 20.
  - Add tests in `tests/test_player_assert_real.py` using a FakePlatform (pattern in `tests/test_assertions_pure.py:4`).

  **Must NOT do**:
  - Do not change dry-run behavior.

  **Recommended Agent Profile**:
  - Category: `unspecified-high` — player semantics + exit codes.
  - Skills: `test-driven-development`

  **Parallelization**: Can Parallel: YES | Wave 3 | Blocks: 9 | Blocked By: none

  **References**:
  - Player placeholder: `src/uitrace/player/player.py:229`
  - Observer helpers: `src/uitrace/player/observer.py:11`, `src/uitrace/player/observer.py:40`
  - Error codes: `src/uitrace/errors.py:7`

  **Acceptance Criteria**:
  - [ ] `uv run pytest -q tests/test_player_assert_real.py`

  **QA Scenarios**:
  ```
  Scenario: window_title_contains assert passes
    Tool: Pytest
    Steps: uv run pytest -q tests/test_player_assert_real.py
    Expected: Exit 0
    Evidence: .sisyphus/evidence/task-7-player-assert.txt

  Scenario: pixel assert fails → exit code 20
    Tool: Pytest
    Steps: Test expects UitError(ErrorCode.ASSERTION_FAILED)
    Expected: Pass
    Evidence: .sisyphus/evidence/task-7-player-assert-fail.txt
  ```

  **Commit**: YES | Message: `feat(player): execute assert steps` | Files: `src/uitrace/player/player.py`, `tests/test_player_assert_real.py`

- [ ] 8. Implement real playback for `wait_until` (pixel + window_found)

  **What to do**:
  - In `src/uitrace/player/player.py:229`, add handling for `wait_until`:
    - `kind == "pixel"` → call `uitrace.player.observer.wait_until_pixel`
      - On timeout, raise `UitError(code=ErrorCode.ASSERTION_FAILED, ...)`.
    - `kind == "window_found"` → implement a polling loop:
      - Repeatedly call `platform.locate(event.selector)` until it returns a window or timeout.
      - Poll interval: 50ms (match `observer.wait_until_pixel` default).
      - On timeout, raise `UitError(code=ErrorCode.WINDOW_NOT_FOUND, ...)` so CLI exits 10.
  - Add tests in `tests/test_player_wait_until_real.py` using FakePlatform with stateful `locate`.

  - Make locate failures explicit (required for correctness):
    - Update `src/uitrace/player/player.py:57` `_handle_window_selector` to raise `UitError(code=ErrorCode.WINDOW_NOT_FOUND, ...)` if `platform.locate(selector)` returns None.
    - Keep “no implicit retries” guardrail: window_selector does one locate; waiting must be done via `wait_until window_found`.

  **Must NOT do**:
  - Do not introduce implicit retries inside `window_selector`; waits must be explicit steps.

  **Recommended Agent Profile**:
  - Category: `unspecified-high`
  - Skills: `test-driven-development`

  **Parallelization**: Can Parallel: YES | Wave 3 | Blocks: 9 | Blocked By: 1

  **References**:
  - WaitUntil model: `src/uitrace/core/models.py:118`
  - Observer pixel wait: `src/uitrace/player/observer.py:86`
  - Player scheduler: `src/uitrace/player/player.py:108`

  **Acceptance Criteria**:
  - [ ] `uv run pytest -q tests/test_player_wait_until_real.py`

  **QA Scenarios**:
  ```
  Scenario: window_found succeeds before timeout
    Tool: Pytest
    Steps: uv run pytest -q tests/test_player_wait_until_real.py
    Expected: Exit 0
    Evidence: .sisyphus/evidence/task-8-player-wait_until.txt

  Scenario: window_found times out → exit code 10
    Tool: Pytest
    Steps: Test expects UitError(ErrorCode.WINDOW_NOT_FOUND)
    Expected: Pass
    Evidence: .sisyphus/evidence/task-8-player-wait_until-timeout.txt
  ```

  **Commit**: YES | Message: `feat(player): execute wait_until steps` | Files: `src/uitrace/player/player.py`, `tests/test_player_wait_until_real.py`

- [ ] 9. Add multi-window fixture trace + CLI dry-run test

  **What to do**:
  - Add `tests/fixtures/trace_v1_multi_window.jsonl` containing a simple A→B→C flow with:
    - multiple `window_selector`/`window_bounds`
    - `wait_until kind="window_found"` before B and C contexts
  - Use this exact JSONL content (so there are no schema/field decisions):
    ```jsonl
    {"v":1,"type":"session_start","ts":0.0,"meta":{"tool":"uitrace","os":"macos","python":"3.12"}}
    {"v":1,"type":"window_selector","ts":0.0,"selector":{"title_regex":".*WindowA.*","app":"AppA","pid":null,"platform":"mac"}}
    {"v":1,"type":"window_bounds","ts":0.0,"bounds":{"x":100,"y":100,"w":800,"h":600},"client_inset":{"l":0,"t":0,"r":0,"b":0}}
    {"v":1,"type":"click","ts":0.2,"pos":{"rx":0.5,"ry":0.5},"screen":{"x":500,"y":400},"button":"left","count":1}
    {"v":1,"type":"wait_until","ts":0.3,"kind":"window_found","selector":{"title_regex":".*WindowB.*","app":"AppB","pid":null,"platform":"mac"},"timeout_ms":5000}
    {"v":1,"type":"window_selector","ts":0.3,"selector":{"title_regex":".*WindowB.*","app":"AppB","pid":null,"platform":"mac"}}
    {"v":1,"type":"window_bounds","ts":0.3,"bounds":{"x":200,"y":150,"w":700,"h":500},"client_inset":{"l":0,"t":0,"r":0,"b":0}}
    {"v":1,"type":"click","ts":0.5,"pos":{"rx":0.4,"ry":0.6},"screen":{"x":480,"y":450},"button":"left","count":1}
    {"v":1,"type":"wait_until","ts":0.6,"kind":"window_found","selector":{"title_regex":".*WindowC.*","app":"AppC","pid":null,"platform":"mac"},"timeout_ms":5000}
    {"v":1,"type":"window_selector","ts":0.6,"selector":{"title_regex":".*WindowC.*","app":"AppC","pid":null,"platform":"mac"}}
    {"v":1,"type":"window_bounds","ts":0.6,"bounds":{"x":250,"y":200,"w":650,"h":450},"client_inset":{"l":0,"t":0,"r":0,"b":0}}
    {"v":1,"type":"click","ts":0.8,"pos":{"rx":0.3,"ry":0.4},"screen":{"x":445,"y":380},"button":"left","count":1}
    {"v":1,"type":"session_end","ts":1.0}
    ```
  - Add `tests/test_play_multi_window_dry_run.py` similar to `tests/test_play_command.py:19` to assert:
    - CLI `play --dry-run` emits step_results for the expected event_type sequence.
    - step numbering is stable and 0-based.

  **Must NOT do**:
  - Do not require macOS permissions; dry-run must work on CI.

  **Recommended Agent Profile**:
  - Category: `quick`
  - Skills: none

  **Parallelization**: Can Parallel: YES | Wave 3 | Blocks: none | Blocked By: 1, 7, 8

  **References**:
  - Existing fixture: `tests/fixtures/trace_v1_valid.jsonl:1`
  - Existing CLI dry-run test: `tests/test_play_command.py:19`

  **Acceptance Criteria**:
  - [ ] `uv run pytest -q tests/test_play_multi_window_dry_run.py`

  **QA Scenarios**:
  ```
  Scenario: play --dry-run emits expected steps for multi-window trace
    Tool: Pytest
    Steps: uv run pytest -q tests/test_play_multi_window_dry_run.py
    Expected: Exit 0
    Evidence: .sisyphus/evidence/task-9-play-multi-window-dry-run.txt
  ```

  **Commit**: YES | Message: `test(fixtures): add multi-window trace and dry-run coverage` | Files: `tests/fixtures/trace_v1_multi_window.jsonl`, `tests/test_play_multi_window_dry_run.py`

- [ ] 10. Update docs for multi-window recording + permissions

  **What to do**:
  - Update `README.md:43` usage examples to include:
    - `uitrace record --follow any --out trace.jsonl`
    - Mention Screen Recording is required for `record` in this mode.
  - Add a short note in “Trace Format” documenting `wait_until.kind="window_found"`.

  **Must NOT do**:
  - Do not rewrite the whole README; keep changes minimal.

  **Recommended Agent Profile**:
  - Category: `writing`
  - Skills: none

  **Parallelization**: Can Parallel: YES | Wave 3 | Blocks: none | Blocked By: 1, 6

  **References**:
  - Existing permissions section: `README.md:26`
  - Trace format section: `README.md:87`

  **Acceptance Criteria**:
  - [ ] `uv run pytest -q` (docs changes must not break tests)

  **QA Scenarios**:
  ```
  Scenario: README reflects new CLI flags
    Tool: Bash
    Steps: rg "--follow" README.md
    Expected: Mentions record --follow any
    Evidence: .sisyphus/evidence/task-10-readme.txt
  ```

  **Commit**: YES | Message: `docs: document multi-window record mode` | Files: `README.md`

## Final Verification Wave (4 parallel agents, ALL must APPROVE)
- [ ] F1. Plan Compliance Audit — oracle
- [ ] F2. Code Quality Review — unspecified-high
- [ ] F3. End-to-end CLI Dry-run QA — unspecified-high
- [ ] F4. Scope Fidelity Check — deep

## Commit Strategy
- Preferred: 4 commits (models, platform, recorder, player+tests+fixture, docs) to keep changes reviewable.
- Commit messages MUST be English.

## Success Criteria
- Multi-window interactions (A→B→C) are captured without loss in `--follow any` mode.
- Trace contains explicit window waits (`wait_until window_found`) on switches.
- Player executes waits/asserts in real mode and returns correct exit codes.
- Full test suite passes.
