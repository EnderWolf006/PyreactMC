# -*- coding: utf-8 -*-
"""
Print a saved UI tree JSON in ASCII-safe human-readable format.

Usage:
    python3 print_ui_tree.py [FILE] [--node-id NODE_ID] [--depth N] [--json]
"""

import argparse
import json
import os
import sys
import tempfile


def _key_info(node):
    """Return a useful prop summary for display."""
    props = node.get("props", {}) or {}
    node_type = node.get("type", "")
    if node_type == "Label" and props.get("content"):
        return u' "%s"' % props["content"]
    if node_type == "Image" and props.get("src"):
        return u' src=%s' % props["src"]
    if node_type == "Item" and props.get("identifier"):
        return u' item=%s' % props["identifier"]
    if node_type == "Input":
        value = props.get("value")
        if value is not None:
            return u' value=%s' % value
        return u' input'
    return u""


def _interactive(node):
    props = node.get("props", {}) or {}
    flags = []
    node_type = node.get("type", "")
    # onClick is sanitized to "<function>" when it's a callable; treat both
    # real callables (impossible after JSON) and the "<function>" marker as clickable.
    onclick = props.get("onClick")
    if onclick not in (None, False, "", "<function>"):
        flags.append("clickable")
    if node_type == "Button" and "clickable" not in flags:
        flags.append("clickable")
    if node_type == "Input":
        flags.append("editable")
    return "|".join(flags)


def _print_node(node, prefix="", is_last=True, depth=None, current_depth=0):
    if depth is not None and current_depth > depth:
        return
    connector = "`-- " if is_last else "|-- "
    node_id = node.get("id", "?")
    node_type = node.get("type", "?")
    layout = node.get("layout", {}) or {}
    w = layout.get("width", "?")
    h = layout.get("height", "?")
    x = layout.get("x", "?")
    y = layout.get("y", "?")
    opacity = node.get("opacity", None)
    interactive = _interactive(node)
    interactive_str = " [%s]" % interactive if interactive else ""
    key_str = _key_info(node)
    opacity_str = " op=%.2f" % opacity if isinstance(opacity, (int, float)) and opacity != 1.0 else ""

    line = u"%s%s%s (%s)%s %sx%s @(%s,%s)%s%s" % (
        prefix, connector, node_id, node_type, key_str, w, h, x, y, interactive_str, opacity_str
    )
    sys.stdout.buffer.write((line + "\n").encode("utf-8", errors="replace"))

    children = node.get("children", []) or []
    child_prefix = prefix + ("    " if is_last else "|   ")
    for i, child in enumerate(children):
        _print_node(child, child_prefix, i == len(children) - 1, depth, current_depth + 1)


def print_tree(data, node_id=None, depth=None, as_json=False):
    tree = data.get("tree", data)
    root = tree
    if node_id:
        def _find(node, nid):
            if node.get("id") == nid:
                return node
            for c in node.get("children", []) or []:
                r = _find(c, nid)
                if r:
                    return r
            return None
        root = _find(tree, node_id)
        if root is None:
            print("[print_ui_tree] ERROR: node '%s' not found" % node_id, file=sys.stderr)
            sys.exit(1)

    if as_json:
        sys.stdout.buffer.write((json.dumps(root, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    else:
        _print_node(root, "", True, depth, 0)


def main():
    parser = argparse.ArgumentParser(description="Print Pyreact UI tree in ASCII-safe format")
    parser.add_argument("file", nargs="?", default=None)
    parser.add_argument("--node-id", default=None)
    parser.add_argument("--depth", type=int, default=None)
    parser.add_argument("--json", action="store_true", help="output raw JSON instead of tree")
    args = parser.parse_args()

    from _session import default_tree_path
    path = args.file or default_tree_path()
    with open(path, "rb") as f:
        data = json.loads(f.read().decode("utf-8"))
    print_tree(data, node_id=args.node_id, depth=args.depth, as_json=args.json)


if __name__ == "__main__":
    main()
