import os
import shutil
import tarfile
import tempfile
import urllib.request

_URLS = {
    "rockyou": (
        "https://github.com/ArtesOscuras/Lists"
        "/releases/download/list/rockyou.tar.gz"
    ),
    "usernames": (
        "https://github.com/ArtesOscuras/Lists"
        "/releases/download/list/usernames.tar.gz"
    ),
}

_TAR_NAMES = {
    "rockyou": {"rockyou", "rockyou.txt"},
    "usernames": {"usernames", "usernames.txt"},
}


def _path(name):
    from src.elwand_paths import lst_dir
    return lst_dir() / f"{name}.txt"


def is_installed(name):
    p = _path(name)
    return p.is_file() and p.stat().st_size > 1024


def any_missing():
    return [n for n in _URLS if not is_installed(n)]


def download(name, on_progress=None):
    url = _URLS[name]
    valid_names = _TAR_NAMES[name]
    dest = _path(name)
    dest.parent.mkdir(parents=True, exist_ok=True)

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tmp:
            tmp_path = tmp.name

        with urllib.request.urlopen(url) as resp:
            total = int(resp.headers.get("Content-Length", 0))
            downloaded = 0
            with open(tmp_path, "wb") as f:
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if on_progress and total > 0:
                        on_progress(int(downloaded * 100 / total))

        with tarfile.open(tmp_path, "r:gz") as tar:
            for member in tar.getmembers():
                if (os.path.basename(member.name) in valid_names
                        and member.isfile()):
                    f = tar.extractfile(member)
                    if f:
                        with open(dest, "wb") as out:
                            shutil.copyfileobj(f, out)
                    break

        if not is_installed(name):
            raise RuntimeError("Extraction failed or file too small")

    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)
