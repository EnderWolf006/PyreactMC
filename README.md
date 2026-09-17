# Pyreact-MC

Pyreact-MC 是一个类 React Native 的网易我的世界基岩版 JsonUI 开发框架。它把
JsonUI / ModSDK 中偏底层的 UI 控件创建、布局、事件和状态管理，封装成更接近 React
组件开发体验的 Python API，让复杂游戏内 UI 更容易编写、复用和维护。

## 框架特性

- 类 React 的函数式组件 + hooks + flexbox 布局开发体验，与 React Native 特性基本一致。
- 类 React Native Yoga 的 基于 flexbox 的现代化自研布局引擎，轻松排出各种复杂的布局。
- **因为像 RN，现代 Coding Agent 配合 skills 可以轻松使用 Pyreact-MC 编写调试游戏内 UI。**
- 拥有 Virtual DOM diff 与 fiber 调和机制，只在提交阶段写变更的原生控件，性能极优。
- 全局 `navigator` 页面栈与预注册Screen池，无需额外注册 JsonUI 也可直接用 push/HUD 显示UI。
- 可以与原生 JsonUI 混合使用，支持将 Pyreact 组件挂载到已有 JsonUI 界面，作为子控件嵌入。
- 动画与过渡：`Animated` + `Animation` + `Easing`；纯 visual 变更走快速路径优化，动画丝滑。
- 支持 PC 窗口 resize 重布局 与 移动端异形屏安全区 `SafeArea` 组件；支持触屏、键鼠和手柄操控。
- 内置 `use_event` / `use_custom_event` hooks，可在组件内监听 ModSDK 引擎事件与自定义事件。
- 内置 `primitive` 封装大部分常用原生控件，如 `Label`、`Button`、`Image`、`ScrollView`、`Input` 等。
- 内置 `composite` 封装 `primitive` 组合组件，如 `FilledButton`、`Modal`、`Animated`、 `Dropdown` 等。
- 可通过 `primitive` 与 `composite` 组合出更复杂的自定义组件，可自己封装组件库进行复用。

## 项目结构

- `pyreact/`：框架核心，部署时放到 `behavior/YourClientScript/pyreact`。
- `jsonui/PyreactBase.json`：JsonUI 模板，部署时放入 `resource/ui` 并在 `_ui_defs.json` 注册。
- `examples/`：示例组件（计数器、动画Demo、2048游戏Demo）。
- `.agents/skills/pyreact-ui-building/`：开发使用 Pyreact 的 Agent Skill，[人类也可读](.agents/skills/pyreact-ui-building/references/architecture.md)。
- `.agents/skills/pyreact-debugging/`：调试用 Agent Skill，可自动拉起游戏测试、读取日志与 UI 树、模拟交互、采样性能。

## 使用方法

### 1. 部署框架

1. 把 `pyreact/` 复制到客户端的 `behavior\YourClientScript\pyreact`。
2. 把 `jsonui/PyreactBase.json` 复制到 `resource/ui`，并在 `resource/ui/_ui_defs.json` 中注册。

### 2. 初始化运行时

在客户端系统初始化时调用 `runtime_init`，业务代码无需自己写 ScreenNode 或调用
`RegisterUI`：

```python
# -*- coding: utf-8 -*-
import mod.client.extraClientApi as clientApi
from .pyreact import *
ClientSystem = clientApi.GetClientSystemCls()
class PyreactExampleClientSystem(ClientSystem):
    def __init__(self, namespace, systemName):
        ClientSystem.__init__(self, namespace, systemName)
        runtime_init(self) # 在这里初始化
        self.ListenForEvent(clientApi.GetEngineNamespace(), clientApi.GetEngineSystemName(), 'UiInitFinished', self, self.UiInitFinished)
```

### 3. 编写组件并 push

函数式组件是使用 `@Component` 装饰的普通函数，返回 Primitive / Composite 调用形成的
`Element`；`navigator.push` 会为每个页面创建独立的 ScreenNode、Fiber 与 Hooks 状态。

```python
@Component # 函数式组件装饰器
def CounterDemo():
    count, set_count = use_state(0) # hooks 状态，组件每次渲染都会保持不变

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
                content="这是一个计数器示例",
            ),
            Button(
                style=Style(padding=8),
                onClick=lambda: set_count(count + 1),
                children=Label(shadow=True, content="Count: " + str(count)),
            ),
        ],
    )
```
在 `UiInitFinished` 事件之后的合适时机 push 页面：
```python
def UiInitFinished(self, args):
    navigator.push(CounterDemo)
```

### 4. 挂载到已有 JsonUI 界面（可选）

如需要把 Pyreact 挂到已有 JsonUI 的某个控件时，需要先在JsonUI文件把你要挂载的控件上继承rootBase，也就是`custom_root@PyreactBase.rootBase`。然后在自定义 `ScreenNode.Create`
中调用 `pyreact.create_root(Component).render("/control/path")`

### 说明与约定

- 函数式组件函数名用大驼峰，props 与 `style` 的 key 用驼峰，其余代码遵循 PEP8。
- 枚举禁止裸字符串，建议使用枚举类包装，如 `AlignItems.center`、`ButtonState.pressed`、`Display.none` 等。
- 布局与通用属性放 `Style`，原生控件专属属性放 `props`，比如 `fontSize` 放到 `props`。
- 当回调/闭包会延迟执行，而它引用的变量之后可能变化时，用 functools.partial 来固定值，不要依赖 lambda x=x: 这种默认参数技巧，容易引发机审误判。
- 含 `key=` / `ref=` 的源文件头部加 `# pylint: disable=unexpected-keyword-arg,E1123` 才可过机审。
- `navigator.push` / `replace` / `reset` 与 `create_root` 都支持传入Element（调用函数式组件的值）或 `@Component` 装饰的函数式组件，需要传 props 时必须用带括号的写法。

## 开发文档

完整文档（术语、使用链路、navigator、Style 与 props、全部 Primitive / Composite
参数表）已拆分到 **`pyreact-ui-building`** Agent Skill，作为人类的你也可以按需查阅：

| 文档 | 内容 |
| --- | --- |
| [references/architecture.md](.agents/skills/pyreact-ui-building/references/architecture.md) | 项目结构、框架源码分层、部署位置 |
| [references/terminology.md](.agents/skills/pyreact-ui-building/references/terminology.md) | `Control` / `Component` / `Primitive` / `Composite` 术语 |
| [references/getting-started.md](.agents/skills/pyreact-ui-building/references/getting-started.md) | 最小可用示例、初始化链路、移动端安全区尺寸 |
| [references/navigator.md](.agents/skills/pyreact-ui-building/references/navigator.md) | 全局 navigator 全部命令、与 native UI 组合 |
| [references/conventions.md](.agents/skills/pyreact-ui-building/references/conventions.md) | 命名规范、枚举包装、网易机审 `key`/`ref`、事件监听 Hook |
| [references/style-and-props.md](.agents/skills/pyreact-ui-building/references/style-and-props.md) | `Style` 与 props 分工、`transform`、`opacity` 继承 |
| [references/primitives.md](.agents/skills/pyreact-ui-building/references/primitives.md) | 所有 Primitive 的完整参数表 |
| [references/composites.md](.agents/skills/pyreact-ui-building/references/composites.md) | 所有 Composite 的完整参数表 |

## 调试

**`pyreact-debugging`** Agent Skill 提供启动游戏、实时日志流、UI 树检查、交互模拟、
窗口尺寸适配和 Tracy 函数级性能采样脚本。调试默认关闭（每帧零开销），需要时在首次
初始化开启：

```python
pyreact.runtime_init(self, debug=True)
```

## 许可与归属

本项目采用 [PyreactMC 自定义许可协议](LICENSE)，参考 Apache 2.0 的部分条款起草，**不是标准 Apache-2.0 开源许可**。[中文 NOTICE](NOTICE) 是许可条件的组成部分。使用前请阅读完整文本，尤其注意：

- 在网易《我的世界》中使用时，必须在适用的服务器／存档加载界面及切换维度界面显示：**本项目使用 PyreactMC 客户端 UI 框架**。
- 相关开发者账户下**全部付费组件累计获取量 + 全部网络游戏累计获取量 ≥ 1,000,000 次**（包括不使用本框架的作品）时，未经原作者 EnderWolf006 本人事先书面授权，禁止使用本框架。
- 不希望展示上述归属信息，或需偏离 NOTICE 规定的展示要求时，也须事先与原作者协商并取得书面授权；门槛授权与展示豁免相互独立。

统计口径、适用范围及协商方式见 [NOTICE](NOTICE)。再分发时须一并提供 LICENSE 和 NOTICE；原作者授权不替代网易或其他权利人的许可。
