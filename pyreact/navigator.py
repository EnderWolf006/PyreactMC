# -*- coding: utf-8 -*-
"""自动注册 Screen 池的全局原生栈 navigator。"""
import traceback

from .element import Element
from . import host
from . import native


_NAMESPACE = "PyreactRuntime"
_UI_NAME_PREFIX = "navigator_screen_"
_SCREEN_DEF_PREFIX = "PyreactBase.navigatorScreen"
_SLOT_COUNT = 16
_PARAM_NAVIGATOR_ID = "__pyreact_navigator_id"
_PARAM_ENTRY_KEY = "__pyreact_entry_key"
_POP_EVENT_TIMEOUT_TICKS = 30


class NavigationErrorCode(object):
    not_ready = "not_ready"
    busy = "busy"
    invalid_element = "invalid_element"
    invalid_count = "invalid_count"
    duplicate_key = "duplicate_key"
    key_not_found = "key_not_found"
    empty_stack = "empty_stack"
    capacity_exhausted = "capacity_exhausted"
    native_push_failed = "native_push_failed"
    native_pop_failed = "native_pop_failed"
    screen_mount_failed = "screen_mount_failed"
    target_destroyed = "target_destroyed"


class NavigationError(Exception):
    """navigator 命令失败；``code`` 用于稳定判断错误类型。"""

    def __init__(self, code, message):
        Exception.__init__(self, message)
        self.code = code
        self.message = message

    def __str__(self):
        return self.message


class NavigationEntry(object):
    """一个由 navigator 创建的只读 Pyreact 页面实例。"""

    __slots__ = (
        "_key", "_element", "_slot", "_host", "_active", "_mounted",
        "_on_result", "_owner_key", "_result_called",
    )

    def __init__(self, key, element, slot, on_result, owner_key):
        self._key = key
        self._element = element
        self._slot = slot
        self._host = None
        self._active = False
        self._mounted = False
        self._on_result = on_result
        self._owner_key = owner_key
        self._result_called = False

    @property
    def key(self):
        return self._key

    @property
    def element(self):
        return self._element

    @property
    def is_active(self):
        return self._active

    def __repr__(self):
        return "NavigationEntry(key=%r, active=%r)" % (
            self._key, self._active)


class _ScreenSlot(object):
    __slots__ = (
        "index", "ui_name", "screen_def", "screen_name", "registered",
        "entry_key",
    )

    def __init__(self, index):
        suffix = "%02d" % index
        self.index = index
        self.ui_name = _UI_NAME_PREFIX + suffix
        self.screen_def = _SCREEN_DEF_PREFIX + suffix
        self.screen_name = "navigatorScreen" + suffix
        self.registered = False
        self.entry_key = None


class _TransitionKind(object):
    push = "push"
    pop = "pop"
    replace = "replace"
    pop_to = "pop_to"
    pop_to_top = "pop_to_top"
    clear = "clear"
    reset = "reset"
    close = "close"
    mount_cleanup = "mount_cleanup"


class _TransitionPhase(object):
    advance = "advance"
    wait_pop = "wait_pop"
    wait_push = "wait_push"


class Navigator(object):
    """管理 Pyreact Screen 池，并统一负责实际 UI 栈的所有 pop。"""

    def __init__(self):
        self._navigator_id = "navigator_%d" % id(self)
        self._slots = [_ScreenSlot(index) for index in range(_SLOT_COUNT)]
        self._ready = False
        self._entries = []
        self._key_counter = 0
        self._transition = None
        self._tick_id = 0
        self._pop_revision = 0
        self._debug = False
        self._debug_top_signature = None

    @property
    def is_ready(self):
        return self._ready

    @property
    def capacity(self):
        return len(self._slots)

    @property
    def available_slots(self):
        return len([slot for slot in self._slots
                    if slot.entry_key is None])

    @property
    def depth(self):
        return len(self._entries)

    @property
    def top(self):
        return self._entries[-1] if self._entries else None

    @property
    def top_ui_name(self):
        try:
            return native.get_top_ui()
        except Exception:
            traceback.print_exc()
            return None

    @property
    def is_transitioning(self):
        return self._transition is not None

    def can_go_back(self):
        return len(self._entries) > 1

    def get_entries(self):
        return tuple(self._entries)

    def get_entry(self, key):
        return self._find_entry(key)

    def contains(self, key):
        return self._find_entry(key) is not None

    def _set_debug(self, flag):
        """由 runtime_init 在首次初始化时设置全局调试状态。"""
        self._debug = bool(flag)

    def push(self, element, key=None, on_result=None,
             on_complete=None, on_error=None):
        if not self._prepare_command(on_complete, on_error):
            return False
        checked = self._check_destination(
            element, key, on_result, on_error)
        if checked is None:
            return False
        entry_key, result_callback = checked
        self._transition = self._new_transition(
            _TransitionKind.push, on_complete, on_error)
        self._transition["element"] = element
        self._transition["entry_key"] = entry_key
        self._transition["on_result"] = result_callback
        return self._issue_push()

    def pop(self, count=1, result=None,
            on_complete=None, on_error=None):
        if not self._prepare_command(on_complete, on_error):
            return False
        if (isinstance(count, bool) or
                not isinstance(count, (int, long)) or count <= 0):
            return self._reject(
                NavigationErrorCode.invalid_count,
                "pop count must be a positive integer",
                on_error,
            )
        self._transition = self._new_transition(
            _TransitionKind.pop, on_complete, on_error)
        self._transition["remaining"] = count
        self._transition["result"] = result
        return self._advance(self._tick_id)

    def replace(self, element, key=None,
                on_complete=None, on_error=None):
        if not self._prepare_command(on_complete, on_error):
            return False
        if not self._entries:
            return self._reject(
                NavigationErrorCode.empty_stack,
                "cannot replace without a Pyreact page",
                on_error,
            )
        checked = self._check_destination(element, key, None, on_error)
        if checked is None:
            return False
        entry_key, result_callback = checked
        self._transition = self._new_transition(
            _TransitionKind.replace, on_complete, on_error)
        self._transition.update({
            "source_key": self._entries[-1].key,
            "element": element,
            "entry_key": entry_key,
            "on_result": result_callback,
        })
        return self._advance(self._tick_id)

    def pop_to(self, key, result=None,
               on_complete=None, on_error=None):
        if not self._prepare_command(on_complete, on_error):
            return False
        target = self._find_entry(key)
        if target is None:
            return self._reject(
                NavigationErrorCode.key_not_found,
                "navigation entry key was not found",
                on_error,
            )
        self._transition = self._new_transition(
            _TransitionKind.pop_to, on_complete, on_error)
        self._transition["target_key"] = target.key
        self._transition["result"] = result
        return self._advance(self._tick_id)

    def pop_to_top(self, result=None,
                   on_complete=None, on_error=None):
        if not self._prepare_command(on_complete, on_error):
            return False
        if not self._entries:
            return self._reject(
                NavigationErrorCode.empty_stack,
                "navigator has no Pyreact pages",
                on_error,
            )
        self._transition = self._new_transition(
            _TransitionKind.pop_to_top, on_complete, on_error)
        self._transition["target_key"] = self._entries[0].key
        self._transition["result"] = result
        return self._advance(self._tick_id)

    def clear(self, on_complete=None, on_error=None):
        if not self._prepare_command(on_complete, on_error):
            return False
        self._transition = self._new_transition(
            _TransitionKind.clear, on_complete, on_error)
        return self._advance(self._tick_id)

    def reset(self, element, key=None,
              on_complete=None, on_error=None):
        if not self._prepare_command(on_complete, on_error):
            return False
        checked = self._check_destination(element, key, None, on_error)
        if checked is None:
            return False
        entry_key, result_callback = checked
        self._transition = self._new_transition(
            _TransitionKind.reset, on_complete, on_error)
        self._transition.update({
            "element": element,
            "entry_key": entry_key,
            "on_result": result_callback,
        })
        return self._advance(self._tick_id)

    def close(self, on_complete=None, on_error=None):
        if not self._prepare_command(on_complete, on_error):
            return False
        self._transition = self._new_transition(
            _TransitionKind.close, on_complete, on_error)
        return self._advance(self._tick_id)

    def _initialize(self):
        if self._ready:
            return True
        class_path = __name__ + ".NavigatorScreen"
        try:
            for slot in self._slots:
                if slot.registered:
                    continue
                result = native.register_ui(
                    _NAMESPACE,
                    slot.ui_name,
                    class_path,
                    slot.screen_def,
                )
                if result is False:
                    return False
                slot.registered = True
        except Exception:
            traceback.print_exc()
            return False
        self._ready = True
        return True

    def _prepare_command(self, on_complete, on_error):
        self._check_callbacks(on_complete, on_error)
        if not self._ready:
            return self._reject(
                NavigationErrorCode.not_ready,
                "navigator is not ready; call runtime_init before UiInitFinished",
                on_error,
            )
        if self._transition is not None:
            return self._reject(
                NavigationErrorCode.busy,
                "another navigation transition is running",
                on_error,
            )
        return True

    def _check_destination(self, element, key, on_result, on_error):
        if not isinstance(element, Element):
            self._reject(
                NavigationErrorCode.invalid_element,
                "navigator destination must be a Pyreact Element",
                on_error,
            )
            return None
        if on_result is not None and not callable(on_result):
            raise TypeError("on_result must be callable or None")
        if key is None:
            self._key_counter += 1
            key = "navigation:%d" % self._key_counter
        elif not isinstance(key, basestring) or not key:
            raise TypeError("navigation key must be a non-empty string or None")
        if self._find_entry(key) is not None:
            self._reject(
                NavigationErrorCode.duplicate_key,
                "navigation entry key is already in use",
                on_error,
            )
            return None
        return (key, on_result)

    @staticmethod
    def _check_callbacks(on_complete, on_error):
        if on_complete is not None and not callable(on_complete):
            raise TypeError("on_complete must be callable or None")
        if on_error is not None and not callable(on_error):
            raise TypeError("on_error must be callable or None")

    def _new_transition(self, kind, on_complete, on_error):
        return {
            "kind": kind,
            "phase": _TransitionPhase.advance,
            "on_complete": on_complete,
            "on_error": on_error,
            "on_result": None,
            "result": None,
            "removed": [],
            "remaining": 0,
            "target_key": None,
            "source_key": None,
            "element": None,
            "entry_key": None,
            "waiting_key": None,
            "last_pop_tick": None,
            "observed_pop_revision": self._pop_revision,
            "wait_pop_revision": None,
            "pop_call_failed": False,
            "pending_error": None,
        }

    def _issue_push(self):
        transition = self._transition
        slot = self._acquire_slot()
        if slot is None:
            self._fail(
                NavigationErrorCode.capacity_exhausted,
                "all 16 navigator Screen slots are in use",
            )
            return False
        owner = self._entries[-1] if self._entries else None
        entry = NavigationEntry(
            transition["entry_key"],
            transition["element"],
            slot,
            transition["on_result"],
            owner.key if owner is not None else None,
        )
        slot.entry_key = entry.key
        self._entries.append(entry)
        transition["phase"] = _TransitionPhase.wait_push
        transition["waiting_key"] = entry.key
        params = {
            _PARAM_NAVIGATOR_ID: self._navigator_id,
            _PARAM_ENTRY_KEY: entry.key,
        }
        try:
            screen = native.push_screen(
                _NAMESPACE, slot.ui_name, params)
        except Exception:
            traceback.print_exc()
            screen = None
        if screen is None:
            self._remove_entry(entry.key)
            self._release_slot(entry)
            self._fail(
                NavigationErrorCode.native_push_failed,
                "ModSDK PushScreen failed",
            )
            return False
        if self._find_entry(entry.key) is None:
            return True
        if entry._host is None:
            entry._host = screen
        self._refresh_active_entry()
        return True

    def _advance(self, tick_id):
        transition = self._transition
        if transition is None:
            return False
        self._consume_pop_events(transition)
        phase = transition["phase"]
        if phase == _TransitionPhase.wait_push:
            return True
        if phase == _TransitionPhase.wait_pop:
            last_tick = transition["last_pop_tick"]
            if self._pop_revision != transition["wait_pop_revision"]:
                transition["phase"] = _TransitionPhase.advance
                transition["waiting_key"] = None
                transition["wait_pop_revision"] = None
                transition["pop_call_failed"] = False
            elif last_tick is not None and tick_id <= last_tick:
                return True
            elif transition["pop_call_failed"]:
                if (transition["kind"] == _TransitionKind.close and
                        not self._entries):
                    self._finish(None, True)
                    return True
                self._fail(
                    NavigationErrorCode.native_pop_failed,
                    "ModSDK PopTopUI could not pop the current UI",
                )
                return False
            elif (last_tick is None or
                    tick_id - last_tick <= _POP_EVENT_TIMEOUT_TICKS):
                return True
            else:
                self._fail(
                    NavigationErrorCode.native_pop_failed,
                    "PopScreenAfterClientEvent was not received",
                )
                return False
        last_tick = transition["last_pop_tick"]
        if last_tick is not None and tick_id <= last_tick:
            return True

        kind = transition["kind"]
        if kind == _TransitionKind.pop:
            if transition["remaining"] <= 0:
                self._finish()
                return True
            return self._issue_pop_top()
        if kind in (_TransitionKind.pop_to, _TransitionKind.pop_to_top):
            target = self._find_entry(transition["target_key"])
            if target is None:
                self._fail(
                    NavigationErrorCode.target_destroyed,
                    "navigation target was destroyed before it became top",
                )
                return False
            if self._is_actual_top(target):
                self._finish(target)
                return True
            return self._issue_pop_top()
        if kind == _TransitionKind.replace:
            if self._find_entry(transition["source_key"]) is None:
                return self._issue_push()
            return self._issue_pop_top()
        if kind == _TransitionKind.clear:
            if not self._entries:
                self._finish(None, True)
                return True
            return self._issue_pop_top()
        if kind == _TransitionKind.reset:
            if not self._entries:
                return self._issue_push()
            return self._issue_pop_top()
        if kind == _TransitionKind.close:
            return self._issue_pop_top()
        if kind == _TransitionKind.mount_cleanup:
            if self._find_entry(transition["target_key"]) is None:
                error = transition["pending_error"]
                self._fail(error.code, error.message)
                return False
            return self._issue_pop_top()
        return False

    def _consume_pop_events(self, transition):
        """把命令接受后发生的所有真实 UI 出栈计入固定层数 pop。"""
        observed = transition["observed_pop_revision"]
        if self._pop_revision == observed:
            return
        if transition["kind"] == _TransitionKind.pop:
            count = self._pop_revision - observed
            transition["remaining"] = max(
                0, transition["remaining"] - count)
        transition["observed_pop_revision"] = self._pop_revision

    def _on_pop_screen_after(self, args=None):
        """接收 native、原版 UI 或 navigator 发起的统一出栈确认。"""
        self._pop_revision += 1
        if self._debug:
            screen_name = args.get("screenName") if isinstance(args, dict) else None
            print "[pyreact.navigator] pop_after=%d top=%r" % (
                self._pop_revision, screen_name)
        self._refresh_active_entry()

    def _issue_pop_top(self):
        transition = self._transition
        owned_top = self._actual_owned_top()
        transition["phase"] = _TransitionPhase.wait_pop
        transition["waiting_key"] = (
            owned_top.key if owned_top is not None else None)
        transition["last_pop_tick"] = self._tick_id
        transition["wait_pop_revision"] = self._pop_revision
        transition["pop_call_failed"] = False
        try:
            result = native.pop_top_ui()
        except Exception:
            traceback.print_exc()
            result = False
        if result is False:
            transition["pop_call_failed"] = True
        return True

    def _tick(self):
        self._tick_id += 1
        self._refresh_active_entry()
        if self._transition is not None:
            self._advance(self._tick_id)

    def _attach_screen(self, screen, params):
        if not isinstance(params, dict):
            return None
        if params.get(_PARAM_NAVIGATOR_ID) != self._navigator_id:
            return None
        entry = self._find_entry(params.get(_PARAM_ENTRY_KEY))
        if entry is None:
            return None
        entry._host = screen
        screen._navigator_active = False
        return entry

    def _screen_ready(self, entry):
        if entry is None:
            return
        entry._mounted = True
        self._refresh_active_entry()
        transition = self._transition
        if (transition is not None and
                transition["phase"] == _TransitionPhase.wait_push and
                transition["waiting_key"] == entry.key):
            self._finish(entry)

    def _screen_mount_failed(self, entry):
        if entry is None:
            return
        error = NavigationError(
            NavigationErrorCode.screen_mount_failed,
            "Pyreact Element could not be mounted",
        )
        transition = self._transition
        if (transition is not None and
                transition["phase"] == _TransitionPhase.wait_push and
                transition["waiting_key"] == entry.key):
            transition["kind"] = _TransitionKind.mount_cleanup
            transition["phase"] = _TransitionPhase.advance
            transition["target_key"] = entry.key
            transition["waiting_key"] = None
            transition["pending_error"] = error
            self._advance(self._tick_id)

    def _screen_destroyed(self, entry):
        if entry is None:
            return
        removed = self._remove_entry(entry.key)
        if removed is None:
            return
        removed._mounted = False
        removed._active = False
        self._release_slot(removed)
        transition = self._transition
        if transition is not None:
            transition["removed"].append(removed)
            if (transition["phase"] == _TransitionPhase.wait_push and
                    transition["waiting_key"] == removed.key):
                self._fail(
                    NavigationErrorCode.target_destroyed,
                    "pushed screen was destroyed before mounting",
                )
        else:
            self._deliver_passive_result(removed)
        self._refresh_active_entry()

    def _screen_active(self, entry, screen):
        if entry is None:
            return
        self._refresh_active_entry()
        if entry._active:
            host.PyreactScreenNode.OnActive(screen)

    def _screen_deactive(self, entry, screen):
        if entry is not None:
            entry._active = False
        screen._navigator_active = False
        host.PyreactScreenNode.OnDeactive(screen)

    def _actual_owned_top(self, snapshot=None):
        if snapshot is None:
            snapshot = self._top_snapshot()
        top_name, top_screen = snapshot
        for entry in reversed(self._entries):
            if entry._host is not top_screen:
                continue
            slot = entry._slot
            if top_name in (
                    slot.screen_name, slot.screen_def, slot.ui_name,
                    "navigatorScreenBase"):
                return entry
        return None

    def _is_actual_top(self, entry):
        return self._actual_owned_top() is entry

    def _top_snapshot(self):
        try:
            top_name = native.get_top_ui()
        except Exception:
            traceback.print_exc()
            top_name = None
        try:
            top_screen = native.get_top_screen()
        except Exception:
            traceback.print_exc()
            top_screen = None
        return (top_name, top_screen)

    def _refresh_active_entry(self):
        snapshot = self._top_snapshot()
        active = self._actual_owned_top(snapshot)
        if self._debug:
            signature = (
                snapshot[0],
                active.key if active is not None else None,
                id(snapshot[1]) if snapshot[1] is not None else None,
            )
            if signature != self._debug_top_signature:
                print "[pyreact.navigator] top=%r entry=%r screen=%r" % (
                    snapshot[0], signature[1], signature[2])
                self._debug_top_signature = signature
        for entry in self._entries:
            should_activate = entry is active
            was_active = entry._active
            entry._active = should_activate
            screen = entry._host
            if screen is None:
                continue
            screen._navigator_active = should_activate
            screen._pyreact_active = should_activate
            if should_activate and not was_active and entry._mounted:
                screen.schedule_layout()
        if active is not None and active._host is not None:
            host._ACTIVE_HOST[0] = active._host
        else:
            current = host._ACTIVE_HOST[0]
            if isinstance(current, NavigatorScreen):
                host._ACTIVE_HOST[0] = None

    def _acquire_slot(self):
        for slot in self._slots:
            if slot.registered and slot.entry_key is None:
                return slot
        return None

    @staticmethod
    def _release_slot(entry):
        slot = entry._slot
        if slot is not None and slot.entry_key == entry.key:
            slot.entry_key = None
        entry._slot = None
        entry._host = None

    def _find_entry(self, key):
        for entry in self._entries:
            if entry.key == key:
                return entry
        return None

    def _remove_entry(self, key):
        for index, entry in enumerate(self._entries):
            if entry.key == key:
                return self._entries.pop(index)
        return None

    def _finish(self, entry=None, force_none=False):
        transition = self._transition
        if transition is None:
            return
        callback = transition["on_complete"]
        self._deliver_transition_result(transition)
        self._transition = None
        self._refresh_active_entry()
        if force_none:
            entry = None
        elif entry is None:
            entry = self.top
        self._call_callback(callback, entry)

    def _fail(self, code, message):
        transition = self._transition
        if transition is None:
            return
        callback = transition["on_error"]
        self._deliver_transition_result(transition)
        self._transition = None
        self._refresh_active_entry()
        self._call_callback(callback, NavigationError(code, message))

    def _deliver_transition_result(self, transition):
        removed = transition["removed"]
        chosen = None
        for entry in reversed(removed):
            owner_alive = (
                entry._owner_key is None or
                self._find_entry(entry._owner_key) is not None)
            if chosen is None and owner_alive:
                chosen = entry
            else:
                entry._result_called = True
        if chosen is not None:
            self._deliver_result(chosen, transition["result"])

    def _deliver_passive_result(self, entry):
        if (entry._owner_key is None or
                self._find_entry(entry._owner_key) is not None):
            self._deliver_result(entry, None)
        else:
            entry._result_called = True

    def _deliver_result(self, entry, result):
        if entry._result_called:
            return
        entry._result_called = True
        self._call_callback(entry._on_result, result)

    def _reject(self, code, message, on_error):
        self._call_callback(on_error, NavigationError(code, message))
        return False

    @staticmethod
    def _call_callback(callback, value):
        if not callable(callback):
            return
        try:
            callback(value)
        except Exception:
            traceback.print_exc()


class NavigatorScreen(host.PyreactScreenNode):
    """16 个自动注册 Screen 槽位共用的宿主类。"""

    def __init__(self, namespace, name, params):
        host.PyreactScreenNode.__init__(self, namespace, name, params)
        self._navigator_active = False
        self._navigation_entry = navigator._attach_screen(self, params)

    def Create(self):
        entry = self._navigation_entry
        if entry is None:
            return
        self._debug_mode = navigator._debug
        if host._mount_element(entry.element, self, native.ROOT_PATH):
            navigator._screen_ready(entry)
        else:
            navigator._screen_mount_failed(entry)

    def OnActive(self):
        navigator._screen_active(self._navigation_entry, self)

    def OnDeactive(self):
        navigator._screen_deactive(self._navigation_entry, self)

    def Update(self):
        navigator._refresh_active_entry()
        if self._navigator_active:
            host.PyreactScreenNode.Update(self)

    def Destroy(self):
        entry = self._navigation_entry
        try:
            host.PyreactScreenNode.Destroy(self)
        finally:
            navigator._screen_destroyed(entry)


navigator = Navigator()
