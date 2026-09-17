# 全局 Navigator

`runtime_init(client_system, debug=False)` 会在 `UiInitFinished` 自动注册 16 个 Pyreact
Screen 槽位。业务代码无需为 Pyreact 页面编写 ScreenNode 或调用 `RegisterUI`：

```python
from .pyreact import navigator


def open_detail(item_id):
    navigator.push(DetailPage(itemId=item_id))
```

`push` / `replace` / `reset` 的页面参数统一按 `Element` 处理，两种写法等价：

- 传入已构造的 `Element`：`DetailPage(itemId=item_id)` 或 Primitive 调用结果；
- 传入未调用的 `@Component`：`DetailPage`，框架会以空 props 调用它并取回 `Element`。

无论哪种写法，navigator 记录的 `entry.element` 始终是 `Element`。当前 `@Component`
只接受关键字 props，因此字典参数应写成 `DetailPage(**props)`，并且需要传 props 时
必须使用带括号的写法。每次 push 都会创建独立 ScreenNode、Fiber 和 Hooks 状态。
传入其它类型时 `push` 返回 `False`，并通过 `on_error` 上报 `invalid_element`。

公开命令如下：

- `push(element, key=None, on_result=None, on_complete=None, on_error=None)`：压入 Pyreact 页面。
- `pop(count=1, result=None, on_complete=None, on_error=None)`：等待实际 UI 栈弹出指定层数；native、原版按钮和 navigator 发起的出栈都计数。
- `replace(element, key=None, on_complete=None, on_error=None)`：移除当前 Pyreact 页面及其上方 native UI，再压入替代页面。
- `pop_to(key, result=None, on_complete=None, on_error=None)`：返回指定 Pyreact 页面实例。
- `pop_to_top(result=None, on_complete=None, on_error=None)`：返回最早仍存活的 Pyreact 页面。
- `clear(on_complete=None, on_error=None)`：清除全部 Pyreact 页面及夹在其间的 native UI，停止在 Pyreact 根页面下方。
- `reset(element, key=None, on_complete=None, on_error=None)`：执行 clear 后建立新的 Pyreact 根页面。
- `close(on_complete=None, on_error=None)`：持续关闭所有 UI，直到 `PopTopUI` 无法继续，即返回纯游戏画面。

所有命令立即返回是否被接受。跨帧事务完成后调用
`on_complete(entry_or_none)`，失败时调用 `on_error(error)`。`push` 的
`on_result(result)` 会在该页面被移除且其打开者仍存活时调用。

只读查询包括：`is_ready`、`capacity`、`available_slots`、`depth`、`top`、
`top_ui_name`、`is_transitioning`、`can_go_back()`、`get_entries()`、
`get_entry(key)` 与 `contains(key)`。调试只能在首次运行时初始化时通过
`runtime_init(..., debug=True)` 全局开启，manual root 和 navigator 页面会统一
继承该设置。

## 与 Native UI 自由组合

业务代码可以自由调用 `PushScreen`、`PopScreen`、`PopTopUI`、`SetRemove` 或
游戏提供的原版 UI 接口，并与全局 `navigator` 的 push/pop 任意交错。框架不要求
预先登记 native 页面，也不增加额外使用限制。

运行时监听 `PopScreenAfterClientEvent`，因此 `pop(count)` 按实际发生的出栈事件
计数，而不是按 navigator 自己调用 `PopTopUI` 的次数计数。`replace`、`pop_to`、
`pop_to_top`、`clear`、`reset` 与 `close` 则在每次确认出栈后重新读取
`GetTopUI` / `GetTopScreen`，直到真实栈顶达到目标。事务期间 native 页面自行关闭、
业务代码主动 pop 或继续 push，都会在后续帧重新纳入判断。navigator 自己发起的
连续 pop 仍遵守 ModSDK 每帧最多弹出一个 UI 的原生限制。
