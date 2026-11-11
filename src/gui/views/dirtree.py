"""Helpers to render a flat list of URL paths as a clickable ASCII tree.

The tree building/rendering is pure Python; `insert_clickable_tree` lazily
imports tkinter and inserts the lines into a `tk.Text`, copying a full URL
to the clipboard when a node is clicked.
"""

# Ports considered HTTPS when guessing the scheme of a web target.
from src.webscheme import HTTPS_PORTS as _HTTPS_PORTS


def normalize_path(p):
    """Canonicalize a URL path (leading '/', no '//', no trailing '/')."""
    p = (p or "").strip()
    if not p:
        return "/"
    if not p.startswith("/"):
        p = "/" + p
    while "//" in p:
        p = p.replace("//", "/")
    if len(p) > 1:
        p = p.rstrip("/")
    return p or "/"


def build_tree(paths):
    """Nested dict from a list of paths; implied parent nodes are created."""
    root = {}
    for raw in paths:
        p = normalize_path(raw)
        if p == "/":
            continue
        node = root
        for part in p.strip("/").split("/"):
            if not part:
                continue
            node = node.setdefault(part, {})
    return root


def render_tree(paths):
    """Return [(prefix, name, path), ...] lines, sorted alphabetically per level.

    `prefix` holds the box-drawing connectors for that level and `path` is the
    full normalized path of the node (e.g. "/admin/login").
    """
    root = build_tree(paths)
    lines = []

    def walk(node, prefix, cur):
        items = sorted(node.items(), key=lambda kv: kv[0].lower())
        for i, (name, child) in enumerate(items):
            last = i == len(items) - 1
            connector = "└── " if last else "├── "
            path = cur + "/" + name
            lines.append((prefix + connector, name, path))
            walk(child, prefix + ("    " if last else "│   "), path)

    walk(root, "", "")
    return lines


def base_url(host, ports, preferred=None):
    """Best-guess base URL (`scheme://host[:port]`) for a web target.

    `ports` are the target's known web service ports. A `preferred` scheme
    (from stored domain info) wins; otherwise HTTPS is assumed when a standard
    HTTPS port is present, else HTTP. Standard ports (80/443) are omitted,
    non-standard ones kept.
    """
    host = (host or "").strip()
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    ports = [int(p) for p in (ports or []) if p]
    if preferred in ("http", "https"):
        scheme = preferred
    elif ports:
        scheme = "https" if any(p in _HTTPS_PORTS for p in ports) else "http"
    else:
        scheme = "http"
    default = 443 if scheme == "https" else 80
    matching = [p for p in ports if (p in _HTTPS_PORTS) == (scheme == "https")]
    if default in ports:
        chosen = default
    elif matching:
        chosen = matching[0]
    elif preferred in ("http", "https"):
        chosen = default
    elif ports:
        chosen = ports[0]
    else:
        chosen = default
    if chosen == default:
        return f"{scheme}://{host}"
    return f"{scheme}://{host}:{chosen}"


def insert_clickable_tree(text, paths, base, on_copy,
                          note_map=None, note_key_fn=None,
                          stored_paths=None, on_delete=None, on_note=None,
                          expanded_path=None, expanded_note="",
                          on_expand=None, on_collapse=None, on_note_change=None,
                          muted_tag="muted", bright_tag="bright",
                          tag_prefix=""):
    """Insert a directory tree with an inline action row on the open node.

    Clicking a node expands a compact row right below it (pushing the rest of
    the tree down) with Copy / Delete and a note entry; clicking the same node
    again collapses it. ``expanded_path`` is the currently open node (or None),
    ``expanded_note`` its live note text. ``note_map`` maps
    ``note_key_fn(path)`` -> saved note, shown inline in the muted colour.
    """
    import tkinter as tk
    from src.gui import theme, fonts, icons

    old = getattr(text, "_dir_action_frame", None)
    if old is not None and getattr(text, "_dir_action_tag", None) == tag_prefix:
        try:
            old.destroy()
        except tk.TclError:
            pass
        text._dir_action_frame = None
        text._dir_action_tag = None

    note_map = note_map or {}
    stored_paths = stored_paths or set()
    if note_key_fn is None:
        note_key_fn = lambda p: p

    # Clicking/dragging a directory node must not start a text selection (Tk's
    # Text class binding otherwise selects a large range on slight movement).
    if not getattr(text, "_dir_sel_guard", False):
        text._dir_sel_guard = True
        text._dir_click = False

        def _sel_press(event):
            try:
                tags = text.tag_names(f"@{event.x},{event.y}")
            except tk.TclError:
                tags = ()
            text._dir_click = any(t.startswith("dirnode_") for t in tags)

        def _sel_motion(event):
            if getattr(text, "_dir_click", False):
                try:
                    text.tag_remove("sel", "1.0", "end")
                except tk.TclError:
                    pass
                return "break"

        def _sel_release(event):
            was_dir = getattr(text, "_dir_click", False)
            text._dir_click = False
            if was_dir:
                try:
                    text.tag_remove("sel", "1.0", "end")
                except tk.TclError:
                    pass

        text.bind("<ButtonPress-1>", _sel_press, add="+")
        text.bind("<B1-Motion>", _sel_motion, add="+")
        text.bind("<ButtonRelease-1>", _sel_release, add="+")

    def _icon_btn(parent, image, command, enabled=True):
        btn = tk.Label(parent, image=image, bg=theme.BTN_BG, bd=0,
                       padx=2, pady=1, cursor="")
        btn.image = image
        btn._enabled = enabled
        if not enabled:
            btn.config(bg=theme.BG)

        def _enter(event):
            if btn._enabled:
                btn.config(bg=theme.BTN_HOVER)

        def _leave(event):
            btn.config(bg=theme.BTN_BG if btn._enabled else theme.BG)

        def _click(event):
            if btn._enabled and command:
                command()

        btn.bind("<Enter>", _enter)
        btn.bind("<Leave>", _leave)
        if enabled:
            btn.bind("<Button-1>", _click)
        return btn

    def _action_row(prefix, path):
        url = base + path
        frame = tk.Frame(text, bg=theme.PANEL)
        copy_img = icons.copy_icon()
        del_img = icons.delete_icon()
        if copy_img is not None:
            copy_btn = _icon_btn(frame, copy_img,
                                 lambda: on_copy and on_copy(url))
        else:
            copy_btn = theme.button(frame, "copy", padx=6, pady=1, size=9,
                                    command=lambda: on_copy and on_copy(url))
        copy_btn.pack(side=tk.LEFT, padx=(0, 2))
        deletable = path in stored_paths
        if del_img is not None:
            del_btn = _icon_btn(frame, del_img,
                                lambda: on_delete and on_delete(path),
                                enabled=deletable)
        else:
            del_btn = theme.button(frame, "delete", padx=6, pady=1, size=9,
                                   command=lambda: on_delete and on_delete(path))
            if not deletable:
                del_btn.disable()
        del_btn.pack(side=tk.LEFT, padx=(0, 5))
        tk.Label(frame, text="note:", bg=theme.PANEL, fg=theme.MUTED,
                 font=fonts.view_font(9)).pack(side=tk.LEFT, padx=(0, 3))
        entry = theme.entry(frame, width=24)
        entry.insert(0, expanded_note or "")
        entry.pack(side=tk.LEFT)

        def _save_(event=None):
            if on_note:
                on_note(path, entry.get().strip())
            return "break" if event is not None and event.type == tk.EventType.KeyPress else None

        entry.bind("<Return>", _save_)
        entry.bind("<FocusOut>", _save_)
        if on_note_change:
            entry.bind("<KeyRelease>", lambda e: on_note_change(entry.get()))

        # Align under the node name, keeping ancestor vertical bars.
        indent = prefix[:-4] if len(prefix) >= 4 else ""
        text.insert(tk.END, "  " + indent + "    ", muted_tag)
        text.window_create(tk.END, window=frame)
        text.insert(tk.END, "\n")
        text._dir_action_frame = frame
        text._dir_action_tag = tag_prefix

    def _click(path):
        if expanded_path is not None and path == expanded_path:
            if on_collapse:
                on_collapse()
        elif on_expand:
            on_expand(path)

    def _line(idx, prefix, name, path):
        tag = f"dirnode_{tag_prefix}{idx}"
        text.tag_configure(tag, underline=False)
        text.insert(tk.END, "  " + prefix, muted_tag)
        text.insert(tk.END, name, (bright_tag, tag))
        note = (note_map.get(note_key_fn(path)) or "").strip()
        if note:
            display = note if len(note) <= 80 else note[:79] + "\u2026"
            text.insert(tk.END, "  " + display, muted_tag)
        text.insert(tk.END, "\n")
        if expanded_path is not None and path == expanded_path:
            _action_row(prefix, path)
        def _on_click(event, p=path):
            _click(p)
            return "break"   # do not start a text selection

        text.tag_bind(tag, "<Button-1>", _on_click)
        text.tag_bind(tag, "<Enter>",
                      lambda e, t=tag: text.tag_configure(t, underline=True))
        text.tag_bind(tag, "<Leave>",
                      lambda e, t=tag: text.tag_configure(t, underline=False))

    _line(0, "", "/", "/")
    for idx, (prefix, name, path) in enumerate(render_tree(paths), start=1):
        _line(idx, prefix, name, path)
