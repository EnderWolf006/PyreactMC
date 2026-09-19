# Pyreact-MC

Pyreact-MC 是一个类 React Native 的网易我的世界基岩版 JsonUI 开发框架。它把
JsonUI / ModSDK 中偏底层的 UI 控件创建、布局、事件和状态管理，封装成更接近 React
组件开发体验的 Python API，让复杂游戏内 UI 更容易编写、复用和维护。

## 框架特性

- **组件与状态**：函数式组件、hooks、Virtual DOM diff 与 Fiber 调和，在提交阶段更新原生控件。
- **布局与适配**：自研 flexbox 布局引擎、PC 窗口尺寸变化重排、移动端 `SafeArea` 安全区。
- **页面管理**：全局 `navigator` 页面栈与预注册 Screen 池，支持页面和 HUD，也可嵌入已有 JsonUI。
- **动画**：`Animated`、`Animation` 和 `Easing`，纯视觉属性更新使用快速路径。
- **事件与交互**：监听 ModSDK 引擎事件和自定义事件，支持触屏、键鼠和手柄交互。
- **组件库**：`Label`、`Button`、`Input` 等 Primitive，以及 `FilledButton`、`Modal`、`Dropdown` 等 Composite。
- **Agent 工具**：提供 UI 开发与 MCDK 调试 skills，支持界面检查、回归测试和多项目游戏实例管理。

## 项目结构

- `pyreact/`：框架核心，部署时放到 `behavior/YourClientScript/pyreact`。
- `jsonui/PyreactBase.json`：JsonUI 模板，部署时放入 `resource/ui` 并在 `_ui_defs.json` 注册。
- `examples/`：计数器、动画和 2048 游戏示例。
- `.agents/skills/pyreact-ui-building/`：开发使用 Pyreact 的 Agent Skill，[人类也可读](.agents/skills/pyreact-ui-building/references/architecture.md)。
- `.agents/skills/pyreact-debugging/`：调试用 Agent Skill，可自动拉起游戏测试、读取日志与 UI 树、模拟交互、采样性能。

## 使用方法

框架运行于网易《我的世界》基岩版 ModSDK 的游戏 Python 环境。本仓库提供框架源码与
JsonUI 模板，需部署到已有 Addon 项目；下面的 `behavior` 和 `resource` 分别代表项目的行为包与资源包目录。

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
        runtime_init(self)
        self.ListenForEvent(
            clientApi.GetEngineNamespace(), clientApi.GetEngineSystemName(),
            'UiInitFinished', self, self.UiInitFinished,
        )
```

### 3. 编写组件并 push

函数式组件是使用 `@Component` 装饰的普通函数，返回 Primitive / Composite 调用形成的
`Element`；`navigator.push` 会为每个页面创建独立的 ScreenNode、Fiber 与 Hooks 状态。

```python
@Component
def CounterDemo():
    count, set_count = use_state(0)

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

在上面的客户端系统类中添加 `UiInitFinished` 方法，收到事件后打开页面：

```python
def UiInitFinished(self, args):
    navigator.push(CounterDemo)
```

### 4. 挂载到已有 JsonUI 界面（可选）

先让目标 JsonUI 控件继承 `PyreactBase.rootBase`，例如 `custom_root@PyreactBase.rootBase`。
然后在自定义 `ScreenNode.Create` 中调用 `pyreact.create_root(CounterDemo).render("/control/path")`。

### 说明与约定

- 函数式组件函数名用大驼峰，props 与 `style` 的 key 用驼峰，其余代码遵循 PEP8。
- 枚举禁止裸字符串，建议使用枚举类包装，如 `AlignItems.center`、`ButtonState.pressed`、`Display.none` 等。
- 布局与通用属性放 `Style`，原生控件专属属性放 `props`，比如 `fontSize` 放到 `props`。
- 当回调或闭包引用的变量之后可能变化时，用 `functools.partial` 固定值；`lambda x=x:` 这类默认参数写法可能引发机审误判。
- 含 `key=` / `ref=` 的源文件头部加 `# pylint: disable=unexpected-keyword-arg,E1123` 才可过机审。
- `navigator.push` / `replace` / `reset` 与 `create_root` 支持传入 Element 或 `@Component` 装饰的函数式组件；需要传 props 时，先调用组件生成 Element。

## 开发文档

[DeepWiki](https://deepwiki.com/EnderWolf006/pyreactmc) 提供 AI 生成的实现说明，可作为辅助参考。

完整文档（术语、使用链路、navigator、Style 与 props、全部 Primitive / Composite
参数表）位于 [`pyreact-ui-building`](.agents/skills/pyreact-ui-building/SKILL.md)，可按需查阅：

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

[`pyreact-debugging`](.agents/skills/pyreact-debugging/SKILL.md) 基于
[MCDevTool（MCDK）](https://github.com/GitHub-Zero123/MCDevTool)，调试工具运行在宿主 Python 3，
游戏内执行的测试代码需兼容 Python 2。受管游戏实例和窗口操作目前面向 Windows，宿主需 Python 3.12 或更高版本。

| 场景 | 能力与入口 |
| --- | --- |
| 启动与连接 | 测试世界、MCP 服务、就绪检查：[配置说明](.agents/skills/pyreact-debugging/references/setup.md) |
| 多 agent / 多项目 | 独立实例、端口、世界、owner 路由与证据目录：[实例管理](.agents/skills/pyreact-debugging/references/instances.md) |
| Pyreact UI | Fiber 树、props、布局、navigator、语义交互和断言：[UI 调试](.agents/skills/pyreact-debugging/references/pyreact.md) |
| 游戏与原生 UI | JSON UI、真实键鼠输入、截图、日志、客户端 / 服务端执行和热重载：[运行时调试](.agents/skills/pyreact-debugging/references/runtime.md) |
| 自动回归 | 诊断包、JSON 用例、结果断言、失败证据：[回归编排](.agents/skills/pyreact-debugging/references/workflows.md) |
| 性能分析 | Python CPU / 内存、可选 Native CPU 采样与基线比较：[性能文档](.agents/skills/pyreact-debugging/references/performance.md) |

首次使用无需预先配置 MCDK 或 MCP：按[安装与启动说明](.agents/skills/pyreact-debugging/references/setup.md)
运行 `setup_mcdk.py --install --project <Addon目录>`，工具会在用户目录安装并校验官方固定版本。
开发游戏需事先通过 MC Studio 下载。

MCDK 通用调试不要求开启 Pyreact 调试。需要 Fiber 快照和框架交互时，在首次初始化开启：

```python
pyreact.runtime_init(self, debug=True)
```

多个 agent 可以并行调试各自的游戏实例；真实键鼠输入和窗口操作共享桌面，由工具串行协调。
并行修改源码时使用独立 worktree 或项目副本。网易客户端的部分全局选项与缓存仍可能共享。

`.mcdev.json` 包含本机游戏路径，已加入 Git 忽略规则。实例数据默认写入用户目录下的
`.pyreact-debug/instances/`；游戏、MCDK 二进制、存档和诊断产物无需放入本仓库。

## 许可与归属

本项目采用 [PyreactMC 自定义许可协议](LICENSE)，参考 Apache 2.0 的部分条款起草，**不是标准 Apache-2.0 开源许可**。[中文 NOTICE](NOTICE) 是许可条件的组成部分。使用前请阅读完整文本，尤其注意：

- 在网易《我的世界》中使用时，必须在开发者组件／服务器游戏的**作品详情介绍**中写明：**本项目使用 PyreactMC 客户端 UI 框架**（无需修改服务器／存档加载界面或切换维度界面）。
- 相关开发者账户下**全部付费组件累计获取量 + 全部网络游戏累计获取量 ≥ 1,000,000 次**（包括不使用本框架的作品）时，未经原作者 EnderWolf006 本人事先书面授权，禁止使用本框架。
- 不希望标注上述归属信息，或需偏离 NOTICE 规定的归属陈述要求时，也须事先与原作者协商并取得书面授权；门槛授权与归属陈述豁免相互独立。

统计口径、适用范围及协商方式见 [NOTICE](NOTICE)。再分发时须一并提供 LICENSE 和 NOTICE；原作者授权不替代网易或其他权利人的许可。
