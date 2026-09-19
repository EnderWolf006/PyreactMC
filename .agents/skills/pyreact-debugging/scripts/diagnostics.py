"""Bounded, read-only diagnostics for an explicitly owned MCDK session."""
import argparse
import base64
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

from mcdk import Client, MCDKError, return_value


def session_artifacts():
    if not os.environ.get("MCDEV_SESSION_FILE") or not os.environ.get("MCDEV_OWNER"):
        raise ValueError("Bind MCDEV_SESSION_FILE and MCDEV_OWNER before running workflows")
    from _session import artifact_dir
    return Path(artifact_dir())


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def bounded_process(command, timeout, cwd):
    """Kill the local worker at the deadline; never replay its remote operation."""
    started = time.monotonic()
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    try:
        result = subprocess.run(command, cwd=str(cwd), stdin=subprocess.DEVNULL,
                                capture_output=True, timeout=timeout, creationflags=flags)
        record = {"ok": result.returncode == 0, "returncode": result.returncode,
                  "stdout": result.stdout.decode("utf-8", errors="replace"),
                  "stderr": result.stderr.decode("utf-8", errors="replace")}
    except subprocess.TimeoutExpired as exc:
        record = {"ok": False, "timeout": True, "outcome": "unknown; remote operation may have completed",
                  "stdout": (exc.stdout or b"").decode("utf-8", errors="replace"),
                  "stderr": (exc.stderr or b"").decode("utf-8", errors="replace")}
    except OSError as exc:
        record = {"ok": False, "error": str(exc)}
    record["elapsed_seconds"] = round(time.monotonic() - started, 3)
    return record


def probe(name, timeout):
    session_artifacts()
    if name == "pyreact":
        from _protocol import request
        result = request("dump_tree", timeout=timeout)
        if result is None:
            raise MCDKError("Pyreact debug tree unavailable")
        return result
    with Client(timeout=timeout) as client:
        if name == "tools":
            return client._post("tools/list")
        if name in ("client", "server"):
            result = return_value(client.call("execute_code", {
                "code": "_result = {'mcdk_probe': True}",
                "is_client": name == "client", "direct_return": True}))
            if result != {"mcdk_probe": True}:
                raise MCDKError("Unexpected IPC probe response")
            return result
        if name == "screens":
            return client.call("jsonui_debugger", {"cmd": "/screens"})
        if name == "capture":
            result = client.call("capture_game_window", {})
            block = next(b for b in result["content"] if b.get("type") == "image")
            if block.get("mimeType") != "image/jpeg":
                raise MCDKError("Expected JPEG screenshot")
            # Worker cwd is the unique run directory, never a caller-selected path.
            Path("capture.jpg").write_bytes(base64.b64decode(block["data"], validate=True))
            return {"path": str(Path("capture.jpg").resolve()), "mimeType": "image/jpeg"}
        tool = {"logs": "get_latest_logs", "errors": "get_latest_error_logs"}[name]
        return client.call(tool, {"max_count": 100, "order": "desc"})


def diagnose(timeout=15, pyreact=False, capture=False):
    root = session_artifacts()
    run_id = uuid.uuid4().hex
    output = root / "diagnostics" / run_id
    output.mkdir(parents=True, exist_ok=False)
    report = {"run_id": run_id, "session_file": os.environ["MCDEV_SESSION_FILE"],
              "owner": os.environ["MCDEV_OWNER"], "ok": True, "probes": []}
    names = ["tools", "client", "server", "screens", "logs", "errors"]
    if pyreact:
        names.append("pyreact")
    if capture:
        names.append("capture")
    for name in names:
        record = bounded_process([sys.executable, "-X", "utf8", str(Path(__file__).resolve()),
                                  "--_probe", name, "--timeout", str(timeout)], timeout, output)
        record["name"] = name
        report["probes"].append(record)
        report["ok"] = report["ok"] and record["ok"]
        write_json(output / (name + ".json"), record)
        write_json(output / "evidence.json", report)
    return report, output / "evidence.json"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout", type=float, default=15, help="hard deadline per probe, 0-120 seconds")
    parser.add_argument("--pyreact", action="store_true")
    parser.add_argument("--capture", action="store_true", help="save a screenshot only when requested")
    parser.add_argument("--_probe", choices=["tools", "client", "server", "screens", "logs", "errors", "pyreact", "capture"], help=argparse.SUPPRESS)
    args = parser.parse_args()
    if not 0 < args.timeout <= 120:
        parser.error("timeout must be greater than zero and at most 120 seconds")
    try:
        if args._probe:
            print(json.dumps(probe(args._probe, args.timeout), ensure_ascii=False))
            return 0
        report, evidence = diagnose(args.timeout, args.pyreact, args.capture)
        print(json.dumps({"ok": report["ok"], "run_id": report["run_id"], "evidence": str(evidence)}))
        return 0 if report["ok"] else 1
    except Exception as exc:
        print("[diagnostics] %s" % exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
