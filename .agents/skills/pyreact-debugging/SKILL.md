---
name: pyreact-debugging
description: 调试运行在网易我的世界基岩版 ModSDK 中的 Pyreact-MC UI 框架。需要启动游戏、调整窗口尺寸测试 UI 适配、检查 UI 树、模拟交互、查看日志、定位渲染问题或分析性能时使用；必要时支持截取游戏窗口并供多模态模型读取。
metadata:
  audience: agents
  domain: pyreact-debugging
  platform: netease-minecraft-bedrock-modsdk
---

## 我能做什么

- 启动携带日志服务的游戏实例（自动生成 `.cppconfig`，无需 mcpywrap）
- 实时流式接收游戏日志，log server 跟随游戏进程生命周期
- 通过剪贴板 seq 协议检查 Pyreact UI 树 / 子树
- 模拟按钮点击、Input 文本输入、Slider 数值变化或 ScrollView 像素滚动，并读取滚动位置
- 调整 Minecraft 游戏客户区尺寸，测试常见宽高比下的 UI 适配
- 必要时截取 Minecraft 游戏窗口，并在多模态模型中读取画面检查实际 UI
- 启停性能 profile
- 通过游戏内嵌 Tracy server 做函数级 CPU 采样、热点排行和前后 diff

## 什么时候使用

- 需要启动游戏进行 Pyreact UI 调试
- 检查运行时 UI 树结构（节点 id / type / props / style / layout / opacity）
- 定位渲染 bug（节点未渲染、布局异常、props 未生效、opacity 继承错误）
- 切换窗口宽高比，验证响应式布局和 ScreenSizeChanged 后的重排
- 检查实际画面中的错位、遮挡、裁剪、颜色、透明度、贴图和文字可读性
- 模拟按钮点击或文本输入，验证交互逻辑与受控值回写
- 做性能分析
- 需要量化 Pyreact/Mod 函数耗时、比较优化前后结果

## 通信架构

```
外部脚本 ──剪贴板请求 JSON──▶ 游戏 PyreactScreenNode.Update 每帧轮询
                              │  poll_clipboard 解析 cmd
外部脚本 ◀──剪贴板响应 JSON───┘  SetClipboardContent({pyreact_ack,seq,tree,error})

游戏日志  ──TCP stream──────────────▶ log server（内存 + 文件）
外部脚本 ──HTTP GET  /logs──────────▶ log server
外部脚本 ──Win32 SetWindowPos───────▶ Minecraft 客户区尺寸
外部脚本 ──PrintWindow / XComposite──▶ Minecraft 后台客户区 ──PNG──▶ 多模态模型
```

- UI 检查/交互走剪贴板通道（`_protocol.py` 封装，依赖 pyperclip）
- 请求 `{"pyreact_debug":{"cmd":"dump_tree|dump_subtree|click|set_input|set_slider|scroll|get_scroll|navigator|ping","id":...,"value":...,"seq":N}}`，响应 `{"pyreact_ack":true,"seq":N,"tree":...,"result":...,"error":null}`，**按 seq 匹配**丢弃过期内容
- 日志优先通过 HTTP `/logs` 从 log server 内存获取；HTTP 不可达时 `get_logs.py` 自动回退到读 log server 持久化的日志文件（`--from-file` 显式指定）
- log server 跟随游戏进程生命周期，HTTP API 监听 `port+1`

### 视觉检查能力

- `capture_screen.py` 使用 Windows `PrintWindow(PW_RENDERFULLCONTENT)` 或 Linux X11/XWayland Composite 在后台截取 Minecraft 窗口，不改变当前焦点和 Z 序，也不依赖 Pillow、pyautogui 或其他第三方截图包。
- **不要轻易使用 `capture_screen.py`。** 优先使用 `get_ui_tree.py`、`query_tree.py`、`diff_ui_tree.py`、`expect.py`、日志和源码分析定位问题，避免用截图代替可重复、可断言的结构化检查。
- 仅在以下情况使用截图：其他工具实在无法定位且问题必须观察实际像素；已经经历很长时间或很多轮迭代，需要确认视觉结果是否收敛；完成 breaking change 后，需要快速确认是否明显改坏。
- 不要在每次交互或每个适配档位后机械截图。先用 UI 树、layout diff、断言和日志验证；只有满足上述条件时才截取关键状态。
- 使用截图时，先确认当前模型支持图像输入/本地图片读取，再执行脚本并用运行环境提供的本地图片读取工具打开输出 PNG。只运行脚本并得到路径不算完成视觉检查。
- 当当前模型不支持图像输入时，仍可为用户保存截图，但不得声称已经看过或判断过画面；继续使用 UI 树、日志和用户反馈完成文本侧诊断。
- 窗口截图只包含游戏窗口客户区，其他窗口遮挡目标窗口不影响结果；`--region` 模式才直接读取桌面区域。
- 视觉结果与 UI 树互为补充：视觉检查负责实际像素，`get_ui_tree.py` 负责节点、props、style 和 layout。定位问题时应尽量同时获取二者。

### 窗口尺寸适配档位

- 使用 `resize_window.py` 调整 Minecraft **客户区**尺寸。测试 UI 适配时建议依次覆盖 `20:9`、`4:3`、`16:10`、`16:9` 四个档位。
- 默认统一使用 1080 客户区高度：`20:9 = 2400x1080`、`4:3 = 1440x1080`、`16:10 = 1728x1080`、`16:9 = 1920x1080`。统一高度能把主要变量保持为宽高比。
- 每次 resize 后先等待脚本返回并确认 `ok=true`、`actualClient` 等于 `requestedClient`，再 dump UI 树或执行断言。不要仅凭命令退出码假设窗口尺寸已经生效。
- 测适配优先比较各档位的 UI 树、layout diff 和关键节点断言。截图仍遵守上面的严格使用条件，不要因为切换了档位就自动截图。

### Tracy 性能前置条件

- 游戏运行时内嵌 native Tracy server，默认监听 `127.0.0.1:8086`。
- 首次使用先运行 `python3 tracy.py setup`，从上游 `mcdk-mcp-tracy` 固定 commit 下载并校验 `tracy-capture.exe` 与 `tracy-csvexport.exe`。
- Tracy 采样不依赖 MCDK，MC Studio 启动的游戏也可采样。
- 采样窗口内必须制造真实负载。静止游戏可能没有有意义的 zone 数据。

## 启用调试功能

调试默认关闭（每帧零开销）。推荐在运行时初始化处统一开启，manual root 与全局 navigator 创建的 Screen 都会继承该设置：

```python
import pyreact

# ClientSystem.__init__
pyreact.runtime_init(self, debug=True)
```

`debug` 只允许在首次 `runtime_init` 时设置。`create_root`、`Root` 和 `navigator`
不提供单独或动态调试开关；初始化后再次调用 `runtime_init` 也不会改变该值。

开启后 `PyreactScreenNode.Update` 每帧调 `debug.poll_clipboard(host)`，处理 `dump_tree` / `dump_subtree` / `click` / `set_input` / `set_slider` / `scroll` / `get_scroll` / `navigator` / `ping` 命令。游戏侧实现见 `pyreact/debug.py`。

## 前置依赖

外部脚本运行在 CPython 3。所有协作开发机器都应从 `PATH` 提供 `python3` 和 `pip3`；不得写死解释器的本机绝对路径。依赖：
- `pyperclip`：剪贴板访问（`clipboard_ipc.py` 封装）
- `psutil`：进程管理（`launch_game.py` / `kill_game.py`）
- `requests`：HTTP 客户端（`get_logs.py`）

安装：Windows 使用 `pip install pyperclip psutil requests`；Linux 使用 `python3 -m pip install pyperclip psutil requests`。

Linux 游戏目录在脚本目录的 `config.py` 中通过 `LINUX_GAME_DIR` 配置，Wine 前缀默认从上级 `.wine-mcchina` 自动发现。临时覆盖可使用 `--engine-dir` / `--wine-prefix`，或设置 `MCCHINA_ENGINE_DIR` / `MCCHINA_WINEPREFIX`。Windows 仍使用 MC Studio 注册表自动发现。以下示例中的 `python` 在 Linux 下替换为 `python3`。

## 脚本参考

所有脚本位于 `.agents/skills/pyreact-debugging/scripts/`，用 `python3 <script>.py` 运行。详细参数见各脚本 `--help`。

### launch_game.py
启动 Minecraft 游戏并附带后台常驻 log server。**启动前自动杀掉残留游戏/log_server 进程。**
```
python3 launch_game.py [--project DIR] [--config FILE] [--port PORT] [--log-output FILE] [--engine-dir DIR] [--wine-prefix DIR]
```
- `--project`：addon 项目根（含 `studio.json`；注意 studio.json 在 addon 上一级目录）。省略时按当前目录自动检测
- `--config`：直接指定 `.cppconfig` 路径，跳过自动生成
- `--port`：log server 监听端口（默认随机）
- `--log-output`：日志持久化路径（默认 `%TEMP%/pyreact-debug/pyreact_game_<port>.log`）
- `--engine-dir`：临时覆盖 `config.py` 中的 Linux 游戏目录
- `--wine-prefix`：Linux Wine 前缀；默认自动发现上级 `.wine-mcchina`

> AppReady 探测走三层回退：优先 HTTP `/logs`，HTTP 不可达时读 log server 写的 ready 标记文件（`<log-output>.ready`），再不行直接 grep 日志文件。log server 自身 stderr 写入 `<log-output>.diag`（捕获 HTTP 线程 bind 失败的 traceback）。超时只告警不阻塞，游戏照常启动。

### _mcs.py
读取 `studio.json` 并生成 `.cppconfig`，供 launch_game 使用。Windows 从注册表发现 MC Studio，Linux 从脚本目录的 `config.py` 读取游戏目录并自动发现 Wine 前缀；动态扫描 `behavior_pack*` / `resource_pack*` 目录并挂载到游戏数据目录。
```
python3 _mcs.py [project_root]
```

### get_ui_tree.py
通过剪贴板请求游戏 dump UI 树，保存 JSON 并打印树形视图。
```
python3 get_ui_tree.py [--node-id NODE_ID] [--output FILE] [--timeout N] [--quiet] [--json]
```
- `--node-id`：dump 子树（`dump_subtree`），省略则 dump 整树（`dump_tree`）
- 默认保存到 `%TEMP%/pyreact-debug/ui_tree.json`

### navigator.py
检查并控制游戏内全局 navigator。命令只操作已有页面；CLI 无法构造游戏进程中的 Python `Element`，因此不提供 `push`、`replace` 或 `reset`。
```
python3 navigator.py status [--timeout N]
python3 navigator.py pop [--count N] [--timeout N]
python3 navigator.py pop-to ENTRY_KEY [--timeout N]
python3 navigator.py pop-to-top [--timeout N]
python3 navigator.py clear [--timeout N]
python3 navigator.py close [--timeout N]
```
- `status` 输出 `depth`、`top_key`、`top_ui_name`、槽位数量、事务阶段和所有 `NavigationEntry` 的 JSON 快照。
- `pop` 的 `count` 按 `PopScreenAfterClientEvent` 确认的真实出栈次数计数；原版 UI 自行关闭、业务 native pop 和 navigator pop 完全等价。
- `pop-to` / `pop-to-top` / `clear` / `close` 只负责提交异步跨帧事务；返回的 `accepted=true` 表示命令已接受，可在仍有活跃 Pyreact host 时再次运行 `status` 查看进度。
- `close` 成功回到纯游戏画面后没有活跃 Pyreact host，后续 `status` 超时是预期行为。

### capture_screen.py
自动查找 Minecraft 的最大可见顶层窗口，在后台截取客户区并输出 PNG。stdout 是一行 JSON，包含绝对路径、尺寸、屏幕区域、捕获后端和窗口元数据。
```
python3 capture_screen.py [--output FILE] [--pid PID] [--title TEXT] [--include-frame]
python3 capture_screen.py --region X,Y,WIDTH,HEIGHT [--output FILE]
python3 capture_screen.py --list-windows
```
- 默认输出到 `%TEMP%/pyreact-debug/screenshots/minecraft_YYYYMMDD_HHMMSS.png`。
- 自动匹配失败时，先用 `--list-windows` 查看候选，再传 `launch_game.py` 输出的 `--pid` 或窗口标题子串 `--title`。
- `--include-frame` 在 Windows 同时截取标题栏和边框；Linux/X11 只支持客户区。
- 目标窗口必须处于非最小化状态；脚本不会恢复、激活或前置窗口。
- `--region` 绕过窗口查找，按虚拟桌面坐标截取指定区域。该模式是桌面截图，输出 `background=false`，可能包含遮挡和无关内容，只应在窗口匹配确实失败时使用。
- Linux 需要 `DISPLAY`、`libX11` 和 `libXcomposite`。XWayland 可用；纯 Wayland 会明确报错，因为未授权的后台窗口像素读取被协议禁止。
- 脚本成功后，多模态 Agent 必须把 JSON 中的 `path` 交给本地图片读取工具实际查看，并确认 `background=true`、核对 `backend`。若画面全黑，先确认游戏未最小化且没有独占全屏，再重试窗口化模式。

### resize_window.py
自动查找 Minecraft 窗口并精确调整**客户区**尺寸。脚本会按 DPI 和窗口样式换算外框尺寸、居中到当前显示器，并在 resize 后核对实际客户区。
```
python3 resize_window.py --preset 20:9
python3 resize_window.py --preset 4:3
python3 resize_window.py --preset 16:10
python3 resize_window.py --preset 16:9
python3 resize_window.py --preset 16:9 --height 900
python3 resize_window.py --size 1366x768
python3 resize_window.py --list-presets
```
- 推荐档位默认尺寸为 `2400x1080`、`1440x1080`、`1728x1080`、`1920x1080`；`--height` 会按所选宽高比重新计算宽度。
- `--size WIDTHxHEIGHT` 用于自定义客户区尺寸；不要把标题栏和边框算入尺寸。
- 支持 `--pid`、`--title`、`--process-name`、`--no-center`、`--no-activate`、`--settle` 和 `--list-windows`。
- stdout 是一行 JSON。只有 `ok=true` 且 `actualClient` 与 `requestedClient` 一致时，才视为 resize 成功；不一致时退出码为 2。
- 请求尺寸已经匹配时返回 `changed=false`，不改变最大化状态；尺寸不同时会先退出最大化再 resize，并通过 `wasMaximized` 报告原状态。

### simulate.py
模拟按钮点击、Input 输入、Slider 数值变化或 ScrollView 滚动。点击目标支持 `--node-id` / `--key` / `--label`；Input、Slider 使用 `--node-id` 和 `--value`；ScrollView 使用 `--node-id`，传 `--position` 设置像素位置，不传则读取当前位置。
```
python3 simulate.py click (--node-id ID | --key PREFIX | --label TEXT) [--timeout N] [--settle S]
python3 simulate.py input --node-id ID --value TEXT [--timeout N] [--settle S]
python3 simulate.py slider --node-id ID --value NUMBER [--timeout N] [--settle S]
python3 simulate.py scroll --node-id ID [--position PIXELS] [--timeout N]
```
- `--key PREFIX`：dump 树→按节点顶层 `key` 前缀查找→点击。Composite 的 key 会解析到其内部 Button；0 或多个匹配会报错，不会猜测目标。兼容旧快照中的 `props.key`；旧游戏端未输出 key 时请改用 `--label`。
- `--label TEXT`：找子树 conten 包含 TEXT 的 Label，定位其可点击节点（Button 或带 onClick）点击。对 FilledButton 等复合组件（文本 Label 与内层 Button 是兄弟关系）也能正确定位
- `input`：游戏侧调用目标 Input 的 `SetEditText`，再走正式的 `onChange` 文本 diff 分发；受控 Input 会在下一帧把新 `value` 写回 UI 树。
- `slider`：游戏侧更新目标 Slider 的 `#slider_value` property bag 并调用 `SetSliderValue`，再走正式的 `onChange` 数值 diff 分发；原生会按 `steps` 对数值取整或裁剪，受控 Slider 会在下一帧把新 `value` 写回 UI 树。
- `scroll`：游戏侧确认目标是 ScrollView，调用 `SetScrollViewPos` 设置像素位置，并在响应中返回 `before` / `position`；省略 `--position` 时通过 `GetScrollViewPos` 只读当前位置。
- `--settle S`：交互后等 S 秒让 UI 重渲染再返回（配合后续 dump）。**默认 `0.0`**；如需配合后续 `get_ui_tree` 抓稳定态，请显式传 `--settle 1` 等。

### print_ui_tree.py
打印保存的 UI 树 JSON 为 ASCII 树形视图（含 type / props 摘要 / layout / opacity / clickable 标记）。
```
python3 print_ui_tree.py [FILE] [--node-id NODE_ID] [--depth N] [--json]
```

### diff_ui_tree.py
对比两个 UI 树快照，报告 `added` / `removed` / `changed` 节点。
```
python3 diff_ui_tree.py <before.json> <after.json> [--props] [--layout] [--summary]
```
- `--summary`：只输出一行计数（`+N added | -N removed | ~N changed | N props | N layout`），不打印 JSON diff
- `--props` / `--layout`：仅比对 pyreact 层快照（`node.props` / `node.layout`），不覆盖 native 运行时已应用但未回写快照的状态（如背景色）。若视觉有变化但 diff 的 `changed` 为空，需配合 `get_ui_tree` 核对 native 控件实际值

### simulate_and_diff.py
一步完成：dump(before) → click/input → settle → dump(after) → diff。
```
python3 simulate_and_diff.py click (--node-id ID | --key PREFIX | --label TEXT) [--timeout N] [--settle N] [--props] [--layout] [--summary] [--timing]
python3 simulate_and_diff.py input --node-id ID --value TEXT [--timeout N] [--settle N] [--props] [--layout] [--summary] [--timing]
python3 simulate_and_diff.py slider --node-id ID --value NUMBER [--timeout N] [--settle N] [--props] [--layout] [--summary] [--timing]
```
- `--settle`：点击后等待 UI 稳定的秒数（默认 0.5）
- `--summary`：精简输出。stdout JSON 用 `added_count`/`removed_count`（整数）替代完整的 added/removed 路径列表，仅保留 `changed` 详情。重渲染密集的点击（如切换分类刷新整列商品）默认输出可达数百行，加 `--summary` 可压到约 10 行且仍可 JSON 解析
- `--label`：先用本次 before 树解析目标，再派发交互；适合筛选、列表增删导致原生 id 变化的界面。Input 和 Slider 只接受 `--node-id`，可先用 `query_tree.py --inputs` / `--sliders` 发现当前 id。
- `--timing`：在 JSON 的 `timing_ms` 和 stderr 中输出 before dump、action、settle、after dump、diff、total 分段耗时。
- 流分离：**stdout 输出可解析 JSON（diff 结果），stderr 输出进度与汇总计数行**（`[simulate_and_diff] +N added, -N removed, ~N changed`）。需要程序化取计数时直接解析 stdout JSON；若只要人读汇总，重定向 stdout 到 `/dev/null` 仅看 stderr
- `--props` / `--layout`：仅比对 pyreact 层快照（`node.props` / `node.layout`），**不覆盖 native 运行时已应用的状态**（如经 `SetColor` 应用但未回写 props 快照的背景色）。若点击后 diff 的 `changed` 为空但实际视觉有变化，可能是此原因，需配合 `get_ui_tree` 核对 native 控件实际值
- `--output-before FILE` / `--output-after FILE`：把 before/after 快照**额外**写到指定文件。每次 `simulate_and_diff` 都会用 after 覆盖共享 `%TEMP%/pyreact-debug/ui_tree.json`，连续点击或回归对比时**强烈建议**显式指定，否则基线会被刷新到最新态导致后续 diff 失真（已踩坑案例：连续点击测1后、立刻对比测2，用 `ui_tree.json` 做 before 基线其实已被测1的 after 覆盖过）
- **diff=0 诊断提示**：当点击成功派发（ack 收到）但 UI 树完全无变化（无 structural / props / layout 任何变化）时，stderr 会多打印一行：`Note: click dispatched to <id> but UI tree is fully unchanged. onClick may be a no-op or absent - use query_tree.py --clickable to inspect handlers.`，便于不必读源码即可区分"onClick 是 no-op / 缺失"和"变化被 --props/--layout 过滤掉"

### click_tour.py
批量点击巡检：按顺序点击一组节点，逐个输出紧凑 diff 块（只含 `changed` 详情），末尾汇总。适合回归巡检（如依次点击 8 个分类按钮）。
```
python3 click_tour.py (--nodes a,b,c | --labels 文本1,文本2) --settle 1 [--props] [--layout] [--timing] [--timeout N]
```
- 复用 `simulate_and_diff` 的 dump→click→settle→dump→diff 流程（直接 import `_protocol.request` / `diff_ui_tree._flatten`/`_node_summary`，不子进程调用）
- 相邻节点间自动 `sleep(0.2)` 让上一次点击状态稳定再做下一次 before-dump
- `--labels`：每一项在自己的 before 树上重新解析可点击 Label，避免批量巡检复用失效 native id；重复文本会报告歧义并跳过该项。
- `--timing`：每项输出分阶段耗时，便于直接汇总交互性能。
- 每个节点 STDOUT 块：`===== NODE id =====` / `+N added, -N removed, ~N changed` / 各 `changed` 条目（`path`/`before`/`after`）
- 节点点击/dump 超时不中断，标 error 继续下一个；末行 STDERR：`[click_tour] done: N nodes, M with changes, K errors`

### query_tree.py
程序化查询已保存的 UI 树 JSON，避免 `python3 -c` 内联解析在 Windows GBK 下崩（中文内容 `UnicodeDecodeError: 'gbk'`）。始终用 `open(..., encoding="utf-8")` 读，所有输出走 `sys.stdout.buffer.write(...encode("utf-8"))`。
```
python3 query_tree.py (--prop KEY | --count-children | --children | --descendant-count | --find-key PREFIX | --find-type TYPE | --clickable | --inputs) [--file FILE] [--node-id ID]
python3 query_tree.py --sliders [--file FILE] [--node-id ID]
```
- 9 种互斥查询模式，`--file`/`--node-id` 可选（省略 `--node-id` 操作根节点）
- `--prop KEY`：取节点 `props[KEY]`（如 `--prop content` 取 Label 文本）
- `--count-children` / `--children`：直接子节点数 / 列出 `id (type)`
- `--descendant-count`：所有嵌套后代总数（不含自身）
- `--find-key PREFIX` / `--find-type TYPE`：子树内按 `key` 前缀 / `type` 精确筛节点 id
- `--clickable`：列出所有可点击节点（Button 或带 onClick），每行 `id | type | key=.. | content/src/identifier=.. | onClick=handler/none`；当 Button 自身没有文本 props 时，会显示最多 5 个唯一后代 Label 的 `labels=...`，便于定位 FilledButton 和好友行等复合组件。
- `--inputs`：列出所有 Input 的 id、受控 `value` 和 `onChange` 标记，便于取得 `simulate.py input` 的目标 id。
- `--sliders`：列出所有 Slider 的 id、受控 `value`、`steps` 和 `onChange` 标记，便于取得 `simulate.py slider` 的目标 id。
- 默认输入文件同 `print_ui_tree`：`<tempdir>/pyreact-debug/ui_tree.json`

### expect.py
对已保存的 UI 树做声明式断言，exit 0=PASS / 1=FAIL，便于脚本/测试编排。
```
python3 expect.py [--file FILE] (exists --node-id ID | count --type TYPE (--eq|--gte|--lte) N | prop --node-id ID --key KEY --eq VALUE)
```
- `exists`：节点 id 存在即 PASS
- `count --type T --eq N`：类型 T 节点数等于 N（亦可 `--gte`/`--lte`）
- `prop --node-id ID --key K --eq V`：节点的 props[K] 值等于 V（字符串比较）
- 默认读共享 `ui_tree.json`。典型组合：`simulate_and_diff click --node-id X`（刷新共享树）→ `expect.py prop --node-id Y --key content --eq 期望`

### get_logs.py
从 log server 获取游戏日志。HTTP 优先，HTTP 不可达时自动回退读 log server 写的日志文件。
```
python3 get_logs.py (--port PORT | --from-file FILE) [--tail N] [--head N] [--lines START[-END]] [--since LINENUM] [--grep PATTERN] [--ignore-case] [--follow]
```
- `--from-file FILE`：直接读该日志文件，跳过 HTTP（`--port` 与 `--from-file` 至少一个）
- `--port PORT`：先 HTTP；HTTP 失败自动定位 `%TEMP%/pyreact-debug/pyreact_game_<port>.log` 回退读文件（stderr 提示）
- `--grep PATTERN`：按正则过滤日志行
- `--tail N` / `--head N`：取末尾 / 开头 N 行
- `--lines START[-END]`：按行号区间切片，如 `--lines 30-50`
- `--since LINENUM`：取行号 > LINENUM 之后的行（增量查看测试过程中产生的新日志）
- `--ignore-case`：`--grep` 忽略大小写
- `--follow`：持续流式输出新日志，HTTP 与文件模式都支持（Ctrl+C 退出）

### tracy.py
基于上游 [lovelyXiaoQi/mcdk-mcp-tracy](https://github.com/lovelyXiaoQi/mcdk-mcp-tracy) 的 native Tracy CLI 工作流。它通过 TCP 8086 抓取函数级 zone，用 CSV export 归约为 `self_ms` / `total_ms` / `calls`，并把精简 capture 保存到临时目录供 query/diff 使用。
```
python3 tracy.py setup
python3 tracy.py status [--port 8086]
python3 tracy.py capture --seconds 10 --contains Pyreact --label before
python3 tracy.py list
python3 tracy.py query CAPTURE_ID --contains Pyreact --metric self --limit 50
python3 tracy.py diff BASE_ID NEW_ID --metric self --contains Pyreact
python3 tracy.py self-test
```
- `setup`：下载固定版本的两个 Tracy CLI 并校验 SHA-256；可用 `--bin-dir DIR` 或 `TRACY_BIN_DIR` 改变安装位置。
- `status`：同时检查 Tracy TCP 可达性和 CLI 文件完整性。采样前必须确认 `ok=true`。
- `capture`：`--seconds` 范围为 `(0, 60]`；`--contains` 只影响 inline 输出，capture 文件保留全部函数；`--top` 控制输出行数。
- `list`：列出最近最多 20 个持久化 capture。默认目录为 `%TEMP%/pyreact-debug/tracy-captures`。
- `query`：按 capture id 查询热点，`--metric self|total` 选择排序指标。
- `diff`：比较两个 capture，`delta_ms < 0` 表示变快；`summary.pct` 是总耗时变化百分比，`improved/regressed` 是函数级结果。
- `self-test`：不启动游戏即可验证 CSV 归约、排行和 diff 逻辑。

标准流程：
1. `python3 tracy.py setup`（只需首次执行）。
2. 启动游戏后运行 `python3 tracy.py status`。
3. 先约定采样时长和场景；用户在游戏中准备好后执行 `capture --label before`。
4. 查看 `top`，结合源码给出热点报告；未经用户确认不要直接改热点代码。
5. 同场景、同时长再次执行 `capture --label after`，再运行 `diff BEFORE_ID AFTER_ID`。

热点报告必须包含：
- top 5~10：函数名、`self_ms`、`total_ms`、`calls`、`per_frame_ms`、`per_call_ms`。
- 先区分“调用次数过多”和“单次太贵”，再结合对应源码说明根因。
- 优化方案按性价比排序，逐条写预期收益、风险和改动量；用户确认选项后再修改代码。
- 前后 diff 必须使用相同场景和相同时长；`delta_ms < 0` 才代表优化生效。

输出中的 top 行同时包含总耗时与均摊数据：
```
{"name": "onRenderTick @ Main.py", "self_ms": 134.2, "total_ms": 328.1,
 "calls": 2628, "per_call_ms": 0.0511, "per_frame_ms": 0.0510}
```

### kill_game.py
杀掉游戏 + log server 进程，**始终等待并验证游戏已退出**，残留则二次 force-kill。兼容 Windows 进程名和 Wine/Linux 截断后的进程名，并按命令行识别运行 `log_server.py` 的 Python，与端口无关。
```
python3 kill_game.py [--wait]
```
- `--wait`：等待更久（10s，默认 4s）再确认；无论是否加 `--wait` 都会验证并在仍存活时升级强杀

## 新项目配置参考

- `studio.json`: `StudioPort=10492`, `NameSpace="ew"`, `Id="bfd5cdf648c44f1cbcfb89d41c57dfbe"`
- `work.mcscfg`: `Name="PyreactMC"`, UID 同 Id
- log server 端口由 `launch_game` 随机分配，HTTP API 在 `port+1`

## 典型工作流

1. **启动游戏**：`python3 launch_game.py`（记录输出的 game pid 和 log server port；AppReady 探测自动走 HTTP→ready-file→日志文件回退）
2. 确认 ClientSystem 首次初始化时已调用 `runtime_init(self, debug=True)`
3. **检查 Navigator / UI 树**：`python3 navigator.py status` 检查页面栈；`python3 get_ui_tree.py` 打印并保存当前 UI 树（共享到 `%TEMP%/pyreact-debug/ui_tree.json`）
4. **适配测试（按需）**：依次运行 `python3 resize_window.py --preset 20:9`、`python3 resize_window.py --preset 4:3`、`python3 resize_window.py --preset 16:10`、`python3 resize_window.py --preset 16:9`，每个档位确认 `actualClient` 后重新 dump UI 树并检查 layout/断言。
5. **发现交互节点**：`python3 query_tree.py --clickable` 列出按钮；`python3 query_tree.py --inputs` 列出 Input；`python3 query_tree.py --sliders` 列出 Slider 及其当前受控值和步数。
6. **模拟交互**：
   - `python3 simulate_and_diff.py click --node-id my_button`（原生 id）
   - `python3 simulate.py click --key category_3 --settle 1`（按 Fiber key，稳定）+ 再 `python3 get_ui_tree.py`
   - `python3 simulate.py click --label 方块 --settle 1`（按显示文本）
   - `python3 simulate.py input --node-id __pyr_2 --value 测试文本 --settle 1`
   - `python3 simulate.py slider --node-id __pyr_3 --value 4 --settle 1`（设置固定格或百分比 Slider，并触发正式 `onChange`）
   - `python3 simulate.py scroll --node-id __pyr_42 --position 180`（滚到指定像素）
   - `python3 simulate.py scroll --node-id __pyr_42`（读取当前滚动位置）
   - `python3 simulate_and_diff.py input --node-id __pyr_2 --value 测试文本 --settle 1 --props`
   - `python3 simulate_and_diff.py slider --node-id __pyr_3 --value 0.75 --settle 1 --props`
   - `python3 simulate_and_diff.py click --label 在线 --settle 1 --summary --timing`（避免使用可能失效的 native id）
   `simulate_and_diff` 点击后会**刷新共享 `ui_tree.json`**，后续 `expect.py` / `query_tree.py` 直接读最新态
   **连续点击或对比多阶段状态时**用 `--output-before`/`--output-after` 独立保存，避免上一轮的 after 已覆盖共享 `ui_tree.json` 导致下一轮 before 基线失真：
   ```
   python3 simulate_and_diff.py click --node-id btn_a --output-before ui_a_before.json --output-after ui_a_after.json
   python3 simulate_and_diff.py click --node-id btn_b --output-before ui_b_before.json --output-after ui_b_after.json
   python3 diff_ui_tree.py ui_a_after.json ui_b_before.json  # 跨点击对比
   ```
7. **断言验证**：`python3 expect.py prop --node-id title_label --key content --eq 方块`（exit 0 通过 / 1 失败）
8. **批量巡检（可选）**：`python3 click_tour.py --labels 全部,在线,游戏中 --settle 1 --timing`（或使用 `--nodes`）一次跑完点出每个节点的紧凑 diff 和耗时
9. **视觉检查（严格按需）**：仅当结构化工具实在定位不到、已长时间多轮迭代，或 breaking change 后需要视觉回归时，才执行 `capture_screen.py` 并实际读取图片。
10. **查日志**：`python3 get_logs.py --port <port>`（HTTP 不可达自动回退读日志文件）或 `python3 get_logs.py --from-file <path>`
11. **函数级性能采样（可选）**：先 `python3 tracy.py status`，再在真实负载期间运行 `python3 tracy.py capture --seconds 10 --contains Pyreact --label before`
12. **关闭**：`python3 kill_game.py`（始终验证清理，残留自动强杀）
