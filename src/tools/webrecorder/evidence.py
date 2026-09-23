import json
import os
from datetime import datetime
from src.elwand_paths import evidence_dir as _evidence_dir


def _ensure_dir(target_dir):
    os.makedirs(target_dir, exist_ok=True)


def save_session_meta(target_dir, target, browser):
    _ensure_dir(target_dir)
    meta = {
        "target": target,
        "browser": browser,
        "started_at": datetime.now().isoformat(),
        "request_count": 0,
    }
    with open(os.path.join(target_dir, "session.json"), "w") as f:
        json.dump(meta, f, indent=2)
    return meta


def update_session_count(target_dir, count):
    path = os.path.join(target_dir, "session.json")
    if os.path.isfile(path):
        with open(path) as f:
            meta = json.load(f)
        meta["request_count"] = count
        meta["ended_at"] = datetime.now().isoformat()
        with open(path, "w") as f:
            json.dump(meta, f, indent=2)


def save_request(target_dir, index, req_data, resp_data, body):
    _ensure_dir(target_dir)
    method = req_data.get("method", "GET")
    path_part = req_data.get("url", "").rstrip("/").rsplit("/", 1)[-1] or "root"
    safe_path = "".join(c if c.isalnum() or c in "._-" else "_" for c in path_part)[:40]
    name = f"{index:04d}_{method}_{safe_path}"

    req_dir = os.path.join(target_dir, name)
    _ensure_dir(req_dir)

    with open(os.path.join(req_dir, "request.json"), "w") as f:
        json.dump(req_data, f, indent=2)
    with open(os.path.join(req_dir, "response.json"), "w") as f:
        json.dump(resp_data, f, indent=2)

    if body:
        body_path = os.path.join(req_dir, "body.html")
        try:
            with open(body_path, "wb") as f:
                f.write(body if isinstance(body, bytes) else body.encode(errors="replace"))
        except Exception:
            pass


def sanitize_name(target):
    return "".join(c if c.isalnum() or c in "._-" else "_" for c in target)


def target_dir(target):
    return os.path.join(str(_evidence_dir()), sanitize_name(target))
