# 独立实例与并行调试

`instances.py` 解决“一个 agent 一个项目一个游戏”的路由问题。每次 `start` 都创建唯一实例 ID、MCP 端口、MCDK 工作目录、APPDATA、世界名和证据目录；启动后还会检查 MCDK 子进程、游戏 PID 的创建时间，以及客户端和服务端加载的 session probe。只有这些标记都匹配才返回 `ready`。

## 启动

```powershell
$a = python3 -X utf8 .agents/skills/pyreact-debugging/scripts/instances.py start `
  --project 'D:/AddonA' --owner agent-a | ConvertFrom-Json
$b = python3 -X utf8 .agents/skills/pyreact-debugging/scripts/instances.py start `
  --project 'C:/work/AddonB' --owner agent-b --preset ui | ConvertFrom-Json
```

两个项目可以同时运行。项目可以是副本或独立 worktree；同一目录的并发源码热更新会互相影响。启动器只读取源 `.mcdev.json`，为实例生成副本，并额外加入仅用于路由校验的 managed session probe Mod。

## 路由命令

```powershell
python3 .agents/skills/pyreact-debugging/scripts/instances.py list
python3 .agents/skills/pyreact-debugging/scripts/instances.py status --session $a.session_file --owner agent-a
python3 .agents/skills/pyreact-debugging/scripts/instances.py exec --session $a.session_file --owner agent-a -- mcdk.py exec check.py
python3 .agents/skills/pyreact-debugging/scripts/instances.py exec --session $b.session_file --owner agent-b -- mcdk.py exec check.py --server
```

`exec` 只允许 skill 脚本，并把 session、owner 和正确 MCP URL 注入子进程。脚本启动的 MCDK client 会再次验证游戏内标记；错误 owner、过期 PID、端口冲突或 marker 不匹配都会在业务调用前失败。不要把两个实例的 URL 交给同一个无绑定客户端。

## 输入、窗口和证据

不同实例的代码执行、日志、UI 树、截图和性能采样可以并行。真实鼠标、键盘、拖拽、窗口激活和 resize 需要前台桌面，因此受全局桌面锁和 lease 串行化；超时后 lease 会暂时保留，避免不确定的输入被重放。每个实例仍只操作自己绑定的游戏 PID。

实例停止后保留生成的 native 测试世界和 `artifacts` 证据，便于比较；使用 `stop --force` 前先读取 `status` 和本次启动日志。MCDK / 网易客户端的全局引擎日志、选项和原生缓存不承诺完全隔离，也不要把该方案当作安全边界。

MCDK 1.6 没有独立的 prepare-only 命令。启动器使用同版本的 MCDK 配置、短暂的 `where.exe` bootstrap 让 MCDK 完成世界和调试包准备，再以真实游戏启动；若升级 MCDK 后配置 schema 变化，应重新运行实例回归测试并检查 `prepare.log`。
