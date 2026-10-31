"""Dedicated helpers for the `op-big-pickle` provider.

The opencode free tier (big-pickle) only serves requests that look like the
official OpenCode client. Everything needed for that mimicry lives here:

* the TLS ClientHello fingerprint (Bun/BoringSSL),
* opencode-style session/message identifiers,
* the ``<env>`` block the server expects in the system prompt.

The rules were discovered empirically; see ``big-pickle.md`` at the repo root
for the full list and for the procedure to refresh the fingerprint when
opencode changes its client.

This module must stay free of tkinter and must not import ``utls`` at module
load time (the native wheel is only needed when the provider is actually
used).
"""

import datetime
import os
import secrets
import sys
import threading
import time

PROVIDER_ID = "op-big-pickle"
MODEL = "big-pickle"
BASE_URL = "https://opencode.ai/zen/v1"
API_KEY = "public"
PROJECT = "global"
# Real client UA: opencode/<version> ai-sdk/provider-utils/<v> runtime/bun/<v>
UA = "opencode/1.19.5 ai-sdk/provider-utils/4.0.23 runtime/bun/1.4.4"

_ID_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
_ID_MASK = (1 << 48) - 1
_TIMESTAMP_MASK = (1 << 36) - 1
# A persisted session older than this is regenerated (opencode's timestamp
# wraps every ~795 days, so a month is a safe freshness window).
_MAX_ID_AGE_MS = 30 * 24 * 60 * 60 * 1000

# Captured from the official client: opencode 1.19.5 / Bun 1.4.4.
# JA4: t13d1713h1_5b57614c22b0_7f527383e249
#
# The dict is the exact output of
#   utls.Fingerprint.from_capture(raw_client_hello).to_dict()
# with ``permute_extensions`` disabled because Bun keeps a stable extension
# order (unlike Chrome). Refresh it if opencode/Bun changes its ClientHello:
# capture the handshake (big-pickle.md explains how), run ``to_dict()`` and
# replace this constant.
FINGERPRINT = {
    "alpn": ["http/1.1"],
    "alps": [],
    "alps_use_new_codepoint": True,
    "cipher_suites": [
        4865, 4866, 4867, 49195, 49199, 49196, 49200, 52393, 52392,
        49161, 49171, 49162, 49172, 156, 157, 47, 53,
    ],
    "compress_certificate": [],
    "ech": "off",
    "extensions_order": [0, 23, 65281, 10, 11, 35, 16, 5, 13, 18, 51, 45, 43],
    "grease": False,
    "grease_sigalgs": False,
    "key_shares": [4588, 29],
    "padding": None,
    "permute_extensions": False,
    "permute_trust_anchors": False,
    "record_size_limit": None,
    "signature_algorithms": [
        1027, 2052, 1025, 1283, 2053, 1281, 2054, 1537, 2055, 1539, 513,
    ],
    "supported_groups": [4588, 29, 23, 24],
    "trust_anchors": None,
}

_id_lock = threading.Lock()
_id_last_ms = 0
_id_counter = 0

_ctx = None
_ctx_lock = threading.Lock()


def generate_id(prefix, descending=True):
    """Generate an ID byte-compatible with opencode's identifier.ts.

    OpenCode uses the low 48 bits of ``Date.now() * 0x1000 + counter`` (the
    counter starts at 1 and is shared by all IDs created in the same
    millisecond). Session IDs are descending (bitwise NOT), message IDs are
    ascending.
    """
    global _id_last_ms, _id_counter
    with _id_lock:
        now = int(time.time() * 1000)
        if now != _id_last_ms:
            _id_last_ms = now
            _id_counter = 0
        _id_counter += 1
        value = (now * 0x1000 + _id_counter) & _ID_MASK
        if descending:
            value = (~value) & _ID_MASK
        time_hex = value.to_bytes(6, "big").hex()
        random_part = "".join(
            _ID_CHARS[b % 62] for b in secrets.token_bytes(14)
        )
    return prefix + time_hex + random_part


def is_valid_session_id(session_id):
    """True if ``session_id`` is a usable opencode session ID.

    The server rejects IDs whose counter is 0 (Elwand's legacy generator) and
    IDs encoded with the wrong half of the timestamp.
    """
    if not isinstance(session_id, str) or not session_id.startswith("ses_"):
        return False
    if len(session_id) != 30:
        return False
    try:
        value = int(session_id[4:16], 16)
    except ValueError:
        return False
    decoded = (~value) & _ID_MASK
    counter = decoded & 0xFFF
    if counter < 1:
        return False
    stamp = (decoded >> 12) & _TIMESTAMP_MASK
    now = int(time.time() * 1000) & _TIMESTAMP_MASK
    age = (now - stamp) & _TIMESTAMP_MASK
    return age <= _MAX_ID_AGE_MS


def env_block():
    """Return the ``<env>`` block the server expects in the system prompt."""
    try:
        cwd = os.getcwd()
    except OSError:
        cwd = os.sep
    root = os.path.abspath(os.sep)
    git = "no"
    probe = cwd
    while True:
        try:
            if os.path.isdir(os.path.join(probe, ".git")):
                git = "yes"
                break
        except OSError:
            break
        parent = os.path.dirname(probe)
        if parent == probe:
            break
        probe = parent
    platform = {
        "darwin": "darwin",
        "linux": "linux",
        "win32": "win32",
    }.get(sys.platform, sys.platform)
    date = datetime.datetime.now().strftime("%a %b %d %Y")
    return (
        "<env>\n"
        f"  Working directory: {cwd}\n"
        f"  Workspace root folder: {root}\n"
        f"  Is directory a git repo: {git}\n"
        f"  Platform: {platform}\n"
        f"  Today's date: {date}\n"
        "</env>"
    )


def apply_env(system_prompt):
    """Append the ``<env>`` block to a system prompt."""
    block = env_block()
    if system_prompt:
        return system_prompt.rstrip() + "\n\n" + block
    return block


def with_env(messages):
    """Add the ``<env>`` block to a verbatim message list."""
    block = env_block()
    result = list(messages)
    for index, message in enumerate(result):
        if isinstance(message, dict) and message.get("role") == "system":
            content = message.get("content") or ""
            result[index] = {
                **message,
                "content": content.rstrip() + "\n\n" + block,
            }
            return result
    return [{"role": "system", "content": block}] + result


def build_ssl_context():
    """Return a cached ``utls`` SSLContext with the official fingerprint."""
    global _ctx
    if _ctx is not None:
        return _ctx
    with _ctx_lock:
        if _ctx is None:
            import utls

            context = utls.SSLContext()
            context.load_default_certs()
            context.set_fingerprint(utls.Fingerprint.from_dict(FINGERPRINT))
            _ctx = context
    return _ctx


def build_http_client():
    """Return an HTTP client compatible with the installed OpenAI SDK.

    openai >= 3 uses ``httpx2`` while older versions use ``httpx``.
    ``DefaultHttpxClient`` always points at the right one, so the utls
    SSLContext can be injected without importing the wrong module.
    """
    context = build_ssl_context()
    try:
        from openai import DefaultHttpxClient

        return DefaultHttpxClient(verify=context, timeout=300)
    except ImportError:
        import httpx

        return httpx.Client(verify=context, timeout=300)


def is_free_limit_error(error):
    """True when the server rejected the request for the free-tier quota."""
    response = getattr(error, "response", None)
    if response is None:
        return False
    try:
        return "FreeUsageLimitError" in (response.text or "")
    except Exception:
        return False
