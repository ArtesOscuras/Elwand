"""Find binaries using 3 levels: PATH, shell rc alias, interactive shell."""
import os
import re
import shutil
import subprocess


def _real_home():
    """Home of the invoking user even when running under sudo.

    `sudo` may set HOME to the target user's home (e.g. /root) and a PATH that
    does not include the user's tool directories, so the shell rc holding the
    alias/PATH is not found. SUDO_USER lets us read the real user's rc.
    """
    sudo_user = os.environ.get("SUDO_USER")
    if sudo_user and os.geteuid() == 0:
        try:
            import pwd
            return pwd.getpwnam(sudo_user).pw_dir
        except Exception:
            pass
    return os.path.expanduser("~")


def resolve(name):
    if not name:
        return None

    found = shutil.which(name)
    if found:
        return found

    found = _parse_rc_for_binary(name)
    if found:
        return found

    found = _find_via_interactive_shell(name)
    if found:
        return found

    return None


def _shell_rc_file():
    shell = os.environ.get("SHELL", "")
    home = _real_home()
    candidates = []
    if "zsh" in shell:
        candidates = [os.path.join(home, ".zshrc")]
    elif "bash" in shell:
        candidates = [os.path.join(home, ".bashrc"), os.path.join(home, ".bash_profile")]
    candidates.append(os.path.join(home, ".zshrc"))
    candidates.append(os.path.join(home, ".bashrc"))
    for c in candidates:
        if os.path.isfile(c) and os.access(c, os.R_OK):
            return c
    return None


def _parse_rc_for_binary(name):
    rc_file = _shell_rc_file()
    if not rc_file:
        return None

    try:
        with open(rc_file) as f:
            content = f.read()
    except (OSError, UnicodeDecodeError):
        return None

    for pattern in [
        rf"alias\s+{re.escape(name)}\s*=\s*'([^']+)'",
        rf'alias\s+{re.escape(name)}\s*=\s*"([^"]+)"',
    ]:
        m = re.search(pattern, content)
        if m:
            path = m.group(1).strip()
            if os.path.isfile(path) and os.access(path, os.X_OK):
                return path

    for pattern in [
        r'export\s+PATH\s*=\s*"([^"]+)"',
        r"export\s+PATH\s*=\s*'([^']+)'",
        r'export\s+PATH\s*=\s*([^\n]+)',
    ]:
        for m in re.finditer(pattern, content):
            extra_paths = m.group(1).strip()
            for p in extra_paths.split(":"):
                p = os.path.expandvars(p.strip())
                candidate = os.path.join(p, name)
                if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                    return candidate

    return None


def _find_via_interactive_shell(name):
    shell = os.environ.get("SHELL", "/bin/sh")
    try:
        r = subprocess.run(
            [shell, "-ic", f"command -v {name}"],
            capture_output=True, timeout=5, text=True,
        )
        out = r.stdout.strip()
        if out and os.path.isfile(out):
            return out
    except (FileNotFoundError, PermissionError, subprocess.TimeoutExpired, OSError):
        pass
    return None
