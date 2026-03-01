# uitrace: 修复 focus+center 后的 window-relative 点击偏移

## TL;DR
> **Summary**: `play` 时 macOS `focus()` 会触发窗口居中，但系统窗口 bounds 更新存在延迟，导致 click/scroll 可能用到“居中前”的 stale bounds，从而产生与窗口位移等量的点击偏移。
> **Deliverables**:
> - 回放在 `focus + center` 后等待 window bounds 收敛，再执行 click/scroll
> - 新增/增强单测覆盖“bounds 延迟更新导致偏移”的场景（纯 Python fake 平台）
> - 回归验证：`pytest` / `mypy` / `ruff` 全绿
> **Effort**: Short
> **Parallel**: YES — 2 waves
> **Critical Path**: 实现 bounds 收敛等待 → 单测覆盖 race → 全量验证

## Context

### Original Request
用户希望：当前 click/scroll 等 action 是基于 window 相对坐标记录；回放时即便窗口被移动（特别是 `focus window` 后自动 `center`）也必须准确点击，不产生偏移。

### Interview Summary
- 环境：单显示器
- 策略：保持“自动居中”默认行为
- 偏移特征：偏移≈窗口位移（dx/dy），典型 stale bounds/race 信号

### Repo Reality (discovered)
- 录制：`src/uitrace/recorder/recorder.py:68` `_screen_to_relative()` 将 `screen(x,y)` 归一化为 `pos(rx,ry)`；事件同时保存 `screen` 与 `pos`。
- 回放：`src/uitrace/player/executor.py:7` `window_rel_to_screen()` 将 `pos(rx,ry)` + 当前 `bounds` 还原到屏幕坐标；`src/uitrace/player/player.py:84` `_refresh_bounds()` 在 click/scroll 前刷新 bounds。
- macOS 聚焦/居中：`src/uitrace/platform/macos.py:166` `focus()` → `_raise_window()` → `_center_ax_window()`（Accessibility 移动窗口）；Player 目前在 `focus` 后固定 `sleep(0.2)`（`src/uitrace/player/player.py:66` / `src/uitrace/player/player.py:401`）。

### Metis Review (gaps addressed)
- 风险：仅靠“连续两次相同 bounds”可能过早接受旧值（stale 值短时间保持不变），导致偏移复现。
- 决策：等待逻辑必须“基于 baseline（focus 前 bounds）观察到 change 后再收敛”，并且具备超时降级（不抛异常、不死锁）。
- 覆盖：`window_selector` 与 `wait_until(kind=window_found)` 两处 `focus + sleep` 必须一致处理。

## Work Objectives

### Core Objective
在真实回放（非 dry-run）中，窗口 `focus + center` 后 click/scroll 必须使用“居中后的最新 bounds”计算注入坐标，避免 dx/dy 等量偏移。

### Deliverables
- 新增 Player 内部“focus 后等待 bounds 更新并稳定”的收敛逻辑
- 对应单测：模拟 `get_bounds()` 延迟更新，确保 click 注入坐标使用更新后的 bounds

### Definition of Done (verifiable)
- `uv run pytest -q` 返回 0
- `uv run mypy src` 返回 0
- `uv run ruff check .` 返回 0
- 新增测试覆盖以下断言：当 `get_bounds()` 在 focus 后延迟若干次才反映新位置时，最终注入坐标对应新 bounds（不再等量偏移）。

### Must Have
- 不改变 trace v1 schema（`Click.pos` / `Click.screen` 结构不变）
- 不修改坐标数学公式（`_screen_to_relative`、`window_rel_to_screen` 不动）
- 等待逻辑有明确 timeout，且 timeout 后降级继续执行（不挂死、不抛新异常）

### Must NOT Have (guardrails)
- 不新增 CLI 开关/配置项（本次保持行为一致，仅修复偏移）
- 不引入多显示器/Retina/阴影 inset 等额外议题（单独 issue）
- 不修改 `Platform` 协议接口（`src/uitrace/platform/base.py`）

## Verification Strategy
> ZERO HUMAN INTERVENTION — all verification is agent-executed.
- Test decision: tests-after（pytest）
- QA policy: 每个实现任务提供 2 个场景（正常收敛 / 超时降级）
- Evidence: 写入 `.sisyphus/evidence/`（命令输出/pytest log）

## Execution Strategy

### Parallel Execution Waves

Wave 1 (implementation + tests)
- Task 1-3

Wave 2 (verification + hardening)
- Task 4

### Dependency Matrix (full)
- Task 1 blocks Task 2
- Task 2 blocks Task 3
- Task 3 blocks Task 4

### Agent Dispatch Summary
- Wave 1: 3 tasks — category `unspecified-high` (core logic + tests)
- Wave 2: 1 task — category `quick` (run verifications)

## TODOs
> Implementation + Test = ONE task. Never separate.
> EVERY task includes QA Scenarios.

- [ ] 1. 在 Player 中实现 focus 后 bounds 收敛等待（避免 stale bounds）

  **What to do**:
  - 在 `src/uitrace/player/player.py` 的 `Player` 类中新增私有方法（命名固定）：`_wait_bounds_settle_after_focus()`。
    - 入参：`win: WindowRef`, `baseline: Rect`
    - 行为：
      1) 以 `baseline` 作为 focus 前 bounds
      2) **该方法本身不调用** `platform.focus(win)`；由调用方先 focus，再调用该方法
      3) focus 后轮询 `platform.get_bounds(win)`
      4) **仅当观察到 bounds 与 baseline 不同（change observed）后**，再要求“连续 2 次读取相同 bounds”（stable）才返回
      5) 超时后返回“最后一次读取到的 bounds”（若一直 None 则回退 baseline），不得抛异常
    - 轮询参数（写死常量，避免新配置项）：
      - `POLL_INTERVAL_S = 0.05`
      - `TIMEOUT_MS = 1000`
      - `STABLE_READS = 2`
    - 终止条件使用 **poll 次数**（`max_polls = ceil(TIMEOUT_MS / (POLL_INTERVAL_S*1000))`），不要依赖真实时间；sleep 使用 `self._sleep(POLL_INTERVAL_S)`。
  - 替换 Player 里两处 `focus + sleep(0.2)`：
    - `src/uitrace/player/player.py:57` `_handle_window_selector()`：
      - 在 focus 前先抓 baseline：`baseline = self._platform.get_bounds(win) or win.bounds`
      - focus 后调用 `_wait_bounds_settle_after_focus(win, baseline)`
      - 将返回的 bounds 用作后续 `current_bounds`（建议：让 `_handle_window_selector` 返回 `(win, bounds)` 并在 run loop 里赋值）
    - `src/uitrace/player/player.py:343` `wait_until(kind="window_found")` 成功后：
      - baseline 同上；focus 后调用 `_wait_bounds_settle_after_focus`
      - 更新 `current_bounds`（避免后续 click 使用旧值）

  **Must NOT do**:
  - 不修改坐标公式：`src/uitrace/player/executor.py:7` `window_rel_to_screen()`、`src/uitrace/recorder/recorder.py:68` `_screen_to_relative()`
  - 不修改 `Platform` 协议：`src/uitrace/platform/base.py`
  - 不新增 CLI 参数/配置项

  **Recommended Agent Profile**:
  - Category: `unspecified-high` — Reason: 需要修改核心回放逻辑并补齐测试覆盖
  - Skills: [`systematic-debugging`] — Reason: 需要验证 race / stale-bounds 的根因与收敛策略

  **Parallelization**: Can Parallel: NO | Wave 1 | Blocks: Task 2 | Blocked By: —

  **References**:
  - Focus + sleep 现状：`src/uitrace/player/player.py:66`、`src/uitrace/player/player.py:401`
  - click 前刷新 bounds：`src/uitrace/player/player.py:84` `_refresh_bounds()`
  - window_found 轮询模式参考：`src/uitrace/player/player.py:371`
  - wait_until_pixel 轮询模式参考：`src/uitrace/player/observer.py:86`
  - 坐标还原公式：`src/uitrace/player/executor.py:7`

  **Acceptance Criteria**:
  - [ ] 新增 `_wait_bounds_settle_after_focus()` 并在两处 focus 路径使用
  - [ ] `uv run pytest -q tests/test_player_click_refresh_real.py > .sisyphus/evidence/task-1-pytest.txt` 返回 0
  - [ ] `uv run pytest -q tests/test_player_wait_until_real.py > .sisyphus/evidence/task-1-wait-until.txt` 返回 0

  **QA Scenarios**:
  ```
  Scenario: Bounds 延迟更新也不偏移
    Tool: Bash
    Steps:
      1) uv run pytest -q tests/test_player_click_refresh_real.py > .sisyphus/evidence/task-1-pytest.txt
    Expected:
      - 新增的“focus 后延迟更新 bounds”测试通过
      - click 注入坐标使用更新后的 bounds（不等量偏移）
    Evidence: .sisyphus/evidence/task-1-pytest.txt

  Scenario: Bounds 一直不变（超时降级）
    Tool: Bash
    Steps:
      1) uv run pytest -q tests/test_player_wait_until_real.py > .sisyphus/evidence/task-1-wait-until.txt
    Expected:
      - 测试运行不超时、不死锁
      - wait_until(window_found) 相关测试依然通过
    Evidence: .sisyphus/evidence/task-1-wait-until.txt
  ```

  **Commit**: YES | Message: `fix(player): wait for updated bounds after focus centering` | Files: [`src/uitrace/player/player.py`, `tests/test_player_click_refresh_real.py`, (optional) `tests/test_player_wait_until_real.py`]

- [ ] 2. 增加“stale bounds 保持不变后才跳变”的回归单测

  **What to do**:
  - 在 `tests/test_player_click_refresh_real.py` 增加一个新的 fake 平台（命名固定）：`StaleThenJumpPlatform`。
    - `get_bounds()` 在前 2 次调用返回旧 bounds（与 baseline 完全相同），第 3 次开始返回新 bounds
    - 事件序列包含：`session_start` → `window_selector` → `window_bounds` → `click`
    - 新测试函数名固定：`test_click_waits_for_bounds_change_after_focus()`
    - bounds 取值固定：
      - old: `Rect(x=100, y=100, w=400, h=300)`
      - new: `Rect(x=300, y=200, w=400, h=300)`
    - click 取值固定：`Pos(rx=0.5, ry=0.5)`（窗口中心）
    - 断言固定：最终 `inject_click(x,y,...)` 的 `(x,y)` 必须等于新 bounds 中心 `(500, 350)`
  - 确保该测试在没有 Task 1 改动时会失败（即：旧逻辑仅调用 `get_bounds` 两次，不足以看到 jump），在 Task 1 后通过。

  **Must NOT do**:
  - 不引入真实 macOS 依赖（纯 fake 平台 + 单测即可）
  - 不把睡眠写成真实 `time.sleep`（避免测试变慢）

  **Recommended Agent Profile**:
  - Category: `unspecified-high` — Reason: 需要构造稳定复现的竞态回归用例
  - Skills: [`test-driven-development`] — Reason: 先让测试红，再落地收敛逻辑更稳

  **Parallelization**: Can Parallel: YES | Wave 1 | Blocks: Task 3 | Blocked By: Task 1

  **References**:
  - 现有 fake 平台样例：`tests/test_player_click_refresh_real.py:19`
  - click 注入断言：`tests/test_player_click_refresh_real.py:70`

  **Acceptance Criteria**:
  - [ ] `uv run pytest -q tests/test_player_click_refresh_real.py > .sisyphus/evidence/task-2-pytest.txt` 返回 0

  **QA Scenarios**:
  ```
  Scenario: 回归用例可稳定复现并被修复
    Tool: Bash
    Steps:
      1) uv run pytest -q tests/test_player_click_refresh_real.py > .sisyphus/evidence/task-2-pytest.txt
    Expected:
      - 新增测试稳定通过
    Evidence: .sisyphus/evidence/task-2-pytest.txt

  Scenario: 坐标数学不被破坏
    Tool: Bash
    Steps:
      1) uv run pytest -q tests/test_executor_math.py > .sisyphus/evidence/task-2-executor-math.txt
    Expected:
      - window_rel_to_screen 的中心/边界/clamp 测试仍通过
    Evidence: .sisyphus/evidence/task-2-executor-math.txt
  ```

  **Commit**: NO | Message: — | Files: — (此任务建议并入 Task 1 提交，避免拆散 bugfix)

- [ ] 3. 回归：确保 wait_until(window_found) 的 focus 路径不会再次引入偏移

  **What to do**:
  - 在 `tests/test_player_wait_until_real.py` 新增一个小测试：
    - 构造 `wait_until(kind="window_found")` 成功后紧跟 `window_bounds` 与 `click`
    - fake 平台在 focus 后 `get_bounds()` 先返回旧值再跳变
    - 断言 click 注入坐标使用跳变后的新 bounds

  - 新测试函数名固定：`test_window_found_focus_waits_for_bounds_change_before_click()`
  - bounds 取值与 Task 2 保持一致（old/new 同值），click 仍使用 `Pos(rx=0.5, ry=0.5)`，断言注入坐标为 `(500, 350)`

  **Must NOT do**:
  - 不修改 `wait_until window_found` 的 locate 语义（仍按 selector 轮询）

  **Recommended Agent Profile**:
  - Category: `unspecified-high` — Reason: 覆盖第二条 focus 路径，避免同类 bug 漏网
  - Skills: []

  **Parallelization**: Can Parallel: YES | Wave 1 | Blocks: Task 4 | Blocked By: Task 1

  **References**:
  - window_found focus 现状：`src/uitrace/player/player.py:400`
  - window_found 测试文件：`tests/test_player_wait_until_real.py:176`

  **Acceptance Criteria**:
  - [ ] `uv run pytest -q tests/test_player_wait_until_real.py > .sisyphus/evidence/task-3-pytest.txt` 返回 0

  **QA Scenarios**:
  ```
  Scenario: window_found 路径也能等待 bounds 更新
    Tool: Bash
    Steps:
      1) uv run pytest -q tests/test_player_wait_until_real.py > .sisyphus/evidence/task-3-pytest.txt
    Expected:
      - 新增测试通过
      - 现有 window_found / pixel wait_until 测试均通过
    Evidence: .sisyphus/evidence/task-3-pytest.txt

  Scenario: 超时不会阻塞回放
    Tool: Bash
    Steps:
      1) uv run pytest -q tests/test_player_wait_until_real.py -k timeout > .sisyphus/evidence/task-3-timeout.txt
    Expected:
      - timeout 用例仍按预期抛出 UitError(WINDOW_NOT_FOUND)
    Evidence: .sisyphus/evidence/task-3-timeout.txt
  ```

  **Commit**: NO | Message: — | Files: —

- [ ] 4. 全量验证与最小回归检查

  **What to do**:
  - 运行质量门禁：ruff / mypy / pytest
  - 确认没有引入新的长时间 sleep（仅收敛等待轮询）

  **Recommended Agent Profile**:
  - Category: `quick` — Reason: 主要是命令执行与输出核对
  - Skills: []

  **Parallelization**: Can Parallel: NO | Wave 2 | Blocks: Final Verification Wave | Blocked By: Task 1-3

  **References**:
  - Dev 命令：`README.md:116`

  **Acceptance Criteria**:
  - [ ] `uv run ruff check . > .sisyphus/evidence/task-4-ruff.txt` 返回 0
  - [ ] `uv run mypy src > .sisyphus/evidence/task-4-mypy.txt` 返回 0
  - [ ] `uv run pytest -q > .sisyphus/evidence/task-4-pytest.txt` 返回 0

  **QA Scenarios**:
  ```
  Scenario: 全量测试绿
    Tool: Bash
    Steps:
      1) uv run pytest -q > .sisyphus/evidence/task-4-pytest.txt
    Expected:
      - exit code 0
    Evidence: .sisyphus/evidence/task-4-pytest.txt

  Scenario: 静态检查绿
    Tool: Bash
    Steps:
      1) uv run ruff check . > .sisyphus/evidence/task-4-ruff.txt
      2) uv run mypy src > .sisyphus/evidence/task-4-mypy.txt
    Expected:
      - 两条命令 exit code 0
    Evidence: .sisyphus/evidence/task-4-ruff.txt / .sisyphus/evidence/task-4-mypy.txt
  ```

  **Commit**: NO | Message: — | Files: —

## Final Verification Wave (4 parallel agents, ALL must APPROVE)
- [ ] F1. Plan Compliance Audit — oracle
- [ ] F2. Code Quality Review — unspecified-high
- [ ] F3. Real Manual QA — unspecified-high
- [ ] F4. Scope Fidelity Check — deep

## Commit Strategy
- 1 commit (recommended): `fix(player): wait for updated bounds after focus centering`

## Success Criteria
- 录制仍保持 window-relative (`pos`)；回放在 `focus + center` 后 click/scroll 不再出现与窗口位移等量的偏移。
