# -*- coding: utf-8 -*-
"""
Read game logs from the log_server HTTP API, with file fallback.

By default talks to the log_server HTTP API on port+1. If the HTTP API is
unreachable (a known failure mode), it transparently falls back to reading the
log file that log_server writes (``<tempdir>/pyreact-debug/pyreact_game_<port>.log``),
so log retrieval keeps working even when the HTTP server thread is down.

Usage:
    python3 get_logs.py --port PORT [--from-file FILE]
                       [--tail N | --head N | --lines START[-END] | --since LINENUM]
                       [--grep PATTERN] [--ignore-case]
                       [--follow]

--from-file: read the given log file directly instead of using HTTP.
"""

import argparse
import os
import sys
import time
try:
    from urllib.request import urlopen
    from urllib.parse import urlencode
except ImportError:
    from urllib2 import urlopen
    from urllib import urlencode
import json


def _default_log_file_for_port(port):
    return os.path.join(
        os.environ.get("TEMP") or os.environ.get("TMP") or "/tmp",
        "pyreact-debug", "pyreact_game_%d.log" % port,
    )


def _write(text):
    sys.stdout.buffer.write(text.encode("utf-8"))
    sys.stdout.buffer.flush()


def fetch_logs_http(port, since=0, grep=None, ignore_case=False):
    """Fetch logs from the log_server HTTP API. Returns dict {lines:[{n,text}], total}
    or None if the HTTP API is unreachable."""
    params = {"since": since}
    if grep:
        params["grep"] = grep
    if ignore_case:
        params["ignore_case"] = "1"
    url = "http://localhost:%d/logs?%s" % (port + 1, urlencode(params))
    try:
        resp = urlopen(url, timeout=5)
        return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


def read_log_file(path):
    """Read a raw log file into a list of {n, text} dicts (1-based)."""
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except Exception as e:
        print("[get_logs] ERROR: cannot read log file %s: %s" % (path, e), file=sys.stderr)
        sys.exit(1)
    text = raw.decode("utf-8", errors="replace")
    lines = text.splitlines(keepends=True)
    return [{"n": i + 1, "text": l} for i, l in enumerate(lines)]


def apply_filters(lines, grep, ignore_case, args, total):
    """Apply --grep/--ignore-case, then --lines/--since/--head/--tail selection."""
    if grep:
        import re as _re
        flags = _re.IGNORECASE if ignore_case else 0
        pat = _re.compile(grep, flags)
        lines = [e for e in lines if pat.search(e["text"])]
    if args.lines:
        parts = args.lines.split("-")
        start = max(1, int(parts[0]))
        end = int(parts[1]) if len(parts) > 1 else total
        lines = [e for e in lines if start <= e["n"] <= end]
    elif args.since:
        lines = [e for e in lines if e["n"] >= max(1, args.since)]
    elif args.head:
        lines = lines[:args.head]
    elif args.tail:
        lines = lines[-args.tail:]
    return lines


def main():
    parser = argparse.ArgumentParser(description="Read Pyreact game logs (HTTP with file fallback)")
    parser.add_argument("--port", type=int, default=None, help="Log server port (launch_game.py output)")
    parser.add_argument("--from-file", default=None, metavar="FILE", help="read this log file directly (skip HTTP)")
    parser.add_argument("--tail", type=int, default=None, metavar="N")
    parser.add_argument("--head", type=int, default=None, metavar="N")
    parser.add_argument("--lines", default=None, metavar="START[-END]")
    parser.add_argument("--since", type=int, default=None, metavar="LINENUM")
    parser.add_argument("--grep", default=None, metavar="PATTERN",
                        help="regex filter")
    parser.add_argument("--ignore-case", action="store_true")
    parser.add_argument("--follow", action="store_true", help="Stream new log lines continuously (Ctrl+C to stop)")
    args = parser.parse_args()

    if not args.port and not args.from_file:
        parser.error("at least one of --port or --from-file is required")

    use_file = bool(args.from_file)
    log_file = args.from_file
    if not use_file:
        # try HTTP; on failure auto-detect the default log file for this port
        probe = fetch_logs_http(args.port, grep=args.grep, ignore_case=args.ignore_case)
        if probe is None:
            cand = _default_log_file_for_port(args.port)
            if os.path.isfile(cand):
                print("[get_logs] HTTP API unreachable; falling back to %s" % cand, file=sys.stderr)
                use_file = True
                log_file = cand
            else:
                print("[get_logs] ERROR: cannot reach log_server on port %d and no log file at %s" % (
                    args.port + 1, cand), file=sys.stderr)
                sys.exit(1)

    if use_file:
        all_lines = read_log_file(log_file)
        total = len(all_lines)
        # For file mode, grep+ignore_case are applied inside apply_filters too.
        selected = apply_filters(all_lines, args.grep, args.ignore_case, args, total)
        if args.follow:
            _write("[get_logs] following file %s (Ctrl+C to stop)...\n" % log_file)
            for entry in selected:
                _write("%6d: %s" % (entry["n"], entry["text"]))
            seen = total
            try:
                while True:
                    time.sleep(0.5)
                    fresh = read_log_file(log_file)
                    new = fresh[seen:] if seen < len(fresh) else []
                    if args.grep:
                        import re as _re
                        flags = _re.IGNORECASE if args.ignore_case else 0
                        pat = _re.compile(args.grep, flags)
                        new = [e for e in new if pat.search(e["text"])]
                    for entry in new:
                        _write("%6d: %s" % (entry["n"], entry["text"]))
                    seen = len(fresh)
            except KeyboardInterrupt:
                _write("\n[get_logs] stopped.\n")
            return
        _write("[get_logs] %d lines (file: %s)\n\n" % (len(selected), log_file))
        for entry in selected:
            _write("%6d: %s" % (entry["n"], entry["text"]))
        if selected and not selected[-1]["text"].endswith("\n"):
            _write(b"\n")
        return

    # HTTP mode (incl. --follow)
    if args.follow:
        data = fetch_logs_http(args.port, grep=args.grep, ignore_case=args.ignore_case)
        seen = data["total"]
        if args.tail:
            for entry in data["lines"][-args.tail:]:
                _write("%6d: %s" % (entry["n"], entry["text"]))
        _write("[get_logs] following from line %d (Ctrl+C to stop)...\n" % (seen + 1))
        try:
            while True:
                time.sleep(0.5)
                data = fetch_logs_http(args.port, since=seen, grep=args.grep, ignore_case=args.ignore_case)
                for entry in data["lines"]:
                    _write("%6d: %s" % (entry["n"], entry["text"]))
                seen = data["total"]
        except KeyboardInterrupt:
            _write("\n[get_logs] stopped.\n")
        return

    data = fetch_logs_http(args.port, grep=args.grep, ignore_case=args.ignore_case)
    total = data["total"]
    lines = apply_filters(data["lines"], None, args.ignore_case, args, total)
    if not lines:
        print("[get_logs] no matching lines.")
        return
    _write("[get_logs] %d lines (total: %d)\n\n" % (len(lines), total))
    for entry in lines:
        _write("%6d: %s" % (entry["n"], entry["text"]))
    if lines and not lines[-1]["text"].endswith("\n"):
        _write(b"\n")


if __name__ == "__main__":
    main()
