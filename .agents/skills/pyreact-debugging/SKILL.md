---
name: pyreact-debugging
description: 使用 MCDevTool（MCDK）调试网易我的世界 ModSDK 中的 Pyreact-MC 与相关 Mod / Addon。支持多 agent 多项目独立游戏实例、诊断包与自动回归，以及 Pyreact / 原生 JSON UI、客户端和服务端测试、日志、热重载、窗口适配和性能分析。
metadata:
  audience: agents
  domain: pyreact-debugging
  platform: netease-minecraft-bedrock-modsdk
---

# 基于 MCDevTool 的运行时调试

底层使用 [GitHub-Zero123/MCDevTool](https://github.com/GitHub-Zero123/MCDevTool)：MCDK 管理游戏、调试 Mod、IPC、日志和 MCP 服务。本 skill 的 Python 脚本只做 MCP 适配、Pyreact 语义操作与离线快照分析，不再自行生成 cppconfig、运行日志服务器或使用剪贴板通信。

适用范围从 Pyreact UI 扩展到同一开发世界中的 Mod / Addon 联调。纯 UI 编写仍使用 `pyreact-ui-building`；运行时诊断、测试与性能验证使用本 skill。

## 入口与能力选择

首次使用、未安装 MCDK 或没有 MCP 连接时，先阅读 [首次安装、启动与连接](references/setup.md)，执行 `setup_mcdk.py` 检查前置条件；缺 MCDK 时用 `--install` 安装官方固定版本。无需预先了解 MCDK、设置 PATH 或注册全局 MCP。不要在启动前直接向默认 19133 端口调用工具。

| 任务 | 入口 | 按需阅读 |
| --- | --- | --- |
| 从未配置环境安装、发现游戏、启动与连接 | `setup_mcdk.py`、`instances.py start` | [首次安装与启动](references/setup.md) |
| 多 agent / 多项目并行运行与路由 | `instances.py start/list/status/exec/stop` | [独立实例与并行调试](references/instances.md) |
| 一次收集诊断证据、带断言的 JSON 回归 | `diagnostics.py`、`run_case.py` | [诊断与回归编排](references/workflows.md) |
| Fiber、props、Style、布局、navigator、受控输入与回归断言 | Pyreact 专用脚本，经 `execute_code` 调用 | [Pyreact 检查与交互](references/pyreact.md) |
| 原版 / Mod JSON UI、可见性、原生布局、节点检索、HTML / SVG | `jsonui_debugger` | [原生 UI、输入与热重载](references/runtime.md) |
| 真实点击、拖拽、长按、滚轮、键盘、视角、文本、截图 | `mc_input`、`capture_game_window` | [原生 UI、输入与热重载](references/runtime.md) |
| 客户端 / 服务端测试函数、状态查询、结构化日志、代码与资源热更新 | `execute_code`、日志工具、`reload_game` | [原生 UI、输入与热重载](references/runtime.md) |
| Python CPU 热点 / 调用关系、内存增长 / 保留量、Native CPU 与基线比较 | `mc_profiler` | [性能分析](references/performance.md) |

优先使用环境已连接的、已绑定当前实例的 MCDK MCP 工具（名称可能带服务前缀）。多 agent 或多个项目并行时，必须通过 `instances.py exec` 传递 session 和 owner；不要让多个 agent 共享一个无绑定的 `MCDEV_MCP_URL`。

已有明确的非受管服务地址时，可用标准库 CLI；受管实例把以下命令包装为 `instances.py exec --session <file> --owner <agent> -- mcdk.py ...`：

```powershell
python3 .agents/skills/pyreact-debugging/scripts/mcdk.py tools
python3 .agents/skills/pyreact-debugging/scripts/mcdk.py call get_latest_logs
python3 .agents/skills/pyreact-debugging/scripts/mcdk.py call jsonui_debugger --args-file ui-query.json
```

`ui-query.json` 是 UTF-8 JSON 对象，例如 `{"cmd":"/overview --screen=top"}`。复杂参数写文件，避免 PowerShell 引号破坏 JSON。统一 CLI 支持上游全部工具，不把 `mc_input` 的 `op + args` 误写成 `cmd` 字符串。自定义服务地址设置 `MCDEV_MCP_URL`，默认 `http://127.0.0.1:19133/mcp`；不连接游戏内部私有 IPC 端口。

## 工作原则

1. 先明确待验证行为、项目与当前世界。检查实际 `tools/list`、所需工具 `/help` 和运行时能力；工具可枚举不等于玩家已入世界或游戏 IPC 已就绪。
2. 优先使用测试函数、返回值、树、日志和断言收集证据。循环测试使用 `run_id`、明确成功条件与耗时，避免仅凭“没有异常”判断成功。
3. 区分 Pyreact Fiber 状态、原生 UI 已应用状态和实际像素。框架树 diff 无变化不代表原生控件无变化；`/render` 是布局示意，不是游戏截图。
4. Pyreact `simulate.py` 调用组件回调 / 控件设置路径；真实命中区域、遮挡、焦点、拖拽和输入法使用 `mc_input` 验证。输入投递成功不等于业务成功，随后检查状态或日志。
5. 网络超时后先查询状态再决定是否重试。CLI 不自动重放工具调用，以免重复点击、出栈、执行代码或启动采样。
6. 视觉效果本身是目标、结构化证据不足或重大 UI 修改需要视觉回归时，使用 MCDK 截图并实际读取返回图片。不要在每步交互后机械截图。
7. 修改与测试按用户已授权的任务范围推进。真实世界重置、关闭其他会话等不由“调试”默认授权。普通诊断、回归和已授权修复无需额外审批流程。

## 能力边界

- MCDK 原生 JSON UI、日志、输入、截图和通用代码执行不要求 Pyreact；Fiber 快照与 Pyreact 回调需要加载对应框架，并在首次 `pyreact.runtime_init(self, debug=True)` 开启调试。
- 受管脚本要求宿主 CPython 3.12+、Windows x64 和 Windows PowerShell；`execute_code` 在游戏 Python 2 执行。不要把 Python 3 语法或本机模块直接发进游戏。
- 此迁移以 Windows 游戏调试为主要环境。上游平台支持以实际构建与 `/doctor` 为准，不沿用旧脚本对 Linux/Wine 的保证。Native CPU 仅为可选 Windows x64 能力。
- MCDK 当前无客户区 resize 工具，保留 `resize_window.py` 作为 Windows 补充；不是 MCDK 的跨平台能力。
- `instances.py` 为每个项目创建独立 MCDK 工作目录、APPDATA、端口、世界和证据目录，并用进程创建时间、游戏内 session probe 同时校验路由。它支持不同项目同时启动各自游戏；真实桌面输入仍由全局锁串行化。
- 实例隔离的是项目 / 世界 / MCP 端口 / Python 运行时环境 / 调试证据。网易客户端的引擎日志、选项、原生缓存和桌面焦点仍可能共享；需要并行修改源码时，为每个 agent 使用独立 worktree 或项目副本。
- 没有通用自动构造 Pyreact 页面 Element、无条件保留 UI 状态或完整 IDE 断点调试的 MCP 保证。通过已存在的业务入口打开页面，按实际重载结果重新定位节点。

接口依据核对于 2026-09-19，上游 commit `2a723d932a1c8cbb516cbbead1b0dd0007090c22`。安装版本的工具 schema 和 `/help` 优先于本文示例；不要把设计文档中尚未实现的能力当作工具。
