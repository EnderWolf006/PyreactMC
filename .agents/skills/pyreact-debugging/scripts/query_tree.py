# -*- coding: utf-8 -*-
"""
Query a saved Pyreact UI tree JSON without fragile inline ``python3 -c`` parsing.

This avoids Windows GBK decoding errors (``UnicodeDecodeError: 'gbk' codec
can't decode byte ...``) that occur when the tree contains non-ASCII text such
as Chinese item names. The JSON is always read with ``encoding="utf-8"`` and all
data output is written through ``sys.stdout.buffer.write(...encode("utf-8"))``
so it is safe to pipe on a Windows console with a non-UTF-8 code page.

Usage:
    python3 query_tree.py --prop content
    python3 query_tree.py --prop content --node-id abc123
    python3 query_tree.py --count-children
    python3 query_tree.py --children --node-id abc123
    python3 query_tree.py --descendant-count
    python3 query_tree.py --find-key category
    python3 query_tree.py --find-type Label
    python3 query_tree.py --find-type Label --file path/to/ui_tree.json
    python3 query_tree.py --sliders

Exactly one mode flag is required; mode flags are mutually exclusive.
``--file`` and ``--node-id`` are optional and may combine with any mode flag.
If ``--node-id`` is omitted the query operates on the tree root.
Default input file is <tempdir>/pyreact-debug/ui_tree.json (same as
print_ui_tree.py).
"""

import argparse
import json
import os
import sys
import tempfile


def _find(node, target_id):
    """Recursively find a node by ``id``. Returns the node or ``None``."""
    if node.get("id") == target_id:
        return node
    for child in node.get("children", []) or []:
        found = _find(child, target_id)
        if found is not None:
            return found
    return None


def _walk(node):
    """Recursive generator yielding the node and all of its descendants."""
    yield node
    for child in node.get("children", []) or []:
        for descendant in _walk(child):
            yield descendant


def _is_clickable(node):
    """A node is clickable if it is a Button, or carries a real onClick handler.

    The game-side dump sanitizes callables to the string "<function>", so both
    that marker and any truthy non-False onClick count as a real handler.
    """
    props = node.get("props", {}) or {}
    if node.get("type") == "Button":
        return True
    onclick = props.get("onClick")
    return onclick not in (None, False, "", "<function>")


def _has_handler(node):
    """True if the node actually carries an onClick handler (vs. being a Button
    with no handler). Lets callers distinguish real buttons from inert ones."""
    onclick = (node.get("props", {}) or {}).get("onClick")
    return onclick not in (None, False, "")


def _clickable_summary(node):
    """One-line summary of a clickable node for --clickable output."""
    props = node.get("props", {}) or {}
    parts = [node.get("id", u"?"), node.get("type", u"?")]
    key = node.get("key", props.get("key"))
    if key:
        parts.append(u"key=%s" % key)
    # Prefer direct content/src/identifier. FilledButton keeps its visible text
    # in descendant Labels, so expose several unique labels for disambiguation
    # (friend rows, for example, contain an avatar initial and a player name).
    for label_prop in ("content", "src", "identifier"):
        val = props.get(label_prop)
        if isinstance(val, str) and val:
            parts.append(u"%s=%s" % (label_prop, val))
            break
    else:
        labels = []
        for descendant in _walk(node):
            if descendant is node or descendant.get("type") != "Label":
                continue
            val = (descendant.get("props", {}) or {}).get("content")
            if isinstance(val, str) and val and val not in labels:
                labels.append(val)
            if len(labels) >= 5:
                break
        if labels:
            parts.append(u"labels=%s" % u"|".join(labels))
    parts.append(u"onClick=%s" % (u"handler" if _has_handler(node) else u"none"))
    return u" | ".join(parts)


def _emit(text):
    """Write a single line to stdout as UTF-8 encoded bytes."""
    sys.stdout.buffer.write((text + u"\n").encode("utf-8"))


def _format_value(value):
    """Render a prop value to a printable string."""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def main():
    parser = argparse.ArgumentParser(
        description="Query a saved Pyreact UI tree JSON (Windows-console-safe)."
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--prop", metavar="KEY",
        help="print the target node's props[KEY] value (e.g. content, src, identifier)",
    )
    mode.add_argument(
        "--count-children", action="store_true",
        help="print the number of direct children of the target node",
    )
    mode.add_argument(
        "--children", action="store_true",
        help="print each direct child's id and type as 'id (type)', one per line",
    )
    mode.add_argument(
        "--descendant-count", action="store_true",
        help="print the total descendant count (all nested children)",
    )
    mode.add_argument(
        "--find-key", metavar="PREFIX",
        help="print ids of subtree nodes whose key starts with PREFIX",
    )
    mode.add_argument(
        "--find-type", metavar="TYPE",
        help="print ids of subtree nodes whose type == TYPE",
    )
    mode.add_argument(
        "--clickable", action="store_true",
        help="list clickable nodes (Button or has onClick) with key/label/handler info",
    )
    mode.add_argument(
        "--inputs", action="store_true",
        help="list Input nodes with id, value and onChange marker",
    )
    mode.add_argument(
        "--sliders", action="store_true",
        help="list Slider nodes with id, value, steps and onChange marker",
    )
    parser.add_argument(
        "--file", default=None,
        help="path to ui_tree.json (default: <tempdir>/pyreact-debug/ui_tree.json)",
    )
    parser.add_argument(
        "--node-id", default=None,
        help="operate on this node instead of the tree root",
    )
    args = parser.parse_args()

    from _session import default_tree_path
    path = args.file or default_tree_path()

    if not os.path.isfile(path):
        print("[query_tree] ERROR: file not found: %s" % path, file=sys.stderr)
        sys.exit(1)

    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (IOError, OSError) as e:
        print("[query_tree] ERROR: could not read file: %s" % e, file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        print("[query_tree] ERROR: invalid JSON: %s" % e, file=sys.stderr)
        sys.exit(1)

    tree = data.get("tree", data)

    if args.node_id:
        root = _find(tree, args.node_id)
        if root is None:
            print(
                "[query_tree] ERROR: node '%s' not found" % args.node_id,
                file=sys.stderr,
            )
            sys.exit(1)
    else:
        root = tree

    node_label = root.get("id", args.node_id or u"<root>")

    if args.prop is not None:
        props = root.get("props", {}) or {}
        if args.prop not in props:
            print(
                "[query_tree] ERROR: prop '%s' not found on node '%s'"
                % (args.prop, node_label),
                file=sys.stderr,
            )
            sys.exit(1)
        _emit(_format_value(props[args.prop]))
    elif args.count_children:
        children = root.get("children", []) or []
        _emit(str(len(children)))
    elif args.children:
        children = root.get("children", []) or []
        for child in children:
            _emit(u"%s (%s)" % (child.get("id", u"?"), child.get("type", u"?")))
    elif args.descendant_count:
        count = sum(1 for _ in _walk(root)) - 1
        _emit(str(count))
    elif args.find_key is not None:
        for node in _walk(root):
            props = node.get("props", {}) or {}
            key = node.get("key", props.get("key"))
            if key is not None and str(key).startswith(args.find_key):
                _emit(node.get("id", u"?"))
    elif args.find_type is not None:
        for node in _walk(root):
            if node.get("type") == args.find_type:
                _emit(node.get("id", u"?"))
    elif args.clickable:
        for node in _walk(root):
            if _is_clickable(node):
                _emit(_clickable_summary(node))
    elif args.inputs:
        for node in _walk(root):
            if node.get("type") != "Input":
                continue
            props = node.get("props", {}) or {}
            value = props.get("value", u"<uncontrolled>")
            onchange = props.get("onChange")
            marker = u"handler" if onchange not in (None, False, "") else u"none"
            _emit(u"%s | value=%s | onChange=%s" % (
                node.get("id", u"?"), value, marker,
            ))
    elif args.sliders:
        for node in _walk(root):
            if node.get("type") != "Slider":
                continue
            props = node.get("props", {}) or {}
            value = props.get("value", u"<uncontrolled>")
            steps = props.get("steps", 1)
            onchange = props.get("onChange")
            marker = u"handler" if onchange not in (None, False, "") else u"none"
            _emit(u"%s | value=%s | steps=%s | onChange=%s" % (
                node.get("id", u"?"), value, steps, marker,
            ))


if __name__ == "__main__":
    main()
