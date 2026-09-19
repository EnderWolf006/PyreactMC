# -*- coding: utf-8 -*-
"""Renderer：把 Style 的视觉部分应用到原生控件。

尺寸/位置由 layout 引擎负责；透明度需沿 fiber 树继承，通常在 layout.apply
中设置。本模块处理可见性、层级，以及 **visual-only 快速路径** 下的 alpha /
transform（不重跑整棵布局树）。

各 Primitive 的原生属性（text/texture/color 等）由其自身 ``apply_props`` 处理。
"""
from . import native
from .constants import Color, Display
from .style import resolve_transform


_Z_INDEX_UNSET = object()


def resolve_visible(style):
    """解析 Style 对应的最终 visible 值。"""
    visible = True
    if style is not None and style.has("display") and style.get("display") == Display.none:
        visible = False
    if style is not None and style.has("visible"):
        visible = visible and bool(style.get("visible"))
    return visible


def apply_style(host, fiber, control, style, visible=None):
    """应用通用视觉属性（visible / zIndex）。

    透明度与 transform 由 layout.apply（全量布局）或
    ``apply_visual_fast``（visual-only）负责，避免与布局 frame 签名冲突。
    """
    if control is None:
        return
    if visible is None:
        visible = resolve_visible(style)
    previous_visible = fiber.primitive_state.get("_visible")
    if previous_visible is None or previous_visible != visible:
        native.set_visible(control, visible)
        fiber.primitive_state["_visible"] = visible

    has_z_index = style is not None and style.has("zIndex")
    previous_z_index = fiber.primitive_state.get(
        "_z_index", _Z_INDEX_UNSET)
    if has_z_index:
        z_index = style.get("zIndex")
    elif previous_z_index is not _Z_INDEX_UNSET:
        # zIndex 从显式值变回未设置时，恢复 Primitive 模板默认层级。
        z_index = 1
    else:
        z_index = _Z_INDEX_UNSET
    if z_index is not _Z_INDEX_UNSET and previous_z_index != z_index:
        try:
            native.set_layer(control, z_index)
            fiber.primitive_state["_z_index"] = z_index
        except (TypeError, ValueError):
            pass


def apply_visual_fast(host, fiber):
    """仅更新 opacity / transform，不重建布局树。

    要求 fiber 此前已通过 layout.apply 写入过 ``_layout_applied`` 与
    ``_layout_base_pos``。父级累计 opacity 从父 primitive 的
    ``_inherited_opacity`` 推导。

    opacity 变化时会沿子树刷新继承 alpha（仍跳过 measure/layout）。
    transform 不改变逻辑布局原点；scale 通过 SetSize + origin 位置矫正
    实现，并把视觉缩放同步到所有原生子控件。
    """
    applied = fiber.primitive_state.get("_layout_applied")
    base_pos = fiber.primitive_state.get("_layout_base_pos")
    base_size = fiber.primitive_state.get("_layout_base_size")
    if applied is None or base_pos is None or base_size is None:
        # 尚未布局完成：退回全量布局
        host._commit_layout_dirty = True
        return False

    base_w, base_h = base_size
    base_rx, base_ry = base_pos
    _old_alpha = applied[4]
    prev_inherited = fiber.primitive_state.get("_inherited_opacity")
    parent_opacity = _parent_inherited_opacity(fiber)
    own_opacity = _style_opacity_value(fiber.style)
    inherited = parent_opacity * own_opacity
    color_alpha = _color_alpha(fiber)
    final_alpha = inherited * color_alpha
    tx, ty, sx, sy, ox, oy = resolve_transform(fiber.style)
    parent_sx, parent_sy = _parent_visual_scale(fiber)
    visual_scale = (parent_sx * sx, parent_sy * sy)
    base_draw_w = base_w * parent_sx
    base_draw_h = base_h * parent_sy
    draw_w = base_draw_w * sx
    draw_h = base_draw_h * sy
    relative_x = (base_rx + tx) * parent_sx + (
        base_draw_w - draw_w) * ox
    relative_y = (base_ry + ty) * parent_sy + (
        base_draw_h - draw_h) * oy
    draw_w, draw_h = _adjust_visual_size(
        fiber, draw_w, draw_h, visual_scale[0], visual_scale[1])

    new_applied = (draw_w, draw_h, relative_x, relative_y, final_alpha)
    opacity_changed = (prev_inherited is None or prev_inherited != inherited
                       or final_alpha != _old_alpha)
    if applied == new_applied and not opacity_changed:
        return True

    control = native.get_control(host, fiber.native_path)
    if control is None:
        host._commit_layout_dirty = True
        return False

    fiber.primitive_state["_inherited_opacity"] = inherited
    fiber.primitive_state["_native_color_alpha"] = final_alpha
    old_visual_scale = fiber.primitive_state.get("_visual_scale")
    fiber.primitive_state["_layout_parent_scale"] = (parent_sx, parent_sy)
    fiber.primitive_state["_visual_scale"] = visual_scale
    prev_w, prev_h = applied[0], applied[1]
    prev_rx, prev_ry = applied[2], applied[3]
    size_changed = draw_w != prev_w or draw_h != prev_h
    if size_changed:
        native.set_size(control, (draw_w, draw_h))
    if relative_x != prev_rx or relative_y != prev_ry:
        control.SetPosition((relative_x, relative_y))
    inherit_fill_alpha = getattr(
        fiber.comp_type, "fill_children_inherit_alpha", True)
    if final_alpha != _old_alpha or size_changed:
        for fill_path in fiber.primitive_state.get("_fill_children", ()):
            fc = native.get_control(host, fill_path)
            if fc is None:
                continue
            if size_changed:
                native.set_size(fc, (draw_w, draw_h))
            if final_alpha != _old_alpha and inherit_fill_alpha:
                fc.SetAlpha(final_alpha)
    if final_alpha != _old_alpha:
        control.SetAlpha(final_alpha)
    fiber.primitive_state["_layout_applied"] = new_applied
    _apply_visual_scale(
        host, fiber, control, visual_scale[0], visual_scale[1])

    # Button 等自定义 apply_layout 可能依赖 inherited opacity
    if fiber.primitive_state.get("_has_custom_apply_layout"):
        _apply_custom_layout_visual(host, fiber, inherited)

    # 父 opacity 变化时，子树继承 alpha 也需同步（无需 re-measure）
    if opacity_changed:
        _refresh_subtree_opacity(host, fiber, inherited)
    if old_visual_scale != visual_scale:
        _refresh_subtree_transform(host, fiber, visual_scale[0], visual_scale[1])

    host._commit_native_dirty = True
    return True


def _refresh_subtree_opacity(host, parent_fiber, parent_inherited):
    """按 parent_inherited 刷新 parent 下所有 primitive 的继承 alpha。"""
    for child in parent_fiber.child_fibers:
        _refresh_fiber_opacity(host, child, parent_inherited)


def _refresh_subtree_transform(host, parent_fiber, parent_sx, parent_sy):
    """父级 scale 变化时同步子树视觉 frame，不触发逻辑 layout。"""
    for child in parent_fiber.child_fibers:
        _refresh_fiber_transform(host, child, parent_sx, parent_sy)


def _refresh_fiber_transform(host, fiber, parent_sx, parent_sy):
    if fiber.is_component:
        for child in fiber.child_fibers:
            _refresh_fiber_transform(host, child, parent_sx, parent_sy)
        return
    applied = fiber.primitive_state.get("_layout_applied")
    base_pos = fiber.primitive_state.get("_layout_base_pos")
    base_size = fiber.primitive_state.get("_layout_base_size")
    if applied is None or base_pos is None or base_size is None:
        return
    base_w, base_h = base_size
    base_rx, base_ry = base_pos
    tx, ty, sx, sy, ox, oy = resolve_transform(fiber.style)
    visual_scale = (parent_sx * sx, parent_sy * sy)
    base_draw_w = base_w * parent_sx
    base_draw_h = base_h * parent_sy
    draw_w = base_draw_w * sx
    draw_h = base_draw_h * sy
    relative_x = (base_rx + tx) * parent_sx + (
        base_draw_w - draw_w) * ox
    relative_y = (base_ry + ty) * parent_sy + (
        base_draw_h - draw_h) * oy
    draw_w, draw_h = _adjust_visual_size(
        fiber, draw_w, draw_h, visual_scale[0], visual_scale[1])
    final_alpha = applied[4]
    next_applied = (draw_w, draw_h, relative_x, relative_y, final_alpha)
    control = native.get_control(host, fiber.native_path)
    if control is not None and applied != next_applied:
        if applied[0] != draw_w or applied[1] != draw_h:
            native.set_size(control, (draw_w, draw_h))
        if applied[2] != relative_x or applied[3] != relative_y:
            control.SetPosition((relative_x, relative_y))
        inherit_fill_alpha = getattr(
            fiber.comp_type, "fill_children_inherit_alpha", True)
        for fill_path in fiber.primitive_state.get("_fill_children", ()):
            fill = native.get_control(host, fill_path)
            if fill is not None:
                native.set_size(fill, (draw_w, draw_h))
                fill.SetPosition((0.0, 0.0))
                if inherit_fill_alpha:
                    fill.SetAlpha(final_alpha)
        fiber.primitive_state["_layout_applied"] = next_applied
        if fiber.primitive_state.get("_has_custom_apply_layout"):
            _apply_custom_layout_visual(host, fiber,
                                        fiber.primitive_state.get(
                                            "_inherited_opacity", 1.0))
    fiber.primitive_state["_layout_parent_scale"] = (parent_sx, parent_sy)
    fiber.primitive_state["_visual_scale"] = visual_scale
    if control is not None:
        _apply_visual_scale(
            host, fiber, control, visual_scale[0], visual_scale[1])
    _refresh_subtree_transform(host, fiber, visual_scale[0], visual_scale[1])


def _refresh_fiber_opacity(host, fiber, parent_opacity):
    if fiber.is_component:
        # 组件自身 style 恒为 None，透传 parent_opacity
        for child in fiber.child_fibers:
            _refresh_fiber_opacity(host, child, parent_opacity)
        return
    applied = fiber.primitive_state.get("_layout_applied")
    if applied is None:
        return
    own = _style_opacity_value(fiber.style)
    inherited = parent_opacity * own
    color_alpha = _color_alpha(fiber)
    final_alpha = inherited * color_alpha
    base_w, base_h, rx, ry, old_alpha = applied
    fiber.primitive_state["_inherited_opacity"] = inherited
    fiber.primitive_state["_native_color_alpha"] = final_alpha
    if final_alpha != old_alpha:
        control = native.get_control(host, fiber.native_path)
        if control is not None:
            control.SetAlpha(final_alpha)
            inherit_fill_alpha = getattr(
                fiber.comp_type, "fill_children_inherit_alpha", True)
            if inherit_fill_alpha:
                for fill_path in fiber.primitive_state.get("_fill_children", ()):
                    fc = native.get_control(host, fill_path)
                    if fc is not None:
                        fc.SetAlpha(final_alpha)
        fiber.primitive_state["_layout_applied"] = (
            base_w, base_h, rx, ry, final_alpha)
        if fiber.primitive_state.get("_has_custom_apply_layout"):
            _apply_custom_layout_visual(host, fiber, inherited)
    for child in fiber.child_fibers:
        _refresh_fiber_opacity(host, child, inherited)


def _apply_custom_layout_visual(host, fiber, inherited_opacity):
    """为有 apply_layout 钩子的 Primitive 同步 visual 相关状态。

    构造最小 node 对象，避免依赖完整 LayoutNode。
    """
    class _MiniNode(object):
        pass

    applied = fiber.primitive_state.get("_layout_applied")
    if applied is None:
        return
    node = _MiniNode()
    node.fiber = fiber
    node.frame_w = applied[0]
    node.frame_h = applied[1]
    node.frame_x = 0.0
    node.frame_y = 0.0
    node.inherited_opacity = inherited_opacity
    try:
        fiber.comp_type.apply_layout(host, node)
    except Exception:
        pass


def _parent_inherited_opacity(fiber):
    """父级累计 opacity（不含本 fiber）。"""
    parent = fiber.parent_fiber
    while parent is not None:
        if parent.is_primitive:
            value = parent.primitive_state.get("_inherited_opacity")
            if value is not None:
                return value
            # 未缓存时按 1.0（layout 前不应走 visual-fast）
            return 1.0
        # 组件节点：其自身 opacity 已在 layout 时乘入子树；
        # visual-only 变更不会改组件 opacity（组件无 native style 承载）。
        parent = parent.parent_fiber
    return 1.0


def _parent_visual_scale(fiber):
    """取得最近原生父控件的累计视觉 scale。"""
    parent = fiber.parent_fiber
    while parent is not None:
        if parent.is_primitive:
            return parent.primitive_state.get("_visual_scale", (1.0, 1.0))
        parent = parent.parent_fiber
    return (1.0, 1.0)


def _apply_visual_scale(host, fiber, control, scale_x, scale_y):
    """调用 Primitive 可选的视觉缩放同步钩子。"""
    callback = getattr(fiber.comp_type, "apply_visual_scale", None)
    if callable(callback):
        callback(host, fiber, control, scale_x, scale_y)


def _adjust_visual_size(fiber, width, height, scale_x, scale_y):
    """应用 Primitive 可选的 native 绘制尺寸补偿。"""
    callback = getattr(fiber.comp_type, "adjust_visual_size", None)
    if callable(callback):
        return callback(width, height, scale_x, scale_y)
    return (width, height)


def _style_opacity_value(style):
    if style is not None and style.has("opacity"):
        op = style.get("opacity")
        if op is not None:
            return max(0.0, min(1.0, float(op)))
    return 1.0


def _color_alpha(fiber):
    color = to_color(fiber.props.get("color") if fiber.props else None)
    if color is not None:
        return color.a
    return 1.0


def to_color(value):
    """把 Color / 元组 / int 统一转成 Color。"""
    if value is None:
        return None
    if isinstance(value, Color):
        return value
    if isinstance(value, (int, long)):
        return Color(value)
    if isinstance(value, (list, tuple)):
        if len(value) == 3:
            return Color(value[0], value[1], value[2])
        if len(value) == 4:
            return Color(value[0], value[1], value[2], value[3])
    return None
