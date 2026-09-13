# Pyreact-MC 开发文档

Pyreact-MC 是一个类 React Native 的网易我的世界 Mod UI 开发框架。它的目标是把 JsonUI / ModSDK 中偏底层的控件创建、布局、事件和状态管理，封装成更接近 React 组件开发体验的 Python API，让复杂游戏内 UI 更容易编写、复用和维护。

## 术语约定

- 原生 JsonUI / ModSDK 控件叫 `Control`。
- Pyreact 中所有组件都叫 `Component`。
- 单个原生控件映射到 Pyreact 的组件叫 `Primitive`，包括 `Panel`、`Label`、`Image`、`Item`、`PaperDoll`、`Input`、`Slider`、`ScrollView`、`Button` 等。
- Pyreact 内置且由多个 Primitive 组合成的组件叫 `Composite`，包括 `Dropdown`、`FilledButton`、`ListView`、`Modal`、`SafeArea`、`Toggle` 等。
- 用户态通过 `@Component` 创建的业务组件叫 `Custom Component`。
- 其他概念尽量沿用 React / React Native 叫法。

## 项目结构

- `pyreact/`：Pyreact-MC 框架核心，需放到 `behavior\YourClientScript\pyreact`
    - `component.py`：组件装饰器与组件包装逻辑。
    - `element.py`：虚拟元素结构和 children 归一化。
    - `hooks.py`：类 react 的 hooks。
    - `host.py`：ScreenNode、root、运行时初始化和宿主侧调度。
    - `renderer.py`：提交阶段，将虚拟节点变化应用到原生控件。
    - `reconciler.py`：虚拟 DOM diff 与 fiber 调和。
    - `layout.py`：类 React Native 的 flex 布局计算。
    - `native.py`：ModSDK / JsonUI 原生控件访问与模板路径。
    - `primitives.py`：Primitive 组件。
    - `composites/`：Composite 组件包，按组件拆分。
    - `style.py`：`Style` 对象和样式解析。
    - `constants.py`：颜色、枚举和常量。
- `jsonui/PyreactBase`: JsonUI 模板文件，需放入 `resource/ui` 下并在 `_ui_defs.json` 注册。
- `examples/`：示例Pyreact组件代码。
- `.agents/skills/pyreact-debug`：调试用 Agent Skill，可让 Agent 打开游戏自动测试调试。

## 基础使用链路

一个使用全局 navigator 的最小 Pyreact-MC UI 由两部分组成：

1. 定义一个使用 `@Component` 装饰的组件。
2. 客户端系统中初始化 Pyreact，并在 UI 加载完成后 push 组件。

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
navigator 的 Screen 池。

### 移动端安全区尺寸

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

## 全局 Navigator

`runtime_init(client_system, debug=False)` 会在 `UiInitFinished` 自动注册 16 个 Pyreact
Screen 槽位。业务代码无需为 Pyreact 页面编写 ScreenNode 或调用 `RegisterUI`：

```python
from .pyreact import navigator


def open_detail(item_id):
    navigator.push(DetailPage(itemId=item_id))
```

`push` 只接受 `@Component` 或 Primitive 调用后生成的 `Element`。当前
`@Component` 使用关键字 props，因此字典参数应写成 `DetailPage(**props)`。
每次 push 都会创建独立 ScreenNode、Fiber 和 Hooks 状态。

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

### 与 Native UI 自由组合

业务代码可以自由调用 `PushScreen`、`PopScreen`、`PopTopUI`、`SetRemove` 或
游戏提供的原版 UI 接口，并与全局 `navigator` 的 push/pop 任意交错。框架不要求
预先登记 native 页面，也不增加额外使用限制。

运行时监听 `PopScreenAfterClientEvent`，因此 `pop(count)` 按实际发生的出栈事件
计数，而不是按 navigator 自己调用 `PopTopUI` 的次数计数。`replace`、`pop_to`、
`pop_to_top`、`clear`、`reset` 与 `close` 则在每次确认出栈后重新读取
`GetTopUI` / `GetTopScreen`，直到真实栈顶达到目标。事务期间 native 页面自行关闭、
业务代码主动 pop 或继续 push，都会在后续帧重新纳入判断。navigator 自己发起的
连续 pop 仍遵守 ModSDK 每帧最多弹出一个 UI 的原生限制。

## 组件设计规范

- 每个 Pyreact 自定义组件必须使用 `@Component` 装饰器。
- `@Component` 负责处理组件通用的 `key`、`ref` 等能力。
- 所有 hooks 行为应尽量与 React 保持一致。
- `children` 可以是单个组件，也可以是组件列表或元组。
- 组件名使用大驼峰命名法，例如 `CounterDemo`。
- props 和 style 的 key 使用驼峰命名法，例如 `fontSize`、`alignItems`、`marginBottom`。
- 其余函数和变量使用 PEP8 风格。
- 为方便代码补全和减少拼写错误，枚举禁止使用裸字符串，必须使用类包装，例如 `ButtonState.default`、`AlignItems.center`。

### 网易机审与 `key` / `ref`

组件调用上的 `key=` / `ref=` 可能被网易机审报 `E1123` / `unexpected-keyword-arg`。出现 `key=` 或 `ref=` 的源文件，文件头需加：

```python
# pylint: disable=unexpected-keyword-arg,E1123
```

### 绑定回调参数：推荐 `functools.partial`

在循环或其它作用域里给 `onClick` 等绑定「当前值」时，有人会用默认参数技巧（Default Argument Hack）避开 Python `lambda` 的延迟绑定（Late Binding），例如 `lambda item_id=item_id: pick(item_id)`。该写法可读性较差，且网易机审常报 `E0602`。推荐 `functools.partial`，语义更清晰：

```python
from functools import partial

onClick=partial(pick, item_id)
```

### 函数式组件监听 ModSDK 事件

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

## Style 与 props 分工

布局属性和组件通用属性必须放在 `Style` 中，例如：

- 宽高与尺寸：`width`、`height`、`minWidth`、`minHeight`、`maxWidth`、`maxHeight`、`aspectRatio`
- flex 布局：`flex`、`flexGrow`、`flexShrink`、`flexBasis`、`flexDirection`、`flexWrap`
- 对齐：`alignItems`、`alignSelf`、`alignContent`、`justifyContent`
- 间距：`gap`、`rowGap`、`columnGap`
- 内外边距：`padding`、`paddingHorizontal`、`paddingVertical`、`margin`、`marginHorizontal`、`marginVertical`
- 定位：`position`、`top`、`left`、`right`、`bottom`
- 显示：`display`（`Display.none` 时不参与布局）
- 通用视觉：`opacity`、`zIndex`、`visible`、`transform`

内部实现将 Style 字段分为 **layout** 与 **visual**。layout 变更会触发完整 measure/layout；仅 `opacity` / `transform` 等 paint 类 visual 变更会走快速路径，直接写 native alpha/位置，跳过整树布局。

`transform` 支持 `Translate`（设计像素平移）与 `Scale`（缩放），不参与布局流，叠加在 layout frame 之外：

注：对于简单动画尽量使用 visual 过渡，避免频繁触发 layout。

```python
from pyreact import Style, Translate, Scale

Style(transform=[Translate(10, -4)])
Style(transform=[{"translateX": 10, "translateY": -4}])
Style(transform=[Scale(1.5)])                       # 等比缩放，默认中心原点
Style(transform=[Scale(2.0, 0.5, origin=(0, 0))])   # x/y 独立，origin 左上
Style(transform=[{"scale": 1.2, "origin": (0.5, 1.0)}])
```

`Scale(x, y=None, origin=(0.5, 0.5))`：`y` 省略时等比缩放；`origin` 取值 0..1，表示缩放原点在自身 frame 中的相对位置。缩放只影响视觉 frame、不参与布局流，但会沿原生子树同步尺寸和本地位置，因此图片、文本等内部元素会作为整体缩放。Label 的原生字号按累计 `scaleY` 同步，并在缩放时将 native 绘制 frame 右下扩 `0.94px`，避免浮点 frame 裁掉字形边缘。多个 `Scale` 相乘，origin 取最后一项。

`flexWrap` 使用 `FlexWrap.no_wrap`、`FlexWrap.wrap` 或
`FlexWrap.wrap_reverse`。margin 支持 `"auto"`；百分比 margin/padding
遵循 RN/Yoga 语义，四个方向都相对包含块宽度解析。

原生控件专属属性放在 props 中，例如：

- `Label`：`content`、`color`、`fontSize`、`textAlign`、`linePadding`、`shadow`
- `Image`：`src`、`color`、`uv`、`uvSize`、`rotate`、`grayscale`、`clipRatio`、`frames`
- `Item`：`identifier`、`aux`、`enchant`、`userData`
- `PaperDoll`：`renderType`、实体/模型来源、模型缩放、旋转、渲染深度、MoLang 与光照参数
- `Slider`：`value`、`steps`、`onChange`
- `ScrollView`：`showScrollbar`
- `Button`：`onClick`、`buttonBuilder`

如果 native 控件支持 `color` 属性，Pyreact props 也支持 `color` 属性，并且值必须是 `Color` 对象或能明确转换为 `Color` 的兼容值。

组件的 `opacity` 支持继承：

```text
子组件最终 opacity = 父组件最终 opacity * 子组件自身 opacity
```

如果控件同时具有 `color` 和 `opacity`，最终 native alpha 应等于继承后的 `Style.opacity * Color.alpha`。

## Primitive 参数文档

所有 Primitive 都支持以下通用参数：

- `key`：Element 复用键，用于 diff 时对齐节点。
- `ref`：原生 Control 引用回调，或带 `current` 字段的对象。
- `style`：`Style` 实例，承载布局、显示、透明度、`zIndex` 等通用属性。
- `children`：子组件，可以是单个 Element、列表、元组、文本或数字。

### Panel

Panel 是容器 Primitive，映射普通 panel 控件。

- `style`：常用 `width`、`height`、`flex`、`padding`、`margin`、`flexDirection`、`alignItems`、`justifyContent`、`opacity`、`display`。
- `children`：挂载到 Panel 自身的子组件。

Panel 当前没有原生专属 props。

### Label

Label 是文本 Primitive，映射 label 控件。

- `style`：控制布局、位置、透明度和可见性。
- `content`：文本内容。`unicode` 会按 utf-8 编码后传给原生控件。
- `color`：文字颜色，必须是 `Color` 对象或能明确转换为 `Color` 的值。
- `fontSize`：`FontSize` 枚举值或数值。框架约定 `fontSize=10` 对应原生 `SetTextFontSize(1.0)`，传给原生前会乘以 `0.1`。
- `textAlign`：`TextAlignment` 枚举值。
- `linePadding`：`float`，多行文本的行间距（像素）。对应 ModSDK `SetTextLinePadding`，仅对换行后的多行文本生效，单行时无影响。与 RN 的 `lineHeight` 语义不同（`lineHeight` 是绝对行高，`linePadding` 是额外行间距）。
- `shadow`：`bool`，是否启用文字阴影。
- `children`：不建议传入；Label 主要通过 `content` 显示文本。

原生属性应用顺序为 `linePadding -> fontSize -> textAlign -> shadow -> color -> text`，保证 SDK 在 `SetText(syncSize=True)` 自适应尺寸前已收到全部影响排版/行高的属性。

Label 位于 `Scale` 子树时，框架按累计 `scaleY` 更新 `SetTextFontSize`，以保持字形自身比例；缩放后的 native 绘制 frame 在右下额外扩 `0.94px`，不影响逻辑 layout 或父级布局。

#### 自动换行

Label 支持在可推断宽度的场景下自动换行（对齐 RN `numberOfLines` 缺省时的 wrap 行为）：

- Label 自身 `style.width` 为显式数值 / px；
- 父级为 `column` 布局、有显式 `width`、`alignItems` 默认或显式 `stretch`、Label 未设置 `alignSelf` 为非 `stretch`/`auto`、且 Label 自身无显式 `width`。

以上场景下，布局量测阶段会把可用宽度传入 `measure_text`，由 SDK 在限定宽度内换行并返回多行宽高。其他场景（`row + flex`、`auto` 容器嵌 `auto` Label 的循环依赖等）当前退化为单行量测，不自动换行，后续完善。

### Image

Image 是图片 Primitive，映射 image 控件。

- `style`：控制布局、位置、透明度和可见性。
- `src`：贴图路径。
- `color`：图片颜色，必须是 `Color` 对象或能明确转换为 `Color` 的值。
- `uv`：二元组，设置贴图 UV 起点。
- `uvSize`：二元组，设置贴图 UV 尺寸。
- `rotatePivot`：二元组，设置旋转锚点。
- `rotate`：数值角度。内部按上次角度计算增量调用原生 Rotate。
- `grayscale`：`bool`，是否灰度显示。
- `clipRatio`：`float`，设置贴图裁剪比例。
- `imageAdaption`：`ImageAdaptionType` 枚举值。
- `nineSliceData`：四元组，仅九宫格适配时使用，顺序为左、右、上、下。
- `frames`：序列帧列表或元组。每帧可以是贴图路径，或者包含 `src`、`uv`、
  `uvSize` 的字典。字典帧只更新自己包含的字段，适合用顶层 `src` 配合 UV
  播放图集。未设置或传入空序列时禁用序列帧动画。
- `frameDuration`：每帧持续时间，单位为秒，默认 `0.1`，必须大于 `0`。
- `playing`：是否播放，默认 `True`。设为 `False` 会停在当前帧，再次设为
  `True` 后从当前帧继续；已经结束的非循环动画会从 `initialFrame` 重播。
- `loop`：是否循环，默认 `True`。
- `initialFrame`：初始帧索引，默认 `0`。
- `onAnimationEnd`：非循环动画结束时调用的无参回调。末帧会完整显示一个
  `frameDuration` 后才触发。
- `children`：挂载到 Image 自身的子组件。

多贴图序列帧：

```python
Image(
    frames=[
        "textures/ui/fire_0",
        "textures/ui/fire_1",
        "textures/ui/fire_2",
    ],
    frameDuration=0.08,
    loop=True,
    style=Style(width=32, height=32),
)
```

单张图集序列帧：

```python
Image(
    src="textures/ui/fire_sheet",
    frames=sprite_sheet_frames((16, 16), columns=3, rows=1),
    frameDuration=0.08,
    style=Style(width=32, height=32),
)
```

`sprite_sheet_frames(frame_size, columns, rows, count=None, offset=(0, 0),
spacing=(0, 0))` 按从左到右、从上到下的顺序生成 UV 帧。例如当前
`400 x 608`、`4 x 4` 的 `frames.png` 可直接写成：

```python
frames = sprite_sheet_frames((100, 152), 4, 4)
```

存在边距或帧间空隙时可以指定 `offset` 和 `spacing`；图集网格未全部使用时
可用 `count` 截断帧数。

### Item

Item 是物品展示 Primitive，映射原生 ItemRenderer 控件。

- `style`：通常设置 `width`、`height`。
- `identifier`：物品 identifier，例如 `minecraft:stone_sword`。
- `aux`：物品附加值，默认 `0`。
- `enchant`：`bool`，是否显示附魔效果。
- `userData`：物品 userData，空 dict 会视为 `None`。
- `itemDict`：ModSDK 物品字典。优先读取 `newItemName` / `newAuxValue`，并支持 `itemName` / `auxValue`、`userData`、`enchantData`、`modEnchantData`。

### PaperDoll

PaperDoll 是网易纸娃娃 Primitive，映射 JsonUI 的
`netease_paper_doll_renderer`，可渲染实体、骨骼模型或网格体模型。

- `style`：通常设置稳定的 `width`、`height`，也支持 `opacity`、`visible`、`zIndex` 等通用属性。
- `renderType`：`PaperDollRenderType.entity`、`PaperDollRenderType.skeleton` 或 `PaperDollRenderType.block_geometry`，默认 `entity`。
- `entityId`：实体运行时 ID；与 `entityIdentifier` 同传时 ModSDK 优先使用该字段。
- `entityIdentifier`：实体 identifier，例如 `minecraft:cow`。
- `skeletonModelName`：骨骼模型名称，仅 skeleton 模式使用。
- `animation`：骨骼动画名称，ModSDK 默认 `idle`。
- `animationLooped`：`bool`，骨骼动画是否循环，ModSDK 默认 `True`。
- `blockGeometryModelName`：`CombineBlockPaletteToGeometry` 返回的网格体模型名称，仅 block geometry 模式使用。
- `scale`：`float`，模型缩放比例，ModSDK 默认 `1.0`。
- `renderDepth`：`int`，渲染深度，用于处理 UI 遮挡剔除。ModSDK 对玩家默认 `-50`，普通生物默认 `-15`。
- `initRotX`、`initRotY`、`initRotZ`：初始三轴旋转角度。
- `molangDict`：MoLang 变量名到 `float` 的字典。
- `rotationAxis`：三元组，手势旋转所环绕的轴；JsonUI 模板的 `rotation` 为 `freedom_gesture` 时生效。
- `lightDirection`：三元组，骨骼模型的光照方向，仅 skeleton 模式支持。
- `children`：不建议传入；PaperDoll 主要用于渲染模型。

`ref.current` 返回 BaseUIControl。如需取得渲染后的模型 ID，先调用
`ref.current.asNeteasePaperDoll()`，之后再异步调用 `GetModelId()`；不要在
`RenderEntity` 或 `RenderSkeletonModel` 后立即读取。

```python
PaperDoll(
    style=Style(width=180, height=240),
    renderType=PaperDollRenderType.entity,
    entityIdentifier="minecraft:cow",
    scale=1.0,
    renderDepth=-15,
    initRotY=25,
)
```

### Input

Input 是文本输入 Primitive，映射 `common.text_edit_box`。

- `style`：控制输入框尺寸、位置、透明度和可见性。
- `value`：`str` 或 `unicode`，受控输入值。传入后原生文本会与该值同步。
- `onChange`：文本改变回调，签名为 `onChange(value)`。
- `children`：子组件，挂载到 Input 自身；一般不需要传入。

传入 `value + onChange` 时形成受控输入；不传 `value` 时为非受控输入，框架会保留原生输入内容并只在实际文本变化时触发 `onChange`。

### Slider

Slider 是滑块 Primitive，映射 `common.slider`，外观与原版设置界面滑块一致。

- `style`：控制滑块尺寸、位置、透明度和可见性；建议提供稳定的 `width` 和 `height`。
- `value`：`int` 或 `float`，受控滑块值。传入后原生值会与该值同步。
- `steps`：`int`，原生滑块格数，默认 `1`。`1` 表示 `0.0` 到 `1.0` 的连续值；大于 `1` 时为固定格滑块，值范围为 `0` 到 `steps - 1`。
- `onChange`：值改变回调，签名为 `onChange(value)`，其中 `value` 为 `float`。
- `children`：不建议传入；Slider 主要通过原生滑块交互。

传入 `value + onChange` 时形成受控滑块；不传 `value` 时为非受控滑块。框架使用一个共享的原生 Slider 事件绑定扫描已注册 Slider，只在值真正变化时触发对应回调。

```python
value, set_value = use_state(2.0)

Slider(
    style=Style(width=220, height=16),
    value=value,
    steps=6,
    onChange=set_value,
)
```

### ScrollView

ScrollView 是滚动容器 Primitive，映射 `common.scrolling_panel`。

- `style`：必须提供稳定尺寸，例如 `width` / `height` 或 `flex`。
- `showScrollbar`：`bool`，是否显示滚动条，默认 `True`。
- `children`：子组件会挂载到 `scrolling_content` 路径下。

可以通过 `ref.current` 获取 ScrollView 模板引用，并使用
`ScrollView.scroll_to` 设置像素滚动位置、使用
`ScrollView.scroll_to_percent` 设置百分比位置，或使用
`ScrollView.scroll_to_top` 回到内容顶部：

```python
scroll_ref = use_ref(None)

def back_to_top():
    ScrollView.scroll_to_top(scroll_ref.current)

ScrollView(ref=scroll_ref, children=items)
```

ScrollView 不再内置 `contentContainerStyle`。需要内容容器样式时，在 `children` 中显式放入 `Panel`，或者使用 `ListView`。

### Button

Button 是按钮 Primitive，映射原生 button 控件。

- `style`：控制按钮布局、尺寸、padding、透明度和可见性。按钮内容默认水平、
  垂直居中；显式设置 `alignItems` 或 `justifyContent` 可覆盖对应默认值。
- `onClick`：点击回调。当前绑定原生 touch up 事件。
- `buttonBuilder`：函数 `buttonBuilder(state)`，`state` 为 `ButtonState.default`、`ButtonState.hover` 或 `ButtonState.pressed`。返回单个 `Image` 时会复用模板状态控件设置背景。
- `children`：按钮内容，挂载到 Button 自身。

Button 模板中包含 `default`、`hover`、`pressed` 三个状态子控件，状态切换由原生 button 控件处理。

## Composite 参数文档

Composite 是由 Primitive 组合出来的框架内置组件，统一存放在
`pyreact/composites/`。每个主要 Composite 使用独立模块实现，不直接映射单个
原生 Control。

### Animated

Animated 是动画容器 Composite，基于 `Panel`。运行时监听客户端 `GameRenderTickEvent`，在每个渲染帧开始时推进时间线；事件频率等于当前 FPS。动画帧仍通过 Pyreact 的 state、diff 和 commit 流程提交；若插值字段仅含 visual（如 `opacity` / `transform`），会走 visual 快速路径，避免每帧整树 layout。

- `style`：外层 `Panel` 的静态 `Style`。
- `children`：单个组件或组件列表/元组。
- `enter`：可选 `Animation`，首次显示及重新显示时播放。
- `exit`：可选 `Animation`，`visible` 从 `True` 变为 `False` 时播放；完成后才卸载 children，并从布局流隐藏外层 `Panel`。
- `duration`：`transition` 过渡时长，单位秒，默认 `0.3`。
- `transition`：可选 `Style`。它直接或间接使用的 state 变化后，会从当前帧平滑过渡到新样式；动画中途更新目标时也从当前帧接续。
- `transitionEasing`：`transition` 使用的 easing 函数，默认 `Easing.linear`。
- `onTransitionComplete`：可选回调，在 state 驱动的 `transition` 自然结束时调用。
- `visible`：presence 开关，默认 `True`。退出动画必须通过 `visible=False` 触发；父组件直接删除 Animated 时，Fiber 已经卸载，无法播放 `exit`。

`Animation(duration=0.3, delay=0.0, easing=None, from_=None, to=None, onComplete=None)`：

- `duration`、`delay`：动画时长和延迟，单位秒。
- `easing`：函数 `easing(t)`，输入进度 `t` 为 `0~1`；默认使用 `Easing.linear`。
- `from_`、`to`：普通 `Style`。可插值字段包括数值尺寸、flex 数值、gap、定位偏移、padding、margin、`opacity` 和 `transform`（translate 与 scale，scale 的 origin 也会插值）；单位一致的百分比/px 字符串也可插值。
- `onComplete`：动画自然完成后的回调；被新的动画中断时不会调用。

离散字段（`display`、`visible`、`zIndex`、对齐方式等）不能可靠插值，应放在静态 `style` 或 transition 目标的最终值中；动画进行中会保持 from 侧的值。

Animation 进入/退出预设：

- `Animation.fade_in(...)` / `Animation.fade_out(...)`：透明度进入、退出。
- `Animation.slide_in_left(...)` / `Animation.slide_out_left(...)`：从左侧进入、向左侧退出（`transform` translate）。
- `Animation.slide_in_right(...)` / `Animation.slide_out_right(...)`：从右侧进入、向右侧退出。
- `Animation.slide_in_up(...)` / `Animation.slide_out_up(...)`：从上方进入、向上方退出。
- `Animation.slide_in_down(...)` / `Animation.slide_out_down(...)`：从下方进入、向下方退出。

fade 预设参数为 `duration`、`delay`、`easing`、`onComplete`。slide 预设额外支持非负的 `distance`，单位为设计像素，内部使用 `Style(transform=[Translate(...)])`。所有参数均可用关键字覆盖。

Easing 预设：

- 基础：`Easing.linear`、`Easing.ease_in`、`Easing.ease_out`、`Easing.ease_in_out`。
- 三次曲线：`Easing.cubic_in`、`Easing.cubic_out`、`Easing.cubic_in_out`。
- 回弹超调：`Easing.back_in`、`Easing.back_out`、`Easing.back_in_out`。
- 弹跳：`Easing.bounce_in`、`Easing.bounce_out`、`Easing.bounce_in_out`。
- 自定义三次贝塞尔：`Easing.cubic_bezier(x1, y1, x2, y2)` 返回 easing 函数。`x1`、`x2` 必须在 `0~1`，`y1`、`y2` 可超出该范围以实现回弹超调。

`Colors` 提供 Flutter Material 基础颜色（默认 500 色阶，不包含 shade 层级）：`red`、`pink`、`purple`、`deepPurple`、`indigo`、`blue`、`lightBlue`、`cyan`、`teal`、`green`、`lightGreen`、`lime`、`yellow`、`amber`、`orange`、`deepOrange`、`brown`、`grey`、`blueGrey`，以及 `black`、`white`、`transparent`。

```python
@Component
def Expandable():
    expanded, set_expanded = use_state(False)
    visible, set_visible = use_state(True)
    target_width = 180 if expanded else 90  # 间接使用 state 也可过渡

    return Animated(
        visible=visible,
        style=Style(height=36),
        enter=Animation.slide_in_left(
            distance=24,
            duration=0.25,
            easing=Easing.back_out,
        ),
        exit=Animation.fade_out(
            duration=0.2,
        ),
        duration=0.3,
        transitionEasing=Easing.ease_in_out,
        transition=Style(width=target_width),
        children=FilledButton(
            style=Style(width="100%", height="100%"),
            onClick=lambda: set_expanded(not expanded),
        ),
    )
```

### FilledButton

FilledButton 是纯色背景按钮 Composite，基于 `Button + Image` 组合。

- `default`：默认态 `Color`，默认 `Colors.transparent`。
- `hover`：悬停态 `Color`。未传时使用 `default.lighten(0.2)`。
- `pressed`：按下态 `Color`。未传时使用 `default.darken(0.2)`。
- `key`、`ref`、`style`、`children`、`onClick`：原样透传给内部 `Button`。
- 其他 props：通过 `**kwargs` 原样透传给内部 `Button`。

### Modal

Modal 是类似 React Native Modal 的全屏模态层 Composite，基于
`Panel + Button` 组合。它通过 ModSDK `GetScreenSize()` 获取完整屏幕尺寸，
不使用安全区尺寸。底层透明 `Button` 会吞噬点击，避免事件穿透到模态层下方；
传入 `onClick` 后可用于点击内容外侧关闭。

- `visible`：是否渲染模态层，默认 `True`。
- `style`：模态根 `Panel` 的 `Style`，可设置 `opacity`、`zIndex` 等；全屏
  尺寸和屏幕原点定位由 Modal 保证。
- `onClick`：可选背景点击回调。省略时仍会吞噬底层点击。
- `children`：显示在透明背景 `Button` 上方的组件。

```python
Modal(
    visible=dialog_open,
    onClick=close_dialog,
    children=Panel(
        style=Style(
            position=Position.absolute,
            left=80,
            top=48,
            width=160,
            height=114,
        ),
        children=dialog_content,
    ),
)
```

### SafeArea

SafeArea 是类似 React Native `SafeAreaView` 的异形屏安全区容器 Composite，
基于 `Panel`。它使用 `runtime_init()` 创建的 `common.base_screen` 探针结果，
根据容器绝对 frame 与全局安全矩形的重叠，把仍需避让的 inset 转换为 padding。

- `style`：应用到内部 `Panel` 的 `Style`。已有 `padding`、
  `paddingHorizontal`、`paddingVertical` 或单边 padding 会与安全区 inset 相加，
  百分比 padding 仍按父容器宽度解析。
- `children`：单个组件，或组件列表/元组。

根 SafeArea 会应用完整 inset；非根 SafeArea 如果已经位于安全矩形内则应用零
inset，嵌套 SafeArea 因此不会重复 padding。部分越过安全矩形边界时只应用实际
重叠的部分。

探针尚未完成首次布局时先按零 inset 渲染；测量完成后 `SafeArea` 会自动刷新。
inset 使用 JsonUI 设计坐标，不是设备物理像素。

### Dropdown

Dropdown 是下拉选择 Composite，基于 `Button + Image + Label + ListView`
组合，默认尺寸、贴图、间距和选项高亮尽量贴近原生 `server_form`。

- `style`：外层 `Panel` 的 `Style`，默认 `width="100%"`、`height=30`。
- `menuStyle`：展开菜单 `Panel` 的 `Style`，可覆盖默认位置和尺寸。
- `optionStyle`：每个选项 `Button` 的 `Style`，默认 `height=17`。
- `labelStyle`：收起态已选文本 `Label` 的 `Style`。
- `optionLabelStyle`：菜单选项文本 `Label` 的 `Style`。
- `options`：选项列表。每项可以是标量、`(label, value)`，或含
  `label` / `value` 的 dict。
- `value`：受控值。传入后选中态完全由 `value` 决定。
- `defaultValue`：非受控初始值；省略时默认选中第一项。
- `onChange`：选中后以 `onChange(value)` 调用。
- `placeholder`：当前值未匹配选项时显示的文本。
- `disabled`：禁用后不可展开或选择。
- `maxVisibleOptions`：菜单最多同时显示的选项数，默认 `5`。
- `showScrollbar`：选项超出可见数量时是否显示滚动条，默认 `True`。

展开时 Dropdown 会使用 `Modal` 创建覆盖完整屏幕的透明点击层；点击菜单外部或
选中选项都会自动收起。菜单顶部与触发按钮顶部对齐，因此选项会直接覆盖触发按钮。

```python
Dropdown(
    style=Style(width=120),
    options=[
        ("生存", "survival"),
        ("创造", "creative"),
        ("冒险", "adventure"),
    ],
    value=game_mode,
    onChange=set_game_mode,
)
```

### ListView

ListView 是列表 Composite，基于 `ScrollView + Panel` 组合。

- `style`：应用到外层 `ScrollView`，通常设置 `width`、`height` 或 `flex`。
- `contentContainerStyle`：应用到滚动内容 `Panel`。默认 `width="100%"`、`flexDirection=FlexDirection.column`、`alignItems=AlignItems.stretch`。
- `data`：列表数据。`None` 会当作空列表。
- `renderItem`：函数 `renderItem(item, index)`，返回 Element。未提供时使用 `Label(content=str(item))`。
- `keyExtractor`：函数 `keyExtractor(item, index)`，返回每项 key。未提供时优先读取 dict item 的 `id` 字段，否则使用 index 字符串。
- `listHeaderComponent`：列表头部 Element。
- `listFooterComponent`：列表底部 Element。
- `emptyComponent`：`data` 为空时显示的 Element。
- `numColumns`：列数。大于 `1` 时会把 item 按行包进 Panel。
- `columnWrapperStyle`：多列模式下行 Panel 的 Style，默认 row 布局。
- `showScrollbar`：透传给内部 `ScrollView`，控制滚动条显示。

### Toggle

Toggle 是原版风格开关 Composite，使用 `Button + Image` 模拟，不依赖原生
Toggle Control。默认尺寸和四种状态贴图与 `ui_template_toggles.json` 中的
`switch_toggle` 一致。

- `style`：应用到内部 `Button`，默认 `width=30`、`height=16`。
- `value`：受控 bool 值。传入后显示状态完全由 `value` 决定。
- `defaultValue`：非受控初始值，默认 `False`。
- `onChange`：点击后以 `onChange(nextValue)` 调用。
- `disabled`：禁用点击，并按原版 locked 状态使用 `0.5` 透明度。

```python
enabled, set_enabled = use_state(True)

Toggle(
    value=enabled,
    onChange=set_enabled,
)
```

## 许可与归属

本项目采用 [PyreactMC 自定义许可协议](LICENSE)，参考 Apache 2.0 的部分条款起草，**不是标准 Apache-2.0 开源许可**。[中文 NOTICE](NOTICE) 是许可条件的组成部分。使用前请阅读完整文本，尤其注意：

- 在网易《我的世界》中使用时，必须在适用的服务器／存档加载界面及切换维度界面显示：**本项目使用 PyreactMC 客户端 UI 框架**。
- 相关开发者账户下**全部付费组件累计获取量 + 全部网络游戏累计获取量 ≥ 1,000,000 次**（包括不使用本框架的作品）时，未经原作者 EnderWolf006 本人事先书面授权，禁止使用本框架。
- 不希望展示上述归属信息，或需偏离 NOTICE 规定的展示要求时，也须事先与原作者协商并取得书面授权；门槛授权与展示豁免相互独立。

统计口径、适用范围及协商方式见 [NOTICE](NOTICE)。再分发时须一并提供 LICENSE 和 NOTICE；原作者授权不替代网易或其他权利人的许可。



