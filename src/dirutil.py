"""Helpers for the stored directory rows (path, discovered_at, port, scheme)."""


def group_directories(rows):
    """Group directory rows by (scheme, port).

    Returns ``[(scheme, port, [paths...]), ...]`` sorted by port (unknown
    ports last), then by scheme name. Accepts legacy 2-tuples too.
    """
    groups = {}
    for row in rows:
        path = row[0]
        port = row[2] if len(row) > 2 else None
        scheme = row[3] if len(row) > 3 else ""
        key = ((scheme or "").lower(), port)
        groups.setdefault(key, []).append(path)

    def _sort_key(item):
        (scheme, port), _paths = item
        return (1 if port is None else 0, port if port is not None else 0, scheme)

    return [(scheme, port, paths)
            for (scheme, port), paths in sorted(groups.items(), key=_sort_key)]


def port_label(scheme, port):
    if port is None:
        return f"Unknown port ({scheme})" if scheme else "Unknown port"
    return f"Port {port} ({scheme or '?'})"


def note_key(path, port, scheme):
    """Key used by the directory_notes table (unknown port -> -1)."""
    return (path, int(port) if port else -1, (scheme or "").lower())
