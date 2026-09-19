# -*- coding: utf-8 -*-
"""Shared clipboard request/response helpers for pyreact-debugging scripts.

Protocol:
  Request  (script -> game):  {"pyreact_debug": {"cmd": "...", "id": "...", "value": "...", "seq": N}}
  Response (game -> script):  {"pyreact_ack": true, "seq": N, "tree": {...}, "error": null}

seq is a unique int per request; the script waits for a response whose seq
matches, discarding stale clipboard content. This replaces the old two-step
(ack-then-json) scheme with a single round-trip keyed by seq.
"""

import json
import time
import uuid

from clipboard_ipc import read_clipboard, write_clipboard


def new_seq():
    """Unique across processes and restarts, without timestamp wraparound."""
    return uuid.uuid4().int


def request(cmd, node_id=None, value=None, timeout=5.0):
    """Send a pyreact_debug request and wait for the matching-seq response.

    :param cmd: command name ("dump_tree" / "dump_subtree" / "click" /
        "set_input" / "set_slider" / "scroll" / "get_scroll" /
        "navigator" / "ping").
    :param node_id: target node id for subtree and interaction commands.
    :param value: value for "set_input" / "set_slider" / "scroll" /
        "navigator";
        None means omit the field.
    :param timeout: seconds to wait for a matching response.
    :return: response dict (with keys pyreact_ack/seq/tree/error) or None on timeout.
    """
    seq = new_seq()
    payload = {"cmd": cmd, "seq": seq}
    if node_id:
        payload["id"] = node_id
    if value is not None:
        payload["value"] = value
    # Clear clipboard first to avoid picking up stale content.
    write_clipboard("")
    time.sleep(0.05)
    trigger = json.dumps({"pyreact_debug": payload}, ensure_ascii=False)
    write_clipboard(trigger)
    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(0.1)
        content = read_clipboard()
        if not content or content == trigger:
            continue
        try:
            data = json.loads(content)
        except (ValueError, TypeError):
            continue
        if isinstance(data, dict) and data.get("seq") == seq and "pyreact_ack" in data:
            return data
    return None
