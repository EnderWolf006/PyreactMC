"""Instance binding, process identities and cross-process locks (stdlib only)."""
import contextlib
import ctypes
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
import uuid


def registry_dir():
    # Keep paths stable across desktop/CLI hosts and MSIX LocalAppData redirection.
    return Path(os.environ.get("USERPROFILE", tempfile.gettempdir())) / ".pyreact-debug" / "instances"


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


@contextlib.contextmanager
def file_lock(path, timeout=10):
    """OS-owned byte lock; automatically released if the owner process dies."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        handle.seek(0, 2)
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        deadline = time.monotonic() + timeout
        while True:
            try:
                handle.seek(0)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise TimeoutError("Resource busy: " + str(path))
                time.sleep(0.05)
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)


def _kernel():
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
    kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    return kernel


def _identity(kernel, handle):
    from ctypes import wintypes
    times = [wintypes.FILETIME() for _ in range(4)]
    code = wintypes.DWORD()
    if not kernel.GetProcessTimes(handle, *(ctypes.byref(t) for t in times)):
        raise OSError("GetProcessTimes failed")
    if not kernel.GetExitCodeProcess(handle, ctypes.byref(code)) or code.value != 259:
        return None
    return str((times[0].dwHighDateTime << 32) | times[0].dwLowDateTime)


def process_identity(pid):
    if os.name != "nt":
        raise RuntimeError("Managed game instances require Windows")
    kernel = _kernel()
    handle = kernel.OpenProcess(0x1000, False, int(pid))
    if not handle:
        return None
    try:
        return _identity(kernel, handle)
    finally:
        kernel.CloseHandle(handle)


def terminate_owned(pid, identity):
    """Validate and terminate using the same handle, avoiding PID reuse races."""
    kernel = _kernel()
    handle = kernel.OpenProcess(0x1000 | 0x1 | 0x100000, False, int(pid))
    if not handle:
        return
    try:
        current = _identity(kernel, handle)
        if current is None:
            return
        if current != identity:
            raise RuntimeError("Process identity changed; refusing to stop pid %s" % pid)
        if not kernel.TerminateProcess(handle, 1):
            raise OSError("TerminateProcess failed")
        kernel.WaitForSingleObject(handle, 5000)
    finally:
        kernel.CloseHandle(handle)


def load_session(path=None, owner=None, live=False):
    path = path or os.environ.get("MCDEV_SESSION_FILE")
    if not path:
        return None
    path = Path(path).resolve(strict=True)
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema") != 1 or Path(data.get("session_file", "")).resolve() != path:
        raise ValueError("Invalid instance manifest")
    owner = owner or os.environ.get("MCDEV_OWNER")
    if not owner or owner != data.get("owner"):
        raise ValueError("Instance owner mismatch; pass the assigned --owner")
    if live:
        if data.get("state") != "ready":
            raise RuntimeError("Instance is not ready: " + str(data.get("state")))
        for prefix in ("mcdk", "game"):
            if (not data.get(prefix + "_identity") or
                    process_identity(data[prefix + "_pid"]) != data[prefix + "_identity"]):
                raise RuntimeError("Stale instance: " + prefix + " process exited or changed")
    return data


def artifact_dir():
    data = load_session()
    if data:
        result = Path(data["artifacts"])
    else:
        result = Path(tempfile.gettempdir()) / "pyreact-debug"
        url = os.environ.get("MCDEV_MCP_URL")
        if url:
            result /= "endpoint-" + hashlib.sha256(url.encode()).hexdigest()[:16]
    result.mkdir(parents=True, exist_ok=True)
    return result


def default_tree_path():
    return str(artifact_dir() / "ui_tree.json")


def desktop_lock(timeout=10):
    return file_lock(registry_dir() / "desktop.lock", timeout)
