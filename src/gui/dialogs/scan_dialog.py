from src.gui import fonts, windowing
import tkinter as tk
from tkinter import ttk
from src.network_iface import interfaces, ifaddresses, AF_INET
from src.machines import store


class ScanDialog(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.result = None

        self.title("Scanner")
        windowing.size_dialog(self, 580, 460)
        self.configure(bg="#111111")

        self.transient(parent)
        self.wait_visibility(); self.grab_set()

        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=0)
        self.rowconfigure(1, weight=1)

        style = ttk.Style()
        style.theme_use("default")
        style.configure("TNotebook", background="#111111", borderwidth=0)
        style.configure("TNotebook.Tab", background="#222222", foreground="#888888",
                        font=fonts.view_font(11), padding=[20, 6],
                        borderwidth=0, focuscolor="")
        style.map("TNotebook.Tab", background=[("selected", "#111111")],
                  foreground=[("selected", "#ffffff")])

        self._notebook = ttk.Notebook(self)
        self._notebook.grid(row=0, column=0, sticky="ew", padx=0, pady=(5, 0))

        self._scan_frame = tk.Frame(self._notebook, bg="#111111")
        self._tcp_frame = tk.Frame(self._notebook, bg="#111111")
        self._udp_frame = tk.Frame(self._notebook, bg="#111111")
        self._banner_frame = tk.Frame(self._notebook, bg="#111111")

        self._notebook.add(self._scan_frame, text="  Scan  ")
        self._notebook.add(self._tcp_frame, text="  TCP Scan  ")
        self._notebook.add(self._udp_frame, text="  UDP Scan  ")
        self._notebook.add(self._banner_frame, text="  Port-inspector  ")

        self._build_scan_tab()
        self._build_port_tab(self._tcp_frame, "tcpscan")
        self._build_port_tab(self._udp_frame, "udpscan")
        self._build_banner_tab()

        footer = tk.Frame(self, bg="#111111")
        footer.grid(row=1, column=0, sticky="ew", padx=15, pady=(10, 15))

        cancel_btn = tk.Label(
            footer, text="  Cancel  ", bg="#222222", fg="#ffffff",
            font=fonts.view_font(10), relief=tk.RAISED, bd=1,
            padx=15, pady=6, cursor="",
        )
        cancel_btn.pack(side=tk.RIGHT, padx=(5, 0))
        cancel_btn.bind("<Button-1>", lambda e: self.destroy())
        cancel_btn.bind("<Enter>", lambda e: cancel_btn.config(bg="#333333"))
        cancel_btn.bind("<Leave>", lambda e: cancel_btn.config(bg="#222222"))

        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.wait_window(self)

    def _build_scan_tab(self):
        frame = self._scan_frame
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=0)
        frame.rowconfigure(1, weight=1)
        frame.rowconfigure(2, weight=0)

        tk.Label(
            frame, text="Select a network interface for scanning:",
            font=fonts.view_font(11), fg="#ffffff", bg="#111111",
        ).grid(row=0, column=0, sticky="w", padx=15, pady=(15, 5))

        list_frame = tk.Frame(frame, bg="#000000")
        list_frame.grid(row=1, column=0, sticky="nsew", padx=15, pady=(0, 5))
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)

        self._iface_listbox = tk.Listbox(
            list_frame,
            bg="#000000", fg="#ffffff",
            selectbackground="#333333", selectforeground="#ffffff",
            font=fonts.view_font(12), borderwidth=0, highlightthickness=0,
            activestyle="none", exportselection=False,
        )
        self._iface_listbox.grid(row=0, column=0, sticky="nsew")

        scrollbar = tk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self._iface_listbox.yview)
        scrollbar.configure(bg="#333333", troughcolor="#1a1a1a", activebackground="#555555",
                            width=10, borderwidth=0, highlightthickness=0, elementborderwidth=0)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self._iface_listbox.configure(yscrollcommand=scrollbar.set)

        self._interfaces = self._list_interfaces()
        for name, ip, _ in self._interfaces:
            self._iface_listbox.insert(tk.END, f"  {name:<8} {ip}")
        if self._interfaces:
            self._iface_listbox.selection_set(0)
            self._iface_listbox.activate(0)
            self._iface_listbox.focus_set()

        ip_frame = tk.Frame(frame, bg="#111111")
        ip_frame.grid(row=2, column=0, sticky="ew", padx=15, pady=(5, 5))
        ip_frame.columnconfigure(1, weight=1)

        tk.Label(
            ip_frame, text="Or enter a specific IP:",
            font=fonts.view_font(10), fg="#888888", bg="#111111",
        ).grid(row=0, column=0, sticky="w", padx=(0, 10))

        self._scan_ip_var = tk.StringVar()
        self._scan_ip_entry = tk.Entry(
            ip_frame, textvariable=self._scan_ip_var,
            bg="#000000", fg="#ffffff", insertbackground="#ffffff",
            font=fonts.view_font(12), borderwidth=1, relief=tk.FLAT,
            highlightthickness=1, highlightcolor="#333333", highlightbackground="#333333",
        )
        self._scan_ip_entry.grid(row=0, column=1, sticky="ew")
        self._scan_ip_entry.bind("<Return>", lambda e: self._select_scan())

        self._iface_listbox.bind("<Return>", lambda e: self._select_scan())
        self._iface_listbox.bind("<Double-Button-1>", lambda e: self._select_scan())

        select_btn = tk.Label(
            frame, text="  Scan  ", bg="#222222", fg="#ffffff",
            font=fonts.view_font(10), relief=tk.RAISED, bd=1,
            padx=15, pady=6, cursor="",
        )
        select_btn.grid(row=2, column=0, sticky="e", padx=15, pady=(5, 8))
        select_btn.bind("<Button-1>", lambda e: self._select_scan())
        select_btn.bind("<Enter>", lambda e: select_btn.config(bg="#333333"))
        select_btn.bind("<Leave>", lambda e: select_btn.config(bg="#222222"))

    @staticmethod
    def _list_interfaces():
        result = []
        for iface in interfaces():
            if iface == "lo0":
                continue
            addrs = ifaddresses(iface).get(AF_INET)
            if addrs:
                result.append((iface, addrs[0]["addr"], addrs[0]["netmask"]))
        return result

    def _select_scan(self):
        custom_ip = self._scan_ip_var.get().strip()
        if custom_ip:
            self.result = {"action": "scan", "ip": custom_ip}
        else:
            sel = self._iface_listbox.curselection()
            if sel:
                self.result = {"action": "scan", "iface": self._interfaces[sel[0]]}
        self.destroy()

    def _build_port_tab(self, frame, action):
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=0)
        frame.rowconfigure(1, weight=1)
        frame.rowconfigure(2, weight=0)

        label_text = "TCP port scan" if action == "tcpscan" else "UDP port scan"

        tk.Label(
            frame, text=f"Select a machine for {label_text}:",
            font=fonts.view_font(11), fg="#ffffff", bg="#111111",
        ).grid(row=0, column=0, sticky="w", padx=15, pady=(15, 5))

        list_frame = tk.Frame(frame, bg="#000000")
        list_frame.grid(row=1, column=0, sticky="nsew", padx=15, pady=(0, 5))
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)

        lb = tk.Listbox(
            list_frame,
            bg="#000000", fg="#ffffff",
            selectbackground="#333333", selectforeground="#ffffff",
            font=fonts.view_font(11), borderwidth=0, highlightthickness=0,
            activestyle="none",
        )
        lb.grid(row=0, column=0, sticky="nsew")

        scrollbar = tk.Scrollbar(list_frame, orient=tk.VERTICAL, command=lb.yview)
        scrollbar.configure(bg="#333333", troughcolor="#1a1a1a", activebackground="#555555",
                            width=10, borderwidth=0, highlightthickness=0, elementborderwidth=0)
        scrollbar.grid(row=0, column=1, sticky="ns")
        lb.configure(yscrollcommand=scrollbar.set)

        machines = store.get_all_sorted()
        machine_list = [m for m in machines if not (m.ip == "127.0.0.1" or m.ip.startswith("127."))]
        for m in machine_list:
            label = f"  #{m.id:<4} {m.ip:<16} {m.device_type or 'device unknown'}"
            lb.insert(tk.END, label)

        if machine_list:
            lb.selection_set(0)

        lb.bind("<Return>", lambda e: self._select_port(action, machine_list, lb))
        lb.bind("<Double-Button-1>", lambda e: self._select_port(action, machine_list, lb))

        select_btn = tk.Label(
            frame, text="  Scan  ", bg="#222222", fg="#ffffff",
            font=fonts.view_font(10), relief=tk.RAISED, bd=1,
            padx=15, pady=6, cursor="",
        )
        select_btn.grid(row=2, column=0, sticky="e", padx=15, pady=(5, 8))
        select_btn.bind("<Button-1>", lambda e: self._select_port(action, machine_list, lb))
        select_btn.bind("<Enter>", lambda e: select_btn.config(bg="#333333"))
        select_btn.bind("<Leave>", lambda e: select_btn.config(bg="#222222"))

    def _build_banner_tab(self):
        frame = self._banner_frame
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=0)
        frame.rowconfigure(1, weight=1)
        frame.rowconfigure(2, weight=0)

        tk.Label(
            frame, text="Select a machine and port to probe:",
            font=fonts.view_font(11), fg="#ffffff", bg="#111111",
        ).grid(row=0, column=0, sticky="w", padx=15, pady=(15, 5))

        list_frame = tk.Frame(frame, bg="#000000")
        list_frame.grid(row=1, column=0, sticky="nsew", padx=15, pady=(0, 5))
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)

        lb = tk.Listbox(
            list_frame,
            bg="#000000", fg="#ffffff",
            selectbackground="#333333", selectforeground="#ffffff",
            font=fonts.view_font(11), borderwidth=0, highlightthickness=0,
            activestyle="none",
        )
        lb.grid(row=0, column=0, sticky="nsew")

        scrollbar = tk.Scrollbar(list_frame, orient=tk.VERTICAL, command=lb.yview)
        scrollbar.configure(bg="#333333", troughcolor="#1a1a1a", activebackground="#555555",
                            width=10, borderwidth=0, highlightthickness=0, elementborderwidth=0)
        scrollbar.grid(row=0, column=1, sticky="ns")
        lb.configure(yscrollcommand=scrollbar.set)

        machines = store.get_all_sorted()
        machine_list = [m for m in machines if not (m.ip == "127.0.0.1" or m.ip.startswith("127."))]
        for m in machine_list:
            label = f"  #{m.id:<4} {m.ip:<16} {m.device_type or 'device unknown'}"
            lb.insert(tk.END, label)

        if machine_list:
            lb.selection_set(0)

        port_frame = tk.Frame(frame, bg="#111111")
        port_frame.grid(row=2, column=0, sticky="ew", padx=15, pady=(5, 5))
        port_frame.columnconfigure(1, weight=1)

        tk.Label(
            port_frame, text="Port:",
            font=fonts.view_font(10), fg="#888888", bg="#111111",
        ).grid(row=0, column=0, sticky="w", padx=(0, 10))

        banner_port_var = tk.StringVar(value="80")
        banner_port_entry = tk.Entry(
            port_frame, textvariable=banner_port_var,
            bg="#000000", fg="#ffffff", insertbackground="#ffffff",
            font=fonts.view_font(12), borderwidth=1, relief=tk.FLAT, width=8,
            highlightthickness=1, highlightcolor="#333333", highlightbackground="#333333",
        )
        banner_port_entry.grid(row=0, column=1, sticky="w")

        select_btn = tk.Label(
            frame, text="  Scan  ", bg="#222222", fg="#ffffff",
            font=fonts.view_font(10), relief=tk.RAISED, bd=1,
            padx=15, pady=6, cursor="",
        )
        select_btn.grid(row=2, column=0, sticky="e", padx=15, pady=(5, 8))
        select_btn.bind("<Button-1>", lambda e: self._select_banner(machine_list, lb, banner_port_var))
        select_btn.bind("<Enter>", lambda e: select_btn.config(bg="#333333"))
        select_btn.bind("<Leave>", lambda e: select_btn.config(bg="#222222"))

        lb.bind("<Return>", lambda e: self._select_banner(machine_list, lb, banner_port_var))
        lb.bind("<Double-Button-1>", lambda e: self._select_banner(machine_list, lb, banner_port_var))
        banner_port_entry.bind("<Return>", lambda e: self._select_banner(machine_list, lb, banner_port_var))

    def _select_banner(self, machine_list, lb, port_var):
        sel = lb.curselection()
        if sel:
            idx = sel[0]
            if idx < len(machine_list):
                try:
                    port = int(port_var.get().strip())
                except ValueError:
                    port = 80
                self.result = {"action": "port-inspector", "ip": machine_list[idx].ip, "port": port}
                self.destroy()

    def _select_port(self, action, machine_list, lb):
        sel = lb.curselection()
        if sel:
            idx = sel[0]
            if idx < len(machine_list):
                self.result = {"action": action, "ip": machine_list[idx].ip}
                self.destroy()
