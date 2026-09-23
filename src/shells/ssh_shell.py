import os
import queue
import re
import threading
import time
from . import shell_db
from src.elwand_paths import logs_dir as _logs_dir

_DBG_FILE = os.path.join(_logs_dir(), "debugging_logs")
_DBG_LOCK = threading.Lock()


def _dbg(msg):
    line = f"{time.strftime('%H:%M:%S')}  {msg}\n"
    try:
        with _DBG_LOCK:
            os.makedirs(os.path.dirname(_DBG_FILE), exist_ok=True)
            with open(_DBG_FILE, "a") as f:
                f.write(line)
    except (PermissionError, OSError):
        pass


class SSHConnectionThread:
    def __init__(self, host, port, user, password, on_connected=None, on_error=None):
        self._host = host
        self._port = port or 22
        self._user = user
        self._password = password
        self._on_connected = on_connected
        self._on_error = on_error
        self._sid = None
        self._queue = queue.Queue()
        self._running = True
        self._client = None
        self._channel = None

    @property
    def queue(self):
        return self._queue

    def start(self):
        t = threading.Thread(target=self._run, daemon=True)
        t.start()

    def stop(self):
        self._running = False
        self._queue.put(None)
        self._close()

    def _close(self):
        if self._channel:
            try:
                self._channel.close()
            except Exception:
                pass
        if self._client:
            try:
                self._client.close()
            except Exception:
                pass

    def _run(self):
        import paramiko
        from paramiko import SSHClient, AutoAddPolicy, AuthenticationException, SSHException

        client = SSHClient()
        client.set_missing_host_key_policy(AutoAddPolicy())
        self._client = client

        try:
            client.connect(
                self._host,
                port=self._port,
                username=self._user,
                password=self._password,
                timeout=10,
                allow_agent=False,
                look_for_keys=False,
            )
            _dbg(f"[ssh-shell] connected as {self._user}")
        except AuthenticationException as e:
            if self._on_error:
                self._on_error(f"Authentication failed: {e}")
            return
        except SSHException as e:
            if self._on_error:
                self._on_error(f"SSH error: {e}")
            return
        except Exception as e:
            if self._on_error:
                self._on_error(f"Connection failed: {e}")
            return

        try:
            channel = client.invoke_shell(term="xterm", width=120, height=50)
            self._channel = channel
            channel.settimeout(0.5)
            _dbg("[ssh-shell] shell opened")
        except SSHException as e:
            if self._on_error:
                self._on_error(f"Failed to open shell: {e}")
            self._close()
            return

        session = shell_db.add_session(self._host, self._port, 0)
        self._sid = session["id"]
        from src.gui.views.shell_list import enable_default_agent_access
        enable_default_agent_access(session["id"])
        session["type"] = "SSH"
        session["cmd_queue"] = self._queue
        session["ssh_channel"] = channel

        shell_db.append_output(self._sid, f"Connected to {self._host}:{self._port}\n")
        shell_db.append_output(self._sid, f"Logged in as {self._user}\n")

        reader = threading.Thread(
            target=self._read_channel,
            args=(channel,),
            daemon=True,
        )
        reader.start()

        if self._on_connected:
            self._on_connected(self._sid)

        time.sleep(1)

        while self._running:
            try:
                raw = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue
            if raw is None:
                break

            cmd = raw.strip()
            if not cmd:
                continue

            if cmd == "quit" or cmd == "exit" or cmd == "bye":
                shell_db.append_output(self._sid, "logout\n")
                break

            _dbg(f"[ssh-shell #{self._sid}] sending: {repr(cmd)}")
            try:
                channel.send(cmd + "\n")
                _dbg(f"[ssh-shell #{self._sid}] sent OK ({len(cmd)} chars)")
            except SSHException as e:
                shell_db.append_output(self._sid, f"Send error: {e}\n")
                break

        self._close()
        shell_db.append_output(self._sid, "Connection closed.\n")
        shell_db.set_status(self._sid, "disconnected")

    def _read_channel(self, channel):
        sid = self._sid
        first = True
        try:
            while self._running:
                if channel.recv_ready():
                    data = channel.recv(4096)
                    if not data:
                        break
                    if first:
                        _dbg(f"[ssh-shell #{sid}] first recv: {data[:200]}")
                        first = False
                    text = data.decode(errors="replace")
                    text = text.replace("\r\n", "\n").replace("\r", "\n")
                    if text:
                        shell_db.append_output(sid, text)
                elif channel.closed:
                    break
                else:
                    time.sleep(0.05)
        except Exception:
            pass
        finally:
            _dbg(f"[ssh-shell #{sid}] reader stopped")
