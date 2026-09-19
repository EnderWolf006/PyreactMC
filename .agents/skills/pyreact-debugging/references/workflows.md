# 诊断与回归编排

两个入口都要求通过 `instances.py exec --session <file> --owner <agent> -- ...` 绑定实例。每轮在该实例 `artifacts/diagnostics/<run_id>` 或 `artifacts/cases/<run_id>` 保存输入、返回值、耗时、错误和 `evidence.json`，不会覆盖其他实例的证据。

## 诊断包

```powershell
python3 .agents/skills/pyreact-debugging/scripts/instances.py exec `
  --session $a.session_file --owner agent-a -- diagnostics.py --timeout 15 --pyreact
```

默认检查工具列表、客户端与服务端 IPC、原生 screen、近期日志和错误日志。`--pyreact` 额外查询 Fiber 树；确需视觉证据时加 `--capture`，并读取生成的 `capture.jpg`。`ok=true` 表示探针成功，日志里仍可能含业务错误，需查看对应记录。

## JSON 用例

把以下内容放进项目用例文件。`code_file` 相对用例文件定位，在游戏 Python 2 执行并通过 `_result` 返回 JSON；`server:true` 选择服务端。

```json
{
  "name": "inventory-check",
  "timeout": 20,
  "steps": [
    {"code_file": "inventory_check.py", "server": true, "path": ["ready"], "expect": true},
    {"script": "get_ui_tree.py", "argv": ["--quiet"]},
    {"script": "expect.py", "argv": ["count", "--type", "Label", "--gte", "1"]}
  ]
}
```

```powershell
python3 .agents/skills/pyreact-debugging/scripts/instances.py exec `
  --session $a.session_file --owner agent-a -- run_case.py D:/AddonA/tests/inventory.json
```

每个用例必须至少包含一个真实断言。`path` 是返回 JSON 的对象键 / 数组下标序列；`expect` 精确比较 JSON，布尔值不与整数混同。UI 断言前必须抓取新树；修改状态的代码、模拟交互或 navigator 操作之后，需要再次抓树。

脚本步骤支持 get_ui_tree、simulate、simulate_and_diff、navigator、query_tree 和 expect。不能覆盖路由、输出路径或用 `--help` 绕过断言。运行前校验全部步骤，单步失败或超时立即停止，不重放动作；超时只终止本地 worker，远端动作可能已执行，下一轮前先检查游戏状态。
