"""Hashcat engine — wraps the hashcat binary for background cracking."""
import json
import os
import re
import subprocess
import tempfile
import threading
import time

from src.resolve_binary import resolve


_PROGRESS_RE = re.compile(r"Progress\.+:\s+(\d+)/(\d+)")
_RECOVERED_RE = re.compile(r"Recovered\.+:\s+(\d+)/(\d+).*?Digests")

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


class HashcatEngine:
    def __init__(self, mode, hash_value, wordlist=None, mask=None,
                 custom_charsets=None, rules_file=None,
                 backend=None,
                 on_output=None, on_cracked=None, on_done=None,
                 on_progress=None, on_status=None):
        self._mode = str(mode)
        self._hash_value = hash_value
        self._wordlist = wordlist
        self._mask = mask
        self._custom_charsets = custom_charsets or {}
        self._rules_file = rules_file
        self._backend = backend
        self._on_output = on_output
        self._on_cracked = on_cracked
        self._on_done = on_done
        self._on_progress = on_progress
        self._on_status = on_status
        self._proc = None
        self._stop_flag = threading.Event()
        self._progress_done = 0
        self._progress_total = 0
        self._progress_recovered = 0
        self._outfile_path = None
        self._outfile_seen = 0
        self._cracked = []
        self._kernel_error = False
        self._saw_status_json = False

    def start(self):
        threading.Thread(target=self._run, daemon=True).start()

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
            return {"cpu": True, "gpu": True}

        try:
            r = subprocess.run(
                [binary, "-I"],
                capture_output=True, text=True, timeout=10,
            )
            output = r.stdout + r.stderr
            has_cpu = "Type...........: CPU" in output
            has_gpu = "Type...........: GPU" in output
            return {"cpu": has_cpu, "gpu": has_gpu}
        except (OSError, subprocess.TimeoutExpired):
            return {"cpu": True, "gpu": True}

    def _make_outfile(self):
        try:
            fd, path = tempfile.mkstemp(prefix="elwand_hashcat_", suffix=".out")
            os.close(fd)
            os.unlink(path)
            self._outfile_path = path
            return path
        except OSError:
            self._outfile_path = None
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
        if self._outfile_path:
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
            self._finish([])
            return

        self._clear_unreadable_kernels(binary)

        cmd = [binary, "-m", self._mode, self._hash_value]

        if self._mask:
            cmd.extend(["-a", "3", self._mask, "--increment"])
            for key, charset in sorted(self._custom_charsets.items()):
                if charset:
                    cmd.extend([f"-{key}", charset])
        else:
            cmd.append(self._wordlist)

        outfile = self._make_outfile()
        if outfile:
            cmd.extend(["--outfile", outfile, "--outfile-format", "2"])

        cmd.extend([
            "--quiet", "--status", "--status-timer=1", "--potfile-disable",
        ])
        if _supports_status_json(binary):
            cmd.append("--status-json")
        if self._backend:
            cmd.extend(["-D", self._backend])
        if self._rules_file:
            cmd.extend(["-r", self._rules_file])

        if self._mask:
            self._emit(
                f"\n[>] hashcat -m {self._mode} -a 3 "
                f"'{self._hash_value[:40]}...' {self._mask}\n", "info")
        else:
            self._emit(
                f"\n[>] hashcat -m {self._mode} "
                f"'{self._hash_value[:40]}...' {self._wordlist}\n", "info")

        try:
            self._proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1,
            )
        except (FileNotFoundError, PermissionError, OSError) as e:
            if self._on_output:
                self._on_output(f"Failed to start hashcat: {e}\n", "error")
            self._cleanup_outfile()
            self._finish([])
            return

        for line in self._proc.stdout:
            if self._stop_flag.is_set():
                self._proc.terminate()
                break
            line = line.rstrip("\n")
            if not line:
                continue
            if line.lstrip().startswith("{") and self._handle_status_json(line):
                self._poll_outfile()
                continue
            self._emit(f"  {line}\n")
            low = line.lower()
            if ("build failed" in low or "permission denied" in low
                    or "no devices" in low):
                self._kernel_error = True
            self._parse_progress(line)
            self._poll_outfile()

        try:
            self._proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self._proc.kill()

        self._poll_outfile()
        self._cleanup_outfile()
        if self._kernel_error and not self._cracked:
            self._emit(self._kernel_hint(binary), "error")
        self._finish(self._cracked)

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
            self._progress_done = int(m.group(1))
            self._progress_total = int(m.group(2))
            if self._on_progress:
                self._on_progress(self._progress_done, self._progress_total,
                                  self._progress_recovered)
            return
        m = _RECOVERED_RE.search(line)
        if m:
            self._progress_recovered = int(m.group(1))

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

    def _finish(self, cracked):
        if (not self._saw_status_json and self._on_progress
                and self._progress_total > 0):
            self._on_progress(self._progress_total, self._progress_total,
                              self._progress_recovered)
        if self._on_done:
            self._on_done(cracked or [])
