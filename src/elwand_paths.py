import os
import shutil
from pathlib import Path
from importlib.resources import files

_PKG = files("src")

_DATA_HOME_NAME = "elwand"
_LEGACY_DATA_HOME_NAME = "hsf"
_migrated = False

def fonts_dir() -> Path:
    return _PKG / "fonts"

def icons_dir() -> Path:
    return _PKG / "icons"

def hashcat_db() -> Path:
    return _PKG / "data" / "hashcat.dbs"

def _compute_base_home() -> Path:
    sudo_user = os.environ.get("SUDO_USER")
    if sudo_user and os.geteuid() == 0:
        import pwd
        try:
            return Path(pwd.getpwnam(sudo_user).pw_dir)
        except Exception:
            pass
    return Path.home()


def _migrate_legacy_data_home(new_home: Path) -> None:
    global _migrated
    if _migrated:
        return
    _migrated = True
    old_home = new_home.parent / _LEGACY_DATA_HOME_NAME
    if old_home == new_home:
        return
    try:
        if old_home.is_dir() and not new_home.exists():
            new_home.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(old_home), str(new_home))
    except (OSError, PermissionError):
        pass


def _get_data_home() -> Path:
    override = os.environ.get("ELWAND_HOME") or os.environ.get("HSF_HOME")
    if override:
        return Path(override)
    new_home = _compute_base_home() / ".local" / "share" / _DATA_HOME_NAME
    _migrate_legacy_data_home(new_home)
    return new_home


def chown_to_real_user(path):
    if os.geteuid() != 0:
        return
    sudo_uid = os.environ.get("SUDO_UID")
    sudo_gid = os.environ.get("SUDO_GID")
    if not sudo_uid or not sudo_gid:
        return
    try:
        os.chown(str(path), int(sudo_uid), int(sudo_gid))
    except (OSError, PermissionError):
        pass

def databases_dir() -> Path:
    p = _get_data_home() / "databases"
    p.mkdir(parents=True, exist_ok=True)
    return p

def credentials_dir() -> Path:
    p = _get_data_home() / "credentials"
    p.mkdir(parents=True, exist_ok=True)
    return p

def evidence_dir() -> Path:
    p = _get_data_home() / "evidence"
    p.mkdir(parents=True, exist_ok=True)
    return p

def chrome_profile_dir() -> Path:
    p = _get_data_home() / "chrome_profile"
    p.mkdir(parents=True, exist_ok=True)
    return p

def antibot_profile_dir() -> Path:
    p = _get_data_home() / "antibot_profile"
    p.mkdir(parents=True, exist_ok=True)
    return p

def lst_dir() -> Path:
    p = _get_data_home() / "lst"
    p.mkdir(parents=True, exist_ok=True)
    if not any(p.iterdir()):
        src = _PKG / "lst"
        if src.is_dir():
            for f in src.iterdir():
                if f.is_file():
                    _dst = p / f.name
                    if not _dst.exists():
                        _dst.write_bytes(f.read_bytes())
    return p

def rules_dir() -> Path:
    p = _get_data_home() / "rules"
    p.mkdir(parents=True, exist_ok=True)
    if not any(p.iterdir()):
        src = _PKG / "rules"
        if src.is_dir():
            for f in src.iterdir():
                if f.is_file():
                    _dst = p / f.name
                    if not _dst.exists():
                        _dst.write_bytes(f.read_bytes())
    return p

def pocs_dir() -> Path:
    p = _get_data_home() / "pocs"
    p.mkdir(parents=True, exist_ok=True)
    return p

def reports_dir() -> Path:
    p = _get_data_home() / "reports"
    p.mkdir(parents=True, exist_ok=True)
    return p

def cache_dir() -> Path:
    p = _get_data_home() / "cache"
    p.mkdir(parents=True, exist_ok=True)
    return p

def handshakes_dir() -> Path:
    p = _get_data_home() / "handshakes"
    p.mkdir(parents=True, exist_ok=True)
    return p

def models_catalog_file() -> Path:
    return databases_dir() / "models_catalog.json"

def settings_file() -> Path:
    p = _get_data_home() / "settings.json"
    return p

def session_file() -> Path:
    return _get_data_home() / "session.json"

def logs_dir() -> Path:
    return _PKG / "logs"

def runtime_logs_dir() -> Path:
    p = _get_data_home() / "logs"
    p.mkdir(parents=True, exist_ok=True)
    return p
