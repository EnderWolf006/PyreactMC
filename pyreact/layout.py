# -*- coding: utf-8 -*-
"""Flexbox 布局引擎（RN 风格子集）。

由于 ModSDK 的 SetSize 只接受像素、百分比仅存于 JSON 模板，动态布局必须由
本引擎在 Python 侧算出每个控件的像素 frame，再通过 SetPosition/SetSize 应用。

支持子集：
- flexDirection: row/row-reverse/column/column-reverse（默认 column）
- width/height: 数值(px) / "NN%" / "NNpx" / None(auto)
- flex/flexGrow/flexShrink/flexBasis: 按 flex line 分配主轴剩余空间
- alignItems: flex-start/center/flex-end/stretch
- alignSelf: auto/flex-start/center/flex-end/stretch
- alignContent: flex-start/center/flex-end/stretch/space-between/space-around/space-evenly
- justifyContent: flex-start/center/flex-end/space-between/space-around/space-evenly
- flexWrap: nowrap/wrap/wrap-reverse
- gap/rowGap/columnGap
- display: flex/none
- position: relative/absolute，支持 top/left/right/bottom
- padding / margin（简写与各边）

流程：先做后序 measure（叶子用 GetSize 量测、auto 容器由子项推算），
再做前序 layout 算绝对 frame，最后 apply。
"""
from . import native
from .style import resolve_padding, resolve_margin
from .constants import (
    FlexDirection, AlignItems, AlignSelf, AlignContent,
    JustifyContent, Color, FlexWrap, Position, Display,
)


_DIMENSION_SPEC_CACHE = {}
_DIMENSION_CACHE_MISS = object()
_DIMENSION_CACHE_LIMIT = 256
_MARGIN_FIELDS = frozenset((
    "margin", "marginHorizontal", "marginVertical",
    "marginTop", "marginRight", "marginBottom", "marginLeft",
))


class LayoutNode(object):
    __slots__ = (
        "fiber", "style", "children", "parent",
        "measured_w", "measured_h",
        "frame_x", "frame_y", "frame_w", "frame_h",
        "content_w", "content_h",
        "inherited_opacity",
        "visual_scale_x", "visual_scale_y",
        "first_measured_w", "first_measured_h",
        "measure_padding", "measure_margin_key", "measure_margin",
        "label_max_width",
        "direction", "column", "reverse", "display_none", "position",
        "gap_main", "gap_cross",
    )

    def __init__(self, fiber):
        self.fiber = fiber
        self.style = fiber.style
        self.children = []
        self.parent = None
        self.measured_w = None
        self.measured_h = None
        self.frame_x = 0.0
        self.frame_y = 0.0
        self.frame_w = 0.0
        self.frame_h = 0.0
        self.content_w = 0.0
        self.content_h = 0.0
        # 累计到本控件（含自身 opacity）的透明度，由 _collect 沿 fiber 树计算
        self.inherited_opacity = 1.0
        self.visual_scale_x = 1.0
        self.visual_scale_y = 1.0
        self.first_measured_w = None
        self.first_measured_h = None
        self.measure_padding = None
        self.measure_margin_key = None
        self.measure_margin = None
        self.label_max_width = None
        self.direction = _flex_direction(self.style)
        self.column = (self.direction != FlexDirection.row and
                       self.direction != FlexDirection.row_reverse)
        self.reverse = _is_reverse_direction(self.direction)
        self.display_none = (self.style is not None and
                             self.style.get("display") == Display.none)
        self.position = Position.relative
        if self.style is not None and self.style.get("position") is not None:
            self.position = self.style.get("position")
        self.gap_main, self.gap_cross = _resolve_gap(self.style, self.column)

# ---------------------------------------------------------------------------
# 构建布局树（组件透明，只取 primitive）
# ---------------------------------------------------------------------------

def build_layout_tree(root_fiber):
    """从根 fiber 构建 LayoutNode 列表（根可能渲染出多个 primitive）。"""
    return _collect(root_fiber, 1.0)


def _style_opacity(fiber):
    """取 fiber 自身 Style.opacity，未设置视为 1.0。"""
    style = fiber.style
    if style is not None and style.has("opacity"):
        op = style.get("opacity")
        if op is not None:
            return max(0.0, min(1.0, float(op)))
    return 1.0


def _collect(fiber, parent_opacity):
    """收集 fiber 下属的 primitive LayoutNode（递归穿透 component）。

    parent_opacity 为累计到 fiber 父级的透明度；fiber 自身的 opacity 会乘入
    并向其子 primitive 传递（组件 fiber 的 opacity 也参与继承）。
    返回的 LayoutNode.inherited_opacity 已含该 primitive 自身的 opacity。
    """
    own_opacity = parent_opacity * _style_opacity(fiber)
    result = []
    for cf in fiber.child_fibers:
        if cf.is_primitive:
            node = LayoutNode(cf)
            # primitive 自身的 inherited = 父累计 * 自身 style opacity
            node.inherited_opacity = own_opacity * _style_opacity(cf)
            node.children = _collect(cf, own_opacity)
            for c in node.children:
                c.parent = node
            result.append(node)
        else:
            result.extend(_collect(cf, own_opacity))
    return result


# ---------------------------------------------------------------------------
# 尺寸解析
# ---------------------------------------------------------------------------

def _parse_dimension(value, parent_size, measured):
    """返回 (size, is_explicit)。value 为 None/auto/数值/百分比/px。"""
    if value is None:
        return (measured if measured is not None else 0.0), False
    if isinstance(value, bool):
        return (measured if measured is not None else 0.0), False
    if isinstance(value, (int, long, float)):
        return float(value), True
    if isinstance(value, basestring):
        spec = _DIMENSION_SPEC_CACHE.get(value, _DIMENSION_CACHE_MISS)
        if spec is _DIMENSION_CACHE_MISS:
            s = value.strip()
            if s.endswith("%"):
                try:
                    spec = (1, float(s[:-1]) / 100.0)
                except ValueError:
                    spec = (2, 0.0)
            elif s.endswith("px"):
                try:
                    spec = (3, float(s[:-2]))
                except ValueError:
                    spec = (4, 0.0)
            else:
                try:
                    spec = (3, float(s))
                except ValueError:
                    spec = (0, 0.0)
            if len(_DIMENSION_SPEC_CACHE) >= _DIMENSION_CACHE_LIMIT:
                _DIMENSION_SPEC_CACHE.clear()
            _DIMENSION_SPEC_CACHE[value] = spec
        kind, number = spec
        if kind == 1:
            if parent_size is None:
                return 0.0, True
            return number * parent_size, True
        if kind == 2:
            return 0.0, False
        if kind == 3:
            return number, True
        if kind == 4:
            return 0.0, True
        return (measured if measured is not None else 0.0), False
    return (measured if measured is not None else 0.0), False


def _is_column(style):
    direction = _flex_direction(style)
    return direction != FlexDirection.row and direction != FlexDirection.row_reverse


def _flex_direction(style):
    direction = FlexDirection.column
    if style is not None and style.has("flexDirection"):
        direction = style.get("flexDirection")
    return direction


def _is_reverse_direction(direction):
    return direction == FlexDirection.row_reverse or direction == FlexDirection.column_reverse


def _is_display_none(style):
    return style is not None and style.has("display") and style.get("display") == Display.none


def _number(value, default=0.0):
    """把 Style 数值安全转为 float，非法值回退到 default。"""
    if value is None or isinstance(value, bool):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _flex_wrap(style):
    if style is None:
        return FlexWrap.no_wrap
    value = style.get("flexWrap")
    if value == FlexWrap.wrap or value == FlexWrap.wrap_reverse:
        return value
    return FlexWrap.no_wrap


def _is_auto(value):
    return isinstance(value, basestring) and value.strip() == "auto"


def _resolve_auto_margins(style):
    """返回四边 margin 是否为 auto，覆盖顺序与 resolve_margin 一致。"""
    if style is None or style._set_keys.isdisjoint(_MARGIN_FIELDS):
        return (False, False, False, False)
    short = getattr(style, "margin", None)
    horizontal = getattr(style, "marginHorizontal", None)
    vertical = getattr(style, "marginVertical", None)
    top = getattr(style, "marginTop", None)
    right = getattr(style, "marginRight", None)
    bottom = getattr(style, "marginBottom", None)
    left = getattr(style, "marginLeft", None)

    t = r = b = l = _is_auto(short)
    if horizontal is not None:
        r = l = _is_auto(horizontal)
    if vertical is not None:
        t = b = _is_auto(vertical)
    if top is not None:
        t = _is_auto(top)
    if right is not None:
        r = _is_auto(right)
    if bottom is not None:
        b = _is_auto(bottom)
    if left is not None:
        l = _is_auto(left)
    return (t, r, b, l)


def _is_scroll_node(node):
    """是否为 ScrollView Primitive。

    layout.py 不直接 import primitives，避免初始化阶段产生循环依赖。
    """
    return node is not None and node.fiber.comp_type.__class__.__name__ == "ScrollViewPrimitive"


def _is_parent_scroll(node):
    return node is not None and _is_scroll_node(node.parent)


def _resolve_gap(style, column):
    gap_main = 0.0
    gap_cross = 0.0
    if style is not None:
        gap = float(style.get("gap")) if style.has("gap") and style.get("gap") is not None else 0.0
        row_gap = float(style.get("rowGap")) if style.has("rowGap") and style.get("rowGap") is not None else gap
        column_gap = float(style.get("columnGap")) if style.has("columnGap") and style.get("columnGap") is not None else gap
        if column:
            gap_main = row_gap
            gap_cross = column_gap
        else:
            gap_main = column_gap
            gap_cross = row_gap
    return gap_main, gap_cross


# ---------------------------------------------------------------------------
# measure（后序）
# ---------------------------------------------------------------------------

def _has_unmeasured_text(node):
    """是否存在“有文本内容但尚未量测出尺寸”的叶子（需等屏幕渲染后重试）。"""
    if not node.children:
        props = node.fiber.last_props
        content = props.get("content") if props else None
        if content and (node.measured_w == 0.0 or node.measured_h == 0.0):
            return True
        return False
    for c in node.children:
        if _has_unmeasured_text(c):
            return True
    return False


def _needs_post_measure(node):
    """判断原生刷新后是否可能改变本树的自适应尺寸。"""
    if not node.children:
        props = node.fiber.last_props or {}
        content = props.get("content")
        # 文本由独立 measure 控件量测，结果由 native.measure_text 缓存，
        # 不依赖目标 Label 在首轮 UpdateScreen 后的尺寸。
        if content is not None and content != "":
            return False
        primitive_name = node.fiber.comp_type.__class__.__name__
        if primitive_name in ("PanelPrimitive", "LabelPrimitive"):
            return False
        style = node.style
        width = style.get("width") if style is not None else None
        height = style.get("height") if style is not None else None
        return width is None or height is None
    for child in node.children:
        if _needs_post_measure(child):
            return True
    return False


def measure(node, host, snapshot=False):
    """后序量测，填充 measured_w/h。None 表示该轴依赖父级（无法自底向上确定）。"""
    children_changed = False
    for child in node.children:
        if measure(child, host, snapshot):
            children_changed = True

    style = node.style
    w_val = style.get("width") if style is not None else None
    h_val = style.get("height") if style is not None else None
    column = node.column

    if not node.children:
        # 叶子量测：文本控件用专用 measure 控件量测（目标控件可能未渲染，
        # 直接 GetSize 会得 0）；其它控件用原生 GetSize，若得 0 则回退到
        # Style 中的显式 width/height（如 Item/Image 模板尺寸为 0 的情况）
        props = node.fiber.last_props
        content = props.get("content") if props else None
        if content is not None and content != "":
            from .constants import font_size_to_scale
            font_scale = None
            if props and props.get("fontSize") is not None:
                font_scale = font_size_to_scale(props.get("fontSize"))
            # 传入影响排版/行高的 props，让量测结果与实际渲染一致
            line_padding = props.get("linePadding")
            text_align = props.get("textAlign")
            shadow = props.get("shadow")
            # 若能从 Style/父级推断出可用宽度，则量测换行后的多行尺寸
            if snapshot or node.label_max_width is None:
                node.label_max_width = (_resolve_label_max_width(node),)
            max_width = node.label_max_width[0]
            size = native.measure_text(
                host, content, font_scale,
                line_padding=line_padding,
                text_alignment=text_align,
                shadow=shadow,
                max_width=max_width,
            )
        else:
            size = native.get_size(host, node.fiber.native_path)
            if size[0] == 0.0 or size[1] == 0.0:
                sw = style.get("width") if style is not None else None
                sh = style.get("height") if style is not None else None
                mw, _ = _parse_dimension(sw, None, size[0])
                mh, _ = _parse_dimension(sh, None, size[1])
                w = mw if (size[0] == 0.0 and sw is not None) else size[0]
                h = mh if (size[1] == 0.0 and sh is not None) else size[1]
                size = (w, h)
        node.measured_w = size[0]
        node.measured_h = size[1]
        if snapshot:
            node.first_measured_w = node.measured_w
            node.first_measured_h = node.measured_h
            return False
        return (children_changed or
                node.first_measured_w != node.measured_w or
                node.first_measured_h != node.measured_h)

    measured_w, w_explicit = _parse_dimension(w_val, None, None)
    measured_h, h_explicit = _parse_dimension(h_val, None, None)
    if w_explicit and measured_w == 0.0 and isinstance(w_val, basestring) and w_val.strip().endswith("%"):
        w_explicit = False
    if h_explicit and measured_h == 0.0 and isinstance(h_val, basestring) and h_val.strip().endswith("%"):
        h_explicit = False

    if snapshot or node.measure_padding is None:
        node.measure_padding = (resolve_padding(style) if style is not None
                                else (0, 0, 0, 0))
    pad_t, pad_r, pad_b, pad_l = node.measure_padding
    content_w = measured_w - pad_l - pad_r if w_explicit else None
    content_h = measured_h - pad_t - pad_b if h_explicit else None
    auto_w, auto_h = _measure_auto_container(node, content_w, content_h)

    node.measured_w = measured_w if w_explicit else auto_w + pad_l + pad_r
    node.measured_h = measured_h if h_explicit else auto_h + pad_t + pad_b
    if snapshot:
        node.first_measured_w = node.measured_w
        node.first_measured_h = node.measured_h
        return False
    return (children_changed or
            node.first_measured_w != node.measured_w or
            node.first_measured_h != node.measured_h)


def _resolve_label_max_width(node):
    """尝试推断 Label 叶子的可用宽度，供 measure_text 触发 SDK 自动换行。

    第一阶段只支持以下可推断宽度的场景，只在 measure 阶段用 Style 静态推断，
    不依赖前序 frame 结果：

    - Label 自身 ``style.width`` 为显式数值 / px 字符串（``%`` 需要父尺寸，
      此处无法解析，会被跳过）；
    - 父级为 column 布局、有显式 width（数值 / px）、alignItems 默认或显式
      stretch、Label 未设置 alignSelf 为非 stretch/auto、且 Label 自身无显式
      width：用父 content width 减去 Label 左右 margin 作为 max_width。

    其他场景（row + flex、auto 容器嵌 auto Label 的循环依赖等）返回 None，
    量测退化为单行，Label 不会自动换行。后续可完善 row + flex 的主轴推断。

    :return: max_width 像素值，或 None 表示无法推断。
    """
    style = node.style
    # 1. 自身显式 width（数值 / px）
    if style is not None:
        w_val = style.get("width")
        if w_val is not None:
            w, explicit = _parse_dimension(w_val, None, None)
            if explicit and w > 0.0:
                return w

    # 2. 依赖父级推断（column + stretch）
    parent = node.parent
    if parent is None or parent.style is None:
        return None
    pstyle = parent.style
    direction = parent.direction
    # 仅 column 布局下 stretch 能把 Label 拉到父宽；row 下 Label 宽度由内容决定
    if direction != FlexDirection.column and direction != FlexDirection.column_reverse:
        return None
    pw_val = pstyle.get("width")
    if pw_val is None:
        return None
    pw, pw_explicit = _parse_dimension(pw_val, None, None)
    if not pw_explicit or pw <= 0.0:
        return None
    # 父 content width = pw - parent padding 左右
    pad_t, pad_r, pad_b, pad_l = resolve_padding(pstyle, pw, None)
    parent_content_w = pw - pad_l - pad_r
    if parent_content_w <= 0.0:
        return None
    # alignItems 默认即为 stretch（与 RN 一致）；非 stretch 不推断
    align = AlignItems.stretch
    if pstyle.has("alignItems"):
        align = pstyle.get("alignItems")
    if align != AlignItems.stretch:
        return None
    # alignSelf 非 stretch/auto 的 Label 不会被拉满，不推断
    if style is not None and style.has("alignSelf"):
        self_align = style.get("alignSelf")
        if self_align != AlignSelf.auto and self_align != AlignSelf.stretch:
            return None
    # 扣除 Label 自身左右 margin
    mt, mr, mb, ml = resolve_margin(style, parent_content_w, None) if style else (0, 0, 0, 0)
    max_w = parent_content_w - ml - mr
    if max_w <= 0.0:
        return None
    return max_w


def _measure_auto_container(node, known_w, known_h):
    style = node.style
    column = node.column
    wrap = _flex_wrap(style)
    gap_main, gap_cross = node.gap_main, node.gap_cross

    lines = []
    cur_main = 0.0
    cur_cross = 0.0
    cur_count = 0
    max_main_limit = known_h if column else known_w

    for child in node.children:
        cstyle = child.style
        if child.display_none:
            continue
        if child.position == Position.absolute:
            continue

        child_w = _measure_child_axis(cstyle, "width", known_w, child.measured_w)
        child_h = _measure_child_axis(cstyle, "height", known_h, child.measured_h)
        margin_key = (known_w, known_h)
        if child.measure_margin is None or child.measure_margin_key != margin_key:
            child.measure_margin_key = margin_key
            child.measure_margin = (resolve_margin(cstyle, known_w, known_h)
                                    if cstyle else (0, 0, 0, 0))
        mt, mr, mb, ml = child.measure_margin
        if column:
            item_main = child_h + mt + mb
            item_cross = child_w + ml + mr
        else:
            item_main = child_w + ml + mr
            item_cross = child_h + mt + mb

        if wrap != FlexWrap.no_wrap and max_main_limit is not None and cur_count > 0:
            used_with_gap = cur_main + gap_main * cur_count + item_main
            if used_with_gap > max_main_limit + 0.001:
                lines.append((cur_main, cur_cross, cur_count))
                cur_main = 0.0
                cur_cross = 0.0
                cur_count = 0

        cur_main += item_main
        if item_cross > cur_cross:
            cur_cross = item_cross
        cur_count += 1

    if cur_count > 0:
        lines.append((cur_main, cur_cross, cur_count))

    if not lines:
        return (0.0, 0.0)

    if wrap != FlexWrap.no_wrap:
        max_line_main = max(line[0] + gap_main * max(0, line[2] - 1) for line in lines)
        total_cross = sum(line[1] for line in lines) + gap_cross * max(0, len(lines) - 1)
        if column:
            return (total_cross, max_line_main)
        return (max_line_main, total_cross)

    total_main = sum(line[0] for line in lines) + gap_main * max(0, lines[0][2] - 1)
    max_cross = max(line[1] for line in lines)
    if column:
        return (max_cross, total_main)
    return (total_main, max_cross)


def _measure_child_axis(style, axis, parent_size, measured):
    val = style.get(axis) if style is not None else None
    size, explicit = _parse_dimension(val, parent_size, measured)
    if explicit:
        if parent_size is None and isinstance(val, basestring) and val.strip().endswith("%"):
            return measured if measured is not None else 0.0
        return size
    if axis == "width" and style is not None and style.has("flexBasis") and measured in (None, 0.0):
        fb, fb_explicit = _parse_dimension(style.get("flexBasis"), parent_size, measured)
        if fb_explicit:
            return fb
    return measured if measured is not None else 0.0


def _remeasure_row_flex_text(item, host, cross_size):
    """用 flex 求解后的宽度重测 row 中的 auto-height Label。"""
    if host is None or item["cross_explicit"] or item["aspect_ratio"] > 0.0:
        return
    node = item["node"]
    if node.children:
        return
    props = node.fiber.last_props or {}
    content = props.get("content")
    max_width = item["main_base"]
    if content is None or content == "" or max_width <= 0.0:
        return
    width_key = (max_width,)
    if node.label_max_width == width_key:
        item["cross_base"] = _apply_cross_min_max(
            node.style,
            node.measured_h or item["cross_base"],
            cross_size,
            False,
        )
        return

    from .constants import font_size_to_scale
    font_scale = None
    if props.get("fontSize") is not None:
        font_scale = font_size_to_scale(props.get("fontSize"))
    size = native.measure_text(
        host,
        content,
        font_scale,
        line_padding=props.get("linePadding"),
        text_alignment=props.get("textAlign"),
        shadow=props.get("shadow"),
        max_width=max_width,
    )
    node.label_max_width = width_key
    if size[1] > 0.0:
        changed = abs((node.measured_h or 0.0) - size[1]) > 0.0001
        node.measured_h = size[1]
        item["cross_base"] = _apply_cross_min_max(
            node.style, size[1], cross_size, False
        )
        if changed:
            host._layout_text_remeasured = True


def _resolve_flexible_lengths(items, main_size, gap_total, column):
    """按 RN/Yoga 的权重为单个 flex line 分配主轴空间。

    常规路径只遍历两次。只有 min/max 截断分配结果时才重新分配该行，
    且每轮至少冻结一个子项，因此最坏循环次数不超过子项数。
    """
    if not items:
        return
    outer = gap_total + sum(
        it["m_main_start"] + it["m_main_end"] for it in items
    )
    initial_free = main_size - outer - sum(it["main_base"] for it in items)
    growing = initial_free > 0.0001
    if abs(initial_free) <= 0.0001:
        return
    if growing:
        if not any(it["flex_grow"] > 0.0 for it in items):
            return
    elif not any(it["flex_shrink"] > 0.0 for it in items):
        return

    base_sizes = [it["main_base"] for it in items]
    targets = list(base_sizes)

    factors = []
    for index, it in enumerate(items):
        if growing:
            factor = it["flex_grow"]
        else:
            # Yoga 的 shrink 权重是 flexShrink * flex base size。
            factor = it["flex_shrink"] * max(0.0, it["flex_base"])
        factors.append(max(0.0, factor))

    frozen = [factor <= 0.0 for factor in factors]
    while True:
        active = [i for i in range(len(items)) if not frozen[i]]
        if not active:
            break
        factor_sum = sum(factors[i] for i in active)
        if factor_sum <= 0.0:
            break
        occupied = outer
        for i in range(len(items)):
            occupied += targets[i] if frozen[i] else base_sizes[i]
        remaining = main_size - occupied
        if growing and remaining <= 0.0001:
            break
        if not growing and remaining >= -0.0001:
            break

        clamped = []
        proposed = {}
        for i in active:
            value = base_sizes[i] + remaining * (factors[i] / float(factor_sum))
            value = max(0.0, value)
            limited = _apply_main_min_max(
                items[i]["node"].style, value, main_size, column
            )
            proposed[i] = limited
            if abs(limited - value) > 0.0001:
                clamped.append(i)

        if not clamped:
            for i in active:
                targets[i] = proposed[i]
            break
        for i in clamped:
            targets[i] = proposed[i]
            frozen[i] = True

    for i, it in enumerate(items):
        it["main_base"] = targets[i]


# ---------------------------------------------------------------------------
# layout（前序，绝对坐标）
# ---------------------------------------------------------------------------

def _resolve_local_safe_area_padding(node, box):
    """返回当前节点与全局安全矩形重叠产生的局部 padding。"""
    safe_area = node.fiber.props.get("_safeArea")
    if safe_area is None:
        return (0.0, 0.0, 0.0, 0.0)

    safe_width, safe_height, top, right, bottom, left = safe_area
    if top <= 0.0 and right <= 0.0 and bottom <= 0.0 and left <= 0.0:
        return (0.0, 0.0, 0.0, 0.0)

    x, y, width, height = box
    width = max(0.0, float(width))
    height = max(0.0, float(height))
    screen_width = float(safe_width) + left + right
    screen_height = float(safe_height) + top + bottom
    safe_right = screen_width - right
    safe_bottom = screen_height - bottom

    local_top = min(height, max(0.0, top - y))
    local_right = min(width, max(0.0, x + width - safe_right))
    local_bottom = min(height, max(0.0, y + height - safe_bottom))
    local_left = min(width, max(0.0, left - x))

    # 极端尺寸下避免同一轴两边 padding 之和超过节点本身。
    if local_left + local_right > width:
        local_right = max(0.0, width - local_left)
    if local_top + local_bottom > height:
        local_bottom = max(0.0, height - local_top)
    return (local_top, local_right, local_bottom, local_left)

def layout(node, box, host):
    """box = (x, y, w, h) 绝对坐标，作为本节点的外框。"""
    node.frame_x, node.frame_y, node.frame_w, node.frame_h = box
    node.content_w = box[2]
    node.content_h = box[3]
    style = node.style
    direction = node.direction
    column = node.column
    reverse = node.reverse

    pad_t, pad_r, pad_b, pad_l = resolve_padding(style, box[2], box[3]) if style is not None else (0, 0, 0, 0)
    safe_t, safe_r, safe_b, safe_l = _resolve_local_safe_area_padding(
        node, box)
    pad_t += safe_t
    pad_r += safe_r
    pad_b += safe_b
    pad_l += safe_l
    cx = box[0] + pad_l
    cy = box[1] + pad_t
    cw = max(0.0, box[2] - pad_l - pad_r)
    ch = max(0.0, box[3] - pad_t - pad_b)

    if not node.children:
        return

    # 解析每个子项的主/交叉尺寸
    main_size = ch if column else cw
    cross_size = cw if column else ch

    # gap：RN 语义。rowGap 是纵向行距，columnGap 是横向列距。
    gap_main, gap_cross = node.gap_main, node.gap_cross

    items = []
    abs_items = []  # position:absolute 的子项，脱离 flex 流
    for child in node.children:
        cstyle = child.style
        if child.display_none:
            continue
        # position:absolute 脱离流式布局
        if child.position == Position.absolute:
            abs_items.append(child)
            continue

        if column:
            w, w_exp = _parse_dimension(cstyle.get("width") if cstyle else None, cw, child.measured_w)
            h, h_exp = _parse_dimension(cstyle.get("height") if cstyle else None, ch, child.measured_h)
            child_main_base = h
            child_cross_base = w
            main_explicit = h_exp
            cross_explicit = w_exp
        else:
            w, w_exp = _parse_dimension(cstyle.get("width") if cstyle else None, cw, child.measured_w)
            h, h_exp = _parse_dimension(cstyle.get("height") if cstyle else None, ch, child.measured_h)
            child_main_base = w
            child_cross_base = h
            main_explicit = w_exp
            cross_explicit = h_exp

        # aspectRatio：已知一轴推算另一轴
        ar = cstyle.get("aspectRatio") if (cstyle and cstyle.has("aspectRatio")) else None
        ar = _number(ar, 0.0)
        if ar > 0.0:
            if column:
                if w_exp and not h_exp:
                    child_main_base = w / ar
                    main_explicit = True
                elif h_exp and not w_exp:
                    child_cross_base = h * ar
                    cross_explicit = True
            else:
                if h_exp and not w_exp:
                    child_main_base = h * ar
                    main_explicit = True
                elif w_exp and not h_exp:
                    child_cross_base = w / ar
                    cross_explicit = True

        # flex / flexGrow / flexShrink / flexBasis
        flex_grow = 0.0
        flex_shrink = 0.0
        flex_basis = None
        if cstyle is not None:
            if cstyle.has("flex"):
                flex = _number(cstyle.get("flex"), 0.0)
                if flex > 0.0:
                    # RN 的正数 flex shorthand：grow=N, shrink=1, basis=0。
                    flex_grow = flex
                    flex_shrink = 1.0
                    flex_basis = 0.0
                elif flex < 0.0:
                    # RN 支持 flex=-1：保持 auto basis，但允许收缩。
                    flex_shrink = 1.0
            if cstyle.has("flexGrow"):
                flex_grow = max(0.0, _number(cstyle.get("flexGrow"), 0.0))
            if cstyle.has("flexShrink"):
                flex_shrink = max(0.0, _number(cstyle.get("flexShrink"), 0.0))
            if cstyle.has("flexBasis"):
                fb_val = cstyle.get("flexBasis")
                if fb_val is not None:
                    fb, _ = _parse_dimension(fb_val, main_size, child_main_base)
                    flex_basis = fb

        margin_key = (cw, ch)
        if (child.measure_margin is None or
                child.measure_margin_key != margin_key):
            child.measure_margin_key = margin_key
            child.measure_margin = (resolve_margin(cstyle, cw, ch)
                                    if cstyle else (0, 0, 0, 0))
        mt, mr, mb, ml = child.measure_margin
        auto_t, auto_r, auto_b, auto_l = _resolve_auto_margins(cstyle)
        if column:
            if reverse:
                m_main_start, m_main_end = mb, mt
                auto_main_start, auto_main_end = auto_b, auto_t
            else:
                m_main_start, m_main_end = mt, mb
                auto_main_start, auto_main_end = auto_t, auto_b
            m_cross_start, m_cross_end = ml, mr
            auto_cross_start, auto_cross_end = auto_l, auto_r
        else:
            if reverse:
                m_main_start, m_main_end = mr, ml
                auto_main_start, auto_main_end = auto_r, auto_l
            else:
                m_main_start, m_main_end = ml, mr
                auto_main_start, auto_main_end = auto_l, auto_r
            m_cross_start, m_cross_end = mt, mb
            auto_cross_start, auto_cross_end = auto_t, auto_b

        # 主轴基础尺寸：flexBasis 优先，否则显式/量测值
        if flex_basis is not None:
            flex_base = max(0.0, flex_basis)
        else:
            flex_base = max(0.0, child_main_base if child_main_base is not None else 0.0)

        # 换行使用经过 min/max 约束的 hypothetical main size；实际 grow/shrink
        # 仍保留未约束的 flex base 参与 shrink 权重计算。
        main_base = _apply_main_min_max(cstyle, flex_base, main_size, column)
        child_cross_base = _apply_cross_min_max(cstyle, child_cross_base or 0.0, cross_size, column)

        # alignSelf：覆盖父级 alignItems
        self_align = None
        if cstyle is not None and cstyle.has("alignSelf"):
            self_align = cstyle.get("alignSelf")

        items.append({
            "node": child, "main_base": main_base, "cross_base": child_cross_base or 0.0,
            "flex_base": flex_base,
            "flex_grow": flex_grow, "flex_shrink": flex_shrink,
            "flex_basis_set": flex_basis is not None,
            "aspect_ratio": ar,
            "main_explicit": main_explicit, "cross_explicit": cross_explicit,
            "self_align": self_align,
            "position": child.position,
            "m_main_start": m_main_start, "m_main_end": m_main_end,
            "m_cross_start": m_cross_start, "m_cross_end": m_cross_end,
            "auto_main_start": auto_main_start, "auto_main_end": auto_main_end,
            "auto_cross_start": auto_cross_start, "auto_cross_end": auto_cross_end,
        })

    # justifyContent 分布剩余空间
    justify = JustifyContent.flex_start
    if style is not None and style.has("justifyContent"):
        justify = style.get("justifyContent")

    # alignItems（默认 stretch，与 ReactNative 一致）
    align = AlignItems.stretch
    if style is not None and style.has("alignItems"):
        align = style.get("alignItems")

    # alignContent：多行在交叉轴上的分布，nowrap 时无效。
    align_content = AlignContent.flex_start
    if style is not None and style.has("alignContent"):
        align_content = style.get("alignContent")

    # flexWrap
    wrap = _flex_wrap(style)
    wrap_reverse = wrap == FlexWrap.wrap_reverse

    main_origin = (cy if column else cx)
    cross_origin = (cx if column else cy)

    # 把 items 切分成若干“行”（主轴方向）。nowrap 时只有一行。
    lines = []
    if wrap != FlexWrap.no_wrap:
        cur_line = []
        cur_main = 0.0
        for idx, it in enumerate(items):
            item_main = it["main_base"] + it["m_main_start"] + it["m_main_end"]
            existing_gap_total = gap_main * len(cur_line) if cur_line else 0.0
            if cur_line and cur_main + existing_gap_total + item_main > main_size + 0.001:
                lines.append(cur_line)
                cur_line = []
                cur_main = 0.0
            cur_line.append(it)
            cur_main += item_main
        if cur_line:
            lines.append(cur_line)
    else:
        lines.append(items)

    if not lines:
        lines.append([])

    # Yoga 先形成 flex line，再在每一行内独立 grow/shrink。
    for line_items in lines:
        line_gap_total = gap_main * max(0, len(line_items) - 1)
        _resolve_flexible_lengths(line_items, main_size, line_gap_total, column)
        for it in line_items:
            if not column:
                _remeasure_row_flex_text(it, host, cross_size)
            ar = it["aspect_ratio"]
            main_definite = (it["main_explicit"] or it["flex_basis_set"] or
                             it["flex_grow"] > 0.0)
            if ar > 0.0 and main_definite and not it["cross_explicit"]:
                if column:
                    cross = it["main_base"] * ar
                else:
                    cross = it["main_base"] / ar
                it["cross_base"] = _apply_cross_min_max(
                    it["node"].style, cross, cross_size, column
                )
                # aspectRatio 确定的交叉轴不能再被 alignItems:stretch 覆盖。
                it["cross_explicit"] = True

    # 预计算每一行的交叉轴尺寸，再由 alignContent 分配行组位置。
    line_metrics = []
    for line_items in lines:
        line_main_used = sum(
            it["main_base"] + it["m_main_start"] + it["m_main_end"]
            for it in line_items
        )
        if wrap == FlexWrap.no_wrap:
            line_cross = cross_size
        else:
            line_cross = 0.0
            for it in line_items:
                ic = it["cross_base"] + it["m_cross_start"] + it["m_cross_end"]
                if ic > line_cross:
                    line_cross = ic
        line_metrics.append({
            "items": line_items,
            "main_used": line_main_used,
            "cross": line_cross,
        })

    line_count_total = len(line_metrics)
    cross_gap_total = gap_cross * max(0, line_count_total - 1) if line_count_total > 1 else 0.0
    used_cross = sum(m["cross"] for m in line_metrics) + cross_gap_total
    cross_free = cross_size - used_cross
    cross_leading = 0.0
    line_cross_gap = gap_cross
    if wrap != FlexWrap.no_wrap and line_count_total > 0:
        if align_content == AlignContent.center:
            cross_leading = max(0.0, cross_free) / 2.0
        elif align_content == AlignContent.flex_end:
            cross_leading = max(0.0, cross_free)
        elif align_content == AlignContent.space_between:
            line_cross_gap = gap_cross + (max(0.0, cross_free) / float(line_count_total - 1) if line_count_total > 1 else 0.0)
        elif align_content == AlignContent.space_around:
            sg = max(0.0, cross_free) / float(line_count_total)
            cross_leading = sg / 2.0
            line_cross_gap = gap_cross + sg
        elif align_content == AlignContent.space_evenly:
            sg = max(0.0, cross_free) / float(line_count_total + 1)
            cross_leading = sg
            line_cross_gap = gap_cross + sg
        elif align_content == AlignContent.stretch and cross_free > 0.0:
            extra_cross = cross_free / float(line_count_total)
            for m in line_metrics:
                m["cross"] += extra_cross

    # 逐行布局
    cross_pos_cursor = cross_leading
    for metric in line_metrics:
        line_items = metric["items"]
        line_main_used = metric["main_used"]
        line_cross = metric["cross"]
        if not line_items:
            continue
        line_count = len(line_items)
        line_gap_total = gap_main * max(0, line_count - 1)
        line_free = main_size - line_main_used - line_gap_total
        auto_main_count = sum(
            int(it["auto_main_start"]) + int(it["auto_main_end"])
            for it in line_items
        )
        auto_main_share = 0.0
        if auto_main_count > 0 and line_free > 0.0:
            auto_main_share = line_free / float(auto_main_count)
            line_free = 0.0
        # justifyContent leading/gap
        if justify == JustifyContent.center:
            line_leading = max(0.0, line_free) / 2.0
            line_gap = gap_main
        elif justify == JustifyContent.flex_end:
            line_leading = max(0.0, line_free)
            line_gap = gap_main
        elif justify == JustifyContent.space_between:
            line_leading = 0.0
            line_gap = gap_main + (max(0.0, line_free) / float(line_count - 1) if line_count > 1 else 0.0)
        elif justify == JustifyContent.space_around:
            sg = max(0.0, line_free) / float(line_count) if line_count > 0 else 0.0
            line_leading = sg / 2.0
            line_gap = gap_main + sg
        elif justify == JustifyContent.space_evenly:
            sg = max(0.0, line_free) / float(line_count + 1) if line_count > 0 else 0.0
            line_leading = sg
            line_gap = gap_main + sg
        else:
            line_leading = 0.0
            line_gap = gap_main

        pos = line_leading
        for it in line_items:
            child = it["node"]
            m_start = it["m_main_start"]
            m_end = it["m_main_end"]
            if it["auto_main_start"]:
                m_start += auto_main_share
            if it["auto_main_end"]:
                m_end += auto_main_share
            m_cross_s = it["m_cross_start"]
            m_cross_e = it["m_cross_end"]

            # 该子项的有效对齐：alignSelf 覆盖 alignItems
            eff_align = align
            if it["self_align"] is not None and it["self_align"] != AlignSelf.auto:
                eff_align = it["self_align"]

            child_cross = it["cross_base"]
            cross_explicit = it["cross_explicit"]
            if it["auto_cross_start"] or it["auto_cross_end"]:
                auto_cross_free = max(
                    0.0, line_cross - child_cross - m_cross_s - m_cross_e
                )
                if it["auto_cross_start"] and it["auto_cross_end"]:
                    cross_offset = m_cross_s + auto_cross_free / 2.0
                elif it["auto_cross_start"]:
                    cross_offset = m_cross_s + auto_cross_free
                else:
                    cross_offset = m_cross_s
            elif eff_align == AlignItems.center or eff_align == AlignSelf.center:
                cross_offset = (line_cross - child_cross - m_cross_s - m_cross_e) / 2.0 + m_cross_s
            elif eff_align == AlignItems.flex_end or eff_align == AlignSelf.flex_end:
                cross_offset = line_cross - child_cross - m_cross_e
            elif (eff_align == AlignItems.stretch or eff_align == AlignSelf.stretch) and not cross_explicit:
                cross_offset = m_cross_s
                child_cross = line_cross - m_cross_s - m_cross_e
                child_cross = _apply_cross_min_max(child.style, child_cross, cross_size, column)
                it["cross_base"] = child_cross
            else:  # flex_start 或 stretch 但子项有显式尺寸
                cross_offset = m_cross_s

            main_pos = pos + m_start
            line_cross_pos = cross_pos_cursor
            if wrap_reverse:
                line_cross_pos = cross_size - cross_pos_cursor - line_cross
            cross_abs = cross_origin + line_cross_pos + cross_offset

            if column:
                main_abs = main_origin + main_pos
                if reverse:
                    main_abs = main_origin + main_size - main_pos - it["main_base"]
                child_box = (cross_abs, main_abs, child_cross, it["main_base"])
            else:
                main_abs = main_origin + main_pos
                if reverse:
                    main_abs = main_origin + main_size - main_pos - it["main_base"]
                child_box = (main_abs, cross_abs, it["main_base"], child_cross)

            if it["position"] == Position.relative:
                child_box = _apply_relative_offset(child.style, child_box, cw, ch)

            layout(child, child_box, host)
            pos += it["main_base"] + m_start + m_end + line_gap

        cross_pos_cursor += line_cross + line_cross_gap

    # absolute 定位子项：相对父级 padding box，用 top/left/right/bottom 定位
    for child in abs_items:
        cstyle = child.style
        top_v = cstyle.get("top") if (cstyle and cstyle.has("top")) else None
        left_v = cstyle.get("left") if (cstyle and cstyle.has("left")) else None
        right_v = cstyle.get("right") if (cstyle and cstyle.has("right")) else None
        bottom_v = cstyle.get("bottom") if (cstyle and cstyle.has("bottom")) else None
        w, w_explicit = _parse_dimension(
            cstyle.get("width") if cstyle else None, cw, child.measured_w
        )
        h, h_explicit = _parse_dimension(
            cstyle.get("height") if cstyle else None, ch, child.measured_h
        )
        left = _parse_dimension(left_v, cw, 0.0)[0] if left_v is not None else None
        right = _parse_dimension(right_v, cw, 0.0)[0] if right_v is not None else None
        top = _parse_dimension(top_v, ch, 0.0)[0] if top_v is not None else None
        bottom = _parse_dimension(bottom_v, ch, 0.0)[0] if bottom_v is not None else None
        mt, mr, mb, ml = (resolve_margin(cstyle, cw, ch)
                          if cstyle else (0.0, 0.0, 0.0, 0.0))

        # 与 RN 一致：auto 尺寸配合相对两侧 inset 时拉伸填充可用空间。
        if not w_explicit and left is not None and right is not None:
            w = max(0.0, cw - left - right - ml - mr)
            w_explicit = True
        if not h_explicit and top is not None and bottom is not None:
            h = max(0.0, ch - top - bottom - mt - mb)
            h_explicit = True

        ar = cstyle.get("aspectRatio") if (cstyle and cstyle.has("aspectRatio")) else None
        ar = _number(ar, 0.0)
        if ar > 0.0:
            if w_explicit and not h_explicit:
                h = w / ar
            elif h_explicit and not w_explicit:
                w = h * ar
        w = _apply_cross_min_max(cstyle, max(0.0, w or 0.0), cw, True)
        h = _apply_main_min_max(cstyle, max(0.0, h or 0.0), ch, True)

        # 解析 inset（相对 padding box）；显式尺寸下 left/top 优先。
        ax = cx
        ay = cy
        if left is not None:
            ax = cx + left + ml
        elif right is not None:
            ax = cx + cw - w - right - mr
        else:
            ax += ml
        if top is not None:
            ay = cy + top + mt
        elif bottom is not None:
            ay = cy + ch - h - bottom - mb
        else:
            ay += mt
        layout(child, (ax, ay, w, h), host)

    _update_content_size(node)

    # Scroll 的直接内容容器没有显式高度时，应按内容高度撑开，而不是被
    # 直接内容容器按子节点撑开，避免被视口高度锁住。
    if _is_parent_scroll(node):
        explicit_h = style is not None and style.has("height") and style.get("height") is not None
        if not explicit_h and node.content_h > node.frame_h:
            node.frame_h = node.content_h


def _update_content_size(node):
    if not node.children:
        node.content_w = node.frame_w
        node.content_h = node.frame_h
        return

    max_right = node.frame_x + node.frame_w
    max_bottom = node.frame_y + node.frame_h
    for child in node.children:
        if child.display_none:
            continue
        right = child.frame_x + child.frame_w
        bottom = child.frame_y + child.frame_h
        if child.content_w > child.frame_w:
            right = child.frame_x + child.content_w
        if child.content_h > child.frame_h:
            bottom = child.frame_y + child.content_h
        if right > max_right:
            max_right = right
        if bottom > max_bottom:
            max_bottom = bottom

    node.content_w = max(0.0, max_right - node.frame_x)
    node.content_h = max(0.0, max_bottom - node.frame_y)


def _apply_main_min_max(style, main_base, main_size, column):
    """对主轴尺寸应用 min/max 约束。"""
    if style is None:
        return main_base
    if column:
        min_v = style.get("minHeight")
        max_v = style.get("maxHeight")
    else:
        min_v = style.get("minWidth")
        max_v = style.get("maxWidth")
    if min_v is not None:
        mn, explicit = _parse_dimension(min_v, main_size, 0.0)
        if explicit and main_base < mn:
            main_base = mn
    if max_v is not None:
        mx, explicit = _parse_dimension(max_v, main_size, 0.0)
        if explicit and main_base > mx:
            main_base = mx
    return main_base


def _apply_cross_min_max(style, cross_base, cross_size, column):
    """对交叉轴尺寸应用 min/max 约束。"""
    if style is None:
        return cross_base
    if column:
        min_v = style.get("minWidth")
        max_v = style.get("maxWidth")
    else:
        min_v = style.get("minHeight")
        max_v = style.get("maxHeight")
    if min_v is not None:
        mn, explicit = _parse_dimension(min_v, cross_size, 0.0)
        if explicit and cross_base < mn:
            cross_base = mn
    if max_v is not None:
        mx, explicit = _parse_dimension(max_v, cross_size, 0.0)
        if explicit and cross_base > mx:
            cross_base = mx
    return cross_base


def _apply_relative_offset(style, box, parent_w, parent_h):
    """position:relative 偏移自身视觉位置，不影响兄弟布局。"""
    if style is None:
        return box
    x, y, w, h = box
    left_v = style.get("left") if style.has("left") else None
    right_v = style.get("right") if style.has("right") else None
    top_v = style.get("top") if style.has("top") else None
    bottom_v = style.get("bottom") if style.has("bottom") else None
    if left_v is not None:
        lv, _ = _parse_dimension(left_v, parent_w, 0.0)
        x += lv
    elif right_v is not None:
        rv, _ = _parse_dimension(right_v, parent_w, 0.0)
        x -= rv
    if top_v is not None:
        tv, _ = _parse_dimension(top_v, parent_h, 0.0)
        y += tv
    elif bottom_v is not None:
        bv, _ = _parse_dimension(bottom_v, parent_h, 0.0)
        y -= bv
    return (x, y, w, h)


# ---------------------------------------------------------------------------
# apply
# ---------------------------------------------------------------------------

def apply(node, host, parent_abs_x=0.0, parent_abs_y=0.0,
          parent_scale_x=1.0, parent_scale_y=1.0):
    """把 frame 应用到原生控件。

    所有控件（含 auto 叶子）都 SetSize：auto 叶子的原生尺寸可能为 0（引擎未
    自动量测），需用 measure_text 量得的尺寸显式设置，否则不可见。

    透明度：propagate_alpha 恒为 false，由 pyreact 计算每个控件独立 alpha：
    最终 alpha = inherited_opacity（沿 fiber 树累计，含组件）* color.alpha
    （若该控件的 props 提供了 Color 对象的 color 属性）。

    transform（translate/scale）在布局 frame 之外叠加，不改变逻辑布局流。
    scale 会沿原生子树传递，子控件的视觉 frame 按父级 scale 同步，确保
    文字和背景等内部元素作为整体缩放。
    """
    from .style import resolve_transform

    node.fiber.primitive_state["_inherited_opacity"] = node.inherited_opacity
    # 先比较 frame 签名，避免未变化节点仍调用昂贵的 GetBaseUIControl。
    color_alpha = _color_alpha(node.fiber)
    base_rx = node.frame_x - parent_abs_x
    base_ry = node.frame_y - parent_abs_y
    tx, ty, sx, sy, ox, oy = resolve_transform(node.fiber.style)
    node.visual_scale_x = parent_scale_x * sx
    node.visual_scale_y = parent_scale_y * sy
    node.fiber.primitive_state["_visual_scale"] = (
        node.visual_scale_x, node.visual_scale_y)
    base_draw_w = node.frame_w * parent_scale_x
    base_draw_h = node.frame_h * parent_scale_y
    draw_w = base_draw_w * sx
    draw_h = base_draw_h * sy
    relative_x = (base_rx + tx) * parent_scale_x + (
        base_draw_w - draw_w) * ox
    relative_y = (base_ry + ty) * parent_scale_y + (
        base_draw_h - draw_h) * oy
    adjust_visual_size = getattr(
        node.fiber.comp_type, "adjust_visual_size", None)
    if callable(adjust_visual_size):
        draw_w, draw_h = adjust_visual_size(
            draw_w, draw_h,
            node.visual_scale_x, node.visual_scale_y)
    applied = (draw_w, draw_h, relative_x, relative_y,
               node.inherited_opacity * color_alpha)
    previous = node.fiber.primitive_state.get("_layout_applied")
    custom_layout = node.fiber.primitive_state.get("_has_custom_apply_layout")
    control = None
    if previous != applied or custom_layout:
        control = native.get_control(host, node.fiber.native_path)
    if control is not None:
        node.fiber.primitive_state["_native_color_alpha"] = applied[4]
        # 始终记录布局基点与基准尺寸，供 visual-only 快速路径叠加 transform
        node.fiber.primitive_state["_layout_base_pos"] = (base_rx, base_ry)
        node.fiber.primitive_state["_layout_base_size"] = (
            node.frame_w, node.frame_h)
        node.fiber.primitive_state["_layout_parent_scale"] = (
            parent_scale_x, parent_scale_y)
        if previous != applied:
            native.set_size(control, (draw_w, draw_h))
            # 位置：相对原生父控件（其绝对左上 = parent_abs）+ transform
            control.SetPosition((relative_x, relative_y))
            control.SetAlpha(applied[4])
            node.fiber.primitive_state["_layout_applied"] = applied
            # 同步“铺满”型模板子控件（如按钮背景图），SDK 默认不会随父尺寸重算
            inherit_fill_alpha = getattr(
                node.fiber.comp_type, "fill_children_inherit_alpha", True)
            for fill_path in node.fiber.primitive_state.get("_fill_children", ()):
                fc = native.get_control(host, fill_path)
                if fc is not None:
                    native.set_size(fc, (draw_w, draw_h))
                    fc.SetPosition((0.0, 0.0))
                    if inherit_fill_alpha:
                        fc.SetAlpha(applied[4])
            apply_visual_scale = getattr(
                node.fiber.comp_type, "apply_visual_scale", None)
            if callable(apply_visual_scale):
                apply_visual_scale(
                    host, node.fiber, control,
                    node.visual_scale_x, node.visual_scale_y)
        if custom_layout:
            node.fiber.comp_type.apply_layout(host, node)

    if node.fiber.primitive_state.get("_has_custom_apply_children"):
        if node.fiber.comp_type.apply_children(host, node, apply):
            return
    for child in node.children:
        apply(child, host, node.frame_x, node.frame_y,
              node.visual_scale_x, node.visual_scale_y)


def _color_alpha(fiber):
    """取该控件 props 中 color 属性的 alpha（Color 对象），无则 1.0。"""
    color = fiber.props.get("color") if fiber.props else None
    if color is None:
        color = fiber.last_props.get("color") if fiber.last_props else None
    if isinstance(color, Color):
        return color.a
    return 1.0


# ---------------------------------------------------------------------------
# 对外入口
# ---------------------------------------------------------------------------

def layout_tree(root_fiber, host, root_path):
    """构建布局树、量测、布局、应用。返回 (ready, nodes)。

    ready 为 True 表示已成功应用布局，nodes 为根 LayoutNode 列表（debug
    快照用，debug 模式下 host._debug_layout_nodes 保留引用）。ready 为 False
    时 nodes 为 None，由调用方下一帧重试。

    root_path 为根容器（/root）路径。
    """
    host._layout_screen_flushed = False
    nodes = build_layout_tree(root_fiber)
    if not nodes:
        return True, None
    # 根内容盒 = /root 的像素尺寸，左上角 (0,0)
    rw, rh = native.get_size(host, root_path)
    if rw <= 0 or rh <= 0:
        return False, None

    # 先量测所有节点，并保存第一轮结果。第二轮只在原生刷新后量测结果
    # 发生变化时执行，避免每次提交无条件重复整棵树的 layout/apply。
    for node in nodes:
        measure(node, host, True)

    # 若有文本叶子尚未量测出尺寸，跳过本次布局，等下帧重试
    for node in nodes:
        if _has_unmeasured_text(node):
            return False, None

    # 第一遍布局：用 measure_text/get_size 的量测值算 frame 并应用
    _layout_and_apply(nodes, rw, rh, host)
    # 应用后刷新，让原生控件按新尺寸渲染
    native.update_screen(host, True)
    if not any(_needs_post_measure(node) for node in nodes):
        host._layout_screen_flushed = True
        return True, nodes
    # 第二遍：重新量测（此时 auto 容器/ItemRenderer 等可能已获得真实渲染尺寸），
    # 再算 frame 并应用。解决切换 tab 后行高基于旧尺寸、导致行重叠的问题。
    measurements_changed = False
    for node in nodes:
        if measure(node, host):
            measurements_changed = True
    if measurements_changed:
        _layout_and_apply(nodes, rw, rh, host)
    else:
        # 第一轮应用后的刷新已经提交了最终 frame；宿主无需再刷新一次。
        host._layout_screen_flushed = True
    return True, nodes


def _layout_and_apply(nodes, rw, rh, host):
    """对根 LayoutNode 列表执行 layout + apply。"""
    host._layout_text_remeasured = False
    _layout_nodes(nodes, rw, rh, host)
    if host._layout_text_remeasured:
        # row flex 文本的约束宽度只有主轴求解后才知道。若换行高度变化，
        # 在 apply 前重新汇总 auto 容器，避免首帧使用旧的单行高度。
        for node in nodes:
            measure(node, host)
        host._layout_text_remeasured = False
        _layout_nodes(nodes, rw, rh, host)
    for node in nodes:
        apply(node, host, 0.0, 0.0)


def _layout_nodes(nodes, rw, rh, host):
    """只计算根布局，不访问目标原生控件。"""
    offset = 0.0
    for node in nodes:
        box = (0.0, offset, rw, rh)
        layout(node, box, host)
        offset += node.frame_h
