# -*- coding: utf-8 -*-
"""Style：布局与通用视觉属性的容器。

Style 在公开 API 上仍是单一对象；内部将字段分为：

- **layout**：参与 Yoga 式布局计算的属性（宽高、flex、margin、position 等）
- **visual**：不改变布局流、只影响绘制/叠放/位移的属性（opacity、zIndex、
  visible、transform）

``display`` 既影响可见性也影响是否参与布局，归入 layout 集合（变更会触发布局）。

命名与 React Native 对齐。
"""


# ---------------------------------------------------------------------------
# 字段分类（内部实现用）
# ---------------------------------------------------------------------------

_LAYOUT_FIELDS = frozenset((
    # 尺寸
    "width", "height",
    "minWidth", "minHeight", "maxWidth", "maxHeight",
    "aspectRatio",
    # flex
    "flex", "flexGrow", "flexShrink", "flexBasis", "flexDirection",
    "alignItems", "justifyContent", "flexWrap", "alignSelf", "alignContent",
    # gap
    "gap", "rowGap", "columnGap",
    # 显示（none 时不参与布局）
    "display",
    # 定位
    "position", "top", "left", "right", "bottom",
    # 内外边距
    "padding", "paddingHorizontal", "paddingVertical",
    "paddingTop", "paddingBottom", "paddingLeft", "paddingRight",
    "margin", "marginHorizontal", "marginVertical",
    "marginTop", "marginBottom", "marginLeft", "marginRight",
))

_VISUAL_FIELDS = frozenset((
    "opacity", "zIndex", "visible", "transform",
))

# 可在动画时间线中插值的字段（layout 数值类 + visual 中可插值项）
_INTERPOLATABLE_FIELDS = frozenset((
    "width", "height",
    "minWidth", "minHeight", "maxWidth", "maxHeight",
    "aspectRatio",
    "flex", "flexGrow", "flexShrink", "flexBasis",
    "gap", "rowGap", "columnGap",
    "top", "left", "right", "bottom",
    "padding", "paddingHorizontal", "paddingVertical",
    "paddingTop", "paddingBottom", "paddingLeft", "paddingRight",
    "margin", "marginHorizontal", "marginVertical",
    "marginTop", "marginBottom", "marginLeft", "marginRight",
    "opacity",
    "transform",
))


class Translate(object):
    """transform 中的平移。值单位为设计像素。

    用法::

        Style(transform=[Translate(10, 0)])
        Style(transform=[Translate(x=4, y=-2)])
    """

    __slots__ = ("x", "y")

    def __init__(self, x=0.0, y=0.0):
        self.x = float(x)
        self.y = float(y)

    def __eq__(self, other):
        if not isinstance(other, Translate):
            return False
        return self.x == other.x and self.y == other.y

    def __ne__(self, other):
        return not self.__eq__(other)

    def __repr__(self):
        return "Translate(%r, %r)" % (self.x, self.y)


class Scale(object):
    """transform 中的缩放。不影响逻辑布局，会同步作用到原生子树的视觉 frame。

    实现为 SetSize（frame * scale）+ SetPosition（按 origin 矫正），原生控件
    不会自动缩放其子控件内容，因此 renderer 会递归同步子控件 frame。Label
    另外按累计纵向比例更新 fontSize，并在缩放时扩张 0.94px native frame
    防止字形边缘被裁剪。origin 为 (ox, oy)，0..1，默认 (0.5, 0.5) 中心。

    用法::

        Style(transform=[Scale(1.5)])
        Style(transform=[Scale(2.0, 0.5, origin=(0.0, 0.0))])
    """

    __slots__ = ("x", "y", "origin")

    def __init__(self, x=1.0, y=None, origin=(0.5, 0.5)):
        self.x = float(x)
        self.y = float(x if y is None else y)
        self.origin = (float(origin[0]), float(origin[1]))

    def __eq__(self, other):
        if not isinstance(other, Scale):
            return False
        return (self.x == other.x and self.y == other.y
                and self.origin == other.origin)

    def __ne__(self, other):
        return not self.__eq__(other)

    def __repr__(self):
        return "Scale(%r, %r, origin=%r)" % (self.x, self.y, self.origin)


class Style(object):
    """样式对象。所有属性可选，未设置即为 ``None``（表示使用默认/auto）。"""

    _EDGE_FIELDS = (
        "padding", "paddingHorizontal", "paddingVertical",
        "paddingTop", "paddingBottom", "paddingLeft", "paddingRight",
        "margin", "marginHorizontal", "marginVertical",
        "marginTop", "marginBottom", "marginLeft", "marginRight",
    )

    __slots__ = (
        # 尺寸
        "width", "height",
        "minWidth", "minHeight", "maxWidth", "maxHeight",
        "aspectRatio",
        # flex
        "flex", "flexGrow", "flexShrink", "flexBasis", "flexDirection",
        "alignItems", "justifyContent", "flexWrap", "alignSelf", "alignContent",
        # gap
        "gap", "rowGap", "columnGap",
        # 显示
        "display",
        # 定位
        "position", "top", "left", "right", "bottom",
        # 内外边距
        "padding", "paddingHorizontal", "paddingVertical",
        "paddingTop", "paddingBottom", "paddingLeft", "paddingRight",
        "margin", "marginHorizontal", "marginVertical",
        "marginTop", "marginBottom", "marginLeft", "marginRight",
        # 通用视觉
        "opacity", "zIndex", "visible",
        # transform（目前仅 translate）
        "transform",
        # 内部：显式设置的 key / 分类缓存
        "_set_keys",
        "_layout_keys",
        "_visual_keys",
    )

    def __init__(self, **kwargs):
        # 预置布局边距字段，避免 layout 热路径触发 slot 缺失查找。
        for slot in self._EDGE_FIELDS:
            setattr(self, slot, None)
        # 记录哪些 key 被显式设置，便于 diff
        self._set_keys = set()
        self._layout_keys = set()
        self._visual_keys = set()
        for key, value in kwargs.items():
            if key in self.__slots__ and not key.startswith("_"):
                if key == "transform":
                    value = _normalize_transform(value)
                setattr(self, key, value)
                self._set_keys.add(key)
                if key in _LAYOUT_FIELDS:
                    self._layout_keys.add(key)
                elif key in _VISUAL_FIELDS:
                    self._visual_keys.add(key)
            else:
                # 未知样式键：忽略但不报错，避免阻断渲染
                pass

    def get(self, key, default=None):
        if key in self._set_keys:
            return getattr(self, key, default)
        return default

    def has(self, key):
        return key in self._set_keys

    def has_layout(self):
        return bool(self._layout_keys)

    def has_visual(self):
        return bool(self._visual_keys)

    def layout_keys(self):
        return self._layout_keys

    def visual_keys(self):
        return self._visual_keys

    def copy(self):
        """浅拷贝为新 Style（显式字段一致）。"""
        values = {}
        for key in self._set_keys:
            values[key] = getattr(self, key)
        return Style(**values)

    def merge(self, other):
        """返回一个新 Style，other 中的设置覆盖 self。"""
        merged = Style()
        for slot in self.__slots__:
            if slot.startswith("_"):
                continue
            setattr(merged, slot, getattr(self, slot, None))
        merged._set_keys = set(self._set_keys)
        merged._layout_keys = set(self._layout_keys)
        merged._visual_keys = set(self._visual_keys)
        if other is not None:
            for key in other._set_keys:
                setattr(merged, key, getattr(other, key))
                merged._set_keys.add(key)
                if key in _LAYOUT_FIELDS:
                    merged._layout_keys.add(key)
                    merged._visual_keys.discard(key)
                elif key in _VISUAL_FIELDS:
                    merged._visual_keys.add(key)
                    merged._layout_keys.discard(key)
        return merged

    def without_fields(self, fields):
        """复制 Style，但移除 fields 中的显式字段。"""
        removed = set(fields)
        values = {}
        for key in self._set_keys:
            if key not in removed:
                values[key] = getattr(self, key)
        return Style(**values)

    def equals(self, other):
        if other is None:
            return False
        if self._set_keys != other._set_keys:
            return False
        for key in self._set_keys:
            if getattr(self, key) != getattr(other, key):
                return False
        return True

    def layout_equals(self, other):
        """仅比较 layout 字段是否一致。"""
        return _subset_equals(self, other, _LAYOUT_FIELDS)

    def visual_equals(self, other):
        """仅比较 visual 字段是否一致。"""
        return _subset_equals(self, other, _VISUAL_FIELDS)

    def __repr__(self):
        parts = []
        for key in sorted(self._set_keys):
            parts.append("%s=%r" % (key, getattr(self, key)))
        return "Style(%s)" % ", ".join(parts)


def style_layout_changed(prev, nxt):
    """两个 Style 的 layout 部分是否变化（None 视为空 Style）。"""
    if prev is nxt:
        return False
    return not _subset_equals(prev, nxt, _LAYOUT_FIELDS)


def style_visual_changed(prev, nxt):
    """两个 Style 的 visual 部分是否变化。"""
    if prev is nxt:
        return False
    return not _subset_equals(prev, nxt, _VISUAL_FIELDS)


# 绘制类 visual：变更时可不走整树 layout，只更新 native alpha/position
_PAINT_FIELDS = frozenset(("opacity", "transform"))


def style_paint_changed(prev, nxt):
    """opacity / transform 是否变化（visual-fast 路径触发条件）。"""
    if prev is nxt:
        return False
    return not _subset_equals(prev, nxt, _PAINT_FIELDS)


def resolve_transform(style):
    """解析 Style.transform，返回 (tx, ty, sx, sy, ox, oy)。

    tx/ty 为累计平移（设计像素），sx/sy 为累计缩放，ox/oy 为缩放原点。
    """
    if style is None or not style.has("transform"):
        return (0.0, 0.0, 1.0, 1.0, 0.5, 0.5)
    return _transform_components(style.get("transform"))


def _subset_equals(a, b, field_set):
    a_keys = set()
    b_keys = set()
    if a is not None:
        a_keys = a._set_keys & field_set
    if b is not None:
        b_keys = b._set_keys & field_set
    if a_keys != b_keys:
        return False
    for key in a_keys:
        if getattr(a, key) != getattr(b, key):
            return False
    return True


def _normalize_transform(value):
    """规范化 transform 输入为 list[Translate/Scale] 或 None。

    支持：
    - None
    - Translate / Scale 实例
    - dict：``{"translateX": x, "translateY": y}``、
      ``{"scale": s}`` / ``{"scaleX": x, "scaleY": y, "origin": (ox, oy)}``
    - list/tuple：以上各项的组合
    """
    if value is None:
        return None
    items = value
    if isinstance(value, (Translate, Scale)):
        items = (value,)
    elif isinstance(value, dict):
        items = (value,)
    elif not isinstance(value, (list, tuple)):
        raise TypeError(
            "Style.transform must be Translate, Scale, dict, list, or None")
    result = []
    for item in items:
        if item is None:
            continue
        if isinstance(item, Translate):
            result.append(Translate(item.x, item.y))
            continue
        if isinstance(item, Scale):
            result.append(Scale(item.x, item.y, item.origin))
            continue
        if isinstance(item, dict):
            if ("scale" in item or "scaleX" in item or "scaleY" in item):
                s = item.get("scale")
                if s is None:
                    s = 1.0
                sx = item.get("scaleX", s)
                sy = item.get("scaleY", s)
                origin = item.get("origin", (0.5, 0.5))
                result.append(Scale(sx, sy, origin))
            if ("translate" in item or "translateX" in item
                    or "translateY" in item):
                tx = item.get("translateX", item.get("translate", 0.0))
                ty = item.get("translateY", 0.0)
                if tx is None:
                    tx = 0.0
                if ty is None:
                    ty = 0.0
                result.append(Translate(tx, ty))
            # 未知 transform 类型忽略（为后续 rotate 等预留）
            continue
        raise TypeError(
            "Style.transform items must be Translate, Scale or dict, got %r"
            % type(item).__name__)
    if not result:
        return None
    return result


def _transform_components(transform):
    """把 transform 列表累计为 (tx, ty, sx, sy, ox, oy)。"""
    tx = 0.0
    ty = 0.0
    sx = 1.0
    sy = 1.0
    ox = 0.5
    oy = 0.5
    if transform:
        for item in transform:
            if isinstance(item, Translate):
                tx += item.x
                ty += item.y
            elif isinstance(item, Scale):
                sx *= item.x
                sy *= item.y
                ox, oy = item.origin
    return (tx, ty, sx, sy, ox, oy)


def interpolate_transform(from_value, to_value, progress):
    """在两组 transform 之间插值，返回 list[Translate/Scale]。"""
    ftx, fty, fsx, fsy, fox, foy = _transform_components(from_value)
    ttx, tty, tsx, tsy, tox, toy = _transform_components(to_value)
    result = [Translate(
        ftx + (ttx - ftx) * progress,
        fty + (tty - fty) * progress,
    )]
    if (fsx, fsy) != (1.0, 1.0) or (tsx, tsy) != (1.0, 1.0):
        result.append(Scale(
            fsx + (tsx - fsx) * progress,
            fsy + (tsy - fsy) * progress,
            (fox + (tox - fox) * progress, foy + (toy - foy) * progress),
        ))
    return result


def _resolve_edge_value(value, parent_size):
    if value is None:
        return 0.0
    if isinstance(value, bool):
        return 0.0
    if isinstance(value, (int, long, float)):
        return float(value)
    if isinstance(value, basestring):
        s = value.strip()
        if s.endswith("%"):
            try:
                pct = float(s[:-1]) / 100.0
            except ValueError:
                return 0.0
            if parent_size is None:
                return 0.0
            return parent_size * pct
        if s.endswith("px"):
            try:
                return float(s[:-2])
            except ValueError:
                return 0.0
        try:
            return float(s)
        except ValueError:
            return 0.0
    return 0.0


def _resolve_box_edges(style, prefix, parent_width=None, parent_height=None):
    """解析 margin/padding 的四边值，返回 (top, right, bottom, left)。

    支持简写：``padding=8``（四边同值）、``paddingHorizontal/Vertical``、
    以及 ``paddingTop/Right/Bottom/Left`` 单边覆盖。
    """
    short = getattr(style, prefix, None)
    h = getattr(style, prefix + "Horizontal", None)
    v = getattr(style, prefix + "Vertical", None)
    top = getattr(style, prefix + "Top", None)
    bottom = getattr(style, prefix + "Bottom", None)
    left = getattr(style, prefix + "Left", None)
    right = getattr(style, prefix + "Right", None)

    # RN/Yoga 与 CSS 一致：四个方向的百分比 margin/padding 都相对
    # containing block 的宽度解析，而不是上下边相对高度。
    t = r = b = l = 0.0
    if short is not None:
        t = b = _resolve_edge_value(short, parent_width)
        r = l = _resolve_edge_value(short, parent_width)
    if h is not None:
        r = l = _resolve_edge_value(h, parent_width)
    if v is not None:
        t = b = _resolve_edge_value(v, parent_width)
    if top is not None:
        t = _resolve_edge_value(top, parent_width)
    if bottom is not None:
        b = _resolve_edge_value(bottom, parent_width)
    if left is not None:
        l = _resolve_edge_value(left, parent_width)
    if right is not None:
        r = _resolve_edge_value(right, parent_width)
    return (t, r, b, l)


def resolve_padding(style, parent_width=None, parent_height=None):
    return _resolve_box_edges(style, "padding", parent_width, parent_height)


def resolve_margin(style, parent_width=None, parent_height=None):
    return _resolve_box_edges(style, "margin", parent_width, parent_height)
