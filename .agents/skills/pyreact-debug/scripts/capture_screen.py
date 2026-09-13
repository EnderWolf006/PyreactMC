# -*- coding: utf-8 -*-
"""Capture Minecraft without changing focus or relying on third-party packages.

Windows uses ``PrintWindow`` and Linux uses an X11 Composite named pixmap.  Both
capture the target window's own surface, so another window may remain focused or
cover the game while this command runs.
"""

from __future__ import print_function

import argparse
import ctypes
import ctypes.util
from ctypes import wintypes
import json
import os
import struct
import sys
import tempfile
import time
import zlib


IS_WINDOWS = os.name == "nt"

if IS_WINDOWS:
    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32
    kernel32 = ctypes.windll.kernel32
else:
    user32 = None
    gdi32 = None
    kernel32 = None

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
SRCCOPY = 0x00CC0020
CAPTUREBLT = 0x40000000
DIB_RGB_COLORS = 0
BI_RGB = 0
SW_RESTORE = 9
PW_CLIENTONLY = 0x00000001
PW_RENDERFULLCONTENT = 0x00000002


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", ctypes.c_long),
        ("biHeight", ctypes.c_long),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", ctypes.c_long),
        ("biYPelsPerMeter", ctypes.c_long),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [
        ("bmiHeader", BITMAPINFOHEADER),
        ("bmiColors", wintypes.DWORD * 3),
    ]


if IS_WINDOWS:
    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    user32.EnumWindows.argtypes = [WNDENUMPROC, wintypes.LPARAM]
    user32.EnumWindows.restype = wintypes.BOOL
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsWindowVisible.restype = wintypes.BOOL
    user32.IsIconic.argtypes = [wintypes.HWND]
    user32.IsIconic.restype = wintypes.BOOL
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.SetForegroundWindow.restype = wintypes.BOOL
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.BringWindowToTop.argtypes = [wintypes.HWND]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
    user32.AttachThreadInput.restype = wintypes.BOOL
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextLengthW.restype = ctypes.c_int
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(RECT)]
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(RECT)]
    user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(POINT)]
    user32.GetDC.argtypes = [wintypes.HWND]
    user32.GetDC.restype = wintypes.HDC
    user32.GetWindowDC.argtypes = [wintypes.HWND]
    user32.GetWindowDC.restype = wintypes.HDC
    user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
    user32.PrintWindow.argtypes = [wintypes.HWND, wintypes.HDC, wintypes.UINT]
    user32.PrintWindow.restype = wintypes.BOOL

    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.GetCurrentThreadId.restype = wintypes.DWORD

    gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
    gdi32.CreateCompatibleDC.restype = wintypes.HDC
    gdi32.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
    gdi32.CreateCompatibleBitmap.restype = wintypes.HBITMAP
    gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
    gdi32.SelectObject.restype = wintypes.HGDIOBJ
    gdi32.BitBlt.argtypes = [
        wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        wintypes.HDC, ctypes.c_int, ctypes.c_int, wintypes.DWORD,
    ]
    gdi32.BitBlt.restype = wintypes.BOOL
    gdi32.GetDIBits.argtypes = [
        wintypes.HDC, wintypes.HBITMAP, wintypes.UINT, wintypes.UINT,
        wintypes.LPVOID, ctypes.POINTER(BITMAPINFO), wintypes.UINT,
    ]
    gdi32.GetDIBits.restype = ctypes.c_int
    gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
    gdi32.DeleteDC.argtypes = [wintypes.HDC]


def _emit(payload):
    text = json.dumps(payload, ensure_ascii=False)
    if sys.version_info[0] >= 3:
        sys.stdout.buffer.write((text + "\n").encode("utf-8"))
    else:
        sys.stdout.write((text + "\n").encode("utf-8"))


def _window_text_windows(hwnd):
    length = user32.GetWindowTextLengthW(hwnd)
    if length <= 0:
        return u""
    buffer_ = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buffer_, length + 1)
    return buffer_.value


def _process_name_windows(pid):
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return u""
    try:
        size = wintypes.DWORD(32768)
        path = ctypes.create_unicode_buffer(size.value)
        query = getattr(kernel32, "QueryFullProcessImageNameW", None)
        if not query or not query(handle, 0, path, ctypes.byref(size)):
            return u""
        return os.path.basename(path.value)
    finally:
        kernel32.CloseHandle(handle)


def _window_rect_windows(hwnd, include_frame=False):
    if include_frame:
        rect = RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            raise RuntimeError("GetWindowRect failed")
        return rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top

    rect = RECT()
    if not user32.GetClientRect(hwnd, ctypes.byref(rect)):
        raise RuntimeError("GetClientRect failed")
    origin = POINT(0, 0)
    if not user32.ClientToScreen(hwnd, ctypes.byref(origin)):
        raise RuntimeError("ClientToScreen failed")
    return origin.x, origin.y, rect.right - rect.left, rect.bottom - rect.top


def _list_windows_windows():
    windows = []

    @WNDENUMPROC
    def callback(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        title = _window_text_windows(hwnd)
        if not title:
            return True
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        try:
            x, y, width, height = _window_rect_windows(hwnd)
        except RuntimeError:
            return True
        if width <= 1 or height <= 1:
            return True
        windows.append({
            "hwnd": int(hwnd),
            "pid": int(pid.value),
            "process": _process_name_windows(pid.value),
            "title": title,
            "x": x,
            "y": y,
            "width": width,
            "height": height,
            "minimized": bool(user32.IsIconic(hwnd)),
        })
        return True

    if not user32.EnumWindows(callback, 0):
        raise RuntimeError("EnumWindows failed")
    return windows


def _find_game_window(windows, pid=None, title=None, process_name=None):
    candidates = windows
    if pid is not None:
        candidates = [item for item in candidates if item["pid"] == pid]
    if title:
        title_lower = title.lower()
        candidates = [item for item in candidates if title_lower in item["title"].lower()]
    if process_name:
        process_lower = process_name.lower()
        process_matches = [
            item for item in candidates
            if item["process"].lower() == process_lower
        ]
        if process_matches:
            candidates = process_matches
        elif pid is None and not title:
            candidates = [
                item for item in candidates
                if "minecraft" in item["title"].lower()
                or u"\u6211\u7684\u4e16\u754c" in item["title"]
            ]
    if not candidates:
        return None
    candidates.sort(key=lambda item: item["width"] * item["height"], reverse=True)
    return candidates[0]


def _activate_window(hwnd):
    """Best-effort foreground activation before screen-based capture."""
    foreground = user32.GetForegroundWindow()
    current_thread = kernel32.GetCurrentThreadId()
    foreground_thread = 0
    target_thread = user32.GetWindowThreadProcessId(hwnd, None)
    attached_foreground = False
    attached_target = False
    try:
        if foreground:
            foreground_thread = user32.GetWindowThreadProcessId(foreground, None)
        if foreground_thread and foreground_thread != current_thread:
            attached_foreground = bool(user32.AttachThreadInput(
                current_thread, foreground_thread, True,
            ))
        if target_thread and target_thread != current_thread:
            attached_target = bool(user32.AttachThreadInput(
                current_thread, target_thread, True,
            ))
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, SW_RESTORE)
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
    finally:
        if attached_target:
            user32.AttachThreadInput(current_thread, target_thread, False)
        if attached_foreground:
            user32.AttachThreadInput(current_thread, foreground_thread, False)
    return user32.GetForegroundWindow() == hwnd


# X11 declarations live here instead of importing python-xlib so the debug
# utility keeps its existing standard-library-only installation footprint.
class XWindowAttributes(ctypes.Structure):
    _fields_ = [
        ("x", ctypes.c_int),
        ("y", ctypes.c_int),
        ("width", ctypes.c_int),
        ("height", ctypes.c_int),
        ("border_width", ctypes.c_int),
        ("depth", ctypes.c_int),
        ("visual", ctypes.c_void_p),
        ("root", ctypes.c_ulong),
        ("window_class", ctypes.c_int),
        ("bit_gravity", ctypes.c_int),
        ("win_gravity", ctypes.c_int),
        ("backing_store", ctypes.c_int),
        ("backing_planes", ctypes.c_ulong),
        ("backing_pixel", ctypes.c_ulong),
        ("save_under", ctypes.c_int),
        ("colormap", ctypes.c_ulong),
        ("map_installed", ctypes.c_int),
        ("map_state", ctypes.c_int),
        ("all_event_masks", ctypes.c_long),
        ("your_event_mask", ctypes.c_long),
        ("do_not_propagate_mask", ctypes.c_long),
        ("override_redirect", ctypes.c_int),
        ("screen", ctypes.c_void_p),
    ]


class XImage(ctypes.Structure):
    pass


XDestroyImageProc = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.POINTER(XImage))


class XImageFuncs(ctypes.Structure):
    _fields_ = [
        ("create_image", ctypes.c_void_p),
        ("destroy_image", XDestroyImageProc),
        ("get_pixel", ctypes.c_void_p),
        ("put_pixel", ctypes.c_void_p),
        ("sub_image", ctypes.c_void_p),
        ("add_pixel", ctypes.c_void_p),
    ]


XImage._fields_ = [
        ("width", ctypes.c_int),
        ("height", ctypes.c_int),
        ("xoffset", ctypes.c_int),
        ("format", ctypes.c_int),
        ("data", ctypes.c_void_p),
        ("byte_order", ctypes.c_int),
        ("bitmap_unit", ctypes.c_int),
        ("bitmap_bit_order", ctypes.c_int),
        ("bitmap_pad", ctypes.c_int),
        ("depth", ctypes.c_int),
        ("bytes_per_line", ctypes.c_int),
        ("bits_per_pixel", ctypes.c_int),
        ("red_mask", ctypes.c_ulong),
        ("green_mask", ctypes.c_ulong),
        ("blue_mask", ctypes.c_ulong),
        ("obdata", ctypes.c_void_p),
        ("funcs", XImageFuncs),
]


def _load_x11():
    library_name = ctypes.util.find_library("X11")
    if not library_name:
        raise RuntimeError("libX11 is required for Linux background capture")
    x11 = ctypes.CDLL(library_name)
    x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
    x11.XOpenDisplay.restype = ctypes.c_void_p
    x11.XCloseDisplay.argtypes = [ctypes.c_void_p]
    x11.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
    x11.XDefaultRootWindow.restype = ctypes.c_ulong
    x11.XQueryTree.argtypes = [
        ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(ctypes.c_ulong),
        ctypes.POINTER(ctypes.c_ulong), ctypes.POINTER(ctypes.POINTER(ctypes.c_ulong)),
        ctypes.POINTER(ctypes.c_uint),
    ]
    x11.XQueryTree.restype = ctypes.c_int
    x11.XInternAtom.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
    x11.XInternAtom.restype = ctypes.c_ulong
    x11.XGetWindowProperty.argtypes = [
        ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_long,
        ctypes.c_long, ctypes.c_int, ctypes.c_ulong, ctypes.POINTER(ctypes.c_ulong),
        ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_ulong),
        ctypes.POINTER(ctypes.c_ulong), ctypes.POINTER(ctypes.POINTER(ctypes.c_ubyte)),
    ]
    x11.XGetWindowProperty.restype = ctypes.c_int
    x11.XGetWindowAttributes.argtypes = [
        ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(XWindowAttributes),
    ]
    x11.XGetWindowAttributes.restype = ctypes.c_int
    x11.XFetchName.argtypes = [
        ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(ctypes.c_void_p),
    ]
    x11.XFetchName.restype = ctypes.c_int
    x11.XTranslateCoordinates.argtypes = [
        ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_int,
        ctypes.c_int, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int),
        ctypes.POINTER(ctypes.c_ulong),
    ]
    x11.XTranslateCoordinates.restype = ctypes.c_int
    x11.XGetImage.argtypes = [
        ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int, ctypes.c_int,
        ctypes.c_uint, ctypes.c_uint, ctypes.c_ulong, ctypes.c_int,
    ]
    x11.XGetImage.restype = ctypes.POINTER(XImage)
    x11.XFree.argtypes = [ctypes.c_void_p]
    x11.XFree.restype = ctypes.c_int
    x11.XFreePixmap.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    x11.XFreePixmap.restype = ctypes.c_int
    x11.XSync.argtypes = [ctypes.c_void_p, ctypes.c_int]
    return x11


def _x11_open_display(x11):
    if not os.environ.get("DISPLAY"):
        raise RuntimeError(
            "DISPLAY is not set; Linux background capture requires an X11 session"
        )
    display = x11.XOpenDisplay(None)
    if not display:
        raise RuntimeError("XOpenDisplay failed for %s" % os.environ["DISPLAY"])
    return display


def _x11_window_title(x11, display, window_id):
    value = ctypes.c_void_p()
    if not x11.XFetchName(display, window_id, ctypes.byref(value)) or not value.value:
        return u""
    try:
        raw = ctypes.string_at(value.value)
        return raw.decode("utf-8", "replace")
    finally:
        x11.XFree(value)


def _x11_property_values(x11, display, window_id, property_name, limit=4096):
    atom = x11.XInternAtom(display, property_name.encode("ascii"), True)
    if not atom:
        return []
    actual_type = ctypes.c_ulong()
    actual_format = ctypes.c_int()
    item_count = ctypes.c_ulong()
    bytes_after = ctypes.c_ulong()
    data = ctypes.POINTER(ctypes.c_ubyte)()
    status = x11.XGetWindowProperty(
        display, window_id, atom, 0, limit, False, 0,
        ctypes.byref(actual_type), ctypes.byref(actual_format),
        ctypes.byref(item_count), ctypes.byref(bytes_after), ctypes.byref(data),
    )
    if status != 0 or not data or actual_format.value != 32:
        if data:
            x11.XFree(data)
        return []
    try:
        values = ctypes.cast(data, ctypes.POINTER(ctypes.c_ulong))
        return [int(values[index]) for index in range(item_count.value)]
    finally:
        x11.XFree(data)


def _x11_window_pid(x11, display, window_id):
    values = _x11_property_values(x11, display, window_id, "_NET_WM_PID", 1)
    return values[0] if values else None


def _linux_process_name(pid):
    if not pid:
        return ""
    try:
        with open("/proc/%d/comm" % pid, "rb") as handle:
            return handle.read().strip().decode("utf-8", "replace")
    except (IOError, OSError):
        return ""


def _x11_top_level_windows(x11, display, root):
    for property_name in ("_NET_CLIENT_LIST_STACKING", "_NET_CLIENT_LIST"):
        values = _x11_property_values(x11, display, root, property_name)
        if values:
            return values

    root_return = ctypes.c_ulong()
    parent_return = ctypes.c_ulong()
    children = ctypes.POINTER(ctypes.c_ulong)()
    count = ctypes.c_uint()
    if not x11.XQueryTree(
            display, root, ctypes.byref(root_return), ctypes.byref(parent_return),
            ctypes.byref(children), ctypes.byref(count)):
        raise RuntimeError("XQueryTree failed")
    try:
        return [int(children[index]) for index in range(count.value)]
    finally:
        if children:
            x11.XFree(children)


def _x11_window_rect(x11, display, window_id):
    attrs = XWindowAttributes()
    if not x11.XGetWindowAttributes(display, window_id, ctypes.byref(attrs)):
        raise RuntimeError("XGetWindowAttributes failed for window %d" % window_id)
    root = x11.XDefaultRootWindow(display)
    x = ctypes.c_int()
    y = ctypes.c_int()
    child = ctypes.c_ulong()
    if not x11.XTranslateCoordinates(
            display, window_id, root, 0, 0, ctypes.byref(x), ctypes.byref(y),
            ctypes.byref(child)):
        x.value = attrs.x
        y.value = attrs.y
    return x.value, y.value, attrs.width, attrs.height, attrs


def _list_windows_linux():
    x11 = _load_x11()
    display = _x11_open_display(x11)
    try:
        root = x11.XDefaultRootWindow(display)
        result = []
        for window_id in _x11_top_level_windows(x11, display, root):
            try:
                x, y, width, height, attrs = _x11_window_rect(
                    x11, display, window_id,
                )
            except RuntimeError:
                continue
            title = _x11_window_title(x11, display, window_id)
            if not title or width <= 1 or height <= 1 or attrs.map_state == 0:
                continue
            pid = _x11_window_pid(x11, display, window_id)
            result.append({
                "hwnd": window_id,
                "pid": pid,
                "process": _linux_process_name(pid),
                "title": title,
                "x": x,
                "y": y,
                "width": width,
                "height": height,
                "minimized": attrs.map_state != 2,
            })
        return result
    finally:
        x11.XCloseDisplay(display)


def _window_rect(hwnd, include_frame=False):
    if IS_WINDOWS:
        return _window_rect_windows(hwnd, include_frame=include_frame)
    if include_frame:
        raise RuntimeError("--include-frame is not supported on Linux/X11")
    x11 = _load_x11()
    display = _x11_open_display(x11)
    try:
        return _x11_window_rect(x11, display, hwnd)[:4]
    finally:
        x11.XCloseDisplay(display)


def _list_windows():
    if IS_WINDOWS:
        return _list_windows_windows()
    return _list_windows_linux()


def _png_chunk(chunk_type, data):
    return (
        struct.pack(">I", len(data)) + chunk_type + data
        + struct.pack(">I", zlib.crc32(chunk_type + data) & 0xffffffff)
    )


def _write_png(path, width, height, bgra):
    raw = bytearray()
    stride = width * 4
    for row_index in range(height):
        raw.append(0)
        row = bgra[row_index * stride:(row_index + 1) * stride]
        for offset in range(0, len(row), 4):
            raw.extend((row[offset + 2], row[offset + 1], row[offset]))
    raw_bytes = raw.decode("latin-1").encode("latin-1")
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    png = (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", header)
        + _png_chunk(b"IDAT", zlib.compress(raw_bytes, 6))
        + _png_chunk(b"IEND", b"")
    )
    output_dir = os.path.dirname(os.path.abspath(path))
    if output_dir and not os.path.isdir(output_dir):
        os.makedirs(output_dir)
    with open(path, "wb") as handle:
        handle.write(png)


def _windows_bitmap_to_png(memory_dc, bitmap, width, height, output_path):
    info = BITMAPINFO()
    info.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    info.bmiHeader.biWidth = width
    info.bmiHeader.biHeight = -height
    info.bmiHeader.biPlanes = 1
    info.bmiHeader.biBitCount = 32
    info.bmiHeader.biCompression = BI_RGB
    pixels = ctypes.create_string_buffer(width * height * 4)
    rows = gdi32.GetDIBits(
        memory_dc, bitmap, 0, height, pixels, ctypes.byref(info),
        DIB_RGB_COLORS,
    )
    if rows != height:
        raise RuntimeError("GetDIBits returned %d of %d rows" % (rows, height))
    _write_png(output_path, width, height, bytearray(pixels.raw))


def _capture_window_windows(hwnd, width, height, include_frame, output_path):
    window_dc = user32.GetWindowDC(hwnd) if include_frame else user32.GetDC(hwnd)
    if not window_dc:
        raise RuntimeError("GetWindowDC failed")
    memory_dc = None
    bitmap = None
    old_bitmap = None
    try:
        memory_dc = gdi32.CreateCompatibleDC(window_dc)
        if not memory_dc:
            raise RuntimeError("CreateCompatibleDC failed")
        bitmap = gdi32.CreateCompatibleBitmap(window_dc, width, height)
        if not bitmap:
            raise RuntimeError("CreateCompatibleBitmap failed")
        old_bitmap = gdi32.SelectObject(memory_dc, bitmap)
        flags = PW_RENDERFULLCONTENT
        if not include_frame:
            flags |= PW_CLIENTONLY
        if not user32.PrintWindow(hwnd, memory_dc, flags):
            raise RuntimeError(
                "PrintWindow failed; use windowed mode and disable exclusive fullscreen"
            )
        _windows_bitmap_to_png(memory_dc, bitmap, width, height, output_path)
    finally:
        if old_bitmap and memory_dc:
            gdi32.SelectObject(memory_dc, old_bitmap)
        if bitmap:
            gdi32.DeleteObject(bitmap)
        if memory_dc:
            gdi32.DeleteDC(memory_dc)
        user32.ReleaseDC(hwnd, window_dc)


def _capture_region_windows(x, y, width, height, output_path):
    if width <= 0 or height <= 0:
        raise ValueError("capture region must have positive width and height")

    screen_dc = user32.GetDC(0)
    if not screen_dc:
        raise RuntimeError("GetDC failed")
    memory_dc = None
    bitmap = None
    old_bitmap = None
    try:
        memory_dc = gdi32.CreateCompatibleDC(screen_dc)
        if not memory_dc:
            raise RuntimeError("CreateCompatibleDC failed")
        bitmap = gdi32.CreateCompatibleBitmap(screen_dc, width, height)
        if not bitmap:
            raise RuntimeError("CreateCompatibleBitmap failed")
        old_bitmap = gdi32.SelectObject(memory_dc, bitmap)
        if not gdi32.BitBlt(
                memory_dc, 0, 0, width, height, screen_dc, x, y,
                SRCCOPY | CAPTUREBLT):
            raise RuntimeError("BitBlt failed")

        _windows_bitmap_to_png(memory_dc, bitmap, width, height, output_path)
    finally:
        if old_bitmap and memory_dc:
            gdi32.SelectObject(memory_dc, old_bitmap)
        if bitmap:
            gdi32.DeleteObject(bitmap)
        if memory_dc:
            gdi32.DeleteDC(memory_dc)
        user32.ReleaseDC(0, screen_dc)


def _load_xcomposite():
    library_name = ctypes.util.find_library("Xcomposite")
    if not library_name:
        raise RuntimeError(
            "libXcomposite is required for unobscured Linux background capture"
        )
    composite = ctypes.CDLL(library_name)
    composite.XCompositeQueryExtension.argtypes = [
        ctypes.c_void_p, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int),
    ]
    composite.XCompositeQueryExtension.restype = ctypes.c_int
    composite.XCompositeNameWindowPixmap.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    composite.XCompositeNameWindowPixmap.restype = ctypes.c_ulong
    return composite


def _mask_component(pixel, mask):
    if not mask:
        return 0
    shift = 0
    shifted_mask = mask
    while not shifted_mask & 1:
        shifted_mask >>= 1
        shift += 1
    value = (pixel & mask) >> shift
    return int((value * 255 + shifted_mask // 2) // shifted_mask)


def _ximage_to_bgra(image):
    value = image.contents
    if value.bits_per_pixel not in (24, 32):
        raise RuntimeError(
            "unsupported X11 pixel depth: %d bits per pixel" % value.bits_per_pixel
        )
    bytes_per_pixel = value.bits_per_pixel // 8
    raw_size = value.bytes_per_line * value.height
    raw = ctypes.string_at(value.data, raw_size)
    output = bytearray(value.width * value.height * 4)
    output_offset = 0
    byte_order = "little" if value.byte_order == 0 else "big"
    for row_index in range(value.height):
        row_offset = row_index * value.bytes_per_line
        for column_index in range(value.width):
            offset = row_offset + column_index * bytes_per_pixel
            pixel = int.from_bytes(
                raw[offset:offset + bytes_per_pixel], byte_order=byte_order,
            )
            output[output_offset] = _mask_component(pixel, value.blue_mask)
            output[output_offset + 1] = _mask_component(pixel, value.green_mask)
            output[output_offset + 2] = _mask_component(pixel, value.red_mask)
            output[output_offset + 3] = 255
            output_offset += 4
    return output


def _capture_x11_drawable(x11, display, drawable, width, height, output_path):
    image = x11.XGetImage(
        display, drawable, 0, 0, width, height, 0xffffffffffffffff, 2,
    )
    if not image:
        raise RuntimeError("XGetImage failed")
    try:
        _write_png(output_path, width, height, _ximage_to_bgra(image))
    finally:
        image.contents.funcs.destroy_image(image)


def _capture_window_linux(window_id, width, height, output_path):
    x11 = _load_x11()
    composite = _load_xcomposite()
    display = _x11_open_display(x11)
    pixmap = 0
    try:
        event_base = ctypes.c_int()
        error_base = ctypes.c_int()
        if not composite.XCompositeQueryExtension(
                display, ctypes.byref(event_base), ctypes.byref(error_base)):
            raise RuntimeError("the X11 Composite extension is unavailable")
        pixmap = composite.XCompositeNameWindowPixmap(display, window_id)
        x11.XSync(display, False)
        if not pixmap:
            raise RuntimeError(
                "XCompositeNameWindowPixmap failed; ensure an X11 compositor is running"
            )
        _capture_x11_drawable(x11, display, pixmap, width, height, output_path)
    finally:
        if pixmap:
            x11.XFreePixmap(display, pixmap)
        x11.XCloseDisplay(display)


def _capture_region_linux(x, y, width, height, output_path):
    x11 = _load_x11()
    display = _x11_open_display(x11)
    try:
        root = x11.XDefaultRootWindow(display)
        image = x11.XGetImage(
            display, root, x, y, width, height, 0xffffffffffffffff, 2,
        )
        if not image:
            raise RuntimeError("XGetImage failed for desktop region")
        try:
            _write_png(output_path, width, height, _ximage_to_bgra(image))
        finally:
            image.contents.funcs.destroy_image(image)
    finally:
        x11.XCloseDisplay(display)


def _default_output():
    directory = os.path.join(tempfile.gettempdir(), "pyreact-debug", "screenshots")
    filename = "minecraft_%s.png" % time.strftime("%Y%m%d_%H%M%S")
    return os.path.join(directory, filename)


def _parse_region(value):
    try:
        values = [int(part.strip()) for part in value.split(",")]
    except ValueError:
        raise argparse.ArgumentTypeError("region must be X,Y,WIDTH,HEIGHT")
    if len(values) != 4 or values[2] <= 0 or values[3] <= 0:
        raise argparse.ArgumentTypeError("region must be X,Y,WIDTH,HEIGHT")
    return tuple(values)


def main():
    parser = argparse.ArgumentParser(
        description="Capture Minecraft in the background without changing focus",
    )
    parser.add_argument("--output", default=None, help="PNG output path")
    parser.add_argument("--pid", type=int, default=None, help="game process id")
    parser.add_argument("--title", default=None, help="window title substring")
    parser.add_argument(
        "--process-name", default="Minecraft.Windows.exe",
        help="game executable name (default: Minecraft.Windows.exe)",
    )
    parser.add_argument(
        "--include-frame", action="store_true",
        help="include the title bar and window border",
    )
    parser.add_argument(
        "--region", type=_parse_region, default=None,
        help="capture screen region X,Y,WIDTH,HEIGHT instead of finding a window",
    )
    parser.add_argument(
        "--list-windows", action="store_true",
        help="list visible top-level windows and exit",
    )
    args = parser.parse_args()

    try:
        if IS_WINDOWS:
            set_dpi_aware = getattr(user32, "SetProcessDPIAware", None)
            if set_dpi_aware:
                set_dpi_aware()

        windows = _list_windows()
        if args.list_windows:
            _emit({"ok": True, "windows": windows})
            return 0

        window = None
        backend = None
        if args.region:
            x, y, width, height = args.region
        else:
            window = _find_game_window(
                windows, pid=args.pid, title=args.title,
                process_name=args.process_name,
            )
            if not window:
                raise RuntimeError(
                    "Minecraft window not found; use --list-windows, --pid, or --title"
                )
            if window["minimized"]:
                raise RuntimeError(
                    "Minecraft window is minimized; restore it before background capture"
                )
            x, y, width, height = _window_rect(
                window["hwnd"], include_frame=args.include_frame,
            )

        output_path = os.path.abspath(args.output or _default_output())
        if window:
            if IS_WINDOWS:
                backend = "win32-printwindow"
                _capture_window_windows(
                    window["hwnd"], width, height, args.include_frame, output_path,
                )
            else:
                backend = "x11-composite"
                _capture_window_linux(window["hwnd"], width, height, output_path)
        else:
            backend = "win32-desktop-bitblt" if IS_WINDOWS else "x11-root-image"
            if IS_WINDOWS:
                _capture_region_windows(x, y, width, height, output_path)
            else:
                _capture_region_linux(x, y, width, height, output_path)
        _emit({
            "ok": True,
            "path": output_path,
            "width": width,
            "height": height,
            "region": [x, y, width, height],
            "window": window,
            "activated": False,
            "background": bool(window),
            "backend": backend,
        })
        return 0
    except Exception as exc:
        _emit({"ok": False, "error": str(exc)})
        return 1


if __name__ == "__main__":
    sys.exit(main())
