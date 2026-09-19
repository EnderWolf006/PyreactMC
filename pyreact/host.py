# -*- coding: utf-8 -*-
"""宿主层：PyreactScreenNode、create_root、runtime_init。

PyreactScreenNode 是用户 ScreenNode 的基类，负责：
- 作为按钮触摸回调的“UI 类方法”分发入口（SDK 要求回调必须是类函数）
- 在 GameRenderTickEvent 中推进动画，并提交 dirty -> diff -> 布局 -> 刷屏
- 在 Update 生命周期中处理普通 state 更新、输入同步与 effect
"""
import traceback
import time

import mod.client.extraClientApi as clientApi

from . import hooks
from . import native
from . import reconciler
from . import layout as layout_mod
from .element import resolve_element

# 当前活跃宿主（modsdk 单线程，同一时刻只有一个 screen）
_ACTIVE_HOST = [None]
_INITIALIZED = [False]
_RUNTIME_CLIENT_SYSTEM = [None]
_RUNTIME_DEBUG = [False]
_SAFE_AREA_SIZE = [None]
_SAFE_AREA_INSETS = [None]
_SAFE_AREA_PROBE = [None]
_SAFE_AREA_UI_REGISTERED = [False]
_SAFE_AREA_LISTENERS = []

_SAFE_AREA_UI_NAMESPACE = "PyreactRuntime"
_SAFE_AREA_UI_NAME = "safe_area_probe"
_SAFE_AREA_SCREEN_DEF = "PyreactBase.safeAreaProbe"
_UI_INIT_PRIORITY = 10
_SCREEN_CONTROL_PATH = "/variables_button_mappings_and_controls"
_SAFE_AREA_CONTROL_PATH = (
    "/variables_button_mappings_and_controls/safezone_screen_matrix/"
    "inner_matrix/safezone_screen_panel/root_screen_panel"
)


class SafeAreaInsets(object):
    """JsonUI 坐标系中的安全区四边距离。"""

    __slots__ = ("top", "right", "bottom", "left")

    def __init__(self, top, right, bottom, left):
        self.top = float(top)
        self.right = float(right)
        self.bottom = float(bottom)
        self.left = float(left)

    def to_tuple(self):
        """按 ``(top, right, bottom, left)`` 返回四元组。"""
        return (self.top, self.right, self.bottom, self.left)

    def __eq__(self, other):
        return isinstance(other, SafeAreaInsets) and (
            self.to_tuple() == other.to_tuple())

    def __ne__(self, other):
        return not self.__eq__(other)

    def __repr__(self):
        return (
            "SafeAreaInsets(top=%.3f, right=%.3f, bottom=%.3f, "
            "left=%.3f)" % self.to_tuple()
        )


class _RuntimeEventHandler(object):
    """接收引擎事件并转发给 Pyreact 运行时。"""

    def on_ui_init_finished(self, args):
        _create_safe_area_probe()
        from .navigator import navigator
        navigator._initialize()

    def on_screen_size_changed(self, args):
        notify_screen_size_changed()

    def on_game_render_tick(self, args=None):
        notify_game_render_tick()

    def on_pop_screen_after(self, args):
        from .navigator import navigator
        navigator._on_pop_screen_after(args)


_RUNTIME_EVENT_HANDLER = _RuntimeEventHandler()


class SafeAreaProbeScreen(native.ScreenNode):
    """挂载在 HUD 上的空 Screen，用于读取 common.base_screen 安全区。"""

    def __init__(self, namespace, name, param):
        native.ScreenNode.__init__(self, namespace, name, param)
        _SAFE_AREA_PROBE[0] = self

    def Create(self):
        if _SAFE_AREA_INSETS[0] is None:
            self._capture_size()

    def Update(self):
        if _SAFE_AREA_INSETS[0] is None:
            self._capture_size()

    def Destroy(self):
        if _SAFE_AREA_PROBE[0] is self:
            _SAFE_AREA_PROBE[0] = None

    def _capture_size(self):
        screen_width, screen_height = native.get_size(
            self, _SCREEN_CONTROL_PATH)
        safe_width, safe_height = native.get_size(
            self, _SAFE_AREA_CONTROL_PATH)
        if (screen_width <= 0 or screen_height <= 0 or
                safe_width <= 0 or safe_height <= 0):
            return

        screen_x, screen_y = native.get_global_position(
            self, _SCREEN_CONTROL_PATH)
        safe_x, safe_y = native.get_global_position(
            self, _SAFE_AREA_CONTROL_PATH)
        left = _normalize_inset(safe_x - screen_x)
        top = _normalize_inset(safe_y - screen_y)
        right = _normalize_inset(
            screen_x + screen_width - safe_x - safe_width)
        bottom = _normalize_inset(
            screen_y + screen_height - safe_y - safe_height)

        _publish_safe_area(
            (float(safe_width), float(safe_height)),
            SafeAreaInsets(top, right, bottom, left),
        )


def _normalize_inset(value):
    """消除布局浮点误差，并防止安全区尺寸取整产生负 inset。"""
    result = float(value)
    if result < 0.0:
        return 0.0
    if result < 0.001:
        return 0.0
    return result


class PyreactScreenNode(native.ScreenNode):
    """用户 ScreenNode 的基类。"""

    def __init__(self, namespace, name, param):
        native.ScreenNode.__init__(self, namespace, name, param)
        _ACTIVE_HOST[0] = self
        self._pyreact_active = True
        self._root_fiber = None
        self._root_path = native.ROOT_PATH
        self._dirty = set()
        self._pending_effects = set()
        self._animation_frames = {}
        self._needs_layout = False
        self._commit_native_dirty = False
        self._commit_layout_dirty = False
        self._layout_screen_flushed = False
        self._button_handlers = {}
        self._input_handlers = {}
        self._input_values = {}
        self._input_controlled_values = {}
        self._input_sync_pending = False
        self._input_edit_bound = False
        self._input_edit_handler_method_name = None
        self._slider_handlers = {}
        self._slider_values = {}
        self._slider_controlled_values = {}
        self._slider_sync_pending = False
        self._slider_bound = False
        self._slider_handler_method_name = None
        # debug 模式：剪贴板 IPC 轮询（见 pyreact/debug.py）
        self._debug_mode = _RUNTIME_DEBUG[0]
        self._debug_layout_nodes = None
        self._debug_game = None
        self._debug_ready_signaled = False

    # ---- 生命周期 ----
    def Create(self):
        # 子类覆盖：在此调用 pyreact.create_root(...).render("/root")
        pass

    def OnActive(self):
        """Screen 回到栈顶后恢复提交、动画和布局。"""
        self._pyreact_active = True
        _ACTIVE_HOST[0] = self
        self.schedule_layout()

    def OnDeactive(self):
        """Screen 被覆盖后暂停提交和动画。"""
        self._pyreact_active = False
        if _ACTIVE_HOST[0] is self:
            _ACTIVE_HOST[0] = None

    def Update(self):
        if not self._pyreact_active:
            return
        if not self._input_edit_bound:
            if self._input_controlled_values:
                self._ensure_input_edit_handler()
            else:
                for callback in self._input_handlers.values():
                    if callable(callback):
                        self._ensure_input_edit_handler()
                        break
        if not self._slider_bound:
            if self._slider_controlled_values:
                self._ensure_slider_handler()
            else:
                for callback in self._slider_handlers.values():
                    if callable(callback):
                        self._ensure_slider_handler()
                        break
        if self._debug_mode:
            from . import debug
            try:
                debug.poll_clipboard(self)
            except Exception:
                pass
        self._pyreact_flush()
        if self._input_sync_pending:
            self._pyreact_sync_controlled_inputs()
        if self._slider_sync_pending:
            self._pyreact_sync_controlled_sliders()

    def schedule_layout(self):
        """安排下一帧完整布局，供窗口尺寸变化事件调用。"""
        self._needs_layout = True
        try:
            native.update_screen(self, True)
        except Exception:
            pass

    def Destroy(self):
        self._pyreact_active = False
        if self._root_fiber is not None:
            try:
                reconciler.unmount_fiber(self._root_fiber, self)
                native.update_screen(self, True)
            except Exception:
                pass
            self._root_fiber = None
        self._dirty.clear()
        self._pending_effects.clear()
        self._animation_frames.clear()
        self._button_handlers.clear()
        self._input_handlers.clear()
        self._input_values.clear()
        self._input_controlled_values.clear()
        self._unbind_input_edit_handler()
        self._slider_handlers.clear()
        self._slider_values.clear()
        self._slider_controlled_values.clear()
        self._unbind_slider_handler()
        if _ACTIVE_HOST[0] is self:
            _ACTIVE_HOST[0] = None

    # ---- 刷帧 ----
    def _pyreact_flush(self):
        if (not self._dirty and not self._needs_layout and
                not self._commit_native_dirty and
                not self._commit_layout_dirty and not self._pending_effects):
            return
        pending_native_dirty = self._commit_native_dirty
        pending_layout_dirty = self._commit_layout_dirty
        self._commit_native_dirty = False
        self._commit_layout_dirty = False
        # 重渲染 dirty 组件
        if self._dirty:
            dirty = self._dirty
            self._dirty = set()
            def depth(fiber):
                value = 0
                while fiber.parent_fiber is not None:
                    value += 1
                    fiber = fiber.parent_fiber
                return value

            # A parent's reconciliation may consume a child's state update.
            # Visit ancestors first and skip already-rendered descendants.
            for fiber in sorted(dirty, key=depth):
                if (fiber.dirty and fiber._mounted and fiber.is_component
                        and fiber.host is self):
                    try:
                        reconciler.rerender_component(fiber, self)
                    except Exception:
                        traceback.print_exc()
        # 布局：仅当根容器已具备真实尺寸时才执行
        # （Create 阶段屏幕尚未布局，GetSize 可能返回 0）
        needs_layout = (
            self._needs_layout or pending_layout_dirty or
            self._commit_layout_dirty)
        self._needs_layout = needs_layout
        if self._root_fiber is not None and needs_layout:
            rw, rh = native.get_size(self, self._root_path)
            if rw > 0 and rh > 0:
                try:
                    # 返回 False 表示文本叶子尚未能量测（屏幕未渲染），下帧重试
                    ready, nodes = layout_mod.layout_tree(self._root_fiber, self, self._root_path)
                    if ready:
                        self._needs_layout = False
                    # debug 模式保留 layout 快照供 dump
                    if self._debug_mode and nodes is not None:
                        self._debug_layout_nodes = nodes
                    if self._layout_screen_flushed:
                        self._layout_screen_flushed = False
                    else:
                        native.update_screen(self, True)
                except Exception:
                    traceback.print_exc()
                    self._needs_layout = True
        elif pending_native_dirty or self._commit_native_dirty:
            try:
                native.update_screen(self, True)
            except Exception:
                traceback.print_exc()
        if self._pending_effects:
            try:
                hooks.flush_pending_effects(self)
            except Exception:
                traceback.print_exc()
        self._commit_native_dirty = False
        self._commit_layout_dirty = False

    # ---- dirty 调度 ----
    def schedule_render(self, fiber):
        if not fiber._mounted and fiber not in hooks._current_fiber_stack:
            return
        fiber.dirty = True
        self._dirty.add(fiber)

    # ---- 函数式组件事件监听 ----
    def pyreact_listen_engine_event(self, event_name, listener, priority=0):
        """订阅 ModSDK 引擎事件，供 use_event 使用。"""
        return _listen_runtime_event(
            clientApi.GetEngineNamespace(),
            clientApi.GetEngineSystemName(),
            event_name,
            listener,
            priority,
        )

    def pyreact_listen_custom_event(self, namespace, system_name, event_name,
                                    listener, priority=0):
        """订阅指定客户端 System 的自定义事件，供 use_custom_event 使用。"""
        return _listen_runtime_event(
            namespace,
            system_name,
            event_name,
            listener,
            priority,
        )

    # ---- 动画帧 ----
    def pyreact_register_animation_frame(self, slot):
        registration_id = id(slot)
        self._animation_frames[registration_id] = slot
        slot["_registration_id"] = registration_id

    def pyreact_unregister_animation_frame(self, slot):
        registration_id = slot.pop("_registration_id", None)
        if registration_id is not None:
            self._animation_frames.pop(registration_id, None)

    def _pyreact_tick_animation_frames(self, now=None):
        if not self._animation_frames or self._root_fiber is None:
            return
        if now is None:
            now = time.time()
        for slot in list(self._animation_frames.values()):
            fiber = slot.get("fiber")
            if fiber is None or not fiber._mounted:
                continue
            if not slot.get("active"):
                continue
            callback = slot.get("callback")
            if not callable(callback):
                continue
            try:
                callback(now)
            except Exception:
                traceback.print_exc()

    # ---- 按钮回调分发 ----
    def pyreact_register_button(self, path, on_down, on_up, on_click):
        self._button_handlers[path] = (on_down, on_up, on_click)

    def pyreact_unregister_button(self, path):
        self._button_handlers.pop(path, None)

    def _pyreact_dispatch_touch_down(self, args):
        path = args.get("ButtonPath") if isinstance(args, dict) else None
        handlers = self._button_handlers.get(path) if path else None
        if handlers:
            on_down = handlers[0]
            if on_down:
                on_down()

    def _pyreact_dispatch_touch_up(self, args):
        path = args.get("ButtonPath") if isinstance(args, dict) else None
        handlers = self._button_handlers.get(path) if path else None
        if handlers:
            on_up, on_click = handlers[1], handlers[2]
            if on_up:
                on_up()
            if on_click:
                on_click()

    # ---- 输入框回调分发 ----
    def pyreact_register_input(self, path, on_change):
        """注册输入框路径及其 onChange 回调。"""
        self._input_handlers[path] = on_change
        if callable(on_change):
            self._ensure_input_edit_handler()

    def pyreact_unregister_input(self, path):
        self._input_handlers.pop(path, None)
        self._input_values.pop(path, None)
        self._input_controlled_values.pop(path, None)
        if not self._input_controlled_values:
            self._input_sync_pending = False

    def pyreact_set_input_value(self, path, value):
        self._input_values[path] = value

    def pyreact_get_input_value(self, path):
        return self._input_values.get(path)

    def pyreact_set_input_controlled_value(self, path, value):
        self._input_controlled_values[path] = value
        self._input_sync_pending = True
        self._ensure_input_edit_handler()

    def pyreact_unset_input_controlled_value(self, path):
        self._input_controlled_values.pop(path, None)
        if not self._input_controlled_values:
            self._input_sync_pending = False

    def _pyreact_sync_controlled_inputs(self):
        """在 value 提交或编辑事件后保证受控 Input 与 props.value 一致。"""
        retry = False
        for path, desired in list(self._input_controlled_values.items()):
            control = native.get_control(self, path)
            if control is None:
                retry = True
                continue
            edit_box = control.asTextEditBox()
            if edit_box is None:
                retry = True
                continue
            try:
                current = edit_box.GetEditText()
            except Exception:
                retry = True
                continue
            if isinstance(current, unicode):
                current = current.encode("utf-8")
            elif current is not None and not isinstance(current, str):
                current = str(current)
            if current != desired:
                try:
                    edit_box.SetEditText(desired)
                except Exception:
                    retry = True
                    continue
            self._input_values[path] = desired
        self._input_sync_pending = retry

    def _ensure_input_edit_handler(self):
        """为当前 ScreenNode 动态注册共享的 edit_box 事件处理器。

        JsonUI 模板中的 ``$text_box_name`` 指向同一个 binding name，因此
        回调没有可靠的控件路径；事件到达后扫描已注册输入框并做文本 diff。
        """
        if self._input_edit_bound:
            return

        screen_name = getattr(self, "screen_name", None)
        if not screen_name:
            return
        view_binder = native.ViewBinder
        try:
            flags = view_binder.BF_EditChanged | view_binder.BF_EditFinished
        except Exception:
            return

        method_name = "__pyreact_input_edit_handler_%s" % str(id(self))
        binding_name = "%%%s.message_text_edit_box0" % native.TEMPLATE_NAMESPACE
        runtime = self

        def _handler(screen, args=None):
            runtime._pyreact_dispatch_input_change(args)

        # ModSDK 的 ScreenNode 绑定注册会依据函数名查找类成员。
        try:
            _handler.func_name = method_name
        except Exception:
            pass
        try:
            _handler.__name__ = method_name
        except Exception:
            pass
        _handler.binding_flags = flags
        _handler.binding_name = binding_name

        try:
            setattr(self.__class__, method_name, _handler)
            bound = getattr(self, method_name)
            self._process_default(bound, screen_name)
        except Exception:
            if method_name in self.__class__.__dict__:
                delattr(self.__class__, method_name)
            return

        self._input_edit_handler_method_name = method_name
        self._input_edit_bound = True

    def _unbind_input_edit_handler(self):
        if not self._input_edit_bound:
            return
        method_name = self._input_edit_handler_method_name
        screen_name = getattr(self, "screen_name", None)
        if method_name and screen_name:
            try:
                bound = getattr(self, method_name)
                self._process_default_unregister(bound, screen_name)
            except Exception:
                pass
        if method_name and method_name in self.__class__.__dict__:
            delattr(self.__class__, method_name)
        self._input_edit_bound = False
        self._input_edit_handler_method_name = None

    def _pyreact_dispatch_input_change(self, args=None):
        """读取所有输入框当前文本，只触发真正发生变化的回调。"""
        for path, callback in list(self._input_handlers.items()):
            control = native.get_control(self, path)
            if control is None:
                continue
            edit_box = control.asTextEditBox()
            if edit_box is None:
                continue
            try:
                value = edit_box.GetEditText()
            except Exception:
                continue
            if value is None:
                continue
            if isinstance(value, unicode):
                value = value.encode("utf-8")
            elif not isinstance(value, str):
                value = str(value)
            if self._input_values.get(path) == value:
                continue
            self._input_values[path] = value
            if path in self._input_controlled_values:
                self._input_sync_pending = True
            if not callable(callback):
                continue
            try:
                callback(value)
            except Exception:
                traceback.print_exc()

    # ---- 滑块回调分发 ----
    def pyreact_register_slider(self, path, on_change):
        """注册 Slider 路径及其 onChange 回调。"""
        self._slider_handlers[path] = on_change
        if callable(on_change):
            self._ensure_slider_handler()

    def pyreact_unregister_slider(self, path):
        self._slider_handlers.pop(path, None)
        self._slider_values.pop(path, None)
        self._slider_controlled_values.pop(path, None)
        if not self._slider_controlled_values:
            self._slider_sync_pending = False

    def pyreact_set_slider_value(self, path, value):
        self._slider_values[path] = value

    def pyreact_get_slider_value(self, path):
        return self._slider_values.get(path)

    def pyreact_set_slider_controlled_value(self, path, value):
        self._slider_controlled_values[path] = value
        self._slider_sync_pending = True
        self._ensure_slider_handler()

    def pyreact_unset_slider_controlled_value(self, path):
        self._slider_controlled_values.pop(path, None)
        if not self._slider_controlled_values:
            self._slider_sync_pending = False

    def _pyreact_sync_controlled_sliders(self):
        """在 value 提交或滑动事件后保证受控 Slider 与 props.value 一致。"""
        retry = False
        for path, desired in list(self._slider_controlled_values.items()):
            control = native.get_control(self, path)
            if control is None:
                retry = True
                continue
            slider = control.asSlider()
            if slider is None:
                retry = True
                continue
            try:
                current = float(slider.GetSliderValue())
            except Exception:
                retry = True
                continue
            if current != desired:
                try:
                    bag = control.GetPropertyBag()
                    if not isinstance(bag, dict):
                        bag = {}
                    else:
                        bag = dict(bag)
                    bag["#slider_value"] = desired
                    control.SetPropertyBag(bag)
                    slider.SetSliderValue(desired)
                except Exception:
                    retry = True
                    continue
            self._slider_values[path] = desired
        self._slider_sync_pending = retry

    def _ensure_slider_handler(self):
        """为当前 ScreenNode 动态注册所有 Slider 共享的事件处理器。"""
        if self._slider_bound:
            return

        screen_name = getattr(self, "screen_name", None)
        if not screen_name:
            return
        view_binder = native.ViewBinder
        try:
            flags = view_binder.BF_SliderChanged | view_binder.BF_SliderFinished
        except Exception:
            return

        method_name = "__pyreact_slider_handler_%s" % str(id(self))
        binding_name = "%%%s.slider0" % native.TEMPLATE_NAMESPACE
        runtime = self

        def _handler(screen, value=None, is_finish=False, unused=None):
            runtime._pyreact_dispatch_slider_change(value, is_finish)
            return native.ViewRequest.Refresh

        try:
            _handler.func_name = method_name
        except Exception:
            pass
        try:
            _handler.__name__ = method_name
        except Exception:
            pass
        _handler.binding_flags = flags
        _handler.binding_name = binding_name

        try:
            setattr(self.__class__, method_name, _handler)
            bound = getattr(self, method_name)
            self._process_default(bound, screen_name)
        except Exception:
            if method_name in self.__class__.__dict__:
                delattr(self.__class__, method_name)
            return

        self._slider_handler_method_name = method_name
        self._slider_bound = True

    def _unbind_slider_handler(self):
        if not self._slider_bound:
            return
        method_name = self._slider_handler_method_name
        screen_name = getattr(self, "screen_name", None)
        if method_name and screen_name:
            try:
                bound = getattr(self, method_name)
                self._process_default_unregister(bound, screen_name)
            except Exception:
                pass
        if method_name and method_name in self.__class__.__dict__:
            delattr(self.__class__, method_name)
        self._slider_bound = False
        self._slider_handler_method_name = None

    def _pyreact_dispatch_slider_change(self, value=None, is_finish=False):
        """扫描 Slider 当前值，只触发真正发生变化的 onChange。"""
        for path, callback in list(self._slider_handlers.items()):
            control = native.get_control(self, path)
            if control is None:
                continue
            slider = control.asSlider()
            if slider is None:
                continue
            try:
                current = float(slider.GetSliderValue())
            except Exception:
                continue
            if self._slider_values.get(path) == current:
                continue
            self._slider_values[path] = current
            if path in self._slider_controlled_values:
                self._slider_sync_pending = True
            if not callable(callback):
                continue
            try:
                callback(current)
            except Exception:
                traceback.print_exc()


class Root(object):
    """渲染根。"""

    def __init__(self, component, host):
        self._component = component
        self._host = host

    def render(self, path):
        element = resolve_element(self._component)
        if element is None:
            raise TypeError(
                "create_root requires a Pyreact Element or @Component, got %r"
                % (self._component,)
            )
        return _mount_element(element, self._host, path)


def _mount_element(element, host, path):
    """把一个已构造的 Element 直接挂载到指定宿主路径。"""
    root_fiber = None
    if host._root_fiber is not None:
        reconciler.unmount_fiber(host._root_fiber, host)
        host._root_fiber = None
    host._debug_layout_nodes = None
    host._root_path = path
    try:
        root_fiber = reconciler.create_fiber(element, host)
        reconciler.mount_fiber(root_fiber, path, host)
        host._root_fiber = root_fiber
        native.update_screen(host, True)
        # Create 阶段根尺寸可能尚未就绪，交由首帧 Update 兜底重排。
        rw, rh = native.get_size(host, path)
        if rw > 0 and rh > 0:
            layout_mod.layout_tree(root_fiber, host, path)
            native.update_screen(host, True)
            host._layout_screen_flushed = False
        host._needs_layout = True
        host._commit_native_dirty = False
        host._commit_layout_dirty = False
        hooks.flush_pending_effects(host)
        if host._debug_mode and not host._debug_ready_signaled:
            from . import debug
            debug.notify_ready()
            host._debug_ready_signaled = True
        return True
    except Exception:
        traceback.print_exc()
        if root_fiber is not None:
            try:
                reconciler.unmount_fiber(root_fiber, host)
                native.update_screen(host, True)
            except Exception:
                traceback.print_exc()
        host._root_fiber = None
        return False


def create_root(component):
    """创建渲染根。须在 ScreenNode.Create 中调用。

    ``component`` 可以是未调用的 ``@Component`` 组件，也可以是已构造的
    ``Element``（``Component()`` 或 Primitive 调用结果），两者等价。
    """
    host = _ACTIVE_HOST[0]
    if host is None:
        raise RuntimeError("create_root called without an active PyreactScreenNode")
    return Root(component, host)


def get_safe_area_size():
    """返回 JsonUI 安全内容区的 ``(width, height)``，尚未测得时返回 None。"""
    return _SAFE_AREA_SIZE[0]


def get_safe_area_insets():
    """返回 SafeAreaInsets；探针尚未完成布局时返回 None。"""
    return _SAFE_AREA_INSETS[0]


def _publish_safe_area(size, insets):
    """发布有效测量，并通知已挂载的 SafeArea。"""
    previous = _SAFE_AREA_INSETS[0]
    previous_size = _SAFE_AREA_SIZE[0]
    _SAFE_AREA_SIZE[0] = size
    _SAFE_AREA_INSETS[0] = insets
    if previous == insets and previous_size == size:
        return
    listeners = tuple(_SAFE_AREA_LISTENERS)
    for listener in listeners:
        try:
            listener(insets)
        except Exception:
            traceback.print_exc()


def _subscribe_safe_area(listener):
    """订阅首次测量及窗口变化后的更新，返回取消订阅函数。"""
    if not callable(listener):
        raise TypeError("safe area listener must be callable")
    current = _SAFE_AREA_INSETS[0]
    _SAFE_AREA_LISTENERS.append(listener)
    if current is not None:
        listener(current)

    def cleanup():
        for index, current_listener in enumerate(_SAFE_AREA_LISTENERS):
            if current_listener is listener:
                del _SAFE_AREA_LISTENERS[index]
                break

    return cleanup


def _create_safe_area_probe():
    """首次 UI 初始化时创建空 HUD Screen，等待一次有效测量。"""
    if _SAFE_AREA_INSETS[0] is not None or _SAFE_AREA_PROBE[0] is not None:
        return
    screen_class_path = __name__ + ".SafeAreaProbeScreen"
    try:
        if not _SAFE_AREA_UI_REGISTERED[0]:
            result = native.register_ui(
                _SAFE_AREA_UI_NAMESPACE,
                _SAFE_AREA_UI_NAME,
                screen_class_path,
                _SAFE_AREA_SCREEN_DEF,
            )
            if result is False:
                return
            _SAFE_AREA_UI_REGISTERED[0] = True
        probe = native.create_ui(
            _SAFE_AREA_UI_NAMESPACE,
            _SAFE_AREA_UI_NAME,
            {"isHud": 1},
        )
        if probe is not None:
            _SAFE_AREA_PROBE[0] = probe
    except Exception:
        traceback.print_exc()


def runtime_init(client_system, debug=False):
    """初始化运行时，并设置所有 Pyreact Screen 的全局调试开关。"""
    if client_system is None:
        raise ValueError("runtime_init requires a ClientSystem")
    if _INITIALIZED[0]:
        return
    _RUNTIME_CLIENT_SYSTEM[0] = client_system
    _RUNTIME_DEBUG[0] = bool(debug)
    from .navigator import navigator
    navigator._set_debug(_RUNTIME_DEBUG[0])
    client_system.ListenForEvent(
        clientApi.GetEngineNamespace(),
        clientApi.GetEngineSystemName(),
        "UiInitFinished",
        _RUNTIME_EVENT_HANDLER,
        _RUNTIME_EVENT_HANDLER.on_ui_init_finished,
        _UI_INIT_PRIORITY,
    )
    client_system.ListenForEvent(
        clientApi.GetEngineNamespace(),
        clientApi.GetEngineSystemName(),
        "ScreenSizeChangedClientEvent",
        _RUNTIME_EVENT_HANDLER,
        _RUNTIME_EVENT_HANDLER.on_screen_size_changed,
    )
    client_system.ListenForEvent(
        clientApi.GetEngineNamespace(),
        clientApi.GetEngineSystemName(),
        "PopScreenAfterClientEvent",
        _RUNTIME_EVENT_HANDLER,
        _RUNTIME_EVENT_HANDLER.on_pop_screen_after,
    )
    client_system.ListenForEvent(
        clientApi.GetEngineNamespace(),
        clientApi.GetEngineSystemName(),
        "GameRenderTickEvent",
        _RUNTIME_EVENT_HANDLER,
        _RUNTIME_EVENT_HANDLER.on_game_render_tick,
    )
    _INITIALIZED[0] = True


def _listen_runtime_event(namespace, system_name, event_name, listener,
                          priority):
    """注册并返回对应的解除函数；参数与 ModSDK 注销调用保持一致。"""
    client_system = _RUNTIME_CLIENT_SYSTEM[0]
    if client_system is None:
        raise RuntimeError("runtime_init must run before subscribing to events")
    callback = listener.dispatch
    client_system.ListenForEvent(
        namespace,
        system_name,
        event_name,
        listener,
        callback,
        priority,
    )

    def cleanup():
        client_system.UnListenForEvent(
            namespace,
            system_name,
            event_name,
            listener,
            callback,
            priority,
        )

    return cleanup


def notify_screen_size_changed():
    """响应 ScreenSizeChangedClientEvent，安排当前宿主重排。"""
    # The probe's next Update reads the new native geometry, after resize.
    _SAFE_AREA_INSETS[0] = None
    host = _ACTIVE_HOST[0]
    if host is not None:
        host.schedule_layout()


def notify_game_render_tick():
    """每个客户端渲染帧推进并提交 Animated 时间线。"""
    from .navigator import navigator
    navigator._tick()
    host = _ACTIVE_HOST[0]
    if host is None or not host._animation_frames:
        return
    host._pyreact_tick_animation_frames(time.time())
    host._pyreact_flush()
