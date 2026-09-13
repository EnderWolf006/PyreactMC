# -*- coding: utf-8 -*-
"""
Kill all running Minecraft.Windows.exe processes.

Usage:
    python3 kill_game.py [--wait]
"""

import argparse
import os
import sys


def _is_game_process(info):
    name = (info.get('name') or '').lower()
    if name in ('minecraft.windows.exe', 'minecraft.window'):
        return True
    cmdline = info.get('cmdline') or []
    return any(os.path.basename(arg or '').lower() == 'minecraft.windows.exe'
               for arg in cmdline)


def _is_log_server_process(info):
    cmdline = info.get('cmdline') or []
    return any(os.path.basename(arg or '') == 'log_server.py' for arg in cmdline)


def kill_game(wait=False):
    try:
        import psutil
    except ImportError:
        print("[kill_game] psutil not installed. Run: pip3 install psutil")
        sys.exit(1)

    import time

    killed = []
    for proc in psutil.process_iter(['name', 'pid', 'cmdline']):
        if _is_game_process(proc.info):
            try:
                proc.kill()
                killed.append(('game', proc.info['pid']))
            except Exception as e:
                print("[kill_game] failed to kill game pid %d: %s" % (proc.info['pid'], e))
        elif _is_log_server_process(proc.info):
            try:
                proc.kill()
                killed.append(('log_server', proc.info['pid']))
            except Exception as e:
                print("[kill_game] failed to kill log_server pid %d: %s" % (proc.info['pid'], e))

    if not killed:
        print("[kill_game] no processes found")
        return False

    print("[kill_game] killed: %s" % killed)

    # ALWAYS verify the game is gone (the original bug: this only ran with
    # --wait, so a plain `kill_game.py` reported success while the OS was still
    # reaping the process and a follow-up check saw it linger). Escalate with a
    # second kill if it survives the wait.
    deadline = time.time() + (10 if wait else 4)
    while time.time() < deadline:
        still = [p for p in psutil.process_iter(['name', 'cmdline'])
                 if _is_game_process(p.info)]
        if not still:
            break
        time.sleep(0.3)

    still = [p for p in psutil.process_iter(['name', 'pid', 'cmdline'])
             if _is_game_process(p.info)]
    if still:
        print("[kill_game] WARNING: still alive, escalating force-kill: %s" % [p.info['pid'] for p in still])
        for p in still:
            try:
                p.kill()
            except Exception:
                pass
        time.sleep(1.0)

    return True


def main():
    parser = argparse.ArgumentParser(description="Kill Minecraft game process")
    parser.add_argument("--wait", action="store_true", help="Wait until process is gone")
    args = parser.parse_args()
    ok = kill_game(wait=args.wait)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
