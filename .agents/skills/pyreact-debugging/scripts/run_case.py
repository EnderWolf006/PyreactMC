"""Run a JSON regression case against one explicitly bound MCDK session.

Example: {"steps": [{"code_file": "check.py", "server": false,
                     "path": ["players", 0, "ready"], "expect": true}]}
Script steps use {"script": "get_ui_tree.py", "argv": ["--json"]}.
At least one real assertion is required. A failed/timed-out step stops the case.
"""
import argparse
import json
import os
from pathlib import Path
import sys
import uuid

from diagnostics import bounded_process, session_artifacts, write_json
from mcdk import Client, return_value

SCRIPTS = Path(__file__).resolve().parent
ALLOWED = {"get_ui_tree.py", "simulate.py", "simulate_and_diff.py",
           "navigator.py", "query_tree.py", "expect.py"}
TREE_WRITERS = {"get_ui_tree.py", "simulate_and_diff.py"}
# These workflows own routing and evidence paths. No argparse abbreviation
# can select another target because target-capable launch/MCP/window CLIs
# are absent from the whitelist.
FORBIDDEN = {"--url", "--session", "--owner", "--pid", "--title", "--project",
             "--output", "--output-before", "--output-after", "--file", "--help", "-h"}


def validate(case, directory, timeout):
    if not isinstance(case, dict) or set(case) - {"name", "steps", "timeout"}:
        raise ValueError("case supports only name, steps and timeout")
    steps = case.get("steps")
    if not isinstance(steps, list) or not 1 <= len(steps) <= 128:
        raise ValueError("case needs 1-128 steps")
    default_timeout = case.get("timeout", timeout)
    assertions = 0
    fresh_tree = False
    validated = []
    for index, item in enumerate(steps):
        if not isinstance(item, dict):
            raise ValueError("step %d must be an object" % index)
        step = dict(item)
        limit = step.get("timeout", default_timeout)
        if isinstance(limit, bool) or not isinstance(limit, (int, float)) or not 0 < limit <= 120:
            raise ValueError("step timeout must be greater than zero and at most 120 seconds")
        step["timeout"] = limit
        if "script" in step:
            if set(step) - {"script", "argv", "timeout"} or step["script"] not in ALLOWED:
                raise ValueError("step %d: script is not whitelisted or has unsupported keys" % index)
            argv = step.get("argv", [])
            if not isinstance(argv, list) or not all(isinstance(arg, str) for arg in argv):
                raise ValueError("argv must be an array of strings, never a shell command")
            if any(arg.split("=", 1)[0] in FORBIDDEN or
                   (arg.startswith("--") and any(flag.startswith(arg.split("=", 1)[0]) for flag in FORBIDDEN))
                   for arg in argv):
                raise ValueError("case cannot override routing, files, or bypass assertions with help")
            step["argv"] = argv
            if step["script"] == "expect.py":
                if not fresh_tree:
                    raise ValueError("expect.py requires a fresh get_ui_tree/simulate_and_diff step")
                if not argv or argv[0] not in ("exists", "count", "prop"):
                    raise ValueError("expect.py must specify an assertion")
                if argv[0] == "count" and not any(arg.split("=", 1)[0] in ("--eq", "--gte", "--lte") for arg in argv):
                    raise ValueError("count requires a comparison")
                if argv[0] == "prop" and not any(arg.split("=", 1)[0] == "--eq" for arg in argv):
                    raise ValueError("prop requires --eq")
                assertions += 1
            elif step["script"] in TREE_WRITERS:
                fresh_tree = True
            elif step["script"] in ("simulate.py", "navigator.py"):
                fresh_tree = False
        elif "code_file" in step:
            if set(step) - {"code_file", "server", "expect", "path", "timeout"}:
                raise ValueError("code step has unsupported keys")
            if not isinstance(step.get("server", False), bool):
                raise ValueError("server must be a boolean")
            keys = step.get("path", [])
            if not isinstance(keys, list) or not all(type(key) in (str, int) for key in keys):
                raise ValueError("path must be an array of JSON object keys / array indices")
            source = (directory / step["code_file"]).resolve()
            if source.stat().st_size > 1024 * 1024:
                raise ValueError("code file exceeds 1 MiB")
            step["code"] = source.read_text(encoding="utf-8-sig")
            step["code_file"] = str(source)
            assertions += "expect" in step
            fresh_tree = False
        else:
            raise ValueError("each step requires script or code_file")
        validated.append(step)
    if not assertions:
        raise ValueError("case must include at least one expect.py or code expect assertion")
    return validated


def run_case(case_file, timeout=30):
    root = session_artifacts()
    source = Path(case_file).resolve()
    case = json.loads(source.read_text(encoding="utf-8-sig"))
    steps = validate(case, source.parent, timeout)  # Validate every step before any mutation.
    run_id = uuid.uuid4().hex
    output = root / "cases" / run_id
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "case.json", case)
    report = {"run_id": run_id, "name": case.get("name", source.stem), "ok": True,
              "session_file": os.environ["MCDEV_SESSION_FILE"], "owner": os.environ["MCDEV_OWNER"], "steps": []}
    for index, step in enumerate(steps):
        prefix = "%03d" % (index + 1)
        if "script" in step:
            command = [sys.executable, "-X", "utf8", str(SCRIPTS / step["script"])] + step["argv"]
        else:
            code_file = output / (prefix + "-code.py")
            code_file.write_text(step["code"], encoding="utf-8")
            command = [sys.executable, "-X", "utf8", str(Path(__file__).resolve()), "--_code", str(code_file),
                       "--timeout", str(step["timeout"])]
            if step.get("server"):
                command.append("--server")
        record = bounded_process(command, step["timeout"], output)
        record["index"] = index + 1
        record["step"] = {key: value for key, value in step.items() if key != "code"}
        if record["ok"] and "expect" in step:
            try:
                actual = json.loads(record["stdout"])
                for key in step.get("path", []):
                    actual = actual[key]
                # JSON booleans must not compare equal to Python integers.
                record["actual"] = actual
                record["ok"] = json.dumps(actual, sort_keys=True) == json.dumps(step["expect"], sort_keys=True)
                if not record["ok"]:
                    record["error"] = "expected JSON value differs from actual"
            except (ValueError, TypeError, KeyError, IndexError) as exc:
                record["ok"] = False
                record["error"] = "assertion failed: " + str(exc)
        if record["ok"] and step.get("script") in TREE_WRITERS:
            tree = root / "ui_tree.json"
            if tree.is_file():
                (output / (prefix + "-tree.json")).write_bytes(tree.read_bytes())
        write_json(output / (prefix + "-result.json"), record)
        report["steps"].append(record)
        report["ok"] = report["ok"] and record["ok"]
        write_json(output / "evidence.json", report)
        if not record["ok"]:
            break
    return report, output / "evidence.json"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", nargs="?", help="UTF-8 JSON case file")
    parser.add_argument("--timeout", type=float, default=30, help="hard per-step deadline (maximum 120s)")
    parser.add_argument("--_code", help=argparse.SUPPRESS)
    parser.add_argument("--server", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if not 0 < args.timeout <= 120:
        parser.error("timeout must be greater than zero and at most 120 seconds")
    try:
        if args._code:
            session_artifacts()
            with Client(timeout=args.timeout) as client:
                result = return_value(client.call("execute_code", {
                    "code": Path(args._code).read_text(encoding="utf-8"),
                    "is_client": not args.server, "direct_return": True}))
            print(json.dumps(result, ensure_ascii=False))
            return 0
        if not args.case:
            parser.error("case is required")
        report, evidence = run_case(args.case, args.timeout)
        print(json.dumps({"ok": report["ok"], "run_id": report["run_id"], "evidence": str(evidence)}))
        return 0 if report["ok"] else 1
    except Exception as exc:
        print("[run_case] %s" % exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
