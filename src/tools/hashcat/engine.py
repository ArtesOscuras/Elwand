"""Hashcat engine — wraps the hashcat binary for background cracking."""
import os
import re
import subprocess
import tempfile
import threading

from src.resolve_binary import resolve


_PROGRESS_RE = re.compile(r"Progress\.+:\s+(\d+)/(\d+)")
_RECOVERED_RE = re.compile(r"Recovered\.+:\s+(\d+)/(\d+).*?Digests")


class HashcatEngine:
    def __init__(self, mode, hash_value, wordlist=None, mask=None,
                 custom_charsets=None, rules_file=None,
                 backend=None,
                 on_output=None, on_cracked=None, on_done=None,
                 on_progress=None):
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
        self._proc = None
        self._stop_flag = threading.Event()
        self._progress_done = 0
        self._progress_total = 0
        self._progress_recovered = 0
        self._outfile_path = None
        self._outfile_seen = 0
        self._cracked = []

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
            self._emit(f"  {line}\n")
            self._parse_progress(line)
            self._poll_outfile()

        try:
            self._proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self._proc.kill()

        self._poll_outfile()
        self._cleanup_outfile()
        self._finish(self._cracked)

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

    def _finish(self, cracked):
        if self._on_progress and self._progress_total > 0:
            self._on_progress(self._progress_total, self._progress_total,
                              self._progress_recovered)
        if self._on_done:
            self._on_done(cracked or [])
