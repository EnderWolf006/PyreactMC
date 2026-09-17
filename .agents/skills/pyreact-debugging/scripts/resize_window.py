# -*- coding: utf-8 -*-
"""Resize the Minecraft client area for responsive UI testing."""

from __future__ import print_function

import argparse
import ctypes
from ctypes import wintypes
import sys
import time

from capture_screen import (
    RECT,
    SW_RESTORE,
    _activate_window,
    _emit,
    _find_game_window,
    _list_windows,
    _window_rect,
    user32,
)


GWL_STYLE = -16
GWL_EXSTYLE = -20
MONITOR_DEFAULTTONEAREST = 2
SWP_NOZORDER = 0x0004
SWP_NOOWNERZORDER = 0x0200
SWP_FRAMECHANGED = 0x0020
SWP_SHOWWINDOW = 0x0040

PRESETS = {
    "20:9": (20, 9),
    "4:3": (4, 3),
    "16:10": (16, 10),
    "16:9": (16, 9),
}
DEFAULT_HEIGHT = 1080


class MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", RECT),
        ("rcWork", RECT),
        ("dwFlags", wintypes.DWORD),
    ]


LONG_PTR = ctypes.c_longlong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_long
get_window_long = getattr(user32, "GetWindowLongPtrW", user32.GetWindowLongW)
get_window_long.argtypes = [wintypes.HWND, ctypes.c_int]
get_window_long.restype = LONG_PTR

user32.GetMenu.argtypes = [wintypes.HWND]
user32.GetMenu.restype = wintypes.HMENU
user32.IsZoomed.argtypes = [wintypes.HWND]
user32.IsZoomed.restype = wintypes.BOOL
user32.AdjustWindowRectEx.argtypes = [
    ctypes.POINTER(RECT), wintypes.DWORD, wintypes.BOOL, wintypes.DWORD,
]
user32.AdjustWindowRectEx.restype = wintypes.BOOL
user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
user32.MonitorFromWindow.restype = wintypes.HANDLE
user32.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(MONITORINFO)]
user32.GetMonitorInfoW.restype = wintypes.BOOL
user32.SetWindowPos.argtypes = [
    wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
    ctypes.c_int, ctypes.c_int, wintypes.UINT,
]
user32.SetWindowPos.restype = wintypes.BOOL


def _parse_size(value):
    normalized = value.lower().replace(" ", "")
    parts = normalized.split("x")
    if len(parts) != 2:
        raise argparse.ArgumentTypeError("size must be WIDTHxHEIGHT")
    try:
        width, height = int(parts[0]), int(parts[1])
    except ValueError:
        raise argparse.ArgumentTypeError("size must be WIDTHxHEIGHT")
    if width <= 0 or height <= 0:
        raise argparse.ArgumentTypeError("width and height must be positive")
    return width, height


def _preset_size(preset, height):
    numerator, denominator = PRESETS[preset]
    width = int(round(float(height) * numerator / denominator))
    return width, height


def _preset_payload():
    payload = {}
    for name in ("20:9", "4:3", "16:10", "16:9"):
        width, height = _preset_size(name, DEFAULT_HEIGHT)
        payload[name] = {
            "width": width,
            "height": height,
            "size": "%dx%d" % (width, height),
        }
    return payload


def _monitor_work_area(hwnd):
    monitor = user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST)
    if not monitor:
        raise RuntimeError("MonitorFromWindow failed")
    info = MONITORINFO()
    info.cbSize = ctypes.sizeof(MONITORINFO)
    if not user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
        raise RuntimeError("GetMonitorInfoW failed")
    rect = info.rcWork
    return rect.left, rect.top, rect.right, rect.bottom


def _outer_size_for_client(hwnd, client_width, client_height):
    style = int(get_window_long(hwnd, GWL_STYLE)) & 0xffffffff
    exstyle = int(get_window_long(hwnd, GWL_EXSTYLE)) & 0xffffffff
    has_menu = bool(user32.GetMenu(hwnd))
    rect = RECT(0, 0, client_width, client_height)

    adjusted = False
    adjust_for_dpi = getattr(user32, "AdjustWindowRectExForDpi", None)
    get_dpi = getattr(user32, "GetDpiForWindow", None)
    if adjust_for_dpi and get_dpi:
        adjust_for_dpi.argtypes = [
            ctypes.POINTER(RECT), wintypes.DWORD, wintypes.BOOL,
            wintypes.DWORD, wintypes.UINT,
        ]
        adjust_for_dpi.restype = wintypes.BOOL
        get_dpi.argtypes = [wintypes.HWND]
        get_dpi.restype = wintypes.UINT
        dpi = get_dpi(hwnd)
        if dpi:
            adjusted = bool(adjust_for_dpi(
                ctypes.byref(rect), style, has_menu, exstyle, dpi,
            ))
    if not adjusted:
        adjusted = bool(user32.AdjustWindowRectEx(
            ctypes.byref(rect), style, has_menu, exstyle,
        ))
    if not adjusted:
        raise RuntimeError("AdjustWindowRectEx failed")
    return rect.right - rect.left, rect.bottom - rect.top


def _resize_window(hwnd, client_width, client_height, center=True):
    _, _, current_width, current_height = _window_rect(hwnd)
    current_outer_x, current_outer_y, current_outer_width, current_outer_height = (
        _window_rect(hwnd, include_frame=True)
    )
    work_left, work_top, work_right, work_bottom = _monitor_work_area(hwnd)
    work_width = work_right - work_left
    work_height = work_bottom - work_top
    was_maximized = bool(user32.IsZoomed(hwnd))

    if current_width == client_width and current_height == client_height:
        return {
            "x": current_outer_x,
            "y": current_outer_y,
            "width": current_outer_width,
            "height": current_outer_height,
            "fitsWorkArea": (
                current_outer_width <= work_width
                and current_outer_height <= work_height
            ),
            "workArea": [work_left, work_top, work_width, work_height],
            "changed": False,
            "wasMaximized": was_maximized,
        }

    user32.ShowWindow(hwnd, SW_RESTORE)
    outer_width, outer_height = _outer_size_for_client(
        hwnd, client_width, client_height,
    )

    current_x, current_y, _, _ = _window_rect(hwnd, include_frame=True)
    if center:
        x = work_left + (work_width - outer_width) // 2
        y = work_top + (work_height - outer_height) // 2
    else:
        x, y = current_x, current_y

    flags = SWP_NOZORDER | SWP_NOOWNERZORDER | SWP_FRAMECHANGED | SWP_SHOWWINDOW
    if not user32.SetWindowPos(
            hwnd, 0, x, y, outer_width, outer_height, flags):
        raise RuntimeError("SetWindowPos failed")
    return {
        "x": x,
        "y": y,
        "width": outer_width,
        "height": outer_height,
        "fitsWorkArea": outer_width <= work_width and outer_height <= work_height,
        "workArea": [work_left, work_top, work_width, work_height],
        "changed": True,
        "wasMaximized": was_maximized,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Resize the Minecraft client area for responsive UI testing",
    )
    size_group = parser.add_mutually_exclusive_group()
    size_group.add_argument(
        "--preset", choices=("20:9", "4:3", "16:10", "16:9"),
        help="recommended responsive-test aspect ratio",
    )
    size_group.add_argument(
        "--size", type=_parse_size, help="custom client size WIDTHxHEIGHT",
    )
    parser.add_argument(
        "--height", type=int, default=DEFAULT_HEIGHT,
        help="client height used with --preset (default: 1080)",
    )
    parser.add_argument("--pid", type=int, default=None, help="game process id")
    parser.add_argument("--title", default=None, help="window title substring")
    parser.add_argument(
        "--process-name", default="Minecraft.Windows.exe",
        help="game executable name (default: Minecraft.Windows.exe)",
    )
    parser.add_argument(
        "--no-center", action="store_true",
        help="keep the current top-left position instead of centering",
    )
    parser.add_argument(
        "--no-activate", action="store_true",
        help="do not bring the resized window to the foreground",
    )
    parser.add_argument(
        "--settle", type=float, default=0.5,
        help="seconds to wait before checking the resulting client size",
    )
    parser.add_argument(
        "--list-presets", action="store_true",
        help="print recommended presets and exit",
    )
    parser.add_argument(
        "--list-windows", action="store_true",
        help="list visible top-level windows and exit",
    )
    args = parser.parse_args()

    try:
        set_dpi_aware = getattr(user32, "SetProcessDPIAware", None)
        if set_dpi_aware:
            set_dpi_aware()

        if args.list_presets:
            _emit({"ok": True, "defaultHeight": DEFAULT_HEIGHT,
                   "presets": _preset_payload()})
            return 0

        windows = _list_windows()
        if args.list_windows:
            _emit({"ok": True, "windows": windows})
            return 0
        if not args.preset and not args.size:
            raise ValueError("pass --preset or --size")
        if args.height <= 0:
            raise ValueError("--height must be positive")

        requested_width, requested_height = (
            _preset_size(args.preset, args.height)
            if args.preset else args.size
        )
        window = _find_game_window(
            windows, pid=args.pid, title=args.title,
            process_name=args.process_name,
        )
        if not window:
            raise RuntimeError(
                "Minecraft window not found; use --list-windows, --pid, or --title"
            )

        outer = _resize_window(
            window["hwnd"], requested_width, requested_height,
            center=not args.no_center,
        )
        activated = None
        if not args.no_activate:
            activated = _activate_window(window["hwnd"])
        if args.settle > 0:
            time.sleep(args.settle)

        client_x, client_y, actual_width, actual_height = _window_rect(window["hwnd"])
        matches = (
            actual_width == requested_width and actual_height == requested_height
        )
        payload = {
            "ok": matches,
            "preset": args.preset,
            "requestedClient": [requested_width, requested_height],
            "actualClient": [actual_width, actual_height],
            "clientOrigin": [client_x, client_y],
            "outerWindow": outer,
            "activated": activated,
            "window": window,
        }
        if not matches:
            payload["error"] = "actual client size does not match requested size"
        _emit(payload)
        return 0 if matches else 2
    except Exception as exc:
        _emit({"ok": False, "error": str(exc)})
        return 1


if __name__ == "__main__":
    sys.exit(main())
