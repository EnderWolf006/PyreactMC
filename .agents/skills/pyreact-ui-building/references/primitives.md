# Primitive 参数文档

所有 Primitive 都支持以下通用参数：

- `key`：Element 复用键，用于 diff 时对齐节点。
- `ref`：原生 Control 引用回调，或带 `current` 字段的对象。
- `style`：`Style` 实例，承载布局、显示、透明度、`zIndex` 等通用属性。
- `children`：子组件，可以是单个 Element、列表、元组、文本或数字。

## Panel

Panel 是容器 Primitive，映射普通 panel 控件。

- `style`：常用 `width`、`height`、`flex`、`padding`、`margin`、`flexDirection`、`alignItems`、`justifyContent`、`opacity`、`display`。
- `children`：挂载到 Panel 自身的子组件。

Panel 当前没有原生专属 props。

## Label

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

### 自动换行

Label 支持在可推断宽度的场景下自动换行（对齐 RN `numberOfLines` 缺省时的 wrap 行为）：

- Label 自身 `style.width` 为显式数值 / px；
- 父级为 `column` 布局、有显式 `width`、`alignItems` 默认或显式 `stretch`、Label 未设置 `alignSelf` 为非 `stretch`/`auto`、且 Label 自身无显式 `width`。

以上场景下，布局量测阶段会把可用宽度传入 `measure_text`，由 SDK 在限定宽度内换行并返回多行宽高。其他场景（`row + flex`、`auto` 容器嵌 `auto` Label 的循环依赖等）当前退化为单行量测，不自动换行，后续完善。

## Image

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

## Item

Item 是物品展示 Primitive，映射原生 ItemRenderer 控件。

- `style`：通常设置 `width`、`height`。
- `identifier`：物品 identifier，例如 `minecraft:stone_sword`。
- `aux`：物品附加值，默认 `0`。
- `enchant`：`bool`，是否显示附魔效果。
- `userData`：物品 userData，空 dict 会视为 `None`。
- `itemDict`：ModSDK 物品字典。优先读取 `newItemName` / `newAuxValue`，并支持 `itemName` / `auxValue`、`userData`、`enchantData`、`modEnchantData`。

## PaperDoll

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

## Input

Input 是文本输入 Primitive，映射 `common.text_edit_box`。

- `style`：控制输入框尺寸、位置、透明度和可见性。
- `value`：`str` 或 `unicode`，受控输入值。传入后原生文本会与该值同步。
- `onChange`：文本改变回调，签名为 `onChange(value)`。
- `children`：子组件，挂载到 Input 自身；一般不需要传入。

传入 `value + onChange` 时形成受控输入；不传 `value` 时为非受控输入，框架会保留原生输入内容并只在实际文本变化时触发 `onChange`。

## Slider

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

## ScrollView

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

## Button

Button 是按钮 Primitive，映射原生 button 控件。

- `style`：控制按钮布局、尺寸、padding、透明度和可见性。按钮内容默认水平、
  垂直居中；显式设置 `alignItems` 或 `justifyContent` 可覆盖对应默认值。
- `onClick`：点击回调。当前绑定原生 touch up 事件。
- `buttonBuilder`：函数 `buttonBuilder(state)`，`state` 为 `ButtonState.default`、`ButtonState.hover` 或 `ButtonState.pressed`。返回单个 `Image` 时会复用模板状态控件设置背景。
- `children`：按钮内容，挂载到 Button 自身。

Button 模板中包含 `default`、`hover`、`pressed` 三个状态子控件，状态切换由原生 button 控件处理。
