---
name: pyreact-ui-building
description: 用 Pyreact-MC 框架编写运行在网易我的世界基岩版 ModSDK 中的 JsonUI 界面。需要新增或修改游戏内 UI 页面、编写 @Component 业务组件、使用 Primitive / Composite、编写 Style flex 布局、接入全局 navigator 页面栈、监听 ModSDK 事件、实现动画与过渡，或查询某个组件的 props 参数时使用。
metadata:
  audience: agents
  domain: pyreact-ui-building
  platform: netease-minecraft-bedrock-modsdk
---

## 我能做什么

- 用 `@Component` 函数式组件 + hooks（`use_state` / `use_ref` / `use_effect` / `use_memo` / `use_callback`）编写业务 UI。
- 组合框架内置 Primitive（`Panel`、`Label`、`Image`、`Item`、`PaperDoll`、`Input`、`Slider`、`ScrollView`、`Button`）与 Composite（`Animated`、`Dropdown`、`FilledButton`、`ListView`、`Modal`、`SafeArea`、`Toggle`）。
- 用 `Style` 编写 flex 布局、尺寸、间距、定位、`opacity`、`transform`。
- 通过全局 `navigator` 管理页面栈，并与 native JsonUI / 原版 UI 自由交错。
- 通过 `use_event` / `use_custom_event` 在函数式组件里监听 ModSDK 引擎事件与自定义事件。
- 用 `Animated` + `Animation` + `Easing` 实现进入/退出动画与样式过渡。
- 把已有的 native JsonUI 控件挂载到 Pyreact 根上。

## 什么时候使用

- 新增游戏内 UI 页面、面板、列表、下拉框、对话框、开关等。
- 修改既有组件的外观、布局、样式或交互回调。
- 需要确认某个 Primitive / Composite 的完整参数语义（例如 `Label.linePadding`、`Image.frames`、`PaperDoll.renderType`、`Slider.steps`）。
- 处理移动端异形屏安全区、响应式布局、`ScreenSizeChanged` 后的重排。
- 编写 `examples/` 下的示例组件。

## 不适用

- 调试实际运行效果（启动游戏、dump UI 树、模拟点击、窗口尺寸适配、性能采样）请使用 `pyreact-debugging` skill。

## 文档索引

| 文档 | 内容 |
| --- | --- |
| `references/architecture.md` | 项目结构、框架源码分层、部署位置 |
| `references/terminology.md` | `Control` / `Component` / `Primitive` / `Composite` 术语约定 |
| `references/getting-started.md` | 最小可用示例、初始化链路、移动端安全区尺寸 |
| `references/navigator.md` | 全局 navigator 全部命令、与 native UI 组合 |
| `references/conventions.md` | 命名规范、枚举包装、网易机审 `key`/`ref`、事件监听 Hook |
| `references/style-and-props.md` | `Style` 与 props 的分工、`transform`、`opacity` 继承 |
| `references/primitives.md` | 所有 Primitive 的完整参数表 |
| `references/composites.md` | 所有 Composite 的完整参数表 |

## 硬性约束

- 每个 Pyreact 自定义组件必须使用 `@Component` 装饰器。
- 枚举禁止使用裸字符串，必须使用类包装：`AlignItems.center`、`ButtonState.pressed`、`FontSize.large`、`Position.absolute`、`Display.none`、`FlexWrap.wrap`、`TextAlignment.center`。
- 布局与组件通用属性只能放在 `Style` 里；native 控件专属属性（`content`、`src`、`identifier`、`value`、`onClick` 等）放在 props 里。
- 组件名用大驼峰（`CounterDemo`），props 与 `style` 的 key 用驼峰（`fontSize`、`alignItems`、`marginBottom`），其余函数和变量遵循 PEP8。
- `children` 可以是单个组件，也可以是列表或元组。
- 循环或其它作用域里给 `onClick` 绑定「当前值」时使用 `functools.partial`（不要用 `lambda x=x:` 默认参数技巧，网易机审常报 `E0602`）。
- 源文件中出现 `key=` 或 `ref=` 时，文件头需加 `# pylint: disable=unexpected-keyword-arg,E1123`。
- 所有传入 native `color` 的值必须是 `Color` 对象或能明确转换为 `Color` 的值。

## 最小示例

```python
# -*- coding: utf-8 -*-
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
            Label(style=Style(marginBottom=8), fontSize=FontSize.large, shadow=True, content="这是一个计数器示例"),
            Button(
                style=Style(padding=8),
                onClick=increment,
                children=Label(shadow=True, content="Count: " + str(count)),
            ),
        ],
    )


class PyreactExampleClientSystem(ClientSystem):
    def __init__(self, namespace, systemName):
        ClientSystem.__init__(self, namespace, systemName)
        runtime_init(self)  # 在客户端系统初始化时调用
        self.ListenForEvent(
            clientApi.GetEngineNamespace(), clientApi.GetEngineSystemName(),
            'UiInitFinished', self, self.UiInitFinished,
        )

    def UiInitFinished(self, args):
        navigator.push(CounterDemo())
```

需要挂载到已有 native JsonUI 控件时，在自定义 `ScreenNode.Create` 中调用
`pyreact.create_root(Component).render("/control/path")`，无需使用 navigator 的 Screen 池。

`navigator.push` / `replace` / `reset` 与 `create_root` 都同时接受两种写法，内部统一
归一为 `Element`：已构造的 `Element`（`CounterDemo()`、`Panel(...)`），或未调用的
`@Component`（`CounterDemo`，以空 props 调用）。需要传 props 时用带括号的写法。

## 推荐工作流

1. 先按任务读取对应 reference：布局/样式看 `style-and-props.md`，组件参数看 `primitives.md` / `composites.md`，页面栈看 `navigator.md`，命名与机审看 `conventions.md`。
2. 修改框架本体时定位到对应模块（见 `architecture.md`）；业务组件与示例放在 `examples/` 或项目的 `behavior` 客户端脚本里。
3. 只用框架已有能力就能表达时，不要新增 API；扩展 API 时同步更新本 skill 的 reference。
4. 改完后用 `pyreact-debugging` skill 启动游戏，检查 UI 树、layout diff 和交互，再确认视觉。
