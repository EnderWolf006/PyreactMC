# -*- coding: utf-8 -*-
"""调试支持：剪贴板 IPC，UI 树 dump、交互模拟和原生控件状态修改。

通过剪贴板与外部脚本通信（轮询模式，挂在 PyreactScreenNode.Update 每帧）。
外部脚本写请求 JSON 到剪贴板，本模块轮询读取、执行、写回响应 JSON。

协议：
  请求 {"pyreact_debug":{"cmd":"dump_tree|...|navigator|ping","id":"<node_id>","value":"...","seq":1}}
  响应 {"pyreact_ack":true,"tree":{...},"seq":1,"error":null}

layout/opacity 数据来自 LayoutNode 快照（debug 模式下 host._debug_layout_nodes，
由 layout_tree 完成后保留）。Fiber 不存 layout 字段，零侵入。
"""
import json
import traceback as _tb


# AppReady 信号：UI 首次挂载完成后 print 此字符串，launch_game 的 _poll_ready
# 检测 log_server 日志中的该信号即退出等待（避免 60s 超时 fallback）。
READY_SIGNAL = '=====> PyreactRuntime AppReady:'
_LAST_REQUEST_SEQ = [None]


def notify_ready():
    """UI 首次挂载完成后调用，发 AppReady 信号给 launch_game。"""
    print(READY_SIGNAL)


def _get_game(host):
    """lazy 获取 ModSDK Game 组件（剪贴板访问）。"""
    if host._debug_game is None:
        import mod.client.extraClientApi as clientApi
        host._debug_game = clientApi.GetEngineCompFactory().CreateGame(
            clientApi.GetLevelId())
    return host._debug_game


def _type_name(fiber):
    """fiber 对外类型名：primitive strip 'Primitive' 后缀，component 用 __name__。"""
    comp = fiber.comp_type
    from .primitives import Primitive
    if isinstance(comp, Primitive):
        return comp.__class__.__name__.replace("Primitive", "")
    name = getattr(comp, "__name__", None)
    if name:
        return name
    return type(comp).__name__


def _sanitize(value):
    """把任意值转为 JSON 安全的标量/容器。

    函数 -> '<function>'，Color 对象 -> {r,g,b,a}，dict/list 递归，
    其余 repr 截断兜底（避免函数/对象 props 破坏 JSON 序列化）。
    """
    if value is None or isinstance(value, (bool, int, float, basestring)):
        return value
    if callable(value):
        return "<function>"
    # Color 对象：有 r/g/b/a 属性
    if (hasattr(value, "r") and hasattr(value, "g")
            and hasattr(value, "b") and hasattr(value, "a")):
        return {"r": value.r, "g": value.g, "b": value.b, "a": value.a}
    if isinstance(value, dict):
        return {k: _sanitize(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_sanitize(v) for v in value]
    # 枚举/其他对象：repr 截断
    try:
        r = repr(value)
        if len(r) > 80:
            r = r[:80] + "..."
        return r
    except Exception:
        return "<unknown>"


def _sanitize_dict(d):
    if d is None:
        return {}
    if not isinstance(d, dict):
        return _sanitize(d)
    return {k: _sanitize(v) for k, v in d.items()}


def _style_to_dict(style):
    """Style 对象 -> dict（遍历 _set_keys）。"""
    if style is None:
        return {}
    keys = getattr(style, "_set_keys", None)
    if not keys:
        return {}
    out = {}
    for k in keys:
        if hasattr(style, k):
            out[k] = _sanitize(getattr(style, k))
    return out


def serialize_fiber(fiber, layout_map):
    """序列化 fiber 为 dict。

    component fiber 无 native 控件，在 layout_map 中无对应 LayoutNode，
    layout/opacity 省略（准确反映 component 是逻辑节点不参与原生布局）；
    primitive fiber 从 layout_map 取 LayoutNode 拿 frame/opacity。

    :param layout_map: {id(fiber): LayoutNode} 映射，由 _build_layout_map 生成。
    """
    if fiber is None:
        return None
    nid = fiber.native_name or fiber.native_path
    if not nid:
        nid = "<%s>" % _type_name(fiber)
    out = {
        "id": nid,
        "type": _type_name(fiber),
        "props": _sanitize_dict(fiber.props),
        "style": _style_to_dict(fiber.style),
        "children": [],
    }
    ln = layout_map.get(id(fiber)) if layout_map else None
    if ln is not None:
        out["layout"] = {
            "x": ln.frame_x,
            "y": ln.frame_y,
            "width": ln.frame_w,
            "height": ln.frame_h,
        }
        out["opacity"] = ln.inherited_opacity
    for cf in fiber.child_fibers:
        out["children"].append(serialize_fiber(cf, layout_map))
    return out


def find_fiber_by_id(root_fiber, node_id):
    """递归找 native_name == node_id 的 fiber。"""
    if root_fiber is None:
        return None
    if root_fiber.native_name is not None and root_fiber.native_name == node_id:
        return root_fiber
    for cf in root_fiber.child_fibers:
        found = find_fiber_by_id(cf, node_id)
        if found is not None:
            return found
    return None


def dispatch_click(host, root_fiber, node_id):
    """模拟点击：找 fiber，调其 on_click 回调（host._button_handlers[path][2]）。"""
    fiber = find_fiber_by_id(root_fiber, node_id)
    if fiber is None:
        return {"ok": False, "error": "fiber not found: %s" % node_id}
    path = fiber.native_path
    handlers = host._button_handlers.get(path) if path else None
    if not handlers:
        return {"ok": False, "error": "no button handler at path: %s" % path}
    on_click = handlers[2]
    if on_click is None:
        return {"ok": False, "error": "no on_click callback"}
    try:
        on_click()
        return {"ok": True, "error": None}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def dispatch_input(host, root_fiber, node_id, value):
    """设置 Input 原生文本，并通过宿主的正常 onChange 路径分发。"""
    fiber = find_fiber_by_id(root_fiber, node_id)
    if fiber is None:
        return {"ok": False, "error": "fiber not found: %s" % node_id}

    from .primitives import InputPrimitive
    if not isinstance(fiber.comp_type, InputPrimitive):
        return {"ok": False, "error": "node is not Input: %s" % node_id}

    control = host.GetBaseUIControl(fiber.native_path)
    if control is None:
        return {"ok": False, "error": "input control not found: %s" % fiber.native_path}
    edit_box = control.asTextEditBox()
    if edit_box is None:
        return {"ok": False, "error": "control is not text edit box: %s" % node_id}

    if value is None:
        value = ""
    if isinstance(value, unicode):
        text = value.encode("utf-8")
    elif isinstance(value, str):
        text = value
    else:
        text = str(value)

    try:
        edit_box.SetEditText(text)
    except Exception as e:
        return {"ok": False, "error": "SetEditText failed: %s" % e}

    # Force the same text-diff path used by BF_EditChanged/BF_EditFinished.
    host.pyreact_set_input_value(fiber.native_path, None)
    host._pyreact_dispatch_input_change({"Text": text})
    return {"ok": True, "value": text}


def dispatch_slider(host, root_fiber, node_id, value):
    """设置 Slider 原生值，并通过宿主的正常 onChange 路径分发。"""
    fiber = find_fiber_by_id(root_fiber, node_id)
    if fiber is None:
        return {"ok": False, "error": "fiber not found: %s" % node_id}

    from .primitives import SliderPrimitive
    if not isinstance(fiber.comp_type, SliderPrimitive):
        return {"ok": False, "error": "node is not Slider: %s" % node_id}

    control = host.GetBaseUIControl(fiber.native_path)
    if control is None:
        return {"ok": False,
                "error": "slider control not found: %s" % fiber.native_path}
    slider = control.asSlider()
    if slider is None:
        return {"ok": False, "error": "control is not slider: %s" % node_id}

    try:
        target = float(value)
    except (TypeError, ValueError):
        return {"ok": False, "error": "invalid slider value: %s" % value}

    try:
        before = float(slider.GetSliderValue())
        bag = control.GetPropertyBag()
        if not isinstance(bag, dict):
            bag = {}
        else:
            bag = dict(bag)
        bag["#slider_value"] = target
        control.SetPropertyBag(bag)
        slider.SetSliderValue(target)
        current = float(slider.GetSliderValue())
    except Exception as e:
        return {"ok": False, "error": "SetSliderValue failed: %s" % e}

    # Force the same value-diff path used by BF_SliderChanged/BF_SliderFinished.
    host.pyreact_set_slider_value(fiber.native_path, None)
    host._pyreact_dispatch_slider_change(current, False)
    return {"ok": True, "before": before, "value": current,
            "target": target}


def dispatch_scroll(host, root_fiber, node_id, position=None):
    """读取或设置 ScrollView 的像素滚动位置。"""
    fiber = find_fiber_by_id(root_fiber, node_id)
    if fiber is None:
        return {"ok": False, "error": "fiber not found: %s" % node_id}

    from .primitives import ScrollViewPrimitive
    if not isinstance(fiber.comp_type, ScrollViewPrimitive):
        return {"ok": False, "error": "node is not ScrollView: %s" % node_id}

    control = host.GetBaseUIControl(fiber.native_path)
    if control is None:
        return {"ok": False,
                "error": "scroll control not found: %s" % fiber.native_path}

    before = ScrollViewPrimitive.get_scroll_position(control)
    if before is None:
        return {"ok": False, "error": "GetScrollViewPos failed: %s" % node_id}
    if position is None:
        return {"ok": True, "position": before}

    try:
        target = float(position)
    except (TypeError, ValueError):
        return {"ok": False, "error": "invalid scroll position: %s" % position}

    if not ScrollViewPrimitive.scroll_to(control, target):
        return {"ok": False, "error": "SetScrollViewPos failed: %s" % node_id}
    current = ScrollViewPrimitive.get_scroll_position(control)
    if current is None:
        return {"ok": False, "error": "GetScrollViewPos failed: %s" % node_id}
    return {"ok": True, "before": before, "position": current,
            "target": target}


def _build_layout_map(host):
    """从 host._debug_layout_nodes（LayoutNode forest）建 {id(fiber): LayoutNode}。

    LayoutNode 树穿透 component 只含 primitive，是 fiber 树的子集。
    此 map 让 serialize_fiber O(1) 查 primitive fiber 的 LayoutNode，
    component fiber 不在 map 中（layout 自然省略）。
    """
    m = {}
    nodes = host._debug_layout_nodes
    if not nodes:
        return m
    stack = list(nodes)
    while stack:
        ln = stack.pop()
        if ln is None:
            continue
        if ln.fiber is not None:
            m[id(ln.fiber)] = ln
        for c in ln.children:
            stack.append(c)
    return m


def navigator_state():
    """返回不含 Element/host 引用的 JSON 安全 navigator 快照。"""
    from .navigator import navigator

    entries = []
    for entry in navigator.get_entries():
        slot = entry._slot
        entries.append({
            "key": entry.key,
            "is_active": entry.is_active,
            "is_mounted": entry._mounted,
            "slot": slot.index if slot is not None else None,
            "ui_name": slot.ui_name if slot is not None else None,
            "screen_name": slot.screen_name if slot is not None else None,
        })
    transition = navigator._transition
    transition_state = None
    if transition is not None:
        transition_state = {
            "kind": transition.get("kind"),
            "phase": transition.get("phase"),
            "target_key": transition.get("target_key"),
            "waiting_key": transition.get("waiting_key"),
            "remaining": transition.get("remaining"),
        }
    top = navigator.top
    return {
        "is_ready": navigator.is_ready,
        "capacity": navigator.capacity,
        "available_slots": navigator.available_slots,
        "depth": navigator.depth,
        "top_key": top.key if top is not None else None,
        "top_ui_name": navigator.top_ui_name,
        "is_transitioning": navigator.is_transitioning,
        "can_go_back": navigator.can_go_back(),
        "transition": transition_state,
        "entries": entries,
    }


def dispatch_navigator(value):
    """执行 pyreact-debug navigator 命令并返回即时接收状态。"""
    from .navigator import navigator

    if not isinstance(value, dict):
        return {"ok": False, "error": "navigator requires an action object"}
    action = value.get("action")
    errors = []

    def on_error(error):
        errors.append(error)

    if action == "status":
        return {"ok": True, "action": action, "state": navigator_state()}
    if action == "pop":
        accepted = navigator.pop(
            count=value.get("count", 1), on_error=on_error)
    elif action == "pop_to":
        key = value.get("key")
        if not isinstance(key, basestring) or not key:
            return {"ok": False, "error": "pop_to requires a non-empty key"}
        accepted = navigator.pop_to(key, on_error=on_error)
    elif action == "pop_to_top":
        accepted = navigator.pop_to_top(on_error=on_error)
    elif action == "clear":
        accepted = navigator.clear(on_error=on_error)
    elif action == "close":
        accepted = navigator.close(on_error=on_error)
    else:
        return {"ok": False, "error": "unknown navigator action: %s" % action}

    if errors:
        error = errors[0]
        return {
            "ok": False,
            "accepted": False,
            "action": action,
            "error": str(error),
            "error_code": getattr(error, "code", None),
            "state": navigator_state(),
        }
    return {
        "ok": bool(accepted),
        "accepted": bool(accepted),
        "action": action,
        "state": navigator_state(),
    }


def poll_clipboard(host):
    """轮询剪贴板，执行 debug 请求，写回响应。全程不抛异常。"""
    if host._root_fiber is None:
        return
    game = _get_game(host)
    if game is None:
        return
    try:
        content = game.GetClipboardContent()
    except Exception:
        return
    if not content:
        return
    try:
        data = json.loads(content)
    except Exception:
        return  # 非 JSON，忽略（不干扰其他剪贴板用途）
    req = data.get("pyreact_debug") if isinstance(data, dict) else None
    if not isinstance(req, dict):
        return  # 非 debug 请求，不处理
    cmd = req.get("cmd")
    seq = req.get("seq")
    # push/pop 可在当前回调尚未写响应时同步创建新 Screen。先认领 seq，
    # 防止新 host 重入轮询同一请求并覆盖原 host 的正确响应。
    if seq is not None and _LAST_REQUEST_SEQ[0] == seq:
        return
    if seq is not None:
        _LAST_REQUEST_SEQ[0] = seq
    node_id = req.get("id")
    resp = {"pyreact_ack": True, "seq": seq}
    try:
        if cmd == "ping":
            pass
        elif cmd == "dump_tree":
            resp["tree"] = serialize_fiber(host._root_fiber, _build_layout_map(host))
        elif cmd == "dump_subtree":
            if not node_id:
                resp["pyreact_ack"] = False
                resp["error"] = "dump_subtree requires 'id'"
            else:
                fiber = find_fiber_by_id(host._root_fiber, node_id)
                if fiber is None:
                    resp["pyreact_ack"] = False
                    resp["error"] = "fiber not found: %s" % node_id
                else:
                    resp["tree"] = serialize_fiber(fiber, _build_layout_map(host))
        elif cmd == "click":
            if not node_id:
                resp["pyreact_ack"] = False
                resp["error"] = "click requires 'id'"
            else:
                result = dispatch_click(host, host._root_fiber, node_id)
                resp["result"] = result
                if not result.get("ok"):
                    resp["pyreact_ack"] = False
                    resp["error"] = result.get("error")
        elif cmd == "set_input":
            if not node_id:
                resp["pyreact_ack"] = False
                resp["error"] = "set_input requires 'id'"
            elif "value" not in req:
                resp["pyreact_ack"] = False
                resp["error"] = "set_input requires 'value'"
            else:
                result = dispatch_input(host, host._root_fiber, node_id, req.get("value"))
                resp["result"] = result
                if not result.get("ok"):
                    resp["pyreact_ack"] = False
                    resp["error"] = result.get("error")
        elif cmd == "set_slider":
            if not node_id:
                resp["pyreact_ack"] = False
                resp["error"] = "set_slider requires 'id'"
            elif "value" not in req:
                resp["pyreact_ack"] = False
                resp["error"] = "set_slider requires 'value'"
            else:
                result = dispatch_slider(
                    host, host._root_fiber, node_id, req.get("value"))
                resp["result"] = result
                if not result.get("ok"):
                    resp["pyreact_ack"] = False
                    resp["error"] = result.get("error")
        elif cmd == "scroll":
            if not node_id:
                resp["pyreact_ack"] = False
                resp["error"] = "scroll requires 'id'"
            elif "value" not in req:
                resp["pyreact_ack"] = False
                resp["error"] = "scroll requires 'value'"
            else:
                result = dispatch_scroll(
                    host, host._root_fiber, node_id, req.get("value"))
                resp["result"] = result
                if not result.get("ok"):
                    resp["pyreact_ack"] = False
                    resp["error"] = result.get("error")
        elif cmd == "get_scroll":
            if not node_id:
                resp["pyreact_ack"] = False
                resp["error"] = "get_scroll requires 'id'"
            else:
                result = dispatch_scroll(host, host._root_fiber, node_id)
                resp["result"] = result
                if not result.get("ok"):
                    resp["pyreact_ack"] = False
                    resp["error"] = result.get("error")
        elif cmd == "navigator":
            result = dispatch_navigator(req.get("value"))
            resp["result"] = result
            if not result.get("ok"):
                resp["pyreact_ack"] = False
                resp["error"] = result.get("error")
        else:
            resp["pyreact_ack"] = False
            resp["error"] = "unknown cmd: %s" % cmd
    except Exception as e:
        resp["pyreact_ack"] = False
        resp["error"] = str(e)
        _tb.print_exc()
    try:
        game.SetClipboardContent(json.dumps(resp))
    except Exception:
        pass
