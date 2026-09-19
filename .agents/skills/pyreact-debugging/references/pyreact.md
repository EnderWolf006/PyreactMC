# Pyreact 检查与交互

首次初始化时开启：

```python
pyreact.runtime_init(self, debug=True)
```

初始化后重复调用不会改变 debug。框架仍兼容旧游戏侧剪贴板协议，但 skill 不再使用它；`_protocol.py` 通过 MCDK 客户端 `execute_code` 注入 Python 2 适配代码，调用已部署框架的序列化与交互函数。无需往 Mod 中复制额外桥接文件。上游 execute_code 对返回对象有 8 层深度限制，适配器先将完整响应编码为 JSON 字符串，再在宿主解码，避免深层 Fiber 丢失。

适配器发现已加载的 `pyreact.host` 或 `*.pyreact.host`。存在多个副本时不猜测，设置 `PYREACT_MODULE` 为完整包路径（例如 `YourClientScript.pyreact`）。这不是宿主文件路径。缺少活跃 root 时，打开业务 UI 后重试；`navigator status` 经 MCDK 可在页面关闭后继续查询，不再依赖活跃 Screen 的剪贴板轮询。

以下命令均位于 `.agents/skills/pyreact-debugging/scripts/`；从仓库根使用完整脚本相对路径，或先进入该目录。具体选项查 `--help`。

## 观察、查询与断言

```text
python3 get_ui_tree.py --output before.json
python3 get_ui_tree.py --node-id __pyr_42 --json
python3 query_tree.py --clickable --file before.json
python3 query_tree.py --inputs
python3 query_tree.py --sliders
python3 query_tree.py --find-key category_
python3 query_tree.py --find-type Label
python3 print_ui_tree.py before.json --depth 3
python3 diff_ui_tree.py before.json after.json --props --layout
python3 expect.py --file after.json exists --node-id __pyr_42
python3 expect.py --file after.json count --type Button --gte 1
python3 expect.py --file after.json prop --node-id title_label --key content --eq 方块
```

共享快照默认在 `<tempdir>/pyreact-debug/ui_tree.json`。`--file` 应明确指向要比较的时刻；连续回归不要把会被覆盖的共享文件当永久基线。断言退出码 0=PASS、1=FAIL。

快照描述 Fiber 的 type/key/props/style/layout/opacity；Component 是逻辑节点，不一定有 native layout。视觉快速路径可能只更新原生状态，未回写快照；这种情况用 `jsonui_debugger /node` 交叉检查。不要把 Pyreact 节点 id 直接当成原生 screen/path，先从原生 `/overview`、`/find` 定位。

## 语义交互

```text
python3 simulate.py click --key category_3 --settle 1
python3 simulate.py click --label 方块 --settle 1
python3 simulate.py input --node-id __pyr_2 --value 测试文本 --settle 1
python3 simulate.py slider --node-id __pyr_3 --value 4 --settle 1
python3 simulate.py scroll --node-id __pyr_42 --position 180
python3 simulate.py scroll --node-id __pyr_42
python3 simulate_and_diff.py click --label 在线 --settle 1 --summary --timing --output-before before.json --output-after after.json
python3 click_tour.py --labels 全部,在线,游戏中 --settle 1 --timing
```

`--key` 按 key 前缀找组件并解析内层 Button；`--label` 找文本关联按钮。零匹配或多匹配报错，不猜目标。Input / Slider 使用当前 dump 的 node id；列表重排或重载后重新获取。

Input / Slider 调用原有控件设置与 onChange 分发，受控值通常下一帧回写；Slider 可按 steps 量化或裁剪。ScrollView 用像素位置，省略 position 只读。回调成功并不证明真实鼠标能点击该控件。

`simulate.py --settle` 默认 0，`simulate_and_diff.py` 默认 0.5；等待后重新 dump 验证最终状态。后者 stdout 是 diff JSON、stderr 是诊断，after 会覆盖共享快照；用独立 before/after 文件保存基线。

## Navigator

```text
python3 navigator.py status
python3 navigator.py pop --count 1
python3 navigator.py pop-to ENTRY_KEY
python3 navigator.py pop-to-top
python3 navigator.py clear
python3 navigator.py close
```

`accepted=true` 仅表示跨帧事务被接受。再次查询 depth/top/transition 验证；close 后仍可通过 MCDK 查询空栈。命令不构造游戏内 Element；push/replace/reset 通过项目已有测试函数执行，不向 MCP 传 Python 对象。

## 尺寸适配（Windows 补充）

`resize_window.py` 使用独立 Win32 窗口辅助代码，只负责 MCDK 未提供的客户区尺寸调整。先 `--list-windows`，用游戏 PID（不是 mcdk_pid）选定窗口。

```text
python3 resize_window.py --pid GAME_PID --preset 20:9 --no-activate
python3 resize_window.py --pid GAME_PID --preset 4:3 --no-activate
python3 resize_window.py --pid GAME_PID --preset 16:10 --no-activate
python3 resize_window.py --pid GAME_PID --preset 16:9 --no-activate
```

默认高度 1080，对应 2400×1080、1440×1080、1728×1080、1920×1080；可用 `--height` 或 `--size 1366x768`。返回 `ok=true` 且 actualClient=requestedClient 才算生效。记录原尺寸并在测试后恢复，再用树/layout/断言检查适配；不必每个档位都截图。
