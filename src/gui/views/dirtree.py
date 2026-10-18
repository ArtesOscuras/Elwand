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
                          muted_tag="muted", bright_tag="bright",
                          flash="#00cc66"):
    """Insert a clickable directory tree into a `tk.Text`.

    `on_copy(url)` is called with `base + node_path` when a node is clicked
    (the node flashes briefly). Returns the list of node paths.
    """
    import tkinter as tk

    def _click(url, tag):
        on_copy(url)
        try:
            text.tag_configure(tag, foreground=flash)
            text.after(700, lambda: _restore(tag))
        except tk.TclError:
            pass

    def _restore(tag):
        try:
            text.tag_configure(tag, foreground="")
        except tk.TclError:
            pass

    def _line(idx, prefix, name, path):
        tag = f"dircopy_{idx}"
        text.tag_configure(tag, underline=False)
        text.insert(tk.END, "  " + prefix, muted_tag)
        text.insert(tk.END, name, (bright_tag, tag))
        text.insert(tk.END, "\n")
        url = base + path
        text.tag_bind(tag, "<Button-1>", lambda e, u=url, t=tag: _click(u, t))
        text.tag_bind(tag, "<Enter>",
                      lambda e, t=tag: text.tag_configure(t, underline=True))
        text.tag_bind(tag, "<Leave>",
                      lambda e, t=tag: text.tag_configure(t, underline=False))

    _line(0, "", "/", "/")
    for idx, (prefix, name, path) in enumerate(render_tree(paths), start=1):
        _line(idx, prefix, name, path)
