import threading
import tkinter as tk
from tkinter import ttk

from src.gui import fonts, windowing

BG = "#111111"
FG = "#ffffff"
MUTED = "#888888"
SUCCESS = "#00cc66"
ERR_COLOR = "#f44747"
PANEL = "#000000"
SEL_BG = "#2d6cdf"
BTN_BG = "#222222"
BTN_HOVER = "#333333"

POLL_MS = 1500


class WifiOperatorDialog(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Wifi operator")
        windowing.size_dialog(self, 900, 640, min_w=760, min_h=520)
        self.configure(bg=BG)
        self.transient(parent)

        self._mode = "single"          # "single" | "all"
        self._iface = None
        self._net_key = None
        self._client_key = None
        self._poll_id = None
        self._nets_sig = None
        self._clients_sig = None
        self._ifaces_sig = None
        self._destroyed = False
        self._busy = False
        self._nets = {}
        self._clients = {}
        self._iface_labels = {}
        self._csa_iface_labels = {}
        self._csa_params = {}
        self._deauth_params = {}
        self._csa_all_essid = False
        self._csa_running = False
        self._csa_stop = None
        self._csa_thread = None
        self._csa_nets_sig = None
        self._csa_clients_sig = None
        self._csa_ifaces_sig = None

        style = ttk.Style()
        try:
            style.theme_use("default")
        except tk.TclError:
            pass
        style.configure("TNotebook", background=BG, borderwidth=0)
        style.configure("TNotebook.Tab", background="#222222", foreground=MUTED,
                        font=fonts.view_font(10), padding=[12, 4])
        style.map("TNotebook.Tab", background=[("selected", "#111111")],
                  foreground=[("selected", FG)])

        self._nb = ttk.Notebook(self)
        self._nb.grid(row=0, column=0, sticky="nsew")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        self._tab_deauther = tk.Frame(self._nb, bg=BG)
        self._nb.add(self._tab_deauther, text="Deauther")

        self._tab_csa = tk.Frame(self._nb, bg=BG)
        self._nb.add(self._tab_csa, text="CSA Spoof")

        self._build_deauther()
        self._build_csa()

        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self.update_idletasks()
        self.wait_visibility()
        self.grab_set()

        self._update_toggles()
        self._update_all_essid_btn()
        self._poll()

    # ---------- UI construction ----------

    def _build_deauther(self):
        tab = self._tab_deauther
        tab.columnconfigure(0, weight=1)
        tab.columnconfigure(1, weight=1)
        tab.rowconfigure(1, weight=1)
        tab.rowconfigure(3, weight=1)

        iface_row = tk.Frame(tab, bg=BG)
        iface_row.grid(row=0, column=0, columnspan=2, sticky="ew",
                       padx=12, pady=(10, 4))
        tk.Label(iface_row, text="Interface:", fg=MUTED, bg="#111111",
                 font=fonts.view_font_bold(10)).pack(side=tk.LEFT)
        self._iface_frame = tk.Frame(iface_row, bg=BG)
        self._iface_frame.pack(side=tk.LEFT, padx=(8, 0))

        net_frame = tk.Frame(tab, bg=BG)
        net_frame.grid(row=1, column=0, sticky="nsew", padx=(12, 6), pady=4)
        net_frame.columnconfigure(0, weight=1)
        net_frame.rowconfigure(1, weight=1)
        tk.Label(net_frame, text="Networks (ESSID / MHz)", fg=MUTED, bg="#111111",
                 font=fonts.view_font_bold(10), anchor="w").grid(
            row=0, column=0, sticky="ew")
        self._net_list = self._make_listbox(net_frame)
        self._net_list.grid(row=1, column=0, sticky="nsew")
        self._make_scrollbar(net_frame, self._net_list).grid(
            row=1, column=1, sticky="ns")
        self._net_list.bind("<<ListboxSelect>>",
                            lambda e: self._on_net_select())

        right = tk.Frame(tab, bg=BG)
        right.grid(row=1, column=1, sticky="nsew", padx=(6, 12), pady=4)
        right.columnconfigure(0, weight=1)
        right.rowconfigure(2, weight=1)

        toggles = tk.Frame(right, bg=BG)
        toggles.grid(row=0, column=0, sticky="ew")
        self._single_btn = self._make_toggle(toggles, "Single target", "single")
        self._single_btn.pack(side=tk.LEFT)
        self._all_btn = self._make_toggle(toggles, "Broadcast", "all")
        self._all_btn.pack(side=tk.LEFT, padx=(6, 0))

        tk.Label(right, text="Clients (probe MACs)", fg=MUTED, bg="#111111",
                 font=fonts.view_font_bold(10), anchor="w").grid(
            row=1, column=0, sticky="ew", pady=(8, 0))
        self._client_list = self._make_listbox(right)
        self._client_list.grid(row=2, column=0, sticky="nsew")
        self._make_scrollbar(right, self._client_list).grid(
            row=2, column=1, sticky="ns")
        self._client_list.bind("<<ListboxSelect>>",
                               lambda e: self._on_client_select())

        from src.tools.scanner.wifi_monitor import DEAUTH_DEFAULTS
        params = tk.Frame(tab, bg=BG)
        params.grid(row=2, column=0, columnspan=2, sticky="ew",
                    padx=12, pady=(6, 2))
        fields = [
            ("count", "Count", DEAUTH_DEFAULTS["count"]),
            ("reason", "Reason", DEAUTH_DEFAULTS["reason"]),
            ("interval", "Interval s", DEAUTH_DEFAULTS["interval"]),
            ("rate", "TX rate", DEAUTH_DEFAULTS["rate"]),
        ]
        for i, (key, label, val) in enumerate(fields):
            tk.Label(params, text=label, fg=MUTED, bg="#111111",
                     font=fonts.view_font(10)).grid(
                row=0, column=i * 2, padx=(0 if i == 0 else 8, 2))
            ent = tk.Entry(params, width=6, bg=PANEL, fg=FG,
                           insertbackground=FG, font=fonts.view_font(10),
                           relief=tk.FLAT, highlightthickness=0,
                           justify=tk.CENTER)
            ent.insert(0, str(val))
            ent.grid(row=0, column=i * 2 + 1)
            self._deauth_params[key] = ent

        out_frame = tk.Frame(tab, bg=BG)
        out_frame.grid(row=3, column=0, columnspan=2, sticky="nsew",
                       padx=12, pady=(6, 4))
        out_frame.columnconfigure(0, weight=1)
        out_frame.rowconfigure(0, weight=1)
        self._out = tk.Text(
            out_frame, bg=PANEL, fg=FG, font=fonts.view_font(10),
            state=tk.DISABLED, wrap=tk.WORD, cursor="",
            borderwidth=0, highlightthickness=0, height=8,
        )
        self._out.grid(row=0, column=0, sticky="nsew")
        self._out.tag_configure("success", foreground=SUCCESS)
        self._out.tag_configure("error", foreground=ERR_COLOR)
        self._out.tag_configure("info", foreground=FG)
        self._out.tag_configure("muted", foreground=MUTED)
        self._make_scrollbar(out_frame, self._out).grid(
            row=0, column=1, sticky="ns")

        btns = tk.Frame(tab, bg=BG)
        btns.grid(row=4, column=0, columnspan=2, sticky="ew",
                  padx=12, pady=(4, 12))
        btns.columnconfigure(0, weight=1)
        self._deauth_btn = self._make_button(btns, "Deauth")
        self._deauth_btn.grid(row=0, column=1, padx=(0, 6))
        self._deauth_btn.bind("<Button-1>", lambda e: self._on_deauth())
        close_btn = self._make_button(btns, "Close")
        close_btn.grid(row=0, column=2)
        close_btn.bind("<Button-1>", lambda e: self._on_close())

    def _build_csa(self):
        from src.tools.scanner.csa_attack import DEFAULTS
        tab = self._tab_csa
        tab.columnconfigure(0, weight=1)
        tab.columnconfigure(1, weight=1)
        tab.rowconfigure(1, weight=1)

        iface_row = tk.Frame(tab, bg=BG)
        iface_row.grid(row=0, column=0, columnspan=2, sticky="ew",
                       padx=12, pady=(10, 4))
        tk.Label(iface_row, text="Interface:", fg=MUTED, bg="#111111",
                 font=fonts.view_font_bold(10)).pack(side=tk.LEFT)
        self._csa_iface_frame = tk.Frame(iface_row, bg=BG)
        self._csa_iface_frame.pack(side=tk.LEFT, padx=(8, 0))

        net_frame = tk.Frame(tab, bg=BG)
        net_frame.grid(row=1, column=0, sticky="nsew", padx=(12, 6), pady=4)
        net_frame.columnconfigure(0, weight=1)
        net_frame.rowconfigure(1, weight=1)
        tk.Label(net_frame, text="Networks (ESSID / MHz)", fg=MUTED,
                 bg="#111111", font=fonts.view_font_bold(10),
                 anchor="w").grid(row=0, column=0, sticky="ew")
        self._csa_net_list = self._make_listbox(net_frame)
        self._csa_net_list.grid(row=1, column=0, sticky="nsew")
        self._make_scrollbar(net_frame, self._csa_net_list).grid(
            row=1, column=1, sticky="ns")
        self._csa_net_list.bind("<<ListboxSelect>>",
                                lambda e: self._on_net_select("csa"))

        right = tk.Frame(tab, bg=BG)
        right.grid(row=1, column=1, sticky="nsew", padx=(6, 12), pady=4)
        right.columnconfigure(0, weight=1)
        right.rowconfigure(2, weight=1)

        toggles = tk.Frame(right, bg=BG)
        toggles.grid(row=0, column=0, sticky="ew")
        self._csa_single_btn = self._make_toggle(toggles, "Single target",
                                                 "single")
        self._csa_single_btn.pack(side=tk.LEFT)
        self._csa_all_btn = self._make_toggle(toggles, "Broadcast", "all")
        self._csa_all_btn.pack(side=tk.LEFT, padx=(6, 0))

        tk.Label(right, text="Clients (probe MACs)", fg=MUTED, bg="#111111",
                 font=fonts.view_font_bold(10), anchor="w").grid(
            row=1, column=0, sticky="ew", pady=(8, 0))
        self._csa_client_list = self._make_listbox(right)
        self._csa_client_list.grid(row=2, column=0, sticky="nsew")
        self._make_scrollbar(right, self._csa_client_list).grid(
            row=2, column=1, sticky="ns")
        self._csa_client_list.bind("<<ListboxSelect>>",
                                   lambda e: self._on_client_select("csa"))

        params = tk.Frame(tab, bg=BG)
        params.grid(row=2, column=0, columnspan=2, sticky="ew",
                    padx=12, pady=(6, 2))
        fields = [
            ("target_chan", "Target ch", DEFAULTS["target_chan"]),
            ("attack_window", "Attack s", DEFAULTS["attack_window"]),
            ("observe_window", "Observe s", DEFAULTS["observe_window"]),
            ("count", "Count", DEFAULTS["count"]),
            ("csa_interval", "Interval s", DEFAULTS["csa_interval"]),
            ("tx_rate", "TX rate", DEFAULTS["tx_rate"]),
            ("duration", "Duration s", DEFAULTS["duration"]),
        ]
        for i, (key, label, val) in enumerate(fields):
            tk.Label(params, text=label, fg=MUTED, bg="#111111",
                     font=fonts.view_font(10)).grid(
                row=0, column=i * 2, padx=(0 if i == 0 else 8, 2))
            ent = tk.Entry(params, width=6, bg=PANEL, fg=FG,
                           insertbackground=FG, font=fonts.view_font(10),
                           relief=tk.FLAT, highlightthickness=0,
                           justify=tk.CENTER)
            ent.insert(0, str(val))
            ent.grid(row=0, column=i * 2 + 1)
            self._csa_params[key] = ent

        essid_row = tk.Frame(tab, bg=BG)
        essid_row.grid(row=3, column=0, columnspan=2, sticky="ew",
                       padx=12, pady=(0, 2))
        self._csa_all_essid_btn = tk.Label(
            essid_row, text="  All networks with this ESSID  ",
            bg=BTN_BG, fg=MUTED, padx=12, pady=5,
            font=fonts.view_font_bold(10), cursor="")
        self._csa_all_essid_btn.pack(side=tk.LEFT)
        self._csa_all_essid_btn.bind(
            "<Button-1>", lambda e: self._toggle_all_essid())
        self._csa_all_essid_btn.bind(
            "<Enter>", lambda e: self._all_essid_hover(True))
        self._csa_all_essid_btn.bind(
            "<Leave>", lambda e: self._all_essid_hover(False))

        out_frame = tk.Frame(tab, bg=BG)
        out_frame.grid(row=4, column=0, columnspan=2, sticky="nsew",
                       padx=12, pady=(6, 4))
        out_frame.columnconfigure(0, weight=1)
        out_frame.rowconfigure(0, weight=1)
        self._csa_out = tk.Text(
            out_frame, bg=PANEL, fg=FG, font=fonts.view_font(10),
            state=tk.DISABLED, wrap=tk.WORD, cursor="",
            borderwidth=0, highlightthickness=0, height=8,
        )
        self._csa_out.grid(row=0, column=0, sticky="nsew")
        self._csa_out.tag_configure("success", foreground=SUCCESS)
        self._csa_out.tag_configure("error", foreground=ERR_COLOR)
        self._csa_out.tag_configure("info", foreground=FG)
        self._csa_out.tag_configure("muted", foreground=MUTED)
        self._make_scrollbar(out_frame, self._csa_out).grid(
            row=0, column=1, sticky="ns")

        btns = tk.Frame(tab, bg=BG)
        btns.grid(row=5, column=0, columnspan=2, sticky="ew",
                  padx=12, pady=(4, 12))
        btns.columnconfigure(0, weight=1)
        self._csa_start_btn = self._make_button(btns, "Start attack")
        self._csa_start_btn.grid(row=0, column=1, padx=(0, 6))
        self._csa_start_btn.bind("<Button-1>", lambda e: self._on_csa_start())
        self._csa_stop_btn = self._make_button(btns, "Stop")
        self._csa_stop_btn.grid(row=0, column=2, padx=(0, 6))
        self._csa_stop_btn.bind("<Button-1>", lambda e: self._on_csa_stop())
        close_btn = self._make_button(btns, "Close")
        close_btn.grid(row=0, column=3)
        close_btn.bind("<Button-1>", lambda e: self._on_close())

    def _make_listbox(self, parent):
        lb = tk.Listbox(
            parent, bg=PANEL, fg=FG, font=fonts.view_font(10),
            selectbackground=SEL_BG, selectforeground=FG,
            activestyle="none", borderwidth=0, highlightthickness=0,
            cursor="", exportselection=False,
        )
        return lb

    def _make_scrollbar(self, parent, widget):
        sb = tk.Scrollbar(parent, orient=tk.VERTICAL, command=widget.yview)
        sb.configure(bg="#333333", troughcolor="#1a1a1a",
                     activebackground="#555555", width=10,
                     borderwidth=0, highlightthickness=0, elementborderwidth=0)
        widget.configure(yscrollcommand=sb.set)
        return sb

    def _make_button(self, parent, text):
        btn = tk.Label(parent, text=text, bg=BTN_BG, fg=FG, padx=15, pady=6,
                       font=fonts.view_font(10), cursor="")
        btn.bind("<Enter>", lambda e: btn.config(bg=BTN_HOVER))
        btn.bind("<Leave>", lambda e: btn.config(bg=BTN_BG))
        return btn

    def _make_toggle(self, parent, text, value):
        lbl = tk.Label(parent, text=text, bg=BTN_BG, fg=MUTED, padx=12, pady=5,
                       font=fonts.view_font_bold(10), cursor="")
        lbl.bind("<Button-1>", lambda e, v=value: self._set_mode(v))
        lbl.bind("<Enter>", lambda e, l=lbl, v=value: self._toggle_hover(l, v, True))
        lbl.bind("<Leave>", lambda e, l=lbl, v=value: self._toggle_hover(l, v, False))
        return lbl

    # ---------- CSA "all ESSID" box ----------

    def _toggle_all_essid(self):
        self._csa_all_essid = not self._csa_all_essid
        self._update_all_essid_btn()

    def _update_all_essid_btn(self):
        lbl = getattr(self, "_csa_all_essid_btn", None)
        if lbl is None:
            return
        lbl.config(bg=SEL_BG if self._csa_all_essid else BTN_BG,
                   fg=FG if self._csa_all_essid else MUTED)

    def _all_essid_hover(self, entering):
        lbl = getattr(self, "_csa_all_essid_btn", None)
        if lbl is None:
            return
        if entering:
            lbl.config(bg=BTN_HOVER)
        else:
            self._update_all_essid_btn()

    # ---------- toggles ----------

    def _set_mode(self, value):
        self._mode = value
        self._update_toggles()
        self._update_client_state()

    def _update_toggles(self):
        pairs = [("single", self._single_btn), ("all", self._all_btn),
                 ("single", self._csa_single_btn), ("all", self._csa_all_btn)]
        for value, lbl in pairs:
            if value == self._mode:
                lbl.config(bg=SEL_BG, fg=FG)
            else:
                lbl.config(bg=BTN_BG, fg=MUTED)

    def _toggle_hover(self, lbl, value, entering):
        if value == self._mode:
            return
        lbl.config(bg=BTN_HOVER if entering else BTN_BG)

    def _update_client_state(self):
        state = tk.DISABLED if self._mode == "all" else tk.NORMAL
        fg = MUTED if self._mode == "all" else FG
        for lb in (self._client_list, self._csa_client_list):
            lb.config(state=state, fg=fg)

    # ---------- polling ----------

    def _poll(self):
        if self._destroyed:
            return
        self._refresh_ifaces()
        self._refresh_networks()
        self._refresh_clients()
        self._poll_id = self.after(POLL_MS, self._poll)

    def _refresh_ifaces(self):
        from src.tools.scanner import wifi_monitor as wm
        if self._csa_running:
            return
        ifaces = wm.monitor_ifaces()
        sig = tuple(ifaces)
        if sig == self._ifaces_sig:
            return
        self._ifaces_sig = sig
        for frame in (self._iface_frame, self._csa_iface_frame):
            for w in frame.winfo_children():
                w.destroy()
        self._iface_labels = {}
        self._csa_iface_labels = {}
        if not ifaces:
            self._iface = None
            for frame in (self._iface_frame, self._csa_iface_frame):
                tk.Label(frame, text="(monitor off)", fg=ERR_COLOR, bg=BG,
                         font=fonts.view_font(10)).pack(side=tk.LEFT)
            return
        if self._iface not in ifaces:
            self._iface = ifaces[0]
        for iface in ifaces:
            for frame, store in ((self._iface_frame, self._iface_labels),
                                 (self._csa_iface_frame,
                                  self._csa_iface_labels)):
                lbl = tk.Label(frame, text=iface, padx=10, pady=3,
                               font=fonts.view_font_bold(10), cursor="")
                lbl.pack(side=tk.LEFT, padx=(0, 6))
                lbl.bind("<Button-1>",
                         lambda e, x=iface: self._set_iface(x))
                lbl.bind("<Enter>",
                         lambda e, x=iface: self._iface_hover(x, True))
                lbl.bind("<Leave>",
                         lambda e, x=iface: self._iface_hover(x, False))
                store[iface] = lbl
        self._update_iface_labels()

    def _set_iface(self, iface):
        self._iface = iface
        self._update_iface_labels()

    def _update_iface_labels(self):
        for store in (self._iface_labels, self._csa_iface_labels):
            for iface, lbl in store.items():
                active = iface == self._iface
                lbl.config(bg=SEL_BG if active else BTN_BG,
                           fg=FG if active else MUTED)

    def _iface_hover(self, iface, entering):
        if iface == self._iface:
            return
        for store in (self._iface_labels, self._csa_iface_labels):
            lbl = store.get(iface)
            if lbl:
                lbl.config(bg=BTN_HOVER if entering else BTN_BG)

    def _refresh_networks(self):
        from src.tools.scanner import wifi_monitor as wm
        nets = wm.get_networks()
        sig = tuple((n["bssid"], n.get("ssid"), n.get("chan"), n.get("stale"))
                    for n in nets)
        if sig == self._nets_sig:
            return
        self._nets_sig = sig
        self._nets = {n["bssid"]: n for n in nets}
        keys = list(self._nets)
        for lb in (self._net_list, self._csa_net_list):
            lb.delete(0, tk.END)
            for i, n in enumerate(nets):
                lb.insert(tk.END, self._net_label(n))
                if n.get("stale"):
                    lb.itemconfig(i, foreground=ERR_COLOR)
            if self._net_key in self._nets:
                idx = keys.index(self._net_key)
                lb.selection_set(idx)
                lb.see(idx)
        if self._net_key not in self._nets:
            self._net_key = None
            self._clients_sig = None
            self._csa_clients_sig = None

    def _net_label(self, n):
        from src.tools.scanner.wifi_monitor import channel_to_freq
        ssid = n.get("ssid") or "(hidden)"
        freq = n.get("freq") or ""
        if not freq:
            chan = n.get("chan") or 0
            if chan:
                freq = f"{channel_to_freq(chan)} MHz"
        label = f"{ssid} / {freq}" if freq else ssid
        if n.get("pmf") in ("capable", "required"):
            label += "  [PMF]"
        return label

    def _on_net_select(self, tab="deauther"):
        lb = self._net_list if tab == "deauther" else self._csa_net_list
        sel = lb.curselection()
        if not sel:
            return
        keys = list(self._nets)
        idx = sel[0]
        if idx < len(keys):
            self._net_key = keys[idx]
        self._clients_sig = None
        self._csa_clients_sig = None
        self._refresh_clients()

    def _refresh_clients(self):
        from src.tools.scanner import wifi_monitor as wm
        net = self._nets.get(self._net_key) or {}
        ssid = net.get("ssid")
        if not ssid or ssid == "(hidden)":
            ssid = None
        bssid = self._net_key
        clients = (wm.probes_for(ssid=ssid, bssid=bssid)
                   if (ssid or bssid) else [])
        sig = tuple(c["mac"] for c in clients)
        if sig == self._clients_sig:
            return
        self._clients_sig = sig
        self._csa_clients_sig = sig
        self._clients = {c["mac"]: c for c in clients}
        keys = list(self._clients)
        for lb in (self._client_list, self._csa_client_list):
            # A disabled Listbox silently ignores delete/insert, so enable it
            # while refilling, then restore the state for the current mode.
            lb.config(state=tk.NORMAL)
            lb.delete(0, tk.END)
            for c in clients:
                lb.insert(tk.END, c["mac"])
            if self._client_key in self._clients:
                idx = keys.index(self._client_key)
                lb.selection_set(idx)
                lb.see(idx)
        self._update_client_state()
        if self._client_key not in self._clients:
            self._client_key = None

    def _on_client_select(self, tab="deauther"):
        lb = self._client_list if tab == "deauther" else self._csa_client_list
        sel = lb.curselection()
        if not sel:
            self._client_key = None
            return
        keys = list(self._clients)
        idx = sel[0]
        if idx < len(keys):
            self._client_key = keys[idx]

    # ---------- actions ----------

    def _selected_net(self):
        if self._net_key:
            return self._nets.get(self._net_key)
        return None

    def _on_deauth(self):
        if self._busy:
            return
        net = self._selected_net()
        if not net:
            self._log("[!] Select a network first.", "error")
            return
        if net.get("pmf") in ("capable", "required"):
            self._log("[!] This network advertises PMF (802.11w); the client "
                      "may ignore forged deauth frames.", "error")
        client = None
        if self._mode == "single":
            client = self._client_key
            if not client:
                self._log("[!] Select a client, or switch to Broadcast.",
                          "error")
                return
        self._busy = True
        self._deauth_btn.config(text="Deauthing...")
        bssid = net["bssid"]
        iface = self._iface
        opts = {
            "count": self._deauth_param("count", int),
            "reason": self._deauth_param("reason", int),
            "interval": self._deauth_param("interval", float),
            "rate": self._deauth_param("rate", int),
        }
        threading.Thread(target=self._run_deauth,
                         args=(bssid, client, iface, opts), daemon=True).start()

    def _run_deauth(self, bssid, client, iface, opts):
        from src.tools.scanner import wifi_monitor as wm
        target = client if client else "all clients (broadcast)"
        self._log_async(
            f"[*] Sending {opts['count']} deauth frames (reason "
            f"{opts['reason']}) to {target} ...")
        if iface:
            wm.reserve_iface(iface)
            wm.wait_iface_released(iface, timeout=6.0)
        ok, msg = False, "Deauth failed."
        try:
            ok, msg = wm.deauth(bssid, client=client, iface=iface, **opts)
        except Exception as e:
            msg = f"Deauth error: {e}"
        finally:
            if iface:
                wm.release_iface(iface)
        self._log_async(("[+] " if ok else "[!] ") + msg,
                        "info" if ok else "error")
        self._post(self._end_deauth)

    def _end_deauth(self):
        self._busy = False
        if not self._destroyed and self.winfo_exists():
            self._deauth_btn.config(text="Deauth")

    def _post(self, fn):
        """Run fn on the GUI thread, safely from a worker thread."""
        try:
            safe = getattr(self.master, "_safe_after", None)
            if callable(safe):
                safe(fn)
                return
        except Exception:
            pass
        try:
            self.after(0, fn)
        except (tk.TclError, RuntimeError):
            pass

    def _log_async(self, text, color="info", tab="deauther"):
        self._post(lambda: self._log(text, color, tab))

    def _log(self, text, color="info", tab="deauther"):
        if self._destroyed or not self.winfo_exists():
            return
        widget = self._out if tab == "deauther" else self._csa_out
        widget.config(state=tk.NORMAL)
        widget.insert(tk.END, text + "\n", color)
        widget.see(tk.END)
        widget.config(state=tk.DISABLED)

    def _log_csa(self, text, color="info"):
        self._log_async(text, color, "csa")

    # ---------- CSA attack ----------

    def _csa_param(self, key, cast):
        from src.tools.scanner.csa_attack import DEFAULTS
        ent = self._csa_params.get(key)
        try:
            return cast(ent.get().strip())
        except Exception:
            return DEFAULTS[key]

    def _deauth_param(self, key, cast):
        from src.tools.scanner.wifi_monitor import DEAUTH_DEFAULTS
        ent = self._deauth_params.get(key)
        try:
            return cast(ent.get().strip())
        except Exception:
            return DEAUTH_DEFAULTS[key]

    def _on_csa_start(self):
        if self._csa_running:
            return
        net = self._selected_net()
        if not net:
            self._log("[!] Select a network first.", "error", "csa")
            return
        iface = self._iface
        if not iface:
            self._log("[!] No monitor interface available.", "error", "csa")
            return
        client = self._client_key if self._mode == "single" else None
        if self._mode == "single" and not client:
            self._log("[!] Select a client, or switch to Broadcast.",
                      "error", "csa")
            return
        chan = net.get("chan") or 0
        if not chan:
            self._log("[!] Unknown channel for the selected network.",
                      "error", "csa")
            return
        sel_ssid = net.get("ssid") or ""
        if self._csa_all_essid and sel_ssid and sel_ssid != "(hidden)":
            targets = [(n.get("bssid"), n.get("chan") or 0)
                       for n in self._nets.values()
                       if n.get("ssid") == sel_ssid and n.get("chan")]
            if net["bssid"] not in [b for b, _ in targets]:
                targets.insert(0, (net["bssid"], chan))
        else:
            targets = [(net["bssid"], chan)]
        targets = [(b, c) for b, c in targets if b and c]
        if not targets:
            self._log("[!] No target BSSID/channel available.",
                      "error", "csa")
            return
        opts = {
            "target_chan": self._csa_param("target_chan", int),
            "attack_window": self._csa_param("attack_window", float),
            "observe_window": self._csa_param("observe_window", float),
            "count": self._csa_param("count", int),
            "csa_interval": self._csa_param("csa_interval", float),
            "tx_rate": self._csa_param("tx_rate", int),
            "duration": self._csa_param("duration", float),
        }
        self._csa_running = True
        self._csa_stop = threading.Event()
        self._csa_start_btn.config(text="Attacking...")
        tlist = ", ".join("%s@ch%d" % (b, c) for b, c in targets)
        self._log(f"[*] {iface} reserved for the CSA attack on "
                  f"{sel_ssid or net['bssid']} ({len(targets)} target(s): "
                  f"{tlist}).", "muted", "csa")
        self._csa_thread = threading.Thread(
            target=self._run_csa,
            args=(iface, targets, client, sel_ssid, opts),
            daemon=True)
        self._csa_thread.start()

    def _run_csa(self, iface, targets, client, ssid, opts):
        from src.tools.scanner import wifi_monitor as wm
        from src.tools.scanner import csa_attack
        try:
            wm.reserve_iface(iface)
            if not wm.wait_iface_released(iface, timeout=6.0):
                self._log_csa("[!] Interface did not become free; continuing "
                              "anyway.", "error")
            summary = csa_attack.csa_pulse(
                iface, targets=targets, client=client, ssid=ssid,
                on_log=lambda m, c="info": self._log_csa(m, c),
                stop_event=self._csa_stop, **opts)
            if summary.get("handshakes"):
                self._log_csa(
                    f"[+] Handshake captured ({summary['handshakes']}) -> "
                    f"{summary.get('hc22000') or 'handshakes dir'}", "success")
            elif not summary.get("ok"):
                self._log_csa(f"[!] {summary.get('reason') or 'failed'}",
                              "error")
            else:
                self._log_csa("[*] Done. No handshake captured this run.")
        except Exception as e:
            self._log_csa(f"[!] Error: {e}", "error")
        finally:
            try:
                wm.release_iface(iface)
            except Exception:
                pass
            self._post(self._end_csa)

    def _on_csa_stop(self):
        if self._csa_stop is not None:
            self._csa_stop.set()
            self._log("[*] Stopping the attack...", "muted", "csa")

    def _end_csa(self):
        self._csa_running = False
        if not self._destroyed and self.winfo_exists():
            self._csa_start_btn.config(text="Start attack")

    def _on_close(self):
        self._destroyed = True
        if self._csa_stop is not None:
            self._csa_stop.set()
        if self._poll_id:
            try:
                self.after_cancel(self._poll_id)
            except tk.TclError:
                pass
            self._poll_id = None
        self.destroy()
