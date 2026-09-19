# -*- coding: utf-8 -*-
"""Hooks，行为与 React 保持一致。

实现要点：每个组件 Fiber 持有一个 ``hooks`` 列表与一个每次渲染重置的
``hook_index``。渲染组件前由 reconciler 把该 Fiber 压入 ``_current_fiber``
栈，hook 按调用顺序读写对应槽位，从而在多次渲染间保持状态。
"""

import traceback

# 渲染上下文栈
_current_fiber_stack = []

# “尚无上一次依赖”的哨兵
_NO_DEPS = object()
_STATE_SCALAR_TYPES = (type(None), bool, int, long, float, basestring)


class RefObject(object):
    """稳定的可变引用对象，更新 ``current`` 不触发重渲染。"""

    __slots__ = ("current",)

    def __init__(self, current=None):
        self.current = current


class _EventListener(object):
    """稳定的 ModSDK 事件转发对象，始终调用本轮渲染的 callback。"""

    __slots__ = ("callback",)

    def __init__(self):
        self.callback = None

    def dispatch(self, args=None):
        callback = self.callback
        if callable(callback):
            callback(args)


def _current_fiber():
    if not _current_fiber_stack:
        raise RuntimeError("pyreact hook called outside of a component render")
    return _current_fiber_stack[-1]


def push_fiber(fiber):
    _current_fiber_stack.append(fiber)


def pop_fiber():
    _current_fiber_stack.pop()


def _next_slot(fiber, default_factory):
    """按 hook_index 取/建槽位，并自增索引。"""
    idx = fiber.hook_index
    fiber.hook_index += 1
    while len(fiber.hooks) <= idx:
        fiber.hooks.append(default_factory())
    slot = fiber.hooks[idx]
    return slot


def _deps_changed(prev_deps, next_deps):
    """依赖比较：None 表示每次都变；元组逐项比较。"""
    if next_deps is None:
        return True
    if prev_deps is _NO_DEPS:
        return True
    if prev_deps is None:
        return True
    if len(prev_deps) != len(next_deps):
        return True
    for a, b in zip(prev_deps, next_deps):
        if a != b:
            return True
    return False


def _state_value_equal(previous, next_value):
    """按 React 风格判断无需提交的 state 更新。

    对容器只使用 identity，避免 setter 热路径为了判断相等而扫描大列表；
    对不可变标量使用值比较，使重复设置同一个字符串/枚举不会触发重渲染。
    """
    if previous is next_value:
        return True
    if (isinstance(previous, _STATE_SCALAR_TYPES) and
            isinstance(next_value, _STATE_SCALAR_TYPES)):
        return previous == next_value
    return False


def use_state(initial):
    """状态 hook，返回 (value, setter)。

    setter 接受新值或接受旧值返回新值的函数（函数式更新）。
    """
    fiber = _current_fiber()

    def make_slot():
        value = initial() if callable(initial) else initial
        slot = {"type": "state", "value": value}

        def set_state(new_value):
            if callable(new_value):
                new_value = new_value(slot["value"])
            if _state_value_equal(slot["value"], new_value):
                return
            slot["value"] = new_value
            fiber.host.schedule_render(fiber)

        slot["setter"] = set_state
        return slot

    slot = _next_slot(fiber, make_slot)
    return slot["value"], slot["setter"]


def use_ref(initial=None):
    """引用 hook，返回一个 ``.current`` 可变对象。"""
    fiber = _current_fiber()

    def make_slot():
        value = initial() if callable(initial) else initial
        return {"type": "ref", "value": RefObject(value)}

    slot = _next_slot(fiber, make_slot)
    return slot["value"]


def use_effect(effect, deps=None):
    """副作用 hook。effect 在 commit 后、deps 变化时执行，可返回清理函数。"""
    fiber = _current_fiber()

    def make_slot():
        return {"type": "effect", "effect": None, "deps": _NO_DEPS,
                "cleanup": None, "dirty": False}

    slot = _next_slot(fiber, make_slot)
    if _deps_changed(slot["deps"], deps):
        slot["dirty"] = True
        fiber.has_pending_effects = True
        pending = getattr(fiber.host, "_pending_effects", None)
        if pending is not None:
            pending.add(fiber)
    slot["effect"] = effect
    slot["deps"] = deps
    return None


def use_memo(factory, deps=None):
    """记忆化 hook，deps 不变时复用上次的计算结果。"""
    fiber = _current_fiber()

    def make_slot():
        return {"type": "memo", "value": None, "deps": _NO_DEPS}

    slot = _next_slot(fiber, make_slot)
    if _deps_changed(slot["deps"], deps):
        slot["value"] = factory()
        slot["deps"] = deps
    return slot["value"]


def use_callback(callback, deps=None):
    """记忆化回调，deps 不变时返回同一函数引用。"""
    fiber = _current_fiber()

    def make_slot():
        return {"type": "callback", "value": None, "deps": _NO_DEPS}

    slot = _next_slot(fiber, make_slot)
    if _deps_changed(slot["deps"], deps):
        slot["value"] = callback
        slot["deps"] = deps
    return slot["value"]


def use_animation_frame(callback, active=True):
    """内部逐帧回调 hook，供 Animated Composite 使用。

    callback 接收当前秒级时间戳。槽位随 Fiber 卸载自动注销。
    """
    fiber = _current_fiber()

    def make_slot():
        return {"type": "animation_frame", "callback": callback,
                "active": False, "fiber": fiber}

    slot = _next_slot(fiber, make_slot)
    slot["callback"] = callback
    slot["active"] = bool(active)
    if slot["active"] and slot.get("_registration_id") is None:
        fiber.host.pyreact_register_animation_frame(slot)
    elif not slot["active"] and slot.get("_registration_id") is not None:
        fiber.host.pyreact_unregister_animation_frame(slot)
    return None


def use_event(event_name, callback, active=True, priority=0):
    """监听客户端引擎事件。

    事件来源固定为 ModSDK engine namespace/systemName，因此函数组件无需
    传入它们。callback 接收 ModSDK 原始 ``args``；其引用会在每次渲染更新，
    不会因订阅只注册一次而读取旧 state。组件卸载或订阅参数变化时自动解除。

    :param event_name: 引擎事件名，例如 ``"OnKeyPressInGame"``。
    :param callback: ``callback(args)``。
    :param active: False 时不订阅。
    :param priority: ModSDK 监听优先级，范围 0 到 10。
    """
    return _use_runtime_event(
        "engine", None, None, event_name, callback, active, priority)


def use_custom_event(namespace, system_name, event_name, callback,
                     active=True, priority=0):
    """监听指定客户端 System 广播的自定义事件。

    自定义事件的来源不一定是当前 Pyreact ClientSystem，因此必须显式传入
    发送方的 namespace 与 systemName。自定义事件应由其宿主 System 定义并
    通过 ``BroadcastEvent`` 发送。

    :param namespace: 发送方客户端 System 的 namespace。
    :param system_name: 发送方客户端 System 的 systemName。
    :param event_name: 发送方定义的事件名。
    :param callback: ``callback(args)``。
    :param active: False 时不订阅。
    :param priority: ModSDK 监听优先级，范围 0 到 10。
    """
    return _use_runtime_event(
        "custom", namespace, system_name, event_name, callback, active,
        priority)


def _use_runtime_event(source, namespace, system_name, event_name, callback,
                       active, priority):
    if not isinstance(event_name, basestring) or not event_name:
        raise TypeError("event_name must be a non-empty string")
    if source == "custom":
        if not isinstance(namespace, basestring) or not namespace:
            raise TypeError("custom event namespace must be a non-empty string")
        if not isinstance(system_name, basestring) or not system_name:
            raise TypeError("custom event system_name must be a non-empty string")
    if not callable(callback):
        raise TypeError("event callback must be callable")
    if isinstance(priority, bool):
        raise TypeError("event priority must be an integer")
    try:
        priority = int(priority)
    except (TypeError, ValueError):
        raise TypeError("event priority must be an integer")
    if priority < 0 or priority > 10:
        raise ValueError("event priority must be between 0 and 10")

    fiber = _current_fiber()
    listener = use_ref(_EventListener).current
    listener.callback = callback

    def subscribe():
        if not active:
            return None
        if source == "engine":
            return fiber.host.pyreact_listen_engine_event(
                event_name, listener, priority)
        return fiber.host.pyreact_listen_custom_event(
            namespace, system_name, event_name, listener, priority)

    use_effect(
        subscribe,
        (source, namespace, system_name, event_name, bool(active), priority),
    )
    return None


def flush_effects(fiber):
    """提交后执行该 Fiber 上所有 dirty 的 effect（递归子 Fiber）。"""
    _flush_fiber_effects(fiber)
    for child in fiber.child_fibers:
        flush_effects(child)


def flush_pending_effects(host):
    """只提交本轮依赖发生变化的 effect Fiber。"""
    pending = host._pending_effects
    host._pending_effects = set()
    for fiber in pending:
        if not fiber._mounted:
            continue
        _flush_fiber_effects(fiber)
        fiber.has_pending_effects = False


def _flush_fiber_effects(fiber):
    for slot in fiber.hooks:
        if slot.get("type") != "effect" or not slot.get("dirty"):
            continue
        # Clear before calling user code: errors must neither replay an old
        # cleanup nor discard unrelated pending subscriptions.
        slot["dirty"] = False
        cleanup = slot["cleanup"]
        slot["cleanup"] = None
        if cleanup is not None:
            try:
                cleanup()
            except Exception:
                traceback.print_exc()
        try:
            cleanup = slot["effect"]()
            slot["cleanup"] = cleanup if callable(cleanup) else None
        except Exception:
            traceback.print_exc()


def run_cleanup(fiber, recursive=True):
    """卸载时运行所有 effect 的清理函数（递归子 Fiber）。"""
    pending = getattr(fiber.host, "_pending_effects", None)
    if pending is not None:
        pending.discard(fiber)
    if fiber.hooks:
        for slot in fiber.hooks:
            if slot.get("type") == "effect" and slot["cleanup"] is not None:
                try:
                    slot["cleanup"]()
                except Exception:
                    pass
                slot["cleanup"] = None
            elif slot.get("type") == "animation_frame":
                fiber.host.pyreact_unregister_animation_frame(slot)
    if recursive:
        for child in fiber.child_fibers:
            run_cleanup(child)
