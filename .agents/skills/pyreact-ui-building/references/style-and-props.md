# Style 与 props 分工

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
