# -*- coding: utf-8 -*-
"""
Simulate a button click, Input change, Slider change, or ScrollView scroll.

Click target can be specified in three ways (mutually exclusive):
  --node-id ID   click the native node with this id (default; what the game
                 reports as the clickable element's native_name)
  --key PREFIX   dump the tree, find the node whose props['key'] starts with
                 PREFIX, and click it. React-idiomatic and stable across
                 re-renders (the BedwarsShop category buttons use
                 key="category_0".."category_7"). Errors if 0 or >1 matches.
  --label TEXT   find a clickable Button (or node with onClick) whose subtree
                 contains a Label whose content includes TEXT, and click it.
                 Useful when you only know the displayed text.
Usage:
    python3 simulate.py click --node-id NODE_ID [--timeout N] [--settle S]
    python3 simulate.py click --key category_3 [--timeout N] [--settle S]
    python3 simulate.py click --label 方块 [--timeout N] [--settle S]
    python3 simulate.py input --node-id NODE_ID --value TEXT [--timeout N] [--settle S]
    python3 simulate.py slider --node-id NODE_ID --value NUMBER [--timeout N] [--settle S]
    python3 simulate.py scroll --node-id NODE_ID [--position PIXELS] [--timeout N]

--settle: seconds to wait after the click for the UI to re-render (default 0).
"""

import argparse
import sys
import time

from _protocol import request


def _walk(node, ancestors=None):
    """Yield (node, ancestor_stack) for the node and all descendants."""
    stack = ancestors or []
    yield node, stack
    for child in node.get("children", []) or []:
        for n, s in _walk(child, stack + [node]):
            yield n, s


def _is_clickable(node):
    props = node.get("props", {}) or {}
    if node.get("type") == "Button":
        return True
    onclick = props.get("onClick")
    return onclick not in (None, False, "", "<function>")


def _is_component_boundary(node):
    """Return True for serialized Custom/Composite Component wrapper nodes."""
    node_id = node.get("id", "")
    return isinstance(node_id, str) and node_id.startswith("<") and node_id.endswith(">")


def _resolve_key(tree, prefix):
    matches = []
    seen = set()
    for node, _ in _walk(tree):
        key = node.get("key", (node.get("props", {}) or {}).get("key"))
        if key is None or not str(key).startswith(prefix):
            continue
        # A Composite owns the key, while its primitive Button owns the
        # actual native event. Only resolve an unambiguous descendant.
        candidates = [node] if node.get("type") == "Button" else [
            child for child, _ in _walk(node) if child.get("type") == "Button"]
        for candidate in candidates:
            if candidate.get("id") not in seen:
                seen.add(candidate.get("id"))
                matches.append(candidate)
    return matches


def _resolve_label(tree, text):
    """Find a clickable node identified by displayed text.

    Composite buttons (e.g. FilledButton) put the text in a Label that is a
    SIBLING of the clickable inner Button, not a descendant of it. So for a
    matching Label we: (1) take the nearest clickable ancestor if one exists,
    else (2) take the first clickable descendant of the nearest enclosing
    ancestor (the composite boundary). Returns the resolved clickable nodes
    (deduped by id)."""
    results = []
    seen_ids = set()
    for node, ancestors in _walk(tree):
        if node.get("type") != "Label":
            continue
        content = (node.get("props", {}) or {}).get("content", "")
        if not (isinstance(content, str) and text in content):
            continue
        target = None
        # (1) nearest clickable ancestor
        for anc in reversed(ancestors):
            if _is_clickable(anc):
                target = anc
                break
        # (2) A composite such as FilledButton may serialize its text Label as
        # a sibling of the native Button. Only associate within a Component
        # boundary that owns exactly one clickable descendant. Searching an
        # arbitrary Panel would incorrectly map nearby headings to action
        # buttons in the same layout container.
        if target is None:
            for anc in reversed(ancestors):
                if not _is_component_boundary(anc):
                    continue
                clickables = []
                seen = set()
                for d, _ in _walk(anc):
                    if d is anc or not _is_clickable(d):
                        continue
                    node_id = d.get("id")
                    if node_id not in seen:
                        seen.add(node_id)
                        clickables.append(d)
                if len(clickables) == 1:
                    target = clickables[0]
                    break
        if target is not None:
            tid = target.get("id")
            if tid not in seen_ids:
                seen_ids.add(tid)
                results.append(target)
    return results


def _resolve_single(matches, description):
    """Return one target or print a useful zero/ambiguous-match error."""
    if len(matches) == 0:
        print("[simulate] ERROR: no node matching %s" % description, file=sys.stderr)
        sys.exit(1)
    if len(matches) > 1:
        print("[simulate] ERROR: ambiguous target %s matched %d nodes:" %
              (description, len(matches)), file=sys.stderr)
        for match in matches:
            print("  %s (type=%s)" % (match.get("id"), match.get("type")), file=sys.stderr)
        sys.exit(1)
    return matches[0].get("id")


def _click(node_id, timeout):
    print("[simulate] clicking %s..." % node_id, file=sys.stderr)
    data = request("click", node_id=node_id, timeout=timeout)
    if data is None:
        print("[simulate] ERROR: no response within %.1fs" % timeout, file=sys.stderr)
        sys.exit(1)
    if data.get("error"):
        print("[simulate] ERROR: %s" % data["error"], file=sys.stderr)
        sys.exit(1)
    print("[simulate] OK: click dispatched to %s" % node_id, file=sys.stderr)
    return data


def _input(node_id, value, timeout):
    print("[simulate] setting input %s..." % node_id, file=sys.stderr)
    data = request("set_input", node_id=node_id, value=value, timeout=timeout)
    if data is None:
        print("[simulate] ERROR: no response within %.1fs" % timeout, file=sys.stderr)
        sys.exit(1)
    if data.get("error"):
        print("[simulate] ERROR: %s" % data["error"], file=sys.stderr)
        sys.exit(1)
    print("[simulate] OK: input dispatched to %s" % node_id, file=sys.stderr)
    return data


def _slider(node_id, value, timeout):
    print("[simulate] setting slider %s to %s..." % (node_id, value),
          file=sys.stderr)
    data = request("set_slider", node_id=node_id, value=value, timeout=timeout)
    if data is None:
        print("[simulate] ERROR: no response within %.1fs" % timeout,
              file=sys.stderr)
        sys.exit(1)
    if data.get("error"):
        print("[simulate] ERROR: %s" % data["error"], file=sys.stderr)
        sys.exit(1)
    result = data.get("result", {})
    print("[simulate] OK: slider %.3f -> %.3f" % (
        result.get("before", 0), result.get("value", 0)), file=sys.stderr)
    return data


def _scroll(node_id, position, timeout):
    if position is None:
        print("[simulate] reading scroll position from %s..." % node_id,
              file=sys.stderr)
        data = request("get_scroll", node_id=node_id, timeout=timeout)
    else:
        print("[simulate] scrolling %s to %.2f px..." % (node_id, position),
              file=sys.stderr)
        data = request("scroll", node_id=node_id, value=position,
                       timeout=timeout)
    if data is None:
        print("[simulate] ERROR: no response within %.1fs" % timeout,
              file=sys.stderr)
        sys.exit(1)
    if data.get("error"):
        print("[simulate] ERROR: %s" % data["error"], file=sys.stderr)
        sys.exit(1)
    result = data.get("result", {})
    if position is None:
        print("[simulate] OK: scroll position=%.2f px" % result.get("position", 0),
              file=sys.stderr)
    else:
        print("[simulate] OK: %.2f -> %.2f px" % (
            result.get("before", 0), result.get("position", 0)),
            file=sys.stderr)
    return data


def main():
    parser = argparse.ArgumentParser(description="Simulate Pyreact UI interaction via clipboard")
    parser.add_argument("action", choices=["click", "input", "slider", "scroll"],
                        help="interaction type")
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--node-id", default=None)
    target.add_argument("--key", default=None, metavar="PREFIX", help="click node whose props.key starts with PREFIX")
    target.add_argument("--label", default=None, metavar="TEXT", help="click clickable node whose subtree Label contains TEXT")
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--value", default=None,
                        help="text for input, or numeric value for slider")
    parser.add_argument("--position", type=float, default=None,
                        help="ScrollView pixel position; omit to read current position")
    parser.add_argument("--settle", type=float, default=0.0, help="seconds to wait after interaction for re-render (default 0)")
    args = parser.parse_args()

    if args.action == "input":
        if args.node_id is None:
            parser.error("input requires --node-id")
        if args.value is None:
            parser.error("input requires --value")
        if args.key or args.label:
            parser.error("input only supports --node-id")
        if args.position is not None:
            parser.error("--position only supports scroll")
    elif args.action == "slider":
        if args.node_id is None:
            parser.error("slider requires --node-id")
        if args.value is None:
            parser.error("slider requires --value")
        if args.key or args.label:
            parser.error("slider only supports --node-id")
        if args.position is not None:
            parser.error("--position only supports scroll")
    elif args.action == "scroll":
        if args.node_id is None:
            parser.error("scroll requires --node-id")
        if args.key or args.label:
            parser.error("scroll only supports --node-id")
        if args.value is not None:
            parser.error("--value only supports input or slider")
    elif args.position is not None:
        parser.error("--position only supports scroll")

    node_id = args.node_id

    if args.key or args.label:
        print("[simulate] dumping tree to resolve target...", file=sys.stderr)
        dump = request("dump_tree", timeout=args.timeout)
        if dump is None:
            print("[simulate] ERROR: could not dump tree to resolve target", file=sys.stderr)
            sys.exit(1)
        if dump.get("error"):
            print("[simulate] ERROR: %s" % dump["error"], file=sys.stderr)
            sys.exit(1)
        tree = dump.get("tree", dump)
        if args.key:
            matches = _resolve_key(tree, args.key)
            node_id = _resolve_single(matches, "key starting with '%s'" % args.key)
            print("[simulate] resolved key '%s' -> %s" % (args.key, node_id), file=sys.stderr)
        elif args.label:
            matches = _resolve_label(tree, args.label)
            node_id = _resolve_single(matches, "clickable label containing '%s'" % args.label)
            print("[simulate] resolved label '%s' -> %s" % (args.label, node_id), file=sys.stderr)

    if args.action == "click":
        _click(node_id, args.timeout)
    elif args.action == "input":
        _input(node_id, args.value, args.timeout)
    elif args.action == "slider":
        _slider(node_id, args.value, args.timeout)
    else:
        _scroll(node_id, args.position, args.timeout)

    if args.settle > 0:
        time.sleep(args.settle)


if __name__ == "__main__":
    main()
