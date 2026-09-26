import os
import platform
import re
import shutil
import socket
import subprocess
import threading
import time
import tkinter as tk
from concurrent.futures import ThreadPoolExecutor, as_completed
from src.network_iface import interfaces, ifaddresses, AF_INET
from . import fonts
from . import windowing
from .console import Console
from .visualizer import Visualizer
from .views import WifiView, NetworkView, DomainListView, EvidenceListView, CredentialListView, UsersView, PasswordsView, HashListView, ShellListView, ToolsView, InventoryView, PeopleView, ServicesView, DictionarysView, RulesView, PocsView, ReportsView, ReportView, HandshakesView
from .dialogs import ScanDialog
from src import settings as elwand_settings
from src.machines import store, start_autosave as start_machines_autosave, stop_autosave as stop_machines_autosave
from src.machines import machine_db
from src.machines import domain_db
import src.machines
from src.tools.scanner import PassiveMDNSScanner, ActiveScanner
from src.tools.scanner.mdns_cache import load as load_mdns_cache, save as save_mdns_cache, start_autosave, clear as clear_mdns_cache, wipe as wipe_mdns_cache
from src.tools.scanner.identifier import identify_device, get_gateway_ip, extract_model_for_ip, _probe_smb_info, _probe_ssh_banner, _probe_ttl, _run_whatweb, _probe_web_internal, _identify_linux_distro, _extract_domains_from_whatweb, _dbg
from src.shells import ShellListener, shell_db
from src import event_bus

import datetime as _datetime

def _ctx_log(msg):
    try:
        from src.elwand_paths import runtime_logs_dir
        p = str(runtime_logs_dir())
        import os as _os
        _os.makedirs(p, exist_ok=True)
        with open(_os.path.join(p, "ctx_debug.log"), "a") as f:
            f.write(f"{_datetime.datetime.now().isoformat()} {msg}\n")
    except Exception:
        pass


class _ReviewDialogManager:
    def __init__(self, parent):
        self._parent = parent
        self._dlg = None
        self._url_entry = None
        self._method_var = None
        self._headers_text = None
        self._resp_headers_text = None
        self._body_text = None
        self._status_label = None
        self._resp_header_label = None
        self._on_send = None
        self._done = None
        self._stage = None
        self._review_out = False
        self._review_in = False

    def add(self, url, method, headers, body, res_type, stage, on_send, done,
            resp_status=None, resp_status_text=None, resp_headers=None, resp_body=""):
        _dbg(f"[review] add: stage={stage} review_out={self._review_out} review_in={self._review_in} url={url[:80]}")
        if stage == "Request" and not self._review_out:
            _dbg("[review] continuing (outgoing off)")
            on_send()
            done.set()
            return
        if stage == "Response" and not self._review_in:
            _dbg("[review] continuing (incoming off)")
            on_send()
            done.set()
            return
        _dbg("[review] adding to pending")
        self._on_send = on_send
        self._done = done
        self._stage = stage
        self._pending = (url, method, headers, body, res_type,
                         resp_status, resp_status_text, resp_headers, resp_body)
        self._parent.after(0, self._show_pending)

    def show_waiting(self):
        self._parent.after(100, self._show_waiting_ui)

    def _show_pending(self):
        if self._dlg is None:
            self._build_dialog()
        url, method, headers, body, res_type, resp_status, resp_status_text, resp_headers, resp_body = self._pending
        label = "OUTGOING" if self._stage == "Request" else "INCOMING"
        self._dlg.title(f"Review Request — {label}")
        self._url_entry.delete(0, tk.END)
        self._url_entry.insert(0, url)
        self._method_var.set(method)
        info_parts = []
        if res_type:
            info_parts.append(f"Type: {res_type}")
            if self._stage == "Response" and res_type == "Document":
                info_parts.append("WARNING: body edits not supported for page HTML")
        if self._stage == "Response":
            info_parts.append(f"Status: {resp_status or '?'} {resp_status_text or ''}")
        self._status_label.configure(text="  |  ".join(info_parts) if info_parts else "")
        self._headers_text.configure(state=tk.NORMAL)
        self._headers_text.delete("1.0", tk.END)
        if headers:
            for k, v in headers.items():
                self._headers_text.insert(tk.END, f"{k}: {v}\n")
        self._headers_text.configure(state=tk.NORMAL)
        self._resp_headers_text.configure(state=tk.NORMAL)
        self._resp_headers_text.delete("1.0", tk.END)
        if self._stage == "Response" and resp_headers:
            for k, v in resp_headers.items():
                self._resp_headers_text.insert(tk.END, f"{k}: {v}\n")
        self._resp_headers_text.configure(state=tk.NORMAL)
        self._body_text.configure(state=tk.NORMAL)
        self._body_text.delete("1.0", tk.END)
        display = body if self._stage == "Request" and body else ""
        if self._stage == "Response" and resp_body:
            display = resp_body
        if display:
            self._body_text.insert("1.0", display)
        self._original_body = self._body_text.get("1.0", "end-1c")
        self._body_text.configure(state=tk.NORMAL)
        self._dlg.deiconify()
        self._dlg.lift()
        self._dlg.focus_set()

    def _build_dialog(self):
        self._dlg = tk.Toplevel(self._parent)
        self._dlg.title("Review Request")
        windowing.size_dialog(self._dlg, 800, 750)
        self._dlg.configure(bg="#111111")
        self._dlg.protocol("WM_DELETE_WINDOW", self._send_and_close)
        self._dlg.columnconfigure(0, weight=1)
        row = 0
        self._dlg.rowconfigure(row, weight=0)

        url_frame = tk.Frame(self._dlg, bg="#111111")
        url_frame.grid(row=row, column=0, sticky="ew", padx=15, pady=(10, 0))
        url_frame.columnconfigure(1, weight=1)
        tk.Label(url_frame, text="URL:", bg="#111111", fg="#aaaaaa",
                 font=("Menlo", 10)).grid(row=0, column=0, sticky="w", padx=(0, 5))
        self._url_entry = tk.Entry(url_frame, bg="#000000", fg="#ffffff",
                                   font=("Menlo", 10), borderwidth=0, highlightthickness=1,
                                   highlightbackground="#333333", insertbackground="#ffffff")
        self._url_entry.grid(row=0, column=1, sticky="ew")
        row += 1
        self._dlg.rowconfigure(row, weight=0)

        info_frame = tk.Frame(self._dlg, bg="#111111")
        info_frame.grid(row=row, column=0, sticky="ew", padx=15, pady=(5, 0))
        info_frame.columnconfigure(2, weight=1)
        tk.Label(info_frame, text="Method:", bg="#111111", fg="#aaaaaa",
                 font=("Menlo", 10)).grid(row=0, column=0, sticky="w", padx=(0, 5))
        self._method_var = tk.StringVar(value="GET")
        method_menu = tk.OptionMenu(info_frame, self._method_var, "GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS")
        method_menu.configure(bg="#000000", fg="#ffffff", borderwidth=0, highlightthickness=0,
                               font=("Menlo", 10), activebackground="#333333", activeforeground="#ffffff")
        method_menu["menu"].configure(bg="#000000", fg="#ffffff", font=("Menlo", 10))
        method_menu.grid(row=0, column=1, sticky="w")
        self._status_label = tk.Label(info_frame, text="", bg="#111111", fg="#888888",
                                       font=("Menlo", 10))
        self._status_label.grid(row=0, column=2, sticky="w", padx=(15, 0))
        row += 1
        self._dlg.rowconfigure(row, weight=0)

        tk.Label(self._dlg, text="Request Headers:", bg="#111111", fg="#aaaaaa",
                 font=("Menlo", 10, "bold"), anchor="w").grid(row=row, column=0, sticky="ew", padx=15, pady=(10, 0))
        row += 1
        self._dlg.rowconfigure(row, weight=1)

        self._headers_text = tk.Text(self._dlg, bg="#000000", fg="#ffffff",
                                      font=("Menlo", 10), borderwidth=0, highlightthickness=1,
                                      highlightbackground="#333333", insertbackground="#ffffff",
                                      wrap=tk.NONE, padx=8, pady=8, height=5)
        self._headers_text.grid(row=row, column=0, sticky="nsew", padx=15, pady=(2, 0))
        row += 1
        self._dlg.rowconfigure(row, weight=0)

        self._resp_header_label = tk.Label(self._dlg, text="Response Headers:", bg="#111111", fg="#aaaaaa",
                                            font=("Menlo", 10, "bold"), anchor="w")
        self._resp_header_label.grid(row=row, column=0, sticky="ew", padx=15, pady=(10, 0))
        row += 1
        self._dlg.rowconfigure(row, weight=1)

        self._resp_headers_text = tk.Text(self._dlg, bg="#000000", fg="#ffffff",
                                           font=("Menlo", 10), borderwidth=0, highlightthickness=1,
                                           highlightbackground="#333333", insertbackground="#ffffff",
                                           wrap=tk.NONE, padx=8, pady=8, height=4)
        self._resp_headers_text.grid(row=row, column=0, sticky="nsew", padx=15, pady=(2, 0))
        row += 1
        self._dlg.rowconfigure(row, weight=0)

        tk.Label(self._dlg, text="Body:", bg="#111111", fg="#aaaaaa",
                 font=("Menlo", 10, "bold"), anchor="w").grid(row=row, column=0, sticky="ew", padx=15, pady=(10, 0))
        row += 1
        self._dlg.rowconfigure(row, weight=2)

        self._body_text = tk.Text(self._dlg, bg="#000000", fg="#ffffff",
                                   font=("Menlo", 10), borderwidth=0, highlightthickness=1,
                                   highlightbackground="#333333", insertbackground="#ffffff",
                                   wrap=tk.WORD, padx=8, pady=8)
        self._body_text.grid(row=row, column=0, sticky="nsew", padx=15, pady=(2, 0))
        row += 1
        self._dlg.rowconfigure(row, weight=0)

        check_frame = tk.Frame(self._dlg, bg="#111111")
        check_frame.grid(row=row, column=0, sticky="w", padx=15, pady=(8, 0))
        self._out_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            check_frame, text="  Review outgoing", variable=self._out_var,
            bg="#111111", fg="#888888", selectcolor="#111111",
            font=("Menlo", 10),
            activebackground="#111111", activeforeground="#ffffff",
            command=self._on_check_change,
        ).pack(side=tk.LEFT, padx=(0, 15))
        self._in_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            check_frame, text="  Review incoming", variable=self._in_var,
            bg="#111111", fg="#888888", selectcolor="#111111",
            font=("Menlo", 10),
            activebackground="#111111", activeforeground="#ffffff",
            command=self._on_check_change,
        ).pack(side=tk.LEFT)
        row += 1
        self._dlg.rowconfigure(row, weight=0)

        btn_frame = tk.Frame(self._dlg, bg="#111111")
        btn_frame.grid(row=row, column=0, sticky="ew", padx=15, pady=(8, 12))
        send_btn = tk.Label(
            btn_frame, text="  Send  ", bg="#222222", fg="#ffffff",
            font=("Menlo", 10), relief=tk.RAISED, bd=1,
            padx=15, pady=6,
        )
        send_btn.pack(side=tk.RIGHT)
        send_btn.bind("<Button-1>", lambda e: self._send_and_close())
        send_btn.bind("<Enter>", lambda e: send_btn.config(bg="#333333"))
        send_btn.bind("<Leave>", lambda e: send_btn.config(bg="#222222"))

    def _show_waiting_ui(self):
        if self._dlg is None:
            self._build_dialog()
        self._dlg.title("Review Request")
        self._url_entry.delete(0, tk.END)
        self._method_var.set("GET")
        self._status_label.configure(text="Waiting for requests...")
        self._headers_text.configure(state=tk.NORMAL)
        self._headers_text.delete("1.0", tk.END)
        self._resp_headers_text.configure(state=tk.NORMAL)
        self._resp_headers_text.delete("1.0", tk.END)
        self._body_text.configure(state=tk.NORMAL)
        self._body_text.delete("1.0", tk.END)
        self._dlg.deiconify()
        self._dlg.lift()
        self._dlg.focus_set()

    def _on_check_change(self):
        self._review_out = self._out_var.get()
        self._review_in = self._in_var.get()

    def _parse_text_headers(self, text_widget):
        raw = text_widget.get("1.0", "end-1c")
        headers = {}
        for line in raw.split("\n"):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" in line:
                k, _, v = line.partition(":")
                headers[k.strip()] = v.strip()
        return headers

    def _send_and_close(self):
        if self._on_send:
            url = self._url_entry.get().strip()
            method = self._method_var.get()
            body = self._body_text.get("1.0", "end-1c")
            if body == self._original_body:
                body = None
            if self._stage == "Response":
                headers = self._parse_text_headers(self._resp_headers_text)
            else:
                headers = self._parse_text_headers(self._headers_text)
            self._on_send(url=url if url else None,
                          method=method if method else None,
                          headers=headers if headers else None,
                          body=body)
        self._original_body = ""
        self._on_send = None
        self._url_entry.delete(0, tk.END)
        self._method_var.set("GET")
        self._status_label.configure(text="Sent. Waiting for next request...")
        self._headers_text.configure(state=tk.NORMAL)
        self._headers_text.delete("1.0", tk.END)
        self._resp_headers_text.configure(state=tk.NORMAL)
        self._resp_headers_text.delete("1.0", tk.END)
        self._body_text.configure(state=tk.NORMAL)
        self._body_text.delete("1.0", tk.END)
        if self._done:
            self._done.set()
            self._done = None

    def close(self):
        def _close_ui():
            if self._dlg:
                self._dlg.destroy()
                self._dlg = None
            if self._done:
                self._done.set()
        self._parent.after(0, _close_ui)


def _probe_one_port(ip, port, payload_bytes, label):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(3)
    response = b""
    try:
        sock.connect((ip, port))
        sock.sendall(payload_bytes)
        sock.settimeout(3)
        while True:
            try:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                response += chunk
            except socket.timeout:
                break
    except Exception:
        pass
    finally:
        sock.close()
    text = response.decode(errors="replace").strip()
    return label, text


def _do_port_inspection(ip, port):
    from concurrent.futures import ThreadPoolExecutor, as_completed
    probes = [
        ("hello\r\n", "hello"),
        ("GET / HTTP/1.0\r\nHost: {ip}\r\n\r\n", "HTTP GET"),
        (bytes([0x16, 0x03, 0x01, 0x00, 0x01, 0x01, 0x00, 0x03, 0x03] + [0x00]*36), "TLS ClientHello"),
        ("SSH-2.0-OpenSSH_client\r\n", "SSH hello"),
        ("EHLO test\r\n", "SMTP EHLO"),
        ("USER anonymous\r\n", "FTP USER"),
        ("PING\r\n", "Redis PING"),
        ("CAPA\r\n", "POP3 CAPA"),
        ("a001 CAPABILITY\r\n", "IMAP CAPABILITY"),
        ("INFO\r\n", "Redis INFO"),
        ("stats\r\n", "Memcached stats"),
        ("QUIT\r\n", "QUIT"),
        ("\x01\x00\x00\x01\x01", "RDP connect"),
        (b"\x00\x00\x00\xa4\x00\x00\x00\x04\x00\x00\x00\x00\x00\x00\x00\x0d\x00\x00\x00\x08", "PostgreSQL startup"),
        (b"\x00\x00\x00\x85\xffSMBr\x00\x00\x00\x00\x18", "SMB negotiate"),
        ("RFB 003.008\n", "VNC RFB"),
        (b"\x00" * 36, "MySQL handshake"),
        ('{"isMaster": 1}', "MongoDB isMaster"),
        ('{"buildinfo": 1}', "MongoDB buildInfo"),
        ("GET /version HTTP/1.0\r\nHost: {ip}\r\n\r\n", "Docker API"),
        ("GET /_cluster/health HTTP/1.0\r\nHost: {ip}\r\n\r\n", "Elasticsearch"),
        ("HELP\r\n", "generic HELP"),
        ("STATUS\r\n", "generic STATUS"),
        ("OPTIONS / HTTP/1.0\r\nHost: {ip}\r\n\r\n", "HTTP OPTIONS"),
        ("OPTIONS * RTSP/1.0\r\nCSeq: 1\r\n\r\n", "RTSP OPTIONS"),
        ("OPTIONS sip:test@{ip} SIP/2.0\r\nVia: SIP/2.0/TCP test\r\nFrom: <sip:test@test>\r\nTo: <sip:test@test>\r\nCall-ID: 1@test\r\nCSeq: 1 OPTIONS\r\n\r\n", "SIP OPTIONS"),
        ("\xff\xfb\x01\xff\xfb\x03\xff\xfd\x18", "Telnet options"),
        ("\x00\x00\x00\x01", "MySQL login"),
    ]
    results = []
    futures = {}
    with ThreadPoolExecutor(max_workers=5) as ex:
        for payload, label in probes:
            if isinstance(payload, str):
                payload_bytes = payload.replace("{ip}", ip).encode()
            else:
                payload_bytes = payload
            futures[ex.submit(_probe_one_port, ip, port, payload_bytes, label)] = label
        for f in as_completed(futures):
            label, text = f.result()
            if text:
                results.append((label, text))
    return results


def _do_ping(ip):
    try:
        if os.geteuid() == 0:
            from scapy.all import sr1, IP, ICMP
            start = time.monotonic()
            reply = sr1(IP(dst=ip) / ICMP(), timeout=2, verbose=False)
            elapsed = time.monotonic() - start
            if reply is not None:
                return (elapsed * 1000, reply.ttl)
    except Exception:
        pass
    if shutil.which("ping"):
        cmd = ["ping", "-n", "1", ip] if platform.system().lower() == "windows" else ["ping", "-c", "1", ip]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            output = proc.stdout + proc.stderr
            if proc.returncode != 0:
                return None
            m = re.search(r'time[=<](\d+\.?\d*)\s*ms', output)
            rtt = float(m.group(1)) if m else None
            m = re.search(r'ttl[=<](\d+)', output, re.IGNORECASE)
            ttl = int(m.group(1)) if m else None
            return (rtt, ttl)
        except Exception:
            pass
    return None


def _do_nslookup(host):
    import subprocess, shutil
    binary = shutil.which("nslookup")
    if not binary:
        return "nslookup not available on this system"
    try:
        proc = subprocess.run(
            [binary, host], capture_output=True, text=True, timeout=10
        )
    except subprocess.TimeoutExpired:
        return f"nslookup {host} timed out"
    except Exception as e:
        return f"nslookup {host} failed: {e}"
    output = (proc.stdout + proc.stderr).strip()
    if not output:
        return f"No response for {host}"
    addresses = []
    for line in output.splitlines():
        m = re.search(r"Address[es]*:\s+(\S+)", line)
        if m:
            addr = m.group(1)
            if addr not in addresses and ":" not in addr:
                addresses.append(addr)
    if not addresses and proc.returncode != 0:
        return f"Failed to resolve {host}"
    if not addresses:
        return output[:500]
    lines = [f"nslookup {host}:"]
    lines.append(output.splitlines()[-1] if output.splitlines() else "")
    return "\n".join(lines)



def _do_scan_ip(ip):
    from src.tools.scanner.mdns_cache import get_services
    import src.machines
    src.machines.interface_name = ""
    src.machines.interface_ip = ""
    gateway = get_gateway_ip()
    result = identify_device(ip, gateway_ip=gateway, hostname="")
    ttl = _probe_ttl(ip)
    mds = get_services(ip)
    has_evidence = result != "device unknown" or ttl is not None or bool(mds)
    if not has_evidence:
        return None
    machine = store.add_or_update(ip=ip, method="manual")
    machine.device_type = result
    model = extract_model_for_ip(machine.ip, resolve=True)
    if model:
        machine.model = model
    if result == "Windows machine":
        os_info, domain, server_name = _probe_smb_info(machine.ip)
        if os_info:
            machine.device_type = os_info
            machine.os = os_info
        if domain:
            machine.domain = domain
            domain_db.init_or_update(domain, machine.id, machine.ip, "smb")
            machine_db.save_domain(machine.id, domain, "smb")
        if server_name:
            machine.hostname = server_name
    if result == "Linux device":
        banner = _probe_ssh_banner(machine.ip)
        if banner:
            distro = _identify_linux_distro(banner)
            if distro:
                machine.device_type = distro
                machine.os = distro
    machine_db.save_machine_info(machine)
    return {
        "id": machine.id,
        "ip": machine.ip,
        "device_type": machine.device_type,
        "os": getattr(machine, "os", ""),
        "hostname": getattr(machine, "hostname", ""),
        "domain": getattr(machine, "domain", ""),
        "model": getattr(machine, "model", ""),
        "ttl": ttl,
    }


def _do_bannergrab(ip, port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(3)
    response = b""
    try:
        sock.connect((ip, port))
        sock.settimeout(2)
        while True:
            try:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                response += chunk
            except socket.timeout:
                break
    except (OSError, ConnectionError, socket.timeout):
        return None
    finally:
        sock.close()
    return response.decode(errors="replace").strip()


_TCP_SCAN_PORTS = [
    7, 9, 13, 21, 22, 23, 25, 37, 49, 53, 69, 70, 79, 80, 88, 110, 111,
    113, 119, 123, 135, 137, 138, 139, 143, 161, 162, 179, 199, 389, 443,
    445, 465, 512, 513, 514, 515, 548, 554, 587, 631, 636, 646, 873, 993,
    995, 1025, 1026, 1027, 1080, 1099, 1433, 1434, 1521, 1723, 2049, 2121,
    2222, 2375, 2701, 3128, 3260, 3306, 3389, 3690, 4369, 4444, 4786, 4848,
    5000, 5353, 5432, 5555, 5672, 5800, 5900, 5985, 5986, 6379, 6667, 7001,
    7002, 7777, 8000, 8009, 8080, 8180, 8443, 8888, 9000, 9090, 9200, 9443,
    9999, 11211, 27017, 50070, 61616,
]


def _do_tcp_scan_common(ip):
    from concurrent.futures import ThreadPoolExecutor, as_completed
    open_ports = []
    lock = threading.Lock()
    def _check(p):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex((ip, p))
        sock.close()
        if result == 0:
            with lock:
                open_ports.append(p)
    with ThreadPoolExecutor(max_workers=50) as ex:
        list(ex.map(_check, _TCP_SCAN_PORTS))
    return sorted(open_ports)


_UDP_SCAN_PORTS = [
    7, 9, 11, 13, 17, 19, 37, 42, 49, 53,
    67, 68, 69, 80, 88, 111, 113, 119, 123, 135,
    137, 138, 139, 143, 161, 162, 177, 194, 389, 443,
    445, 464, 500, 512, 514, 520, 546, 554, 587, 631,
    636, 873, 993, 995, 1194, 1434, 1521, 1701, 1723, 1812,
    1900, 2049, 2222, 3128, 3306, 3389, 3478, 4500, 5000, 5060,
    5353, 5432, 5555, 5672, 5900, 5985, 6379, 7000, 7070, 8000,
    8080, 8443, 8888, 9200, 10000, 11211, 27017, 49152,
]


def _do_udp_scan_common(ip):
    from concurrent.futures import ThreadPoolExecutor, as_completed
    open_ports = []
    lock = threading.Lock()
    def _check(p):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(1)
        try:
            sock.sendto(b"", (ip, p))
            sock.recvfrom(1024)
            with lock:
                open_ports.append(p)
        except (socket.timeout, ConnectionRefusedError, OSError):
            pass
        finally:
            sock.close()
    with ThreadPoolExecutor(max_workers=50) as ex:
        list(ex.map(_check, _UDP_SCAN_PORTS))
    return sorted(open_ports)


def _wifi_monitor_running():
    try:
        from src.tools.scanner import wifi_monitor
        return wifi_monitor.is_running()
    except Exception:
        return False


class App(tk.Tk):
    def __init__(self):
        fonts.register_before_tk()
        super().__init__()
        fonts.set_root(self)
        self.title("Elwand - Your AI-Powered Security Workbench")
        self.minsize(800, 600)
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        win_w, win_h = min(1280, int(sw * 0.9)), min(800, int(sh * 0.9))
        self.geometry(
            f"{win_w}x{win_h}+{(sw - win_w) // 2}+{(sh - win_h) // 2}")
        self.state("normal")

        fonts.init(self)
        self.configure(bg="#000000")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        self._pane = tk.PanedWindow(self, orient=tk.VERTICAL, bg="#2d2d2d",
                                     sashwidth=5, sashrelief=tk.FLAT, borderwidth=0)
        self._pane.grid(row=0, column=0, sticky="nsew", padx=2, pady=2)

        self.visualizer = Visualizer(self._pane)
        self._pane.add(self.visualizer, stretch="always")

        elwand_settings.load()
        windowing.init(self)
        console_font = elwand_settings.get("console_font_size", 11)
        self.console = Console(self._pane, initial_font_size=console_font)
        self.console._focus_callback = self._toggle_focus
        self._pane.add(self.console, stretch="always")

        self.after(300, self._set_initial_sash)

        self._passive_scanner = None
        self._active_scanner = None
        self._selected_interface = None
        self._identifying_ips = set()
        self._system_process = None
        self._recorder = None
        self._bruteforce_dlg = None
        self._bruteforce_engine = None
        self._consultor_mode = False
        self._agent_mode = False
        self._closing = False
        self._llm_running = False
        self._agent_stop_event = None
        self._llm_messages = []
        self._llm_request_id = None
        self._llm_session_id = None
        self._llm_project_id = None
        self._silent_mode_cycle = False
        self._last_ctx_hash = None
        self._context_injected = False
        self._last_token_pct = None
        self._total_api_tokens = 0
        self._fuzz_dlg = None
        self._tcpscan_running = False
        self._tcpscan_process = None
        self._udpscan_running = False
        self._port_inspector_running = False
        self._shell_listener = None

        from src.gui.views.nav import set_settings_callback as _nav_set_settings
        from src.gui.views.nav import set_zoom_callback as _nav_set_zoom_cb
        from .dialogs.settings import SettingsDialog
        _nav_set_settings(lambda: SettingsDialog(self))
        _nav_set_zoom_cb(self._on_zoom_changed)

        try:
            from src.llm import models_catalog
            models_catalog.refresh_async()
        except Exception:
            pass

        self._register_views()
        self.visualizer.activate_view("tools")
        self._register_commands()

        view_scale = elwand_settings.get("view_scale", 1.0)
        from src.gui.views.nav import set_initial_zoom as _nav_set_zoom
        _nav_set_zoom(view_scale)

        self.visualizer.winfo_toplevel().update_idletasks()
        self.visualizer._refresh_labels(
            self.visualizer.get_active_view())
        self.visualizer.winfo_toplevel().update_idletasks()

        self.after(0, self._enter_fullscreen)

        load_mdns_cache()
        start_autosave()
        store.load()
        start_machines_autosave(store)
        try:
            from src.machines import credential_db
            credential_db.repair_handshake_hashes()
        except Exception:
            pass

        self.after(500, self._run_init_checks)

        event_bus.start(self, self._process_scanner_events)

        self.protocol("WM_DELETE_WINDOW", self._on_close)

        mode = self._load_session()
        if mode in ("agent", "consultor"):
            self._silent_mode_cycle = True
            try:
                if mode == "agent":
                    self._enter_agent_mode()
                else:
                    self._enter_consultor_mode()
            finally:
                self._silent_mode_cycle = False
            self.console.info(
                f"Session restored ({len(self._llm_messages)} messages)")

        self.bind_all("<Control-f>", self._toggle_focus)
        self.bind_all("<Command-f>",  self._toggle_focus)
        self.bind_all("<F11>", self._toggle_fullscreen)
        self.bind_all("<Command-Control-f>", self._toggle_fullscreen)

    def _run_init_checks(self):
        from .dialogs.init_dialog import InitDialog
        dialog = InitDialog(self)
        self.wait_window(dialog)
        if self._passive_scanner is None or not self._passive_scanner.is_running:
            self._start_passive_scanner()
        if self._shell_listener is None or not self._shell_listener.is_running:
            self._start_shell_listener()

    def _set_initial_sash(self):
        self.update_idletasks()
        h = self.winfo_height()
        if h > 100:
            self._pane.sash_place(0, 0, h * 2 // 3)

    def _start_passive_scanner(self):
        from src.tools.scanner.mdns import _check_permission
        if not _check_permission():
            self.console.error("mDNS passive scanner: permission denied. Run as root or install with CAP_NET_RAW.")
            return
        self._passive_scanner = PassiveMDNSScanner(on_host_callback=self._on_host_discovered)
        self._passive_scanner.start()
        self.console.info("Passive listening mDNS started")

    def _start_wifi_monitor(self):
        from src.tools.scanner import wifi_monitor
        if not wifi_monitor.monitor_supported():
            self.console.info(
                "WiFi scan-only mode (monitor mode not available on this platform)")
            return
        wifi_monitor.start_monitor()

    def _stop_wifi_monitor(self):
        from src.tools.scanner import wifi_monitor
        wifi_monitor.stop_monitor()

    def _start_shell_listener(self):
        port = 443 if self._is_root() else 8443
        self._shell_listener = ShellListener(
            port=port,
            on_new_session=self._on_shell_session,
        )
        self._shell_listener.start()
        self.console.info(f"Reverse shell listener started on port {port}")

    def _on_service_toggle(self, key, enable):
        if key == "mdns":
            if enable:
                if self._passive_scanner is None or not self._passive_scanner.is_running:
                    self._start_passive_scanner()
                    self.console.info("Passive mDNS listener started")
            else:
                if self._passive_scanner and self._passive_scanner.is_running:
                    self._passive_scanner.stop()
                    self.console.info("Passive mDNS listener stopped")
        elif key == "revershell":
            if enable:
                if self._shell_listener is None or not self._shell_listener.is_running:
                    self._start_shell_listener()
            else:
                if self._shell_listener and self._shell_listener.is_running:
                    self._shell_listener.stop()
                    self.console.info("Reverse shell listener stopped")
        elif key.startswith("wifi:"):
            from src.tools.scanner import wifi_monitor
            iface = key.split(":", 1)[1]
            if enable:
                if not wifi_monitor.capture_supported():
                    self.console.info(
                        "WiFi capture not available on this platform "
                        "(Linux: needs a monitor adapter; macOS: needs root "
                        "and tcpdump).")
                    return
                wifi_monitor.enable_iface(iface)
                self.console.info(f"Monitor mode ON on {iface}")
            else:
                wifi_monitor.disable_iface(iface)
                self.console.info(f"Monitor mode OFF on {iface}")

    def _services_state(self):
        from src.tools.scanner import wifi_monitor
        states = {
            "mdns": (self._passive_scanner is not None
                     and self._passive_scanner.is_running),
            "revershell": (self._shell_listener is not None
                           and self._shell_listener.is_running),
        }
        for iface in wifi_monitor.wifi_interfaces():
            states[f"wifi:{iface}"] = wifi_monitor.is_iface_enabled(iface)
        return states

    def _register_views(self):
        wifi_view = WifiView(self.visualizer)
        wifi_view._on_network_click = self._open_wifi_view
        self.visualizer.register_view("wifi", wifi_view)

        net_view = NetworkView(self.visualizer)
        net_view._on_machine_click = self._open_machine_view
        self.visualizer.register_view("machines", net_view)

        domain_view = DomainListView(self.visualizer)
        domain_view._on_domain_click = self._open_domain_view
        self.visualizer.register_view("domains", domain_view)

        evidence_view = EvidenceListView(self.visualizer)
        evidence_view._on_item_click = self._open_evidence_view
        self.visualizer.register_view("evidences", evidence_view)

        cred_view = CredentialListView(self.visualizer)
        cred_view._on_cred_click = self._open_credential_view
        self.visualizer.register_view("credentials", cred_view)

        users_view = UsersView(self.visualizer)
        users_view._on_user_click = self._open_user_view
        self.visualizer.register_view("users", users_view)

        people_view = PeopleView(self.visualizer)
        people_view._on_person_click = self._open_people_view
        self.visualizer.register_view("people", people_view)

        passwords_view = PasswordsView(self.visualizer)
        self.visualizer.register_view("passwords", passwords_view)

        inventory_view = InventoryView(self.visualizer)
        inventory_view._on_item_click = self._on_inventory_click
        self.visualizer.register_view("inventory", inventory_view)

        hash_view = HashListView(self.visualizer)
        hash_view._on_hash_click = self._open_hash_view
        self.visualizer.register_view("hashes", hash_view)

        tools_view = ToolsView(self.visualizer)
        tools_view._on_tool_click = self._on_tool_click
        self.visualizer.register_view("tools", tools_view)

        shell_view = ShellListView(self.visualizer)
        shell_view._on_shell_click = self._open_shell_view
        self.visualizer.register_view("shells", shell_view)

        services_view = ServicesView(self.visualizer)
        services_view._on_toggle = self._on_service_toggle
        services_view._check_state = self._services_state
        self.visualizer.register_view("services", services_view)

        dictionarys_view = DictionarysView(self.visualizer)
        dictionarys_view._on_item_click = self._open_dictionary_view
        self.visualizer.register_view("dictionarys", dictionarys_view)

        rules_view = RulesView(self.visualizer)
        rules_view._on_item_click = self._open_rule_view
        self.visualizer.register_view("rules_view", rules_view)

        pocs_view = PocsView(self.visualizer)
        pocs_view._on_item_click = self._open_poc_view
        self.visualizer.register_view("pocs", pocs_view)

        reports_view = ReportsView(self.visualizer)
        reports_view._on_item_click = self._open_report_view
        reports_view._on_new_click = self._new_report
        self.visualizer.register_view("reports", reports_view)

        handshakes_view = HandshakesView(self.visualizer)
        self.visualizer.register_view("handshakes", handshakes_view)

    def _register_commands(self):
        self.console.set_mode_cycle_callback(self._cycle_mode)
        self.console.register_command("view", self._cmd_view, "Switch or list views")
        self.console.set_subcommands("view", ["list", "wifi", "tools", "inventory", "machine", "domain", "shell", "credential", "hash", "user", "passwords", "people", "evidence", "services", "dictionary", "rule", "poc", "report", "handshake"])
        self.console.register_command("use", self._cmd_use, "Use a tool")
        self.console.set_subcommands("use", ["scanner", "port-inspector", "fuzzer", "webrecorder", "nslookup", "ping", "tcpscan", "udpscan", "bannergrab", "whatweb", "bruteforce", "hashcat", "dicma", "wifioperator"])
        self.console.register_command("connect", self._cmd_connect, "Connect via FTP/SFTP/SSH/WinRM")
        self.console.set_subcommands("connect", ["ftp", "sftp", "ssh", "winrm"])
        self.console.register_command("start", self._cmd_start, "Start listeners")
        self.console.set_subcommands("start", ["shells-listener", "mdns-listener"])
        self.console.register_command("stop", self._cmd_stop, "Stop listeners")
        self.console.set_subcommands("stop", ["shells-listener", "mdns-listener", "scanner", "bruteforce", "fuzzer", "webrecorder", "tcpscan", "udpscan", "whatweb", "port-inspector", "bannergrab", "hashcat"])
        self.console.register_command("delete", self._cmd_delete, "Delete stored data")
        self.console.set_subcommands("delete", ["all", "dbs", "credential", "evidence", "hash", "handshake", "machine", "domain", "user", "password", "shell", "people", "dictionary", "rule", "poc", "report", "inventory", "cache", "wifi"])
        self.console.register_command("add", self._cmd_add, "Add to inventory")
        self.console.set_subcommands("add", ["machine", "domain", "credential", "user", "password", "hash", "people", "dictionary", "rule"])
        self.console.register_command("init", self._cmd_init, "Re-run initialization checks")
        self.console.register_command("settings", self._cmd_settings, "Open settings dialog")
        self.console.register_command("debug", self._cmd_debug, "Debug utilities")
        self.console.set_subcommands("debug", ["ctx_screenshot", "rotate_opencode_headers"])
        self.console.register_command("exit", self._cmd_exit, "Close the application")

        self.console.set_system_handler(self._run_system)
        self.console.set_system_stop_handler(self._stop_system)

        self.console.set_arg2_provider("delete", "credential", self._autocomplete_credential_user)
        self.console.set_arg2_provider("delete", "evidence", self._autocomplete_evidence)
        self.console.set_arg2_provider("delete", "hash", self._autocomplete_hash)
        self.console.set_arg2_provider("delete", "handshake", self._autocomplete_handshakes)
        self.console.set_arg2_provider("delete", "machine", self._autocomplete_store_ip)
        self.console.set_arg2_provider("delete", "domain", self._autocomplete_domain)
        self.console.set_arg2_provider("delete", "user", self._autocomplete_user)
        self.console.set_arg2_provider("delete", "password", self._autocomplete_password)
        self.console.set_arg2_provider("delete", "shell", self._autocomplete_shell)
        self.console.set_arg2_provider("delete", "people", self._autocomplete_people)
        self.console.set_arg2_provider("delete", "dictionary", self._autocomplete_delete_dictionary)
        self.console.set_arg2_provider("delete", "rule", self._autocomplete_delete_rules)
        self.console.set_arg2_provider("delete", "poc", self._autocomplete_delete_pocs)

        self.console.set_arg2_provider("view", "machine", self._autocomplete_store_ip_noall)
        self.console.set_arg2_provider("view", "domain", self._autocomplete_domain_only)
        self.console.set_arg2_provider("view", "shell", self._autocomplete_shell_noall)
        self.console.set_arg2_provider("view", "credential", self._autocomplete_credential_user_noall)
        self.console.set_arg2_provider("view", "user", self._autocomplete_user_noall)
        self.console.set_arg2_provider("view", "hash", self._autocomplete_hash_noall)
        self.console.set_arg2_provider("view", "evidence", self._autocomplete_evidence_only)
        self.console.set_arg2_provider("view", "people", self._autocomplete_people_noall)
        self.console.set_arg2_provider("view", "dictionary", self._autocomplete_dictionary_noall)
        self.console.set_arg2_provider("view", "rule", self._autocomplete_rules_noall)
        self.console.set_arg2_provider("view", "poc", self._autocomplete_pocs_noall)

        self.console.set_arg2_provider("connect", "ftp", self._autocomplete_store_ip_noall)
        self.console.set_arg2_provider("connect", "sftp", self._autocomplete_store_ip_noall)
        self.console.set_arg2_provider("connect", "ssh", self._autocomplete_store_ip_noall)
        self.console.set_arg2_provider("connect", "winrm", self._autocomplete_store_ip_noall)
        self.console.set_arg3_provider("connect", "ftp", self._autocomplete_connect_credential)
        self.console.set_arg3_provider("connect", "sftp", self._autocomplete_connect_credential)
        self.console.set_arg3_provider("connect", "ssh", self._autocomplete_connect_credential)
        self.console.set_arg3_provider("connect", "winrm", self._autocomplete_connect_credential)

        self.console.set_arg2_provider("add", "machine", self._autocomplete_format_ip)
        self.console.set_arg2_provider("add", "domain", self._autocomplete_format_domain)
        self.console.set_arg2_provider("add", "credential", self._autocomplete_user_noall)
        self.console.set_arg2_provider("add", "user", self._autocomplete_format_username)
        self.console.set_arg2_provider("add", "password", self._autocomplete_format_password)
        self.console.set_arg2_provider("add", "hash", self._autocomplete_hash_types)
        self.console.set_arg2_filter_contains("add", "hash")

        self.console.set_arg2_provider("use", "scanner", self._autocomplete_use_scanner)
        self.console.set_arg3_provider("use", "scanner", self._autocomplete_use_scanner_ip)

        self.console.set_arg2_provider("use", "nslookup", self._autocomplete_webrecorder_target)
        self.console.set_arg2_provider("use", "ping", self._autocomplete_webrecorder_target)
        self.console.set_arg2_provider("use", "tcpscan", self._autocomplete_use_tcpscan)
        self.console.set_arg2_provider("use", "udpscan", self._autocomplete_use_udpscan)

        self.console.set_arg2_provider("use", "whatweb", self._autocomplete_use_tcpscan)
        self.console.set_arg3_provider("use", "whatweb", self._autocomplete_port_inspector_ports)

        self.console.set_arg2_provider("use", "bruteforce", self._autocomplete_bruteforce_proto)
        self.console.set_arg3_provider("use", "bruteforce", self._autocomplete_webrecorder_target)
        self.console.set_arg4_provider("use", "bruteforce", self._autocomplete_bruteforce_userlist)
        self.console.set_arg5_provider("use", "bruteforce", self._autocomplete_bruteforce_passlist)

        self.console.set_arg2_provider("use", "fuzzer", self._autocomplete_fuzzer_method)
        self.console.set_arg3_provider("use", "fuzzer", self._autocomplete_webrecorder_target)
        self.console.set_arg4_provider("use", "fuzzer", self._autocomplete_fuzzer_arg4)
        self.console.set_arg5_provider("use", "fuzzer", self._autocomplete_fuzzer_arg5)

        self.console.set_arg2_provider("use", "port-inspector", self._autocomplete_use_port_inspector)
        self.console.set_arg3_provider("use", "port-inspector", self._autocomplete_port_inspector_ports)

        self.console.set_arg2_provider("use", "bannergrab", self._autocomplete_use_tcpscan)
        self.console.set_arg3_provider("use", "bannergrab", self._autocomplete_port_inspector_ports)

        self.console.set_arg2_provider("use", "webrecorder", self._autocomplete_webrecorder_target)
        self.console.set_arg3_provider("use", "webrecorder", self._autocomplete_webrecorder_ports)
        self.console.set_arg4_provider("use", "webrecorder", self._autocomplete_webrecorder_scheme)

        self.console.set_arg2_provider("use", "hashcat", self._autocomplete_hashcat_hash)
        self.console.set_arg3_provider("use", "hashcat", self._autocomplete_hashcat_wordlist)

        self.console.set_arg2_provider("use", "dicma", self._autocomplete_dicma_mode)
        self.console.set_arg3_provider("use", "dicma", self._autocomplete_dicma_arg3)
        self.console.set_arg3_filter_contains("use", "dicma")
        self.console.set_arg4_provider("use", "dicma", self._autocomplete_dicma_arg4)
        self.console.set_arg5_provider("use", "dicma", self._autocomplete_dicma_arg5)
        self.console.set_arg4_filter_contains("use", "dicma")
        self.console.set_arg5_filter_contains("use", "dicma")

        self.console.set_arg3_provider("add", "credential", self._autocomplete_password_noall)
        self.console.set_arg3_provider("add", "hash", self._autocomplete_format_hash)

    @staticmethod
    def _autocomplete_dicma_mode(prefix):
        return ["users", "related", "passwords", "rules"]

    @staticmethod
    def _autocomplete_dicma_arg3(prefix, arg2_value=None):
        if arg2_value == "users":
            return App._autocomplete_dicma_users(prefix)
        elif arg2_value == "related":
            return App._autocomplete_dicma_related(prefix)
        elif arg2_value == "passwords":
            return App._autocomplete_dicma_passwords(prefix)
        elif arg2_value == "rules":
            return App._autocomplete_dicma_rules_dict(prefix)
        return []

    @staticmethod
    def _autocomplete_dicma_arg4(prefix, arg2_value=None):
        if arg2_value == "users":
            return [("<output_name.txt>", "")]
        if arg2_value == "related":
            return [("<examp 30,10,2>", "")]
        if arg2_value in ("passwords", "rules"):
            return ["light", "normal", "full"]
        return []

    @staticmethod
    def _autocomplete_dicma_arg5(prefix, arg2_value=None):
        if arg2_value == "users":
            return []
        if arg2_value == "rules":
            return [("<output_name.rule>", "")]
        return [("<output_name.txt>", "")]

    @staticmethod
    def _autocomplete_dicma_users(prefix):
        results = ["all"]
        from src.machines.people_db import load_people
        for p in load_people():
            full = f"{p.get('first_name','')} {p.get('last_name','')}".strip()
            if full:
                insert = full.replace(" ", "_")
                results.append((insert, insert))
        return results

    @staticmethod
    def _autocomplete_dicma_related(prefix):
        from src.machines.people_db import load_people
        results = [("<custom_word>", "")]
        for p in load_people():
            full = f"{p.get('first_name','')} {p.get('last_name','')}".strip()
            if full:
                insert = full.replace(" ", "_")
                results.append((insert, insert))
        return results

    @staticmethod
    def _autocomplete_dicma_passwords(prefix):
        from src.machines.credential_db import load_passwords
        from src.machines.people_db import load_people
        results = [("<word>", ""),
                   ("all-passwords", "all-passwords"),
                   ("all-interests", "all-interests"),
                   ("all", "all")]
        for pw in load_passwords():
            if pw:
                results.append((pw, pw))
        for p in load_people():
            full = f"{p.get('first_name','')} {p.get('last_name','')}".strip()
            if full:
                insert = full.replace(" ", "_")
                results.append((insert, insert))
        return results

    def _autocomplete_dicma_arg5(self, prefix):
        try:
            full = self.console._entry.get() if hasattr(self.console, '_entry') else ""
            parts = full.split()
            if len(parts) >= 2 and parts[0] == "use" and parts[1] == "dicma":
                if len(parts) >= 3 and parts[2] == "rules":
                    return [("<output_name.rule>", "")]
        except Exception:
            pass
        return [("<output_name.txt>", "")]

    @staticmethod
    def _autocomplete_dicma_rules_dict(prefix):
        from src.elwand_paths import lst_dir
        results = []
        try:
            for fname in sorted(os.listdir(str(lst_dir()))):
                if os.path.isfile(os.path.join(str(lst_dir()), fname)):
                    results.append((fname, fname))
        except OSError:
            pass
        return results

    @staticmethod
    def _autocomplete_delete_rules(prefix):
        from src.elwand_paths import rules_dir
        results = ["all"]
        try:
            for fname in sorted(os.listdir(str(rules_dir()))):
                if os.path.isfile(os.path.join(str(rules_dir()), fname)):
                    results.append((fname, fname))
        except OSError:
            pass
        return results

    @staticmethod
    def _autocomplete_delete_dictionary(prefix):
        from src.elwand_paths import lst_dir
        results = ["all"]
        try:
            for fname in sorted(os.listdir(str(lst_dir()))):
                if os.path.isfile(os.path.join(str(lst_dir()), fname)):
                    results.append((fname, fname))
        except OSError:
            pass
        return results

    @staticmethod
    def _autocomplete_dictionary_noall(prefix):
        from src.elwand_paths import lst_dir
        results = []
        try:
            for fname in sorted(os.listdir(str(lst_dir()))):
                if os.path.isfile(os.path.join(str(lst_dir()), fname)):
                    results.append((fname, fname))
        except OSError:
            pass
        return results

    @staticmethod
    def _autocomplete_rules_noall(prefix):
        from src.elwand_paths import rules_dir
        results = []
        try:
            for fname in sorted(os.listdir(str(rules_dir()))):
                if os.path.isfile(os.path.join(str(rules_dir()), fname)):
                    results.append((fname, fname))
        except OSError:
            pass
        return results

    @staticmethod
    def _autocomplete_delete_pocs(prefix):
        from src.elwand_paths import pocs_dir
        results = ["all"]
        try:
            for fname in sorted(os.listdir(str(pocs_dir()))):
                if os.path.isfile(os.path.join(str(pocs_dir()), fname)):
                    results.append((fname, fname))
        except OSError:
            pass
        return results

    @staticmethod
    def _autocomplete_pocs_noall(prefix):
        from src.elwand_paths import pocs_dir
        results = []
        try:
            for fname in sorted(os.listdir(str(pocs_dir()))):
                if os.path.isfile(os.path.join(str(pocs_dir()), fname)):
                    results.append((fname, fname))
        except OSError:
            pass
        return results

    @staticmethod
    def _autocomplete_store_ip(prefix):
        results = [("all", "all")]
        for m in store.get_all():
            results.append((f"{m.ip}  #{m.id}", m.ip))
        return results

    @staticmethod
    def _autocomplete_store_ip_noall(prefix):
        results = []
        for m in store.get_all():
            results.append((f"{m.ip}  #{m.id}", m.ip))
        return results

    @staticmethod
    def _autocomplete_credential_user(prefix):
        from src.machines.credential_db import load_credentials
        results = ["all"]
        for c in load_credentials():
            u = c.get("username", "")
            if u:
                results.append(u)
        return results

    @staticmethod
    def _autocomplete_connect_credential(prefix, arg2_value=None):
        from src.machines.credential_db import load_credentials
        results = []
        for c in load_credentials():
            u = c.get("username", "")
            if u:
                results.append(u)
        return results

    @staticmethod
    def _autocomplete_format_ip(prefix, arg2_value=None):
        return [("<ip>", "")]

    @staticmethod
    def _autocomplete_format_domain(prefix, arg2_value=None):
        return [("<domain>", "")]

    @staticmethod
    def _autocomplete_format_username(prefix, arg2_value=None):
        return [("<username>", "")]

    @staticmethod
    def _autocomplete_format_password(prefix, arg2_value=None):
        return [("<password>", "")]

    @staticmethod
    def _autocomplete_format_hash(prefix, arg2_value=None):
        return [("<hash>", "")]

    @staticmethod
    def _autocomplete_user_noall(prefix, arg2_value=None):
        from src.machines.credential_db import load_usernames
        return list(load_usernames())

    @staticmethod
    def _autocomplete_password_noall(prefix, arg2_value=None):
        from src.machines.credential_db import load_passwords
        return list(load_passwords())

    @staticmethod
    def _autocomplete_hash_types(prefix):
        import sqlite3
        from src.elwand_paths import hashcat_db
        results = []
        try:
            with sqlite3.connect(str(hashcat_db())) as conn:
                rows = conn.execute(
                    "SELECT \"Hash-Mode\", \"Hash-Name\" FROM DefaultMode ORDER BY \"Hash-Mode\""
                ).fetchall()
            for mode, name in rows:
                if name:
                    results.append((f"{mode}  {name}", str(mode)))
        except (sqlite3.DatabaseError, sqlite3.OperationalError):
            pass
        return results

    @staticmethod
    def _autocomplete_use_scanner(prefix):
        results = [("stop", "stop"), ("ip", "ip"), ("<ip>", "")]
        for iface in interfaces():
            if iface == "lo0":
                continue
            addrs = ifaddresses(iface).get(AF_INET)
            if addrs:
                results.append((iface, iface))
        return results

    @staticmethod
    def _autocomplete_use_scanner_ip(prefix, arg2_value=None):
        if arg2_value != "ip":
            return []
        results = []
        from src.machines import domain_db
        for m in store.get_all():
            results.append((f"{m.ip}  #{m.id}", m.ip))
        for d in domain_db.list_all():
            results.append((d, d))
        return results

    @staticmethod
    def _autocomplete_use_port_inspector(prefix):
        results = [("stop", "stop")]
        for m in store.get_all():
            results.append((f"{m.ip}  #{m.id}", m.ip))
        return results

    @staticmethod
    def _autocomplete_use_tcpscan(prefix):
        results = [("stop", "stop")]
        from src.machines import domain_db
        for m in store.get_all():
            results.append((f"{m.ip}  #{m.id}", m.ip))
        for d in domain_db.list_all():
            results.append((d, d))
        return results

    @staticmethod
    def _autocomplete_use_udpscan(prefix):
        results = [("stop", "stop")]
        from src.machines import domain_db
        for m in store.get_all():
            results.append((f"{m.ip}  #{m.id}", m.ip))
        for d in domain_db.list_all():
            results.append((d, d))
        return results

    @staticmethod
    def _autocomplete_bruteforce_proto(prefix):
        return [("ftp", "ftp"), ("ssh", "ssh"), ("smb", "smb"),
                ("rdp", "rdp"), ("ldap", "ldap"), ("mssql", "mssql"),
                ("mysql", "mysql"), ("pgsql", "pgsql")]

    @staticmethod
    def _autocomplete_bruteforce_userlist(prefix):
        from src.elwand_paths import lst_dir
        results = [("users", "users")]
        try:
            for fname in sorted(os.listdir(str(lst_dir()))):
                if os.path.isfile(os.path.join(str(lst_dir()), fname)):
                    results.append((fname, fname))
        except OSError:
            pass
        return results

    @staticmethod
    def _autocomplete_bruteforce_passlist(prefix):
        from src.elwand_paths import lst_dir
        results = [("passwords", "passwords")]
        try:
            for fname in sorted(os.listdir(str(lst_dir()))):
                if os.path.isfile(os.path.join(str(lst_dir()), fname)):
                    results.append((fname, fname))
        except OSError:
            pass
        return results

    @staticmethod
    def _autocomplete_fuzzer_method(prefix):
        return [("dir", "dir"), ("vhost", "vhost"), ("dns", "dns")]

    def _autocomplete_fuzzer_arg4(self, prefix, arg2_value=None):
        if arg2_value == "dir":
            results = [("<port>", "")]
            raw = self.console.input_var.get().strip()
            parts = raw.split()
            if len(parts) >= 4:
                target = parts[3]
                from src.machines import machine_db as _mdb
                machine = store.get(target)
                if not machine:
                    if target.startswith("#") and target[1:].isdigit():
                        machine = store.get_by_id(int(target[1:]))
                    elif target.isdigit():
                        machine = store.get_by_id(int(target))
                if machine:
                    ports = _mdb.load_tcp_ports(machine.id)
                    for p in ports:
                        results.append((str(p), str(p)))
            return results
        else:
            from src.elwand_paths import lst_dir
            results = []
            try:
                for fname in sorted(os.listdir(str(lst_dir()))):
                    if os.path.isfile(os.path.join(str(lst_dir()), fname)):
                        results.append((fname, fname))
            except OSError:
                pass
            return results

    def _autocomplete_fuzzer_arg5(self, prefix, arg2_value=None):
        if arg2_value == "dir":
            from src.elwand_paths import lst_dir
            results = []
            try:
                for fname in sorted(os.listdir(str(lst_dir()))):
                    if os.path.isfile(os.path.join(str(lst_dir()), fname)):
                        results.append((fname, fname))
            except OSError:
                pass
            return results
        return []

    @staticmethod
    def _hash_choices(include_all=False):
        """Hash autocomplete: '#id  <truncated hash>' label, short token inserted.

        The token inserted into the prompt is ``#<id>:<truncated hash>`` so it
        stays short; command handlers resolve it back to the full hash with
        ``_find_hash``.
        """
        from src.machines.credential_db import load_hashes
        results = []
        if include_all:
            results.append(("all", "all"))
        for h in load_hashes():
            hval = h.get("hash", "") or ""
            hid = h.get("id", "")
            short = hval if len(hval) <= 40 else hval[:40] + "\u2026"
            display = f"#{hid}  {short}" if hid != "" else short
            token = f"#{hid}:{hval[:40]}" if hid != "" else hval
            results.append((display, token))
        return results

    @staticmethod
    def _find_hash(token):
        """Resolve a console hash token to a stored hash row.

        Accepts the full hash, ``#<id>``, ``#<id>:<preview>``, a bare id, or a
        unique hash prefix.
        """
        from src.machines.credential_db import load_hashes
        t = (token or "").strip()
        if not t:
            return None
        rows = load_hashes()
        for h in rows:
            if h.get("hash") == t:
                return h
        if t.startswith("#"):
            id_part = t[1:].split(":", 1)[0]
            if id_part.isdigit():
                for h in rows:
                    if str(h.get("id")) == id_part:
                        return h
        if t.isdigit():
            for h in rows:
                if str(h.get("id")) == t:
                    return h
        cands = [h for h in rows if (h.get("hash") or "").startswith(t)]
        if len(cands) == 1:
            return cands[0]
        return None

    @staticmethod
    def _autocomplete_hashcat_hash(prefix):
        return App._hash_choices()

    @staticmethod
    def _autocomplete_hashcat_wordlist(prefix, arg2_value=None):
        from src.elwand_paths import lst_dir
        results = []
        try:
            for fname in sorted(os.listdir(str(lst_dir()))):
                if os.path.isfile(os.path.join(str(lst_dir()), fname)):
                    results.append((fname, fname))
        except OSError:
            pass
        return results

    @staticmethod
    def _autocomplete_port_inspector_ports(prefix, arg2_value=None):
        results = [("<port>", "")]
        if arg2_value:
            from src.machines import machine_db
            machine = store.get(arg2_value)
            if not machine:
                if arg2_value.startswith("#") and arg2_value[1:].isdigit():
                    machine = store.get_by_id(int(arg2_value[1:]))
                elif arg2_value.isdigit():
                    machine = store.get_by_id(int(arg2_value))
            if machine:
                ports = machine_db.load_tcp_ports(machine.id)
                for p in ports:
                    results.append((str(p), str(p)))
        return results

    @staticmethod
    def _autocomplete_webrecorder_target(prefix, arg2_value=None):
        from src.machines import domain_db
        results = []
        for d in domain_db.list_all():
            results.append((d, d))
        for m in store.get_all():
            results.append((f"{m.ip}  #{m.id}", m.ip))
        return results

    @staticmethod
    def _autocomplete_domain_only(prefix):
        from src.machines import domain_db
        return list(domain_db.list_all())

    @staticmethod
    def _autocomplete_shell_noall(prefix):
        from src.shells import shell_db
        results = []
        for s in shell_db.get_all():
            results.append((f"{s['ip']}  #{s['id']}", s["ip"]))
        return results

    @staticmethod
    def _autocomplete_credential_user_noall(prefix):
        from src.machines.credential_db import load_credentials
        results = []
        for c in load_credentials():
            u = c.get("username", "")
            if u:
                results.append(u)
        return results

    @staticmethod
    def _autocomplete_hash_noall(prefix):
        return App._hash_choices()

    @staticmethod
    def _autocomplete_evidence_only(prefix):
        from src.elwand_paths import evidence_dir
        results = []
        try:
            for name in sorted(os.listdir(str(evidence_dir()))):
                results.append(name)
        except OSError:
            pass
        return results

    @staticmethod
    def _autocomplete_webrecorder_ports(prefix, arg2_value=None):
        results = [("<port>", "")]
        if arg2_value:
            from src.machines import machine_db, domain_db
            machine = store.get(arg2_value)
            if not machine:
                if arg2_value.startswith("#") and arg2_value[1:].isdigit():
                    machine = store.get_by_id(int(arg2_value[1:]))
                elif arg2_value.isdigit():
                    machine = store.get_by_id(int(arg2_value))
            if not machine and domain_db.exists(arg2_value):
                for entry in domain_db.load_domain_machines(arg2_value):
                    machine = store.get(entry.get("machine_ip", ""))
                    if machine:
                        break
            if machine:
                ports = machine_db.load_tcp_ports(machine.id)
                for p in ports:
                    results.append((str(p), str(p)))
        return results

    @staticmethod
    def _autocomplete_webrecorder_scheme(prefix):
        return [("http", "http"), ("https", "https")]

    @staticmethod
    def _autocomplete_domain(prefix):
        from src.machines import domain_db
        results = ["all"]
        results.extend(domain_db.list_all())
        return results

    @staticmethod
    def _autocomplete_user(prefix):
        from src.machines.credential_db import load_usernames
        results = ["all"]
        results.extend(load_usernames())
        return results

    @staticmethod
    def _autocomplete_people(prefix):
        from src.machines.people_db import load_people
        results = ["all"]
        for p in load_people():
            label = f"{p.get('first_name','')} {p.get('last_name','')}".strip()
            if label:
                results.append(label)
        return results

    @staticmethod
    def _autocomplete_people_noall(prefix):
        from src.machines.people_db import load_people
        results = []
        for p in load_people():
            label = f"{p.get('first_name','')} {p.get('last_name','')}".strip()
            if label:
                results.append(label)
        return results

    @staticmethod
    def _autocomplete_password(prefix):
        from src.machines.credential_db import load_passwords
        results = ["all"]
        results.extend(load_passwords())
        return results

    @staticmethod
    def _autocomplete_hash(prefix):
        return App._hash_choices(include_all=True)

    @staticmethod
    def _autocomplete_handshakes(prefix):
        from src.elwand_paths import handshakes_dir
        results = [("all", "all")]
        base = str(handshakes_dir())
        try:
            for f in sorted(os.listdir(base)):
                if f.lower().endswith(".pcap") and os.path.isfile(
                        os.path.join(base, f)):
                    results.append((f, f))
        except OSError:
            pass
        return results

    @staticmethod
    def _autocomplete_evidence(prefix):
        from src.elwand_paths import evidence_dir
        results = ["all"]
        try:
            for name in sorted(os.listdir(str(evidence_dir()))):
                results.append(name)
        except OSError:
            pass
        return results

    @staticmethod
    def _autocomplete_shell(prefix):
        from src.shells import shell_db
        results = [("all", "all")]
        for s in shell_db.get_all():
            results.append((f"{s['ip']}  #{s['id']}", s["ip"]))
        return results

    def _cmd_view(self, args):
        if not args:
            self.console.body("Usage: view <subcommand> or view list")
            return
        sub = args[0].lower()
        rest = args[1:]
        if sub == "list":
            names = self.visualizer.get_view_names()
            if names:
                self.console.title("Available views")
                for n in names:
                    v = self.visualizer.get_view(n)
                    desc = getattr(v, "description", "")
                    self.console.body(f"  {n:<12} {desc}")
            else:
                self.console.warning("No views available.")
        elif sub == "machine":
            if rest:
                self._cmd_view_machine(rest)
            else:
                self.visualizer.activate_view("machines")
        elif sub == "domain":
            if rest:
                self._cmd_view_domain(rest)
            else:
                self.visualizer.activate_view("domains")
        elif sub == "shell":
            if rest:
                self._cmd_view_shell(rest)
            else:
                self.visualizer.activate_view("shells")
        elif sub == "credential":
            if rest:
                self._cmd_view_credential(rest)
            else:
                self.visualizer.activate_view("credentials")
        elif sub == "hash":
            if rest:
                self._cmd_view_hash(rest)
            else:
                self.visualizer.activate_view("hashes")
        elif sub == "user":
            if rest:
                self._cmd_view_user(rest)
            else:
                self.visualizer.activate_view("users")
        elif sub == "evidence":
            if rest:
                self._cmd_view_evidence_name(rest)
            else:
                self.visualizer.activate_view("evidences")
        elif sub in ("wifi", "tools", "passwords", "inventory", "services"):
            self.visualizer.activate_view(sub)
        elif sub == "dictionary":
            if rest:
                self._cmd_view_file(rest, "dictionary")
            else:
                self.visualizer.activate_view("dictionarys")
        elif sub == "rule":
            if rest:
                self._cmd_view_file(rest, "rule")
            else:
                self.visualizer.activate_view("rules_view")
        elif sub == "poc":
            if rest:
                self._cmd_view_file(rest, "poc")
            else:
                self.visualizer.activate_view("pocs")
        elif sub == "report":
            if rest:
                self._open_report_view(rest[0])
            else:
                self.visualizer.activate_view("reports")
        elif sub == "handshake":
            self.visualizer.activate_view("handshakes")
        elif sub == "people":
            if rest:
                self._cmd_view_people(rest)
            else:
                self.visualizer.activate_view("people")
        else:
            self.console.error(f"Unknown view subcommand: {sub}. Use 'view list' to see available views.")

    def _cmd_view_file(self, args, file_type):
        if not args:
            return
        fname = args[0]
        if file_type == "dictionary":
            from src.elwand_paths import lst_dir
            base = str(lst_dir())
            title = f"Dictionary \u2014 {fname}"
        elif file_type == "poc":
            from src.elwand_paths import pocs_dir
            base = str(pocs_dir())
            title = f"POC \u2014 {fname}"
        else:
            from src.elwand_paths import rules_dir
            base = str(rules_dir())
            title = f"Rule \u2014 {fname}"
        path = os.path.join(base, fname)
        if not os.path.isfile(path):
            self.console.warning(f"File not found: {fname}")
            return
        from .views.file_detail import open_file_search
        open_file_search(self, path, title, file_type=file_type)

    def _resolve_target(self, target):
        if re.match(r"^\d+\.\d+\.\d+\.\d+$", target):
            return target, None
        if re.match(r"^\d+$", target):
            mid = int(target)
            for m in store.get_all():
                if m.id == mid:
                    return m.ip, m
        m = store.get(target)
        if m:
            return target, m
        for d in domain_db.list_all():
            if d == target:
                info = domain_db.load_domain_info(d)
                return target, None
        return None, None

    def _resolve_to_ip(self, target):
        ip, machine = self._resolve_target(target)
        if ip and re.match(r"^\d+\.\d+\.\d+\.\d+$", ip):
            return ip
        try:
            info = socket.getaddrinfo(target, None, socket.AF_INET, socket.SOCK_STREAM)
            if info:
                ip = info[0][4][0]
                dom = target
                machine = store.get(ip)
                if not machine:
                    machine = store.add_or_update(ip=ip, method="manual")
                    machine.device_type = "device unknown"
                    machine_db.save_machine_info(machine)
                if not domain_db.exists(dom):
                    domain_db.init_or_update(dom, machine.id, machine.ip, "use")
                self.console.info(f"{dom} -> {ip}")
                return ip
        except Exception:
            pass
        return None

    def _cmd_use(self, args):
        if not args:
            self.console.body("Usage: use <scanner|port-inspector|fuzzer|webrecorder|nslookup|ping|tcpscan|udpscan|bannergrab|whatweb|ftp|dicma|wifioperator> ...")
            return
        sub = args[0].lower()
        rest = args[1:]
        if sub == "scanner":
            self._cmd_use_scanner(rest)
        elif sub == "port-inspector":
            self._cmd_use_port_inspector(rest)
        elif sub == "bannergrab":
            self._cmd_use_bannergrab(rest)
        elif sub == "fuzzer":
            self._cmd_use_fuzzer(rest)
        elif sub == "webrecorder":
            self._cmd_use_recorder(rest)
        elif sub == "nslookup":
            self._cmd_use_nslookup(rest)
        elif sub == "ping":
            self._cmd_use_ping(rest)
        elif sub == "tcpscan":
            self._cmd_use_tcpscan(rest)
        elif sub == "udpscan":
            self._cmd_use_udpscan(rest)
        elif sub == "whatweb":
            self._cmd_use_whatweb(rest)
        elif sub == "bruteforce":
            self._cmd_use_bruteforce(rest)
        elif sub == "hashcat":
            self._cmd_use_hashcat(rest)
        elif sub == "dicma":
            self._cmd_use_dicma(rest)
        elif sub == "wifioperator":
            self._cmd_use_wifioperator(rest)
        else:
            self.console.error(f"Unknown tool: {sub}")

    def _cmd_use_scanner(self, args):
        if not args:
            self._scan_active()
            return
        if args[0].lower() == "stop":
            self._scan_stop()
            return
        if args[0].lower() == "ip":
            if len(args) < 2:
                self.console.body("Usage: use scanner ip <ip|id|domain>")
                return
            target = args[1]
            ip = self._resolve_to_ip(target)
            if not ip:
                self.console.body("Usage: use scanner ip <ip|id|domain>")
                return
            self._scan_ip(ip)
            return
        target = args[0]
        iface = self._resolve_interface(target)
        if iface:
            if self._active_scanner and self._active_scanner.is_running:
                self.console.warning("Active scan is already running.")
                return
            self._selected_interface = iface
            src.machines.interface_name = iface[0]
            src.machines.interface_ip = iface[1]
            try:
                self._active_scanner = ActiveScanner(
                    on_host_callback=self._on_host_discovered,
                    interface_name=iface[0],
                )
                self._active_scanner.start()
                self.console.info("Active scan started")
                self.console.body(
                    f"    Interface: {self._active_scanner.interface_name}  "
                    f"Network: {self._active_scanner.network_cidr}"
                )
            except RuntimeError as e:
                self.console.error(str(e))
            return
        ip = self._resolve_to_ip(target)
        if not ip:
            self.console.body("Usage: use scanner [<iface|ip|id|domain>|stop]")
            return
        self._scan_ip(ip)

    @staticmethod
    def _resolve_interface(name):
        addrs = ifaddresses(name).get(AF_INET)
        if addrs:
            return (name, addrs[0]["addr"], addrs[0]["netmask"])
        return None

    def _cmd_use_port_inspector(self, args):
        if not args:
            self._show_scan_dialog()
            return
        self._cmd_port_inspector(args)

    def _cmd_use_bannergrab(self, args):
        self._cmd_bannergrab(args)

    def _cmd_bannergrab(self, args):
        if not args:
            self.console.body("Usage: bannergrab <ip|id> <port>")
            return
        if len(args) < 2:
            self.console.body("Usage: bannergrab <ip|id> <port>")
            return
        target, port_str = args[0], args[1]
        try:
            port = int(port_str)
        except ValueError:
            self.console.error("Invalid port number")
            return
        machine = None
        if re.match(r"^\d+$", target):
            mid = int(target)
            for m in store.get_all():
                if m.id == mid:
                    machine = m
                    break
        else:
            machine = store.get(target)
        if not machine:
            self.console.warning(f"No machine found for: {target}")
            return
        ip = machine.ip
        threading.Thread(target=self._run_bannergrab, args=(ip, port), daemon=True).start()

    def _run_bannergrab(self, ip, port):
        self.console.after(0, lambda: self.console.info(f"Bannergrab {ip}:{port}..."))
        text = _do_bannergrab(ip, port)
        if text is None:
            self.console.after(0, lambda: self.console.error(f"Bannergrab {ip}:{port} failed"))
        elif not text.strip():
            self.console.after(0, lambda: self.console.warning(f"Bannergrab {ip}:{port}: no response"))
        else:
            self.console.after(0, lambda t=text: self.console.success(f"Bannergrab {ip}:{port}:"))
            for line in text.split("\n")[:20]:
                self.console.after(0, lambda l=line: self.console.body(f"  {l}"))

    def _cmd_use_fuzzer(self, args):
        self._cmd_fuzz(args)

    def _cmd_use_recorder(self, args):
        if not args:
            self._cmd_recorder([])
            return
        if args[0].lower() == "stop":
            self._cmd_recorder(args)
            return

        target = args[0]
        port = None
        scheme = "http"

        for a in args[1:]:
            al = a.lower()
            if al in ("http", "https"):
                scheme = al
            else:
                try:
                    port = int(a)
                except ValueError:
                    pass

        if scheme not in ("http", "https"):
            scheme = "http"

        self._resolve_to_ip(target)

        from src.tools.webrecorder import find_browsers, Recorder
        browsers = find_browsers()
        if not browsers:
            self.console.error("No supported browser found")
            return
        browser_path = list(browsers.keys())[0]

        evidence_name = self._next_project_name()

        url = f"{scheme}://{target}"
        if port:
            url = f"{url}:{port}"

        def on_log(text, color=None):
            c = {"success": "success", "error": "error", "info": "info"}.get(color)
            if c:
                getattr(self.console, c)(text.rstrip())
            else:
                self.console.body(text.rstrip())

        if self._recorder and self._recorder.is_running():
            self.console.warning("A webrecorder is already running.")
            return

        self._recorder = Recorder(url, browser_path, on_log=on_log, evidence_name=evidence_name)
        self._recorder.start()
        self.console.info(f"Recorder started: {url}  (evidence: {evidence_name})")

    @staticmethod
    def _next_project_name():
        from src.elwand_paths import evidence_dir
        for i in range(1, 100):
            name = f"project_{i:02d}"
            if not os.path.isdir(os.path.join(str(evidence_dir()), name)):
                return name
        return "project_01"

    def _cmd_use_nslookup(self, args):
        if not args:
            self.console.body("Usage: use nslookup <ip|id|domain>")
            return
        self._cmd_nslookup(args)

    def _cmd_use_ping(self, args):
        if not args:
            self.console.body("Usage: use ping <ip|id|domain>")
            return
        self._cmd_ping(args)

    def _cmd_use_tcpscan(self, args):
        self._cmd_tcpscan(args)

    def _cmd_use_udpscan(self, args):
        self._cmd_udpscan(args)

    def _cmd_use_whatweb(self, args):
        self._cmd_whatweb(args)

    def _cmd_use_bruteforce(self, args):
        from .dialogs.bruteforce import BruteforceDialog
        from src.tools.bruteforce import BruteForceEngine
        protos = ["ftp", "ssh", "smb", "rdp", "ldap", "mssql", "mysql", "pgsql"]
        ports = {"ftp": 21, "ssh": 22, "smb": 445, "rdp": 3389, "ldap": 389,
                 "mssql": 1433, "mysql": 3306, "pgsql": 5432}
        if not args:
            self._bruteforce_dlg = BruteforceDialog(self)
            return
        if args[0].lower() == "stop":
            if self._bruteforce_engine:
                self._bruteforce_engine.stop()
                self._bruteforce_engine = None
            if self._bruteforce_dlg:
                self._bruteforce_dlg._stop()
            self.console.info("Bruteforce stopped")
            return
        proto = args[0].lower()
        if proto not in protos:
            self.console.body("Usage: use bruteforce [ftp|ssh|smb|rdp|ldap|mssql|mysql|pgsql] [ip|id|domain]")
            return
        if len(args) < 2:
            dlg = BruteforceDialog(self)
            self._bruteforce_dlg = dlg
            dlg.select_tab(proto)
            return
        target = args[1]
        ip = self._resolve_to_ip(target)
        if not ip:
            self.console.warning(f"No machine found for: {target}")
            return

        from src.machines.credential_db import load_users, load_passwords
        from src.elwand_paths import lst_dir

        userlist = None
        users = None
        if len(args) > 2 and args[2].lower() != "users":
            path = os.path.join(str(lst_dir()), args[2])
            if os.path.isfile(path):
                userlist = path
        if not userlist:
            users = load_usernames()

        passlist = None
        passwords = None
        if len(args) > 3 and args[3].lower() != "passwords":
            path = os.path.join(str(lst_dir()), args[3])
            if os.path.isfile(path):
                passlist = path
        if not passlist:
            passwords = load_passwords()

        if not users and not userlist:
            self.console.warning("No users available")
            return

        def on_result(text, color=None):
            stripped = text.strip()
            if stripped.startswith("[+] "):
                stripped = stripped[4:]
            elif stripped.startswith("[*] "):
                stripped = stripped[4:]
            elif stripped.startswith("[!] "):
                stripped = stripped[4:]
            c = {"success": "success", "error": "error", "info": "info"}.get(color)
            if c:
                getattr(self.console, c)(stripped.rstrip())
            else:
                self.console.body(stripped.rstrip())
        def on_found(p, tgt, port, user, pwd):
            from src.machines.credential_db import save_credential, save_user, load_credentials, load_users
            for c in load_credentials():
                if c.get("username") == user and c.get("password") == pwd:
                    return
            machine = store.get(tgt)
            dom = machine.domain if machine else ""
            if not dom:
                for u in load_users():
                    if u["username"] == user:
                        dom = u.get("domain", "")
                        break
            save_credential(user, pwd, domain=dom, password_origin=f"{p} bruteforce")
            save_user(user)

        user_desc = userlist or f"{len(users)} from inventory" if users else "none"
        pass_desc = passlist or f"{len(passwords)} from inventory" if passwords else "none"
        self.console.info(f"Starting {proto.upper()} brute force against {ip}:{ports[proto]}...")
        self.console.info(f"Users: {user_desc}  Passwords: {pass_desc}")

        engine = BruteForceEngine(
            target=ip, port=ports[proto], protocol=proto,
            userlist=userlist, passlist=passlist,
            users=users, passwords=passwords,
            on_result=on_result,
            on_found=on_found,
        )
        self._bruteforce_engine = engine
        engine.start()

    def _cmd_use_hashcat(self, args):
        from .dialogs.hashcat import HashcatDialog
        if not args:
            HashcatDialog(self)
            return
        if args[0].lower() == "stop":
            if hasattr(self, "_hashcat_engine") and self._hashcat_engine:
                self._hashcat_engine.stop()
                self.console.info("Hashcat stopped.")
            else:
                self.console.info("No hashcat engine running.")
            return

        hash_token = args[0]
        wordlist_name = args[1] if len(args) > 1 else None
        if not wordlist_name:
            self.console.body(
                "Usage: use hashcat <hash> <wordlist>\n"
                "       wordlists from lst/ directory"
            )
            return

        from src.elwand_paths import hashcat_db, lst_dir

        h = App._find_hash(hash_token)
        if not h:
            self.console.error(
                "Hash not found in inventory. Add it first via GUI or "
                "'add hash'.")
            return
        hash_val = h.get("hash", "")
        htype = h.get("type", "")
        mode = h.get("hascat_mode", "")

        if not mode and htype:
            try:
                import sqlite3
                conn = sqlite3.connect(str(hashcat_db()))
                row = conn.execute(
                    'SELECT "Hash-Mode" FROM DefaultMode WHERE "Hash-Name" = ?',
                    (htype,)
                ).fetchone()
                conn.close()
                if row and row[0] and row[0] != -1:
                    mode = str(row[0])
            except Exception:
                pass

        if not mode:
            self.console.error(
                f"Could not determine hashcat mode for hash. "
                f"Add the hash first via GUI or 'add hash'."
            )
            return

        wl_path = os.path.join(str(lst_dir()), wordlist_name)
        if not os.path.isfile(wl_path):
            self.console.error(f"Wordlist not found: {wl_path}")
            return

        self._hashcat_console_cracked = []

        from .dialogs.hashcat import _fmt_int, _fmt_hms, _fmt_speed

        def status_text(st):
            parts = [f"hashcat: {st['state'].capitalize()}"]
            cur, end = st["progress"]
            if end > 0:
                pct = int(cur * 100 / end)
                parts.append(f"{_fmt_int(cur)}/{_fmt_int(end)} ({pct}%)")
            if st["speed"]:
                parts.append(_fmt_speed(st["speed"]))
            if st["eta"]:
                parts.append(f"ETA ~{_fmt_hms(st['eta'])}")
            elif st["state"] == "running":
                parts.append("ETA computing\u2026")
            if st["recovered"][1]:
                parts.append(f"Recovered {st['recovered'][0]}/{st['recovered'][1]}")
            return "   ".join(parts)

        def on_output(text, color=None):
            stripped = text.strip()
            if not stripped:
                return
            low = stripped.lower()
            if color == "error" or any(
                    k in low for k in ("error", "warning", "failed",
                                       "denied", "not found", "no devices")):
                self._safe_after(self.console.warning, stripped)

        running_announced = {"v": False}

        def on_status(st):
            if st["state"] == "running" and not running_announced["v"]:
                running_announced["v"] = True
                if st["eta"]:
                    line = f"Running hashcat    ETA ~{_fmt_hms(st['eta'])}"
                else:
                    line = "Running hashcat    ETA computing\u2026"
                self._safe_after(self.console.info, line)
            self._safe_after(self.console.live_status, status_text(st))

        def on_cracked(hash_val, plain):
            self._hashcat_console_cracked.append(plain)
            from src.machines.credential_db import save_password
            save_password(plain)
            self._safe_after(self.console.success,
                             f"Cracked: {plain}  (saved to inventory)")

        def on_done(cracked):
            self._hashcat_engine = None
            self._safe_after(self.console.clear_live_status)
            if cracked:
                self._safe_after(
                    self.console.success,
                    f"Hashcat done. {len(cracked)} password(s) cracked.")
            else:
                self._safe_after(self.console.info,
                                 "Hashcat done. No passwords found.")

        from src.tools.hashcat import HashcatEngine
        self.console.info(
            f"hashcat -m {mode} "
            f"'{hash_val}' {wordlist_name}"
        )
        self.console.info("Preparing hashcat\u2026")

        engine = HashcatEngine(
            mode=mode,
            hash_value=hash_val,
            wordlist=wl_path,
            on_output=on_output,
            on_status=on_status,
            on_cracked=on_cracked,
            on_done=on_done,
        )
        self._hashcat_engine = engine
        engine.start()

    def _cmd_use_wifioperator(self, args):
        from .dialogs.wifi_operator import WifiOperatorDialog
        WifiOperatorDialog(self)

    def _cmd_use_dicma(self, args):
        from .dialogs.dicma import DicmaDialog
        from src.machines.people_db import load_people
        import threading

        if not args:
            DicmaDialog(self)
            return

        mode = args[0].lower() if args else ""
        uname = lambda n: n.replace("_", " ") if "_" in n else n

        if mode == "users":
            if len(args) < 2:
                DicmaDialog(self, active_tab=0)
                return
            target = uname(args[1])
            out_file = args[2] if len(args) > 2 else "dicma_users.txt"
            names = []
            if target == "all":
                for p in load_people():
                    full = f"{p['first_name']} {p['last_name']}".strip()
                    if full:
                        names.append(full)
            else:
                names.append(target)
            if not names:
                self.console.warning("No names found.")
                return
            self.console.info(f"Dicma users: {len(names)} name(s) → {out_file}")
            self._run_dicma_users(names, out_file, light=False)

        elif mode == "related":
            if len(args) < 2:
                DicmaDialog(self, active_tab=1)
                return
            target = uname(args[1])
            n_str = args[2] if len(args) > 2 else "50"
            out_file = args[3] if len(args) > 3 else "dicma_related.txt"

            words = []
            if target == "<custom_word>":
                self.console.warning("Use the dialog for custom words.")
                DicmaDialog(self, active_tab=1)
                return
            for p in load_people():
                full = f"{p['first_name']} {p['last_name']}".strip()
                if full == target:
                    raw = (p.get("interests") or "").strip()
                    if raw:
                        for part in raw.replace(",", " ").replace(";", " ").split():
                            part = part.strip().lower()
                            if part and len(part) >= 2:
                                words.append(part)
                    break
            if not words:
                self.console.warning(f"No interests found for: {target}")
                return
            try:
                parts = [int(x.strip()) for x in n_str.split(",")]
                n1 = parts[0] if len(parts) > 0 else 50
                n2 = parts[1] if len(parts) > 1 else 0
                n3 = parts[2] if len(parts) > 2 else 0
            except ValueError:
                self.console.error(f"Invalid n format: {n_str}. Use e.g. 30,10,3")
                return
            self.console.info(f"Dicma related: {len(words)} word(s) n1={n1} n2={n2} n3={n3} → {out_file}")
            self._run_dicma_related(words, out_file, n1, n2, n3)

        elif mode == "passwords":
            if len(args) < 2:
                DicmaDialog(self, active_tab=2)
                return
            target = args[1]
            pwd_mode = (args[2] if len(args) > 2 else "normal").lower()
            out_file = args[3] if len(args) > 3 else "dicma_passwords.txt"

            words = []
            if target == "all-passwords":
                from src.machines.credential_db import load_passwords
                words = [p for p in load_passwords() if p]
            elif target == "all-interests":
                for p in load_people():
                    raw = (p.get("interests") or "").strip()
                    if raw:
                        for part in raw.replace(",", " ").replace(";", " ").split():
                            part = part.strip().lower()
                            if part and len(part) >= 2:
                                words.append(part)
                words = list(set(words))
            elif target == "all":
                from src.machines.credential_db import load_passwords
                words = [p for p in load_passwords() if p]
                for p in load_people():
                    raw = (p.get("interests") or "").strip()
                    if raw:
                        for part in raw.replace(",", " ").replace(";", " ").split():
                            part = part.strip().lower()
                            if part and len(part) >= 2:
                                words.append(part)
                words = list(set(words))
            else:
                target_uname = uname(target)
                for p in load_people():
                    full = f"{p['first_name']} {p['last_name']}".strip()
                    if full == target_uname:
                        raw = (p.get("interests") or "").strip()
                        if raw:
                            for part in raw.replace(",", " ").replace(";", " ").split():
                                part = part.strip().lower()
                                if part and len(part) >= 2:
                                    words.append(part)
                        break
                if not words:
                    words.append(target)
            if not words:
                self.console.warning("No words found.")
                return
            light = pwd_mode == "light"
            full = pwd_mode == "full"
            mode_label = pwd_mode
            self.console.info(f"Dicma passwords: {len(words)} word(s) mode={mode_label} → {out_file}")
            self._run_dicma_passwords(words, out_file, light=light, full=full)

        elif mode == "rules":
            if len(args) < 2:
                DicmaDialog(self, active_tab=3)
                return
            dict_file = args[1]
            rules_mode = (args[2] if len(args) > 2 else "normal").lower()
            out_file = args[3] if len(args) > 3 else "dicma_rules.rule"

            self.console.info(f"Dicma rules: dict={dict_file} mode={rules_mode} → {out_file}")
            self._run_dicma_rules(dict_file, out_file, light=(rules_mode == "light"), full=(rules_mode == "full"))

        else:
            self.console.error(f"Unknown dicma mode: {mode}. Use users/related/passwords/rules.")

    def _run_dicma_users(self, names, out_file, light=False):
        from src.elwand_paths import lst_dir
        out_path = os.path.join(str(lst_dir()), out_file)
        self._run_dicma_async(lambda: self._dicma_users_thread(names, out_path, light))

    def _dicma_users_thread(self, names, out_path, light):
        from src.tools.dicma import engine as dicma
        dicma.LIGHT_MODE = light
        dicma.OUTPUT_FILE_BULEAN = True
        dicma.VERBOSE = False
        names_str = ", ".join(names)
        dicma.process_input_user(names_str, out_path)
        self.console.after(0, lambda: self.console.success(
            f"Users dictionary saved to: {out_path}"))

    def _run_dicma_related(self, words, out_file, n1, n2, n3):
        from src.elwand_paths import lst_dir
        out_path = os.path.join(str(lst_dir()), out_file)
        self._run_dicma_async(lambda: self._dicma_related_thread(words, out_path, n1, n2, n3))

    def _dicma_related_thread(self, words, out_path, n1, n2, n3):
        from src.llm.config import load, get_provider, get_active_model
        from src.tools.dicma import engine as dicma
        config = load()
        provider = get_provider(config)
        model = get_active_model(config)
        api_key = provider.get("api_key", "")
        base_url = provider.get("base_url", "")
        if not api_key or not base_url or not model:
            self.console.after(0, lambda: self.console.error(
                "No LLM config found. Configure in Settings → Models."))
            return
        from openai import OpenAI
        client = OpenAI(api_key=api_key, base_url=base_url)
        expanded = dicma.ml_expand_words(client, model, words, n1, n2, n3)
        result = [w for w in expanded if w not in set(words)]
        dicma.save_list_to_file(result, out_path)
        self.console.after(0, lambda: self.console.success(
            f"Related words ({len(result)}) saved to: {out_path}"))

    def _run_dicma_passwords(self, words, out_file, light=False, full=False):
        from src.elwand_paths import lst_dir
        out_path = os.path.join(str(lst_dir()), out_file)
        self._run_dicma_async(lambda: self._dicma_passwords_thread(words, out_path, light, full))

    def _dicma_passwords_thread(self, words, out_path, light, full):
        from src.tools.dicma import engine as dicma
        dicma.LIGHT_MODE = light
        dicma.FULL_MODE = full
        dicma.OUTPUT_FILE_BULEAN = True
        dicma.VERBOSE = False
        dicma._NO_MULTIPROC = True
        dicma.process_passwd(words, out_path)
        self.console.after(0, lambda: self.console.success(
            f"Passwords dictionary saved to: {out_path}"))

    def _run_dicma_rules(self, dict_file, out_file, light=False, full=False):
        from src.elwand_paths import lst_dir, rules_dir
        out_path = os.path.join(str(rules_dir()), out_file)
        self._run_dicma_async(lambda: self._dicma_rules_thread(dict_file, out_path, light, full))

    def _dicma_rules_thread(self, dict_file, out_path, light, full):
        from src.tools.dicma import engine as dicma
        import os as _os
        if dict_file and _os.path.isfile(dict_file):
            suffixes, prefixes, numbers, symbols = dicma.extract_patterns(dict_file)
            all_suf = list(dict.fromkeys(suffixes + numbers + symbols))
            all_pre = list(dict.fromkeys(prefixes + numbers + symbols))
        else:
            all_suf = list(dict.fromkeys(
                dicma.BASIC_SUFIXS + dicma.NUMERIC_PATTERNS + dicma.SYMBOLIC_PATTERNS))
            all_pre = list(dict.fromkeys(
                dicma.BASIC_PREFIXS + dicma.NUMERIC_PATTERNS + dicma.SYMBOLIC_PATTERNS))
        rules = dicma.generate_rules(all_suf, all_pre, light=light, full=full)
        dicma.save_list_to_file(rules, out_path)
        self.console.after(0, lambda: self.console.success(
            f"{len(rules)} rules saved to: {out_path}"))

    def _run_dicma_async(self, fn):
        t = threading.Thread(target=fn, daemon=True)
        t.start()

    def _cmd_connect(self, args):
        if not args:
            self.console.body("Usage: connect <ftp|sftp|ssh|winrm> ...")
            return
        sub = args[0].lower()
        rest = args[1:]
        if sub == "ftp":
            self._cmd_connect_ftp(rest)
        elif sub == "sftp":
            self._cmd_connect_sftp(rest)
        elif sub == "ssh":
            self._cmd_connect_ssh(rest)
        elif sub == "winrm":
            self._cmd_connect_winrm(rest)
        else:
            self.console.error(f"Unknown protocol: {sub}")

    def _cmd_connect_ftp(self, args):
        from .dialogs.remote_access import RemoteAccessDialog
        if not args:
            dlg = RemoteAccessDialog(self)
            dlg._notebook.select(0)
            self.visualizer.activate_view("shells")
            return
        target = args[0]
        ip = self._resolve_target_ip(target)
        if not ip:
            self.console.body("Usage: connect ftp <ip|id> [credential] [port]")
            return
        port = 21
        cred_user = "anonymous"
        cred_pass = ""
        cred_idx = 1
        if len(args) >= 2 and args[1] != "anonymous":
            cred_user = args[1]
            cred_idx = 2
        elif len(args) >= 2:
            cred_idx = 2
        if len(args) > cred_idx:
            try:
                port = int(args[cred_idx])
                if port < 1 or port > 65535:
                    self.console.body("Usage: connect ftp <ip|id> [credential] [port]")
                    return
            except ValueError:
                self.console.body("Usage: connect ftp <ip|id> [credential] [port]")
                return
        if cred_user != "anonymous":
            found = False
            from src.machines import credential_db
            for c in credential_db.load_credentials():
                if c.get("username") == cred_user:
                    cred_pass = c.get("password") or ""
                    found = True
                    break
            if not found:
                self.console.warning(f"No credential found for: {cred_user}")
                return
        self.console.info(f"Connecting FTP to {ip}:{port}...")
        threading.Thread(target=self._run_ftp_connect, args=(ip, port, cred_user, cred_pass), daemon=True).start()
        self.visualizer.activate_view("shells")

    def _cmd_connect_sftp(self, args):
        from .dialogs.remote_access import RemoteAccessDialog
        if not args:
            dlg = RemoteAccessDialog(self)
            dlg._notebook.select(0)
            dlg._ftp_proto.set("sftp")
            self.visualizer.activate_view("shells")
            return
        target = args[0]
        ip = self._resolve_target_ip(target)
        if not ip:
            self.console.body("Usage: connect sftp <ip|id> [credential] [port]")
            return
        port = 22
        cred_user = "anonymous"
        cred_pass = ""
        cred_idx = 1
        if len(args) >= 2 and args[1] != "anonymous":
            cred_user = args[1]
            cred_idx = 2
        elif len(args) >= 2:
            cred_idx = 2
        if len(args) > cred_idx:
            try:
                port = int(args[cred_idx])
                if port < 1 or port > 65535:
                    self.console.body("Usage: connect sftp <ip|id> [credential] [port]")
                    return
            except ValueError:
                self.console.body("Usage: connect sftp <ip|id> [credential] [port]")
                return
        if cred_user != "anonymous":
            found = False
            from src.machines import credential_db
            for c in credential_db.load_credentials():
                if c.get("username") == cred_user:
                    cred_pass = c.get("password") or ""
                    found = True
                    break
            if not found:
                self.console.warning(f"No credential found for: {cred_user}")
                return
        self.console.info(f"Connecting SFTP to {ip}:{port}...")
        from src.shells.sftp_shell import SFTPConnectionThread
        def on_connected(sid):
            self.console.success(f"SFTP session #{sid} to {ip}:{port}")
        def on_error(msg):
            self.console.error(f"SFTP failed: {msg}")
        t = SFTPConnectionThread(ip, port, cred_user, cred_pass, on_connected=on_connected, on_error=on_error)
        t.start()
        self.visualizer.activate_view("shells")

    def _cmd_connect_ssh(self, args):
        from .dialogs.remote_access import RemoteAccessDialog
        if not args:
            dlg = RemoteAccessDialog(self)
            dlg._notebook.select(1)
            self.visualizer.activate_view("shells")
            return
        target = args[0]
        ip = self._resolve_target_ip(target)
        if not ip:
            self.console.body("Usage: connect ssh <ip|id> <credential> [port]")
            return
        if len(args) < 2:
            self.console.body("Usage: connect ssh <ip|id> <credential> [port]")
            return
        cred_user = args[1]
        port = 22
        if len(args) >= 3:
            try:
                port = int(args[2])
                if port < 1 or port > 65535:
                    self.console.body("Usage: connect ssh <ip|id> <credential> [port]")
                    return
            except ValueError:
                self.console.body("Usage: connect ssh <ip|id> <credential> [port]")
                return
        cred_pass = ""
        from src.machines import credential_db
        for c in credential_db.load_credentials():
            if c.get("username") == cred_user:
                cred_pass = c.get("password") or ""
                break
        else:
            self.console.warning(f"No credential found for: {cred_user}")
            return
        self.console.info(f"Connecting SSH to {ip}:{port}...")
        from src.shells.ssh_shell import SSHConnectionThread
        def on_connected(sid):
            self.console.success(f"SSH session #{sid} to {ip}:{port}")
        def on_error(msg):
            self.console.error(f"SSH failed: {msg}")
        t = SSHConnectionThread(ip, port, cred_user, cred_pass, on_connected=on_connected, on_error=on_error)
        t.start()
        self.visualizer.activate_view("shells")

    def _cmd_connect_winrm(self, args):
        from .dialogs.remote_access import RemoteAccessDialog
        if not args:
            dlg = RemoteAccessDialog(self)
            dlg._notebook.select(2)
            self.visualizer.activate_view("shells")
            return
        target = args[0]
        ip = self._resolve_target_ip(target)
        if not ip:
            self.console.body("Usage: connect winrm <ip|id> <credential> [port]")
            return
        if len(args) < 2:
            self.console.body("Usage: connect winrm <ip|id> <credential> [port]")
            return
        cred_user = args[1]
        port = 5985
        if len(args) >= 3:
            try:
                port = int(args[2])
                if port < 1 or port > 65535:
                    self.console.body("Usage: connect winrm <ip|id> <credential> [port]")
                    return
            except ValueError:
                self.console.body("Usage: connect winrm <ip|id> <credential> [port]")
                return
        cred_pass = ""
        cred_hash = ""
        from src.machines import credential_db
        for c in credential_db.load_credentials():
            if c.get("username") == cred_user:
                cred_pass = c.get("password") or ""
                cred_hash = c.get("hash_nt") or ""
                break
        else:
            self.console.warning(f"No credential found for: {cred_user}")
            return
        self.console.info(f"Connecting WinRM to {ip}:{port}...")
        from src.shells.winrm_shell import WinRMConnectionThread
        def on_connected(sid):
            self.console.success(f"WinRM session #{sid} to {ip}:{port}")
        def on_error(msg):
            self.console.error(f"WinRM failed: {msg}")
        t = WinRMConnectionThread(ip, port, cred_user, cred_pass, hash_nt=cred_hash, on_connected=on_connected, on_error=on_error)
        t.start()
        self.visualizer.activate_view("shells")

    def _resolve_target_ip(self, target):
        if re.match(r"^\d+\.\d+\.\d+\.\d+$", target):
            return target
        if re.match(r"^\d+$", target):
            mid = int(target)
            for m in store.get_all():
                if m.id == mid:
                    return m.ip
        return None

    def _cmd_view_machine(self, args):
        if not args:
            self.console.body("Usage: view machine <id|ip>")
            return
        target = args[0]
        machine = store.get(target)
        if not machine and target.isdigit():
            mid = int(target)
            for m in store.get_all():
                if m.id == mid:
                    machine = m
                    break
        if not machine:
            self.console.warning(f"No machine found for: {target}")
            return
        view_name = f"machine_{machine.id}"
        if view_name not in self.visualizer.get_view_names():
            from .views import MachineDetailView
            machine_view = MachineDetailView(self.visualizer, machine)
            machine_view._on_back_click = lambda: self.visualizer.activate_view("machines")
            machine_view._on_domain_click = self._open_domain_view
            self.visualizer.register_view(view_name, machine_view)
        self.visualizer.activate_view(view_name)

    def _cmd_view_domain(self, args):
        if not args:
            self.console.body("Usage: view domain <domain>")
            return
        domain = args[0]
        if not domain_db.exists(domain):
            try:
                info = socket.getaddrinfo(domain, None, socket.AF_INET, socket.SOCK_STREAM)
                ip = info[0][4][0] if info else None
            except Exception:
                ip = None
            if ip:
                machine = store.get(ip)
                if not machine:
                    machine = store.add_or_update(ip=ip, method="manual")
                    machine.device_type = "device unknown"
                    machine_db.save_machine_info(machine)
                domain_db.init_or_update(domain, machine.id, machine.ip, "view")
            else:
                domain_db.init_or_update(domain, 0, "", "view")
        view_name = f"domain_{domain}"
        if view_name not in self.visualizer.get_view_names():
            from .views import DomainDetailView
            detail_view = DomainDetailView(self.visualizer, domain)
            detail_view._on_back_click = lambda: self.visualizer.activate_view("domains")
            detail_view._on_subdomain_click = self._open_domain_view
            detail_view._on_machine_click = self._open_machine_view_by_ip
            self.visualizer.register_view(view_name, detail_view)
        self.visualizer.activate_view(view_name)

    def _open_machine_view(self, machine):
        self._cmd_view_machine([str(machine.id)])

    def _open_machine_view_by_ip(self, ip):
        machine = store.get(ip)
        if machine:
            self._cmd_view_machine([str(machine.id)])
        else:
            self._cmd_view_machine([ip])

    def _cmd_view_shell(self, args):
        if not args:
            self.console.body("Usage: view shell <id|ip>")
            return
        target = args[0]
        session = None
        for s in shell_db.get_all():
            if s["ip"] == target:
                session = s
                break
        if not session and target.isdigit():
            session = shell_db.get_session(int(target))
        if not session:
            self.console.warning(f"No shell found for: {target}")
            return
        self._open_shell_view(session["id"])

    def _cmd_view_credential(self, args):
        if not args:
            self.console.body("Usage: view credential <username>")
            return
        from src.machines.credential_db import load_credentials
        username = args[0]
        for c in load_credentials():
            if c["username"] == username:
                self._open_credential_view(c["id"])
                return
        self.console.warning(f"No credential found for: {username}")

    def _cmd_view_hash(self, args):
        if not args:
            self.console.body("Usage: view hash <hash|id>")
            return
        h = App._find_hash(args[0])
        if not h:
            self.console.warning(f"No hash found matching: {args[0]}")
            return
        self._open_hash_view(h["id"])

    def _cmd_view_user(self, args):
        if not args:
            self.visualizer.activate_view("users")
            return
        self._open_user_view(args[0])

    def _cmd_view_people(self, args):
        if not args:
            self.visualizer.activate_view("people")
            return
        from src.machines.people_db import load_people
        target = " ".join(args).strip().lower()
        for p in load_people():
            label = f"{p.get('first_name','')} {p.get('last_name','')}".strip().lower()
            if label == target:
                self._open_people_view(p["id"])
                return
        self.console.warning(f"No person found for: {target}")

    def _cmd_view_evidence_name(self, args):
        if not args:
            self.console.body("Usage: view evidence <name>")
            return
        self._open_evidence_view(args[0])

    def _open_evidence_view(self, name):
        view_name = f"evidence_{name}"
        if view_name not in self.visualizer.get_view_names():
            from .views import EvidenceDetailView
            detail_view = EvidenceDetailView(self.visualizer, name)
            detail_view._on_back_click = lambda: self.visualizer.activate_view("evidences")
            self.visualizer.register_view(view_name, detail_view)
        self.visualizer.activate_view(view_name)

    def _open_credential_view(self, cred_id):
        view_name = f"credential_{cred_id}"
        if view_name not in self.visualizer.get_view_names():
            from .views import CredentialDetailView
            detail_view = CredentialDetailView(self.visualizer, cred_id)
            detail_view._on_back_click = lambda: self.visualizer.activate_view("credentials")
            self.visualizer.register_view(view_name, detail_view)
        self.visualizer.activate_view(view_name)

    def _open_hash_view(self, hash_id):
        view_name = f"hash_{hash_id}"
        if view_name not in self.visualizer.get_view_names():
            from .views import HashDetailView
            detail_view = HashDetailView(self.visualizer, hash_id)
            detail_view._on_back_click = lambda: self.visualizer.activate_view("hashes")
            self.visualizer.register_view(view_name, detail_view)
        self.visualizer.activate_view(view_name)

    def _open_dictionary_view(self, fname):
        from src.elwand_paths import lst_dir
        from .views.file_detail import open_file_search
        path = os.path.join(str(lst_dir()), fname)
        if not os.path.isfile(path):
            return
        open_file_search(self, path, f"Dictionary \u2014 {fname}")

    def _open_rule_view(self, fname):
        from src.elwand_paths import rules_dir
        from .views.file_detail import open_file_search
        path = os.path.join(str(rules_dir()), fname)
        if not os.path.isfile(path):
            return
        open_file_search(self, path, f"Rule \u2014 {fname}")

    def _open_poc_view(self, fname):
        from src.elwand_paths import pocs_dir
        from .views.file_detail import open_file_search
        path = os.path.join(str(pocs_dir()), fname)
        if not os.path.isfile(path):
            return
        open_file_search(self, path, f"POC \u2014 {fname}", file_type="poc")

    def _open_report_view(self, fname):
        from src.elwand_paths import reports_dir
        path = os.path.join(str(reports_dir()), fname)
        if not os.path.isfile(path):
            return
        view_name = f"report_{fname}"
        if view_name not in self.visualizer.get_view_names():
            detail_view = ReportView(self.visualizer, fname)
            detail_view._on_back_click = lambda: self.visualizer.activate_view("reports")
            detail_view._on_edit_click = lambda: self._edit_report(fname)
            self.visualizer.register_view(view_name, detail_view)
        self.visualizer.activate_view(view_name)

    def _new_report(self):
        from .views.report_dialog import ReportDialog
        ReportDialog(self)

    def _edit_report(self, fname):
        from .views.report_dialog import ReportDialog
        view_name = f"report_{fname}"

        def _after_save(saved_name):
            if view_name in self.visualizer.get_view_names():
                view = self.visualizer.get_view(view_name)
                if view is not None:
                    view._fname = saved_name
                    view._title_label.config(text=saved_name)
                    view._refresh()

        ReportDialog(self, fname=fname, on_save=_after_save)

    def _open_user_view(self, username):
        view_name = f"user_{username}"
        if view_name not in self.visualizer.get_view_names():
            from .views import UserDetailView
            detail_view = UserDetailView(self.visualizer, username)
            detail_view._on_back_click = lambda: self.visualizer.activate_view("users")
            self.visualizer.register_view(view_name, detail_view)
        self.visualizer.activate_view(view_name)

    def _open_people_view(self, person_id):
        view_name = f"person_{person_id}"
        if view_name not in self.visualizer.get_view_names():
            from .views import PeopleDetailView
            detail_view = PeopleDetailView(self.visualizer, person_id)
            detail_view._on_back_click = lambda: self.visualizer.activate_view("people")
            self.visualizer.register_view(view_name, detail_view)
        self.visualizer.activate_view(view_name)

    def _open_wifi_view(self, network):
        key = (network.get("bssid") or network.get("ssid") or "net").replace(":", "")
        view_name = f"wifi_detail_{key}"
        if view_name not in self.visualizer.get_view_names():
            from .views import WifiDetailView
            detail_view = WifiDetailView(self.visualizer, network)
            detail_view._on_back_click = lambda: self.visualizer.activate_view("wifi")
            self.visualizer.register_view(view_name, detail_view)
        self.visualizer.activate_view(view_name)

    def _on_tool_click(self, action):
        if action == "scanner":
            self._scan_active()
            if self._active_scanner and self._active_scanner.is_running:
                self.visualizer.activate_view("machines")
        elif action == "fuzzer":
            self._cmd_fuzz([])
        elif action == "webrecorder":
            self._cmd_recorder([])
        elif action == "bruteforce":
            self._cmd_use_bruteforce([])
        elif action == "hashcat":
            self._cmd_use_hashcat([])
        elif action == "dicma":
            self._cmd_use_dicma([])
        elif action == "wifioperator":
            self._cmd_use_wifioperator([])

    def _on_inventory_click(self, action):
        self.visualizer.activate_view(action)

    def _open_domain_view(self, domain):
        self._cmd_view_domain([domain])

    def _open_shell_view(self, sid):
        view_name = f"shell_{sid}"
        if view_name not in self.visualizer.get_view_names():
            from .views import ShellDetailView, SSHDetailView, ReverseShellDetailView
            s = shell_db.get_session(sid)
            stype = (s or {}).get("type", "")
            if stype == "SSH":
                detail_view = SSHDetailView(self.visualizer, sid)
            elif stype.startswith("Revershell"):
                detail_view = ReverseShellDetailView(self.visualizer, sid)
            else:
                detail_view = ShellDetailView(self.visualizer, sid)
            detail_view._on_back_click = lambda: self.visualizer.activate_view("shells")
            self.visualizer.register_view(view_name, detail_view)
        self.visualizer.activate_view(view_name)

    def _cmd_start_listener(self, args):
        if self._shell_listener and self._shell_listener.is_running:
            if args:
                self.console.warning(f"Shell listener already running on port {self._shell_listener.port}. Use stop-listener first.")
            else:
                self.console.warning(f"Shell listener already running on port {self._shell_listener.port}")
            return
        if args:
            try:
                port = int(args[0])
            except ValueError:
                self.console.error("Invalid port")
                return
            self._shell_listener = ShellListener(
                port=port,
                on_new_session=self._on_shell_session,
            )
            self._shell_listener.start()
            self.console.info(f"Reverse shell listener started on port {port}")
        else:
            self._start_shell_listener()

    def _cmd_start(self, args):
        if not args:
            self.console.body("Usage: start <shells-listener|mdns-listener>")
            return
        sub = args[0].lower()
        if sub == "shells-listener":
            self._cmd_start_shells(args[1:])
        elif sub == "mdns-listener":
            self._cmd_start_mdns(args[1:])
        else:
            self.console.error(f"Unknown start target: {sub}")

    def _cmd_start_shells(self, args):
        if self._shell_listener and self._shell_listener.is_running:
            self.console.warning(f"Shell listener already running on port {self._shell_listener.port}")
            return
        if args:
            try:
                port = int(args[0])
                if port < 1 or port > 65535:
                    self.console.error("Port must be between 1 and 65535")
                    return
            except ValueError:
                self.console.body("Usage: start shells-listener [port]")
                return
            self._shell_listener = ShellListener(port=port, on_new_session=self._on_shell_session)
            self._shell_listener.start()
            self.console.info(f"Reverse shell listener started on port {port}")
        else:
            self._start_shell_listener()

    def _cmd_start_mdns(self, args):
        if self._passive_scanner and self._passive_scanner.is_running:
            self.console.warning("Passive mDNS scanner is already running")
            return
        from src.tools.scanner.mdns import _check_permission
        if not _check_permission():
            self.console.error("mDNS passive scanner: permission denied. Run as root or install with CAP_NET_RAW.")
            return
        self._passive_scanner = PassiveMDNSScanner(on_host_callback=self._on_host_discovered)
        self._passive_scanner.start()
        self.console.info("Passive listening mDNS started")

    def _cmd_stop_listener(self, args):
        if self._shell_listener and self._shell_listener.is_running:
            self._shell_listener.stop()
            self._shell_listener = None
            self.console.info("Reverse shell listener stopped")
        else:
            self.console.warning("No shell listener is running")

    def _cmd_stop(self, args):
        if not args:
            self.console.body("Usage: stop <shells-listener|mdns-listener|scanner>")
            return
        sub = args[0].lower()
        if sub == "shells-listener":
            if self._shell_listener and self._shell_listener.is_running:
                self._shell_listener.stop()
                self._shell_listener = None
                self.console.info("Reverse shell listener stopped")
            else:
                self.console.warning("No shell listener is running")
        elif sub == "mdns-listener":
            if self._passive_scanner and self._passive_scanner.is_running:
                self._passive_scanner.stop()
                self._passive_scanner = None
                self.console.info("Passive mDNS scanner stopped")
            else:
                self.console.warning("Passive mDNS scanner is not running")
        elif sub == "scanner":
            self._scan_stop()
        elif sub == "bruteforce":
            if self._bruteforce_engine:
                self._bruteforce_engine.stop()
                self._bruteforce_engine = None
            if self._bruteforce_dlg:
                self._bruteforce_dlg._stop()
            self.console.info("Bruteforce stopped")
        elif sub == "fuzzer":
            if self._fuzz_dlg:
                self._fuzz_dlg._stop()
            if hasattr(self, '_fuzz_engine') and self._fuzz_engine:
                self._fuzz_engine.stop()
                self._fuzz_engine = None
            self.console.info("Fuzzer stopped")
        elif sub == "webrecorder":
            if self._recorder and self._recorder.is_running():
                self._recorder.stop()
                self._recorder.kill_browser()
                self._recorder = None
                self.console.info("Recorder stopped")
            else:
                self.console.warning("No webrecorder is running")
        elif sub == "tcpscan":
            if self._tcpscan_running:
                self._tcpscan_running = False
                if self._tcpscan_process:
                    self._tcpscan_process.kill()
                self.console.info("TCP scan stopped")
            else:
                self.console.warning("No tcp scan is running")
        elif sub == "udpscan":
            if self._udpscan_running:
                self._udpscan_running = False
                self.console.info("UDP scan stopped")
            else:
                self.console.warning("No udp scan is running")
        elif sub == "whatweb":
            self.console.info("whatweb scan finished")
        elif sub == "port-inspector":
            if self._port_inspector_running:
                self._port_inspector_running = False
                self.console.info("Port inspector stopped")
            else:
                self.console.warning("No port inspector is running")
        elif sub == "hashcat":
            if hasattr(self, "_hashcat_engine") and self._hashcat_engine:
                self._hashcat_engine.stop()
                self._hashcat_engine = None
                self.console.info("Hashcat stopped")
            else:
                self.console.warning("No hashcat engine is running")
        else:
            self.console.error(f"Unknown stop target: {sub}")

    def _on_shell_session(self, **kwargs):
        if "error" in kwargs:
            self.console.after(0, lambda: self.console.error(f"Shell listener error: {kwargs['error']}"))
            return
        session = kwargs.get("session")
        if session:
            self.console.after(0, lambda s=session: self.console.success(
                f"New shell #{s['id']} from {s['ip']}:{s['source_port']}"
            ))

    def _cmd_scan(self, args):
        if not args:
            self._scan_active()
            return
        sub = args[0].lower()
        if re.match(r"^\d+\.\d+\.\d+\.\d+$", sub):
            self._scan_ip(sub)
        elif sub == "active":
            self._scan_active()
        elif sub == "passive":
            self._scan_passive()
        elif sub == "iface":
            self._scan_iface(args[1:])
        elif sub == "stop":
            self._scan_stop()
        elif sub == "list":
            self._scan_list()
        else:
            self._show_scan_help()

    def _show_scan_help(self):
        iface_status = f" ({self._selected_interface[0]})" if self._selected_interface else " (none)"
        self.console.title("Scan commands")
        self.console.body(f"  scan [active]        ARP + mDNS + Nmap (all methods)")
        self.console.body(f"  scan <ip>            Identify a specific IP address")
        self.console.body(f"  scan passive         Restart passive mDNS discovery")
        self.console.body(f"  scan iface           List available interfaces")
        self.console.body(f"  scan iface <name>    Select interface by name")
        self.console.body(f"  scan stop            Stop active scan")
        self.console.body(f"  scan list            List discovered machines")
        self.console.body(f"  Interface{iface_status}")

    def _scan_iface(self, args):
        if args:
            name = args[0]
            addrs = ifaddresses(name).get(AF_INET)
            if addrs:
                self._selected_interface = (name, addrs[0]["addr"], addrs[0]["netmask"])
                src.machines.interface_name = name
                src.machines.interface_ip = addrs[0]["addr"]
                self.console.success(f"Interface set to {name} ({addrs[0]['addr']})")
            else:
                self.console.error(f"Interface '{name}' not found or has no IPv4")
            return

        self.console.title("Available interfaces")
        for iface in interfaces():
            if iface == "lo0":
                continue
            addrs = ifaddresses(iface).get(AF_INET)
            if addrs:
                marker = " <--" if self._selected_interface and self._selected_interface[0] == iface else ""
                self.console.body(f"  {iface:<8} {addrs[0]['addr']:<18}{marker}")

    def _scan_passive(self):
        if self._passive_scanner and self._passive_scanner.is_running:
            self.console.warning("Passive scan is already running.")
            return
        from src.tools.scanner.mdns import _check_permission
        if not _check_permission():
            self.console.error("mDNS passive scanner: permission denied.")
            return
        self._passive_scanner = PassiveMDNSScanner(on_host_callback=self._on_host_discovered)
        self._passive_scanner.start()
        self.console.info("Passive listening mDNS started")

    def _scan_active(self):
        result = self._show_scan_dialog()
        if not result:
            self.console.warning("Scan cancelled")
            return

        action = result.get("action")
        ip = result.get("ip")

        if action == "scan":
            if ip:
                self._scan_ip(ip)
                return
            iface = result.get("iface")
            if not iface:
                return

            if self._active_scanner and self._active_scanner.is_running:
                self.console.warning("Active scan is already running.")
                return

            self._selected_interface = iface
            src.machines.interface_name = iface[0]
            src.machines.interface_ip = iface[1]
            iface_name = iface[0]
            try:
                self._active_scanner = ActiveScanner(
                    on_host_callback=self._on_host_discovered,
                    interface_name=iface_name,
                )
                self._active_scanner.start()
                self.console.info("Active scan started")
                nmap_status = "enabled" if self._active_scanner.has_nmap else "disabled"
                self.console.body(
                    f"    Interface: {self._active_scanner.interface_name}  "
                    f"Network: {self._active_scanner.network_cidr}  "
                    f"Nmap: {nmap_status}"
                )
                if not self._active_scanner.has_nmap:
                    self.console.info("nmap binary not available — ARP scanner using native mode")
            except RuntimeError as e:
                self.console.error(str(e))

        elif action == "tcpscan":
            self._cmd_tcpscan([ip])
        elif action == "udpscan":
            self._cmd_udpscan([ip])
        elif action == "port-inspector":
            self._cmd_port_inspector([ip, str(result.get("port", 80))])

    def _show_scan_dialog(self):
        dialog = ScanDialog(self)
        return dialog.result

    def _scan_stop(self):
        if self._active_scanner and self._active_scanner.is_running:
            self._active_scanner.stop()
            self._active_scanner = None
            self.console.info("Active scan stopped")
        else:
            self.console.warning("No active scan is running.")

    def _scan_interface(self, iface_name):
        from src.network_iface import ifaddresses, AF_INET
        addrs = ifaddresses(iface_name).get(AF_INET)
        if not addrs:
            event_bus.submit({"type": "scan_error", "message": f"Interface {iface_name} has no IPv4 address"})
            return
        iface_tuple = (iface_name, addrs[0]["addr"], addrs[0]["netmask"])
        if self._active_scanner and self._active_scanner.is_running:
            event_bus.submit({"type": "scan_info", "message": "Active scan is already running"})
            return
        self._selected_interface = iface_tuple
        import src.machines
        src.machines.interface_name = iface_tuple[0]
        src.machines.interface_ip = iface_tuple[1]
        from src.tools.scanner.active import ActiveScanner
        try:
            self._active_scanner = ActiveScanner(
                on_host_callback=self._on_host_discovered,
                interface_name=iface_name,
            )
            self._active_scanner.start()
        except RuntimeError as e:
            event_bus.submit({"type": "scan_error", "message": f"Active scan failed: {e}"})

    def _scan_ip(self, ip):
        self.console.info(f"Checking {ip}...")
        threading.Thread(target=self._run_scan_ip, args=(ip,), daemon=True).start()

    def _run_scan_ip(self, ip):
        info = _do_scan_ip(ip)
        if info is None:
            event_bus.submit({"type": "scan_error", "message": f"No device detected at {ip}"})
            return
        event_bus.submit({"type": "scan_ip_result", "machine": store.get(ip)})

    TCP_PORTS_COMMON = [
        7, 9, 13, 21, 22, 23, 25, 37, 49, 53, 69, 70, 79, 80, 88, 110, 111,
        113, 119, 123, 135, 137, 138, 139, 143, 161, 162, 179, 199, 389, 443,
        445, 465, 512, 513, 514, 515, 548, 554, 587, 631, 636, 646, 873, 993,
        995, 1025, 1026, 1027, 1080, 1099, 1433, 1434, 1521, 1723, 2049, 2121,
        2222, 2375, 2701, 3128, 3260, 3306, 3389, 3690, 4369, 4444, 4786, 4848,
        5000, 5353, 5432, 5555, 5672, 5800, 5900, 5985, 5986, 6379, 6667, 7001,
        7002, 7777, 8000, 8009, 8080, 8180, 8443, 8888, 9000, 9090, 9200, 9443,
        9999, 11211, 27017, 50070, 61616,
    ]

    @staticmethod
    def _is_root():
        try:
            return os.geteuid() == 0
        except AttributeError:
            return False

    def _tcp_scan_connect(self, ip, ports, port_callback=None):
        open_ports = []
        def _check(p):
            if not self._tcpscan_running:
                return
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1.5)
            try:
                if sock.connect_ex((ip, p)) == 0:
                    open_ports.append(p)
                    if port_callback:
                        port_callback(p)
            finally:
                sock.close()
        with ThreadPoolExecutor(max_workers=100) as exe:
            futures = [exe.submit(_check, p) for p in ports]
            for f in as_completed(futures):
                if not self._tcpscan_running:
                    break
        return sorted(open_ports)

    def _tcp_scan_syn_nmap(self, ip, ports):
        port_list = ",".join(str(p) for p in ports)
        _dbg(f"[tcpscan-nmap] {ip} ports={len(ports)}")
        try:
            self._tcpscan_process = subprocess.Popen(
                ["nmap", "-n", "-Pn", "-sS", "-p", port_list, ip],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
            )
            out, _ = self._tcpscan_process.communicate(timeout=120)
            _dbg(f"[tcpscan-nmap] output:\n{out}")
        except (subprocess.TimeoutExpired, Exception) as e:
            self._tcpscan_process.kill()
            self._tcpscan_process.communicate()
            _dbg(f"[tcpscan-nmap] killed: {e}")
            return []
        finally:
            self._tcpscan_process = None
        open_ports = []
        for line in out.splitlines():
            m = re.match(r"(\d+)/tcp\s+open", line)
            if m:
                open_ports.append(int(m.group(1)))
        _dbg(f"[tcpscan-nmap] done: open={len(open_ports)} ports={sorted(open_ports)}")
        return sorted(open_ports)

    @staticmethod
    def _detect_scan_method():
        if shutil.which("nmap"):
            return "SYN"
        return "connect"

    def _tcp_scan(self, ip, ports, method, port_callback=None):
        if method.startswith("SYN"):
            return self._tcp_scan_syn_nmap(ip, ports)
        return self._tcp_scan_connect(ip, ports, port_callback=port_callback)

    def _run_tcpscan(self, ip, method, skip_phase1=False):
        machine = store.get(ip)
        self._tcpscan_running = True
        all_ports = list(machine_db.load_tcp_ports(machine.id)) if skip_phase1 and machine else []
        try:
            def _save_ports():
                if machine and machine.id:
                    machine_db.save_tcp_ports(machine.id, sorted(all_ports))

            def _on_port(p):
                if p not in all_ports:
                    all_ports.append(p)
                _save_ports()

            if not skip_phase1:
                # Phase 1: common ports
                open_ports = _do_tcp_scan_common(ip)
                for p in open_ports:
                    if p not in all_ports:
                        all_ports.append(p)
                _save_ports()
                for p in open_ports:
                    self.console.after(0, lambda port=p: self.console.success(
                        f"  {ip}  port {port} open"
                    ))
                self.console.after(0, lambda: self.console.info(
                    f"TCP common ports ({len(_TCP_SCAN_PORTS)}) done. Continuing full scan (65535)..."
                ))

                if not self._tcpscan_running:
                    self.console.after(0, lambda: self.console.warning(f"TCP scan {ip} stopped"))
                    return

            # Phase 2: remaining ports
            common_set = set(_TCP_SCAN_PORTS)
            remaining = [p for p in range(1, 65536) if p not in common_set]
            more = self._tcp_scan(ip, remaining, method, port_callback=_on_port)
            for p in more:
                if p not in all_ports:
                    all_ports.append(p)
            _save_ports()
            for p in more:
                self.console.after(0, lambda port=p: self.console.success(
                    f"  {ip}  port {port} open"
                ))
            self.console.after(0, lambda: self.console.info(
                f"TCP scan {ip} finished ({65535} ports): {len(all_ports)} open"
            ))
        finally:
            self._tcpscan_running = False

    def _get_active_machine(self):
        name = self.visualizer.get_active_view_name()
        if name and name.startswith("machine_"):
            try:
                mid = int(name.split("_")[1])
                for m in store.get_all():
                    if m.id == mid:
                        return m
            except (ValueError, IndexError):
                pass
        return None

    def _cmd_tcpscan(self, args):
        if not args:
            m = self._get_active_machine()
            if m:
                args = [str(m.id)]
            else:
                self.console.body("Usage: tcpscan <ip|id> | tcpscan stop")
                return
        sub = args[0].lower()
        if sub == "stop":
            if not self._tcpscan_running:
                self.console.warning("No tcpscan is running.")
                return
            self._tcpscan_running = False
            if self._tcpscan_process:
                self._tcpscan_process.kill()
            self.console.info("TCP scan stop requested")
            return
        ip = sub
        if re.match(r"^\d+$", ip):
            machine_id = int(ip)
            machine = None
            for m in store.get_all():
                if m.id == machine_id:
                    machine = m
                    break
            if machine:
                ip = machine.ip
            else:
                self.console.warning(f"No machine with ID #{machine_id}")
                return
        if self._tcpscan_running:
            self.console.warning("A TCP scan is already running.")
            return
        if self._udpscan_running:
            self._udpscan_running = False
            self.console.info("UDP scan stopped")
        _dbg(f"[tcpscan] requested for {ip}")
        if self._active_scanner and self._active_scanner.is_running:
            self._active_scanner.stop()
            self._active_scanner = None
            self.console.info("Active scan stopped")
        if self._is_root() and self._detect_scan_method() == "SYN":
            method = "SYN (nmap)"
        else:
            method = "connect" + (" (no root)" if not self._is_root() else "")
        self.console.info(f"TCP scanning {ip}  ({method})...")
        threading.Thread(target=self._run_tcpscan, args=(ip, method), daemon=True).start()

    UDP_PORTS_COMMON = [
        7, 9, 11, 13, 17, 19, 37, 42, 49, 53,
        67, 68, 69, 80, 88, 111, 113, 119, 123, 135,
        136, 137, 138, 139, 143, 158, 161, 162, 177, 194,
        201, 209, 213, 218, 220, 259, 264, 318, 323, 383,
        389, 401, 427, 443, 445, 464, 465, 497, 500, 512,
        513, 514, 515, 517, 518, 520, 521, 525, 529, 531,
        532, 533, 534, 540, 546, 547, 554, 563, 587, 591,
        593, 604, 623, 631, 636, 639, 646, 647, 648, 651,
        660, 666, 674, 691, 700, 702, 706, 711, 712, 720,
        749, 750, 751, 752, 753, 754, 758, 760, 782, 829,
        847, 848, 853, 859, 860, 861, 862, 873, 953, 989,
        990, 991, 992, 993, 995, 1001, 1062, 1194, 1434, 1521,
        1645, 1646, 1701, 1718, 1719, 1720, 1723, 1812, 1813, 1900,
        1901, 2000, 2049, 2082, 2083, 2222, 2223, 2427, 2727, 2967,
        3000, 3031, 3050, 3128, 3130, 3283, 3306, 3389, 3455, 3478,
        3632, 3689, 4000, 4001, 4063, 4105, 4369, 4444, 4500, 4569,
        4662, 4672, 4949, 5000, 5001, 5004, 5005, 5030, 5050, 5060,
        5080, 5093, 5190, 5222, 5223, 5269, 5298, 5351, 5353, 5355,
        5405, 5432, 5480, 5500, 5510, 5550, 5555, 5631, 5632, 5672,
        5683, 5713, 5721, 5722, 5746, 5800, 5863, 5900, 5984, 5985,
        6000, 6001, 6070, 6086, 6129, 6257, 6346, 6347, 6379, 6502,
        6544, 6665, 6666, 6667, 6668, 6669, 6881, 6900, 6980, 7000,
        7070, 7100, 7170, 7676, 7777, 7937, 8000, 8002, 8010, 8074,
        8080, 8081, 8086, 8087, 8200, 8443, 8765, 8888, 9000, 9001,
        9030, 9090, 9100, 9101, 9102, 9103, 9119, 9160, 9200, 9306,
        9312, 9418, 9443, 9535, 9536, 9875, 9898, 9981, 10000, 10080,
        11371, 12345, 13720, 13721, 14567, 15104, 17007, 19283, 19813, 20000,
        20720, 21000, 21554, 22273, 23073, 23399, 23456, 25565, 27000, 27017,
        27374, 28119, 31337, 33434, 34861, 37777, 40193, 41524, 45678, 49152,
        49153, 49167, 50000, 55553, 55555, 62078,
    ]

    def _udp_scan_connect(self, ip, ports, port_callback=None):
        open_ports = []
        def _check(p):
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(1.5)
            try:
                sock.sendto(b"", (ip, p))
                sock.recvfrom(1024)
                open_ports.append(p)
                if port_callback:
                    port_callback(p)
            except socket.timeout:
                pass
            except (ConnectionRefusedError, OSError):
                pass
            finally:
                sock.close()
        with ThreadPoolExecutor(max_workers=100) as exe:
            futures = [exe.submit(_check, p) for p in ports]
            for f in as_completed(futures):
                if not self._udpscan_running:
                    break
        return sorted(open_ports)

    def _udp_scapy_probe(self, ip, ports):
        from scapy.all import IP, UDP, ICMP, sr1, RandShort
        open_ports = []
        for p in ports:
            if not self._udpscan_running:
                break
            try:
                pkt = IP(dst=ip) / UDP(sport=RandShort(), dport=p)
                reply = sr1(pkt, timeout=1.5, verbose=0)
                if reply is None:
                    open_ports.append(p)
                elif reply.haslayer(ICMP) and reply[ICMP].type == 3 and reply[ICMP].code == 3:
                    pass
                else:
                    open_ports.append(p)
            except Exception:
                pass
        return sorted(open_ports)

    def _udp_scan(self, ip, ports, port_callback=None):
        if self._is_root():
            return self._udp_scapy_probe(ip, ports)
        return self._udp_scan_connect(ip, ports, port_callback=port_callback)

    def _run_udpscan(self, ip, skip_phase1=False):
        machine = store.get(ip)
        self._udpscan_running = True
        all_ports = list(machine_db.load_udp_ports(machine.id)) if skip_phase1 and machine else []
        try:
            def _save_ports():
                if machine and machine.id:
                    machine_db.save_udp_ports(machine.id, sorted(all_ports))

            def _on_port(p):
                if p not in all_ports:
                    all_ports.append(p)
                _save_ports()

            if not skip_phase1:
                self.console.after(0, lambda: self.console.info(
                    f"UDP scanning {ip}..."
                ))

                open_ports = _do_udp_scan_common(ip)
                for p in open_ports:
                    if p not in all_ports:
                        all_ports.append(p)
                _save_ports()
                for p in open_ports:
                    self.console.after(0, lambda port=p: self.console.success(
                        f"  {ip}  UDP {port} open"
                    ))

                if not self._udpscan_running:
                    self.console.after(0, lambda: self.console.warning(f"UDP scan {ip} stopped"))
                    return

                self.console.after(0, lambda: self.console.info(
                    f"UDP common ports ({len(_UDP_SCAN_PORTS)}) done. Continuing full scan (65535)..."
                ))

            common_set = set(_UDP_SCAN_PORTS)
            remaining = [p for p in range(1, 65536) if p not in common_set]
            more = self._udp_scan(ip, remaining, port_callback=_on_port)
            for p in more:
                if p not in all_ports:
                    all_ports.append(p)
            _save_ports()
            for p in more:
                self.console.after(0, lambda port=p: self.console.success(
                    f"  {ip}  UDP {port} open"
                ))
            self.console.after(0, lambda: self.console.info(
                f"UDP scan {ip} finished ({65535} ports): {len(all_ports)} open"
            ))
        finally:
            self._udpscan_running = False

    def _cmd_udpscan(self, args):
        if not args:
            m = self._get_active_machine()
            if m:
                args = [str(m.id)]
            else:
                self.console.body("Usage: udpscan <ip|id> | udpscan stop")
                return
        sub = args[0].lower()
        if sub == "stop":
            if not self._udpscan_running:
                self.console.warning("No UDP scan is running.")
                return
            self._udpscan_running = False
            self.console.info("UDP scan stop requested")
            return
        ip = sub
        if re.match(r"^\d+$", ip):
            machine_id = int(ip)
            machine = None
            for m in store.get_all():
                if m.id == machine_id:
                    machine = m
                    break
            if machine:
                ip = machine.ip
            else:
                self.console.warning(f"No machine with ID #{machine_id}")
                return
        if self._udpscan_running:
            self.console.warning("A UDP scan is already running.")
            return
        if self._tcpscan_running:
            self._tcpscan_running = False
            if self._tcpscan_process:
                self._tcpscan_process.kill()
            self.console.info("TCP scan stopped")
        _dbg(f"[udpscan] requested for {ip}")
        threading.Thread(target=self._run_udpscan, args=(ip,), daemon=True).start()

    def _cmd_whatweb(self, args):
        m = self._get_active_machine()
        if not args:
            if m:
                args = [str(m.id)]
            else:
                self.console.body("Usage: whatweb <ip|id|domain> [port]")
                return
        if args[0].lower() == "stop":
            self.console.info("whatweb scan finished")
            return
        target = args[0]
        port = 80
        if len(args) >= 2:
            try:
                port = int(args[1])
            except ValueError:
                self.console.error("Invalid port number")
                return
        machine = None
        domain_name = None
        if re.match(r"^\d+$", target):
            mid = int(target)
            for m in store.get_all():
                if m.id == mid:
                    machine = m
                    break
        elif re.match(r"^\d+\.\d+\.\d+\.\d+$", target):
            machine = store.get(target)
            if not machine:
                machine = store.add_or_update(ip=target, method="manual")
                machine.device_type = "device unknown"
                machine_db.save_machine_info(machine)
        else:
            if not domain_db.exists(target):
                domain_db.init_or_update(target, 0, "0.0.0.0", "manual")
            domain_name = target
            try:
                info = socket.getaddrinfo(domain_name, None, socket.AF_INET, socket.SOCK_STREAM)
                ip = info[0][4][0] if info else domain_name
            except Exception:
                ip = domain_name
            machine = store.get(ip)
            if not machine:
                machine = store.add_or_update(ip=ip, method="manual")
                machine.device_type = "device unknown"
                machine_db.save_machine_info(machine)
            domain_db.init_or_update(domain_name, machine.id, machine.ip, "whatweb")

        if not machine:
            self.console.warning(f"No machine found for: {target}")
            return
        ip = machine.ip
        threading.Thread(target=self._run_webscan, args=(ip, port, machine, domain_name), daemon=True).start()

    @staticmethod
    def _has_whatweb():
        try:
            r = subprocess.run(["whatweb", "--version"], capture_output=True, timeout=5)
            if r.returncode == 0:
                return True, "direct"
        except (FileNotFoundError, PermissionError, OSError, subprocess.TimeoutExpired):
            pass
        try:
            r = subprocess.run("whatweb --version", shell=True, capture_output=True, timeout=5)
            if r.returncode == 0:
                return True, "subshell"
        except (FileNotFoundError, PermissionError, OSError, subprocess.TimeoutExpired):
            pass
        try:
            shell = os.environ.get("SHELL", "/bin/sh")
            r = subprocess.run([shell, "-ic", "whatweb --version"], capture_output=True, timeout=5)
            if r.returncode == 0:
                alias_r = subprocess.run(
                    [shell, "-ic", "alias whatweb 2>/dev/null"],
                    capture_output=True, timeout=5, text=True,
                )
                alias_out = alias_r.stdout.strip()
                if "whatweb=" in alias_out:
                    path = alias_out.split("whatweb=", 1)[1].strip().strip("'").strip('"')
                    if os.path.isfile(path):
                        return True, path
                return True, "interactive"
        except (FileNotFoundError, PermissionError, OSError, subprocess.TimeoutExpired):
            pass
        return False, ""

    @staticmethod
    def _strip_ansi(text):
        return re.sub(r"\x1b\[[0-9;]*m", "", text)

    def _run_webscan(self, ip, port, machine, domain_name=None):
        target = domain_name or ip
        found, mode = self._has_whatweb()
        if found:
            self.console.after(0, lambda: self.console.info(
                f"Web scanning {target}:{port} (whatweb)..."
            ))
            stdout, stderr = _run_whatweb(target, port, mode=mode)
            stdout = self._strip_ansi(stdout)
            stderr = self._strip_ansi(stderr)
            if stderr:
                for line in stderr.split("\n"):
                    if line.strip():
                        self.console.after(0, lambda l=line: self.console.error(f"  whatweb: {l}"))
                stdout = stdout + "\n" + stderr if stdout else stderr
            if stdout:
                machine_db.save_web_service(machine.id, port, stdout)
                if domain_name:
                    domain_db.save_web_service(domain_name, port, stdout)
                domains = _extract_domains_from_whatweb(stdout)
                for d in domains:
                    domain_db.init_or_update(d, machine.id, machine.ip, "whatweb")
                    machine_db.save_domain(machine.id, d, "whatweb")
                self.console.after(0, lambda: self.console.info(
                    f"Web scan {target}:{port} done (whatweb)"
                ))
                for d in domains:
                    self.console.after(0, lambda dom=d: self.console.success(f"  domain: {dom}"))
            else:
                self.console.after(0, lambda: self.console.warning(
                    f"No web service detected at {target}:{port}"
                ))
        else:
            self.console.after(0, lambda: self.console.error(
                "whatweb not found in path"
            ))
            self.console.after(0, lambda: self.console.info(
                f"Web scanning {target}:{port} (internal scanner)..."
            ))
            output = _probe_web_internal(target, port)
            engine = "internal"
            if output:
                machine_db.save_web_service(machine.id, port, output)
                if domain_name:
                    domain_db.save_web_service(domain_name, port, output)
                self.console.after(0, lambda: self.console.info(
                    f"Web scan {ip}:{port} done ({engine})"
                ))
                for line in output.split("\n"):
                    self.console.after(0, lambda l=line: self.console.body(f"  {l}"))
            else:
                self.console.after(0, lambda: self.console.warning(
                    f"No web service detected at {ip}:{port}"
                ))

    def _cmd_port_inspector(self, args):
        if not args:
            self.console.body("Usage: port-inspector <ip|id> <port> | port-inspector stop")
            return
        if args[0].lower() == "stop":
            if not self._port_inspector_running:
                self.console.warning("No port inspector is running.")
                return
            self._port_inspector_running = False
            self.console.info("Port inspector stopped")
            return
        if len(args) < 2:
            self.console.body("Usage: port-inspector <ip|id> <port> | port-inspector stop")
            return
        sub = args[0].lower()
        if sub == "stop":
            if not self._port_inspector_running:
                self.console.warning("No port inspector is running.")
                return
            self._port_inspector_running = False
            self.console.info("Port inspector stopped")
            return
        if len(args) < 2:
            self.console.body("Usage: port-inspector <ip|id> <port> | port-inspector stop")
            return
        target, port_str = args[0], args[1]
        try:
            port = int(port_str)
        except ValueError:
            self.console.error("Invalid port number")
            return
        machine = None
        if re.match(r"^\d+$", target):
            mid = int(target)
            for m in store.get_all():
                if m.id == mid:
                    machine = m
                    break
        else:
            machine = store.get(target)
        if not machine:
            self.console.warning(f"No machine found for: {target}")
            return
        ip = machine.ip
        if self._port_inspector_running:
            self.console.warning("A port inspector is already running.")
            return
        self._port_inspector_running = True
        threading.Thread(target=self._run_port_inspector, args=(ip, port, machine), daemon=True).start()

    def _run_port_inspector(self, ip, port, machine):
        self.console.after(0, lambda: self.console.info(f"Port inspector {ip}:{port} starting..."))
        try:
            for label, text in _do_port_inspection(ip, port):
                if not self._port_inspector_running:
                    self.console.after(0, lambda: self.console.warning(f"Port inspector {ip}:{port} stopped"))
                    return
                machine_db.save_banner(machine.id, port, text, label)
                self.console.after(0, lambda t=text, l=label: self._show_banner_result(ip, port, t, l))
        finally:
            self._port_inspector_running = False
            self.console.after(0, lambda: self.console.info(f"Port inspector {ip}:{port} finished"))

    def _show_banner_result(self, ip, port, text, label):
        self.console.after(0, lambda: self.console.success(f"Port inspector {ip}:{port} ({label}):"))
        for line in text.split("\n")[:10]:
            self.console.after(0, lambda l=line: self.console.body(f"  {l}"))

    def _scan_list(self):
        machines = store.get_all_sorted()
        if not machines:
            self.console.warning("No machines discovered yet.")
            return
        self.console.title(f"Discovered machines ({len(machines)})")
        for m in machines:
            d = m.to_dict()
            self.console.body(
                f"  {d['ip']:<20} {d['hostname']:<20} {','.join(d['methods']):<20} "
                f"first: {d['first_seen']}  last: {d['last_seen']}"
            )

    def _on_host_discovered(self, ip, hostname, method, mac=""):
        if ip == "ERROR":
            event_bus.submit({"type": "scan_error", "message": hostname})
            return

        if ip in ("127.0.0.1", "::1", "localhost") or ip.startswith("127."):
            return

        existing = store.get(ip)
        if existing is None and hostname:
            existing = store.get_by_hostname(hostname)

        is_new = existing is None

        if existing is not None:
            existing.update(hostname=hostname, mac=mac, method=method)
            is_ipv6 = ":" in ip
            if is_ipv6:
                if not existing.ipv6:
                    existing.ipv6 = ip
            machine_db.save_machine_info(existing)
            machine = existing
            _dbg(f"[discovery] ip={ip} hostname={hostname} method={method} merged into #{existing.id}" + (" (new)" if is_new else ""))
        else:
            machine = store.add_or_update(ip=ip, hostname=hostname, mac=mac, method=method)
            _dbg(f"[discovery] ip={ip} hostname={hostname} method={method} new machine #{machine.id}")

        if ip in self._identifying_ips:
            return

        event_bus.submit({
            "type": "discovery",
            "machine": machine,
            "is_new": existing is None,
        })
        if existing is None or existing.device_type in ("", "device unknown", "iOS device"):
            self._identifying_ips.add(ip)
            threading.Thread(target=self._identify, args=(machine,), daemon=True).start()

    def _identify(self, machine):
        _dbg(f"[identify-start] {machine.ip}  hostname={machine.hostname}")
        old_type = machine.device_type
        try:
            gateway = get_gateway_ip()
            result = identify_device(machine.ip, gateway_ip=gateway, hostname=machine.hostname)
            _dbg(f"[identify-done]  {machine.ip}  result={result!r}")
            if result:
                machine.device_type = result
                model = extract_model_for_ip(machine.ip, resolve=True)
                if model:
                    machine.model = model
                if result == "Windows machine":
                    os_info, domain, server_name = _probe_smb_info(machine.ip)
                    if os_info:
                        machine.device_type = os_info
                        machine.os = os_info
                    if domain:
                        machine.domain = domain
                        domain_db.init_or_update(domain, machine.id, machine.ip, "smb")
                        machine_db.save_domain(machine.id, domain, "smb")
                        machine.hostname = server_name
                if result == "Linux device":
                    banner = _probe_ssh_banner(machine.ip)
                    if banner:
                        distro = _identify_linux_distro(banner)
                        if distro:
                            machine.device_type = distro
                            machine.os = distro
                machine_db.save_machine_info(machine)
                if result != old_type:
                    event_bus.submit({
                        "type": "identify_result",
                        "machine": machine,
                        "result": machine.device_type,
                    })
        finally:
            self._identifying_ips.discard(machine.ip)

    def _process_scanner_events(self, events):
        discoveries = []
        identify_results = []
        scan_ip_results = []
        scan_errors = []

        for ev in events:
            t = ev["type"]
            if t == "discovery":
                discoveries.append(ev)
            elif t == "identify_result":
                identify_results.append(ev)
            elif t == "scan_ip_result":
                scan_ip_results.append(ev)
            elif t == "scan_error":
                scan_errors.append(ev)
            elif t == "scan_info":
                self.console.info(ev["message"])
            elif t == "handshake":
                self.console.success(ev["message"])

        for ev in scan_errors:
            self.console.error(ev["message"])

        for ev in discoveries:
            m = ev["machine"]
            if ev.get("is_new"):
                self.console.success(
                    f"{m.ip:<20} {m.hostname:<20} [{', '.join(m.methods)}]"
                )

        for ev in scan_ip_results:
            m = ev["machine"]
            self.console.success(
                f"{m.ip:<20} {m.hostname:<20} [manual]"
            )

        for ev in identify_results:
            m = ev["machine"]
            result = ev["result"]
            if result == "device unknown":
                self.console.body(f"  {m.ip:<20} identified as: {result}")
            else:
                self.console.success(f"  {m.ip:<20} identified as: {result}")

    def _cmd_init(self, args):
        self._run_init_checks()

    def _cmd_settings(self, args):
        from .dialogs.settings import SettingsDialog
        SettingsDialog(self)

    def _cmd_debug(self, args):
        if not args:
            self.console.info("Usage: debug <ctx_screenshot|rotate_opencode_headers>")
            return
        sub = args[0].lower()
        if sub == "ctx_screenshot":
            self._cmd_debug_ctx_screenshot(args[1:])
        elif sub == "rotate_opencode_headers":
            self._cmd_debug_rotate_opencode_headers()
        else:
            self.console.info(
                f"Unknown debug subcommand: {sub}. Use: ctx_screenshot, "
                f"rotate_opencode_headers")

    def _cmd_debug_rotate_opencode_headers(self):
        """Rotate the opencode session and project ids.

        The request (message) id already rotates per user turn, so the next
        prompt gets a new one automatically.
        """
        import hashlib
        import os as _os
        from src.llm.client import _generate_opencode_id
        self._llm_session_id = _generate_opencode_id("ses_", descending=True)
        self._llm_project_id = hashlib.sha1(_os.urandom(32)).hexdigest()
        self._llm_request_id = None
        self._save_session()
        self.console.success(
            "opencode session parameters changed:\n"
            f"  x-opencode-session: {self._llm_session_id}\n"
            f"  x-opencode-project: {self._llm_project_id}")

    def _cmd_debug_ctx_screenshot(self, args):
        import json, os
        from datetime import datetime
        from src.elwand_paths import runtime_logs_dir

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"ctx_screenshot_{ts}.json"
        path = os.path.join(str(runtime_logs_dir()), filename)

        normalized = [self._normalize_msg(m) for m in self._llm_messages]

        data = {
            "timestamp": datetime.now().isoformat(),
            "total_messages": len(normalized),
            "context_limit": self._get_model_context_limit(),
            "context_pct": self._get_context_percentage(),
            "estimated_tokens": self._estimate_tokens(self._llm_messages),
            "agent_mode": self._agent_mode,
            "messages": normalized,
        }

        with open(path, "w") as f:
            json.dump(data, f, indent=2, default=str, ensure_ascii=False)

        self.console.success(
            f"Context saved to logs/{filename} "
            f"({len(normalized)} messages, {os.path.getsize(path)} bytes)")

    def _cycle_mode(self):
        self._silent_mode_cycle = True
        try:
            if getattr(self, "_agent_mode", False):
                self._leave_agent_mode()
            elif getattr(self, "_consultor_mode", False):
                self._leave_consultor_mode()
                self._enter_agent_mode()
            else:
                self._enter_consultor_mode()
        finally:
            self._silent_mode_cycle = False

    def _enter_consultor_mode(self):
        self._consultor_mode = True
        if not self._silent_mode_cycle:
            self.console.info(
                "Consultor mode. Commands: exit, stop, reset, compact, clear, menu."
            )
        self.console.set_mode_handler(self._consultor_handler, "Consultor", "#e6b422",
            commands={"exit": "Quit Elwand", "stop": "Interrupt execution",
                      "reset": "Clear conversation and cache", "compact": "Compact context",
                      "clear": "Clear the console", "menu": "Show help"})
        self._update_mode_prompt()

    def _consultor_handler(self, text):
        text = text.strip()
        if text.lower() == "exit" or not text:
            self._on_close()
            return
        if text.lower() == "menu":
            self.console.info(
                "Consultor mode commands:\n"
                "  exit    - Quit Elwand\n"
                "  stop    - Interrupt the current consultor execution\n"
                "  reset   - Clear conversation history, clear cache, start fresh\n"
                "  compact - Manually compact the conversation context\n"
                "  clear   - Clear the console display\n"
                "  menu    - Show this help\n\n"
                "Press Tab with empty input to cycle modes."
            )
            return
        if text.lower() == "stop":
            if self._agent_stop_event:
                self._agent_stop_event.set()
            self.console.warning("Interrupting consultor execution...")
            return
        if text.lower() == "clear":
            self.console._cmd_clear([])
            return
        if text.lower() == "reset":
            self._llm_messages = []
            self._llm_request_id = None
            self._llm_session_id = None
            self._last_ctx_hash = None
            self._last_token_pct = None
            self._total_api_tokens = 0
            self._context_injected = False
            self._clear_cache()
            self._clear_session()
            self.console.success("Context reset. Conversation history and cache cleared.")
            self._update_mode_prompt()
            return
        if text.lower() == "compact":
            import threading
            self.console._start_thinking_ui()
            def _compact():
                self._compact_if_needed(force=True)
                self._save_session()
                self.console.stop_thinking()
            threading.Thread(target=_compact, daemon=True).start()
            return
        self._consultor_ask(text)

    def _leave_consultor_mode(self):
        self._consultor_mode = False
        self.console.set_mode_handler(None)
        self.console.prompt_label.config(text="Elwand> ", fg="#ffffff")
        if not self._silent_mode_cycle:
            self.console.info("Left consultor mode.")

    _MODEL_CONTEXT_LIMITS = {
        "gpt-4o": 128000, "gpt-4o-mini": 128000, "gpt-4-turbo": 128000,
        "gpt-4": 8192, "gpt-3.5-turbo": 16385, "o1": 200000,
        "o1-mini": 128000, "o3-mini": 200000,
        "claude-3-opus": 200000, "claude-3-sonnet": 200000,
        "claude-3-haiku": 200000, "claude-3.5-sonnet": 200000,
        "claude-3.5-haiku": 200000, "claude-3.7-sonnet": 200000,
        "deepseek-chat": 1000000, "deepseek-v3": 200000,
        "deepseek-r1": 200000, "deepseek-v4": 1000000,
        "deepseek-v4-flash": 1000000, "deepseek-v4-pro": 1000000,
        "gemini-pro": 128000, "gemini-1.5-pro": 2097152,
        "gemini-1.5-flash": 1048576, "gemini-2.0-flash": 1048576,
        "llama3": 8192, "llama3.1": 128000, "llama3.2": 128000,
        "llama3.3": 128000, "llama4": 128000,
        "mistral": 32768, "mixtral": 32768,
        "qwen": 128000, "qwen2": 128000, "qwen2.5": 128000,
    }
    _DEFAULT_CONTEXT_LIMIT = 128000

    def _get_active_model(self):
        try:
            from src.llm.config import load
            config = load()
            pid = config.get("active_provider", "") or ""
            am = config.get("active_models", {})
            providers = config.get("providers", {})
            name = am.get(pid) or (providers.get(pid, {}).get("models", [None])[0])
            override = providers.get(pid, {}).get("context_limit")
            return pid, name, override
        except Exception:
            return "", None, None

    def _get_model_context_limit(self):
        pid, name, override = self._get_active_model()
        if isinstance(override, int) and override > 0:
            return override
        if name:
            try:
                from src.llm import models_catalog
                limit = models_catalog.lookup_context_limit(name)
                if limit:
                    return limit
            except Exception:
                pass
            name_lower = name.lower()
            if name_lower in self._MODEL_CONTEXT_LIMITS:
                return self._MODEL_CONTEXT_LIMITS[name_lower]
            for key, limit in self._MODEL_CONTEXT_LIMITS.items():
                if key in name_lower:
                    return limit
        return self._DEFAULT_CONTEXT_LIMIT

    def _estimate_tokens(self, messages):
        try:
            import json
            text = json.dumps(messages, default=str)
        except Exception:
            text = str(messages)
        return max(1, len(text) // 4)

    def _get_context_percentage(self):
        limit = self._get_model_context_limit()
        if limit <= 0:
            return None
        api = getattr(self, '_total_api_tokens', 0) or 0
        used = api if api > 0 else self._estimate_tokens(self._llm_messages)
        pct = (used * 100) // limit
        if used > 0 and pct == 0:
            pct = 1
        pct = min(99, pct)
        _ctx_log(f"get_ctx_pct api={api} used={used} limit={limit} pct={pct} msgs={len(self._llm_messages)}")
        return pct

    def _update_mode_prompt(self):
        try:
            pct = self._get_context_percentage()
            self._last_token_pct = pct
            if self._agent_mode:
                text = f"Agent ({pct}%)> " if pct is not None else "Agent> "
                self.console.prompt_label.config(text=text, fg="#5ba3ec")
            elif self._consultor_mode:
                text = f"Consultor ({pct}%)> " if pct is not None else "Consultor> "
                self.console.prompt_label.config(text=text, fg="#e6b422")
            _ctx_log(f"update_prompt pct={pct} agent={self._agent_mode} consul={self._consultor_mode} ok")
        except Exception as e:
            _ctx_log(f"update_prompt ERROR: {e}")
            pass

    def _clear_cache(self):
        try:
            from src.elwand_paths import cache_dir
            d = str(cache_dir())
            if os.path.isdir(d):
                for f in os.listdir(d):
                    p = os.path.join(d, f)
                    if os.path.isfile(p):
                        os.remove(p)
                _ctx_log("cache cleared")
        except Exception as e:
            _ctx_log(f"cache clear ERROR: {e}")

    def _llm_session(self):
        """Stable opencode session id, persisted across restarts."""
        if not self._llm_session_id:
            from src.llm.client import _generate_opencode_id
            self._llm_session_id = _generate_opencode_id("ses_", descending=True)
        return self._llm_session_id

    def _new_llm_request_id(self):
        """Per user-turn opencode request id (shared by tool round-trips)."""
        from src.llm.client import _generate_opencode_id
        self._llm_request_id = _generate_opencode_id("msg_", descending=False)
        return self._llm_request_id

    def _save_session(self):
        if getattr(self, '_closing', False):
            return
        from src.llm import session
        mode = "agent" if self._agent_mode else ("consultor" if self._consultor_mode else None)
        try:
            snapshot = list(self._llm_messages)
            segments = self.console.get_segments()
            session.save(
                snapshot, mode=mode,
                context_injected=self._context_injected,
                total_api_tokens=getattr(self, '_total_api_tokens', 0),
                console_segments=segments,
                session_id=getattr(self, '_llm_session_id', None),
                project_id=getattr(self, '_llm_project_id', None))
        except Exception as e:
            _ctx_log(f"session save ERROR: {e}")

    def _load_session(self):
        from src.llm import session
        data = session.load()
        if not data:
            return None
        msgs = [m for m in data.get("messages", [])
                if not (isinstance(m, dict) and m.get("_is_context"))]
        self._llm_messages = msgs
        self._context_injected = False
        self._total_api_tokens = data.get("total_api_tokens", 0)
        self._llm_session_id = data.get("llm_session_id")
        self._llm_project_id = data.get("llm_project_id")
        segments = data.get("console_segments")
        if segments:
            try:
                self.console.restore_segments(segments)
            except Exception as e:
                _ctx_log(f"console restore ERROR: {e}")
        _ctx_log(f"session loaded msgs={len(msgs)} mode={data.get('mode')} api_tokens={self._total_api_tokens}")
        return data.get("mode")

    def _clear_session(self):
        from src.llm import session
        try:
            session.clear()
        except Exception as e:
            _ctx_log(f"session clear ERROR: {e}")

    @staticmethod
    def _msg_attr(msg, key, default=None):
        if isinstance(msg, dict):
            return msg.get(key, default)
        return getattr(msg, key, default)

    def _repair_messages(self):
        msgs = self._llm_messages
        _ctx_log(f"repair start msgs={len(msgs)}")
        removed = 0
        steps = []
        for i in range(len(msgs) - 1, -1, -1):
            role = self._msg_attr(msgs[i], "role")
            if role == "user":
                self._llm_messages[:] = msgs[:i + 1]
                removed = len(msgs) - (i + 1)
                steps.append(f"i={i} user -> keep")
                break
            if role == "assistant":
                tc = self._msg_attr(msgs[i], "tool_calls")
                if tc:
                    tc_count = len(tc) if isinstance(tc, (list, tuple)) else 0
                    tool_count = 0
                    j = i + 1
                    while j < len(msgs) and self._msg_attr(msgs[j], "role") == "tool":
                        tool_count += 1
                        j += 1
                    if tool_count >= tc_count:
                        self._llm_messages[:] = msgs[:j]
                        removed = len(msgs) - j
                        steps.append(f"i={i} asst+{tc_count}tc tool_count={tool_count} ok -> keep to {j}")
                        break
                    else:
                        self._llm_messages[:] = msgs[:i]
                        removed = len(msgs) - i
                        steps.append(f"i={i} asst+{tc_count}tc tool_count={tool_count} INCOMPLETE -> trunc at {i}")
                        break
                else:
                    self._llm_messages[:] = msgs[:i + 1]
                    removed = len(msgs) - (i + 1)
                    steps.append(f"i={i} asst -> keep")
                    break
            if i >= len(msgs) - 15:
                steps.append(f"i={i} {role} skip")
        else:
            system_msgs = [m for m in msgs if self._msg_attr(m, "role") == "system"]
            self._llm_messages[:] = system_msgs
            removed = len(msgs) - len(system_msgs)
            steps.append("no_valid -> system_only")
        for s in steps[-8:]:
            _ctx_log(f"repair step: {s}")
        _ctx_log(f"repair done removed={removed} msgs={len(self._llm_messages)}")

    def _compact_if_needed(self, force=False):
        from src.llm import compaction
        limit = self._get_model_context_limit()
        api = getattr(self, '_total_api_tokens', 0) or 0
        estimated = self._estimate_tokens(self._llm_messages)
        used = api if api > 0 else estimated
        overflow = compaction.is_overflow(used, limit)
        _ctx_log(f"compact check msgs={len(self._llm_messages)} api={api} est={estimated} used={used} limit={limit} overflow={overflow} force={force}")
        if not force and not overflow:
            return False
        before = len(self._llm_messages)
        _ctx_log(f"compact start before={before} est={estimated} limit={limit}")
        t0 = _datetime.datetime.now()
        self.console.after(0, self.console.block_input)
        self.console.after(0, lambda: self.console._set_spinner_color("#ce9178"))
        try:
            from src.llm import LLMClient
            client = LLMClient(purpose="agent", request_id=self._llm_request_id,
                               session_id=self._llm_session(),
                               project_id=self._llm_project_id)
            self.console.after(0, lambda: self.console.warning("Compacting context..."))
            ok = compaction.compact_messages(self._llm_messages, client, limit)
            elapsed = (_datetime.datetime.now() - t0).total_seconds()
            if ok:
                after = len(self._llm_messages)
                _ctx_log(f"compact done ok=True before={before} after={after} elapsed={elapsed:.2f}s")
                self._total_api_tokens = 0
                self._save_session()
                self.console.after(0, lambda: self.console.info(
                    f"Context compacted ({before} → {after} messages)"))
                self.console.after(0, self._update_mode_prompt)
                return True
            else:
                _ctx_log(f"compact done ok=False before={before} elapsed={elapsed:.2f}s")
                self.console.after(0, lambda: self.console.warning("Compaction skipped."))
                return False
        except Exception as e:
            elapsed = (_datetime.datetime.now() - t0).total_seconds()
            _ctx_log(f"compact error after={elapsed:.2f}s {type(e).__name__}: {e}")
            self.console.after(0, lambda m=str(e): self.console.error(f"Compaction error: {m}"))
            return False
        finally:
            self.console.after(0, self.console.unblock_input)
            self.console.after(0, lambda: self.console._set_spinner_color("#5ba3ec"))

    def _enter_agent_mode(self):
        self._agent_mode = True
        import threading
        if self._agent_stop_event is None:
            self._agent_stop_event = threading.Event()
        self._last_token_pct = None
        if not self._silent_mode_cycle:
            self.console.info(
                "Agent mode. Commands: exit, stop, reset, compact, clear, menu."
            )
        self.console.set_mode_handler(self._agent_handler, "Agent", "#5ba3ec",
            commands={"exit": "Quit Elwand", "stop": "Interrupt execution",
                      "reset": "Clear conversation and cache", "compact": "Compact context",
                      "clear": "Clear the console", "menu": "Show help"})
        self._update_mode_prompt()

    def _agent_handler(self, text):
        text = text.strip()
        if text.lower() == "exit" or not text:
            self._on_close()
            return
        if text.lower() == "stop":
            if self._agent_stop_event:
                self._agent_stop_event.set()
            self.console.warning("Interrupting agent execution...")
            return
        if text.lower() == "clear":
            self.console._cmd_clear([])
            return
        if text.lower() == "reset":
            self._llm_messages = []
            self._llm_request_id = None
            self._llm_session_id = None
            self._last_ctx_hash = None
            self._last_token_pct = None
            self._total_api_tokens = 0
            self._context_injected = False
            self._clear_cache()
            self._clear_session()
            self.console.success("Context reset. Conversation history and cache cleared.")
            self._update_mode_prompt()
            return
        if text.lower() == "menu":
            self.console.info(
                "Agent mode commands:\n"
                "  exit    - Quit Elwand\n"
                "  stop    - Interrupt the current agent execution\n"
                "  reset   - Clear conversation history, clear cache, start fresh\n"
                "  compact - Manually compact the conversation context\n"
                "  clear   - Clear the console display\n"
                "  menu    - Show this help"
            )
            return
        if text.lower() == "compact":
            import threading
            self.console._start_thinking_ui()
            def _compact():
                self._compact_if_needed(force=True)
                self._save_session()
                self.console.stop_thinking()
            threading.Thread(target=_compact, daemon=True).start()
            return
        self._agent_ask(text)

    def _leave_agent_mode(self):
        self._agent_mode = False
        self.console.set_mode_handler(None)
        self.console.prompt_label.config(text="Elwand> ", fg="#ffffff")
        if not self._silent_mode_cycle:
            self.console.info("Left agent mode.")

    def _make_stream_emitter(self, color, display, clean_fn=None):
        self.console.reset_markdown_state()
        buf = [""]
        first = [True]
        def _clean(text):
            return clean_fn(text) if clean_fn else text
        def _emit(delta):
            if getattr(self, '_closing', False):
                return
            buf[0] += delta
            if "\n" not in buf[0]:
                return
            lines = buf[0].split("\n")
            for line in lines[:-1]:
                text = _clean(line).rstrip()
                if text.strip():
                    if first[0]:
                        first[0] = False
                        self._safe_after(lambda l=text: self.console.role_mark(l, color))
                    else:
                        self._safe_after(lambda l=text: display(l))
            buf[0] = lines[-1]
        def _flush():
            if getattr(self, '_closing', False):
                return
            text = _clean(buf[0]).rstrip()
            if text.strip():
                if first[0]:
                    first[0] = False
                    self._safe_after(lambda l=text: self.console.role_mark(l, color))
                else:
                    self._safe_after(lambda l=text: display(l))
            buf[0] = ""
            first[0] = True
            self._safe_after(lambda: self.console.flush_markdown())
        return _emit, _flush

    def _make_tool_logger(self, stop):
        def _tool_display(name, result):
            if name in ("check_machine", "check_status", "check_inventory", "check_domain", "list_repo"):
                return result.split("\n")[0] + "..."
            if name == "webfetch":
                return f"fetched {len(result)} chars"
            if name == "websearch":
                return f"searched ({len(result)} chars)"
            if name == "read_cache":
                return f"read {len(result.split(chr(10)))} lines"
            if name in ("poc_exec", "poc_read", "poc_write", "poc_edit"):
                return f"poc {len(result)} chars"
            if name in ("report_read", "report_write"):
                return f"report {len(result)} chars"
            if name == "port_inspector":
                return "inventoried"
            if len(result) > 120:
                return result[:117] + "..."
            return result

        def _on_tool(name, args, result):
            if stop is not None and stop.is_set():
                return
            display = _tool_display(name, result)
            try:
                self.console.after(0, lambda d=display: self.console.info(
                    f"  [tool] {name} {str(args)[:60]} → {d} (~{len(result)//4} tokens)"))
            except RuntimeError:
                pass

        return _on_tool

    def _agent_ask(self, prompt):
        import threading, re
        if getattr(self, '_llm_running', False):
            self.console.warning("Still processing the previous request. Use 'stop' to interrupt first.")
            return
        self._llm_running = True
        self._agent_stop_event = threading.Event()
        _tool_xml_re = re.compile(r'<[^>]*DSML', re.IGNORECASE)
        def _clean(text):
            return _tool_xml_re.sub('', text)
        self._inject_context()
        self._llm_messages.append({"role": "user", "content": prompt})
        self._new_llm_request_id()
        self._llm_session()
        self._save_session()
        def _run():
            self.console.start_thinking()
            stop = self._agent_stop_event
            self._compact_if_needed()
            msg_before = len(self._llm_messages)
            succeeded = False
            _ctx_log(f"agent_ask start msgs={len(self._llm_messages)} prompt_len={len(prompt)}")
            _emit, _flush = self._make_stream_emitter("#5ba3ec", self.console.agent, clean_fn=_clean)
            try:
                from src.llm import LLMClient
                client = LLMClient(purpose="agent", request_id=self._llm_request_id,
                                   session_id=self._llm_session_id,
                                   project_id=self._llm_project_id)
                _on_tool = self._make_tool_logger(stop)
                content = client.chat_with_tools(
                    self._llm_messages, on_tool=_on_tool, tool_context=self,
                    on_text=_emit,
                    on_warning=lambda msg: self._safe_after(
                        lambda m=msg: self.console.warning(m)),
                    stop_event=stop, on_flush=_flush)
                _flush()
                if stop is not None and stop.is_set():
                    self._safe_after(lambda: self.console.warning("Agent stopped."))
                    return
                self._safe_after(lambda: setattr(self, '_total_api_tokens', client.last_prompt_tokens))
                _ctx_log(f"agent_ask tokens={client.last_prompt_tokens} msgs={len(self._llm_messages)} after_stream")
                if content is None:
                    self._safe_after(lambda: self.console.info("  (no response)"))
                    return
                self._llm_messages.append({"role": "assistant", "content": _clean(content)})
                self._safe_after(lambda: self.console.writeln(""))
                self._safe_after(self._update_mode_prompt)
                succeeded = True
                _ctx_log(f"agent_ask success msgs={len(self._llm_messages)} pct={self._get_context_percentage()}")
            except Exception as e:
                _ctx_log(f"agent_ask ERROR: {e}")
                err_str = str(e).lower()
                if "tool_calls" in err_str or "tool_call_id" in err_str:
                    tail = self._llm_messages[-30:]
                    roles = []
                    for m in tail:
                        r = self._msg_attr(m, "role")
                        tc = self._msg_attr(m, "tool_calls")
                        if r == "assistant" and tc:
                            r += "+tc"
                        roles.append(r)
                    _ctx_log(f"repair pre_dump msgs={len(self._llm_messages)} roles={' '.join(roles)}")
                    self._repair_messages()
                    self._save_session()
                if stop is not None and not stop.is_set():
                    try:
                        self.console.after(0, lambda m=str(e): self.console.error(f"Agent error: {m}"))
                    except RuntimeError:
                        pass
                try:
                    self.console.after(0, self._update_mode_prompt)
                except RuntimeError:
                    pass
            finally:
                self.console.stop_thinking()
                if not succeeded and not (stop is not None and stop.is_set()):
                    try:
                        safe = getattr(client, '_safe_len', msg_before)
                        del self._llm_messages[safe:]
                    except (IndexError, AttributeError):
                        pass
                self._save_session()
                self._llm_running = False
        threading.Thread(target=_run, daemon=True).start()

    def _consultor_ask(self, prompt):
        import threading
        if getattr(self, '_llm_running', False):
            self.console.warning("Still processing the previous request. Use 'stop' to interrupt first.")
            return
        self._llm_running = True
        self._agent_stop_event = threading.Event()
        self._inject_context()
        self._llm_messages.append({"role": "user", "content": prompt})
        self._new_llm_request_id()
        self._llm_session()
        self._save_session()
        def _run():
            self.console.start_thinking()
            stop = self._agent_stop_event
            self._compact_if_needed()
            succeeded = False
            _emit, _flush = self._make_stream_emitter("#e6b422", self.console.consultor)
            try:
                from src.llm import LLMClient
                from src.llm.tools import CONSULTOR_TOOLS
                client = LLMClient(request_id=self._llm_request_id,
                                   session_id=self._llm_session_id,
                                   project_id=self._llm_project_id)
                _on_tool = self._make_tool_logger(stop)
                content = client.chat_with_tools(
                    self._llm_messages, tool_context=self, allowed_tools=CONSULTOR_TOOLS,
                    on_tool=_on_tool, on_text=_emit,
                    on_warning=lambda msg: self._safe_after(
                        lambda m=msg: self.console.warning(m)),
                    stop_event=stop, on_flush=_flush)
                _flush()
                if stop is not None and stop.is_set():
                    self._safe_after(lambda: self.console.warning("Consultor stopped."))
                    return
                self._safe_after(lambda: setattr(self, '_total_api_tokens', client.last_prompt_tokens))
                if content is None:
                    self._safe_after(lambda: self.console.info("  (no response)"))
                    return
                self._llm_messages.append({"role": "assistant", "content": content})
                self._safe_after(lambda: self.console.writeln(""))
                self._safe_after(self._update_mode_prompt)
                succeeded = True
            except Exception as e:
                self._safe_after(lambda m=str(e): self.console.error(f"Consultor error: {m}"))
            finally:
                self.console.stop_thinking()
                if not succeeded:
                    try:
                        self._llm_messages.pop()
                    except (IndexError, AttributeError):
                        pass
                self._save_session()
                self._llm_running = False
        threading.Thread(target=_run, daemon=True).start()

    def _build_model_context(self):
        parts = ["Elwand state:"]
        from src.machines import store, domain_db
        machines = store.get_all()
        if machines:
            items = ", ".join(
                f"#{m.id} {m.ip}" for m in machines)
            parts.append(f"Machines: {items}.")
        domains = domain_db.list_all()
        if domains:
            parts.append(f"Domains: {', '.join(domains)}.")
        if not machines and not domains:
            parts.append("No machines or domains.")
        parts.append(
            "Use check_status for details, "
            "check_inventory for inventory.")
        return " ".join(parts)

    def _inject_context(self):
        if self._context_injected:
            return
        ctx = self._build_model_context()
        self._llm_messages.insert(0, {
            "role": "system", "content": ctx, "_is_context": True})
        self._context_injected = True
        _ctx_log(f"inject_context len={len(ctx)} msgs={len(self._llm_messages)}")

    @staticmethod
    def _normalize_msg(msg):
        def _a(obj, key, default=None):
            if isinstance(obj, dict):
                return obj.get(key, default)
            return getattr(obj, key, default)

        if isinstance(msg, dict):
            r = dict(msg)
            r["_type"] = "dict"
            tc = r.get("tool_calls")
            if tc:
                r["tool_calls"] = [
                    {
                        "id": _a(t, "id"),
                        "function": {
                            "name": _a(_a(t, "function", {}), "name", "?"),
                            "arguments": _a(_a(t, "function", {}), "arguments", ""),
                        },
                    }
                    for t in tc
                ]
            return r
        r = {
            "role": _a(msg, "role", "?"),
            "content": _a(msg, "content", None),
            "_type": type(msg).__name__,
        }
        tc = _a(msg, "tool_calls", None)
        if tc:
            r["tool_calls"] = [
                {
                    "id": _a(t, "id"),
                    "function": {
                        "name": _a(_a(t, "function", None), "name", "?"),
                        "arguments": _a(_a(t, "function", None), "arguments", ""),
                    },
                }
                for t in tc
            ]
        return r

    def _cmd_exit(self, args):
        self._on_close()

    def _run_system(self, cmd):
        threading.Thread(target=self._run_system_thread, args=(cmd,), daemon=True).start()

    def _run_system_thread(self, cmd):
        _dbg(f"[system] started: {cmd}")
        args = cmd.split()
        monitor_nmap = None
        if args and args[0].lower() == "nmap":
            for arg in args[1:]:
                if re.match(r"^\d+\.\d+\.\d+\.\d+$", arg):
                    machine = store.get(arg)
                    if machine:
                        monitor_nmap = machine
                        _dbg(f"[system] nmap monitoring for machine #{machine.id} ({arg})")
                    break
        try:
            shell = os.environ.get("SHELL", "/bin/sh")
            proc = subprocess.Popen(
                [shell, "-i", "-c", cmd],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                text=True, bufsize=1,
            )
            self._system_process = proc
            for line in proc.stdout:
                if not self.console.winfo_exists():
                    break
                stripped = line.rstrip()
                if stripped:
                    self.console.after(0, lambda l=stripped: self.console.body(l))
                if monitor_nmap:
                    m = re.match(r"Discovered open port (\d+)/(tcp|udp) on \S+", stripped)
                    if m:
                        port = int(m.group(1))
                        proto = m.group(2)
                        if proto == "udp":
                            if machine_db.save_udp_port(monitor_nmap.id, port):
                                self.console.after(0, lambda p=port, mid=monitor_nmap.id: self.console.success(
                                    f"  nmap: added UDP port {p} to machine #{mid}"
                                ))
                        else:
                            if machine_db.save_tcp_port(monitor_nmap.id, port):
                                self.console.after(0, lambda p=port, mid=monitor_nmap.id: self.console.success(
                                    f"  nmap: added port {p} to machine #{mid}"
                                ))
            proc.wait()
            if self._system_process is proc:
                self._system_process = None
            if proc.returncode != 0 and self.console.winfo_exists():
                self.console.after(0, lambda: self.console.warning(f"exit code: {proc.returncode}"))
        except Exception as e:
            if self.console.winfo_exists():
                self.console.after(0, lambda: self.console.error(f"System command failed: {e}"))

    def _stop_system(self):
        if self._system_process:
            self._system_process.kill()
            self.console.info("Process stopped")

    def _cmd_ping(self, args):
        if not args:
            self.console.body("Usage: ping <ip|id>")
            return
        target = args[0]
        ip = target
        if re.match(r"^\d+$", ip):
            mid = int(ip)
            for m in store.get_all():
                if m.id == mid:
                    ip = m.ip
                    break
            else:
                self.console.warning(f"No machine with ID #{mid}")
                return
        self.console.body(f"Pinging {ip}...")
        threading.Thread(target=self._run_ping, args=(ip,), daemon=True).start()

    def _run_ping(self, ip):
        result = _do_ping(ip)
        if result is None:
            self.console.after(0, lambda: self.console.warning(f"{ip}: no response"))
        else:
            rtt_ms, ttl = result
            ttl_part = f"  ttl={ttl}" if ttl is not None else ""
            self.console.after(0, lambda: self.console.success(f"{ip}: time={rtt_ms:.1f}ms{ttl_part}"))

    def _cmd_nslookup(self, args):
        if not args:
            self.console.body("Usage: nslookup <domain|ip|id>")
            return
        target = args[0]
        if re.match(r"^\d+$", target):
            mid = int(target)
            for m in store.get_all():
                if m.id == mid:
                    target = m.ip
                    break
            else:
                self.console.warning(f"No machine with ID #{mid}")
                return
        threading.Thread(target=self._run_nslookup, args=(target,), daemon=True).start()

    def _run_nslookup(self, target):
        self.console.after(0, lambda: self.console.info(f"nslookup {target}..."))
        result = _do_nslookup(target)
        self.console.after(0, lambda: self.console.body(result))

    def _cmd_domain(self, args):
        if not args:
            self.console.body("Usage: add-domain <name>")
            return
        domain = args[0].strip()
        threading.Thread(target=self._run_domain, args=(domain,), daemon=True).start()

    def _cmd_add(self, args):
        if not args:
            self.console.body("Usage: add <machine|domain|credential|user|password|hash>")
            return
        sub = args[0].lower()
        rest = args[1:]
        if sub == "machine":
            self._cmd_add_machine(rest)
        elif sub == "domain":
            self._cmd_domain(rest)
        elif sub == "credential":
            self._cmd_add_credential(rest)
        elif sub == "user":
            self._cmd_add_user(rest)
        elif sub == "password":
            self._cmd_add_password(rest)
        elif sub == "hash":
            self._cmd_add_hash(rest)
        elif sub == "people":
            self._cmd_add_people(rest)
        elif sub == "dictionary":
            self._cmd_add_file("dictionary", rest)
        elif sub == "rule":
            self._cmd_add_file("rule", rest)
        else:
            self.console.error(f"Unknown add target: {sub}")

    def _cmd_add_file(self, file_type, args):
        from tkinter import filedialog
        if file_type == "dictionary":
            from src.elwand_paths import lst_dir
            dst_dir = str(lst_dir())
            title = "Select dictionary file"
        else:
            from src.elwand_paths import rules_dir
            dst_dir = str(rules_dir())
            title = "Select rule file"
        path = filedialog.askopenfilename(
            parent=self, title=title,
            filetypes=[("All files", "*.*")],
        )
        if not path:
            return
        fname = os.path.basename(path)
        dst = os.path.join(dst_dir, fname)
        try:
            shutil.copy2(path, dst)
            self.console.success(f"{file_type.capitalize()} '{fname}' added")
        except OSError as e:
            self.console.error(f"Failed to copy file: {e}")

    def _run_domain(self, domain):
        self.console.after(0, lambda: self.console.info(f"Resolving {domain}..."))
        try:
            info = socket.getaddrinfo(domain, None, socket.AF_INET, socket.SOCK_STREAM)
            if not info:
                self.console.after(0, lambda: self.console.warning(f"{domain} could not be resolved"))
                return
            ip = info[0][4][0]
        except socket.gaierror:
            self.console.after(0, lambda: self.console.warning(f"{domain} could not be resolved"))
            return

        machine = store.get(ip)
        if machine:
            machine_db.save_domain(machine.id, domain, "manual")
            domain_db.init_or_update(domain, machine.id, machine.ip, "manual")
            self.console.after(0, lambda: self.console.success(
                f"{domain} → {ip}  (added to machine #{machine.id})"
            ))
        else:
            machine = store.add_or_update(ip=ip, method="manual")
            machine.device_type = "device unknown"
            machine_db.save_machine_info(machine)
            machine_db.save_domain(machine.id, domain, "manual")
            domain_db.init_or_update(domain, machine.id, machine.ip, "manual")
            self.console.after(0, lambda: self.console.success(
                f"{domain} → {ip}  (new machine #{machine.id})"
            ))

    def _cmd_add_machine(self, args):
        if not args:
            self.console.body("Usage: add machine <ip>")
            return
        ip = args[0]
        if not re.match(r"^\d+\.\d+\.\d+\.\d+$", ip):
            self.console.body("Usage: add machine <ip>")
            return
        machine = store.add_or_update(ip=ip, method="manual")
        machine.device_type = "device unknown"
        machine_db.save_machine_info(machine)
        self.console.success(f"Machine #{machine.id} ({ip}) added")

    def _cmd_add_credential(self, args):
        from src.machines.credential_db import save_credential, save_user, load_users
        from .views.user_pass import _ntlm_hash
        if len(args) < 2:
            self.console.body("Usage: add credential <username> <password|hash_nt>")
            return
        username = args[0]
        secret = args[1]
        domain = ""
        for u in load_users():
            if u["username"] == username:
                domain = u.get("domain", "")
                break
        nt_pattern = re.compile(r"^[a-fA-F0-9]{32}$")
        if nt_pattern.match(secret):
            cid = save_credential(username, "", domain=domain, hash_nt=secret, hash_nt_origin="manual")
            self.console.success(f"Credential #{cid}: {username} (NT hash) added")
        else:
            hnt = _ntlm_hash(secret)
            cid = save_credential(username, secret, domain=domain, hash_nt=hnt, password_origin="manual", hash_nt_origin="manual")
            self.console.success(f"Credential #{cid}: {username} / {secret} added")
        save_user(username)

    def _cmd_add_user(self, args):
        if not args:
            self.console.body(
                "Usage: add user <username> [local|domain] [origin] [machine_or_domain] "
                "[groups]"
            )
            return
        from src.machines.credential_db import save_user
        username = args[0]
        utype = args[1] if len(args) > 1 else ""
        origin = args[2] if len(args) > 2 else "manual"
        extra = args[3] if len(args) > 3 else ""
        groups = args[4] if len(args) > 4 else ""
        machine = extra if utype == "local" else ""
        domain = extra if utype == "domain" else ""
        save_user(username, origin=origin, utype=utype,
                  machine=machine, domain=domain, groups=groups)
        self.console.success(f"User '{username}' added")

    def _cmd_add_password(self, args):
        if not args:
            self.console.body("Usage: add password <password>")
            return
        from src.machines.credential_db import save_password
        save_password(args[0])
        self.console.success("Password added")

    def _cmd_add_hash(self, args):
        if not args:
            from .dialogs.hashcat import HashcatDialog
            HashcatDialog(self, active_tab=2)
            return
        if len(args) < 2:
            self.console.body("Usage: add hash <type> <hash>")
            return
        hash_type = args[0]
        resolved = self._resolve_hash_type(hash_type)
        if resolved:
            hash_type = resolved
        from src.machines.credential_db import save_hash_entry
        hid = save_hash_entry(hash_type, args[1], origin="manual")
        self.console.success(f"Hash #{hid} added")

    def _cmd_add_people(self, args):
        if not args:
            self.console.body(
                "Usage: add people <first_name> <last_name> "
                "[company] [domain] [username] [role] [linkedin_url] "
                "[source] [interests]"
            )
            return
        from src.machines.people_db import save_person
        pid = save_person(
            first_name=args[0] if len(args) > 0 else "",
            last_name=args[1] if len(args) > 1 else "",
            company=args[2] if len(args) > 2 else "",
            domain=args[3] if len(args) > 3 else "",
            username=args[4] if len(args) > 4 else "",
            role=args[5] if len(args) > 5 else "",
            linkedin_url=args[6] if len(args) > 6 else "",
            source=args[7] if len(args) > 7 else "manual",
            interests=args[8] if len(args) > 8 else "",
        )
        self.console.success(f"Person #{pid} added")

    @staticmethod
    def _resolve_hash_type(type_str):
        if not type_str.isdigit():
            return None
        mode = int(type_str)
        import sqlite3
        from src.elwand_paths import hashcat_db
        try:
            with sqlite3.connect(str(hashcat_db())) as conn:
                row = conn.execute(
                    "SELECT \"Hash-Name\" FROM DefaultMode WHERE \"Hash-Mode\" = ?", (mode,)
                ).fetchone()
            if row and row[0]:
                return row[0]
        except (sqlite3.DatabaseError, sqlite3.OperationalError):
            pass
        return None

    def _cmd_fuzz(self, args):
        from .dialogs.fuzz import FuzzDialog
        if args and args[0].lower() == "stop":
            if self._fuzz_dlg:
                self._fuzz_dlg._stop()
            if hasattr(self, '_fuzz_engine') and self._fuzz_engine:
                self._fuzz_engine.stop()
                self._fuzz_engine = None
            self.console.info("Fuzzer stopped")
            return
        if not args:
            self._fuzz_dlg = FuzzDialog(self)
            return

        method = args[0].lower()
        if method not in ("dir", "vhost", "dns"):
            self.console.body("Usage: use fuzzer <dir|vhost|dns> <target> ...")
            return

        if len(args) < 2:
            self.console.body(f"Usage: use fuzzer {method} <target> ...")
            return
        target = args[1]

        if method == "dir":
            port = 80
            wordlist = None
            if len(args) >= 4:
                if args[2].isdigit():
                    port = int(args[2])
                    wordlist = args[3]
                else:
                    wordlist = args[2]
            elif len(args) == 3:
                wordlist = args[2]
            else:
                self.console.body("Usage: use fuzzer dir <target> <wordlist> [port]")
                return
            if not wordlist:
                self.console.body("Usage: use fuzzer dir <target> <wordlist> [port]")
                return
            from src.elwand_paths import lst_dir
            wl_path = os.path.join(str(lst_dir()), wordlist)
            if not os.path.isfile(wl_path):
                self.console.error(f"Wordlist not found: {wordlist}")
                return
            ip = self._resolve_to_ip(target)
            display_target = ip or target
            url_template = f"http://{display_target}:{port}/FUZZ"
            show_codes = {200, 201, 204, 301, 302, 307, 400, 401, 403, 405, 500, 502, 503}
            def _emit_dir(text, color=None):
                stripped = text.rstrip("\n")
                c = {"success": "success", "error": "error", "info": "info"}.get(color)
                if c:
                    getattr(self.console, c)(stripped)
                else:
                    self.console.body(stripped)
            self.console.after(0, lambda: self.console.info(
                f"Directory fuzzing {url_template.replace('FUZZ', '')} with {wordlist} ({port}/tcp)"))
            from src.tools.fuzz import FuzzEngine
            engine = FuzzEngine(
                target=display_target, wordlist_path=wl_path,
                method="directory", url_template=url_template,
                workers=50, show_codes=show_codes,
                on_result=lambda t, c=None: self.console.after(0, _emit_dir, t, c),
            )
            self._fuzz_engine = engine
            engine.start()

        elif method == "vhost":
            if len(args) < 3:
                self.console.body("Usage: use fuzzer vhost <target> <wordlist>")
                return
            wordlist = args[2]
            from src.elwand_paths import lst_dir
            wl_path = os.path.join(str(lst_dir()), wordlist)
            if not os.path.isfile(wl_path):
                self.console.error(f"Wordlist not found: {wordlist}")
                return
            ip = self._resolve_to_ip(target)
            show_codes = {200, 201, 204, 301, 302, 307, 400, 401, 403, 405, 500, 502, 503}
            def _emit_vhost(text, color=None):
                stripped = text.rstrip("\n")
                c = {"success": "success", "error": "error", "info": "info"}.get(color)
                if c:
                    getattr(self.console, c)(stripped)
                else:
                    self.console.body(stripped)
            self.console.after(0, lambda: self.console.info(
                f"Vhost fuzzing {target} with {wordlist}"))
            from src.tools.fuzz import FuzzEngine
            engine = FuzzEngine(
                target=target, wordlist_path=wl_path,
                method="vhost", target_ip=ip,
                workers=50, show_codes=show_codes,
                on_result=lambda t, c=None: self.console.after(0, _emit_vhost, t, c),
            )
            self._fuzz_engine = engine
            engine.start()

        elif method == "dns":
            if len(args) < 3:
                self.console.body("Usage: use fuzzer dns <target> <wordlist>")
                return
            wordlist = args[2]
            from src.elwand_paths import lst_dir
            wl_path = os.path.join(str(lst_dir()), wordlist)
            if not os.path.isfile(wl_path):
                self.console.error(f"Wordlist not found: {wordlist}")
                return
            show_codes = {200, 201, 204, 301, 302, 307, 400, 401, 403, 405, 500, 502, 503}
            def _emit_dns(text, color=None):
                stripped = text.rstrip("\n")
                c = {"success": "success", "error": "error", "info": "info"}.get(color)
                if c:
                    getattr(self.console, c)(stripped)
                else:
                    self.console.body(stripped)
            self.console.after(0, lambda: self.console.info(
                f"DNS fuzzing {target} with {wordlist}"))
            from src.tools.fuzz import FuzzEngine
            engine = FuzzEngine(
                target=target, wordlist_path=wl_path,
                method="dns",
                workers=50, show_codes=show_codes,
                on_result=lambda t, c=None: self.console.after(0, _emit_dns, t, c),
            )
            self._fuzz_engine = engine
            engine.start()

    def _cmd_ftp(self, args):
        if not args:
            from .dialogs.remote_access import RemoteAccessDialog
            RemoteAccessDialog(self)
            self.visualizer.activate_view("shells")
            return

        target = args[0]
        ip = target
        if re.match(r"^\d+$", ip):
            machine_id = int(ip)
            machine = None
            for m in store.get_all():
                if m.id == machine_id:
                    machine = m
                    break
            if machine:
                ip = machine.ip
            else:
                self.console.warning(f"No machine with ID #{machine_id}")
                return

        port = 21
        cred_user = ""
        cred_pass = ""
        if len(args) >= 2:
            if re.match(r"^\d+$", args[1]):
                port = int(args[1])
                if len(args) >= 3:
                    cred_user = args[2]
            else:
                cred_user = args[1]

        if cred_user:
            from src.machines import credential_db
            for c in credential_db.load_credentials():
                if c.get("username") == cred_user:
                    cred_pass = c.get("password") or ""
                    break

        self.console.info(f"Connecting FTP to {ip}:{port}...")
        threading.Thread(
            target=self._run_ftp_connect,
            args=(ip, port, cred_user, cred_pass),
            daemon=True,
        ).start()
        self.visualizer.activate_view("shells")

    def _run_ftp_connect(self, host, port, user, password):
        from src.shells.ftp_shell import FTPConnectionThread

        def on_connected(sid):
            self.console.after(0, lambda: self.console.success(
                f"FTP session #{sid} to {host}:{port}"
            ))

        def on_error(msg):
            self.console.after(0, lambda: self.console.error(f"FTP failed: {msg}"))

        ftp_thread = FTPConnectionThread(
            host, port, user, password,
            on_connected=on_connected,
            on_error=on_error,
        )
        ftp_thread.start()

    def _cmd_recorder(self, args):
        if not args:
            from src.tools.webrecorder import find_browsers
            from .dialogs.recorder_dialog import WebRecorderDialog
            browsers = find_browsers()
            if not browsers:
                self.console.error(
                    "No supported browser found (chromium-based). Install Chrome, Chromium, or Brave."
                )
                return
            dialog = WebRecorderDialog(self, browsers)
            if not dialog.result:
                return
            threading.Thread(target=self._run_recorder_dialog, args=(dialog.result,), daemon=True).start()
            return
        sub = args[0].lower()
        if sub == "stop":
            if self._recorder and self._recorder.is_running():
                self._recorder.stop()
                self._recorder.kill_browser()
                self._recorder = None
                self.console.info("Recorder stopped")
            else:
                self.console.warning("No webrecorder is running.")
            return
        target = sub
        if re.match(r"^\d+$", target):
            mid = int(target)
            for m in store.get_all():
                if m.id == mid:
                    target = m.ip
                    break
            else:
                self.console.warning(f"No machine with ID #{mid}")
                return
        if self._recorder and self._recorder.is_running():
            self.console.warning("A webrecorder is already running. Use 'webrecorder stop' first.")
            return
        threading.Thread(target=self._run_recorder, args=(target,), daemon=True).start()

    def _run_recorder_dialog(self, config):
        from src.tools.webrecorder import Recorder
        import tkinter as tk
        import threading

        name = config["name"]
        target = config["target"]
        browser_path = config["browser"]
        scope = config.get("scope")
        review_outgoing = config.get("review_mode", False)
        review_incoming = config.get("review_mode", False)

        label = os.path.basename(browser_path)
        self.console.after(0, lambda l=label: self.console.info(f"Using {l}"))

        def on_log(text, color=None):
            if color == "success":
                self.console.after(0, lambda t=text: self.console.success(t.rstrip()))
            elif color == "error":
                self.console.after(0, lambda t=text: self.console.error(t.rstrip()))
            elif color == "info":
                self.console.after(0, lambda t=text: self.console.info(t.rstrip()))
            else:
                self.console.after(0, lambda t=text: self.console.body(t.rstrip()))

        review_mgr = _ReviewDialogManager(self)
        if review_outgoing or review_incoming:
            review_mgr.show_waiting()

        def on_review_request(url, method, headers, body, res_type, net_id, stage, on_send,
                               resp_status=None, resp_status_text=None, resp_headers=None,
                               resp_body=""):
            done = threading.Event()
            review_mgr.add(url, method, headers, body, res_type, stage, on_send, done,
                           resp_status, resp_status_text, resp_headers, resp_body)
            done.wait()

        review_kw = {}
        if review_outgoing or review_incoming:
            review_kw["review_mode"] = True
            review_kw["on_review_request"] = on_review_request

        self._recorder = Recorder(target, browser_path, on_log=on_log, evidence_name=name,
                                   scope=scope, **review_kw)
        self._recorder.start()

        while self._recorder and self._recorder.is_running():
            import time
            time.sleep(1)
        review_mgr.close()

    def _run_recorder(self, target):
        from src.tools.webrecorder import find_browsers, BrowserSelector, Recorder
        from src.tools.webrecorder import evidence

        browsers = find_browsers()
        if not browsers:
            self.console.after(0, lambda: self.console.error(
                "No supported browser found (chromium-based). Install Chrome, Chromium, or Brave."
            ))
            return

        if len(browsers) > 1:
            dialog = BrowserSelector(self, browsers)
            if not dialog.result:
                self.console.after(0, lambda: self.console.warning("Recorder cancelled."))
                return
            browser_path = dialog.result
        else:
            browser_path = list(browsers.keys())[0]

        label = list(browsers.values())[0] if len(browsers) == 1 else os.path.basename(browser_path)
        self.console.after(0, lambda l=label: self.console.info(f"Using {l}"))

        def on_log(text, color=None):
            if color == "success":
                self.console.after(0, lambda t=text: self.console.success(t.rstrip()))
            elif color == "error":
                self.console.after(0, lambda t=text: self.console.error(t.rstrip()))
            elif color == "info":
                self.console.after(0, lambda t=text: self.console.info(t.rstrip()))
            else:
                self.console.after(0, lambda t=text: self.console.body(t.rstrip()))

        self._recorder = Recorder(target, browser_path, on_log=on_log)
        self._recorder.start()

    def _cmd_delete(self, args):
        if not args:
            self.console.body("Usage: delete <all|dbs|inventory|machine|domain|user|credential|password|hash|handshake|people|shell|evidence|poc|report|dictionary|rule|cache|wifi>")
            return
        sub = args[0].lower()
        if sub == "all":
            self._cmd_delete_all()
        elif sub == "dbs":
            self._cmd_delete_dbs(args[1:])
        elif sub == "credential":
            self._cmd_delete_credential(args[1:])
        elif sub == "evidence":
            self._cmd_delete_evidence_single(args[1:])
        elif sub == "hash":
            self._cmd_delete_hash(args[1:])
        elif sub == "handshake":
            self._cmd_delete_handshake(args[1:])
        elif sub == "machine":
            self._cmd_delete_machine(args[1:])
        elif sub == "domain":
            self._cmd_delete_domain(args[1:])
        elif sub == "user":
            self._cmd_delete_user(args[1:])
        elif sub == "password":
            self._cmd_delete_password(args[1:])
        elif sub == "shell":
            self._cmd_delete_shell(args[1:])
        elif sub == "people":
            self._cmd_delete_people(args[1:])
        elif sub == "dictionary":
            self._cmd_delete_dictionary(args[1:])
        elif sub == "rule":
            self._cmd_delete_rule(args[1:])
        elif sub == "poc":
            self._cmd_delete_poc(args[1:])
        elif sub == "report":
            self._cmd_delete_report(args[1:])
        elif sub == "inventory":
            self._cmd_delete_inventory(args[1:])
        elif sub == "cache":
            self._cmd_delete_cache(args[1:])
        elif sub == "wifi":
            self._cmd_delete_wifi()
        else:
            self.console.error(f"Unknown delete target: {sub}.")

    def _cmd_delete_wifi(self):
        from src.tools.scanner import wifi_monitor
        wifi_monitor.clear()
        self.console.success("WiFi networks and probes cleared.")

    def _cmd_delete_creds(self, args):
        from src.machines.credential_db import delete_all
        delete_all()
        self.console.info("All credentials data cleared")

    def _cmd_delete_credential(self, args):
        if not args:
            self.console.body("Usage: delete credential <username|all>")
            return
        from src.machines.credential_db import load_credentials, delete_credential
        username = args[0]
        if username == "all":
            count = 0
            for c in list(load_credentials()):
                delete_credential(c["id"])
                count += 1
            self.console.success(f"{count} credentials deleted")
            return
        for c in load_credentials():
            if c["username"] == username:
                delete_credential(c["id"])
                self.console.success(f"Credential '{username}' deleted")
                return
        self.console.warning(f"No credential found for: {username}")

    def _cmd_delete_evidence_single(self, args):
        import shutil
        from src.elwand_paths import evidence_dir
        if not args:
            self.console.body("Usage: delete evidence <name|all>")
            return
        name = args[0]
        base = str(evidence_dir())
        if name == "all":
            if os.path.isdir(base):
                shutil.rmtree(base)
                os.makedirs(base, exist_ok=True)
            self.console.info("All evidence data cleared")
            return
        path = os.path.join(base, name)
        if not os.path.isdir(path):
            self.console.warning(f"No evidence session found: {name}")
            return
        shutil.rmtree(path)
        self.console.success(f"Evidence '{name}' deleted")

    def _cmd_delete_hash(self, args):
        if not args:
            self.console.body("Usage: delete hash <hash|id|all>")
            return
        from src.machines.credential_db import load_hashes, delete_hash_entry
        target = args[0]
        if target == "all":
            count = 0
            for h in list(load_hashes()):
                delete_hash_entry(h["id"])
                count += 1
            self.console.success(f"{count} hashes deleted")
            return
        h = App._find_hash(target)
        if h:
            delete_hash_entry(h["id"])
            self.console.success(f"Hash deleted (id={h['id']})")
            return
        self.console.warning(f"No hash found matching: {target}")

    def _cmd_delete_handshake(self, args):
        if not args:
            self.console.body("Usage: delete handshake <file|all>")
            return
        from src.elwand_paths import handshakes_dir
        base = str(handshakes_dir())
        target = args[0]

        def _remove(path):
            if os.path.isfile(path):
                try:
                    os.remove(path)
                    return True
                except OSError:
                    return False
            return False

        if target == "all":
            count = 0
            try:
                names = os.listdir(base)
            except OSError:
                names = []
            for f in names:
                if f.lower().endswith((".pcap", ".hc22000")):
                    if _remove(os.path.join(base, f)):
                        count += 1
            self.console.success(f"{count} handshake file(s) deleted")
            return

        fname = os.path.basename(target)
        if not fname.lower().endswith(".pcap"):
            fname += ".pcap"
        path = os.path.join(base, fname)
        if not os.path.isfile(path):
            self.console.warning(f"No handshake found: {target}")
            return
        _remove(path)
        _remove(os.path.splitext(path)[0] + ".hc22000")
        self.console.success(f"Handshake '{fname}' deleted")

    def _cmd_delete_machine(self, args):
        if not args:
            self.console.body("Usage: delete machine <id|ip|all>")
            return
        target = args[0]
        if target == "all":
            count = 0
            for m in list(store.get_all()):
                machine_db.delete_machine_db(m.id)
                store.remove(m.ip)
                count += 1
            self.console.success(f"{count} machines deleted")
            return
        machine = store.get(target)
        if not machine and target.isdigit():
            mid = int(target)
            for m in store.get_all():
                if m.id == mid:
                    machine = m
                    break
        if not machine:
            self.console.warning(f"No machine found for: {target}")
            return
        machine_db.delete_machine_db(machine.id)
        store.remove(machine.ip)
        self.console.success(f"Machine #{machine.id} ({machine.ip}) deleted")

    def _cmd_delete_shell(self, args):
        if not args:
            self.console.body("Usage: delete shell <id|ip|all>")
            return
        from src.shells import shell_db
        target = args[0]
        if target == "all":
            count = 0
            for s in list(shell_db.get_all()):
                shell_db.close_session(s["id"])
                count += 1
            self.console.success(f"{count} shells closed")
            return
        session = None
        for s in shell_db.get_all():
            if s["ip"] == target:
                session = s
                break
        if not session and target.isdigit():
            sid = int(target)
            session = shell_db.get_session(sid)
        if not session:
            self.console.warning(f"No shell found for: {target}")
            return
        shell_db.close_session(session["id"])
        self.console.success(f"Shell #{session['id']} ({session['ip']}) closed")

    def _cmd_delete_domain(self, args):
        if not args:
            self.console.body("Usage: delete domain <domain|all>")
            return
        domain = args[0]
        if domain == "all":
            count = 0
            for d in list(domain_db.list_all()):
                domain_db.delete_domain(d)
                count += 1
            self.console.success(f"{count} domains deleted")
            return
        if not domain_db.exists(domain):
            self.console.warning(f"No domain found for: {domain}")
            return
        domain_db.delete_domain(domain)
        self.console.success(f"Domain '{domain}' deleted")

    def _cmd_delete_user(self, args):
        if not args:
            self.console.body("Usage: delete user <username|all>")
            return
        from src.machines.credential_db import delete_user, load_usernames
        username = args[0]
        if username == "all":
            count = 0
            for u in list(load_usernames()):
                delete_user(u)
                count += 1
            self.console.success(f"{count} users deleted")
            return
        if username not in load_usernames():
            self.console.warning(f"No user found for: {username}")
            return
        delete_user(username)
        self.console.success(f"User '{username}' deleted")

    def _cmd_delete_people(self, args):
        if not args:
            self.console.body("Usage: delete people <name|all>")
            return
        from src.machines.people_db import load_people, delete_person
        target = " ".join(args).strip().lower()
        if target == "all":
            count = 0
            for p in list(load_people()):
                delete_person(p["id"])
                count += 1
            self.console.success(f"{count} people deleted")
            return
        for p in load_people():
            label = f"{p.get('first_name','')} {p.get('last_name','')}".strip().lower()
            if label == target:
                delete_person(p["id"])
                name = f"{p.get('first_name','')} {p.get('last_name','')}".strip()
                self.console.success(f"Person '{name}' deleted")
                return
        self.console.warning(f"No person found for: {target}")

    def _cmd_delete_dictionary(self, args):
        if not args:
            self.console.body("Usage: delete dictionary <filename|all>")
            return
        from src.elwand_paths import lst_dir
        import os as _os
        d = str(lst_dir())
        target = args[0]
        if target == "all":
            count = 0
            for f in sorted(_os.listdir(d)):
                fp = _os.path.join(d, f)
                if _os.path.isfile(fp):
                    _os.remove(fp)
                    count += 1
            self.console.success(f"{count} dictionary files deleted")
            return
        path = _os.path.join(d, target)
        if _os.path.isfile(path):
            _os.remove(path)
            self.console.success(f"Dictionary '{target}' deleted")
        else:
            self.console.warning(f"Dictionary not found: {target}")

    def _cmd_delete_rule(self, args):
        if not args:
            self.console.body("Usage: delete rule <filename|all>")
            return
        from src.elwand_paths import rules_dir
        import os as _os
        d = str(rules_dir())
        target = args[0]
        if target == "all":
            count = 0
            for f in sorted(_os.listdir(d)):
                fp = _os.path.join(d, f)
                if _os.path.isfile(fp):
                    _os.remove(fp)
                    count += 1
            self.console.success(f"{count} rule files deleted")
            return
        path = _os.path.join(d, target)
        if _os.path.isfile(path):
            _os.remove(path)
            self.console.success(f"Rule '{target}' deleted")
        else:
            self.console.warning(f"Rule not found: {target}")

    def _cmd_delete_poc(self, args):
        if not args:
            self.console.body("Usage: delete poc <filename|all>")
            return
        from src.elwand_paths import pocs_dir
        import os as _os
        d = str(pocs_dir())
        target = args[0]
        if target == "all":
            count = 0
            for f in sorted(_os.listdir(d)):
                fp = _os.path.join(d, f)
                if _os.path.isfile(fp):
                    _os.remove(fp)
                    count += 1
            self.console.success(f"{count} POC files deleted")
            return
        path = _os.path.join(d, target)
        if _os.path.isfile(path):
            _os.remove(path)
            self.console.success(f"POC '{target}' deleted")
        else:
            self.console.warning(f"POC not found: {target}")

    def _cmd_delete_report(self, args):
        if not args:
            self.console.body("Usage: delete report <filename|all>")
            return
        from src.elwand_paths import reports_dir
        import os as _os
        d = str(reports_dir())
        target = args[0]
        if target == "all":
            count = 0
            for f in sorted(_os.listdir(d)):
                fp = _os.path.join(d, f)
                if _os.path.isfile(fp):
                    _os.remove(fp)
                    count += 1
            self.console.success(f"{count} report files deleted")
            return
        path = _os.path.join(d, target)
        if _os.path.isfile(path):
            _os.remove(path)
            self.console.success(f"Report '{target}' deleted")
        else:
            self.console.warning(f"Report not found: {target}")

    def _cmd_delete_password(self, args):
        if not args:
            self.console.body("Usage: delete password <password|all>")
            return
        from src.machines.credential_db import delete_password, load_passwords
        pwd = args[0]
        if pwd == "all":
            count = 0
            for p in list(load_passwords()):
                delete_password(p)
                count += 1
            self.console.success(f"{count} passwords deleted")
            return
        if pwd not in load_passwords():
            self.console.warning(f"No password found")
            return
        delete_password(pwd)
        self.console.success("Password deleted")

    def _cmd_delete_evidence(self, args):
        import shutil
        from src.tools.webrecorder.evidence import target_dir
        evidence_dir = target_dir(".")
        evidence_dir = os.path.dirname(evidence_dir)
        if os.path.isdir(evidence_dir):
            shutil.rmtree(evidence_dir)
            os.makedirs(evidence_dir, exist_ok=True)
            self.console.info("All evidence data cleared")
        else:
            self.console.info("Evidence directory not found")

    def _cmd_delete_inventory(self, args):
        from src.machines.credential_db import (
            load_users, delete_user, load_passwords, delete_password,
            load_credentials, delete_credential, load_hashes, load_tickets,
        )
        from src.machines.people_db import load_people
        from src.elwand_paths import pocs_dir

        deleted = 0

        for u in list(load_users()):
            delete_user(u["username"])
            deleted += 1

        for p in list(load_passwords()):
            delete_password(p)
            deleted += 1

        for c in list(load_credentials()):
            delete_credential(c["id"])
            deleted += 1

        for h in list(load_hashes()):
            from src.machines.credential_db import delete_hash_entry
            delete_hash_entry(h["id"])
            deleted += 1

        for t in list(load_tickets()):
            from src.machines.credential_db import delete_ticket
            delete_ticket(t["id"])
            deleted += 1

        for person in list(load_people()):
            from src.machines.people_db import delete_person
            delete_person(person["id"])
            deleted += 1

        pocs = str(pocs_dir())
        if os.path.isdir(pocs):
            for f in os.listdir(pocs):
                p = os.path.join(pocs, f)
                if os.path.isfile(p):
                    os.remove(p)
                    deleted += 1

        self.console.success(f"Inventory cleared ({deleted} items). Machines, domains, rules and dictionaries preserved.")

    def _cmd_delete_cache(self, args):
        from src.elwand_paths import cache_dir
        d = str(cache_dir())
        deleted = 0
        if os.path.isdir(d):
            for f in os.listdir(d):
                p = os.path.join(d, f)
                if os.path.isfile(p):
                    os.remove(p)
                    deleted += 1
        self.console.success(f"Cache cleared ({deleted} files).")

    def _cmd_delete_dbs(self, args):
        store.clear()
        clear_mdns_cache()
        machine_db.delete_all()
        domain_db.delete_all()
        from src.machines.credential_db import delete_all as del_creds
        del_creds()
        wipe_mdns_cache()
        stop_machines_autosave()
        start_machines_autosave(store)
        self.console.info("All data cleared (mDNS cache + machine list + database files)")

    def _cmd_delete_all(self):
        import shutil
        from src.elwand_paths import evidence_dir, pocs_dir, cache_dir
        from src.machines.people_db import delete_all as del_people
        from src.shells import shell_db

        store.clear()
        store.save()
        clear_mdns_cache()
        machine_db.delete_all()
        domain_db.delete_all()
        from src.machines.credential_db import delete_all as del_creds
        del_creds()
        del_people()
        wipe_mdns_cache()
        stop_machines_autosave()
        start_machines_autosave(store)

        for s in list(shell_db.get_all()):
            shell_db.close_session(s["id"])

        base = str(evidence_dir())
        if os.path.isdir(base):
            shutil.rmtree(base)
            os.makedirs(base, exist_ok=True)

        for d in (str(pocs_dir()), str(cache_dir())):
            if os.path.isdir(d):
                for f in os.listdir(d):
                    fp = os.path.join(d, f)
                    if os.path.isfile(fp):
                        os.remove(fp)

        from src.tools.scanner import wifi_monitor
        wifi_monitor.clear()

        self.console.success("All data cleared (machines, domains, inventory, people, shells, evidence, POCs, cache, WiFi networks/probes). Dictionaries, rules and reports preserved.")

    def _toggle_focus(self, event=None):
        focused = self.focus_get()
        if focused is self.console.input_text:
            view = self.visualizer.get_active_view()
            if view and hasattr(view, "terminal"):
                view.terminal.focus_set()
            return "break"
        self.console.input_text.focus()
        return "break"

    def _enter_fullscreen(self):
        try:
            self.attributes("-fullscreen", True)
        except tk.TclError:
            return
        self.winfo_toplevel().update_idletasks()
        self.visualizer._refresh_labels(self.visualizer.get_active_view())
        self.winfo_toplevel().update_idletasks()

    def _toggle_fullscreen(self, event=None):
        try:
            current = bool(self.attributes("-fullscreen"))
            self.attributes("-fullscreen", not current)
        except tk.TclError:
            return "break"
        self.winfo_toplevel().update_idletasks()
        self.visualizer._refresh_labels(self.visualizer.get_active_view())
        self.winfo_toplevel().update_idletasks()
        return "break"

    def _on_zoom_changed(self):
        view = self.visualizer.get_active_view()
        if view is None:
            return
        if hasattr(view, "_on_resize"):
            try:
                view._on_resize(None)
                return
            except Exception:
                pass
        if hasattr(view, "_last_hash"):
            view._last_hash = None
        if hasattr(view, "_rendered"):
            view._rendered = False
        if hasattr(view, "_poll"):
            try:
                view._poll()
            except Exception:
                pass

    def _safe_after(self, callback, *args):
        try:
            if args:
                self.after(0, callback, *args)
            else:
                self.after(0, callback)
        except RuntimeError:
            pass

    def _on_close(self):
        self._closing = True
        self._agent_mode = False
        self._consultor_mode = False
        if self._agent_stop_event:
            self._agent_stop_event.set()
        self.console.stop_thinking()
        if self._passive_scanner:
            self._passive_scanner.stop()
        if self._active_scanner:
            self._active_scanner.stop()
        if self._shell_listener:
            self._shell_listener.stop()
        self._udpscan_running = False
        self._tcpscan_running = False
        stop_machines_autosave()
        store.save()
        save_mdns_cache()
        try:
            from src.tools.scanner import wifi_monitor
            wifi_monitor.shutdown()
        except Exception:
            pass
        elwand_settings.save()
        event_bus.stop()
        self.update_idletasks()
        self.destroy()
