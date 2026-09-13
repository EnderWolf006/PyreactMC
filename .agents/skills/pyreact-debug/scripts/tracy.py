# -*- coding: utf-8 -*-
"""Function-level profiling through Minecraft's embedded Tracy server.

Reference implementation:
https://github.com/lovelyXiaoQi/mcdk-mcp-tracy

This standalone CLI keeps reduced captures on disk so separate agent commands
can query and diff them without running an MCP server.
"""

import argparse
import csv
import hashlib
import io
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import uuid


PINNED_COMMIT = "441be11bfb731a045f6bf12a7ae188caee17507e"
MAX_SECONDS = 60.0
NS_PER_MS = 1000000.0
MAX_CAPTURES = 20
TOOLS = {
    "tracy-capture.exe": {
        "sha256": "ca5f7e69bdf4194e14563c8ef9005187032b7a77c3ad464c01a507b2a1e6c659",
        "size": 8320512,
    },
    "tracy-csvexport.exe": {
        "sha256": "67d7afed782bd84d8a2d4fa04f3d65062e7088bb54f3b7c90f628c3a97b1d144",
        "size": 8228864,
    },
}


def _default_bin_dir():
    return os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "bin"))


def _default_store_dir():
    return os.path.join(tempfile.gettempdir(), "pyreact-debug", "tracy-captures")


def _emit(value):
    text = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    sys.stdout.buffer.write(text.encode("utf-8"))


def _fail(reason, error, hint=None, **extra):
    out = {"ok": False, "reason": reason, "error": str(error)}
    if hint:
        out["hint"] = hint
    out.update(extra)
    _emit(out)
    return 1


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _tool_paths(bin_dir):
    return {name: os.path.join(bin_dir, name) for name in TOOLS}


def _tools_status(bin_dir):
    rows = {}
    all_valid = True
    for name, spec in TOOLS.items():
        path = os.path.join(bin_dir, name)
        exists = os.path.isfile(path)
        actual = _sha256(path) if exists else None
        valid = bool(exists and actual.lower() == spec["sha256"])
        rows[name] = {
            "path": path,
            "exists": exists,
            "valid": valid,
            "sha256": actual,
            "expected_sha256": spec["sha256"],
        }
        all_valid = all_valid and valid
    return all_valid, rows


def _download(url, target):
    try:
        from urllib.request import urlopen
    except ImportError:
        from urllib2 import urlopen
    temp_path = target + ".download"
    response = urlopen(url, timeout=120)
    try:
        with open(temp_path, "wb") as handle:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                handle.write(chunk)
    finally:
        response.close()
    os.replace(temp_path, target)


def command_setup(args):
    bin_dir = os.path.abspath(args.bin_dir)
    if not os.path.isdir(bin_dir):
        os.makedirs(bin_dir)
    installed = []
    for name, spec in TOOLS.items():
        target = os.path.join(bin_dir, name)
        if os.path.isfile(target) and _sha256(target).lower() == spec["sha256"]:
            installed.append({"name": name, "status": "already_valid", "path": target})
            continue
        url = (
            "https://raw.githubusercontent.com/lovelyXiaoQi/mcdk-mcp-tracy/"
            + PINNED_COMMIT + "/bin/" + name
        )
        try:
            _download(url, target)
        except Exception as exc:
            return _fail("download_failed", exc, url=url)
        actual = _sha256(target).lower()
        if actual != spec["sha256"]:
            try:
                os.remove(target)
            except OSError:
                pass
            return _fail(
                "checksum_mismatch",
                "%s checksum mismatch" % name,
                expected=spec["sha256"],
                actual=actual,
            )
        installed.append({"name": name, "status": "installed", "path": target})
    _emit({"ok": True, "bin_dir": bin_dir, "source_commit": PINNED_COMMIT, "tools": installed})
    return 0


def _probe(address, port, timeout=2.0):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect((address, int(port)))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def command_status(args):
    valid, tools = _tools_status(args.bin_dir)
    reachable = _probe(args.address, args.port, args.timeout)
    out = {
        "ok": bool(valid and reachable),
        "native_tracy": {
            "reachable": reachable,
            "address": args.address,
            "port": args.port,
        },
        "bin_dir": os.path.abspath(args.bin_dir),
        "bin_present": valid,
        "tools": tools,
    }
    if not reachable:
        out["reason"] = "tracy_unreachable"
        out["hint"] = "launch Minecraft and confirm its embedded Tracy server listens on TCP 8086"
    elif not valid:
        out["reason"] = "tracy_tools_missing"
        out["hint"] = "run: python3 tracy.py setup"
    _emit(out)
    return 0 if out["ok"] else 1


def _popen_kwargs():
    kwargs = {"stdout": subprocess.PIPE, "stderr": subprocess.PIPE}
    if sys.platform == "win32":
        kwargs["creationflags"] = 0x08000000
    return kwargs


def _run(cmd, timeout):
    return subprocess.run(cmd, timeout=timeout, **_popen_kwargs())


def _decode(data):
    return (data or b"").decode("utf-8", "replace")


def _parse_csv(text):
    out = {}
    for row in csv.DictReader(io.StringIO(text)):
        name = (row.get("name") or "").strip()
        if not name:
            continue
        src = (row.get("src_file") or "").strip()
        key = (name, src)
        try:
            ns = float(row.get("total_ns") or 0.0)
        except ValueError:
            ns = 0.0
        try:
            calls = int(float(row.get("counts") or 0))
        except ValueError:
            calls = 0
        current = out.get(key)
        if current is None:
            out[key] = {
                "ns": ns,
                "calls": calls,
                "src_line": (row.get("src_line") or "").strip(),
            }
        else:
            current["ns"] += ns
            current["calls"] = max(current["calls"], calls)
    return out


def _reduce_csv(self_text, total_text):
    self_map = _parse_csv(self_text)
    total_map = _parse_csv(total_text)
    rows = []
    for key in set(self_map) | set(total_map):
        name, src = key
        self_row = self_map.get(key)
        total_row = total_map.get(key)
        rows.append({
            "name": ("%s @ %s" % (name, src)) if src else name,
            "self_ms": round((self_row["ns"] if self_row else 0.0) / NS_PER_MS, 3),
            "total_ms": round((total_row["ns"] if total_row else 0.0) / NS_PER_MS, 3),
            "calls": (total_row["calls"] if total_row else 0) or (self_row["calls"] if self_row else 0),
            "src_file": src,
            "src_line": (total_row or self_row or {}).get("src_line", ""),
        })
    rows.sort(key=lambda row: (row["self_ms"], row["total_ms"], row["calls"]), reverse=True)
    return rows


def _capture_stats(text):
    def grab(label):
        match = re.search(label + r"\s*:?\s*([\d,]+)", text)
        if not match:
            return None
        return int(match.group(1).replace(",", ""))
    return {"frames": grab("Frames"), "zones": grab("Zones")}


def _filter_rows(rows, contains=None):
    if not contains:
        return list(rows)
    needle = contains.lower()
    return [row for row in rows if needle in row["name"].lower()]


def _public_rows(rows, frames=None, limit=25):
    result = []
    for row in rows[:max(0, int(limit))]:
        item = dict(row)
        calls = item.get("calls") or 0
        item["per_call_ms"] = round(item["self_ms"] / calls, 6) if calls else None
        item["per_frame_ms"] = round(item["self_ms"] / frames, 6) if frames else None
        result.append(item)
    return result


def _capture_id():
    return "cap-%s-%s" % (time.strftime("%Y%m%d-%H%M%S"), uuid.uuid4().hex[:6])


def _ensure_store(path):
    if not os.path.isdir(path):
        os.makedirs(path)


def _capture_path(store_dir, capture_id):
    return os.path.join(store_dir, capture_id + ".json")


def _write_capture(store_dir, capture):
    _ensure_store(store_dir)
    path = _capture_path(store_dir, capture["capture_id"])
    with open(path, "wb") as handle:
        handle.write(json.dumps(capture, ensure_ascii=False, indent=2).encode("utf-8"))
    paths = sorted(
        (os.path.join(store_dir, name) for name in os.listdir(store_dir) if name.endswith(".json")),
        key=lambda item: os.path.getmtime(item),
        reverse=True,
    )
    for old_path in paths[MAX_CAPTURES:]:
        try:
            os.remove(old_path)
        except OSError:
            pass
    return path


def _load_capture(store_dir, capture_id):
    path = capture_id if os.path.isfile(capture_id) else _capture_path(store_dir, capture_id)
    if not os.path.isfile(path):
        raise ValueError("unknown capture: %s" % capture_id)
    with open(path, "rb") as handle:
        return json.loads(handle.read().decode("utf-8"))


def _summary(capture):
    return {key: capture.get(key) for key in (
        "capture_id", "label", "created_at", "seconds", "frames", "zones",
        "unique_functions", "total_self_ms", "total_total_ms", "path",
    )}


def command_capture(args):
    if args.seconds <= 0 or args.seconds > MAX_SECONDS:
        return _fail("bad_request", "seconds must be in (0, 60]")
    valid, tools = _tools_status(args.bin_dir)
    if not valid:
        return _fail("tracy_tools_missing", "Tracy CLI tools are missing or invalid", hint="run: python3 tracy.py setup", tools=tools)
    if not _probe(args.address, args.port, args.probe_timeout):
        return _fail("tracy_unreachable", "no Tracy server on %s:%s" % (args.address, args.port))

    paths = _tool_paths(args.bin_dir)
    fd, trace_path = tempfile.mkstemp(suffix=".tracy")
    os.close(fd)
    try:
        command = [
            paths["tracy-capture.exe"], "-o", trace_path,
            "-a", args.address, "-p", str(args.port),
            "-s", str(args.seconds), "-f",
        ]
        capture_proc = _run(command, args.seconds + 30.0)
        capture_text = _decode(capture_proc.stdout) + "\n" + _decode(capture_proc.stderr)
        if capture_proc.returncode != 0:
            return _fail("capture_failed", capture_text.strip()[-500:], returncode=capture_proc.returncode)
        if not os.path.getsize(trace_path):
            return _fail("capture_failed", "Tracy produced an empty trace")

        self_proc = _run([paths["tracy-csvexport.exe"], "-e", trace_path], 90.0)
        total_proc = _run([paths["tracy-csvexport.exe"], trace_path], 90.0)
        if self_proc.returncode != 0 or total_proc.returncode != 0:
            return _fail(
                "csvexport_failed",
                (_decode(self_proc.stderr) + "\n" + _decode(total_proc.stderr)).strip()[-500:],
                returncodes=[self_proc.returncode, total_proc.returncode],
            )
        rows = _reduce_csv(_decode(self_proc.stdout), _decode(total_proc.stdout))
        stats = _capture_stats(capture_text)
    except subprocess.TimeoutExpired as exc:
        return _fail("timeout", exc)
    except Exception as exc:
        return _fail("capture_failed", exc)
    finally:
        try:
            os.remove(trace_path)
        except OSError:
            pass

    capture_id = _capture_id()
    capture = {
        "version": 1,
        "capture_id": capture_id,
        "label": args.label or capture_id,
        "created_at": time.time(),
        "seconds": args.seconds,
        "address": args.address,
        "port": args.port,
        "frames": stats.get("frames"),
        "zones": stats.get("zones"),
        "unique_functions": len(rows),
        "total_self_ms": round(sum(row["self_ms"] for row in rows), 3),
        "total_total_ms": round(sum(row["total_ms"] for row in rows), 3),
        "rows": rows,
    }
    path = _write_capture(args.store_dir, capture)
    capture["path"] = path
    filtered = _filter_rows(rows, args.contains)
    out = _summary(capture)
    out.update({
        "ok": True,
        "filter": args.contains,
        "matched_functions": len(filtered),
        "matched_self_ms": round(sum(row["self_ms"] for row in filtered), 3),
        "matched_total_ms": round(sum(row["total_ms"] for row in filtered), 3),
        "top": _public_rows(filtered, capture["frames"], args.top),
    })
    if not filtered:
        out["warning"] = "no matching zones; run representative gameplay during capture or remove --contains"
    _emit(out)
    return 0


def command_list(args):
    _ensure_store(args.store_dir)
    captures = []
    for name in os.listdir(args.store_dir):
        if not name.endswith(".json"):
            continue
        try:
            capture = _load_capture(args.store_dir, os.path.join(args.store_dir, name))
            capture["path"] = os.path.join(args.store_dir, name)
            captures.append(_summary(capture))
        except Exception:
            continue
    captures.sort(key=lambda item: item.get("created_at") or 0, reverse=True)
    _emit({"ok": True, "store_dir": args.store_dir, "captures": captures})
    return 0


def command_query(args):
    try:
        capture = _load_capture(args.store_dir, args.capture_id)
    except Exception as exc:
        return _fail("unknown_capture", exc)
    rows = _filter_rows(capture.get("rows") or [], args.contains)
    metric_key = "total_ms" if args.metric == "total" else "self_ms"
    rows.sort(key=lambda row: row.get(metric_key, 0.0), reverse=True)
    _emit({
        "ok": True,
        "capture_id": capture["capture_id"],
        "label": capture.get("label"),
        "metric": args.metric,
        "filter": args.contains,
        "matched_count": len(rows),
        "matched_ms": round(sum(row.get(metric_key, 0.0) for row in rows), 3),
        "matched": _public_rows(rows, capture.get("frames"), args.limit),
    })
    return 0


def _diff_rows(base, new, metric, top, contains=None):
    key = "total_ms" if metric == "total" else "self_ms"
    base_rows = _filter_rows(base.get("rows") or [], contains)
    new_rows = _filter_rows(new.get("rows") or [], contains)
    base_index = {row["name"]: float(row.get(key, 0.0)) for row in base_rows}
    new_index = {row["name"]: float(row.get(key, 0.0)) for row in new_rows}
    improved = []
    regressed = []
    for name in set(base_index) & set(new_index):
        base_ms = base_index[name]
        new_ms = new_index[name]
        delta = new_ms - base_ms
        item = {"name": name, "delta_ms": round(delta, 3), "base_ms": round(base_ms, 3), "new_ms": round(new_ms, 3)}
        if delta < 0:
            improved.append(item)
        elif delta > 0:
            regressed.append(item)
    improved.sort(key=lambda item: item["delta_ms"])
    regressed.sort(key=lambda item: item["delta_ms"], reverse=True)
    added = [{"name": name, "new_ms": round(value, 3)} for name, value in new_index.items() if name not in base_index]
    removed = [{"name": name, "base_ms": round(value, 3)} for name, value in base_index.items() if name not in new_index]
    added.sort(key=lambda item: item["new_ms"], reverse=True)
    removed.sort(key=lambda item: item["base_ms"], reverse=True)
    base_total = sum(base_index.values())
    new_total = sum(new_index.values())
    delta_total = new_total - base_total
    pct = (delta_total / base_total * 100.0) if base_total else None
    return {
        "base_id": base["capture_id"],
        "new_id": new["capture_id"],
        "base_label": base.get("label"),
        "new_label": new.get("label"),
        "metric": metric,
        "filter": contains,
        "summary": {
            "base_total_ms": round(base_total, 3),
            "new_total_ms": round(new_total, 3),
            "delta_ms": round(delta_total, 3),
            "pct": round(pct, 2) if pct is not None else None,
        },
        "improved": improved[:top],
        "regressed": regressed[:top],
        "added": added[:top],
        "removed": removed[:top],
    }


def command_diff(args):
    try:
        base = _load_capture(args.store_dir, args.base_id)
        new = _load_capture(args.store_dir, args.new_id)
    except Exception as exc:
        return _fail("unknown_capture", exc)
    out = _diff_rows(base, new, args.metric, args.top, args.contains)
    out["ok"] = True
    _emit(out)
    return 0


def command_self_test(args):
    self_csv = "name,src_file,src_line,total_ns,counts\nA,a.py,1,3000000,3\nB,b.py,2,1000000,2\n"
    total_csv = "name,src_file,src_line,total_ns,counts\nA,a.py,1,5000000,3\nB,b.py,2,2000000,2\n"
    rows = _reduce_csv(self_csv, total_csv)
    assert rows[0]["name"] == "A @ a.py"
    assert rows[0]["self_ms"] == 3.0
    assert rows[0]["total_ms"] == 5.0
    assert rows[0]["calls"] == 3
    base = {"capture_id": "base", "label": "before", "rows": rows}
    faster = [dict(row) for row in rows]
    faster[0]["self_ms"] = 1.0
    new = {"capture_id": "new", "label": "after", "rows": faster}
    diff = _diff_rows(base, new, "self", 10)
    assert diff["summary"]["delta_ms"] == -2.0
    assert diff["improved"][0]["name"] == "A @ a.py"
    _emit({"ok": True, "tests": ["csv_reduce", "ranking", "capture_diff"]})
    return 0


def build_parser():
    parser = argparse.ArgumentParser(description="Pyreact Tracy function-level profiler")
    parser.add_argument("--bin-dir", default=os.environ.get("TRACY_BIN_DIR") or _default_bin_dir())
    parser.add_argument("--store-dir", default=_default_store_dir())
    sub = parser.add_subparsers(dest="action", required=True)

    sub.add_parser("setup", help="download pinned Tracy v0.11.1 CLI tools")

    status = sub.add_parser("status", help="probe TCP 8086 and validate Tracy CLI tools")
    status.add_argument("--address", default="127.0.0.1")
    status.add_argument("--port", type=int, default=8086)
    status.add_argument("--timeout", type=float, default=2.0)

    capture = sub.add_parser("capture", help="capture and reduce function-level CPU costs")
    capture.add_argument("--seconds", type=float, default=5.0)
    capture.add_argument("--address", default="127.0.0.1")
    capture.add_argument("--port", type=int, default=8086)
    capture.add_argument("--probe-timeout", type=float, default=2.0)
    capture.add_argument("--contains", default=None, help="case-insensitive function/source filter")
    capture.add_argument("--top", type=int, default=25)
    capture.add_argument("--label", default=None)

    sub.add_parser("list", help="list persisted reduced captures")

    query = sub.add_parser("query", help="query costs from a persisted capture")
    query.add_argument("capture_id")
    query.add_argument("--contains", default=None)
    query.add_argument("--metric", choices=["self", "total"], default="self")
    query.add_argument("--limit", type=int, default=50)

    diff = sub.add_parser("diff", help="diff two captures; negative delta means faster")
    diff.add_argument("base_id")
    diff.add_argument("new_id")
    diff.add_argument("--metric", choices=["self", "total"], default="self")
    diff.add_argument("--contains", default=None)
    diff.add_argument("--top", type=int, default=25)

    sub.add_parser("self-test", help="run parser and diff tests without a game")
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    handlers = {
        "setup": command_setup,
        "status": command_status,
        "capture": command_capture,
        "list": command_list,
        "query": command_query,
        "diff": command_diff,
        "self-test": command_self_test,
    }
    return handlers[args.action](args)


if __name__ == "__main__":
    sys.exit(main())
