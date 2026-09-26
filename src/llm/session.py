import json
import os
import threading
from src.elwand_paths import session_file as _session_file

_lock = threading.Lock()


def _get(obj, key, default=None):
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def serialize_messages(messages):
    out = []
    for m in messages:
        role = _get(m, "role")
        content = _get(m, "content")
        d = {}
        if role is not None:
            d["role"] = role
        if content is not None:
            d["content"] = content
        tcs = _get(m, "tool_calls")
        if tcs:
            d["tool_calls"] = []
            for tc in tcs:
                fn = _get(tc, "function")
                d["tool_calls"].append({
                    "id": _get(tc, "id"),
                    "type": _get(tc, "type", "function"),
                    "function": {
                        "name": _get(fn, "name"),
                        "arguments": _get(fn, "arguments", "{}"),
                    },
                })
        tcid = _get(m, "tool_call_id")
        if tcid is not None:
            d["tool_call_id"] = tcid
        for key in ("_is_context", "_is_compaction", "_recent"):
            v = _get(m, key)
            if v is not None:
                d[key] = v
        out.append(d)
    return out


def save(messages, mode=None, context_injected=False, total_api_tokens=0, console_segments=None, session_id=None):
    import datetime as _datetime
    data = {
        "messages": serialize_messages(messages),
        "mode": mode,
        "context_injected": bool(context_injected),
        "total_api_tokens": total_api_tokens,
        "console_segments": console_segments,
        "llm_session_id": session_id,
        "updated": _datetime.datetime.now().isoformat(),
    }
    path = _session_file()
    try:
        os.makedirs(str(path.parent), exist_ok=True)
        tmp = str(path) + ".tmp"
        with _lock, open(tmp, "w") as f:
            json.dump(data, f, ensure_ascii=False, default=str)
        os.replace(tmp, str(path))
    except (PermissionError, OSError):
        pass


def load():
    path = _session_file()
    if not path.exists():
        return None
    try:
        with _lock, open(str(path)) as f:
            data = json.load(f)
        if isinstance(data, dict) and isinstance(data.get("messages"), list):
            return data
    except (json.JSONDecodeError, OSError):
        pass
    return None


def clear():
    path = _session_file()
    try:
        with _lock:
            if path.exists():
                path.unlink()
    except OSError:
        pass
