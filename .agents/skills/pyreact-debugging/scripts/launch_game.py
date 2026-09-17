# -*- coding: utf-8 -*-
"""
Launch Minecraft.Windows.exe and start a detached log server.

Usage:
    python3 launch_game.py [--config FILE] [--project DIR] [--port PORT] [--log-output FILE]
"""

import argparse
import os
import shutil
import subprocess
import socket
import sys
import time

from _mcs import (
    ensure_pack_links,
    find_latest_cppconfig,
    get_minecraft_exe,
    get_wine_prefix,
    setup_runtime,
    to_windows_path,
)
from kill_game import kill_game

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.normpath(os.path.join(_SCRIPT_DIR, "..", "..", "..", ".."))

_READY_SIGNAL = '=====> PyreactRuntime AppReady:'


def _find_free_port():
    s = socket.socket()
    s.bind(("", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _poll_ready(port, deadline, ready_file=None, log_file=None):
    """Poll for the AppReady signal. Tries the HTTP API first; if that is
    unreachable, falls back to the ready-file marker and finally to grepping
    the log file. Robust against the HTTP API being down or slow to start."""
    try:
        from urllib.request import urlopen
    except ImportError:
        from urllib2 import urlopen
    import json

    http_down = False
    while time.time() < deadline:
        time.sleep(0.5)
        # 1. HTTP API (preferred).
        if not http_down:
            try:
                url = "http://localhost:%d/logs?grep=%s" % (
                    port + 1, "PyreactRuntime+AppReady"
                )
                resp = urlopen(url, timeout=3)
                data = json.loads(resp.read().decode('utf-8'))
                for entry in data["lines"]:
                    if _READY_SIGNAL in entry["text"]:
                        return True
                continue
            except Exception:
                http_down = True  # stop retrying HTTP; switch to file fallbacks
        # 2. ready-file marker (written by log_server when AppReady appears).
        if ready_file and os.path.isfile(ready_file):
            return True
        # 3. last resort: grep the log file directly.
        if log_file and os.path.isfile(log_file):
            try:
                with open(log_file, "rb") as f:
                    if _READY_SIGNAL.encode("utf-8") in f.read():
                        return True
            except Exception:
                pass
    return False


def main():
    parser = argparse.ArgumentParser(description="Launch Minecraft game + detached log server")
    parser.add_argument("--config", default=None)
    parser.add_argument("--project", default=None)
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--log-output", default=None)
    parser.add_argument("--engine-dir", default=None,
                        help="override the Linux game directory from config.py")
    parser.add_argument("--wine-prefix", default=None,
                        help="Wine prefix (auto-detected from .wine-mcchina by default)")
    parser.add_argument("--wine", default=None,
                        help="Wine executable (default: MCCHINA_WINE or wine)")
    args = parser.parse_args()

    if args.engine_dir:
        os.environ["MCCHINA_ENGINE_DIR"] = os.path.abspath(args.engine_dir)
    if args.wine_prefix:
        os.environ["MCCHINA_WINEPREFIX"] = os.path.abspath(args.wine_prefix)

    print("[launch_game] killing existing game and log_server processes...")
    kill_game(wait=True)

    if args.project:
        project_root = os.path.abspath(args.project)
    elif os.path.isfile(os.path.join(os.getcwd(), "studio.json")):
        project_root = os.getcwd()
    elif args.config and os.path.basename(os.path.dirname(os.path.abspath(args.config))) == ".runtime":
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(args.config)))
    else:
        sync_cmd = os.path.join(_PROJECT_ROOT, "sync_to_test.cmd")
        if os.path.isfile(sync_cmd):
            target_root = None
            with open(sync_cmd, "r") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("set") and "TARGET_ROOT=" in line and "TARGET_UI_ROOT" not in line:
                        val = line.split("TARGET_ROOT=", 1)[1].strip().strip('"')
                        target_root = os.path.dirname(val)
                        break
            if target_root and os.path.isfile(os.path.join(target_root, "studio.json")):
                print("[launch_game] detected pyreact framework dir.")
                print("[launch_game] addon project is at: %s" % target_root)
                print("[launch_game] re-run from there, or pass --project explicitly.")
                sys.exit(0)
        project_root = _PROJECT_ROOT

    exe = get_minecraft_exe(project_root)
    if not exe:
        print("[launch_game] ERROR: Minecraft.Windows.exe not found.")
        if sys.platform != "win32":
            print("[launch_game] set --engine-dir or MCCHINA_ENGINE_DIR.")
        sys.exit(1)

    wine_prefix = None
    if sys.platform != "win32":
        wine_prefix = get_wine_prefix(project_root)
        if not wine_prefix:
            print("[launch_game] ERROR: Wine prefix not found.")
            print("[launch_game] set --wine-prefix or MCCHINA_WINEPREFIX.")
            sys.exit(1)

    if args.config:
        config_path = os.path.abspath(args.config)
        ensure_pack_links(project_root, wine_prefix)
    else:
        config_path = find_latest_cppconfig(project_root)
        regenerate = not config_path
        if config_path and sys.platform != "win32":
            try:
                import json
                with open(config_path, "r", encoding="utf-8") as config_file:
                    config_version = json.load(config_file).get("version")
                engine_version = os.path.basename(os.path.dirname(exe))
                regenerate = config_version != engine_version
                if regenerate:
                    print("[launch_game] config version %s does not match engine %s." % (
                        config_version, engine_version
                    ))
            except Exception:
                regenerate = True
        if regenerate:
            print("[launch_game] no .cppconfig found, generating one...")
            config_path = setup_runtime(project_root, wine_prefix)
        else:
            ensure_pack_links(project_root, wine_prefix)
        print("[launch_game] using config: %s" % config_path)

    port = args.port if args.port else _find_free_port()

    import tempfile
    if not args.log_output:
        log_dir = os.path.join(tempfile.gettempdir(), "pyreact-debug")
        if not os.path.isdir(log_dir):
            os.makedirs(log_dir)
        args.log_output = os.path.join(log_dir, "pyreact_game_%d.log" % port)

    # ready-file marker: log_server writes this tiny file the moment the
    # AppReady signal appears in a log line, so _poll_ready can detect it
    # even when the HTTP API is unreachable.
    ready_file = args.log_output + ".ready"
    # diag file: captures log_server's own stderr (thread excepthooks etc.)
    diag_file = args.log_output + ".diag"
    for stale_file in (ready_file, diag_file):
        try:
            os.remove(stale_file)
        except OSError:
            pass

    game_args = [
        "config=%s" % config_path,
        "loggingIP=localhost",
        "loggingPort=%d" % port,
    ]
    game_kwargs = {
        "close_fds": True,
        "cwd": os.path.dirname(exe),
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if sys.platform == "win32":
        CREATE_NEW_PROCESS_GROUP = 0x00000200
        CREATE_NEW_CONSOLE = 0x00000010
        game_cmd = [exe] + game_args
        game_kwargs["creationflags"] = CREATE_NEW_CONSOLE | CREATE_NEW_PROCESS_GROUP
    else:
        wine = args.wine or os.environ.get("MCCHINA_WINE") or shutil.which("wine")
        if not wine:
            print("[launch_game] ERROR: wine executable not found.")
            sys.exit(1)
        wine_env = os.environ.copy()
        wine_env["WINEPREFIX"] = wine_prefix
        wine_env.setdefault("WINEARCH", "win64")
        wine_env.setdefault("WINEDEBUG", "-all")
        game_args[0] = "config=%s" % to_windows_path(config_path, wine_prefix)
        game_cmd = [wine, exe] + game_args
        game_kwargs["env"] = wine_env
        game_kwargs["start_new_session"] = True

    game_proc = subprocess.Popen(game_cmd, **game_kwargs)

    server_cmd = [sys.executable, os.path.join(_SCRIPT_DIR, "log_server.py"),
                  "--port", str(port),
                  "--game-pid", str(game_proc.pid),
                  "--output", args.log_output,
                  "--ready-file", ready_file,
                  "--diag", diag_file]

    server_kwargs = {
        "close_fds": True,
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if sys.platform == "win32":
        CREATE_NO_WINDOW = 0x08000000
        CREATE_NEW_PROCESS_GROUP = 0x00000200
        server_kwargs["creationflags"] = CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP
    else:
        server_kwargs["start_new_session"] = True
    subprocess.Popen(server_cmd, **server_kwargs)

    print("[launch_game] game launched.")
    print("[launch_game] game pid: %d" % game_proc.pid)
    if sys.platform != "win32":
        print("[launch_game] engine: %s" % os.path.dirname(exe))
        print("[launch_game] wine prefix: %s" % wine_prefix)
    print("[launch_game] log server port: %d" % port)
    print("[launch_game] log file: %s" % args.log_output)
    print("[launch_game] diag file: %s" % diag_file)
    print("[launch_game] waiting for AppReady signal (max 60s)...")

    # Give log_server a moment to bind its HTTP port
    time.sleep(1.5)

    if _poll_ready(port, time.time() + 60, ready_file=ready_file, log_file=args.log_output):
        print("[launch_game] AppReady received, done.")
    else:
        print("[launch_game] timeout. Game continues running on port %d." % port)
        print("[launch_game] HTTP API may be down; use get_logs.py --from-file %s" % args.log_output)
        print("[launch_game] check diag file for log_server errors: %s" % diag_file)


if __name__ == "__main__":
    main()
