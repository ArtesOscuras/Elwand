import os
import queue
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


class SFTPConnectionThread:
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
        self._sftp = None
        self._cwd = "/"

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
        if self._sftp:
            try:
                self._sftp.close()
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
            _dbg(f"[sftp-shell] connected as {self._user}")
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
            sftp = client.open_sftp()
            self._sftp = sftp
            _dbg("[sftp-shell] sftp session opened")
        except SSHException as e:
            if self._on_error:
                self._on_error(f"SFTP open failed: {e}")
            self._close()
            return

        session = shell_db.add_session(self._host, self._port, 0)
        session["type"] = "SFTP"
        session["cmd_queue"] = self._queue
        self._sid = session["id"]
        from src.gui.views.shell_list import enable_default_agent_access
        enable_default_agent_access(session["id"])

        shell_db.append_output(self._sid, f"Connected to {self._host}:{self._port}\n")
        shell_db.append_output(self._sid, f"Logged in as {self._user}\n")
        shell_db.append_output(self._sid, "Type 'help' for available commands.\n")

        if self._on_connected:
            self._on_connected(self._sid)

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
                shell_db.append_output(self._sid, "Goodbye.\n")
                break

            try:
                output = self._execute(cmd)
                if output:
                    shell_db.append_output(self._sid, output.rstrip("\n") + "\n")
                else:
                    shell_db.append_output(self._sid, "(no output)\n")
            except Exception as e:
                shell_db.append_output(self._sid, f"Error: {e}\n")

        self._close()
        shell_db.append_output(self._sid, "Connection closed.\n")
        shell_db.set_status(self._sid, "disconnected")

    def _execute(self, cmd):
        parts = cmd.split()
        verb = parts[0].lower()
        args = parts[1:]

        if verb == "ls" or verb == "dir":
            path = " ".join(args) if args else self._cwd
            try:
                entries = self._sftp.listdir_attr(path)
                if not entries:
                    return "(empty)"
                lines = []
                for e in entries:
                    perms = "d" if e.st_mode is not None and e.st_mode & 0o40000 else "-"
                    if e.st_mode is not None:
                        perms += "rwx" if e.st_mode & 0o400 else "r--"
                        perms += "rwx" if e.st_mode & 0o200 else "r--"
                        perms += "rwx" if e.st_mode & 0o100 else "r--"
                    else:
                        perms += "r--" * 3
                    name = e.filename
                    lines.append(f"{perms} {name}")
                return "\n".join(lines)
            except Exception as e:
                return f"Error: {e}"

        elif verb == "cd":
            if not args:
                return "Usage: cd <directory>"
            path = " ".join(args)
            try:
                self._sftp.chdir(path)
                self._cwd = self._sftp.getcwd() or self._cwd
                return f"Directory changed to {self._cwd}"
            except Exception as e:
                return f"Error: {e}"

        elif verb == "pwd":
            try:
                return self._sftp.getcwd() or self._cwd
            except Exception as e:
                return f"Error: {e}"

        elif verb == "get":
            if not args:
                return "Usage: get <remote_file> [local_name]"
            remote = args[0]
            local = args[1] if len(args) > 1 else os.path.basename(remote)
            try:
                self._sftp.get(remote, local)
                return f"Downloaded {remote} -> {local}"
            except Exception as e:
                return f"Download failed: {e}"

        elif verb == "put":
            if not args:
                return "Usage: put <local_file> [remote_name]"
            local = args[0]
            remote = args[1] if len(args) > 1 else os.path.basename(local)
            if not os.path.isfile(local):
                return f"Local file not found: {local}"
            try:
                self._sftp.put(local, remote)
                return f"Uploaded {local} -> {remote}"
            except Exception as e:
                return f"Upload failed: {e}"

        elif verb == "delete" or verb == "del":
            if not args:
                return "Usage: delete <remote_file>"
            try:
                self._sftp.remove(args[0])
                return f"Deleted {args[0]}"
            except Exception as e:
                return f"Error: {e}"

        elif verb == "mkdir":
            if not args:
                return "Usage: mkdir <directory>"
            try:
                self._sftp.mkdir(" ".join(args))
                return "Directory created"
            except Exception as e:
                return f"Error: {e}"

        elif verb == "rmdir":
            if not args:
                return "Usage: rmdir <directory>"
            try:
                self._sftp.rmdir(" ".join(args))
                return "Directory removed"
            except Exception as e:
                return f"Error: {e}"

        elif verb == "rename":
            if len(args) < 2:
                return "Usage: rename <old_name> <new_name>"
            try:
                self._sftp.rename(args[0], args[1])
                return f"Renamed {args[0]} -> {args[1]}"
            except Exception as e:
                return f"Error: {e}"

        elif verb == "chmod":
            if len(args) < 2:
                return "Usage: chmod <mode> <file>"
            try:
                mode = int(args[0], 8)
                self._sftp.chmod(args[1], mode)
                return "Permissions changed"
            except Exception as e:
                return f"Error: {e}"

        elif verb == "help":
            return ("Available commands:\n"
                    "  ls/dir     List remote directory\n"
                    "  cd         Change remote directory\n"
                    "  pwd        Print working directory\n"
                    "  get        Download file\n"
                    "  put        Upload file\n"
                    "  delete     Delete remote file\n"
                    "  mkdir      Create remote directory\n"
                    "  rmdir      Remove remote directory\n"
                    "  rename     Rename remote file\n"
                    "  chmod      Change permissions\n"
                    "  quit/exit  Close connection")

        else:
            return f"Unknown command: {verb}"
