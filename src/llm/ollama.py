"""Minimal Ollama HTTP helpers (stdlib only) used to read server-side state.

Elwand does not start or configure the Ollama server; it only reads:
* the models available on the server, and
* the context window the server will actually use for a model.

The context priority mirrors Ollama: a running model's `/api/ps`
`context_length` is authoritative; otherwise a Modelfile `num_ctx` (from
`/api/show`); otherwise the server default applies (the caller decides).
"""

import json
import urllib.request

# Ollama's default when neither the Modelfile nor OLLAMA_CONTEXT_LENGTH sets it.
DEFAULT_CONTEXT = 4096


def is_ollama_base(base_url, provider_id=""):
    b = (base_url or "").lower()
    return ("11434" in b or "ollama" in b
            or (provider_id or "").lower() == "ollama")


def _root(base_url):
    r = (base_url or "").rstrip("/")
    if r.endswith("/v1"):
        r = r[:-3].rstrip("/")
    return r


def _get(base_url, path, timeout=3):
    req = urllib.request.Request(_root(base_url) + path,
                                 headers={"User-Agent": "elwand"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _post(base_url, path, payload, timeout=3):
    req = urllib.request.Request(
        _root(base_url) + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": "elwand"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _post_stream(base_url, path, payload, timeout=120):
    """POST an endpoint that streams NDJSON status lines (e.g. /api/create)."""
    req = urllib.request.Request(
        _root(base_url) + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": "elwand"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        for raw in r:
            line = raw.strip()
            if not line:
                continue
            try:
                obj = json.loads(line.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                continue
            if isinstance(obj, dict) and obj.get("error"):
                raise RuntimeError(obj["error"])


def list_models(base_url, timeout=3):
    """Return the model names on the server, or None if unreachable."""
    try:
        data = _get(base_url, "/api/tags", timeout)
    except Exception:
        return None
    names = []
    for m in data.get("models", []):
        if not isinstance(m, dict):
            continue
        name = m.get("name") or m.get("model")
        if name:
            names.append(name)
    return names


def _matches(a, b):
    if not a or not b:
        return False
    if a == b:
        return True
    # `llama3.2` matches `llama3.2:3b` (and vice versa).
    return a.split(":")[0] == b.split(":")[0]


def running_context(base_url, model, timeout=3):
    """Context length of a currently loaded model (`/api/ps`), or None."""
    try:
        data = _get(base_url, "/api/ps", timeout)
    except Exception:
        return None
    for m in data.get("models", []):
        if not isinstance(m, dict):
            continue
        names = (m.get("name"), m.get("model"))
        if any(_matches(n, model) for n in names if n):
            value = m.get("context_length")
            if isinstance(value, int) and value > 0:
                return value
    return None


def modelfile_context(base_url, model, timeout=3):
    """`num_ctx` configured in the model's Modelfile (`/api/show`), or None."""
    try:
        data = _post(base_url, "/api/show", {"name": model}, timeout)
    except Exception:
        return None
    params = data.get("parameters")
    if isinstance(params, dict):
        value = params.get("num_ctx")
        if isinstance(value, int) and value > 0:
            return value
    elif isinstance(params, str):
        for line in params.splitlines():
            parts = line.split()
            if len(parts) == 2 and parts[0] == "num_ctx":
                try:
                    value = int(parts[1])
                except ValueError:
                    continue
                if value > 0:
                    return value
    return None


def resolve_context(base_url, model, timeout=3):
    """Return (source, context) the server will use, or (None, None).

    `source` is "running" or "modelfile". When neither is known the caller
    should fall back to `DEFAULT_CONTEXT` (or a user override).
    """
    if not model:
        return None, None
    value = running_context(base_url, model, timeout)
    if value:
        return "running", value
    value = modelfile_context(base_url, model, timeout)
    if value:
        return "modelfile", value
    return None, None


def derived_name(base_model, num_ctx):
    """Name of the context-pinned variant of `base_model` (e.g. `m:tag-ctx4096`)."""
    name, sep, tag = base_model.partition(":")
    suffix = f"-ctx{int(num_ctx)}"
    if sep:
        return f"{name}:{tag}{suffix}"
    return f"{name}{suffix}"


def create_context_model(base_url, base_model, num_ctx, timeout=120):
    """Create (or refresh) a model pinned to `num_ctx`; return its name.

    Ollama's OpenAI-compatible endpoint ignores `num_ctx`, so the only way to
    make a specific context effective without restarting the server is to use
    a Modelfile-derived model. The new model references the base blobs, so it
    costs almost no disk.
    """
    num_ctx = int(num_ctx)
    derived = derived_name(base_model, num_ctx)
    try:
        _post_stream(base_url, "/api/create", {
            "model": derived, "from": base_model,
            "parameters": {"num_ctx": num_ctx}}, timeout)
    except Exception:
        # Fallback for older servers: classic Modelfile string.
        modelfile = f"FROM {base_model}\nPARAMETER num_ctx {num_ctx}\n"
        _post_stream(base_url, "/api/create",
                     {"name": derived, "modelfile": modelfile}, timeout)
    return derived


def ensure_context_model(base_url, base_model, num_ctx, timeout=120):
    """Return a model pinned to `num_ctx`, creating it only if missing."""
    derived = derived_name(base_model, num_ctx)
    models = list_models(base_url)
    if models is not None and derived in models:
        return derived
    return create_context_model(base_url, base_model, num_ctx, timeout)

