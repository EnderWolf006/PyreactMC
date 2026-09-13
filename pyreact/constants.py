# -*- coding: utf-8 -*-
"""pyreact 常量与枚举。

所有枚举均使用类包装，禁止裸字符串，方便代码补全与静态检查。
颜色统一以 0~1 浮点 RGBA 存储，适配 ModSDK 的 SetColor/SetTextColor 接口。
"""


class Color(object):
    """RGBA 颜色。支持两种构造方式：

    - ``Color(0xFF0000FF)``  32 位整数，布局为 RRGGBBAA（高 8 位 red，低 8 位 alpha）
    - ``Color(1.0, 0.0, 0.0, 1.0)``  直接给定 0~1 浮点 r,g,b,a
    """

    __slots__ = ("r", "g", "b", "a")

    def __init__(self, *args):
        if len(args) == 1:
            value = args[0]
            if isinstance(value, (int, long)):
                r = ((value >> 24) & 0xFF) / 255.0
                g = ((value >> 16) & 0xFF) / 255.0
                b = ((value >> 8) & 0xFF) / 255.0
                a = (value & 0xFF) / 255.0
            elif isinstance(value, Color):
                r, g, b, a = value.r, value.g, value.b, value.a
            else:
                raise ValueError("Invalid Color argument: %r" % (value,))
            self.r = float(r)
            self.g = float(g)
            self.b = float(b)
            self.a = float(a)
        elif len(args) == 3:
            self.r = float(args[0])
            self.g = float(args[1])
            self.b = float(args[2])
            self.a = 1.0
        elif len(args) == 4:
            self.r = float(args[0])
            self.g = float(args[1])
            self.b = float(args[2])
            self.a = float(args[3])
        else:
            raise ValueError("Color expects 1, 3 or 4 arguments, got %d" % len(args))

    def darken(self, factor):
        """按 factor(0~1) 变暗，返回新 Color。"""
        factor = max(0.0, min(1.0, float(factor)))
        return Color(
            self.r * (1.0 - factor),
            self.g * (1.0 - factor),
            self.b * (1.0 - factor),
            self.a,
        )

    def lighten(self, factor):
        """按 factor(0~1) 变亮，返回新 Color。"""
        factor = max(0.0, min(1.0, float(factor)))
        return Color(
            self.r + (1.0 - self.r) * factor,
            self.g + (1.0 - self.g) * factor,
            self.b + (1.0 - self.b) * factor,
            self.a,
        )

    def with_alpha(self, alpha):
        """返回替换 alpha 通道后的新 Color。"""
        return Color(self.r, self.g, self.b, alpha)

    def to_rgb_tuple(self):
        """返回 (r, g, b) 三元组，供 LabelUIControl.SetTextColor 使用。"""
        return (self.r, self.g, self.b)

    def to_rgba_tuple(self):
        """返回 (r, g, b, a) 四元组，供 ImageUIControl.SetColor 使用。"""
        return (self.r, self.g, self.b, self.a)

    def __eq__(self, other):
        if not isinstance(other, Color):
            return False
        return (self.r, self.g, self.b, self.a) == (other.r, other.g, other.b, other.a)

    def __ne__(self, other):
        return not self.__eq__(other)

    def __hash__(self):
        return hash((self.r, self.g, self.b, self.a))

    def __repr__(self):
        return "Color(r=%.3f, g=%.3f, b=%.3f, a=%.3f)" % (self.r, self.g, self.b, self.a)


class Colors(object):
    """Material 基础颜色预设（默认 500 色阶）。"""

    transparent = Color(0x00000000)
    black = Color(0x000000FF)
    white = Color(0xFFFFFFFF)
    red = Color(0xF44336FF)
    pink = Color(0xE91E63FF)
    purple = Color(0x9C27B0FF)
    deepPurple = Color(0x673AB7FF)
    indigo = Color(0x3F51B5FF)
    blue = Color(0x2196F3FF)
    lightBlue = Color(0x03A9F4FF)
    cyan = Color(0x00BCD4FF)
    teal = Color(0x009688FF)
    green = Color(0x4CAF50FF)
    lightGreen = Color(0x8BC34AFF)
    lime = Color(0xCDDC39FF)
    yellow = Color(0xFFEB3BFF)
    amber = Color(0xFFC107FF)
    orange = Color(0xFF9800FF)
    deepOrange = Color(0xFF5722FF)
    brown = Color(0x795548FF)
    grey = Color(0x9E9E9EFF)
    blueGrey = Color(0x607D8BFF)


class FontSize(object):
    """字号枚举。

    ModSDK 的 SetTextFontSize 接收 scale，本框架的 fontSize 使用更接近
    JsonUI 字号的数值，映射到原生时统一乘以 0.1。
    """

    small = 5
    normal = 10
    medium = 10
    large = 15
    extra_large = 20

    @staticmethod
    def is_valid(value):
        return value in (FontSize.small, FontSize.normal, FontSize.medium,
                         FontSize.large, FontSize.extra_large) or isinstance(value, (int, long, float))


class FlexDirection(object):
    """主轴方向，与 ReactNative 一致。"""

    column = "column"
    row = "row"
    column_reverse = "column-reverse"
    row_reverse = "row-reverse"


class AlignItems(object):
    """交叉轴对齐方式。"""

    flex_start = "flex-start"
    center = "center"
    flex_end = "flex-end"
    stretch = "stretch"


class AlignSelf(object):
    """单个子项的交叉轴对齐，覆盖父级 alignItems。"""

    auto = "auto"
    flex_start = "flex-start"
    center = "center"
    flex_end = "flex-end"
    stretch = "stretch"


class AlignContent(object):
    """多行内容在交叉轴上的分布方式。"""

    flex_start = "flex-start"
    center = "center"
    flex_end = "flex-end"
    stretch = "stretch"
    space_between = "space-between"
    space_around = "space-around"
    space_evenly = "space-evenly"


class JustifyContent(object):
    """主轴对齐/分布方式。"""

    flex_start = "flex-start"
    center = "center"
    flex_end = "flex-end"
    space_between = "space-between"
    space_around = "space-around"
    space_evenly = "space-evenly"


class Position(object):
    """定位方式（与 RN 一致）。"""

    relative = "relative"
    absolute = "absolute"


class Display(object):
    """显示模式。display:none 会从布局流中移除。"""

    flex = "flex"
    none = "none"


class ButtonState(object):
    """按钮状态，供 buttonBuilder 使用。"""

    default = "default"
    hover = "hover"
    pressed = "pressed"


class TextAlignment(object):
    """文本对齐方式。"""

    left = "left"
    center = "center"
    right = "right"


class ImageAdaptionType(object):
    """图片适配方式（SetImageAdaptionType）。"""

    normal = "normal"              # 普通适配，不开启九宫并保持宽高比
    filled = "filled"              # 填充适配，不开启九宫并保持宽高比
    old_nine_slice = "oldNineSlice"        # ModSDK oldNineSlice 模式
    origin_nine_slice = "originNineSlice"  # 原版九宫格适配


class PaperDollRenderType(object):
    """纸娃娃渲染来源。"""

    entity = "entity"
    skeleton = "skeleton"
    block_geometry = "blockGeometry"


class FlexWrap(object):
    """flexWrap 换行模式。"""

    no_wrap = "nowrap"
    wrap = "wrap"
    wrap_reverse = "wrap-reverse"


def font_size_to_scale(font_size):
    """把字号（FontSize 枚举值或数值）转成 SetTextFontSize 的 scale。

    约定：Pyreact 层 fontSize=10 对应原生 scale=1.0，因此传给
    SetTextFontSize 前统一乘以 0.1。
    """
    if font_size is None or isinstance(font_size, bool):
        return None
    if isinstance(font_size, (int, long, float)):
        return float(font_size) * 0.1
    return None
