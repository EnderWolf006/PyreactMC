# 原生 UI、输入与热重载

下面使用 MCP 工具名与参数 JSON，均可直接调用连接的工具，或将参数保存为 UTF-8 JSON，用 `mcdk.py call TOOL --args-file FILE`。先查询当前安装的 schema 和 `/help`。

## 原生 JSON UI

`jsonui_debugger` 接收 `{"cmd":"..."}`：

```text
/help
/screens
/overview --screen=top
/tree <screen> <path> --depth=2 --max-nodes=80
/node <screen> <path> --fields=basic,layout,text,container
/children <screen> <path> --limit=30
/find <screen> <path> reset --match=name --type=Button --limit=5
/html <screen> <path> --depth=2 --html-only
/render <screen> <path> --depth=2 --out=D:/debug/layout.svg
/mod-ui --include-registered --children-depth=1
```

先 `/screens` / `/overview` 找到真实 screen 与建议根路径，再缩小查询范围。用 bounded depth/max-nodes；出现 truncated 时缩小子树，不把截断误判为节点消失。默认 find 匹配节点名，按路径匹配需显式指定。`--nud` 及原版网易调试器相关探测先读 `/help`，按需使用。

`/html`、`/render` 由运行时矩形派生，不还原 JsonUI 源码、贴图或真实渲染。SVG 用绝对 `.svg` 路径导出，不把 SVG 当作 MCP 位图图片块。避免在未知大根节点上无限递归、全量枚举属性包；先 probe/children，保留上游的探测边界。

## 真实输入与截图

先调用 `mc_input`：`{"op":"/help"}`、`{"op":"/state"}`。单入口使用 `op` 与 `args`，例如：

```json
{
  "op": "/run",
  "args": {
    "steps": [
      {"do":"click", "at":[0.5,0.42]},
      {"do":"wait", "ms":200},
      {"do":"text", "value":"测试文本"},
      {"do":"key", "keys":"enter"}
    ],
    "logs":"end",
    "logs_max_count":20
  }
}
```

坐标默认是客户区归一化 0..1，不能直接发送截图像素或 JSON UI 逻辑坐标。支持 click/drag/move/scroll/look/key/text/wait；指针被游戏独占时，相对转视角使用 look。按 `/help` 获取详细步骤参数。单批默认预算 30 秒、最多 64 步；`dry_run` 可先校验。需要跨调用保持按键时才用 leave_held，结束使用 `/release-all`。

工具可能前置窗口和暂时处理 IME，失焦会中止。遇到 FOCUS_LOST、POINTER_MODE_MISMATCH 等错误，读 error/progress/next_calls 并验证当前状态，不重复整批动作。返回的最近日志可能含历史记录，用 run_id 关联。

视觉确认用 `capture_game_window {}`，或：

```text
python3 mcdk.py capture --output D:/debug/game.jpg
```

上游输出 480p JPEG；CLI 解码到本地文件，不把 base64 长串灌进上下文。用本地图片读取工具实际查看，再判断遮挡、贴图、文字与颜色。无图像读取能力时只能提供文件，不声称看过画面。`mc_input` 的 `capture:"end"` 可按需附上输入后截图。

多实例必须通过绑定的 `instances.py exec` 调用。CLI 的真实输入默认预算为 5 秒，允许 1..30000 毫秒，HTTP timeout 至少多 5 秒；不支持 `leave_held=true` 或 `focus:keep`。输入与 `resize_window.py` 共享桌面锁，绑定窗口只能来自本实例 PID。直接调用原生 MCP 会绕过本 skill 的桌面协调，不用于并发真实输入。

## 代码、日志与测试

`execute_code` 参数：`{"code":"...","is_client":true,"direct_return":true}`。服务端设 `is_client:false`。表达式可直接返回，语句将结果赋给 `_result`；复杂对象超过 8 层时会被上游摘要化，可在游戏内 `json.dumps` 后返回字符串并在宿主解码。复杂代码写为 Python 2 兼容的 UTF-8 文件：

```text
python3 mcdk.py exec client_check.py
python3 mcdk.py exec server_check.py --server
```

优先调用项目已有测试入口；需要重复覆盖时再补充可复用入口。结果返回 JSON 安全的计数、断言、耗时和 run_id；异步业务先启动再查询状态，不在游戏线程阻塞等待。示例模式（模块/函数替换为源码中确认存在的入口）：

```python
from YourClientScript import dev_tests
_result = dev_tests.run_case('inventory_filter', run_id='filter-001')
```

日志工具：

| 工具 | 参数和语义 |
| --- | --- |
| `get_latest_logs` | `max_count`、`order:"asc"`，完整日志 |
| `get_latest_error_logs` | 同上，只含 stderr，不保证覆盖 JSON 解析等全部错误 |
| `get_log_range` | `start_index` 包含、`end_index` 不含；0 是最新条目，按最新条目相对索引 |

日志索引不是旧脚本的全局递增行号，新增日志会移动相对范围；重载会清空缓冲区。需要统计多轮成功率、耗时、异常分布时及时保存结果并按 run_id 去重，不能照搬旧 `--since` 游标。

## 热重载

先根据变更类型选择最小有效刷新：

- Python：`.mcdev.json` 的 `auto_hot_reload_mods` 与 `included_mod_dirs` 每目录 `hot_reload` 控制。回到游戏前台触发变更检测；确认加载的是实际部署目录。
- JSON UI：`auto_hot_reload_ui`（默认关闭），资源包 `ui/*.json` 变化后回到前台触发；或 `jsonui_debugger {"cmd":"/reload-ui --preserve-mod-ui"}`。保留 Mod UI 是尽力恢复，不保证业务状态不变。
- Shader / Material / Particle：按需开启 `auto_hot_reload_shaders`、`auto_hot_reload_materials`、`auto_hot_reload_particles`，由上游处理资源包对应目录的单文件变更；支持范围以运行版本为准。
- 其他资源或增量刷新不足：`reload_game {"reload_addons":true}` 触发 addon 数据与游戏刷新；`false` 为完整游戏重载路径。

重载后重新确认世界就绪、页面挂载、节点 ID 和日志结果。跨初始化状态或框架基础结构变更可能需要重启，不能承诺任意 Python 变更都可热更新。
