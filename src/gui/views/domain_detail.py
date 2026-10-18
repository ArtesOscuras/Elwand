from src.gui import fonts
import tkinter as tk
from .base import BaseView
from .dirtree import base_url, insert_clickable_tree
from src.machines import domain_db

MUTED = "#888888"
BRIGHT = "#ffffff"
INFO = "#5ba3ec"


class DomainDetailView(BaseView):
    name = "domain_detail"
    description = "Domain detail view"

    def __init__(self, parent, domain, **kwargs):
        self._domain = domain
        self._last_hash = None
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
        info = domain_db.load_domain_info(self._domain)
        machines = domain_db.load_domain_machines(self._domain)
        subdomains = domain_db.load_subdomains(self._domain)
        directories = domain_db.load_directories(self._domain)
        web = domain_db.load_web_services(self._domain)

        current_hash = hash((
            self._domain,
            tuple(info.items()) if info else None,
            tuple(tuple(m.items()) for m in machines),
            tuple(subdomains),
            tuple(directories),
            tuple(web),
        ))
        if current_hash == self._last_hash and self.text.index("end-1c") != "1.0":
            return
        self._last_hash = current_hash

        self.text.configure(state=tk.NORMAL)
        self.text.delete("1.0", tk.END)

        self._title_label.config(text=f"Domain — {self._domain}")

        first = info.get("first_seen", "") if info else ""
        last = info.get("last_seen", "") if info else ""
        protocol = info.get("protocol", "") if info else ""
        if first and "T" in first:
            first = first[:19].replace("T", " ")
        if last and "T" in last:
            last = last[:19].replace("T", " ")

        rows = [
            ("Domain", self._domain),
            ("Protocol", protocol),
            ("First seen", first),
            ("Last seen", last),
        ]
        label_w = max(len(r[0]) for r in rows) + 2
        for label, value in rows:
            self.text.insert(tk.END, f"  {label + ':':<{label_w}} ", "muted")
            self.text.insert(tk.END, f"{value or '-'}\n", "bright")

        if subdomains:
            self.text.insert(tk.END, f"\nSubdomains ({len(subdomains)}):\n", "info")
            sub_w = max(len(s[0]) for s in subdomains) + 2
            for sub, ts, method in subdomains:
                tag = f"sub_{sub}"
                self.text.tag_configure(tag, underline=False)
                self.text.insert(tk.END, f"  {sub:<{sub_w}}", ("bright", tag))
                self.text.tag_bind(tag, "<Button-1>", lambda e, s=sub: (
                    self._on_subdomain_click and self._on_subdomain_click(s)))
                self.text.tag_bind(tag, "<Enter>", lambda e, t=tag: self.text.tag_configure(t, underline=True))
                self.text.tag_bind(tag, "<Leave>", lambda e, t=tag: self.text.tag_configure(t, underline=False))
                if method:
                    self.text.insert(tk.END, f" ({method})", "muted")
                t = ts.replace("T", " ") if "T" in ts else ts
                self.text.insert(tk.END, f"  {t}\n", "muted")
        else:
            parts = self._domain.split(".")
            if len(parts) > 2:
                parent = ".".join(parts[1:])
                if domain_db.exists(parent):
                    self.text.insert(tk.END, f"\nParent domain:\n", "info")
                    tag = f"sub_{parent}"
                    self.text.tag_configure(tag, underline=False)
                    self.text.insert(tk.END, f"  {parent}", ("bright", tag))
                    self.text.tag_bind(tag, "<Button-1>", lambda e, p=parent: (
                        self._on_subdomain_click and self._on_subdomain_click(p)))
                    self.text.tag_bind(tag, "<Enter>", lambda e, t=tag: self.text.tag_configure(t, underline=True))
                    self.text.tag_bind(tag, "<Leave>", lambda e, t=tag: self.text.tag_configure(t, underline=False))
                    self.text.insert(tk.END, "\n", "muted")
            else:
                self.text.insert(tk.END, "\nSubdomains: (none found yet)\n", "muted")

        directories = domain_db.load_directories(self._domain)
        if directories:
            self.text.insert(tk.END, f"\nDirectories ({len(directories)}):\n", "info")
            insert_clickable_tree(
                self.text, [p for p, _ in directories],
                base_url(self._domain, [p for p, _ in web], preferred=protocol),
                self._copy_to_clipboard)

        web = domain_db.load_web_services(self._domain)
        if web:
            for port, output in web:
                self.text.insert(tk.END, f"\nWeb port {port}:\n", "info")
                for line in output.split("\n"):
                    self.text.insert(tk.END, f"  {line}\n", "bright")

        if machines:
            self.text.insert(tk.END, f"\nMachines ({len(machines)}):\n", "info")
            for m in machines:
                ip = m["machine_ip"]
                tag = f"mch_{ip}"
                self.text.tag_configure(tag, underline=False)
                self.text.insert(tk.END, f"  #{m['machine_id']:<4} {ip}", ("bright", tag))
                self.text.tag_bind(tag, "<Button-1>", lambda e, i=ip: (
                    self._on_machine_click and self._on_machine_click(i)))
                self.text.tag_bind(tag, "<Enter>", lambda e, t=tag: self.text.tag_configure(t, underline=True))
                self.text.tag_bind(tag, "<Leave>", lambda e, t=tag: self.text.tag_configure(t, underline=False))
                if m.get("source"):
                    self.text.insert(tk.END, f" ({m['source']})", "muted")
                self.text.insert(tk.END, "\n")
        else:
            self.text.insert(tk.END, "\nMachines: (none)\n", "muted")

        self.text.configure(state=tk.DISABLED)

    def _copy_to_clipboard(self, url):
        try:
            self.clipboard_clear()
            self.clipboard_append(url)
        except tk.TclError:
            pass
