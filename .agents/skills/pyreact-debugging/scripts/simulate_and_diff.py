# -*- coding: utf-8 -*-
"""
Simulate a UI interaction and immediately diff the UI tree before/after.

Usage:
    python3 simulate_and_diff.py click (--node-id ID | --key PREFIX | --label TEXT) [--timing]
    python3 simulate_and_diff.py input --node-id ID --value TEXT [--timing]
    python3 simulate_and_diff.py slider --node-id ID --value NUMBER [--timing]

Workflow:
    1. Dump UI tree (before)
    2. Simulate the requested interaction on NODE_ID
    3. Wait --settle seconds for UI to stabilize
    4. Dump UI tree (after)
    5. Print diff to stdout

Input and Slider actions use the same game-side paths as their real onChange
events.
"""

import argparse
import json
import os
import sys
import time

from _protocol import request
from diff_ui_tree import _flatten, _node_summary
from get_ui_tree import _default_output
from simulate import _resolve_key, _resolve_label, _resolve_single


def main():
    parser = argparse.ArgumentParser(description="Simulate Pyreact interaction and diff tree before/after")
    parser.add_argument("action", choices=["click", "input", "slider"],
                        help="interaction type")
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--node-id", default=None)
    target.add_argument("--key", default=None, metavar="PREFIX")
    target.add_argument("--label", default=None, metavar="TEXT")
    parser.add_argument("--value", default=None,
                        help="text for input, or numeric value for slider")
    parser.add_argument("--timeout", type=float, default=5.0, help="seconds to wait for response")
    parser.add_argument("--settle", type=float, default=0.5, help="seconds to wait after interaction before re-dump")
    parser.add_argument("--props", action="store_true", help="include props in diff output")
    parser.add_argument("--layout", action="store_true", help="include layout in diff output")
    parser.add_argument("--output-before", default=None, help="save before snapshot to file")
    parser.add_argument("--output-after", default=None, help="save after snapshot to file")
    parser.add_argument("--summary", action="store_true", help="compact output: counts instead of full added/removed path lists")
    parser.add_argument("--timing", action="store_true", help="include dump/action/settle/diff timing in JSON output")
    args = parser.parse_args()
    if args.action in ("input", "slider") and args.value is None:
        parser.error("%s requires --value" % args.action)
    if args.action == "input" and (args.key or args.label):
        parser.error("input only supports --node-id")
    if args.action == "slider" and (args.key or args.label):
        parser.error("slider only supports --node-id")

    now = getattr(time, "perf_counter", time.time)
    total_started = now()

    # 1. before snapshot
    print("[simulate_and_diff] dumping tree (before)...", file=sys.stderr)
    before_started = now()
    before = request("dump_tree", timeout=args.timeout)
    before_ms = (now() - before_started) * 1000.0
    if before is None:
        print("[simulate_and_diff] ERROR: could not get before tree", file=sys.stderr)
        sys.exit(1)
    if args.output_before:
        with open(args.output_before, "wb") as f:
            f.write(json.dumps(before, ensure_ascii=False, indent=2).encode("utf-8"))

    # Resolve semantic targets from the same snapshot used as the diff baseline.
    # This avoids stale native ids after keyed list items leave and re-enter the tree.
    node_id = args.node_id
    before_tree = before.get("tree", before)
    if args.key:
        node_id = _resolve_single(
            _resolve_key(before_tree, args.key),
            "key starting with '%s'" % args.key,
        )
    elif args.label:
        node_id = _resolve_single(
            _resolve_label(before_tree, args.label),
            "clickable label containing '%s'" % args.label,
        )
    print("[simulate_and_diff] resolved target -> %s" % node_id, file=sys.stderr)

    # 2. interaction
    if args.action == "input":
        action_label = "setting input"
    elif args.action == "slider":
        action_label = "setting slider"
    else:
        action_label = "clicking"
    print("[simulate_and_diff] %s %s..." % (action_label, node_id), file=sys.stderr)
    action_started = now()
    if args.action == "input":
        action_resp = request("set_input", node_id=node_id, value=args.value, timeout=args.timeout)
    elif args.action == "slider":
        action_resp = request("set_slider", node_id=node_id, value=args.value, timeout=args.timeout)
    else:
        action_resp = request("click", node_id=node_id, timeout=args.timeout)
    action_ms = (now() - action_started) * 1000.0
    if action_resp is None:
        print("[simulate_and_diff] WARNING: action response not received within %.1fs" % args.timeout, file=sys.stderr)
    elif action_resp.get("error"):
        print("[simulate_and_diff] ERROR: %s" % action_resp["error"], file=sys.stderr)
        sys.exit(1)

    # 3. settle
    settle_started = now()
    if args.settle > 0:
        time.sleep(args.settle)
    settle_ms = (now() - settle_started) * 1000.0

    # 4. after snapshot
    print("[simulate_and_diff] dumping tree (after)...", file=sys.stderr)
    after_started = now()
    after = request("dump_tree", timeout=args.timeout)
    after_ms = (now() - after_started) * 1000.0
    if after is None:
        print("[simulate_and_diff] ERROR: could not get after tree", file=sys.stderr)
        sys.exit(1)
    # Always refresh the shared ui_tree.json with the after snapshot so that
    # downstream tools (query_tree / print_ui_tree / custom verifiers) read the
    # post-click state instead of a stale baseline. (Fixes the bug where running
    # get_ui_tree once and then clicking left downstream readers on the old tree.)
    shared_path = _default_output()
    try:
        with open(shared_path, "wb") as f:
            f.write(json.dumps(after, ensure_ascii=False, indent=2).encode("utf-8"))
        print("[simulate_and_diff] refreshed shared tree: %s" % shared_path, file=sys.stderr)
    except Exception as e:
        print("[simulate_and_diff] WARNING: could not refresh shared tree: %s" % e, file=sys.stderr)
    if args.output_after:
        with open(args.output_after, "wb") as f:
            f.write(json.dumps(after, ensure_ascii=False, indent=2).encode("utf-8"))

    # 5. diff
    after_tree = after.get("tree", after)
    diff_started = now()
    before_flat = _flatten(before_tree)
    after_flat = _flatten(after_tree)

    added = sorted(set(after_flat) - set(before_flat))
    removed = sorted(set(before_flat) - set(after_flat))
    changed = []
    props_changed = 0
    layout_changed = 0
    for path in sorted(set(before_flat) & set(after_flat)):
        b_node = before_flat[path]
        a_node = after_flat[path]
        if not args.props and b_node.get("props") != a_node.get("props"):
            props_changed += 1
        if not args.layout and b_node.get("layout") != a_node.get("layout"):
            layout_changed += 1
        b = _node_summary(b_node, args.props, args.layout)
        a = _node_summary(a_node, args.props, args.layout)
        if b != a:
            changed.append({"path": path, "before": b, "after": a})
    diff_ms = (now() - diff_started) * 1000.0

    if args.summary:
        result = {"added_count": len(added), "removed_count": len(removed), "changed": changed}
    else:
        result = {"added": added, "removed": removed, "changed": changed}
    if args.timing:
        result["timing_ms"] = {
            "before_dump": round(before_ms, 3),
            "action": round(action_ms, 3),
            "settle": round(settle_ms, 3),
            "after_dump": round(after_ms, 3),
            "diff": round(diff_ms, 3),
            "total": round((now() - total_started) * 1000.0, 3),
        }
    sys.stdout.buffer.write((json.dumps(result, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    print("[simulate_and_diff] +%d added, -%d removed, ~%d changed" % (len(added), len(removed), len(changed)), file=sys.stderr)
    if args.timing:
        print(
            "[simulate_and_diff] timing: before=%.1fms action=%.1fms settle=%.1fms "
            "after=%.1fms diff=%.1fms total=%.1fms"
            % (before_ms, action_ms, settle_ms, after_ms, diff_ms,
               (now() - total_started) * 1000.0),
            file=sys.stderr,
        )
    no_structural = not added and not removed and not changed
    if no_structural:
        if not args.props and props_changed:
            print("Note: props changed in %d node(s). Use --props to see details." % props_changed, file=sys.stderr)
        if not args.layout and layout_changed:
            print("Note: layout changed in %d node(s). Use --layout to see details." % layout_changed, file=sys.stderr)
        # When the action was dispatched (ack received) yet the tree is fully
        # unchanged (no structural, no props, no layout diff), the most likely
        # Surface an unchanged action explicitly so the operator can inspect
        # its callback/value wiring without reading the implementation first.
        if action_resp is not None and not props_changed and not layout_changed:
            print(
                "Note: %s dispatched to %s but UI tree is fully unchanged. "
                "For input/slider, verify onChange and controlled value; "
                "for click, use query_tree.py --clickable."
                % (args.action, node_id),
                file=sys.stderr,
            )


if __name__ == "__main__":
    main()
