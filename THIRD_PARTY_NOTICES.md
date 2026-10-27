# Third-party notices

Elwand bundles the following third-party component. The Elwand project license
does not replace or override the licenses below.

## RT2800 USB helper (`rt2800d`)

- **What it is:** a userspace macOS helper for Ralink/MediaTek RT2800 USB
  Wi-Fi adapters (validated with the RT5592, USB `148f:3572`). It provides
  monitor capture and frame injection without a kext.
- **Source code:** `src/data/rt2800/source/` in this repository. The complete
  source is included in the Elwand wheel and source distribution.
- **License:** GPL-2.0; see `src/data/rt2800/COPYING` and
  `src/data/rt2800/source/COPYING`. Some host files also offer BSD-3-Clause as
  indicated by their SPDX headers.
- **Provenance:** derived from the Linux `rt2x00` / `rt2800usb` driver and a
  macOS userspace port, with Elwand modifications for JSON scanning,
  radiotap/pcap capture, explicit CSA injection, deauth capture,
  DTIM-synchronized deauth and the macOS/Elwand integration. See
  `src/data/rt2800/NOTICE` and `src/data/rt2800/BUILD_INFO`.
- **Binary:** `src/data/rt2800/rt2800d` (arm64). The helper runs as a separate
  process; it is not linked into the Python interpreter.
- **Build:** `make -C src/data/rt2800/source/port install` on macOS with Xcode
  Command Line Tools.
- **Firmware:** `src/data/rt2800/rt2870.bin` is Ralink/MediaTek firmware. Its
  redistribution terms are in `src/data/rt2800/ralink-firmware.txt` and
  `src/data/rt2800/source/LICENSES/ralink-firmware.txt`.

If a redistribution of Elwand omits the source above, the corresponding source
is available from the Elwand repository or from the maintainer on request.

## Other dependencies

Python dependencies declared in `pyproject.toml` retain their own licenses.
Refer to each package's metadata for details.
