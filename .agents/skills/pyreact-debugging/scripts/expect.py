# -*- coding: utf-8 -*-
"""
Declarative assertions against the saved UI tree (ui_tree.json).

The intended workflow: run a click via `simulate_and_diff.py` (which now
refreshes the shared ui_tree.json with the post-click state), then assert on
the refreshed tree:

    python3 simulate_and_diff.py click --node-id __pyr_25
    python3 expect.py prop --node-id __pyr_40 --key content --eq 方块
    python3 expect.py count --type HorizontalItemCard --eq 8

Exits 0 on PASS, 1 on FAIL (so it composes in scripts / test runners).

Reads the shared tree at %TEMP%/pyreact-debug/ui_tree.json by default; override
with --file. All assertions print a one-line PASS/FAIL summary to stderr.
"""

import argparse
import json
import os
import sys

try:
    from get_ui_tree import _default_output
except Exception:
    def _default_output():
        d = os.path.join(os.environ.get("TEMP") or "/tmp", "pyreact-debug")
        return os.path.join(d, "ui_tree.json")


def _load(path):
    if not os.path.isfile(path):
        print("[expect] FAIL: tree file not found: %s" % path, file=sys.stderr)
        sys.exit(1)
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
    except Exception as e:
        print("[expect] FAIL: cannot parse tree: %s" % e, file=sys.stderr)
        sys.exit(1)
    # The saved file is the raw clipboard-protocol response
    # {pyreact_ack, seq, tree, error}; unwrap the actual tree (same convention
    # as query_tree.py / print_ui_tree.py).
    return raw.get("tree", raw)


def _walk(node):
    yield node
    for child in node.get("children", []) or []:
        for d in _walk(child):
            yield d


def _find_node(root, node_id):
    for n in _walk(root):
        if n.get("id") == node_id:
            return n
    return None


def _emit(ok, detail):
    status = "PASS" if ok else "FAIL"
    line = "[expect] %s: %s" % (status, detail)
    sys.stdout.buffer.write((line + "\n").encode("utf-8"))
    sys.stdout.buffer.flush()
    sys.exit(0 if ok else 1)


def main():
    parser = argparse.ArgumentParser(description="Declarative UI tree assertions")
    parser.add_argument("--file", default=None, help="tree JSON (default: shared ui_tree.json)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_exists = sub.add_parser("exists", help="assert a node with the given id exists")
    p_exists.add_argument("--node-id", required=True)

    p_count = sub.add_parser("count", help="count nodes of a type, compare to N")
    p_count.add_argument("--type", required=True)
    p_count.add_argument("--eq", type=int, default=None)
    p_count.add_argument("--gte", type=int, default=None)
    p_count.add_argument("--lte", type=int, default=None)

    p_prop = sub.add_parser("prop", help="assert a node's prop equals a value")
    p_prop.add_argument("--node-id", required=True)
    p_prop.add_argument("--key", required=True)
    p_prop.add_argument("--eq", default=None, help="expected value (string)")

    args = parser.parse_args()
    path = args.file or _default_output()
    root = _load(path)

    if args.cmd == "exists":
        node = _find_node(root, args.node_id)
        _emit(node is not None, "node %s %s" % (args.node_id, "exists" if node else "NOT FOUND"))

    elif args.cmd == "count":
        total = sum(1 for n in _walk(root) if n.get("type") == args.type)
        if args.eq is not None:
            ok = total == args.eq
            _emit(ok, "count type=%s -> %d (expected %d)" % (args.type, total, args.eq))
        elif args.gte is not None:
            ok = total >= args.gte
            _emit(ok, "count type=%s -> %d (expected >= %d)" % (args.type, total, args.gte))
        elif args.lte is not None:
            ok = total <= args.lte
            _emit(ok, "count type=%s -> %d (expected <= %d)" % (args.type, total, args.lte))
        else:
            parser.error("count requires --eq / --gte / --lte")

    elif args.cmd == "prop":
        node = _find_node(root, args.node_id)
        if node is None:
            _emit(False, "node %s NOT FOUND" % args.node_id)
        actual = (node.get("props", {}) or {}).get(args.key)
        ok = str(actual) == args.eq
        _emit(ok, "node %s props.%s = %r (expected %r)" % (args.node_id, args.key, actual, args.eq))


if __name__ == "__main__":
    main()
