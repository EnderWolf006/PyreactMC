# 基础使用链路

一个使用全局 navigator 的最小 Pyreact-MC UI 由两部分组成：

1. 定义一个使用 `@Component` 装饰的组件。
2. 客户端系统中初始化 Pyreact，并在 UI 加载完成后 push 组件。

```python
 -*- coding: utf-8 -*-
import mod.client.extraClientApi as clientApi
from .pyreact import *

ClientSystem = clientApi.GetClientSystemCls()

@Component
def CounterDemo():
    count, set_count = use_state(0)

    def increment():
        set_count(count + 1)

    return SafeArea(
        style=Style(
            width="100%",
            height="100%",
            alignItems=AlignItems.center,
            justifyContent=JustifyContent.center,
        ),
        children=[
            Label(
                style=Style(marginBottom=8),
                fontSize=FontSize.large,
                shadow=True,
                content="这是一个计数器示例"
            ),
            Button(
                style=Style(padding=8),
                onClick=increment,
                children=Label(shadow=True, content="Count: " + str(count))
            ),
        ]
    )

class PyreactExampleClientSystem(ClientSystem):
    def __init__(self, namespace, systemName):
        ClientSystem.__init__(self, namespace, systemName)
        runtime_init(self) # 在客户端系统初始化时调用
        self.ListenForEvent(clientApi.GetEngineNamespace(), clientApi.GetEngineSystemName(), 'UiInitFinished', self, self.UiInitFinished)

    def UiInitFinished(self, args):
        navigator.push(CounterDemo())
```


需要挂载到已有 native JsonUI 的某个控件时，可在自定义 `ScreenNode.Create`
中调用 `pyreact.create_root(Component).render("/control/path")`；该模式无需使用
navigator 的 Screen 池。`create_root` 与 navigator 一样同时接受未调用的
`@Component` 和已构造的 `Element`：

```python
# 两种写法等价
pyreact.create_root(CounterDemo).render("/control/path")
pyreact.create_root(CounterDemo()).render("/control/path")
```

传入其它类型时 `render` 抛出 `TypeError`。未调用的 `@Component` 会以空 props
调用，因此需要传 props 时使用带括号的写法（可配合 `functools.partial` 等工厂函数）。

## 移动端安全区尺寸

`runtime_init()` 会在 `UiInitFinished` 后创建一个空的 HUD Screen，通过
`common.base_screen` 测量异形屏安全内容区，并缓存 JsonUI 坐标系下的宽高与
四边 inset：

```python
safe_area_size = pyreact.get_safe_area_size()
safe_area_insets = pyreact.get_safe_area_insets()
if safe_area_size is not None and safe_area_insets is not None:
    safe_width, safe_height = safe_area_size
    top = safe_area_insets.top
    right = safe_area_insets.right
    bottom = safe_area_insets.bottom
    left = safe_area_insets.left
```

UI 尚未完成布局时返回 `None`。运行时会持续等待首次有效布局，测量成功后即固定
使用该结果，不再因 PC 窗口尺寸变化或 UI 重新初始化重复测量。移动端安全区在
运行期间不会变化，PC 安全区恒为零。inset 与 Pyreact 布局使用相同的 JsonUI
坐标系，不是物理像素。

业务组件通常直接使用 `SafeArea`，不需要手动读取 inset：

```python
SafeArea(
    style=Style(width="100%", height="100%", padding=6),
    children=content,
)
```

`SafeArea` 会按自身绝对 frame 只加入仍被系统不安全区域覆盖的 padding，并与
`style` 中已有的 padding 相加；已位于安全矩形内的非根节点以及嵌套
`SafeArea` 不会重复缩进。首次异步测量完成后会自动重渲染。
