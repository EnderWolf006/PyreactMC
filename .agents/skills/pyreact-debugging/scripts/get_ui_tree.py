# -*- coding: utf-8 -*-
"""
Trigger in-game UI tree dump via MCDevTool, then read and print/save the result.

Usage:
    python3 get_ui_tree.py [--node-id NODE_ID] [--output FILE]
                          [--timeout SECONDS] [--quiet] [--json]

Default: fetches the full tree and prints a pretty tree view.
--node-id: dump only the subtree rooted at NODE_ID.
"""

import argparse
import json
import os
import sys
import tempfile

from _protocol import request
from print_ui_tree import print_tree
from _session import default_tree_path


def _default_output():
    return default_tree_path()


def main():
    parser = argparse.ArgumentParser(description="Get Pyreact UI tree from game via MCDevTool")
    parser.add_argument("--node-id", default=None, help="dump subtree rooted at NODE_ID")
    parser.add_argument("--output", default=None)
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--quiet", action="store_true", help="suppress stdout (file save still happens)")
    parser.add_argument("--json", action="store_true", help="print raw JSON instead of pretty tree")
    args = parser.parse_args()

    cmd = "dump_subtree" if args.node_id else "dump_tree"
    print("[get_ui_tree] requesting %s..." % cmd, file=sys.stderr)
    data = request(cmd, node_id=args.node_id, timeout=args.timeout)

    if data is None:
        print("[get_ui_tree] ERROR: no response with matching seq within %.1fs" % args.timeout, file=sys.stderr)
        sys.exit(1)
    if data.get("error"):
        print("[get_ui_tree] ERROR: %s" % data["error"], file=sys.stderr)
        sys.exit(1)

    out_path = args.output or _default_output()
    formatted = json.dumps(data, ensure_ascii=False, indent=2)
    with open(out_path, 'wb') as f:
        f.write(formatted.encode('utf-8'))
    print("[get_ui_tree] saved to %s" % out_path, file=sys.stderr)

    if not args.quiet:
        print_tree(data, node_id=args.node_id, as_json=args.json)


if __name__ == "__main__":
    main()
