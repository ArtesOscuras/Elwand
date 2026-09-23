import os
import socket
import threading
import time as _time
from datetime import datetime
from src.elwand_paths import logs_dir as _logs_dir


# --- debug logging -----------------------------------------------------------
_DBG_FILE = os.path.join(_logs_dir(), "debugging_logs")
_DBG_LOCK = threading.Lock()


def _dbg(msg):
    line = f"{_time.strftime('%H:%M:%S')}  {msg}\n"
    try:
        with _DBG_LOCK:
            os.makedirs(os.path.dirname(_DBG_FILE), exist_ok=True)
            with open(_DBG_FILE, "a") as f:
                f.write(line)
    except (PermissionError, OSError):
        pass
# ---------------------------------------------------------------------------

_id_counter = 0
_lock = threading.Lock()
_sessions = {}


def _next_id():
    global _id_counter
    _id_counter += 1
    return _id_counter


def add_session(ip, port, listener_port):
    sid = _next_id()
    session = {
        "id": sid,
        "ip": ip,
        "source_port": port,
        "listener_port": listener_port,
        "connected_at": datetime.now(),
        "last_active": datetime.now(),
        "status": "connected",
        "type": "Revershell",
        "buffer": [],
        "socket": None,
        "active": True,
    }
    with _lock:
        _sessions[sid] = session
    _dbg(f"[shell-db] session #{sid} added ({ip}:{port})")
    return session


def set_socket(sid, sock):
    s = get_session(sid)
    if s:
        s["socket"] = sock


def set_status(sid, status):
    s = get_session(sid)
    if s:
        _dbg(f"[shell-db] session #{sid} status -> {status}")
        s["status"] = status


def set_os(sid, shell_os):
    s = get_session(sid)
    if s:
        s["os"] = shell_os
        if shell_os == "windows":
            s["type"] = "Revershell (windows)"
        else:
            s["type"] = "Revershell (unix)"


def append_output(sid, data):
    s = get_session(sid)
    if s:
        s["last_active"] = datetime.now()
        if isinstance(data, bytes):
            try:
                data = data.decode(errors="replace")
            except Exception:
                data = repr(data)
        data = data.replace("\r\n", "\n").replace("\r", "\n")
        s["buffer"].append(data)
        ab = s.get("_agent_buffer")
        if ab is not None:
            ab.append(data)
        _dbg(f"[shell-db] append_output #{sid}: {len(data)} chars")


def drain_output(sid):
    s = get_session(sid)
    if not s:
        return ""
    buf = s["buffer"]
    if not buf:
        return ""
    result = "".join(buf)
    s["buffer"] = []
    return result


def enable_agent_buffer(sid):
    s = get_session(sid)
    if s and "_agent_buffer" not in s:
        s["_agent_buffer"] = []


def drain_agent_output(sid):
    s = get_session(sid)
    if not s:
        return ""
    buf = s.get("_agent_buffer")
    if buf is None:
        return ""
    if not buf:
        return ""
    result = "".join(buf)
    s["_agent_buffer"] = []
    return result


def touch_agent(sid, cmd=None):
    s = get_session(sid)
    if s:
        s["_agent_touch"] = True
        if cmd:
            s["_agent_cmd"] = cmd


def pop_agent_touch(sid):
    s = get_session(sid)
    if s and s.pop("_agent_touch", None):
        cmd = s.pop("_agent_cmd", None)
        return cmd if cmd else True
    return False


def get_session(sid):
    with _lock:
        return _sessions.get(sid)


def get_all():
    with _lock:
        return sorted(_sessions.values(), key=lambda s: s["id"], reverse=False)


def get_count():
    with _lock:
        return len(_sessions)


def set_process(sid, proc):
    s = get_session(sid)
    if s:
        s["process"] = proc


def close_session(sid):
    _dbg(f"[shell-db] closing session #{sid}")
    s = get_session(sid)
    if s:
        s["active"] = False
        q = s.get("cmd_queue")
        if q:
            try:
                q.put(None)
                _dbg(f"[shell-db] session #{sid} cmd_queue signalled")
            except Exception:
                pass
        pty_fd = s.get("pty_fd")
        if pty_fd:
            try:
                os.close(pty_fd)
                _dbg(f"[shell-db] session #{sid} pty_fd closed")
            except Exception:
                pass
        sock = s.get("socket")
        if sock:
            try:
                sock.shutdown(socket.SHUT_RDWR)
                _dbg(f"[shell-db] session #{sid} socket shutdown")
            except Exception:
                pass
            try:
                sock.close()
                _dbg(f"[shell-db] session #{sid} socket closed")
            except Exception:
                pass
        proc = s.get("process")
        if proc:
            try:
                proc.terminate()
                _dbg(f"[shell-db] session #{sid} process terminated")
            except Exception:
                pass
        with _lock:
            _sessions.pop(sid, None)
        _dbg(f"[shell-db] session #{sid} removed")
