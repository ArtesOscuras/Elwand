import threading
from scapy.all import sniff, DNS
from scapy.config import conf
conf.verb = 0


def _check_permission():
    try:
        sniff(filter="udp port 5353", timeout=0.1, count=1, store=0)
        return True
    except (PermissionError, OSError):
        return False


class PassiveMDNSScanner:
    def __init__(self, on_host_callback):
        self.on_host = on_host_callback
        self._thread = None
        self._running = False

    def start(self):
        if self._running:
            return True
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return True

    def stop(self):
        self._running = False

    @property
    def is_running(self):
        return self._running

    def _run(self):
        while self._running:
            try:
                sniff(
                    filter="udp port 5353",
                    prn=self._process_packet,
                    timeout=2,
                    store=0,
                )
            except PermissionError:
                self._running = False
                self._emit_error("mDNS passive: permission denied. Run as root or install CAP_NET_RAW.")
                break
            except OSError as e:
                self._emit_error(f"mDNS passive error: {e}")
            except Exception as e:
                self._emit_error(f"mDNS passive transient error: {e}")

    @staticmethod
    def _emit_error(msg):
        try:
            from src import event_bus
            event_bus.submit({"type": "scan_error", "message": msg})
        except Exception:
            pass

    def _process_packet(self, pkt):
        try:
            dns = pkt[DNS]
        except Exception:
            return
        if dns.qr != 1:
            return
        if dns.ancount == 0:
            return

        answers = dns.an if isinstance(dns.an, list) else [dns.an]

        ptr_map = {}
        hosts4 = {}
        hosts6 = {}
        txts = {}
        srv_targets = {}

        for ans in answers:
            rrname = _decode_name(ans.rrname)

            if ans.type == 12:          # PTR
                ptr_map[rrname] = _decode_name(ans.rdata)

            elif ans.type == 1:         # A
                hosts4[rrname] = ans.rdata

            elif ans.type == 28:        # AAAA
                hosts6[rrname] = ans.rdata

            elif ans.type == 33:        # SRV
                target = _decode_name(getattr(ans, "target", ""))
                if not target and isinstance(ans.rdata, bytes):
                    target = _decode_name(_parse_srv_target(ans.rdata))
                srv_targets[rrname] = target

            elif ans.type == 16:        # TXT
                txts[rrname] = _parse_txt(ans.rdata)

        for service_type, instance_name in ptr_map.items():
            target_host = srv_targets.get(instance_name)
            if not target_host:
                continue
            # Prefer the IPv4 address; fall back to IPv6 only when there is no
            # A record. Machines are keyed by IPv4, and an AAAA must never be
            # used as the primary address.
            raw_ip = hosts4.get(target_host) or hosts6.get(target_host)
            if not raw_ip:
                continue
            ip = str(raw_ip)
            txt = txts.get(instance_name, {})

            from src.tools.scanner.mdns_cache import add_service
            add_service(ip, service_type + ".", hostname=target_host, txt=txt)
            self.on_host(ip=ip, hostname=target_host, method="mDNS-Passive")

            # If both records exist, also report the AAAA once the IPv4 machine
            # exists: the discovery handler attaches it to that machine's IPv6
            # field instead of creating a separate (IPv6-keyed) machine.
            raw_ip6 = hosts6.get(target_host)
            ip6 = str(raw_ip6) if raw_ip6 else ""
            if hosts4.get(target_host) and ip6 and ip6 != ip:
                self.on_host(ip=ip6, hostname=target_host,
                             method="mDNS-Passive")


def _decode_name(val):
    if isinstance(val, bytes):
        return val.rstrip(b".").decode(errors="replace")
    return str(val).rstrip(".")


def _parse_srv_target(rdata):
    if len(rdata) < 7:
        return ""
    pos = 6
    parts = []
    while pos < len(rdata):
        length = rdata[pos]
        if length == 0:
            break
        if pos + 1 + length > len(rdata):
            break
        parts.append(rdata[pos + 1 : pos + 1 + length].decode(errors="replace"))
        pos += 1 + length
    return ".".join(parts)


def _parse_txt(rdata):
    txt = {}
    items = []
    if isinstance(rdata, list):
        items = rdata
    elif isinstance(rdata, bytes):
        items = rdata.split(b"\x00") if b"\x00" in rdata else [rdata]
    else:
        return txt
    for item in items:
        item_str = item.decode(errors="replace") if isinstance(item, bytes) else str(item)
        item_str = item_str.strip("\x00").strip()
        if not item_str:
            continue
        if "=" in item_str:
            k, v = item_str.split("=", 1)
            txt[k] = v
    return txt
