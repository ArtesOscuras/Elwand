"""Hashcat engine — wraps the hashcat binary for background cracking."""
import json
import os
import re
import shlex
import subprocess
import tempfile
import threading
import time

from src.resolve_binary import resolve
from src import process_registry


_PROGRESS_RE = re.compile(r"Progress\.+:\s+(\d+)/(\d+)")
_RECOVERED_RE = re.compile(r"Recovered\.+:\s+(\d+)/(\d+).*?Digests")
_REJECTED_RE = re.compile(r"Rejected\.+:\s+(\d+)/")
# hashcat's interactive keyboard prompt (printed even with pipes; CR-delimited)
_PROMPT_RE = re.compile(r"\[s\]tatus\s+\[p\]ause")

_STATUS_NAMES = {
    0: "init",
    1: "autotune",
    2: "selftest",
    3: "running",
    4: "paused",
    5: "exhausted",
    6: "cracked",
    7: "aborted",
    8: "quit",
    9: "bypass",
    10: "aborted",
    11: "aborted",
    13: "error",
    14: "aborted",
    16: "autodetect",
}

_STATUS_JSON_SUPPORTED = None

_PHASE_MARKERS = [
    ("Initializing device kernels and memory", "Preparing kernels\u2026"),
    ("Initializing backend runtime", "Initializing backend\u2026"),
    ("Autodetecting hash-modes", "Detecting hash mode\u2026"),
    ("Starting self-test", "Running self-test\u2026"),
    ("Starting autotune", "Autotuning\u2026"),
    ("Counting lines in", "Loading wordlist\u2026"),
    ("Sorting hashes", "Preparing hashes\u2026"),
    ("Removing duplicate hashes", "Preparing hashes\u2026"),
    ("Sorting salts", "Preparing hashes\u2026"),
    ("Comparing hashes with potfile", "Checking potfile\u2026"),
]


def _supports_status_json(binary):
    global _STATUS_JSON_SUPPORTED
    if _STATUS_JSON_SUPPORTED is None:
        try:
            r = subprocess.run([binary, "--help"], capture_output=True,
                               text=True, timeout=10)
            _STATUS_JSON_SUPPORTED = "status-json" in (r.stdout + r.stderr)
        except Exception:
            _STATUS_JSON_SUPPORTED = False
    return _STATUS_JSON_SUPPORTED


def build_command(mode, hash_value, wordlist=None, mask=None, custom_charsets=None,
                  rules_file=None, backend=None, binary="hashcat",
                  outfile="<TMP>", status_json=True, slow_candidates=False):
    """Build the hashcat argv for an attack.

    Single source of truth used both to run the attack and to preview the
    command in the GUI. `outfile="<TMP>"` is a placeholder the caller replaces
    with a real temp path (Elwand needs `--outfile` to read cracked hashes).
    """
    cmd = [binary, "-m", str(mode), hash_value]
    if mask:
        cmd += ["-a", "3", mask, "--increment"]
        for key, charset in sorted((custom_charsets or {}).items()):
            if charset:
                cmd += [f"-{key}", charset]
    elif wordlist:
        cmd.append(wordlist)
    if outfile:
        cmd += ["--outfile", outfile, "--outfile-format", "2"]
    cmd += ["--status", "--status-timer=1", "--potfile-disable"]
    if status_json:
        cmd.append("--status-json")
    if backend:
        cmd += ["-D", str(backend)]
    if rules_file:
        cmd += ["-r", rules_file]
    if slow_candidates:
        cmd.append("-S")
    return cmd


def count_lines(path):
    """Count the lines of a file (chunked; safe for large wordlists/rules)."""
    n = 0
    try:
        with open(path, "rb") as f:
            while True:
                chunk = f.read(1 << 20)
                if not chunk:
                    break
                n += chunk.count(b"\n")
    except OSError:
        return 0
    return n


def format_command(cmd):
    """Quoted, shell-style rendering of an argv list (for display)."""
    return " ".join(shlex.quote(str(t)) for t in cmd)


class HashcatEngine:
    def __init__(self, mode=None, hash_value=None, wordlist=None, mask=None,
                 custom_charsets=None, rules_file=None,
                 backend=None, command=None,
                 on_output=None, on_cracked=None, on_done=None,
                 on_progress=None, on_status=None, on_phase=None):
        self._mode = str(mode) if mode is not None else ""
        self._hash_value = hash_value
        self._wordlist = wordlist
        self._mask = mask
        self._custom_charsets = custom_charsets or {}
        self._rules_file = rules_file
        self._backend = backend
        self._command = list(command) if command else None
        self._on_output = on_output
        self._on_cracked = on_cracked
        self._on_done = on_done
        self._on_progress = on_progress
        self._on_status = on_status
        self._on_phase = on_phase
        self._proc = None
        self._stop_flag = threading.Event()
        self._progress_done = 0
        self._progress_total = 0
        self._progress_recovered = 0
        self._progress_rejected = 0
        self._outfile_path = None
        self._outfile_owned = False
        self._outfile_seen = 0
        self._cracked = []
        self._kernel_error = False
        self._saw_status_json = False

    def start(self):
        target = os.path.basename(self._wordlist) if self._wordlist else (self._mask or "hash")
        pid = process_registry.register(
            "Hashcat", detail=f"mode {self._mode}  {target}")

        def _wrap():
            try:
                self._run()
            finally:
                process_registry.finish(pid)

        threading.Thread(target=_wrap, daemon=True).start()

    def stop(self):
        self._stop_flag.set()
        if self._proc:
            try:
                self._proc.terminate()
            except Exception:
                pass

    @staticmethod
    def _kernels_dir(binary):
        return os.path.join(os.path.dirname(os.path.realpath(binary)), "kernels")

    def _clear_unreadable_kernels(self, binary):
        """Drop hashcat kernel-cache files this user cannot read/write.

        hashcat compiles its kernels next to the binary. If a previous run as
        another user (typically root) left them unreadable, the kernel build
        fails with 'Permission denied' and nothing is cracked. They are a
        regenerable cache, so removing them is safe.
        """
        kdir = self._kernels_dir(binary)
        try:
            names = os.listdir(kdir)
        except OSError:
            return
        removed = 0
        for name in names:
            if not name.endswith(".kernel"):
                continue
            path = os.path.join(kdir, name)
            if os.access(path, os.R_OK | os.W_OK):
                continue
            try:
                os.remove(path)
                removed += 1
            except OSError:
                pass
        if removed:
            self._emit(
                f"  [i] Removed {removed} unreadable hashcat kernel cache "
                f"file(s) (they belonged to another user; hashcat will rebuild "
                f"them).\n", "info")

    @staticmethod
    def is_available():
        return resolve("hashcat") is not None

    @staticmethod
    def detect_hardware():
        binary = resolve("hashcat")
        if not binary:
            return {"cpu": True, "gpu": True, "mcu": 0}

        try:
            r = subprocess.run(
                [binary, "-I"],
                capture_output=True, text=True, timeout=10,
            )
            output = r.stdout + r.stderr
            has_cpu = "Type...........: CPU" in output
            has_gpu = "Type...........: GPU" in output
            mcu = 0
            cur_type = ""
            for ln in output.splitlines():
                s = ln.strip()
                if s.startswith("Type"):
                    if "GPU" in s:
                        cur_type = "GPU"
                    elif "CPU" in s:
                        cur_type = "CPU"
                elif s.startswith("Processor(s)") and cur_type == "GPU":
                    m = re.search(r":\s*(\d+)", s)
                    if m:
                        mcu += int(m.group(1))
            return {"cpu": has_cpu, "gpu": has_gpu, "mcu": mcu}
        except (OSError, subprocess.TimeoutExpired):
            return {"cpu": True, "gpu": True, "mcu": 0}

    def _make_outfile(self):
        try:
            fd, path = tempfile.mkstemp(prefix="elwand_hashcat_", suffix=".out")
            os.close(fd)
            os.unlink(path)
            self._outfile_path = path
            self._outfile_owned = True
            return path
        except OSError:
            self._outfile_path = None
            self._outfile_owned = False
            return None

    def _poll_outfile(self):
        if not self._outfile_path:
            return
        try:
            with open(self._outfile_path, "r", errors="replace") as f:
                lines = f.read().splitlines()
        except OSError:
            return
        while self._outfile_seen < len(lines):
            plain = lines[self._outfile_seen]
            self._outfile_seen += 1
            if plain:
                self._cracked.append(plain)
                if self._on_cracked:
                    self._on_cracked(self._hash_value, plain)

    def _cleanup_outfile(self):
        if self._outfile_path and self._outfile_owned:
            try:
                os.unlink(self._outfile_path)
            except OSError:
                pass
        self._outfile_path = None

    def _run(self):
        binary = resolve("hashcat")
        if not binary:
            if self._on_output:
                self._on_output("hashcat binary not found in PATH.\n", "error")
            self._finish([], failed=True)
            return

        self._clear_unreadable_kernels(binary)

        if self._command is not None:
            cmd = list(self._command)
        else:
            cmd = build_command(
                self._mode, self._hash_value, wordlist=self._wordlist,
                mask=self._mask, custom_charsets=self._custom_charsets,
                rules_file=self._rules_file, backend=self._backend,
                binary=binary, outfile="<TMP>",
                status_json=_supports_status_json(binary))

        # Resolve the binary token (keep an explicit, existing path).
        if cmd and not (os.path.isabs(cmd[0]) and os.path.isfile(cmd[0])):
            cmd[0] = binary
        elif not cmd:
            cmd = [binary]

        # Elwand needs --outfile to read cracked hashes: substitute the
        # placeholder, or append the flags if the user removed them.
        if "--outfile" in cmd:
            i = cmd.index("--outfile")
            val = cmd[i + 1] if i + 1 < len(cmd) else ""
            if not val or val in ("<TMP>", "<tmp>"):
                path = self._make_outfile()
                if i + 1 < len(cmd):
                    cmd[i + 1] = path
                    self._outfile_path = path
                else:
                    cmd.append(path)
                    self._outfile_path = path
            else:
                self._outfile_owned = False
                self._outfile_path = val
        else:
            path = self._make_outfile()
            cmd += ["--outfile", path, "--outfile-format", "2"]

        # Ensure live status output.
        if "--status" not in cmd:
            cmd += ["--status", "--status-timer=1"]

        # --status-json only if the binary supports it.
        if _supports_status_json(binary):
            if "--status-json" not in cmd:
                cmd.append("--status-json")
        elif "--status-json" in cmd:
            cmd = [c for c in cmd if c != "--status-json"]

        self._emit("\n[>] " + format_command(cmd) + "\n", "info")

        try:
            self._proc = subprocess.Popen(
                cmd, stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                bufsize=0,
            )
        except (FileNotFoundError, PermissionError, OSError) as e:
            if self._on_output:
                self._on_output(f"Failed to start hashcat: {e}\n", "error")
            self._cleanup_outfile()
            self._finish([], failed=True)
            return

        self._read_stream(self._proc)

        try:
            self._proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self._proc.kill()

        self._poll_outfile()
        self._cleanup_outfile()
        # hashcat exit codes: 0 = cracked, 1 = exhausted (not found); anything
        # else is a failure (bad mode/hash, device error, ...).
        rc = self._proc.returncode
        failed = not self._stop_flag.is_set() and rc not in (0, 1)
        if failed:
            self._emit(f"[!] hashcat failed (exit {rc}).\n", "error")
        if self._kernel_error and not self._cracked:
            self._emit(self._kernel_hint(binary), "error")
            failed = True
        self._finish(self._cracked, failed)

    def _read_stream(self, proc):
        """Read hashcat's output in chunks.

        hashcat prints some phase messages ("Initializing device kernels…")
        without a trailing newline, so a plain line iterator would hold them
        back. Reading raw chunks lets us surface those markers immediately.
        """
        try:
            fd = proc.stdout.fileno()
        except Exception:
            return

        buf = ""
        emitted = set()
        while True:
            if self._stop_flag.is_set():
                proc.terminate()
                break
            try:
                chunk = os.read(fd, 4096)
            except OSError:
                break
            if not chunk:
                break
            buf += chunk.decode("utf-8", errors="replace")
            self._scan_phases(buf, emitted)
            while "\n" in buf:
                line, buf = buf.split("\n", 1)
                self._handle_line(line)
            if len(buf) > 65536:
                buf = buf[-8192:]
        if buf.strip():
            self._handle_line(buf)

    def _scan_phases(self, buf, emitted):
        for marker, label in _PHASE_MARKERS:
            if label in emitted:
                continue
            if marker in buf:
                emitted.add(label)
                if self._on_phase:
                    self._on_phase(label)

    def _handle_line(self, line):
        # hashcat separates its interactive status/prompt from real output with
        # bare CRs (no LF), so split on CR and drop the prompt fragments.
        if "\r" in line:
            for part in line.split("\r"):
                self._handle_line(part)
            return
        if not line.strip():
            return
        if _PROMPT_RE.search(line):
            return
        if line.lstrip().startswith("{") and self._handle_status_json(line):
            self._poll_outfile()
            return
        self._emit(f"  {line}\n")
        low = line.lower()
        if ("build failed" in low or "permission denied" in low
                or "no devices" in low):
            self._kernel_error = True
        self._parse_progress(line)
        self._poll_outfile()

    def _kernel_hint(self, binary):
        kdir = self._kernels_dir(binary)
        return (
            "\n[!] hashcat could not run its compute kernel.\n"
            f"    The kernel cache at {kdir} is not readable/writable by the\n"
            "    current user (usually because hashcat/Elwand was run as root\n"
            "    or with sudo before). Remove it and retry:\n"
            f'      rm -rf "{kdir}"/*\n')

    def _emit(self, text, color=None):
        if self._on_output:
            self._on_output(text, color)

    def _parse_progress(self, line):
        m = _PROGRESS_RE.search(line)
        if m:
            # The human "Progress" line counts REJECTED candidates too; drop
            # them so the bar reflects actually-hashed candidates.
            rej = self._progress_rejected
            self._progress_done = max(0, int(m.group(1)) - rej)
            self._progress_total = max(0, int(m.group(2)) - rej)
            if self._on_progress:
                self._on_progress(self._progress_done, self._progress_total,
                                  self._progress_recovered)
            return
        m = _RECOVERED_RE.search(line)
        if m:
            self._progress_recovered = int(m.group(1))
            return
        m = _REJECTED_RE.search(line)
        if m:
            self._progress_rejected = int(m.group(1))

    def _handle_status_json(self, raw):
        try:
            obj = json.loads(raw)
        except Exception:
            return False
        if not isinstance(obj, dict) or "status" not in obj:
            return False

        self._saw_status_json = True

        try:
            status_number = int(obj.get("status", -1))
        except (TypeError, ValueError):
            status_number = -1
        state = _STATUS_NAMES.get(status_number, "unknown")

        try:
            prog = obj.get("progress") or [0, 0]
            prog = (int(prog[0]), int(prog[1]))
        except (TypeError, ValueError, IndexError):
            prog = (0, 0)

        try:
            rec = obj.get("recovered_hashes") or [0, 0]
            rec = (int(rec[0]), int(rec[1]))
        except (TypeError, ValueError, IndexError):
            rec = (0, 0)

        try:
            rejected = int(obj.get("rejected") or 0)
        except (TypeError, ValueError):
            rejected = 0

        devices = []
        speed = 0
        for d in obj.get("devices") or []:
            try:
                sp = int(d.get("speed") or 0)
            except (TypeError, ValueError):
                sp = 0
            speed += sp
            devices.append({
                "name": d.get("device_name") or "",
                "type": d.get("device_type") or "",
                "speed": sp,
                "util": int(d.get("util") or 0),
                "temp": int(d.get("temp") or 0),
            })

        now = int(time.time())
        try:
            tstart = int(obj.get("time_start") or 0)
        except (TypeError, ValueError):
            tstart = 0
        try:
            est_stop = int(obj.get("estimated_stop") or 0)
        except (TypeError, ValueError):
            est_stop = 0

        elapsed = max(0, now - tstart) if tstart else 0
        eta = max(0, est_stop - now) if est_stop > now else 0
        if not eta and prog[0] > 0 and prog[1] > prog[0] and elapsed:
            eta = int(elapsed * (prog[1] - prog[0]) / prog[0])

        self._progress_done, self._progress_total = prog
        self._progress_recovered = rec[0]

        status = {
            "state": state,
            "status_number": status_number,
            "progress": prog,
            "rejected": rejected,
            "recovered": rec,
            "speed": speed,
            "elapsed": elapsed,
            "eta": eta,
            "devices": devices,
            "guess_base": obj.get("guess_base"),
            "mask_len": int(obj.get("guess_mask_length") or 0),
        }

        if self._on_status:
            self._on_status(status)
        elif self._on_progress:
            self._on_progress(prog[0], prog[1], rec[0])
        return True

    def _finish(self, cracked, failed=False):
        if (not self._saw_status_json and self._on_progress
                and self._progress_total > 0):
            self._on_progress(self._progress_total, self._progress_total,
                              self._progress_recovered)
        if self._on_done:
            self._on_done(cracked or [], failed)
