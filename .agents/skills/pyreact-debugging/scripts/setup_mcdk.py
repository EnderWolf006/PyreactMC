"""Check prerequisites and optionally install the pinned MCDK release per user."""
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import sys
import tempfile
import urllib.request

VERSION = "v1.6.1"
RELEASE = "https://github.com/GitHub-Zero123/MCDevTool/releases/download/" + VERSION
ASSETS = {
    "mcdk.exe": "2cd4348c05a1b3855f4397526a9c4c3deea359d2e57f07a61e2669bd5b47349b",
    "mcdk_stdio_bridge.exe": "dbb9c853715af4720c6871c2d551e0a0c41d7cd0e850e54ed987e515d1ea1b9f",
    "mcdev-tracy-bridge.dll": "7b4424d2322b45e69388fcedd0a9b8ee104eccf2a4c58d7f584c6e53601145d5",
}


def install_dir():
    return Path(os.environ.get("USERPROFILE", str(Path.home()))) / ".pyreact-debug" / "tools" / "mcdk" / VERSION


def resolve_mcdk(explicit=None):
    chosen = explicit or os.environ.get("MCDK_EXE")
    if chosen:
        result = shutil.which(chosen)
        if not result:
            raise FileNotFoundError("MCDK override does not exist: " + chosen)
        return str(Path(result).resolve())
    cached = install_dir() / "mcdk.exe"
    result = str(cached) if cached.is_file() else shutil.which("mcdk")
    return str(Path(result).resolve()) if result else None


def find_games():
    """Bounded discovery in MC Studio's standard drive-root installation paths."""
    if os.name != "nt":
        return []
    mask = ctypes.windll.kernel32.GetLogicalDrives()
    result = set()
    for index in range(26):
        if not mask & (1 << index):
            continue
        drive = chr(65 + index) + ":/"
        # Skip removable and disconnected/network drives.
        if ctypes.windll.kernel32.GetDriveTypeW(ctypes.c_wchar_p(drive)) != 3:
            continue
        root = Path(drive) / "MCStudioDownload/game/MinecraftPE_Netease"
        if root.is_dir():
            result.update(str(p.resolve()) for p in root.glob("*/Minecraft.Windows.exe") if p.is_file())
    return sorted(result)


def resolve_game(project, config, explicit=None):
    chosen = explicit or config.get("game_executable_path")
    if chosen:
        path = (Path(project) / chosen).resolve()
        if not path.is_file():
            raise FileNotFoundError("Game path does not exist; pass --game-exe: " + str(path))
        return str(path)
    candidates = find_games()
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        raise FileNotFoundError("No development game found. Download it in MC Studio or pass --game-exe for a custom location")
    raise ValueError("Multiple development games found; choose the project's version with --game-exe: " + json.dumps(candidates))


def install_asset(name):
    destination = install_dir() / name
    destination.parent.mkdir(parents=True, exist_ok=True)
    expected = ASSETS[name]
    if destination.is_file():
        if hashlib.sha256(destination.read_bytes()).hexdigest() == expected:
            return str(destination)
        raise ValueError("Existing MCDK asset checksum differs; inspect before replacing: " + str(destination))
    # Download beside the destination, verify before atomic publication.
    temporary = None
    try:
        request = urllib.request.Request(RELEASE + "/" + name, headers={"User-Agent": "pyreact-debugging"})
        digest = hashlib.sha256()
        with urllib.request.urlopen(request, timeout=30) as response, tempfile.NamedTemporaryFile(
                dir=destination.parent, suffix=".download", delete=False) as output:
            temporary = Path(output.name)
            total = 0
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > 32 * 1024 * 1024:
                    raise ValueError("Release asset exceeds expected size limit")
                output.write(chunk)
                digest.update(chunk)
        if digest.hexdigest() != expected:
            raise ValueError("Release SHA-256 mismatch: " + name)
        os.replace(temporary, destination)
        return str(destination)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--install", action="store_true", help="download pinned official mcdk.exe with SHA-256 verification")
    parser.add_argument("--native", action="store_true", help="also install optional Native profiler DLL (requires --install)")
    parser.add_argument("--stdio", action="store_true", help="also install optional stdio bridge (requires --install)")
    parser.add_argument("--project", help="Addon/map root; reads but never creates .mcdev.json")
    parser.add_argument("--game-exe", help="explicit development game path")
    parser.add_argument("--mcdk", help="explicit existing mcdk.exe")
    args = parser.parse_args()
    if (args.native or args.stdio) and not args.install:
        parser.error("--native/--stdio require --install")
    report = {"ok": False, "release": VERSION, "install_dir": str(install_dir()), "issues": []}
    try:
        if os.name != "nt" or platform.machine().lower() not in ("amd64", "x86_64"):
            raise RuntimeError("Managed MCDK setup requires Windows x64")
        if sys.version_info < (3, 12):
            raise RuntimeError("Use Python 3.12 or newer (python3, python, or py -3)")
        if not shutil.which("powershell.exe"):
            raise RuntimeError("Windows PowerShell is required for managed instance discovery and junctions")
        if args.install:
            names = ["mcdk.exe"]
            if args.native:
                names.append("mcdev-tracy-bridge.dll")
            if args.stdio:
                names.append("mcdk_stdio_bridge.exe")
            report["installed"] = [install_asset(name) for name in names]
        report["mcdk"] = resolve_mcdk(args.mcdk)
        if not report["mcdk"]:
            report["issues"].append("MCDK not installed: run setup_mcdk.py --install")
        # Official builds may omit MCDK_ENABLE_CLI: --help/envinfo then launch
        # the game instead of returning help. Never execute MCDK during setup.
        project = Path(args.project).resolve(strict=True) if args.project else Path.cwd()
        if not project.is_dir():
            raise ValueError("--project must be a directory")
        source = project / ".mcdev.json"
        config = json.loads(source.read_text(encoding="utf-8-sig")) if source.is_file() else {}
        if not isinstance(config, dict):
            raise ValueError(".mcdev.json must be a JSON object")
        report["game_candidates"] = find_games()
        try:
            report["game_exe"] = resolve_game(project, config, args.game_exe)
        except (ValueError, FileNotFoundError) as exc:
            report["issues"].append(str(exc))
        if args.project:
            report["project"] = str(project)
            report["config_exists"] = source.is_file()
        report["ok"] = not report["issues"]
    except Exception as exc:
        report["issues"].append(str(exc))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
