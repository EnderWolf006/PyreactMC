# 首次安装、启动与连接

MCDK 是外部程序，负责启动网易开发游戏、加载调试 Mod，并开放本机 MCP 服务。本 skill 的 Python 脚本通过 HTTP 调用它；不需要预先注册全局 MCP 或安装 VS Code 插件。

## 1. 检查前置条件

- Windows x64、Windows PowerShell 和宿主 Python **3.12+**。执行 `python3 --version`；不存在时检查 `python --version` 或 `py -3 --version`，下文统一换成可用解释器。游戏内代码仍是 Python 2。
- 已通过网易 MC Studio 下载目标版本的开发游戏。MCDK 不提供游戏本体，也不代替 MC Studio 的安装、登录或版本下载。
- 用户要调试的真实 Addon / 地图项目。本框架仓库不是已部署的 Addon。先确认行为包 / 资源包的 `manifest.json` 与脚本入口；地图项目应有 `level.dat`。项目未知或多个候选无法确定时，先询问项目位置。

下文从仓库根目录运行，`$project` 替换为已确认的项目绝对路径。

```powershell
$scripts = (Resolve-Path '.agents/skills/pyreact-debugging/scripts').Path
$project = 'D:/MyAddon'
python3 "$scripts/setup_mcdk.py" --project $project
```

命令只检查，不下载、不启动游戏、不写项目配置。JSON 返回 `mcdk`、`game_candidates`、`game_exe` 和 `issues`；退出码 1 表示有前置问题，逐项处理。

## 2. 没有 MCDK 时安装

```powershell
python3 "$scripts/setup_mcdk.py" --install --project $project
```

从 [MCDevTool v1.6.1 官方发行版](https://github.com/GitHub-Zero123/MCDevTool/releases/tag/v1.6.1)
下载 `mcdk.exe`，校验固定 SHA-256 后保存到 `%USERPROFILE%/.pyreact-debug/tools/mcdk/v1.6.1/`。
该版本已验证受管世界准备流程；升级时需同步校验值并检查上游兼容性。安装阶段不执行 MCDK，不启动游戏。
部分官方构建未启用 `MCDK_ENABLE_CLI`，会把 `--help` / `envinfo` 当作普通启动，不能用这些命令做无副作用的安装检查。实际可用性由受管启动的就绪校验确认。

不更改系统 PATH、注册表或全局 MCP 配置。重复安装复用校验通过的文件；现有文件校验不匹配时报错，不覆盖。下载或校验失败时报告具体错误，不跳过校验或反复启动游戏。

基础调试只需 `mcdk.exe`。Native CPU 分析额外加 `--native`；IDE stdio 接入额外加 `--stdio`，均与 `--install` 一起使用。已有安装可传 `--mcdk 'D:/Tools/MCDevTool/mcdk.exe'`；离线机器需先取得官方发行文件，再用该参数指定。

启动器查找顺序：`--mcdk` → `MCDK_EXE` → 受管安装 → PATH。显式路径无效会报错，不换用其他版本。

## 3. 定位开发游戏与项目配置

按 `--game-exe` → 项目 `.mcdev.json` 的 `game_executable_path` → 固定磁盘的
`MCStudioDownload/game/MinecraftPE_Netease/*/Minecraft.Windows.exe` 定位游戏。
只有一个自动发现结果时采用；多个版本时按项目要求传 `--game-exe`，不按最大版本号猜测。
自定义安装目录也用 `--game-exe`。没有游戏则回到 MC Studio 下载，不能靠重新安装 MCDK 解决。

项目可以没有 `.mcdev.json`：默认挂载项目目录，只在实例目录生成配置。已有配置按 UTF-8 JSON 对象读取，不支持 JSONC 注释，原文件不改写。`included_mod_dirs` 可指定额外包目录，路径相对项目解析。例如：

```json
{
  "included_mod_dirs": ["./"],
  "auto_hot_reload_mods": true,
  "auto_hot_reload_ui": true
}
```

地图根有 `level.dat` 时自动使用地图；地图在子目录时设置 `world_source_path`。
启动器覆盖独立世界名、随机 MCP 端口、调试 Mod、自动入世界和 `reset_world=false`，关闭可能冲突的 IDE 调试器端口。

## 4. 启动并保存路由

```powershell
$owner = 'agent-a'
$raw = python3 "$scripts/instances.py" start --project $project --owner $owner --wait 90
if ($LASTEXITCODE -ne 0) { throw ($raw -join "`n") }
$instance = ($raw -join "`n") | ConvertFrom-Json
if ($instance.state -ne 'ready') { throw 'Game IPC is not ready' }
```

若检查要求选择路径，在 `start` 命令追加 `--mcdk <exe>` 或 `--game-exe <exe>`。
`launch_game.py --project ... --owner ...` 是兼容入口。`--preset ui` 为新生成世界提供固定种子、超平坦、创造模式及关闭昼夜 / 天气的环境。

启动先准备独立世界，再等待端口、游戏进程身份、客户端与服务端 session probe 匹配。
`--wait` 限制准备后的就绪等待，各准备/探针另有有限超时。失败返回实例信息和错误，读取 `prepare.log` / `mcdk.log`，不循环创建实例。游戏最小化或暂停可能延迟初始化，应检查本实例窗口，不激活其他 agent 的游戏。

## 5. 确认目标项目可调试

所有后续命令使用返回的 `session_file`，不要直接访问默认 19133 端口：

```powershell
python3 "$scripts/instances.py" exec --session $instance.session_file --owner $owner -- mcdk.py tools
python3 "$scripts/instances.py" exec --session $instance.session_file --owner $owner -- diagnostics.py
python3 "$scripts/instances.py" exec --session $instance.session_file --owner $owner -- mcdk.py exec "$project/client_check.py"
python3 "$scripts/instances.py" exec --session $instance.session_file --owner $owner -- mcdk.py exec "$project/server_check.py" --server
```

`client_check.py` / `server_check.py` 是示意名称，先找项目已有检查入口；没有时根据实际模块编写只读探针，通过 `_result` 返回业务系统或状态的 JSON 值。不要导入猜测的模块名。`ready` 只证明基础通道与世界身份就绪，不证明目标业务已正确初始化；还要读取诊断包日志和业务探针返回值。

Pyreact 项目需确认首次 `runtime_init(self, debug=True)`、通过已有业务入口打开页面，再运行：

```powershell
python3 "$scripts/instances.py" exec --session $instance.session_file --owner $owner -- get_ui_tree.py --quiet
```

缺少开关或页面时不能取得 Fiber 树，但日志、原生 UI 和通用代码执行仍可用。
停止本次实例用 `instances.py stop --session $instance.session_file --owner $owner`；无法正常退出时检查身份与日志后用 `--force`。世界和证据保留。

## 可选 MCP 接入与旧入口

IDE 持久接入可用 `mcdk_stdio_bridge.exe --host 127.0.0.1 --port <实例端口>`。
静态工具列表不代表游戏就绪；多 agent 仍用受管 `exec` 路由，真实桌面操作依赖该包装层协调。
本 skill CLI 使用 Streamable HTTP `/mcp`，不接受 `/sse`。

旧剪贴板、`_mcs.py`、日志服务器、`kill_game.py` 与 `tracy.py` 已移除，分别由 MCDK 代码执行、实例管理、日志工具和 `mc_profiler` 替代。旧 `--config`、`--engine-dir`、`--wine-prefix` 与日志端口参数不再适用。
