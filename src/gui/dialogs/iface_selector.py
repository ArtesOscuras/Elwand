from src.gui import fonts, windowing
import tkinter as tk
from src.network_iface import interfaces, ifaddresses, AF_INET


class InterfaceSelector(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.result = None

        self.title("Select Interface")
        windowing.size_dialog(self, 500, 350)
        self.configure(bg="#111111")

        self.transient(parent)
        self.wait_visibility(); self.grab_set()

        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        self.rowconfigure(2, weight=0)
        self.rowconfigure(3, weight=0)

        tk.Label(
            self,
            text="Select a network interface for scanning:",
            font=fonts.view_font(11),
            fg="#ffffff",
            bg="#111111",
        ).grid(row=0, column=0, sticky="w", padx=15, pady=(15, 5))

        list_frame = tk.Frame(self, bg="#000000")
        list_frame.grid(row=1, column=0, sticky="nsew", padx=15, pady=(0, 5))
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)

        self.listbox = tk.Listbox(
            list_frame,
            bg="#000000",
            fg="#ffffff",
            selectbackground="#333333",
            selectforeground="#ffffff",
            font=fonts.view_font(12),
            borderwidth=0,
            highlightthickness=0,
            activestyle="none",
        )
        self.listbox.grid(row=0, column=0, sticky="nsew")

        scrollbar = tk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.listbox.yview)
        scrollbar.configure(bg="#333333", troughcolor="#1a1a1a", activebackground="#555555",
                            width=10, borderwidth=0, highlightthickness=0, elementborderwidth=0)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.listbox.configure(yscrollcommand=scrollbar.set)

        self._interfaces = self._list_interfaces()
        for name, ip, _ in self._interfaces:
            self.listbox.insert(tk.END, f"  {name:<8} {ip}")

        if self._interfaces:
            self.listbox.selection_set(0)

        ip_frame = tk.Frame(self, bg="#111111")
        ip_frame.grid(row=2, column=0, sticky="ew", padx=15, pady=(5, 5))
        ip_frame.columnconfigure(1, weight=1)

        tk.Label(
            ip_frame,
            text="Or enter a specific IP:",
            font=fonts.view_font(10),
            fg="#888888",
            bg="#111111",
        ).grid(row=0, column=0, sticky="w", padx=(0, 10))

        self.ip_var = tk.StringVar()
        self.ip_entry = tk.Entry(
            ip_frame,
            textvariable=self.ip_var,
            bg="#000000",
            fg="#ffffff",
            insertbackground="#ffffff",
            font=fonts.view_font(12),
            borderwidth=1,
            relief=tk.FLAT,
            highlightthickness=1,
            highlightcolor="#333333",
            highlightbackground="#333333",
        )
        self.ip_entry.grid(row=0, column=1, sticky="ew")
        self.ip_entry.bind("<Return>", lambda e: self._select())

        btn_frame = tk.Frame(self, bg="#111111")
        btn_frame.grid(row=3, column=0, sticky="ew", padx=15, pady=(5, 15))

        cancel_btn = tk.Label(
            btn_frame,
            text="  Cancel  ",
            bg="#222222",
            fg="#ffffff",
            font=fonts.view_font(10),
            relief=tk.RAISED,
            bd=1,
            padx=15,
            pady=6,
            cursor="",
        )
        cancel_btn.pack(side=tk.RIGHT, padx=(5, 0))
        cancel_btn.bind("<Button-1>", lambda e: self._cancel())
        cancel_btn.bind("<Enter>", lambda e: cancel_btn.config(bg="#333333"))
        cancel_btn.bind("<Leave>", lambda e: cancel_btn.config(bg="#222222"))

        select_btn = tk.Label(
            btn_frame,
            text="  Select  ",
            bg="#222222",
            fg="#ffffff",
            font=fonts.view_font(10),
            relief=tk.RAISED,
            bd=1,
            padx=15,
            pady=6,
            cursor="",
        )
        select_btn.pack(side=tk.RIGHT)
        select_btn.bind("<Button-1>", lambda e: self._select())
        select_btn.bind("<Enter>", lambda e: select_btn.config(bg="#333333"))
        select_btn.bind("<Leave>", lambda e: select_btn.config(bg="#222222"))

        self.listbox.bind("<Return>", lambda e: self._select())
        self.listbox.bind("<Double-Button-1>", lambda e: self._select())
        self.listbox.focus_set()

        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.wait_window(self)

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

    def _select(self):
        custom_ip = self.ip_var.get().strip()
        if custom_ip:
            self.result = ("ip", custom_ip, "")
        else:
            sel = self.listbox.curselection()
            if sel:
                self.result = self._interfaces[sel[0]]
        self.destroy()

    def _cancel(self):
        self.destroy()
