"""macOS Wi-Fi scanning backend based on CoreWLAN (pyobjc).

This module is imported lazily and only ever used when Elwand runs on macOS.
It provides the same normalized network dictionaries as the Linux backend so
the GUI can render them without platform-specific code.

Importing CoreWLAN is optional: if the dependency is missing, `available()`
returns False and the caller degrades gracefully. Nothing here is imported on
Linux, so the Linux code path is completely unaffected.
"""

import os
import shutil
import struct
import subprocess
import time


def available():
    try:
        import CoreWLAN  # noqa: F401
        return True
    except Exception:
        return False


def _client():
    from CoreWLAN import CWWiFiClient
    return CWWiFiClient.sharedWiFiClient()


def interfaces():
    if available():
        try:
            return [i.interfaceName() for i in _client().interfaces()]
        except Exception:
            pass
    fallback = _hardwareport_interface()
    return [fallback] if fallback else []


def _hardwareport_interface():
    try:
        r = subprocess.run(
            ["networksetup", "-listallhardwareports"],
            capture_output=True, text=True, timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    port = None
    for line in r.stdout.splitlines():
        line = line.strip()
        if line.startswith("Hardware Port:"):
            port = line.split(":", 1)[1].strip()
        elif line.startswith("Device:") and port and "Wi-Fi" in port:
            return line.split(":", 1)[1].strip()
    return None


def _dbm_to_pct(dbm):
    if dbm is None:
        return 0
    return max(0, min(100, 2 * (dbm + 100)))


def _channel_to_freq(ch):
    if ch in (None, 0):
        return ""
    if 1 <= ch <= 13:
        return f"{2412 + (ch - 1) * 5} MHz"
    if 36 <= ch <= 64:
        return f"{5180 + (ch - 36) * 5} MHz"
    if 100 <= ch <= 144:
        return f"{5500 + (ch - 100) * 5} MHz"
    if 149 <= ch <= 165:
        return f"{5745 + (ch - 149) * 5} MHz"
    return f"{ch}"


_SECURITY_NAMES = {
    "kCWSecurityNone": "OPEN",
    "kCWSecurityWEP": "WEP",
    "kCWSecurityDynamicWEP": "WEP",
    "kCWSecurityWPAPersonal": "WPA1",
    "kCWSecurityWPAEnterprise": "WPA1",
    "kCWSecurityWPAPersonalMixed": "WPA1 WPA2",
    "kCWSecurityWPAEnterpriseMixed": "WPA1 WPA2",
    "kCWSecurityWPA2Personal": "WPA2",
    "kCWSecurityPersonal": "WPA2",
    "kCWSecurityWPA2Enterprise": "WPA2",
    "kCWSecurityEnterprise": "WPA2",
    "kCWSecurityWPA3Personal": "WPA3",
    "kCWSecurityWPA3Enterprise": "WPA3",
    "kCWSecurityWPA3Transition": "WPA2 WPA3",
    "kCWSecurityOWE": "OWE",
    "kCWSecurityOWETransition": "OWE",
}


def _security_label(corewlan, network):
    try:
        value = int(network.strongestSupportedSecurity())
    except Exception:
        return "WPA2"
    for name, label in _SECURITY_NAMES.items():
        if getattr(corewlan, name, None) == value:
            return label
    return "WPA2"


def _tcpdump():
    for p in (shutil.which("tcpdump"), "/usr/sbin/tcpdump",
              "/usr/bin/tcpdump"):
        if p and os.path.exists(p):
            return p
    return None


def _read_exact(stream, n):
    buf = b""
    while len(buf) < n:
        chunk = stream.read(n - len(buf))
        if not chunk:
            return None
        buf += chunk
    return buf


def cleanup_capture():
    """Kill leftover monitor tcpdump processes that hold /dev/bpf* devices.

    If a previous capture was interrupted (Ctrl+C, crash, Elwand killed) the
    tcpdump process can survive and keep the BPF device busy, which makes the
    next capture fail or return nothing. Best effort; needs root to kill the
    root-owned ones."""
    try:
        subprocess.run(["pkill", "-f", "tcpdump -I"],
                       capture_output=True, timeout=5)
    except Exception:
        pass


def _stderr_reader(proc, on_line):
    try:
        for raw in iter(proc.stderr.readline, b""):
            line = raw.decode("utf-8", "replace").strip()
            if line:
                on_line(line)
    except Exception:
        pass


# Channels to hop through while capturing (2.4 GHz + 5 GHz).
HOP_CHANNELS = [1, 6, 11, 36, 40, 44, 48, 100, 116, 132, 149, 153, 157, 161]
HOP_DWELL = 0.6
# How long a locked-channel session is kept alive (until the lock changes/stop).
LOCK_HOLD = float("inf")


def _pick_channel(dev, chan):
    """Prefer the 20 MHz variant of a channel (beacons are 20 MHz wide)."""
    best = None
    best_w = None
    for c in (dev.supportedWLANChannels() or []):
        if int(c.channelNumber()) == int(chan):
            w = int(c.channelWidth())
            if best is None or w < best_w:
                best, best_w = c, w
    return best


def set_channel(iface, chan):
    """Set the Wi-Fi channel via CoreWLAN (public API, what `airport` used).

    CoreWLAN refuses to change the channel while the interface is associated,
    which is fine: it is called in monitor mode (disassociated). Returns True
    on success."""
    if not available():
        return False
    try:
        dev = _client().interfaceWithName_(iface)
        if dev is None:
            return False
        c = _pick_channel(dev, chan)
        if c is None:
            return False
        res = dev.setWLANChannel_error_(c, None)
        return bool(res[0]) if isinstance(res, tuple) else bool(res)
    except Exception:
        return False


def supported_channels(iface):
    """Sorted unique channel numbers the radio supports (from CoreWLAN)."""
    if not available():
        return []
    try:
        dev = _client().interfaceWithName_(iface)
        if dev is None:
            return []
        return sorted({int(c.channelNumber())
                       for c in (dev.supportedWLANChannels() or [])})
    except Exception:
        return []


def _hop_band(iface, chans, stop_event, deadline):
    """Hop the given channels until deadline (or stop).

    When `wifi_monitor` has a channel locked, park on it instead of cycling
    (as long as it belongs to this band). Returns as soon as the lock changes
    or is released so `capture_loop` can recreate the session on the right band.
    """
    from src.tools.scanner import wifi_monitor as wm
    i = 0
    fails = 0
    lock = wm._locked_channel
    while not stop_event.is_set() and time.time() < deadline:
        if wm._locked_channel != lock:
            return fails
        target = lock or chans[i % len(chans)]
        if not set_channel(iface, target):
            fails += 1
        i += 1
        end = min(deadline, time.time() + HOP_DWELL)
        while time.time() < end and not stop_event.is_set():
            if wm._locked_channel != lock:
                return fails
            time.sleep(0.05)
    return fails


def _pump(proc, iface, stop_event, deadline, lock_snapshot=None):
    """Read radiotap frames from proc.stdout until deadline/stop/exit.

    Also returns when `wifi_monitor`'s locked channel differs from
    `lock_snapshot` (the lock was set, changed or released mid-session), so the
    session is torn down and recreated with the new lock.
    """
    from functools import partial
    from src.tools.scanner import wifi_monitor as wm
    process = partial(wm._process, device=iface)
    frames = 0
    gh = _read_exact(proc.stdout, 24)
    if not gh:
        return 0
    big = gh[:4] in (b"\xa1\xb2\xc3\xd4", b"\xa1\xb2\x3c\x4d")
    endian = ">" if big else "<"
    while (not stop_event.is_set() and time.time() < deadline
           and proc.poll() is None
           and wm._locked_channel == lock_snapshot):
        ph = _read_exact(proc.stdout, 16)
        if ph is None:
            break
        _ts, _tus, incl, _orig = struct.unpack(endian + "IIII", ph)
        if incl <= 0 or incl > 65535:
            break
        data = _read_exact(proc.stdout, incl)
        if data is None:
            break
        try:
            from scapy.all import RadioTap
            pkt = RadioTap(data)
        except Exception:
            continue
        try:
            process(pkt)
            frames += 1
        except Exception:
            pass
    return frames



def capture_loop(iface, stop_event, hop=True):
    """Monitor-mode RX on macOS via tcpdump -I (radiotap).

    The radio latches onto the band it is on when tcpdump starts, so we run one
    tcpdump per band (binding it by starting on that band's first channel) and
    hop every channel of the band. Requires root (BPF) and the interface to be
    **disassociated** (monitor cannot run while associated; macOS may auto-rejoin).
    """
    import threading
    from src.tools.scanner import wifi_monitor as wm

    tcpdump = _tcpdump()
    if not tcpdump:
        wm._emit_error("macOS monitor: tcpdump not found.")
        return

    cleanup_capture()
    chans = supported_channels(iface) or HOP_CHANNELS
    if hop:
        c24 = [c for c in chans if c <= 14]
        c5 = [c for c in chans if c >= 36]
        bands = [b for b in (c24, c5) if b] or [chans]
    else:
        bands = [chans]
    wm._emit_info(f"macOS monitor: capturing on {iface} "
                  f"({len(bands)} band(s), {len(chans)} channels)")

    err = {"n": 0}

    def _on_err(line):
        low = line.lower()
        core = low.split("tcpdump:", 1)[-1].strip()
        if ("packets captured" in core or "packets received by filter" in core
                or "packets dropped by kernel" in core
                or core.startswith("listening on")
                or core.startswith("data link type")):
            return
        err["n"] += 1
        if err["n"] <= 10:
            wm._emit_error(f"tcpdump: {core}")

    announced = None
    while not stop_event.is_set():
        locked = wm._locked_channel
        if locked != announced:
            if locked:
                wm._emit_info(f"macOS monitor: locked to channel {locked} "
                              f"on {iface}")
            else:
                wm._emit_info(f"macOS monitor: channel lock released on "
                              f"{iface}, resuming hop")
            announced = locked
        session_bands = [[locked]] if locked else bands
        for band in session_bands:
            if stop_event.is_set():
                break
            # A lock set while the previous band was running must take effect
            # now, before binding this band's first channel.
            if wm._locked_channel != locked:
                break
            lock_snapshot = wm._locked_channel
            # Bind the monitor to this band by starting on its first channel.
            set_channel(iface, band[0])
            time.sleep(0.3)
            try:
                proc = subprocess.Popen(
                    [tcpdump, "-I", "-i", iface, "-y", "IEEE802_11_RADIO",
                     "-U", "-w", "-"],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            except Exception as e:
                wm._emit_error(f"macOS monitor: could not start tcpdump: {e}")
                return
            threading.Thread(target=_stderr_reader, args=(proc, _on_err),
                             daemon=True).start()
            if lock_snapshot:
                deadline = time.time() + LOCK_HOLD
            else:
                deadline = time.time() + max(len(band) * HOP_DWELL, 3.0) + 5.0
            hp = threading.Thread(target=_hop_band,
                                  args=(iface, band, stop_event, deadline),
                                  daemon=True)
            hp.start()
            _pump(proc, iface, stop_event, deadline, lock_snapshot)
            _terminate(proc)
            hp.join(timeout=2)


def _terminate(proc):
    try:
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


def scan(iface=None):
    if not available():
        return []
    import CoreWLAN

    client = _client()
    if iface:
        try:
            devices = [client.interfaceWithName_(iface)]
        except Exception:
            devices = []
    else:
        try:
            devices = list(client.interfaces())
        except Exception:
            devices = []

    nets = []
    for dev in devices:
        if dev is None:
            continue
        name = dev.interfaceName()
        try:
            networks, _err = dev.scanForNetworksWithName_error_(None, None)
        except Exception:
            continue
        for n in networks or []:
            bssid = (n.bssid() or "").upper()
            ssid = n.ssid() or "(hidden)"
            try:
                dbm = int(n.rssiValue())
            except (TypeError, ValueError):
                dbm = None
            try:
                chan = int(n.wlanChannel().channelNumber()) if n.wlanChannel() else 0
            except Exception:
                chan = 0
            nets.append({
                "ssid": ssid,
                "bssid": bssid,
                "signal": _dbm_to_pct(dbm),
                "signal_dbm": dbm,
                "security": _security_label(CoreWLAN, n),
                "chan": chan,
                "freq": _channel_to_freq(chan),
                "device": name,
                "devices": [name],
                "stale": False,
                "last_seen": time.time(),
            })
    return nets
