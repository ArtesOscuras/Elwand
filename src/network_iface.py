"""Drop-in replacement for netifaces using Python stdlib only.

Provides the same API surface that Elwand uses from netifaces:
  - AF_INET
  - interfaces()
  - ifaddresses(iface)
  - gateways()

Implemented with socket + fcntl.ioctl (Linux/macOS) instead of
compiled C extensions.  Compatible with Python 3.11+.
"""

import socket
import struct
import sys

_IS_LINUX = sys.platform.startswith("linux")
_IS_MACOS = sys.platform == "darwin"

if _IS_LINUX:
    _SIOCGIFADDR = 0x8915
    _SIOCGIFNETMASK = 0x891B
elif _IS_MACOS:
    _SIOCGIFADDR = 0xC0206921
    _SIOCGIFNETMASK = 0xC0206925
else:
    _SIOCGIFADDR = 0
    _SIOCGIFNETMASK = 0

AF_INET = socket.AF_INET


def interfaces():
    return [name for _, name in socket.if_nameindex()]


def ifaddresses(name):
    if not _SIOCGIFADDR:
        return {}

    import fcntl

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    except OSError:
        return {}

    try:
        ifreq = struct.pack("256s", name[:15].encode())
        addr_data = fcntl.ioctl(sock.fileno(), _SIOCGIFADDR, ifreq)
        ip = socket.inet_ntoa(addr_data[20:24])

        mask_data = fcntl.ioctl(sock.fileno(), _SIOCGIFNETMASK, ifreq)
        netmask = socket.inet_ntoa(mask_data[20:24])

        return {AF_INET: [{"addr": ip, "netmask": netmask}]}
    except OSError:
        return {}
    finally:
        sock.close()


def gateways():
    default = _default_gateway()
    if default:
        gw_ip, iface = default
        return {"default": {AF_INET: [gw_ip, iface]}}
    return {}


def _default_gateway():
    if _IS_LINUX:
        return _gateway_linux()
    if _IS_MACOS:
        return _gateway_macos()
    return None


def _gateway_linux():
    try:
        with open("/proc/net/route") as f:
            for line in f:
                fields = line.strip().split()
                if len(fields) < 4:
                    continue
                if fields[1] == "00000000" and int(fields[3], 16) & 0x0002:
                    gw_raw = struct.pack("<I", int(fields[2], 16))
                    gw_ip = socket.inet_ntoa(gw_raw)
                    return gw_ip, fields[0]
    except (OSError, ValueError):
        pass
    return None


def _gateway_macos():
    import re
    import subprocess

    try:
        r = subprocess.run(
            ["route", "-n", "get", "default"],
            capture_output=True, text=True, timeout=5,
        )
        gw = None
        iface = None
        for line in r.stdout.splitlines():
            m = re.match(r"\s*gateway:\s*(\S+)", line)
            if m:
                gw = m.group(1)
            m = re.match(r"\s*interface:\s*(\S+)", line)
            if m:
                iface = m.group(1)
        if gw and iface:
            return gw, iface
    except (FileNotFoundError, OSError):
        pass
    return None
