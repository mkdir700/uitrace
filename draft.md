## 0) 项目目标与非目标

### 目标

* CLI：列出窗口 → 选择窗口 → 录制操作 → 生成 `trace.jsonl`
* 回放：基于 `trace.jsonl`，可控地重放（可分段、可 dry-run、可输出 step_result）
* 轨迹：对 Agent 友好（可解释、可参数化、可校验），不仅是原始事件 dump

### 非目标（MVP 不做）

* Wayland 完整支持（Linux 先 X11 或仅提供“受限模式”）
* OCR/模板匹配（先用像素锚点/窗口断言）
* UIA/AX 控件级别操作（先做坐标+锚点）

---

## 1) 技术栈与依赖（建议清单）

### 基础

* 包管理/虚拟环境：`uv`
* CLI：`typer`（命令行体验好）
* 输出/交互：`rich`（可选，但很建议）
* 类型与校验：`pydantic>=2`
* JSONL：标准库 `json` + pydantic 序列化

### 输入监听（录制）

* 跨平台优先：`pynput`

  * 鼠标 move/down/up/scroll，键盘 hotkey
  * 现实：macOS 需要 Accessibility 权限；Wayland 下可能受限

### 输入注入（回放）

* 简单可靠：`pyautogui`

  * 现实：macOS 也需要 Accessibility；部分环境会受限
* 更底层/更稳（后续扩展）：每平台各自实现注入（SendInput/CGEventPost/XTest）

### 窗口枚举/定位

* MVP（跨平台但不完美）：`pygetwindow`
* 生产更稳：做平台层：

  * Windows：`pywin32` 或 `ctypes` 调 Win32 API
  * macOS：`pyobjc`（Quartz / AppKit）
  * Linux X11：`python-xlib`

> 建议：**MVP 用 pygetwindow + 少量平台补丁**；等功能跑通后，再把窗口能力替换成自研平台层（接口不变）。

---

## 2) 项目结构（uv + 可扩展架构）

```
uitrace/
  pyproject.toml
  README.md
  src/uitrace/
    __init__.py
    cli.py

    core/
      models.py          # Pydantic 模型：事件、结果、schema 版本
      schema.py          # 版本迁移、校验器、兼容策略
      clock.py           # 单调时钟、时间戳
      jsonl.py           # JSONL 读写（流式）
      errors.py          # 统一错误与退出码
      logging.py         # 可选：结构化日志

    recorder/
      recorder.py        # 录制主逻辑：过滤、归一化、合并
      capture.py         # pynput 封装：事件回调
      hotkeys.py         # 停止/暂停热键管理
      summarize.py       # raw->semantic 归纳（可先轻量）

    player/
      player.py          # 回放主逻辑：step 执行、重试、观测
      executor.py        # 注入执行器（pyautogui）
      observer.py        # 观测：窗口/像素采样、断言
      locate.py          # 窗口定位：selector + probe

    platform/
      base.py            # WindowProvider 抽象接口
      auto.py            # 自动选择当前平台 provider
      win32.py
      macos.py
      x11.py

    tools/
      show.py            # pretty-print trace
      validate.py        # schema 校验
```

---

## 3) CLI 规格（命令、参数、退出码）

### 命令一览

* `uitrace list`：列出可选窗口
* `uitrace record`：录制，输出 JSONL
* `uitrace play`：回放
* `uitrace show`：人类可读展示
* `uitrace validate`：schema 校验与版本迁移提示

### `uitrace list`

```
uitrace list [--json]
```

输出包含：

* `id`（内部索引）
* `title`
* `pid`
* `app/exe`（能拿到则提供）
* `bounds`（x,y,w,h）

### `uitrace record`

```
uitrace record \
  --out traces/foo.jsonl \
  [--select fzf|prompt] \
  [--window-id 3] \
  [--countdown 3] \
  [--sample-window-ms 200] \
  [--include-move false] \
  [--merge true] \
  [--hotkey-stop "ctrl+shift+s"] \
  [--hotkey-pause "ctrl+shift+r"]
```

关键行为：

* 选择窗口后，**只记录落在该窗口范围内**的鼠标事件
* 每 `sample-window-ms` 采样窗口 bounds，变化则写 `window_bounds`
* 默认 **丢弃鼠标 move** 或降采样（否则 JSONL 爆炸）
* 默认做轻量合并：click/scroll 合并

### `uitrace play`

```
uitrace play traces/foo.jsonl \
  [--speed 1.0] \
  [--from-step N] \
  [--to-step M] \
  [--focus] \
  [--dry-run] \
  [--on-fail screenshot|abort|continue] \
  [--report out.jsonl]
```

输出（stdout）逐步打印 **machine-readable** 的 `step_result`（JSON 一行一条），Agent 可直接消费。

### 退出码（建议固定）

* `0`：成功
* `2`：参数错误
* `10`：窗口找不到/定位失败
* `11`：权限不足（macOS Accessibility）
* `20`：断言失败
* `30`：执行注入失败
* `40`：schema 校验失败

---

## 4) JSONL 轨迹规格（Agent 友好 DSL v1）

### 基本原则

* 每行一个对象
* 必须包含：`v`（schema version）、`type`、`ts`（秒，录制开始相对时间）
* 坐标统一为 `pos: { rx, ry }` 相对窗口客户区（0~1）

### 核心事件类型（MVP）

1. `session_start`
2. `window_selector`（目标窗口选择器）
3. `window_bounds`（窗口几何，允许多次出现）
4. `click`
5. `scroll`
6. `assert`（至少 window title / pixel 两种）
7. `wait_until`（像素等待，V2 但建议尽早）
8. `session_end`

#### 示例

```json
{"v":1,"type":"session_start","ts":0.0,"meta":{"tool":"uitrace","os":"macos","dpi_scale":2.0}}
{"v":1,"type":"window_selector","ts":0.0,"selector":{"title_regex":".*Notion.*","app":"Notion","pid":1234}}
{"v":1,"type":"window_bounds","ts":0.0,"bounds":{"x":100,"y":80,"w":1200,"h":900},"client_inset":{"l":0,"t":28,"r":0,"b":0}}
{"v":1,"type":"assert","ts":0.2,"kind":"window_title_contains","value":"Notion"}
{"v":1,"type":"click","ts":1.2,"pos":{"rx":0.52,"ry":0.31},"button":"left","count":1}
{"v":1,"type":"scroll","ts":1.8,"pos":{"rx":0.60,"ry":0.88},"delta":{"y":-240}}
{"v":1,"type":"session_end","ts":5.0}
```

> `client_inset`：窗口外框到客户区的内边距（标题栏高度等）。Windows 很好拿；macOS/X11 初期可以先近似为 0 或仅 t=标题栏高度（后续完善）。

---

## 5) Pydantic Schema（强类型约束）

### 事件基类

* 用 `discriminated union`（按 `type` 分派）
* `extra="forbid"`，防止脏字段进入轨迹文件
* `v` 固定为 1（未来做 v2/v3 迁移）

**建议字段**

* `v: Literal[1]`
* `type: Literal[...]`
* `ts: float`（>=0）
* 可选 `step_id: int`（回放时生成更方便）

### WindowSelector

建议最少包含：

* `title_regex: str | None`
* `title: str | None`
* `pid: int | None`
* `app: str | None`
* `exe: str | None`
* `platform: Literal["win","mac","x11"] | None`

### Pos（相对坐标）

* `rx, ry` float，范围 `[0,1]`（可允许轻微越界，回放时 clamp）

### Assert / WaitUntil

* `kind`：

  * `window_title_contains`
  * `pixel`（pos + rgb + tolerance）
* wait_until 增加 `timeout_ms`

> 你先实现 `window_title_contains` + `pixel` 这两种，稳定性会立刻提升一个数量级。

---

## 6) 核心接口定义（便于平台替换）

### WindowProvider（平台层抽象）

```python
class WindowRef(BaseModel):
    handle: str  # 平台相关句柄（字符串化）
    title: str
    pid: int | None = None
    app: str | None = None
    bounds: Rect

class WindowProvider(Protocol):
    def list_windows(self) -> list[WindowRef]: ...
    def focus(self, win: WindowRef) -> None: ...
    def get_bounds(self, win: WindowRef) -> Rect: ...
    def window_from_point(self, x: int, y: int) -> WindowRef | None: ...
    def locate(self, selector: WindowSelector) -> WindowRef | None: ...
```

### Observer（观测）

* `get_pixel(win, pos) -> (r,g,b)`（从屏幕采样；先不做窗口截图裁剪，直接用屏幕坐标即可）
* `get_active_window() -> WindowRef`

### Executor（注入）

* `click(screen_x, screen_y, button, count)`
* `scroll(screen_x, screen_y, delta_y)`
* `type_text(text, method="paste")`
* `hotkey(keys)`

---

## 7) Recorder 逻辑规格（过滤、归一化、合并）

### 录制主循环

* 选定 `target_window`
* 开始捕获全局事件
* 对每个事件：

  1. 获取当前窗口 bounds（缓存 + 定期刷新）
  2. 判断事件点是否在目标窗口客户区（或先用 window rect 近似）
  3. 转为相对坐标 `rx/ry`
  4. 写入 JSONL（raw 或 semantic）

### 合并策略（建议默认开启）

* click：`down+up` 合并为 `click`
* scroll：50ms 内的滚轮合并（delta 累加）
* move：默认丢弃或 100ms 采样一次（可开关）

### 窗口变化

* 每 `sample-window-ms` 获取 bounds
* 变化（move/resize）则写 `window_bounds`

---

## 8) Player 逻辑规格（定位、断言、回放、可控）

### 回放流程

1. 读取 JSONL → validate（pydantic）→ 得到 event list
2. 定位窗口：`provider.locate(selector)`

   * 找不到 → exit 10
3. 若 `--focus`：focus
4. 初始化时钟：按 `ts/speed` 控制节奏
5. 遍历 step：

   * `assert`：失败 → exit 20（或按策略处理）
   * `wait_until`：轮询像素到满足/超时
   * `click/scroll`：把 `rx/ry + 当前 bounds` → 屏幕坐标 → executor 执行
6. 每步输出 `step_result`（JSONL/stdout）

### `step_result` 建议字段

* `step`
* `type`
* `ok`
* `elapsed_ms`
* `error`（可选）
* `observed`（可选：当前窗口 bounds、像素值等）

---

## 9) uv 项目管理（pyproject.toml 关键片段）

建议用：

* `project.scripts` 暴露 `uitrace`
* 分组依赖：`dev` / `win` / `mac` / `x11`

示意（精简版）：

* `dependencies`: typer, pydantic, rich, pynput, pyautogui
* `optional-dependencies`: win/mac/x11 平台依赖

> 实际版本号你可以先不锁死，MVP 跑通再做 pin。

---

## 10) 版本策略与可迁移性（Agent 长期要用）

* `v=1` 固定 schema
* 未来加字段：必须兼容（新增 optional）
* 未来结构大改：出 `v=2`，提供 `uitrace migrate`（可选）
* `validate` 命令要能输出：第几行、哪个字段错、建议修复

---

## 11) 最小交付清单（你开工即用）

### 你第一阶段（MVP）应该交付的“完成定义”

* [ ] `list` 可列出窗口并可选
* [ ] `record` 输出合法 JSONL（包含 session_start/window_selector/window_bounds/click/scroll/session_end）
* [ ] `play` 可重放 click/scroll
* [ ] `validate` 能严格校验（extra forbid）
* [ ] `play` 每步输出 `step_result`
* [ ] 至少一种断言：`window_title_contains`
* [ ] 至少一种锚点：`pixel`（采样 + tolerance）

---

## 12) 你接下来我建议的实现顺序（最短路径）

1. 先把 **Pydantic models + JSONL reader/writer + validate CLI** 写好（schema 先立住）
2. 做 WindowProvider：先用 `pygetwindow` 兜底实现 `list/locate/focus/get_bounds`
3. Recorder：用 `pynput` 录 `click/scroll`（先不做键盘）
4. Player：用 `pyautogui` 回放 click/scroll
5. Observer：加 `pixel assert / wait_until`（用屏幕采样，先不裁剪窗口截图）

---

如果你认可这套规格，我可以下一步直接给你：

* **Pydantic 模型完整代码（v1）**（含 discriminated union）
* `uitrace validate/show` 的可运行实现
* `record/play` 的最小可运行骨架（先跑通 Windows 或 macOS 任一平台）

## 补充

) macOS 先跑通：你要面对的 3 个“现实门槛”
(1) Accessibility 权限（必须）

macOS 上：

**监听全局输入（event tap）**需要 Accessibility

**注入输入（点击/滚轮/键盘）**同样需要 Accessibility
所以你要在 README/CLI 里把权限引导做成“强制前置检查”。

建议 CLI 增加：

uitrace doctor：检测权限、给出引导

uitrace record/play 开始前自动检查，没有就退出（exit code 11）

(2) “窗口枚举/几何信息”与“客户区”不完全等价

macOS 能拿到 window bounds（通常是窗口外框），但“客户区坐标”不如 Win32 那么标准化。
MVP 先这样处理：

先用 window bounds 近似客户区（rx/ry 仍然可用）

后续再引入 client_inset.t（标题栏高度）做修正（可先手动测/近似）

(3) 事件过滤：只能做到“鼠标点位命中窗口”

“只录某个窗口内操作”的 MVP 做法：

全局监听鼠标事件

每次事件发生时，用屏幕点位 (x,y) 去做 window_from_point（或用 bounds 判断）

命中目标窗口则记录，否则丢弃

macOS 这一块的实现建议走 Quartz / CGWindowList（pyobjc）而不是完全依赖 pygetwindow。

3) macOS 技术栈（你要的：uv + pydantic）
必选依赖（macOS MVP）

pydantic>=2

typer

rich（强烈建议，用来做 list/record UI）

pyobjc-framework-Quartz（窗口信息、event tap、事件注入都能用）

（可选）pynput：你也可以用它先跑通录制，但最终建议转 Quartz event tap（更可控）

为什么推荐 Quartz（pyobjc）统一做监听+注入

少一层依赖/行为更明确

事件时间戳、坐标体系更一致

失败时更容易定位到底是权限问题还是库兼容问题

结论：macOS MVP 用 Quartz 一把梭（窗口枚举 + 输入监听 + 输入注入）。

4) macOS MVP 的功能切片（最短落地路径）
里程碑 M1：只做“回放 click/scroll”

uitrace list：列窗口（title, pid, bounds）

uitrace record：先不做！先手写一个小 trace.jsonl

uitrace play trace.jsonl：能 focus 窗口并 click/scroll

目标：把“注入链路 + 权限链路”先跑通

里程碑 M2：再做“录制 click/scroll”

用 event tap 录制鼠标 down/up/scroll

做窗口过滤（点位命中目标窗口）

输出 JSONL

里程碑 M3：加“锚点/断言”（Agent 可用的关键）

assert window_title_contains

assert pixel + wait_until pixel

回放失败时输出 step_result（Agent 可诊断）

5) macOS 平台层规格（你按接口实现就行）
WindowProvider.macos（建议能力）

list_windows()：用 CGWindowListCopyWindowInfo

locate(selector)：按 app/title_regex/pid 过滤候选

focus(win)：MVP 可以先做“提示用户把窗口置前”，后续用 Accessibility API 做激活（更稳）

get_bounds(win)：直接返回 bounds

window_from_point(x,y)：macOS 没有完全等价 WindowFromPoint 的简洁 API
MVP 做法：遍历当前窗口列表（按 z-order）找第一个 bounds 包含点位的窗口

这套“bounds 命中测试”在多数 GUI 场景足够用，且实现简单。

6) JSONL v1（macOS MVP 建议固定字段）

你先保持这个最小集合（足够 Agent 用）：

session_start

window_selector

window_bounds

click

scroll

assert（window_title_contains / pixel）

wait_until（pixel）

session_end

并且明确：

pos.rx/ry 基于 window_bounds（MVP 先这样）

后续引入 client_inset 修正时，不破坏 v1（只新增 optional 字段）

7) uv 项目初始化建议（你可以照着做）

repo：uitrace

包名：uitrace

CLI：uitrace

你需要的核心文件：

src/uitrace/cli.py：typer app

src/uitrace/core/models.py：pydantic schema（discriminated union）

src/uitrace/platform/macos.py：Quartz 实现

src/uitrace/recorder/ 与 src/uitrace/player/

（你要我也可以下一步直接给你一份完整目录+最小可运行代码骨架）

8) 我建议你把“权限与可观测性”当作一等公民

为了让 Agent 稳定调用，你应该强制做到：

uitrace doctor：输出 JSON（机器可读）+ 人类说明

play 每一步输出 step_result（JSONL）

--dry-run：只输出计划动作，不注入

错误退出码固定（尤其 11：权限不足）

