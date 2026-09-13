# -*- coding: utf-8 -*-
"""
Run a sequence of button clicks and report a compact per-button diff.

Regression tour testing: click each node id in turn and verify its re-render.
For each node the script dumps the UI tree before, clicks the node, waits for
the UI to settle, dumps the tree again, and prints a compact diff block (only
the changed entries) to STDOUT. Progress and a final summary go to STDERR.

Mirrors the dump -> click -> settle -> dump -> diff flow of
``simulate_and_diff.py``, but drives a list of nodes and emits one compact
block per node instead of a single JSON blob. Helpers are imported directly
(no subprocess call to simulate_and_diff.py).

Usage:
    python3 click_tour.py --nodes a,b,c --settle 1 [--timing]
    python3 click_tour.py --labels 在线,游戏中,全部 --settle 1 [--timing]

Per-node STDOUT block:
    ===== NODE a =====
    +N added, -N removed, ~N changed
      path: <path>
        before: <json>
        after: <json>
      ...

Final STDERR summary:
    [click_tour] done: N nodes, M with changes, K errors
"""

import argparse
import json
import sys
import time

from _protocol import request
from diff_ui_tree import _flatten, _node_summary
from simulate import _resolve_label


def _eprint(text):
    """Write UTF-8 progress text when Windows stderr is not UTF-8."""
    sys.stderr.buffer.write((text + "\n").encode("utf-8"))


def _diff(before_tree, after_tree, include_props, include_layout):
    """Return (added, removed, changed) for two UI trees.

    ``added``/``removed`` are sorted path lists (set-diff of flattened paths).
    ``changed`` mirrors simulate_and_diff.py's entry shape:
    ``{"path": full_path, "before": summary_b, "after": summary_a}``.
    """
    before_flat = _flatten(before_tree)
    after_flat = _flatten(after_tree)
    added = sorted(set(after_flat) - set(before_flat))
    removed = sorted(set(before_flat) - set(after_flat))
    changed = []
    for path in sorted(set(before_flat) & set(after_flat)):
        b = _node_summary(before_flat[path], include_props, include_layout)
        a = _node_summary(after_flat[path], include_props, include_layout)
        if b != a:
            changed.append({"path": path, "before": b, "after": a})
    return added, removed, changed


def _emit_block(node_id, added, removed, changed, timing=None):
    """Write one node's compact diff block to STDOUT (Windows-console-safe)."""
    lines = []
    lines.append("===== NODE %s =====" % node_id)
    lines.append("+%d added, -%d removed, ~%d changed" % (len(added), len(removed), len(changed)))
    if timing is not None:
        lines.append("timing_ms: %s" % json.dumps(timing, ensure_ascii=False))
    for entry in changed:
        lines.append("  path: %s" % entry["path"])
        lines.append("    before: %s" % json.dumps(entry["before"], ensure_ascii=False))
        lines.append("    after: %s" % json.dumps(entry["after"], ensure_ascii=False))
    lines.append("")
    sys.stdout.buffer.write(("\n".join(lines) + "\n").encode("utf-8"))


def main():
    parser = argparse.ArgumentParser(
        description="Click a sequence of UI nodes in turn and report a compact per-node diff"
    )
    targets = parser.add_mutually_exclusive_group(required=True)
    targets.add_argument("--nodes", help="comma-separated list of node ids to click in order")
    targets.add_argument("--labels", help="comma-separated visible labels, resolved again before each click")
    parser.add_argument("--settle", type=float, default=0.5, help="seconds to wait after click before re-dump")
    parser.add_argument("--timeout", type=float, default=5.0, help="seconds to wait for each response")
    parser.add_argument("--props", action="store_true", help="include props in changed summary")
    parser.add_argument("--layout", action="store_true", help="include layout in changed summary")
    parser.add_argument("--timing", action="store_true", help="include per-node dump/action/settle/diff timing")
    args = parser.parse_args()

    raw_targets = args.nodes if args.nodes is not None else args.labels
    target_values = [n.strip() for n in raw_targets.split(",") if n.strip()]
    if not target_values:
        _eprint("[click_tour] ERROR: no targets provided")
        sys.exit(2)

    total = len(target_values)
    with_changes = 0
    errors = 0

    for i, target_value in enumerate(target_values):
        now = getattr(time, "perf_counter", time.time)
        node_id = target_value
        # Let the UI settle from the previous click's state before the next
        # before-dump (only between consecutive nodes).
        if i > 0:
            time.sleep(0.2)
        total_started = now()

        # 1. before snapshot
        _eprint("[click_tour] node %d/%d '%s': dumping tree (before)..." % (i + 1, total, target_value))
        before_started = now()
        before = request("dump_tree", timeout=args.timeout)
        before_ms = (now() - before_started) * 1000.0
        if before is None:
            _eprint("[click_tour] ERROR: dump_tree (before) on '%s' timed out" % node_id)
            errors += 1
            continue

        if args.labels is not None:
            before_tree = before.get("tree", before)
            matches = _resolve_label(before_tree, target_value)
            if len(matches) != 1:
                _eprint(
                    "[click_tour] ERROR: label '%s' matched %d clickable nodes"
                    % (target_value, len(matches))
                )
                errors += 1
                continue
            node_id = matches[0].get("id")
            _eprint("[click_tour] resolved label '%s' -> %s" % (target_value, node_id))

        # 2. click
        _eprint("[click_tour] clicking '%s'..." % node_id)
        action_started = now()
        click_resp = request("click", node_id=node_id, timeout=args.timeout)
        action_ms = (now() - action_started) * 1000.0
        if click_resp is None:
            _eprint("[click_tour] ERROR: click on '%s' timed out" % node_id)
            errors += 1
            continue

        # 3. settle
        settle_started = now()
        if args.settle > 0:
            time.sleep(args.settle)
        settle_ms = (now() - settle_started) * 1000.0

        # 4. after snapshot
        _eprint("[click_tour] dumping tree (after)...")
        after_started = now()
        after = request("dump_tree", timeout=args.timeout)
        after_ms = (now() - after_started) * 1000.0
        if after is None:
            _eprint("[click_tour] ERROR: dump_tree (after) on '%s' timed out" % node_id)
            errors += 1
            continue

        # 5. diff (flatten, set-diff added/removed, _node_summary compare)
        before_tree = before.get("tree", before)
        after_tree = after.get("tree", after)
        diff_started = now()
        added, removed, changed = _diff(before_tree, after_tree, args.props, args.layout)
        diff_ms = (now() - diff_started) * 1000.0

        timing = None
        if args.timing:
            timing = {
                "before_dump": round(before_ms, 3),
                "action": round(action_ms, 3),
                "settle": round(settle_ms, 3),
                "after_dump": round(after_ms, 3),
                "diff": round(diff_ms, 3),
                "total": round((now() - total_started) * 1000.0, 3),
            }
        _emit_block(node_id, added, removed, changed, timing)

        if added or removed or changed:
            with_changes += 1

    _eprint("[click_tour] done: %d nodes, %d with changes, %d errors" % (total, with_changes, errors))


if __name__ == "__main__":
    main()
