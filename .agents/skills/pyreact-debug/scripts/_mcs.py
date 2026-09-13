# -*- coding: utf-8 -*-
"""MC Studio and standalone engine path discovery utilities."""

import os
import shutil
import subprocess
import sys


def _parent_dirs(path, limit=8):
    current = os.path.abspath(path)
    for _ in range(limit):
        yield current
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent


def get_wine_prefix(project_root=None):
    """Find the Wine prefix used by the standalone Linux engine."""
    for key in ("MCCHINA_WINEPREFIX", "WINEPREFIX"):
        value = os.environ.get(key)
        if value:
            return os.path.abspath(os.path.expanduser(value))

    starts = [project_root, os.getcwd()]
    for start in starts:
        if not start:
            continue
        for parent in _parent_dirs(start):
            candidate = os.path.join(parent, ".wine-mcchina")
            if os.path.isfile(os.path.join(candidate, "system.reg")):
                return candidate
    return None


def to_windows_path(path, wine_prefix=None):
    """Convert a host path for use inside an embedded Wine argument."""
    path = os.path.abspath(path)
    if sys.platform == "win32":
        return path

    winepath = os.environ.get("MCCHINA_WINEPATH") or shutil.which("winepath")
    if winepath:
        env = os.environ.copy()
        if wine_prefix:
            env["WINEPREFIX"] = wine_prefix
        env.setdefault("WINEDEBUG", "-all")
        try:
            output = subprocess.check_output(
                [winepath, "-w", path], env=env, stderr=subprocess.DEVNULL
            )
            return output.decode("utf-8").strip()
        except (OSError, subprocess.CalledProcessError):
            pass
    return "Z:" + path.replace("/", "\\")


def _find_linux_engine_dir(project_root=None):
    from config import LINUX_GAME_DIR

    game_dir = os.environ.get("MCCHINA_ENGINE_DIR") or LINUX_GAME_DIR
    if not game_dir:
        return None
    game_dir = os.path.abspath(os.path.expanduser(game_dir))
    exe = os.path.join(game_dir, "Minecraft.Windows.exe")
    return game_dir if os.path.isfile(exe) else None


def get_mcs_download_path():
    if sys.platform != 'win32':
        return None
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Netease\MCStudio") as key:
            path, _ = winreg.QueryValueEx(key, "DownloadPath")
            return path
    except Exception:
        return None


def get_mcs_install_path():
    if sys.platform != 'win32':
        return None
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Netease\MCStudio") as key:
            path, _ = winreg.QueryValueEx(key, "InstallPath")
            return path
    except Exception:
        pass
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Netease\MCStudio") as key:
            path, _ = winreg.QueryValueEx(key, "InstallPath")
            return path
    except Exception:
        return None


def get_latest_engine_dir(project_root=None):
    if sys.platform != 'win32':
        return _find_linux_engine_dir(project_root)
    download_path = get_mcs_download_path()
    if not download_path:
        return None
    engine_root = os.path.join(download_path, "game", "MinecraftPE_Netease")
    if not os.path.isdir(engine_root):
        return None
    dirs = [d for d in os.listdir(engine_root)
            if os.path.isdir(os.path.join(engine_root, d)) and not d.startswith("PCLauncher")]
    if not dirs:
        return None
    try:
        from packaging import version
        dirs.sort(key=lambda x: version.parse(x), reverse=True)
    except ImportError:
        dirs.sort(reverse=True)
    return os.path.join(engine_root, dirs[0])


def get_minecraft_exe(project_root=None):
    engine_dir = get_latest_engine_dir(project_root)
    if not engine_dir:
        return None
    exe = os.path.join(engine_dir, "Minecraft.Windows.exe")
    return exe if os.path.isfile(exe) else None


def get_editor_exe():
    download_path = get_mcs_download_path()
    if not download_path:
        return None
    exe = os.path.join(download_path, "MCX64Editor", "MC_Editor.exe")
    return exe if os.path.isfile(exe) else None


def get_safaia_exe():
    install_path = get_mcs_install_path()
    if not install_path:
        return None
    exe = os.path.join(install_path, "safaia", "safaia_server.exe")
    return exe if os.path.isfile(exe) else None


def _discover_pack_dirs(project_root):
    beh_dir = res_dir = None
    for item in os.listdir(project_root):
        lower = item.lower()
        if lower.startswith("behavior_pack") or lower.startswith("behaviorpack"):
            beh_dir = item
        elif lower.startswith("resource_pack") or lower.startswith("resourcepack"):
            res_dir = item
    return beh_dir or "behavior_pack", res_dir or "resource_pack"


def _wine_appdata(wine_prefix):
    users_root = os.path.join(wine_prefix, "drive_c", "users")
    preferred = os.environ.get("USER") or os.environ.get("LOGNAME")
    if preferred and os.path.isdir(os.path.join(users_root, preferred)):
        user_name = preferred
    else:
        users = []
        if os.path.isdir(users_root):
            users = [name for name in os.listdir(users_root)
                     if name.lower() not in ("public", "default")
                     and os.path.isdir(os.path.join(users_root, name))]
        if not users:
            raise RuntimeError("No Wine user directory found under %s" % users_root)
        user_name = sorted(users)[0]
    return os.path.join(users_root, user_name, "AppData", "Roaming")


def ensure_pack_links(project_root, wine_prefix=None):
    """Expose the addon's behavior/resource packs to the game data folder."""
    beh_dir, res_dir = _discover_pack_dirs(project_root)

    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA", "")
    else:
        wine_prefix = wine_prefix or get_wine_prefix(project_root)
        if not wine_prefix:
            raise RuntimeError(
                "Wine prefix not found; set MCCHINA_WINEPREFIX or WINEPREFIX"
            )
        appdata = _wine_appdata(wine_prefix)

    netease_root = os.path.join(appdata, "MinecraftPE_Netease", "games", "com.netease")

    def _ensure_link(link_parent, link_name, target):
        if not os.path.isdir(link_parent):
            os.makedirs(link_parent)
        link_path = os.path.join(link_parent, link_name)
        target = os.path.abspath(target)
        if os.path.lexists(link_path):
            if os.path.islink(link_path) and os.path.realpath(link_path) == os.path.realpath(target):
                return
            if os.path.isdir(link_path) and os.path.samefile(link_path, target):
                return
            raise RuntimeError("Pack link already exists with a different target: %s" % link_path)
        if sys.platform == "win32":
            subprocess.check_call(
                ["cmd", "/c", "mklink", "/J", link_path, target],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
        else:
            os.symlink(target, link_path, target_is_directory=True)

    _ensure_link(
        os.path.join(netease_root, "behavior_packs"), beh_dir,
        os.path.join(project_root, beh_dir)
    )
    _ensure_link(
        os.path.join(netease_root, "resource_packs"), res_dir,
        os.path.join(project_root, res_dir)
    )
    return beh_dir, res_dir


def setup_runtime(project_root, wine_prefix=None):
    """Generate a .cppconfig under <project_root>/.runtime and return its path.

    Replicates mcpywrap's gen_runtime_config logic without requiring mcpywrap.
    """
    import json
    import uuid

    # --- Read studio.json ---
    studio_json = os.path.join(project_root, "studio.json")
    if not os.path.isfile(studio_json):
        raise RuntimeError("studio.json not found in %s" % project_root)
    with open(studio_json, "r", encoding="utf-8") as f:
        studio = json.load(f)

    pkg_name = studio.get("NameSpace", "")
    world_name = studio.get("EditName", "World")
    game_type = studio.get("GameType", 1)
    world_type = studio.get("WorldType", 1)
    seed = studio.get("Seed", "")

    # --- Expose packs in the native or Wine AppData tree ---
    beh_link_name, res_link_name = ensure_pack_links(project_root, wine_prefix)

    # --- Engine version + paths ---
    download_path = get_mcs_download_path() or ""
    engine_dir = get_latest_engine_dir(project_root)
    engine_version = os.path.basename(engine_dir) if engine_dir else "0.0.0"
    if sys.platform == "win32":
        skin_path = os.path.join(download_path, "componentcache", "support", "steve", "steve.png")
    else:
        skin_path = os.path.join(engine_dir, "data", "skin_packs", "vanilla", "steve.png")
        skin_path = to_windows_path(skin_path, wine_prefix or get_wine_prefix(project_root))

    # --- Build config ---
    level_id = str(uuid.uuid4())
    data = {
        "version": engine_version,
        "MainComponentId": pkg_name,
        "LocalComponentPathsDict": {},
        "LocalComponentPaths": None,
        "world_info": {
            "level_id": level_id,
            "game_type": game_type,
            "difficulty": 2,
            "permission_level": 1,
            "cheat": True,
            "cheat_info": {
                "pvp": True,
                "show_coordinates": True,
                "always_day": False,
                "daylight_cycle": True,
                "fire_spreads": True,
                "tnt_explodes": True,
                "keep_inventory": False,
                "mob_spawn": True,
                "natural_regeneration": True,
                "mob_loot": True,
                "mob_griefing": True,
                "tile_drops": True,
                "entities_drop_loot": True,
                "weather_cycle": True,
                "command_blocks_enabled": True,
                "random_tick_speed": 1,
                "experimental_holiday": False,
                "experimental_biomes": False,
                "fancy_bubbles": False
            },
            "resource_packs": [res_link_name],
            "behavior_packs": [beh_link_name],
            "name": world_name,
            "world_type": world_type,
            "start_with_map": False,
            "bonus_items": False,
            "seed": seed
        },
        "room_info": {
            "ip": "", "port": 0, "muiltClient": False, "room_name": "",
            "token": "", "room_id": 0, "host_id": 0, "allow_pe": True,
            "max_player": 0, "visibility_mode": 0, "is_pe": False,
            "tag_ids": None, "item_ids": []
        },
        "skin_info": {"skin": skin_path, "slim": False}
    }

    runtime_dir = os.path.join(project_root, ".runtime")
    if not os.path.isdir(runtime_dir):
        os.makedirs(runtime_dir)

    config_path = os.path.join(runtime_dir, str(uuid.uuid4()) + ".cppconfig")
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return config_path


def find_latest_cppconfig(project_root):
    """Return path to the newest .cppconfig under <project_root>/.runtime, or None."""
    import json
    runtime_dir = os.path.join(project_root, ".runtime")
    if not os.path.isdir(runtime_dir):
        return None
    instances = []
    for f in os.listdir(runtime_dir):
        if not f.endswith(".cppconfig"):
            continue
        fpath = os.path.join(runtime_dir, f)
        try:
            with open(fpath, "r", encoding="utf-8") as fp:
                cfg = json.load(fp)
            if cfg.get("world_info", {}).get("level_id"):
                instances.append((os.path.getctime(fpath), fpath))
        except Exception:
            continue
    if not instances:
        return None
    instances.sort(reverse=True)
    return instances[0][1]
