# 性能分析

使用 MCDevTool `mc_profiler` 单工具，输入是 `{"op":"/...","args":{...}}`，不是旧 `tracy.py` 命令。先调用 `/help`、`/doctor`；详细主题例如 `{"op":"/help","args":{"topic":"/start"}}`。

## 类型与前置条件

| kind | 能力 | 边界 |
| --- | --- | --- |
| `python.cpu` | 自耗时、总耗时、热点、调用关系 | target=client/server/all；clock=cpu/wall，比较时保持一致 |
| `python.memory` | 增长、保留量、结构化调用栈 | 客户端控制侧；不当作服务端或 C++ 堆快照 |
| `native.cpu` | Tracy zone、调用树、线程和最慢调用 | 可选 Windows x64 DLL 与兼容协议；只能看到实际埋点 |

Native 模式需要 `mcdev-tracy-bridge.dll` 与 `mcdk.exe` 同目录。`/doctor {"kind":"native.cpu","deep":true}` 才做有界端点发现；不要假设固定 8086 端口可用。Tracy 端点只能由一个 profiler 占用，避免与 VS Code 插件或 Tracy GUI 争抢。缺失 DLL / 不兼容 / busy 时报告能力不可用，不回退下载旧 CLI。

## 有界采样与比较

```json
{"op":"/start","args":{"kind":"python.cpu","target":"client","clock":"wall","duration_seconds":15,"storage":"disk"}}
```

`duration_seconds` 为整数 1..300。读取返回的 `job.id` 和 `next_calls`，用 `/status` 查询同一 job；达到终态后 `/query`，不要把重复 `/start` 当轮询：

```json
{"op":"/status","args":{"job_id":"ACTUAL_JOB_ID"}}
{"op":"/query","args":{"job_id":"ACTUAL_JOB_ID","view":"hotspots","limit":20}}
{"op":"/export","args":{"job_id":"ACTUAL_JOB_ID","format":"markdown"}}
```

query view 按 kind 和 `/help` 选择：CPU 热点 / 调用树，memory growth / retained，Native threads / slowest-calls 等；先限量查询，再按记录 ID 深入。实际字段、分页和排序以当前帮助为准。

Python memory 可按需设置 traceback_depth（1..16）和 collect_garbage，记录是否主动 GC，避免把不同条件下的增长直接比较。Python CPU 的 CPU clock 和 wall clock 含义不同；报告中注明采样口径。

前后对比使用同一场景、负载、时长、kind、target 和 clock：

```json
{"op":"/compare","args":{"baseline_job_id":"BEFORE_ID","candidate_job_id":"AFTER_ID","view":"hotspots","limit":20}}
```

结果按稳定来源身份对齐，关注新增 / 删除项和候选减基线的差值；不要仅凭总耗时降低断言优化成功，先排除调用量或场景变化。区分“次数太多”和“单次太贵”，结合源码给出收益与改动依据。用户已要求优化时，可直接实现并做同条件复测。

多实例下，通过各自的 session 调用 profiler，并把 job ID 与实例一起记录；同名 ID 不能跨 MCP 服务查询。独立工作目录隔离 MCDK 的磁盘产物，但 Native 采样仍需检查 `/doctor` 的实际进程与端点。并行游戏会竞争主机资源，性能基线应在相同竞争条件下采集。

## 生命周期与产物

- 默认 `storage:"memory"`：进程内临时结果，20 分钟空闲后由后续请求惰性回收，不进入 history，MCDK 退出即丢失。
- `storage:"disk"`：需要跨重启恢复或长期基线时显式选择，再通过 `/history` 等实际帮助查询。
- Markdown / SVG 仅 `/export` 显式写出，使用返回的受控目录路径；不要承诺任意输出路径。
- 任务有服务端截止时间；Native 终止可能仍处于 cleanup_pending，等待清理再启动下一轮。提前停止使用 `/stop`，不要直接杀进程替代正常结束。
- Native 慢调用与 Python / 引擎阶段的关联依赖游戏相应 zone 埋点，不等于任意函数都能无侵入追踪，也不等于完整内存泄漏根因证明。

向用户交付测试场景、采样类型/时长、关键热点/调用量、基线差异和导出路径；明确哪些结论有测量支持、哪些还需进一步验证。
