from src.gui import fonts, theme
import tkinter as tk
from .base import BaseView
import src.sessions as sessions

MUTED = "#888888"
BRIGHT = "#ffffff"
INFO = "#5ba3ec"


def _fmt(ts):
    ts = (ts or "").strip()
    return ts[:19].replace("T", " ") if ts else "-"


class SessionDetailView(BaseView):
    name = "session_detail"
    description = "Session detail view"

    def __init__(self, parent, sid, **kwargs):
        self._sid = sid
        self._last_hash = None
        super().__init__(parent, **kwargs)

    def _build_ui(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=0)
        self.rowconfigure(1, weight=1)

        header = tk.Frame(self, bg="#000000")
        header.grid(row=0, column=0, sticky="ew", pady=(15, 10))

        self._title_label = tk.Label(
            header, text="", font=fonts.view_font_bold(22),
            fg="#ffffff", bg="#000000",
        )
        self._title_label.pack(anchor="center")
        self._title_label.bind("<Button-1>", self._on_title_click)
        self._title_label.bind(
            "<Enter>",
            lambda e: self._title_label.config(font=fonts.view_font_bold_under(22)))
        self._title_label.bind(
            "<Leave>",
            lambda e: self._title_label.config(font=fonts.view_font_bold(22)))

        self._on_back_click = None
        self._on_switch_click = None
        self._on_delete_click = None
        self._on_rename_click = None

        text_frame = tk.Frame(self, bg="#000000")
        text_frame.grid(row=1, column=0, sticky="nsew", padx=(220, 20),
                        pady=(0, 20))
        text_frame.columnconfigure(0, weight=1)
        text_frame.rowconfigure(0, weight=1)

        self.text = tk.Text(
            text_frame, bg="#000000", fg=BRIGHT,
            font=fonts.view_font(13), borderwidth=0, highlightthickness=0,
            state=tk.DISABLED, cursor="", wrap=tk.WORD,
        )
        self.text.grid(row=0, column=0, sticky="nsew")

        scrollbar = tk.Scrollbar(text_frame, orient=tk.VERTICAL,
                                 command=self.text.yview)
        scrollbar.configure(bg="#333333", troughcolor="#1a1a1a",
                            activebackground="#555555", width=10, borderwidth=0,
                            highlightthickness=0, elementborderwidth=0)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.text.configure(yscrollcommand=scrollbar.set)

        self.text.tag_configure("muted", foreground=MUTED)
        self.text.tag_configure("bright", foreground=BRIGHT)
        self.text.tag_configure("info", foreground=INFO)

        self.rowconfigure(2, weight=0)
        btn_frame = tk.Frame(self, bg="#000000")
        btn_frame.grid(row=2, column=0, pady=(15, 15))

        back_btn = theme.button(btn_frame, "  \u2190 Back  ", command=self._back)
        back_btn.pack(side=tk.RIGHT, padx=(10, 0))
        self._delete_btn = theme.button(btn_frame, "  Delete  ", command=self._delete)
        self._delete_btn.pack(side=tk.RIGHT, padx=(0, 10))
        self._rename_btn = theme.button(btn_frame, "  Rename  ", command=self._rename)
        self._rename_btn.pack(side=tk.RIGHT, padx=(0, 10))
        self._switch_btn = theme.button(
            btn_frame, "  Switch session  ", command=self._switch)
        self._switch_btn.pack(side=tk.RIGHT, padx=(0, 10))

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

    def _back(self):
        if self._on_back_click:
            self._on_back_click()

    def _switch(self):
        if self._on_switch_click:
            self._on_switch_click(self._sid)

    def _rename(self):
        if self._on_rename_click:
            self._on_rename_click(self._sid)

    def _delete(self):
        if self._on_delete_click:
            self._on_delete_click(self._sid)

    def refresh(self):
        if self._poll_id:
            try:
                self.after_cancel(self._poll_id)
            except Exception:
                pass
            self._poll_id = None
        self._last_hash = None
        self._poll()

    def _refresh(self):
        meta = sessions.read_meta(self._sid)
        active = self._sid == sessions.get_active_id()

        current_hash = hash((tuple(sorted(meta.items())), active))
        if current_hash == self._last_hash and self.text.index("end-1c") != "1.0":
            return
        self._last_hash = current_hash

        name = meta.get("name") or self._sid
        self._title_label.config(text=name)

        rows = [
            ("Name", name),
            ("ID", self._sid),
            ("Status", "active" if active else "inactive"),
            ("Created", _fmt(meta.get("created"))),
            ("Updated", _fmt(meta.get("updated"))),
            ("Target", meta.get("target") or "-"),
            ("Notes", meta.get("notes") or "-"),
            ("Path", str(sessions.session_dir(self._sid))),
        ]
        label_w = max(len(r[0]) for r in rows) + 2

        self.text.configure(state=tk.NORMAL)
        self.text.delete("1.0", tk.END)
        for label, value in rows:
            self.text.insert(tk.END, f"  {label + ':':<{label_w}} ", "muted")
            self.text.insert(tk.END, f"{value}\n", "bright")
        self.text.configure(state=tk.DISABLED)

        if active:
            self._switch_btn.disable()
        else:
            self._switch_btn.enable()

    def _poll(self):
        self._refresh()
        self._poll_id = self.after(2000, self._poll)


def prompt_session_name(parent, current, title="Rename session"):
    """Small modal dialog to edit a session's custom name; returns the name."""
    from src.gui import windowing

    dlg = tk.Toplevel(parent)
    dlg.title(title)
    dlg.configure(bg=theme.BG)
    dlg.transient(parent.winfo_toplevel())

    var = tk.StringVar(value=current or "")
    tk.Label(dlg, text="Session name", fg=theme.MUTED, bg=theme.BG,
             font=fonts.view_font_bold(10), anchor="w").grid(
        row=0, column=0, sticky="w", padx=15, pady=(15, 4))
    ent = theme.entry(dlg, textvariable=var, width=42)
    ent.grid(row=1, column=0, sticky="ew", padx=15)
    dlg.columnconfigure(0, weight=1)

    bf = tk.Frame(dlg, bg=theme.BG)
    bf.grid(row=2, column=0, sticky="e", padx=15, pady=15)
    result = {"value": None}

    def ok(event=None):
        result["value"] = var.get().strip() or None
        dlg.destroy()

    def cancel(event=None):
        dlg.destroy()

    theme.button(bf, "  OK  ", command=ok).pack(side=tk.RIGHT, padx=(6, 0))
    theme.button(bf, "  Cancel  ", command=cancel).pack(side=tk.RIGHT)
    ent.bind("<Return>", ok)
    dlg.bind("<Escape>", cancel)

    windowing.min_size(dlg, 380, 1)
    dlg.update_idletasks()
    dlg.wait_visibility()
    dlg.grab_set()
    ent.focus_set()
    try:
        ent.select_range(0, "end")
    except tk.TclError:
        pass
    parent.wait_window(dlg)
    return result["value"]
