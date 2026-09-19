# -*- coding: utf-8 -*-
"""Python 2-compatible adapter executed inside MCDK's client-side IPC."""


def pyreact_request(req, module_name=None):
    import importlib
    import sys

    if module_name is None:
        candidates = [name for name, module in list(sys.modules.items())
                      if (name == "pyreact.host" or name.endswith(".pyreact.host"))
                      and hasattr(module, "_ACTIVE_HOST")]
        if len(candidates) != 1:
            raise RuntimeError("Expected one loaded Pyreact host module; set PYREACT_MODULE "
                               "to its package path. Found: %s" % candidates)
        module_name = candidates[0].rsplit(".", 1)[0]
    host_module = importlib.import_module(module_name + ".host")
    debug = importlib.import_module(module_name + ".debug")
    if not host_module._RUNTIME_DEBUG[0]:
        raise RuntimeError("Enable debug=True at the first pyreact.runtime_init call")
    cmd = req["cmd"]
    response = {"pyreact_ack": True, "seq": req["seq"]}
    if cmd == "navigator":
        result = debug.dispatch_navigator(req.get("value"))
    elif cmd == "ping":
        return response
    else:
        host = host_module._ACTIVE_HOST[0]
        if host is None or host._root_fiber is None:
            raise RuntimeError("No active Pyreact root; open the target UI first")
        root = host._root_fiber
        node_id = req.get("id")
        if cmd in ("dump_tree", "dump_subtree"):
            if cmd == "dump_subtree":
                root = debug.find_fiber_by_id(root, node_id)
                if root is None:
                    raise RuntimeError("fiber not found: %s" % node_id)
            response["tree"] = debug.serialize_fiber(root, debug._build_layout_map(host))
            return response
        if not node_id:
            raise ValueError("%s requires a node id" % cmd)
        dispatchers = {"click": debug.dispatch_click, "set_input": debug.dispatch_input,
                       "set_slider": debug.dispatch_slider, "scroll": debug.dispatch_scroll,
                       "get_scroll": debug.dispatch_scroll}
        if cmd not in dispatchers:
            raise ValueError("Unknown Pyreact command: %s" % cmd)
        args = [host, root, node_id]
        if cmd in ("set_input", "set_slider", "scroll"):
            args.append(req["value"])
        result = dispatchers[cmd](*args)
    response["result"] = result
    if not result.get("ok"):
        response["pyreact_ack"] = False
        response["error"] = result.get("error") or "Pyreact command rejected"
    return response
