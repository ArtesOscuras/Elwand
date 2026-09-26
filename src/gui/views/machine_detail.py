from src.gui import fonts, windowing
import tkinter as tk
from .base import BaseView
from src.machines import store
from src.machines import machine_db


MUTED = "#888888"
BRIGHT = "#ffffff"
INFO = "#5ba3ec"


class MachineDetailView(BaseView):
    name = "machine_detail"
    description = "Machine detail view"

    def __init__(self, parent, machine, **kwargs):
        self._machine = machine
        super().__init__(parent, **kwargs)

    def _build_ui(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=0)
        self.rowconfigure(1, weight=1)

        header = tk.Frame(self, bg="#000000")
        header.grid(row=0, column=0, sticky="ew", pady=(15, 10))

        self._title_label = tk.Label(
            header,
            text="",
            font=fonts.view_font_bold(22),
            fg="#ffffff",
            bg="#000000",
        )
        self._title_label.pack(anchor="center")
        self._title_label.bind("<Button-1>", self._on_title_click)
        self._title_label.bind("<Enter>", lambda e: self._title_label.config(font=fonts.view_font_bold_under(22)))
        self._title_label.bind("<Leave>", lambda e: self._title_label.config(font=fonts.view_font_bold(22)))
        self._on_back_click = None
        self._last_hash = None

        text_frame = tk.Frame(self, bg="#000000")
        text_frame.grid(row=1, column=0, sticky="nsew", padx=(220, 20), pady=(0, 20))
        text_frame.columnconfigure(0, weight=1)
        text_frame.rowconfigure(0, weight=1)

        self.text = tk.Text(
            text_frame,
            bg="#000000",
            fg=BRIGHT,
            font=fonts.view_font(13),
            borderwidth=0,
            highlightthickness=0,
            state=tk.DISABLED,
            cursor="",
            wrap=tk.WORD,
        )
        self.text.grid(row=0, column=0, sticky="nsew")

        scrollbar = tk.Scrollbar(text_frame, orient=tk.VERTICAL, command=self.text.yview)
        scrollbar.configure(bg="#333333", troughcolor="#1a1a1a", activebackground="#555555",
                            width=10, borderwidth=0, highlightthickness=0, elementborderwidth=0)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.text.configure(yscrollcommand=scrollbar.set)

        self.text.tag_configure("muted", foreground=MUTED)
        self.text.tag_configure("bright", foreground=BRIGHT)
        self.text.tag_configure("info", foreground=INFO)

        self._poll_id = None

    def on_activate(self):
        self._poll()

    def on_deactivate(self):
        if self._poll_id:
            self.after_cancel(self._poll_id)
            self._poll_id = None

    def _on_title_click(self, event):
        if self._on_back_click:
            self._on_back_click()

    def _poll(self):
        self._refresh()
        self._poll_id = self.after(2000, self._poll)

    def _refresh(self):
        m = store.get(self._machine.ip)
        if m:
            self._machine = m

        ports = machine_db.load_tcp_ports(self._machine.id)
        udp_ports = machine_db.load_udp_ports(self._machine.id)
        web = machine_db.load_web_services(self._machine.id)
        domains = machine_db.load_domains(self._machine.id)
        banners = machine_db.load_banners(self._machine.id)
        directories = machine_db.load_directories(self._machine.id)
        current_hash = hash((
            self._machine.device_type, self._machine.model, self._machine.os,
            self._machine.domain, self._machine.hostname, self._machine.mac,
            tuple(ports), tuple(udp_ports), tuple((p, o) for p, o in web),
            tuple(domains), tuple(banners), tuple(directories),
        ))
        if current_hash == self._last_hash and self.text.index("end-1c") != "1.0":
            return
        self._last_hash = current_hash

        try:
            first_line = self.text.index("@0,0")
            line_num = int(first_line.split(".")[0])
        except Exception:
            line_num = 1

        self.text.configure(state=tk.NORMAL)
        self.text.delete("1.0", tk.END)

        m = self._machine

        self._title_label.config(text=f"Machine #{m.id} — {m.ip}")

        rows = [
            ("IPv4", m.ip),
            ("IPv6", m.ipv6),
            ("Hostname", m.hostname),
            ("MAC", m.mac),
            ("Type", m.device_type),
            ("Model", m.model),
            ("OS", m.os),
            ("Domain", m.domain),
            ("Methods", ", ".join(sorted(m.methods))),
            ("First seen", m.first_seen.strftime("%Y-%m-%d %H:%M:%S")),
            ("Last seen", m.last_seen.strftime("%Y-%m-%d %H:%M:%S")),
        ]
        label_w = max(len(r[0]) for r in rows) + 2
        for label, value in rows:
            self.text.insert(tk.END, f"  {label + ':':<{label_w}} ", "muted")
            self.text.insert(tk.END, f"{value or '-'}\n", "bright")

        domains = machine_db.load_domains(m.id)
        if domains:
            self.text.insert(tk.END, f"\nDomains:\n", "info")
            for d, src in domains:
                tag = f"dom_{d}"
                self.text.tag_configure(tag, underline=False)
                self.text.insert(tk.END, f"  {d}", ("bright", tag))
                self.text.tag_bind(tag, "<Button-1>", lambda e, dm=d: (
                    self._on_domain_click and self._on_domain_click(dm)))
                self.text.tag_bind(tag, "<Enter>", lambda e, t=tag: self.text.tag_configure(t, underline=True))
                self.text.tag_bind(tag, "<Leave>", lambda e, t=tag: self.text.tag_configure(t, underline=False))
                if src:
                    self.text.insert(tk.END, f" ({src})", "muted")
                self.text.insert(tk.END, "\n")

        banners = machine_db.load_banners(m.id)
        if banners:
            last_port = None
            for p, out, probe in reversed(banners):
                if out.strip():
                    last_port = p
                    break
            if last_port is not None:
                for p, out, probe in banners:
                    if p == last_port and out.strip():
                        out_short = out.split("\n")[0][:100]
                        tag = f"banner_{p}"
                        self.text.tag_configure(tag, underline=False)
                        self.text.insert(tk.END, f"\nPort-inspector port {p} ({probe}):\n", ("info", tag))
                        self.text.tag_bind(tag, "<Button-1>", lambda e, pid=p: self._show_banner(pid))
                        self.text.tag_bind(tag, "<Enter>", lambda e, t=tag: self.text.tag_configure(t, underline=True))
                        self.text.tag_bind(tag, "<Leave>", lambda e, t=tag: self.text.tag_configure(t, underline=False))
                        self.text.insert(tk.END, f"  {out_short}\n", "bright")
                        break

        ports = machine_db.load_tcp_ports(m.id)
        if ports:
            self.text.insert(tk.END, f"\nTCP ports ({len(ports)}):\n", "info")
            port_w = max(len(str(p)) for p in ports) + 2
            for p in ports:
                self.text.insert(tk.END, f"  {str(p):<{port_w}}", "muted")
                self.text.insert(tk.END, f"{_service_name(p)}\n", "bright")
        else:
            self.text.insert(tk.END, "\nTCP ports: (not scanned yet)\n", "muted")

        udp_ports = machine_db.load_udp_ports(m.id)
        if udp_ports:
            self.text.insert(tk.END, f"\nUDP ports ({len(udp_ports)}):\n", "info")
            port_w = max(len(str(p)) for p in udp_ports) + 2
            for p in udp_ports:
                self.text.insert(tk.END, f"  {str(p):<{port_w}}", "muted")
                self.text.insert(tk.END, f"{_service_name(p)}\n", "bright")
        else:
            self.text.insert(tk.END, "\nUDP ports: (not scanned yet)\n", "muted")

        web = machine_db.load_web_services(m.id)
        if web:
            for port, output in web:
                self.text.insert(tk.END, f"\nWeb port {port}:\n", "info")
                for line in output.split("\n"):
                    self.text.insert(tk.END, f"  {line}\n", "bright")

        directories = machine_db.load_directories(m.id)
        if directories:
            self.text.insert(tk.END, f"\nDirectories ({len(directories)}):\n", "info")
            for path, ts in directories:
                self.text.insert(tk.END, f"  {path}\n", "bright")

        last_line = self.text.index("end-1c")
        total = int(last_line.split(".")[0]) if last_line else 1
        fraction = line_num / max(total, 1)
        self.text.yview_moveto(min(fraction, 1.0))
        self.text.configure(state=tk.DISABLED)

    def _show_banner(self, port):
        banners = machine_db.load_banners(self._machine.id)
        texts = [(p, o, pr) for p, o, pr in banners if p == port and o.strip()]
        if not texts:
            return

        dlg = tk.Toplevel(self)
        dlg.title(f"Port-inspector — Port {port}")
        windowing.size_dialog(dlg, 750, 550)
        dlg.configure(bg="#111111")
        dlg.transient(self)

        dlg.columnconfigure(0, weight=1)
        dlg.rowconfigure(0, weight=1)

        text = tk.Text(dlg, bg="#000000", fg="#ffffff", cursor="",
                       font=fonts.view_font(11), borderwidth=0, highlightthickness=0,
                       wrap=tk.WORD, padx=15, pady=15)
        text.grid(row=0, column=0, sticky="nsew")

        scrollbar = tk.Scrollbar(dlg, orient=tk.VERTICAL, command=text.yview)
        scrollbar.configure(bg="#333333", troughcolor="#1a1a1a", activebackground="#555555",
                            width=10, borderwidth=0, highlightthickness=0, elementborderwidth=0)
        scrollbar.grid(row=0, column=1, sticky="ns")
        text.configure(yscrollcommand=scrollbar.set)

        text.tag_configure("muted", foreground=MUTED)
        text.tag_configure("bright", foreground=BRIGHT)
        text.tag_configure("info", foreground=INFO)

        text.insert(tk.END, f"Port-inspector results for port {port}\n", "info")
        text.insert(tk.END, f"{'─' * 50}\n", "muted")
        for p, out, probe in texts:
            text.insert(tk.END, f"\nProbe: {probe}\n", "info")
            payload = _PROBE_PAYLOADS.get(probe)
            if payload:
                text.insert(tk.END, f"Sent: {payload}\n", "muted")
            text.insert(tk.END, f"{out}\n", "bright")

        text.configure(state=tk.DISABLED)

        btn_frame = tk.Frame(dlg, bg="#111111")
        btn_frame.grid(row=1, column=0, columnspan=2, pady=(10, 15))

        close_btn = tk.Label(btn_frame, text="  Close  ", bg="#222222", fg="#ffffff",
                             font=fonts.view_font(10), relief=tk.RAISED, bd=1,
                             padx=15, pady=6)
        close_btn.pack()
        close_btn.bind("<Button-1>", lambda e: dlg.destroy())
        close_btn.bind("<Enter>", lambda e: close_btn.config(bg="#333333"))
        close_btn.bind("<Leave>", lambda e: close_btn.config(bg="#222222"))
        dlg.focus_set()


_PROBE_PAYLOADS = {
    "hello": "b'hello\\r\\n'",
    "HTTP GET": "b'GET / HTTP/1.0\\r\\nHost: {ip}\\r\\n\\r\\n'",
    "TLS ClientHello": "b'\\x16\\x03\\x01\\x00\\x01\\x01\\x00\\x03\\x03' + b'\\x00'*36",
    "SSH hello": "b'SSH-2.0-OpenSSH_client\\r\\n'",
    "SMTP EHLO": "b'EHLO test\\r\\n'",
    "FTP USER": "b'USER anonymous\\r\\n'",
    "Redis PING": "b'PING\\r\\n'",
    "POP3 CAPA": "b'CAPA\\r\\n'",
    "IMAP CAPABILITY": "b'a001 CAPABILITY\\r\\n'",
    "Redis INFO": "b'INFO\\r\\n'",
    "Memcached stats": "b'stats\\r\\n'",
    "QUIT": "b'QUIT\\r\\n'",
    "RDP connect": "b'\\x01\\x00\\x00\\x01\\x01'",
    "PostgreSQL startup": "b'\\x00\\x00\\x00\\xa4\\x00\\x00\\x00\\x04\\x00\\x00...'",
    "SMB negotiate": "b'\\x00\\x00\\x00\\x85\\xffSMBr\\x00\\x00\\x00\\x00\\x18'",
    "VNC RFB": "b'RFB 003.008\\n'",
    "MySQL handshake": "b'\\x00'*36",
    "MongoDB isMaster": "b'{\"isMaster\": 1}'",
    "MongoDB buildInfo": "b'{\"buildinfo\": 1}'",
    "Docker API": "b'GET /version HTTP/1.0\\r\\nHost: {ip}\\r\\n\\r\\n'",
    "Elasticsearch": "b'GET /_cluster/health HTTP/1.0\\r\\nHost: {ip}\\r\\n\\r\\n'",
    "generic HELP": "b'HELP\\r\\n'",
    "generic STATUS": "b'STATUS\\r\\n'",
    "HTTP OPTIONS": "b'OPTIONS / HTTP/1.0\\r\\nHost: {ip}\\r\\n\\r\\n'",
    "RTSP OPTIONS": "b'OPTIONS * RTSP/1.0\\r\\nCSeq: 1\\r\\n\\r\\n'",
    "SIP OPTIONS": "b'OPTIONS sip:test@{ip} SIP/2.0\\r\\n...'",
    "Telnet options": "b'\\xff\\xfb\\x01\\xff\\xfb\\x03\\xff\\xfd\\x18'",
    "MySQL login": "b'\\x00\\x00\\x00\\x01'",
}


_SERVICES = {
    7: "echo", 9: "discard", 13: "daytime", 21: "ftp", 22: "ssh", 23: "telnet",
    25: "smtp", 37: "time", 49: "tacacs", 53: "dns", 69: "tftp", 70: "gopher",
    79: "finger", 80: "http", 88: "kerberos", 110: "pop3", 111: "rpcbind",
    113: "ident", 119: "nntp", 123: "ntp", 135: "msrpc", 137: "netbios-ns",
    138: "netbios-dgm", 139: "netbios-ssn", 143: "imap", 161: "snmp", 162: "snmptrap",
    179: "bgp", 199: "smux", 389: "ldap", 443: "https", 445: "smb", 465: "smtps",
    512: "exec", 513: "login", 514: "shell", 515: "printer", 548: "afp",
    554: "rtsp", 587: "submission", 631: "ipp", 636: "ldaps", 646: "ldp",
    873: "rsync", 993: "imaps", 995: "pop3s", 1025: "rpc", 1026: "rpc",
    1027: "rpc", 1080: "socks", 1099: "rmireg", 1433: "mssql", 1434: "mssql",
    1521: "oracle", 1723: "pptp", 2049: "nfs", 2121: "ftp-proxy",
    2222: "ssh-alt", 2375: "docker", 2701: "sms", 3128: "squid",
    3260: "iscsi", 3306: "mysql", 3389: "rdp", 3690: "svn", 4369: "epmd",
    4444: "krb524", 4786: "cisco", 4848: "appserv", 5000: "upnp",
    5353: "mdns", 5432: "postgres", 5555: "adb", 5672: "amqp",
    5800: "vnc", 5900: "vnc", 5985: "winrm", 5986: "winrm-ssl",
    6379: "redis", 6667: "irc", 7001: "weblogic", 7002: "weblogic",
    7777: "cbt", 8000: "http-alt", 8009: "ajp", 8080: "http-proxy",
    8180: "http-alt", 8443: "https-alt", 8888: "http-alt",
    9000: "cslistener", 9090: "websm", 9200: "elastic", 9443: "https-alt",
    9999: "abyss", 11211: "memcache", 27017: "mongodb", 50070: "hdfs",
    61616: "activemq",
}


def _service_name(port):
    return _SERVICES.get(port, "")
