import tkinter as tk
import threading
from src.gui import fonts, windowing
from src.machines import people_db
from .base import BaseView

MUTED = "#888888"
BRIGHT = "#ffffff"
INFO = "#5ba3ec"
SUCCESS = "#00cc66"


class _PersonEditDialog(tk.Toplevel):
    def __init__(self, parent, p):
        super().__init__(parent)
        self._person_id = p["id"]
        self.title(f"Edit Person \u2014 {p.get('first_name','')} {p.get('last_name','')}".strip())
        windowing.size_dialog(self, 500, 500)
        self.configure(bg="#111111")
        self.transient(parent)
        self.wait_visibility()
        self.grab_set()

        self.columnconfigure(0, weight=0)
        self.columnconfigure(1, weight=1)

        self._first_var = tk.StringVar(value=p.get("first_name", ""))
        self._last_var = tk.StringVar(value=p.get("last_name", ""))
        self._company_var = tk.StringVar(value=p.get("company", ""))
        self._domain_var = tk.StringVar(value=p.get("domain", ""))
        self._username_var = tk.StringVar(value=p.get("username", ""))
        self._role_var = tk.StringVar(value=p.get("role", ""))
        self._linkedin_var = tk.StringVar(value=p.get("linkedin_url", ""))
        self._source_var = tk.StringVar(value=p.get("source", ""))
        self._interests_var = tk.StringVar(value=p.get("interests", ""))

        row = 0

        fields = [
            ("First Name:", self._first_var),
            ("Last Name:", self._last_var),
            ("Company:", self._company_var),
            ("Domain:", self._domain_var),
            ("Username:", self._username_var),
            ("Role:", self._role_var),
            ("LinkedIn URL:", self._linkedin_var),
            ("Source:", self._source_var),
            ("Interests:", self._interests_var),
        ]

        for label_text, var in fields:
            tk.Label(
                self, text=label_text, font=fonts.view_font(11),
                fg=BRIGHT, bg="#111111",
            ).grid(row=row, column=0, sticky="w", padx=15,
                    pady=(10 if row == 0 else 3, 0))
            tk.Entry(
                self, textvariable=var, bg="#000000", fg=BRIGHT,
                insertbackground=BRIGHT, font=fonts.view_font(11),
                borderwidth=1, relief=tk.FLAT,
                highlightthickness=1, highlightcolor="#333333",
                highlightbackground="#333333",
            ).grid(row=row, column=1, sticky="ew", padx=15,
                    pady=(10 if row == 0 else 3, 0))
            row += 1

        self._feedback = tk.Label(
            self, text="", font=fonts.view_font(10),
            fg=SUCCESS, bg="#111111",
        )
        self._feedback.grid(row=row, column=0, columnspan=2, pady=(10, 0))
        row += 1

        btn_frame = tk.Frame(self, bg="#111111")
        btn_frame.grid(row=row, column=0, columnspan=2, sticky="ew",
                       padx=15, pady=(15, 15))

        close_btn = tk.Label(
            btn_frame, text="  Close  ", bg="#222222", fg=BRIGHT,
            font=fonts.view_font(10), relief=tk.RAISED, bd=1,
            padx=15, pady=6,
        )
        close_btn.pack(side=tk.RIGHT, padx=(5, 0))
        close_btn.bind("<Button-1>", lambda e: self.destroy())
        close_btn.bind("<Enter>", lambda e: close_btn.config(bg="#333333"))
        close_btn.bind("<Leave>", lambda e: close_btn.config(bg="#222222"))

        update_btn = tk.Label(
            btn_frame, text="  Update  ", bg="#222222", fg=BRIGHT,
            font=fonts.view_font(10), relief=tk.RAISED, bd=1,
            padx=15, pady=6,
        )
        update_btn.pack(side=tk.RIGHT)
        update_btn.bind("<Button-1>", lambda e: self._save())
        update_btn.bind("<Enter>", lambda e: update_btn.config(bg="#333333"))
        update_btn.bind("<Leave>", lambda e: update_btn.config(bg="#222222"))

        self.protocol("WM_DELETE_WINDOW", self.destroy)

    def _save(self):
        fn = self._first_var.get().strip()
        ln = self._last_var.get().strip()
        if not fn and not ln:
            return
        people_db.update_person(
            person_id=self._person_id,
            first_name=fn,
            last_name=ln,
            company=self._company_var.get().strip(),
            domain=self._domain_var.get().strip(),
            username=self._username_var.get().strip(),
            role=self._role_var.get().strip(),
            linkedin_url=self._linkedin_var.get().strip(),
            source=self._source_var.get().strip(),
            interests=self._interests_var.get().strip(),
        )
        self._feedback.config(text="Updated.")
        self.after(800, self.destroy)


class _InvestigateInterestsDialog(tk.Toplevel):
    def __init__(self, parent, person):
        super().__init__(parent)
        self._person = person
        name = f"{person.get('first_name','')} {person.get('last_name','')}".strip()
        self.title(f"Investigate Interests — {name}")
        windowing.size_dialog(self, 900, 750, min_w=600, min_h=500)
        self.configure(bg="#111111")
        self.transient(parent)
        self.wait_visibility()
        self.grab_set()

        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=0)
        self.rowconfigure(1, weight=1)
        self.rowconfigure(2, weight=0)
        self.rowconfigure(3, weight=1)
        self.rowconfigure(4, weight=0)

        import src.llm.config as _cfg
        config = _cfg.load()
        prompt_default = config.get("prompts", {}).get(
            "investigate_interests", "")

        tk.Label(
            self, text="System Prompt (editable):",
            font=fonts.view_font_bold(11), fg=BRIGHT, bg="#111111",
        ).grid(row=0, column=0, sticky="w", padx=15, pady=(10, 3))

        prompt_frame = tk.Frame(self, bg="#000000")
        prompt_frame.grid(row=1, column=0, sticky="nsew", padx=15, pady=(0, 10))
        prompt_frame.columnconfigure(0, weight=1)
        prompt_frame.rowconfigure(0, weight=1)

        self._prompt_text = tk.Text(
            prompt_frame, bg="#000000", fg=BRIGHT, insertbackground=BRIGHT,
            font=fonts.view_font(10), borderwidth=1, relief=tk.FLAT,
            highlightthickness=1, highlightcolor="#333333",
            highlightbackground="#333333", wrap=tk.WORD,
            pady=5, padx=8,
        )
        self._prompt_text.insert("1.0", prompt_default)
        self._prompt_text.grid(row=0, column=0, sticky="nsew")

        tk.Label(
            self, text="Output:",
            font=fonts.view_font_bold(11), fg=BRIGHT, bg="#111111",
        ).grid(row=2, column=0, sticky="w", padx=15, pady=(5, 3))

        output_frame = tk.Frame(self, bg="#000000")
        output_frame.grid(row=3, column=0, sticky="nsew", padx=15, pady=(0, 10))
        output_frame.columnconfigure(0, weight=1)
        output_frame.rowconfigure(0, weight=1)

        self._output_text = tk.Text(
            output_frame, bg="#000000", fg=BRIGHT, insertbackground=BRIGHT,
            font=fonts.view_font(10), borderwidth=0, highlightthickness=0,
            state=tk.DISABLED, wrap=tk.WORD, pady=5, padx=8,
        )
        self._output_text.grid(row=0, column=0, sticky="nsew")

        scrollbar = tk.Scrollbar(output_frame, orient=tk.VERTICAL,
                                  command=self._output_text.yview)
        scrollbar.configure(bg="#333333", troughcolor="#1a1a1a",
                            activebackground="#555555",
                            width=10, borderwidth=0, highlightthickness=0,
                            elementborderwidth=0)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self._output_text.configure(yscrollcommand=scrollbar.set)
        self._output_text.tag_configure("tool", foreground=INFO)
        self._output_text.tag_configure("muted", foreground=MUTED)

        btn_frame = tk.Frame(self, bg="#111111")
        btn_frame.grid(row=4, column=0, sticky="ew", padx=15, pady=(8, 15))

        close_btn = tk.Label(
            btn_frame, text="  Close  ", bg="#222222", fg=BRIGHT,
            font=fonts.view_font(10), relief=tk.RAISED, bd=1,
            padx=15, pady=6,
        )
        close_btn.pack(side=tk.RIGHT, padx=(5, 0))
        close_btn.bind("<Button-1>", lambda e: self.destroy())
        close_btn.bind("<Enter>", lambda e: close_btn.config(bg="#333333"))
        close_btn.bind("<Leave>", lambda e: close_btn.config(bg="#222222"))

        investigate_btn = tk.Label(
            btn_frame, text="  Investigate  ", bg="#222222", fg=BRIGHT,
            font=fonts.view_font(10), relief=tk.RAISED, bd=1,
            padx=15, pady=6,
        )
        investigate_btn.pack(side=tk.RIGHT)
        investigate_btn.bind("<Button-1>", lambda e: self._start())
        investigate_btn.bind("<Enter>", lambda e: investigate_btn.config(bg="#333333"))
        investigate_btn.bind("<Leave>", lambda e: investigate_btn.config(bg="#222222"))

        self.protocol("WM_DELETE_WINDOW", self.destroy)

    def _log(self, text, tag=None):
        def _insert():
            self._output_text.configure(state=tk.NORMAL)
            if tag:
                self._output_text.insert(tk.END, text, tag)
            else:
                self._output_text.insert(tk.END, text)
            self._output_text.see(tk.END)
            self._output_text.configure(state=tk.DISABLED)
        self.after(0, _insert)

    def _start(self):
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        try:
            p = self._person
            name = f"{p.get('first_name','')} {p.get('last_name','')}".strip()
            company = p.get("company", "")
            role = p.get("role", "")
            domain = p.get("domain", "")
            linkedin = p.get("linkedin_url", "")

            person_context = f"Person to investigate:\nName: {name}"
            if company:
                person_context += f"\nCompany: {company}"
            if role:
                person_context += f"\nRole: {role}"
            if domain:
                person_context += f"\nDomain: {domain}"
            if linkedin:
                person_context += f"\nLinkedIn: {linkedin}"

            import src.llm.config as _cfg
            config = _cfg.load()
            system_prompt = self._prompt_text.get("1.0", "end-1c").strip()
            config.setdefault("prompts", {})["investigate_interests"] = system_prompt
            _cfg.save(config)

            messages = [
                {"role": "user", "content": person_context},
            ]

            from src.llm import LLMClient
            client = LLMClient(purpose="investigate_interests")

            def _on_tool(tool_name, args, result):
                short = str(args)[:60]
                if tool_name in ("websearch", "webfetch"):
                    summary = f"done ({len(result)} chars)"
                else:
                    summary = result[:80]
                self.after(0, lambda tn=tool_name, s=short, sm=summary: self._log(
                    f"\n[tool] {tn} {s} → {sm}\n", "tool"))

            self._log("Investigating...\n", "muted")
            buf = [""]
            def _on_text(delta):
                buf[0] += delta
                if "\n" not in buf[0]:
                    return
                lines = buf[0].split("\n")
                for line in lines[:-1]:
                    if line.strip():
                        self.after(0, lambda l=line: self._log(l.rstrip() + "\n"))
                buf[0] = lines[-1]
            content = client.chat_with_tools(
                messages, on_tool=_on_tool, tool_context=None, on_text=_on_text)
            if buf[0].strip():
                self.after(0, lambda b=buf[0]: self._log(b.rstrip() + "\n"))
            if content is None:
                self._log("\n(no response)\n", "muted")
                return

            interests = content.strip()
            cleaned = _clean_interests(interests)
            if cleaned:
                people_db.update_person(
                    person_id=p["id"], interests=cleaned)
                self._log(f"\nSaved: {cleaned}\n", "tool")
            else:
                self._log("\nNo interests found.\n", "muted")
        except Exception as e:
            self.after(0, lambda m=str(e): self._log(
                f"\nError: {m}\n", "muted"))


def _clean_interests(text):
    import re
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'<[^>]*$', '', text)
    text = re.sub(r'\b(interests|hobbies|likes|enjoys):\s*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'[\[\](){}"\'*_~`#]', '', text)
    text = re.sub(r'^[-•·▪▸►»›\d]+[.)]\s*', '', text, flags=re.MULTILINE)
    text = re.sub(r'\n+', ', ', text)
    text = re.sub(r',\s*,', ',', text)
    parts = []
    for p in text.split(','):
        p = p.strip().lower()
        p = re.sub(r'^[-•·▪▸►»›]\s*', '', p)
        p = re.sub(r'^\d+[.)]\s*', '', p)
        p = p.strip()
        if p and p not in ('none', 'n/a', 'unknown'):
            parts.append(p)
    seen = set()
    unique = []
    for p in parts:
        if p not in seen:
            seen.add(p)
            unique.append(p)
    if not unique:
        return ""
    return ", ".join(unique)


class PeopleDetailView(BaseView):
    name = "people_detail"
    description = "Person detail view"

    def __init__(self, parent, person_id, **kwargs):
        self._person_id = person_id
        super().__init__(parent, **kwargs)

    def _build_ui(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=0)
        self.rowconfigure(1, weight=1)
        self.rowconfigure(2, weight=0)

        header = tk.Frame(self, bg="#000000")
        header.grid(row=0, column=0, sticky="ew", pady=(15, 10))

        self._title_label = tk.Label(
            header, text="",
            font=fonts.view_font_bold(22),
            fg="#ffffff", bg="#000000",
        )
        self._title_label.pack(anchor="center")
        self._title_label.bind("<Button-1>", self._on_title_click)
        self._title_label.bind(
            "<Enter>",
            lambda e: self._title_label.config(
                font=fonts.view_font_bold_under(22)))
        self._title_label.bind(
            "<Leave>",
            lambda e: self._title_label.config(
                font=fonts.view_font_bold(22)))
        self._on_back_click = None

        text_frame = tk.Frame(self, bg="#000000")
        text_frame.grid(row=1, column=0, sticky="nsew",
                        padx=(220, 20), pady=(0, 10))
        text_frame.columnconfigure(0, weight=1)
        text_frame.rowconfigure(0, weight=1)

        self.text = tk.Text(
            text_frame,
            bg="#000000", fg=BRIGHT, cursor="",
            font=fonts.view_font(13), borderwidth=0, highlightthickness=0,
            state=tk.DISABLED, wrap=tk.WORD,
        )
        self.text.grid(row=0, column=0, sticky="nsew")

        scrollbar = tk.Scrollbar(text_frame, orient=tk.VERTICAL,
                                  command=self.text.yview)
        scrollbar.configure(bg="#333333", troughcolor="#1a1a1a",
                            activebackground="#555555",
                            width=10, borderwidth=0, highlightthickness=0,
                            elementborderwidth=0)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.text.configure(yscrollcommand=scrollbar.set)

        self.text.tag_configure("muted", foreground=MUTED)
        self.text.tag_configure("bright", foreground=BRIGHT)
        self.text.tag_configure("info", foreground=INFO)

        btn_frame = tk.Frame(self, bg="#000000")
        btn_frame.grid(row=2, column=0, sticky="ew", pady=(0, 15))

        inner = tk.Frame(btn_frame, bg="#000000")
        inner.pack(anchor="center")

        edit_btn = tk.Label(
            inner, text="  Edit  ", bg="#222222", fg="#ffffff",
            font=fonts.view_font(10), relief=tk.RAISED, bd=1,
            padx=15, pady=6,
        )
        edit_btn.pack(side=tk.LEFT, padx=(0, 10))
        edit_btn.bind("<Button-1>", lambda e: self._open_edit())
        edit_btn.bind("<Enter>", lambda e: edit_btn.config(bg="#333333"))
        edit_btn.bind("<Leave>", lambda e: edit_btn.config(bg="#222222"))

        investigate_btn = tk.Label(
            inner, text="  Investigate interests  ", bg="#222222", fg=INFO,
            font=fonts.view_font(10), relief=tk.RAISED, bd=1,
            padx=15, pady=6,
        )
        investigate_btn.pack(side=tk.LEFT, padx=(0, 10))
        investigate_btn.bind("<Button-1>", lambda e: self._open_investigate())
        investigate_btn.bind("<Enter>", lambda e: investigate_btn.config(bg="#333333"))
        investigate_btn.bind("<Leave>", lambda e: investigate_btn.config(bg="#222222"))

        back_btn = tk.Label(
            inner, text="  \u2190 Back  ", bg="#222222", fg="#ffffff",
            font=fonts.view_font(10), relief=tk.RAISED, bd=1,
            padx=15, pady=6,
        )
        back_btn.pack(side=tk.LEFT)
        back_btn.bind("<Button-1>",
                      lambda e: self._on_back_click
                      and self._on_back_click())
        back_btn.bind("<Enter>", lambda e: back_btn.config(bg="#333333"))
        back_btn.bind("<Leave>", lambda e: back_btn.config(bg="#222222"))

    def on_activate(self):
        self._refresh()

    def _on_title_click(self, event):
        if self._on_back_click:
            self._on_back_click()

    def _open_edit(self):
        p = people_db.load_person(self._person_id)
        if p:
            dlg = _PersonEditDialog(self, p)
            self.wait_window(dlg)
            self._refresh()

    def _open_investigate(self):
        p = people_db.load_person(self._person_id)
        if p:
            dlg = _InvestigateInterestsDialog(self, p)
            self.wait_window(dlg)
            self._refresh()

    def _refresh(self):
        p = people_db.load_person(self._person_id)

        self.text.configure(state=tk.NORMAL)
        self.text.delete("1.0", tk.END)

        if not p:
            self._title_label.config(text="Person — not found")
            self.text.insert(tk.END, "Person not found.\n", "muted")
            self.text.configure(state=tk.DISABLED)
            return

        full = f"{p.get('first_name','')} {p.get('last_name','')}".strip()
        self._title_label.config(text=full or f"Person #{p['id']}")

        rows = [
            ("First Name", p.get("first_name", "") or "-"),
            ("Last Name", p.get("last_name", "") or "-"),
            ("Company", p.get("company", "") or "-"),
            ("Domain", p.get("domain", "") or "-"),
            ("Username", p.get("username", "") or "-"),
            ("Role", p.get("role", "") or "-"),
            ("LinkedIn URL", p.get("linkedin_url", "") or "-"),
            ("Source", p.get("source", "") or "-"),
            ("Interests", p.get("interests", "") or "-"),
        ]
        label_w = max(len(r[0]) for r in rows) + 2
        for label, value in rows:
            self.text.insert(tk.END,
                             f"  {label + ':':<{label_w}} ", "muted")
            self.text.insert(tk.END, f"{value}\n", "bright")

        self.text.configure(state=tk.DISABLED)
