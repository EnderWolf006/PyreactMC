# -*- coding: utf-8 -*-
"""Inspect and control the in-game global Pyreact navigator."""
import argparse
import json
import sys

from _protocol import request


def _add_timeout(parser):
    parser.add_argument(
        "--timeout", type=float, default=5.0,
        help="seconds to wait for the clipboard response (default: 5)",
    )


def _write_json(value):
    data = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.buffer.write(data.encode("utf-8") + b"\n")


def _build_parser():
    parser = argparse.ArgumentParser(
        description="Inspect or control the global Pyreact navigator",
    )
    subparsers = parser.add_subparsers(dest="action", required=True)

    status = subparsers.add_parser("status", help="print navigator state")
    _add_timeout(status)

    pop = subparsers.add_parser("pop", help="pop actual UI stack layers")
    pop.add_argument("--count", type=int, default=1)
    _add_timeout(pop)

    pop_to = subparsers.add_parser(
        "pop-to", help="pop until the specified Pyreact entry is top",
    )
    pop_to.add_argument("key", help="NavigationEntry key")
    _add_timeout(pop_to)

    pop_to_top = subparsers.add_parser(
        "pop-to-top", help="return to the oldest live Pyreact entry",
    )
    _add_timeout(pop_to_top)

    clear = subparsers.add_parser(
        "clear", help="remove all Pyreact entries and intervening native UI",
    )
    _add_timeout(clear)

    close = subparsers.add_parser(
        "close", help="pop UI layers until the game interface is reached",
    )
    _add_timeout(close)
    return parser


def _payload(args):
    action = args.action.replace("-", "_")
    value = {"action": action}
    if action == "pop":
        value["count"] = args.count
    elif action == "pop_to":
        value["key"] = args.key
    return value


def main():
    parser = _build_parser()
    args = parser.parse_args()
    data = request("navigator", value=_payload(args), timeout=args.timeout)
    if data is None:
        print(
            "[navigator] ERROR: no response within %.1fs" % args.timeout,
            file=sys.stderr,
        )
        return 1

    result = data.get("result") or {}
    if args.action == "status" and result.get("state") is not None:
        _write_json(result["state"])
    else:
        _write_json(result or data)
    if not data.get("pyreact_ack") or data.get("error"):
        print(
            "[navigator] ERROR: %s" % (
                data.get("error") or "command was rejected"),
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
