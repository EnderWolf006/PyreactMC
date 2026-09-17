# 组件设计规范

- 每个 Pyreact 自定义组件必须使用 `@Component` 装饰器。
- `@Component` 负责处理组件通用的 `key`、`ref` 等能力。
- 所有 hooks 行为应尽量与 React 保持一致。
- `children` 可以是单个组件，也可以是组件列表或元组。
- 组件名使用大驼峰命名法，例如 `CounterDemo`。
- props 和 style 的 key 使用驼峰命名法，例如 `fontSize`、`alignItems`、`marginBottom`。
- 其余函数和变量使用 PEP8 风格。
- 为方便代码补全和减少拼写错误，枚举禁止使用裸字符串，必须使用类包装，例如 `ButtonState.default`、`AlignItems.center`。

## 网易机审与 `key` / `ref`

组件调用上的 `key=` / `ref=` 可能被网易机审报 `E1123` / `unexpected-keyword-arg`。出现 `key=` 或 `ref=` 的源文件，文件头需加：

```python
 pylint: disable=unexpected-keyword-arg,E1123
```

## 绑定回调参数：推荐 `functools.partial`

在循环或其它作用域里给 `onClick` 等绑定「当前值」时，有人会用默认参数技巧（Default Argument Hack）避开 Python `lambda` 的延迟绑定（Late Binding），例如 `lambda item_id=item_id: pick(item_id)`。该写法可读性较差，且网易机审常报 `E0602`。推荐 `functools.partial`，语义更清晰：

```python
from functools import partial

onClick=partial(pick, item_id)
```

## 函数式组件监听 ModSDK 事件

`use_event(event_name, callback, active=True, priority=0)` 用于监听客户端引擎事件。它自动使用引擎的 namespace 和 systemName；`callback(args)` 始终读取最新一轮渲染中的 state，并会在组件卸载时自动调用 `UnListenForEvent`。

`use_custom_event(namespace, system_name, event_name, callback, active=True, priority=0)` 用于监听其他 System 广播的自定义事件 

```python
class MyClientSystem(ClientSystem):
    def __init__(self, namespace, systemName):
        ClientSystem.__init__(self, namespace, systemName)
        pyreact.runtime_init(self)
```

自定义事件仍由发送方 ClientSystem 负责定义和 `BroadcastEvent`；Hook 只管理函数组件订阅的生命周期。

```python
def on_board_reset(args):
    print "board reset", args


use_custom_event(
    "OtherMod",
    "OtherClientSystem",
    "BoardReset",
    on_board_reset,
)
```

```python
class EngineEvent(object):
    key_press = "OnKeyPressInGame"


@Component
def InputDrivenPanel():
    count, set_count = use_state(0)

    def on_key(args):
        if args.get("isDown") == "1":
            set_count(count + 1)

    use_event(EngineEvent.key_press, on_key)
    return Label(content=str(count))
```

`priority` 取值为 0 到 10。将 `active` 设为 `False` 会解除当前订阅；改变事件名、active 或 priority 也会先清理旧订阅再注册新订阅。
