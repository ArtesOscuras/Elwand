"""HTTP/HTTPS scheme helpers shared by the inventory and the views."""

HTTPS_PORTS = frozenset({443, 8443, 9443, 4443, 7443, 10443})


def scheme_for_port(port):
    """Return 'https' if `port` is a standard HTTPS port, else 'http'."""
    try:
        return "https" if int(port) in HTTPS_PORTS else "http"
    except (TypeError, ValueError):
        return "http"


def detect_scheme(host, timeout=5.0):
    """Probe `host` over HTTPS then HTTP; return the scheme that responds.

    Returns 'https', 'http', or None if neither responds.
    """
    import ssl
    import urllib.request

    if not host:
        return None
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    for scheme in ("https", "http"):
        try:
            req = urllib.request.Request(
                f"{scheme}://{host}/",
                headers={"User-Agent": "Mozilla/5.0"},
            )
            with urllib.request.urlopen(req, timeout=timeout, context=ctx):
                return scheme
        except Exception:
            continue
    return None
