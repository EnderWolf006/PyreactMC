"""Client for MCDevTool's JSON-response /mcp endpoint (stdlib only)."""
import argparse
import base64
import json
import os
from pathlib import Path
import sys
import time
import urllib.request
from _session import load_session, desktop_lock, registry_dir, write_json


class MCDKError(RuntimeError):
    pass


class RPCError(MCDKError):
    def __init__(self, error):
        self.error = error
        super().__init__(json.dumps(error, ensure_ascii=False))


class Client:
    def __init__(self, url=None, timeout=15, bind_session=True):
        self.binding = load_session(live=True) if bind_session else None
        if self.binding:
            expected = self.binding["mcp_url"]
            for supplied in (url, os.environ.get("MCDEV_MCP_URL")):
                if supplied and supplied != expected:
                    raise MCDKError("Endpoint conflicts with assigned instance")
            self.url = expected
        else:
            self.url = url or os.environ.get("MCDEV_MCP_URL", "http://127.0.0.1:19133/mcp")
        self.timeout = timeout
        self.session = None
        self.counter = 0
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def _post(self, method, params=None, notification=False):
        self.counter += 1
        payload = {"jsonrpc": "2.0", "method": method, "params": params or {}}
        if not notification:
            payload["id"] = self.counter
        headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
        if self.session:
            headers["Mcp-Session-Id"] = self.session
        request = urllib.request.Request(self.url, json.dumps(payload).encode("utf-8"), headers)
        # A timeout can follow a successful mutation. Never replay tool calls.
        with self.opener.open(request, timeout=self.timeout) as response:
            if method == "initialize":
                self.session = response.headers.get("Mcp-Session-Id")
            raw = response.read()
        if notification:
            return None
        result = json.loads(raw)
        if result.get("id") != payload["id"]:
            raise MCDKError("Mismatched JSON-RPC response id")
        if "error" in result:
            raise RPCError(result["error"])
        return result["result"]

    def __enter__(self):
        try:
            self._post("initialize", {"protocolVersion": "2025-03-26", "capabilities": {},
                                     "clientInfo": {"name": "pyreact-debugging", "version": "1"}})
            if not self.session:
                raise MCDKError("MCDK did not return Mcp-Session-Id; use its /mcp endpoint")
            self._post("notifications/initialized", notification=True)
            # MCDK processes the notification on a worker. Probe with a read
            # before sending any mutation; only this readiness read may retry.
            deadline = time.monotonic() + min(self.timeout, 2)
            while True:
                try:
                    self._post("tools/list")
                    break
                except RPCError as exc:
                    if (exc.error.get("message") != "Session not initialized"
                            or time.monotonic() >= deadline):
                        raise
                    time.sleep(0.02)
            self._verify_binding()
            return self
        except Exception:
            self.close()
            raise

    def close(self):
        if self.session:
            try:
                request = urllib.request.Request(self.url, method="DELETE",
                                                 headers={"Mcp-Session-Id": self.session})
                with self.opener.open(request, timeout=min(self.timeout, 2)):
                    pass
            except Exception:
                pass
            self.session = None

    def __exit__(self, *exc):
        self.close()

    def _verify_binding(self):
        if not self.binding:
            return
        load_session(live=True)
        result = self._post("tools/call", {"name": "execute_code", "arguments": {
            "code": "import sys\n_result = getattr(sys, '_pyreact_mcdk_session', None)",
            "is_client": True, "direct_return": True}})
        if return_value(result) != self.binding["token"]:
            raise MCDKError("Game session marker changed; refuse stale or misrouted command")

    def call(self, name, arguments):
        self._verify_binding()
        if name == "mc_input" and arguments.get("op") not in ("/help", "/state"):
            options = dict(arguments.get("args") or {})
            if options.get("focus") == "keep" or options.get("leave_held"):
                raise MCDKError("Shared desktop requires focus checking and leave_held=false")
            budget = options.get("budget_ms", 5000)
            if not isinstance(budget, int) or not 1 <= budget <= 30000:
                raise MCDKError("Input budget_ms must be 1..30000")
            if self.timeout < budget / 1000.0 + 5:
                raise MCDKError("Input timeout must exceed budget_ms by at least 5 seconds")
            if arguments.get("op") != "/release-all":
                options["budget_ms"] = budget
                options.setdefault("focus", "auto")
                arguments = dict(arguments, args=options)
            with desktop_lock():
                lease = registry_dir() / "desktop-lease.json"
                if lease.exists() and json.loads(lease.read_text()).get("until", 0) > time.time():
                    raise MCDKError("Desktop input still reserved after an uncertain call; retry later")
                write_json(lease, {"until": time.time() + budget / 1000.0 + 10})
                # Preserve the lease on timeout/disconnect: queued input may still execute.
                result = self._post("tools/call", {"name": name, "arguments": arguments})
                write_json(lease, {"until": 0})
        else:
            result = self._post("tools/call", {"name": name, "arguments": arguments})
        if result.get("isError"):
            raise MCDKError(json.dumps(result, ensure_ascii=False))
        structured = result.get("structuredContent")
        if isinstance(structured, dict) and structured.get("ok") is False:
            raise MCDKError(json.dumps(structured, ensure_ascii=False))
        return result


def return_value(result):
    """Decode execute_code's explicit return marker, not arbitrary log braces."""
    structured = result.get("structuredContent")
    if isinstance(structured, dict) and "return_value" in structured:
        return structured["return_value"]
    for block in result.get("content", []):
        if block.get("type") != "text":
            continue
        marker = "\nReturn value JSON: "
        text = block.get("text", "")
        if marker in text:
            return json.loads(text.rsplit(marker, 1)[1])
    raise MCDKError("execute_code returned no value; require direct_return=true and assign _result")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", help="MCDK /mcp URL; defaults to MCDEV_MCP_URL or localhost:19133/mcp")
    parser.add_argument("--timeout", type=float, default=15)
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("tools", help="discover installed tool schemas")
    call = sub.add_parser("call")
    call.add_argument("tool")
    call.add_argument("--args-file", help="UTF-8 JSON object file; omit for empty arguments")
    code = sub.add_parser("exec")
    code.add_argument("file", help="UTF-8 Python 2 source assigning _result")
    code.add_argument("--server", action="store_true")
    capture = sub.add_parser("capture")
    capture.add_argument("--output", required=True, help="output JPEG path")
    args = parser.parse_args()
    try:
        with Client(args.url, args.timeout) as client:
            if args.action == "tools":
                result = client._post("tools/list")
            elif args.action == "exec":
                result = return_value(client.call("execute_code", {
                    "code": Path(args.file).read_text(encoding="utf-8-sig"),
                    "is_client": not args.server, "direct_return": True}))
            elif args.action == "capture":
                result = client.call("capture_game_window", {})
                block = next(b for b in result["content"] if b.get("type") == "image")
                if block.get("mimeType") != "image/jpeg":
                    raise MCDKError("Unexpected screenshot format: " + str(block.get("mimeType")))
                output = Path(args.output).resolve()
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_bytes(base64.b64decode(block["data"], validate=True))
                result = {"path": str(output), "mimeType": block["mimeType"]}
            else:
                arguments = json.loads(Path(args.args_file).read_text(encoding="utf-8-sig")) if args.args_file else {}
                if not isinstance(arguments, dict):
                    raise ValueError("arguments must be a JSON object")
                result = client.call(args.tool, arguments)
        sys.stdout.buffer.write((json.dumps(result, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
        return 0
    except Exception as exc:
        print("[mcdk] %s" % exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
