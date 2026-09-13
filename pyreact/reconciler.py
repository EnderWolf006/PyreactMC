# -*- coding: utf-8 -*-
"""Reconciler：虚拟 DOM 与 diff 算法。

维护一棵 Fiber 树，镜像当前组件/元素树。渲染流程参考 React：
mount 创建原生控件、update 只 patch 变化项、unmount 移除控件。
组件 Fiber 不持有原生控件（透明），其子 Fiber 挂到最近的 primitive 父路径下。
"""
from . import hooks
from . import native
from .element import Element, normalize_children
from .primitives import Primitive

# 全局自增计数器，用于生成唯一的原生控件名（稳定存储在 Fiber 上）
_name_counter = [0]
_primitive_capability_cache = {}


def _next_name(key):
    _name_counter[0] += 1
    uid = _name_counter[0]
    if key is not None:
        return native.sanitize_name(key) + ("__%d" % uid)
    return "__pyr_%d" % uid


class Fiber(object):
    """组件实例 / 宿主节点。"""

    __slots__ = (
        "comp_type", "key", "ref",
        "props", "style", "children_elements",
        "native_path", "native_parent_path", "native_name",
        "child_fibers", "element",
        "hooks", "hook_index", "has_pending_effects",
        "dirty", "parent_fiber", "host",
        "last_props", "last_style", "primitive_state", "_mounted",
        "_is_component", "_is_primitive",
        "_children_native_parent_path",
    )

    def __init__(self, element, host):
        self.comp_type = element.comp_type
        self.key = element.key
        self.ref = element.ref
        self.props = element.props
        self.style = element.style
        self.children_elements = element.children
        self.native_path = None
        self.native_parent_path = None
        self.native_name = None
        self.child_fibers = []
        self.element = element
        self.hooks = []
        self.hook_index = 0
        self.has_pending_effects = False
        self.dirty = False
        self.parent_fiber = None
        self.host = host
        self.last_props = None
        self.last_style = None
        self.primitive_state = {}
        self._mounted = False
        self._children_native_parent_path = None
        self._is_component = callable(self.comp_type) and getattr(
            self.comp_type, "_is_pyreact_component", False)
        if self._is_component:
            self._is_primitive = False
        else:
            self._is_primitive = isinstance(self.comp_type, Primitive)

    @property
    def is_component(self):
        return self._is_component

    @property
    def is_primitive(self):
        return self._is_primitive


def create_fiber(element, host):
    return Fiber(element, host)


def _same_type(fiber, element):
    ft = fiber.comp_type
    et = element.comp_type
    if ft is et:
        return True
    # Primitive 实例：按类比较，避免每次 new 实例导致 diff 失效
    if isinstance(ft, Primitive) and isinstance(et, Primitive):
        return type(ft) is type(et)
    return False


def _primitive_capabilities(primitive_class):
    """返回 Primitive 类的自定义 layout/children 钩子能力。"""
    cached = _primitive_capability_cache.get(primitive_class)
    if cached is not None:
        return cached
    result = []
    for method_name in ("apply_layout", "apply_children"):
        overridden = False
        for owner in primitive_class.__mro__:
            if method_name in owner.__dict__:
                overridden = owner is not Primitive
                break
        result.append(overridden)
    cached = tuple(result)
    _primitive_capability_cache[primitive_class] = cached
    return cached


# ---------------------------------------------------------------------------
# mount
# ---------------------------------------------------------------------------

def mount_fiber(fiber, native_parent_path, host):
    """挂载一个 Fiber。native_parent_path 为其原生控件/子控件应挂载的父路径。"""
    fiber.native_parent_path = native_parent_path
    if fiber.is_component:
        _mount_component(fiber, native_parent_path, host)
    else:
        _mount_primitive(fiber, native_parent_path, host)
    fiber._mounted = True


def _mount_component(fiber, native_parent_path, host):
    output = _render_component(fiber)
    output_list = _normalize_output(output)
    fiber.child_fibers = [create_fiber(e, host) for e in output_list]
    for cf in fiber.child_fibers:
        cf.parent_fiber = fiber
        mount_fiber(cf, native_parent_path, host)


def _mount_primitive(fiber, native_parent_path, host):
    host._commit_native_dirty = True
    host._commit_layout_dirty = True
    fiber.native_name = _next_name(fiber.key)
    native_path = native.join_path(native_parent_path, fiber.native_name)
    fiber.native_path = native_path
    primitive_class = type(fiber.comp_type)
    custom_layout, custom_children = _primitive_capabilities(primitive_class)
    fiber.primitive_state["_has_custom_apply_layout"] = custom_layout
    fiber.primitive_state["_has_custom_apply_children"] = custom_children
    fiber.primitive_state["_fill_children"] = tuple(
        fiber.comp_type.fill_children(native_path))
    # 克隆模板创建原生控件
    native.clone(host, fiber.comp_type.template_path, native_parent_path, fiber.native_name)
    control = native.get_control(host, native_path)
    # 应用样式视觉 + 原生属性
    from . import renderer
    renderer.apply_style(host, fiber, control, fiber.style)
    fiber.comp_type.apply_props(host, fiber, control, None, fiber.props)
    # Element 是不可变描述，保留当前 props 引用作为下一次 diff 快照。
    fiber.last_props = fiber.props
    fiber.last_style = fiber.style
    # ref
    _attach_ref(fiber, control)
    # 子控件挂载到 children_path（默认即 native_path）
    children_parent = fiber.comp_type.children_path(native_path, host)
    fiber._children_native_parent_path = children_parent
    for i, child_el in enumerate(fiber.children_elements):
        cf = create_fiber(child_el, host)
        cf.parent_fiber = fiber
        fiber.child_fibers.append(cf)
        mount_fiber(cf, children_parent, host)


def _render_component(fiber):
    """调用组件的渲染函数（带 hook 上下文）。"""
    fiber.hook_index = 0
    fiber.has_pending_effects = False
    hooks.push_fiber(fiber)
    try:
        output = fiber.comp_type._render(**fiber.props)
    finally:
        hooks.pop_fiber()
    fiber.dirty = False
    return output


def _normalize_output(output):
    if output is None:
        return []
    if isinstance(output, Element):
        return [output]
    if isinstance(output, (list, tuple)):
        return normalize_children(output)
    # 标量 -> 文本
    return normalize_children(output)


def _attach_ref(fiber, control):
    ref = fiber.ref
    if ref is None:
        return
    if callable(ref):
        ref(control)
    else:
        try:
            ref.current = control
        except Exception:
            pass


# ---------------------------------------------------------------------------
# update / reconcile
# ---------------------------------------------------------------------------

def update_fiber(fiber, element, host):
    """用新 element 更新已挂载的 fiber（同类型）。"""
    fiber.element = element
    fiber.props = element.props
    fiber.style = element.style
    fiber.children_elements = element.children
    fiber.key = element.key
    if fiber.is_component:
        _update_component(fiber, host)
    else:
        _update_primitive(fiber, host)


def _update_component(fiber, host):
    # props 变化或 dirty 都需要重渲染
    if fiber.dirty or _props_changed(fiber.last_props, fiber.props):
        output = _render_component(fiber)
        output_list = _normalize_output(output)
        if fiber.child_fibers or output_list:
            reconcile_children(fiber, output_list, host)
    fiber.last_props = fiber.props


def _update_primitive(fiber, host):
    from . import renderer
    from .style import (
        style_layout_changed, style_visual_changed, style_paint_changed,
    )
    props_changed = _props_changed(fiber.last_props, fiber.props)
    style_changed = _style_changed(fiber.last_style, fiber.style)
    layout_changed = style_layout_changed(fiber.last_style, fiber.style)
    visual_changed = style_visual_changed(fiber.last_style, fiber.style)
    # opacity / transform：可走 visual-fast 而不触发 measure/layout
    paint_changed = style_paint_changed(fiber.last_style, fiber.style)
    visible = renderer.resolve_visible(fiber.style)
    visibility_changed = fiber.primitive_state.get("_visible") != visible
    if props_changed or visibility_changed or style_changed:
        control = native.get_control(host, fiber.native_path)
    else:
        control = None
    if visibility_changed or visual_changed:
        # visible / zIndex 走 apply_style；opacity / transform 见 paint 路径
        renderer.apply_style(host, fiber, control, fiber.style, visible)
        host._commit_native_dirty = True
    if props_changed:
        fiber.comp_type.apply_props(host, fiber, control, fiber.last_props, fiber.props)
        host._commit_native_dirty = True
        if fiber.comp_type.props_affect_layout(
                fiber.last_props, fiber.props, fiber.style):
            host._commit_layout_dirty = True
    if layout_changed:
        # 布局字段变化：整树 layout（同时会写回 alpha / transform）
        host._commit_layout_dirty = True
    elif paint_changed:
        # 仅 opacity / transform：跳过 measure/layout，直接写 native
        if not renderer.apply_visual_fast(host, fiber):
            host._commit_layout_dirty = True
    fiber.last_props = fiber.props
    fiber.last_style = fiber.style
    # 子节点 diff
    if fiber.child_fibers or fiber.children_elements:
        reconcile_children(fiber, fiber.children_elements, host)


def reconcile_children(fiber, next_elements, host):
    """按 key 对齐 prev child_fibers 与 next_elements，做增/删/更新。

    next_elements 已是归一化后的 list[Element]。
    """
    prev = fiber.child_fibers
    if not prev and not next_elements:
        return
    prev_map = {}
    for i, cf in enumerate(prev):
        k = cf.key if cf.key is not None else i
        prev_map[k] = cf

    used = set()
    new_children = []
    for i, el in enumerate(next_elements):
        k = el.key if el.key is not None else i
        cf = prev_map.get(k)
        if cf is not None and cf not in used and _same_type(cf, el):
            used.add(cf)
            update_fiber(cf, el, host)
            new_children.append(cf)
        else:
            cf = create_fiber(el, host)
            cf.parent_fiber = fiber
            new_children.append(cf)

    # 卸载未复用的
    for cf in prev:
        if cf not in used:
            unmount_fiber(cf, host)

    # 挂载新创建的（按出现顺序，使用 fiber 的子挂载父路径）
    children_parent = _children_parent_path(fiber)
    for cf in new_children:
        if not cf._mounted:
            mount_fiber(cf, children_parent, host)

    if len(prev) == len(new_children):
        for index, cf in enumerate(prev):
            if cf is not new_children[index]:
                host._commit_layout_dirty = True
                break

    fiber.child_fibers = new_children


def _children_parent_path(fiber):
    """fiber 的子控件应挂载到的原生父路径。"""
    if fiber._children_native_parent_path is not None:
        return fiber._children_native_parent_path
    if fiber.is_primitive:
        result = fiber.comp_type.children_path(fiber.native_path, fiber.host)
    else:
        # 组件透明：用其 native_parent_path
        result = fiber.native_parent_path
    fiber._children_native_parent_path = result
    return result


def _props_changed(prev, nxt):
    if prev is None:
        return True
    if prev is nxt:
        return False
    if len(prev) != len(nxt):
        return True
    for k, value in prev.iteritems():
        if k not in nxt or value != nxt[k]:
            return True
    return False


def _style_changed(prev, nxt):
    if prev is nxt:
        return False
    if prev is None or nxt is None:
        return True
    equals = getattr(prev, "equals", None)
    if callable(equals):
        return not equals(nxt)
    return prev != nxt


# ---------------------------------------------------------------------------
# unmount
# ---------------------------------------------------------------------------

def unmount_fiber(fiber, host, remove_native=True):
    """卸载 Fiber，并尽量只删除每个原生子树的根控件。

    RemoveChildControl 删除父控件时会同时移除其原生子树；逐个删除后代
    会把一次 tab 切换放大成几十次昂贵的 SDK 路径/布局更新。这里仍递归
    执行 hooks、事件和 ref 清理，但由父 Primitive 负责一次原生删除。
    """
    if remove_native:
        host._commit_native_dirty = True
        host._commit_layout_dirty = True
    if fiber.is_component:
        hooks.run_cleanup(fiber)
        for cf in fiber.child_fibers:
            unmount_fiber(cf, host, remove_native)
    else:
        # 卸载子控件
        for cf in fiber.child_fibers:
            unmount_fiber(cf, host, False)
        # 移除自身原生控件
        if remove_native:
            control = native.get_control(host, fiber.native_path)
            native.remove(host, control)
        fiber.comp_type.unmount(host, fiber)
        _attach_ref(fiber, None)
    fiber._mounted = False


# ---------------------------------------------------------------------------
# 重渲染入口（供宿主在 setState 后调用）
# ---------------------------------------------------------------------------

def rerender_component(fiber, host):
    """重新渲染一个 dirty 的组件 fiber 并 reconcile 其输出。"""
    output = _render_component(fiber)
    output_list = _normalize_output(output)
    reconcile_children(fiber, output_list, host)
    fiber.last_props = fiber.props
