import os
import shutil
from pathlib import Path
from importlib.resources import files

_PKG = files("src")

_DATA_HOME_NAME = "elwand"
_LEGACY_DATA_HOME_NAME = "hsf"
_migrated = False
_rt2800_synced = False

# Active work-session directory (set by src.sessions.bootstrap()/set_active()).
# When unset (e.g. standalone scripts) it falls back to the global home so the
# app still works, though data then lives outside sessions/<id>/.
_SESSION_DIR = None


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


def global_home() -> Path:
    """Root shared by every workspace session (settings, providers, assets)."""
    p = _get_data_home()
    p.mkdir(parents=True, exist_ok=True)
    return p


# --- active work session ----------------------------------------------------

def set_session_dir(path):
    global _SESSION_DIR
    _SESSION_DIR = Path(path) if path else None


def active_session_dir() -> Path:
    if _SESSION_DIR is not None:
        return _SESSION_DIR
    return _get_data_home()


def _session_path(sub) -> Path:
    p = active_session_dir() / sub
    p.mkdir(parents=True, exist_ok=True)
    return p


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


# --- session-scoped operational data ---------------------------------------

def databases_dir() -> Path:
    return _session_path("databases")

def credentials_dir() -> Path:
    return _session_path("credentials")

def evidence_dir() -> Path:
    return _session_path("evidence")

def handshakes_dir() -> Path:
    return _session_path("handshakes")

def pocs_dir() -> Path:
    return _session_path("pocs")

def reports_dir() -> Path:
    return _session_path("reports")

def cache_dir() -> Path:
    return _session_path("cache")

def runtime_logs_dir() -> Path:
    return _session_path("logs")

def session_file() -> Path:
    p = active_session_dir()
    p.mkdir(parents=True, exist_ok=True)
    return p / "session.json"


# --- global (shared across sessions) ---------------------------------------

def chrome_profile_dir() -> Path:
    p = global_home() / "chrome_profile"
    p.mkdir(parents=True, exist_ok=True)
    return p

def antibot_profile_dir() -> Path:
    p = global_home() / "antibot_profile"
    p.mkdir(parents=True, exist_ok=True)
    return p

def settings_file() -> Path:
    return global_home() / "settings.json"

def models_catalog_file() -> Path:
    return global_home() / "models_catalog.json"


# --- dictionaries / rules: stock (bundled) vs session (user-created) --------

def stock_lst_dir() -> Path:
    return _PKG / "lst"

def stock_rules_dir() -> Path:
    return _PKG / "rules"

def global_lst_dir() -> Path:
    p = global_home() / "lst"
    p.mkdir(parents=True, exist_ok=True)
    return p

def global_rules_dir() -> Path:
    p = global_home() / "rules"
    p.mkdir(parents=True, exist_ok=True)
    return p

def lst_dir() -> Path:
    """Writable per-session dictionary directory (user/DICMA output)."""
    return _session_path("lst")

def rules_dir() -> Path:
    """Writable per-session rules directory (user/DICMA output)."""
    return _session_path("rules")


def _resolve_in(name, session_dir, shared_dirs, stock_dir):
    if not name:
        return None
    p = Path(name)
    if p.is_absolute() and p.is_file():
        return p
    fname = os.path.basename(name)
    if os.sep in name or (os.altsep and os.altsep in name):
        return None
    for d in (session_dir, *shared_dirs, stock_dir):
        candidate = d / fname
        if candidate.is_file():
            return candidate
    return None


def resolve_lst(name):
    """Return the file for a dictionary name: session, shared, then stock."""
    return _resolve_in(name, lst_dir(), (global_lst_dir(),), stock_lst_dir())


def resolve_rules(name):
    """Return the file for a rules name: session, shared, then stock."""
    return _resolve_in(name, rules_dir(), (global_rules_dir(),), stock_rules_dir())


def _merge(stock_dir, shared_dirs, sess_dir):
    items = {}
    for d in (stock_dir, *shared_dirs):
        try:
            for f in d.iterdir():
                if f.is_file():
                    items[f.name] = "stock"
        except OSError:
            pass
    try:
        for f in sess_dir.iterdir():
            if f.is_file():
                items[f.name] = "session"
    except OSError:
        pass
    return dict(sorted(items.items(), key=lambda kv: kv[0].lower()))


def list_lst():
    """Map name -> 'stock' | 'session' (session overrides shared/stock)."""
    return _merge(stock_lst_dir(), (global_lst_dir(),), lst_dir())


def list_rules():
    return _merge(stock_rules_dir(), (global_rules_dir(),), rules_dir())


def browse_lst_dir() -> Path:
    """Directory to start a file chooser in: session, shared, else stock."""
    for d in (lst_dir(), global_lst_dir()):
        try:
            if any(f.is_file() for f in d.iterdir()):
                return d
        except OSError:
            pass
    return stock_lst_dir()


def browse_rules_dir() -> Path:
    for d in (rules_dir(), global_rules_dir()):
        try:
            if any(f.is_file() for f in d.iterdir()):
                return d
        except OSError:
            pass
    return stock_rules_dir()


def delete_lst(name):
    """Delete a session dictionary; stock files are never removed."""
    p = lst_dir() / os.path.basename(name)
    try:
        if p.is_file():
            p.unlink()
            return True
    except OSError:
        pass
    return False


def delete_rule(name):
    p = rules_dir() / os.path.basename(name)
    try:
        if p.is_file():
            p.unlink()
            return True
    except OSError:
        pass
    return False


def rt2800_dir() -> Path:
    """Runtime directory for the bundled RT2800 USB userspace driver."""
    global _rt2800_synced
    p = global_home() / "rt2800"
    p.mkdir(parents=True, exist_ok=True)
    if not _rt2800_synced:
        _rt2800_synced = True
        src = _PKG / "data" / "rt2800"
        try:
            files = list(src.iterdir()) if src.is_dir() else []
        except (OSError, TypeError):
            files = []
        for f in files:
            if not f.is_file():
                continue
            dst = p / f.name
            try:
                dst.write_bytes(f.read_bytes())
                if f.name == "rt2800d":
                    dst.chmod(0o755)
            except (OSError, PermissionError):
                pass
    return p


def rt2800_bin() -> Path:
    override = os.environ.get("ELWAND_RT2800_BIN")
    if override:
        return Path(override)
    return rt2800_dir() / "rt2800d"


def rt2800_firmware_dir() -> Path:
    override = os.environ.get("ELWAND_RT2800_FW_DIR")
    if override:
        return Path(override)
    return rt2800_dir()


def logs_dir() -> Path:
    return _PKG / "logs"
