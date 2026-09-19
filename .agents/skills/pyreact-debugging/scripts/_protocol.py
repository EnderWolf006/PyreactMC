"""Pyreact commands transported through MCDevTool execute_code, never clipboard."""
import json
import os
from pathlib import Path
import uuid

from mcdk import Client, MCDKError, return_value


def request(cmd, node_id=None, value=None, timeout=5.0):
    payload = {"cmd": cmd, "seq": uuid.uuid4().hex}
    if node_id is not None:
        payload["id"] = node_id
    if value is not None:
        payload["value"] = value
    source = Path(__file__).with_name("_game_bridge.py").read_text(encoding="utf-8")
    code = (
        "import json\n"
        "_pyr_scope = {}\n"
        "eval(compile(%s, '<pyreact-mcdk>', 'exec'), _pyr_scope)\n"
        "_result = json.dumps(_pyr_scope['pyreact_request'](json.loads(%s), json.loads(%s)))\n"
    ) % (repr(source), repr(json.dumps(payload)), repr(json.dumps(os.environ.get("PYREACT_MODULE"))))
    try:
        with Client(timeout=timeout) as client:
            result = return_value(client.call("execute_code", {
                "code": code, "is_client": True, "direct_return": True}))
        # MCDK limits returned object nesting to 8; carry the tree as JSON text.
        if isinstance(result, str):
            result = json.loads(result)
        if not isinstance(result, dict) or result.get("seq") != payload["seq"]:
            raise MCDKError("Invalid Pyreact response or mismatched request id")
        if not result.get("pyreact_ack") or result.get("error"):
            raise MCDKError(result.get("error") or "Pyreact command rejected")
        return result
    except Exception as exc:
        # All legacy CLI consumers treat None as failure (some do not check ack).
        import sys
        print("[mcdk] %s" % exc, file=sys.stderr)
        return None
