# Composite 参数文档

Composite 是由 Primitive 组合出来的框架内置组件，统一存放在
`pyreact/composites/`。每个主要 Composite 使用独立模块实现，不直接映射单个
原生 Control。

## Animated

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

## FilledButton

FilledButton 是纯色背景按钮 Composite，基于 `Button + Image` 组合。

- `default`：默认态 `Color`，默认 `Colors.transparent`。
- `hover`：悬停态 `Color`。未传时使用 `default.lighten(0.2)`。
- `pressed`：按下态 `Color`。未传时使用 `default.darken(0.2)`。
- `key`、`ref`、`style`、`children`、`onClick`：原样透传给内部 `Button`。
- 其他 props：通过 `**kwargs` 原样透传给内部 `Button`。

## Modal

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

## SafeArea

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

## Dropdown

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

## ListView

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

## Toggle

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
