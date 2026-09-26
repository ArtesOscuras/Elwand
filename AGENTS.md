# AGENTS.md

# Elwand (Your AI-Powered Security Workbench)

## Project Overview

Elwand is a Python-based penetration testing platform that provides both a command-line interface and a graphical user interface within the same application.

The application is intended to assist security professionals during assessments by combining interactive workflows, evidence collection, and structured data visualization.

The project must remain maintainable, portable, and suitable for installation through `pipx`.

---

## Core Principles

* Prioritize simplicity and maintainability.
* Minimize external dependencies whenever possible.
* Avoid introducing heavy frameworks unless there is a clear and justified benefit.
* Preserve backward compatibility unless explicitly instructed otherwise.
* Favor explicit, readable code over clever implementations.
* Keep the project compatible with Python 3.11 or newer.

---

## Architecture Overview

The application consists of two major UI areas:

### Lower Section: Interactive Console

The bottom portion of the interface contains an interactive console.

This console allows users to operate Elwand through command-line interactions while the graphical interface remains active.

Features implemented for the GUI should not break console-based workflows, and vice versa.

---

### Upper Section: Views

The upper portion of the interface displays graphical views.

These views present information that Elwand has collected and stored in its databases during operation.

Views should primarily act as visual representations of persisted data rather than independent sources of truth.

---

### Navigation Bar

The navigation bar is implemented in:

```
src/gui/views/nav.py
```

It is located at the top of the views section.

The nav bar includes a **settings gear icon** (`settings.png`, `icons.scaled(34)`) on the far left that opens `SettingsDialog` via a callback (`set_settings_callback(fn)`) registered by `App.__init__` **before** `_register_views()` so the callback is available when views construct their nav bars. The icon follows the same hover pattern as buttons (`bg="#000000"` → `bg="#222222"`, no cursor change).

When modifying navigation behavior:

* Preserve consistency across all views.
* Avoid introducing view-specific hacks.
* Keep navigation logic centralized whenever possible.

### Main Window and Fullscreen

The main window opens in **true fullscreen** (`self.attributes("-fullscreen", True)`). It is applied via `self.after(0, self._enter_fullscreen)` so it runs after the window is mapped; `_enter_fullscreen` re-measures the active view's labels (`_refresh_labels`) to avoid the macOS Aqua stale-metrics issue. `F11` toggles fullscreen (`_toggle_fullscreen`); on macOS `<Command-Control-f>` is bound as well because the system may intercept F11 for "Show Desktop". A centered restore geometry (90% of the screen, capped at 1280x800) is set before entering fullscreen so leaving it does not drop to the 800x600 minimum.

Dialog sizing is handled by the central `windowing` module (see "Modal Dialogs and Cross-Platform `grab_set()`"); the main window geometry itself is not run through it.

---

### Mouse and Clickable Elements

Elwand uses a **hover-only** interaction model. The mouse cursor never changes (`cursor` is always the system default, never `"hand2"`). Clickability is communicated through visual hover effects:

**Clickable text** (nav links, machine names, domain links, hash types, etc.):
- Normal state: no underline, `fg="#ffffff"` (bright) or `fg="#888888"` (muted)
- Hover state: **underline** + slightly lighter color
- Pattern: `<Enter>` sets `font=(..., "underline")`, `<Leave>` restores

```python
btn.bind("<Enter>", lambda e: btn.config(font=fonts.view_font_bold_under(11)))
btn.bind("<Leave>", lambda e: btn.config(font=fonts.view_font_bold(11)))
```

**Buttons** (clickable Labels styled as buttons):
- Normal state: `bg="#222222"`
- Hover state: `bg="#333333"` (subtle lightening)
- Pattern: `<Enter>` sets `bg="#333333"`, `<Leave>` restores `bg="#222222"`

```python
btn.bind("<Enter>", lambda e: btn.config(bg="#333333"))
btn.bind("<Leave>", lambda e: btn.config(bg="#222222"))
```

**Rules:**
- Never set `cursor="hand2"` or any custom cursor.
- Do not change font weight on hover (bold stays bold, regular stays regular).
- For underlined hover on bold text, use `view_font_bold_under(size)` which preserves `"bold"` weight while adding underline.
- All text widgets (non-clickable) set `cursor=""` explicitly to prevent I-beam on disabled widgets.

---

### Event Bus (`src/event_bus.py`)

The event bus decouples background threads (scanner, tools) from the GUI main thread.

* Background threads call `event_bus.submit({"type": "...", ...})` without touching tkinter.
* The `EventAggregator` drains events from a thread-safe queue and delivers them to the main thread in batches via `root.after()`.
* Default flush interval: 300ms (configurable). If the queue fills, flushes every 10ms with a max of 15 events per batch to prevent Tcl bridge saturation.
* All GUI callbacks (`_process_scanner_events`) run exclusively in the main thread.

Future tools (hydra, hashcat) should follow the same pattern: submit events to the bus, never call `after()` or touch tkinter from worker threads/processes.

---

### Named Fonts and Zoom (`src/gui/fonts.py`)

The application uses **named tkinter fonts** for all view components. This enables live zoom via named font reconfiguration — when `fonts.set_view_scale(factor)` is called, ALL widgets using `view_font(N)` or `view_font_bold(N)` update their font size instantly without requiring widget re-creation.

Key functions:

* `view_font(size)` / `view_font_bold(size)` — return named `tkinter.font.Font` objects.
* `view_font_under(size)` / `view_font_bold_under(size)` — underlined variants for hover effects.
* `set_view_scale(factor)` — reconfigures all named fonts. Clamped to [0.5, 4.0].
* `set_root(root)` — must be called once after `tk.Tk()` is created, before any view is instantiated.

When adding new views, **always use `view_font` / `view_font_bold` instead of raw font tuples**. This ensures the view responds to zoom without additional work.

**Icons (`src/gui/icons.py`):** icon sizes are reference sizes that must be scaled with `icons.scaled(base)`, which multiplies by the global scale (`windowing.ui_scale() * fonts.view_scale()`). Pass the scaled value to `icons.icon(name, size=icons.scaled(base))` and use the same value in any manual pixel layout (row widths, tab stops), otherwise icons and columns will drift after a zoom or on a HiDPI screen. `icons.delete_icon()` and `all_icons()` already scale internally. On zoom, `nav._zoom()` calls `set_zoom_callback` (wired by `App._on_zoom_changed`) to force the active view to re-render so the new icon sizes take effect immediately.

---

### GUI Layout Stability on macOS Aqua

Tkinter on macOS Aqua has a known issue where `Label` widgets created before their parent window is fully mapped cache incorrect font metrics. This causes navigation bars, view titles, and other `Label`-based components to render with compressed or incorrect sizing. The layout corrects itself only when an explicit widget reconfiguration (e.g., font change on hover) triggers a full re-measurement.

**Symptoms:**

* Navigation bar buttons appear compressed (too close together) and spread apart only when the mouse hovers over them.
* View titles appear clipped or truncated.
* The problem occurs on every application startup and every GUI resize.
* Switching away from the window and back (alt+tab) temporarily fixes the layout, as does pressing Tab or clicking a nav button.

**Root Cause:**

All views are constructed during `_register_views()` (called from `App.__init__`). At construction time, each view calls `_build_ui()` which creates its widget tree — including the nav bar and title labels — but the view has not yet been gridded into the visualizer. The parent widget width is 1 pixel.

`tk.Label` (and the underlying Tcl `label` widget) calculates its preferred size using CoreText font metrics. On macOS, these metrics may be computed differently when the parent is unmapped or has a degenerate width. The cached preferred size persists even after the view is later gridded at its real width, because `Label` does not re-measure unless explicitly reconfigured (e.g., via `config(font=...)`).

When the user hovers over a nav button, the `<Enter>` handler calls `btn.config(font=hover_font)`, which triggers a full re-measurement of the Label. The new preferred size is correct (computed against the now-mapped parent), and the `pack` layout manager recalculates positions. This is why the layout "fixes itself" on hover.

After `set_initial_zoom()` (which calls `fonts.set_view_scale()`), all named fonts are reconfigured with new sizes. This triggers a resize of all Labels using those fonts, but the Labels again use potentially-stale metrics from before the view was properly mapped.

**Solution (implemented in `src/gui/visualizer.py`):**

After every view activation (`activate_view()`), and after the initial zoom configuration in `App.__init__`, force all `Label` widgets in the active view to re-measure by calling a recursive `_refresh_labels()` helper, then process pending geometry with `update_idletasks()`.

```python
# visualizer.py - activate_view()
self._active_view.grid(row=0, column=0, sticky="nsew")
self._active_view.on_activate()
self.winfo_toplevel().update_idletasks()
self._active_view.update_idletasks()
self._refresh_labels(self._active_view)
self.winfo_toplevel().update_idletasks()
```

```python
# visualizer.py - _refresh_labels (static method)
@staticmethod
def _refresh_labels(widget):
    if isinstance(widget, tk.Label):
        try:
            f = widget.cget("font")
            if f:
                widget.config(font=f)  # idempotent, forces re-measurement
        except Exception:
            pass
    for child in widget.winfo_children():
        Visualizer._refresh_labels(child)
```

The same `_refresh_labels()` call is made in `App.__init__` after `set_initial_zoom()` to handle the startup zoom configuration:

```python
# app.py - after set_initial_zoom()
self.visualizer.winfo_toplevel().update_idletasks()
self.visualizer._refresh_labels(self.visualizer.get_active_view())
self.visualizer.winfo_toplevel().update_idletasks()
```

**Rules for future development:**

* Do NOT modify the navigation bar layout from `pack` to `grid` or vice versa — the original `pack`-based centering with expandable springs is correct and must be preserved.
* Do NOT add `<Configure>` event handlers to nav bar frames as a workaround — these fire unpredictably on macOS and cause multiple redundant layout passes.
* When adding new views with `Label`-based components (titles, nav bars, headers), the `_refresh_labels` mechanism in `activate_view()` handles them automatically — no per-view workaround is needed.
* If a new view is constructed AFTER the initial `activate_view("tools")` call (e.g., lazy-created detail views), it will be built when the visualizer is already mapped, so its Labels will have correct metrics from the start. Only views created during startup registration are affected.

---

### Modal Dialogs and Cross-Platform `grab_set()`

When opening a `tk.Toplevel` dialog that uses `grab_set()` (modal behavior), always call `self.wait_visibility()` before `self.grab_set()`. Without this, Linux X11/Wayland window managers may not have finished mapping the window, causing `tkinter.TclError: grab failed: window not viewable`.

**Correct pattern:**

```python
self.transient(parent)
# Build ALL widgets here (labels, entries, buttons, etc.)
self.minsize(width, 1)      # minimum width, let height be natural
self.update_idletasks()     # force layout calculation
self.wait_visibility()      # must precede grab_set on Linux
self.grab_set()
```

**Important:** Build all widgets **before** `wait_visibility()` so the dialog sizes to its natural content height. Avoid fixed `geometry("WxH")` — prefer `minsize(width, 1)` for minimum width and let the grid/pack layout determine the height. This prevents empty wasted space at the bottom of the dialog.

**DPI-aware sizing (`src/gui/windowing.py`):** never hardcode a dialog's pixel size. Use the central helper so dialogs scale with the display DPI (Linux X11/Wayland is not HiDPI-aware in Tk, so raw pixel sizes look tiny on high-DPI screens):

```python
from src.gui import windowing

windowing.size_dialog(self, 800, 700)                        # reference size at 96 DPI
windowing.size_dialog(self, 900, 640, min_w=760, min_h=520)  # + scaled minimum size
windowing.min_size(dialog, 620, 1)                           # for content-sized dialogs
```

`windowing.init(root)` is called once in `App.__init__` (right after `elwand_settings.load()`). On Linux it sets `tk scaling` from the display DPI and multiplies reference sizes by `dpi/96` (clamped to 95% of the screen); on macOS it is a no-op, preserving the tuned look. Override with the `ELWAND_UI_SCALE`/`ELWAND_DPI` env vars or the `ui_scale` key in `settings.json`.

This pattern is already used in `HashcatDialog`, `InitDialog`, `_CredentialGenerator`, `SettingsDialog`, `_AddUserDialog`, `_AddPersonDialog`, `_UserEditDialog`, `_PersonEditDialog`, and others. New dialogs must follow it.

---

### Path Centralization (`src/elwand_paths.py`)

All filesystem paths are defined in a single module. Never use `os.path.dirname(__file__)` to locate resources.

* **Package data** (bundled with pipx): `fonts_dir()`, `icons_dir()`, `hashcat_db()`, `logs_dir()`
* **Runtime data** (user's home): `databases_dir()`, `credentials_dir()`, `evidence_dir()`, `chrome_profile_dir()`, `antibot_profile_dir()`, `lst_dir()`, `rules_dir()`, `pocs_dir()`, `reports_dir()`, `cache_dir()`, `settings_file()`, `session_file()`, `runtime_logs_dir()`
* Runtime directories are created lazily with `os.makedirs(exist_ok=True)`.
* Override runtime root via `Elwand_HOME` environment variable.

---

## Database and Data Representation

The application stores operational data that is later displayed by the views.

General rules:

* Persist information before presenting it in the GUI.
* Treat databases as the canonical source of application state.
* Avoid duplicating state unnecessarily.
* Ensure database interactions are explicit and easy to trace.

---

## Settings Persistence (`src/settings.py`)

User preferences (console font size, view zoom level) are persisted to `~/.local/share/elwand/settings.json`.

* `load()` / `save()` — read/write JSON with thread-safe I/O.
* `get(key, default)` / `set(key, value)` — access in-memory dict, thread-safe.
* Settings are loaded once at startup (`App.__init__`) and saved on every font/zoom change and on graceful shutdown (`_on_close`).

---

## Session Persistence (`src/llm/session.py`)

The LLM conversation context (and the rendered console output) is persisted to a **single file** `~/.local/share/elwand/session.json` (path via `session_file()` in `src/elwand_paths.py`), so it survives a restart.

* `save(messages, mode=None, context_injected=False, total_api_tokens=0, console_segments=None, session_id=None, project_id=None)` — writes atomically (temp file + `os.replace`) under a `threading.Lock`.
* `load()` — reads and returns the data dict, or `None` if missing/corrupt.
* `clear()` — deletes the file.

The persisted dict holds:
- `messages` — the full `_llm_messages` conversation (serialized via `serialize_messages`, which handles dicts and OpenAI message objects, preserving `tool_calls`, `tool_call_id`, and the markers `_is_context` / `_is_compaction` / `_recent`).
- `mode` — last active mode (`"agent"` / `"consultor"` / `null`).
- `context_injected` — whether the state snapshot was already injected.
- `total_api_tokens` — last `prompt_tokens` from the API (used for the context % and compaction trigger).
- `console_segments` — list of `[text, color]` pairs, the rendered console output with colors.
- `llm_session_id` — the opencode `x-opencode-session` id (`ses_`), kept stable across restarts.
- `llm_project_id` — the opencode `x-opencode-project` id (fixed default unless changed with `debug rotate_opencode_headers`).
- `updated` — ISO timestamp of the last write.

**Integration (`src/gui/app.py`):**
- `_save_session()` — snapshots `list(self._llm_messages)` and the console segments, and writes the file. It is called in **real time**: after the user prompt is appended (synchronously), after each tool call/result (`_persist()` inside `chat_with_tools`), and in the `finally` of each exchange. It checks `_closing` and skips during shutdown.
- `_load_session()` — on startup (`App.__init__`), loads the messages (stripping `_is_context` so the next prompt re-injects a fresh state snapshot), restores `total_api_tokens`, the console via `console.restore_segments()`, and the opencode `llm_session_id`/`llm_project_id`; returns the saved `mode` so the app re-enters agent/consultor mode.
- `_clear_session()` — deletes the file. Called by the `reset` command (both modes), which also clears `_llm_messages`, `_total_api_tokens`, `_llm_session_id`, `_llm_project_id`, and the cache.
- The console tracks its content as `(text, color)` segments in `Console._segments` (`src/gui/console.py`), updated in `write()` / `_write_segments()` and reset in `_cmd_clear()`.

**Rules:**
- The machine/domain/inventory databases are already persistent and remain **outside** the session (the session is currently only the model context + console display).
- The session must stay a **single file** so sessions can be loaded/listed easily in the future.
- `_save_session()` performs no tkinter calls (the console segment capture is a plain Python list read), so it is safe to call from worker threads.

---

## Debugging Logs

The following location is reserved for debugging purposes:

```
src/logs/debugging_logs
```

Multiple modules define a `_dbg()` helper that writes timestamped lines to this file. The `_dbg()` implementations silently ignore `PermissionError` and `OSError` — in a pipx installation, the log file at `site-packages/src/logs/` will be non-writable, and logging is automatically suppressed.

Guidelines:

* Use debugging logs only when they provide meaningful diagnostic value.
* Avoid excessive logging.
* Ensure sensitive information is not unnecessarily recorded.
* Temporary debugging mechanisms should be removable once issues are resolved.
* In development, logs go to `src/logs/debugging_logs`. In production (pipx), they fail silently.

---

## Fonts

Elwand must not depend on fonts provided by the operating system.

The application uses its own bundled fonts located at:

```
src/fonts/
```

Requirements:

* Always use the bundled fonts.
* Do not rely on platform-specific font availability.
* Maintain a consistent appearance across operating systems.

---

## Packaging and Distribution

Elwand is intended to be installed using:

```
pipx
```

Requirements:

* The application must function correctly when installed through pipx.
* Avoid assumptions about editable installations.
* Ensure packaged resources are correctly included.
* Verify that non-code assets remain accessible after installation.

---

## Python Compatibility

Target environment:

* Python 3.11 or newer.
* Tcl/Tk 8.6 or newer (included with Python).

Requirements:

* Do not introduce features that require versions older than 3.11.
* Do not rely on unreleased Python functionality.
* Maintain compatibility across supported Python versions.

---

## Dependency Policy

Dependencies must be kept to an absolute minimum.

Before adding a dependency:

1. Determine whether the functionality can be implemented using the Python standard library.
2. Evaluate the maintenance and portability costs.
3. Justify why the dependency is necessary.
4. **Test the dependency in the pipx environment** — some libraries (e.g., `python-nmap`) use `subprocess` with `shell=True` which triggers `fork()` on macOS and corrupts the CoreFoundation event loop used by Tk Aqua, causing 3-6 second GUI freezes.

Avoid introducing large dependency trees.

---

## External Binary Dependencies

Elwand may rely on external security tools that are expected to exist on the host system.

Examples include:

* `nmap`
* `hashcat`

Guidelines:

* Detect the presence of required binaries gracefully.
* Provide clear error messages when binaries are unavailable.
* Do not bundle these binaries.
* Do not assume fixed installation paths.
* Support standard discovery mechanisms (e.g., PATH resolution).

---

## Hashcat (`src/tools/hashcat/`, dialog + console)

`HashcatEngine` (`src/tools/hashcat/engine.py`) wraps the `hashcat` binary for background cracking, used by both the hashcat dialog and the `use hashcat` console command.

**Binary resolution:** `resolve("hashcat")` (`src/resolve_binary.py`) checks `PATH`, then a shell-rc alias, then `$SHELL -ic 'command -v'`. Under `sudo` it reads the real user's rc via `SUDO_USER` (`_real_home`), otherwise `~` is root's home and the alias is missed.

**Kernel cache:** before running, `_clear_unreadable_kernels()` removes `<hashcat>/kernels/*.kernel` files the current user cannot read/write (a previous run as root leaves them root-owned and the kernel build fails with `Permission denied`); the cache is regenerated by hashcat. If the build still fails, an actionable hint is emitted.

**Status stream:** the engine runs hashcat with `--status --status-timer=1` plus `--status-json` (when supported) and reads stdout in chunks (`os.read`) so hashcat's no-newline phase messages surface. Callbacks:
- `on_status(dict)` — normalized status from the JSON line: `state`, `progress`, `recovered`, `speed`, `elapsed`, `eta`, `devices`.
- `on_phase(label)` — coarse phases from the raw stream: `Preparing hashes…`, `Preparing kernels…`, `Initializing backend…`, `Running self-test…`, `Autotuning…`.
- `on_output` — remaining raw lines (errors/warnings); `on_cracked` / `on_done`.
Without `--status-json` support it falls back to regex parsing (`Progress` / `Recovered`).

**Clean status view (dialog, `src/gui/dialogs/hashcat.py`):** a shared `_StatusPanel` (Crack and Mask tabs) shows a progress bar, `Status`, `current/total (%)`, `Speed`, `Elapsed`/`ETA`, `Recovered`, device util/temp, and a small event log; the raw output is behind a **Details** toggle. During the pre-crack phase (kernel compile / autotune) the bar is **indeterminate/animated** and the phase is shown; once running it becomes determinate and it stays at the crack percentage when found. UI updates are **thread-safe**: engine callbacks enqueue into a `queue.Queue` drained on the main thread (`_drain`, every 50 ms); a 1 s ticker keeps `Elapsed`/`ETA` moving.

**Console output (`use hashcat`, `app.py`):** collapsed to `[*] Preparing hashcat…`, then `[*] Running hashcat    ETA ~HH:MM:SS` (once), a transient live line via `Console.live_status()` (`hashcat: Running 18% … ETA …`), then `[+] Cracked: …` / `[+] Hashcat done. …`. Raw phases are not shown in the console (they live in the dialog's Details). The full hash is printed in the `hashcat -m …` line.

**Hash selection (`app.py`):** `_hash_choices()` returns `(label, token)` pairs — label `#<id>  <truncated hash>…`, token the short `#<id>:<hash prefix>`. `Console` inserts the token so the prompt stays small, and `_find_hash(token)` resolves a full hash, `#id`, `#id:preview`, a bare id, or a unique hash prefix back to the stored row. Used by `use hashcat`, `view hash`, and `delete hash`.

**Console input height:** `Console._input_set()` schedules `_sync_input_height()` so the multi-line input grows when autocomplete inserts a value (not only when typing).

---

## WiFi Monitor (`src/tools/scanner/wifi_monitor.py`)

The WiFi subsystem is **platform-split**: Linux does full passive monitoring + injection; macOS can do **monitor RX (capture)** and scanning, but **no injection**.

**Platform detection** is centralized in `src/info.py` (populated by `init_dialog` at startup). `wifi_monitor` reads `_info.get("platform") or sys.platform` once at import into `_IS_MACOS` / `_IS_LINUX`. Do not duplicate `sys.platform` checks; use `is_macos()` / `is_linux()` and the capability helpers below.

**Capabilities (do NOT use a single flag):**
* `capture_supported()` — monitor-mode RX. Linux: always. macOS: only if `tcpdump` exists.
* `injection_supported()` — frame injection / deauth / CSA. Linux only.
* `monitor_supported()` is kept as an alias of `capture_supported()` (backward compat).
* Gate **capture** features (networks/probes/handshakes, and `lock_channel`) on `capture_supported()`; gate **attack** features (Deauther, CSA Spoof) on `injection_supported()`.

**Per-interface monitor (user-activated, no auto-start):**
* The monitor is **never started automatically** at app boot. Each interface is enabled/disabled explicitly by the user.
* `WifiMonitorService` keeps an `_enabled` set; the manager only spawns workers for enabled + free interfaces. API: `enable_iface(iface)`, `disable_iface(iface)`, `is_iface_enabled(iface)`, `enabled_ifaces()`, `active_ifaces()`.
* `is_running()` means "at least one interface is actively capturing".
* UI: one switch per interface — `<iface> Monitor mode` in **Services** (`key = "wifi:<iface>"`) and a `mon` toggle per interface in **WifiView**.
* `reserve_iface(iface)` / `release_iface(iface)` pause/resume one interface (used by the attacks while injecting) without changing its enabled state.

**Linux:**
* Interfaces via `nmcli` / `iw` (monitor-mode interfaces are included too); monitor mode via `iw`/`ip`/`nmcli`; passive capture of beacons, probes, and EAPOL handshakes with `scapy`.
* `WifiView` uses `get_networks()` (live monitor data). Falls back to the `nmcli` system scan when no interface is capturing.
* `deauth()` works whether or not the monitor service is running: if the interface is not in monitor mode it enters it for the burst and restores it afterwards (so it is not sniffing while injecting).
* Handshake files (`.pcap`, `.hc22000`) are written to `handshakes_dir()`.

**macOS:**
* Backend lives in `src/tools/scanner/wifi_macos.py`, imported lazily only on darwin. `scan()` uses CoreWLAN via `pyobjc-framework-CoreWLAN` (conditional dependency, installed only when `sys_platform == 'darwin'`) and returns the **same normalized dict shape** as Linux.
* **Monitor RX works** on the built-in Apple Silicon radio (no injection). It is done with `tcpdump -I -i <iface> -y IEEE802_11_RADIO -U -w -` (requires **root**/BPF and the interface to be **disassociated**, since monitor mode cannot run while associated). `wifi_macos.capture_loop()` parses the pcap stream and feeds `wifi_monitor._process()` — so networks, client probes and handshakes are collected exactly like on Linux.
* **Channel hopping works via CoreWLAN** (public API). `wifi_macos.set_channel(iface, chan)` uses `CWInterface.setWLANChannel:error:` (the API `airport` used) and always picks the **20 MHz** variant (beacons are 20 MHz wide; 40/80 MHz variants miss them). `wifi_macos.supported_channels(iface)` returns the radio's own channel list (2.4 + 5 GHz incl. DFS). **The radio latches onto the band it is on when `tcpdump` starts** (start it on 5 GHz and it only captures 5 GHz, even while changing channel), so `capture_loop()` runs **one `tcpdump` per band** — it binds each session by setting that band's first channel, then `_hop_band()` cycles the band's channels for `len(band) * HOP_DWELL + 5` s. `HOP_DWELL = 0.6` and the extra **+5 s slack** matter: `set_channel()` adds overhead, so a band pass takes longer than `len(band) * HOP_DWELL`, and without the slack the last channels of the band (e.g. 5 GHz ch161 / Pixel_4431) were cut off before the capture was stopped and their beacons were missed. `setWLANChannel` refuses to change the channel while the interface is associated, which is exactly the monitor-mode state. **Do not** try `dumpcap -k` (prints "Setting 802.11 channels is not supported on this platform") or `ifconfig <iface> channel` ("bad value") — they do not work on macOS 26; CoreWLAN is the only working path. Requires `pyobjc-framework-CoreWLAN` (already a darwin dependency) and root. The user can **lock a channel** (`wifi_monitor.lock_channel`): `capture_loop()` then opens a single `tcpdump` session on that channel and `_hop_band()` parks on it instead of cycling. Because the radio latches its band, a lock is honoured on both platforms, and the session is immediately recreated when the lock changes or is released (detected by `_pump()`/`_hop_band()` comparing `wifi_monitor._locked_channel`), so switching to a channel on the other band rebinds correctly. This lets a user park the radio on an AP's channel to catch a 4-way handshake — but macOS cannot inject, so the handshake only appears if a client naturally (re)connects.
* The old `airport` CLI was removed by Apple (only `airportd.sb` remains); `tcpdump -I` + CoreWLAN `setWLANChannel` replace it.
* Non-root: no capture → `WifiView` falls back to the CoreWLAN scan (scan-only). `WifiDetailView` shows "Probe capture requires root permissions in Mac OS."
* Note: CoreWLAN scanning needs **Location Services** granted to the terminal; running as **root** (sudo) loses that grant and returns empty SSIDs — run Elwand as the normal user for scanning, or as root for monitor capture.
* `iface` discovery falls back to parsing `networksetup -listallhardwareports` if CoreWLAN is unavailable.
* No PMF field via CoreWLAN.

### Wifi Operator (`src/gui/dialogs/wifi_operator.py`)

The dialog has two tabs (Deauther / CSA Spoof), each with an interface selector, a network list, a client list, and a **parameter frame**:

* **CSA Spoof** reads its fields from `csa_attack.DEFAULTS` (`target_chan`, `attack_window`, `observe_window`, `count`, `csa_interval`, `tx_rate`, `duration`) plus an "All networks with this ESSID" toggle.
* **Deauther** reads from `wifi_monitor.DEAUTH_DEFAULTS` (`count`, `reason`, `interval`, `rate`) — the same defaults `deauth()` has always used. `deauth(bssid, client=None, iface=None, count=64, reason=7, interval=0.005, rate=2)` passes them to `_send_deauth()` (radiotap Rate + inter-frame interval). Reason is a plain numeric `Entry`.

### Handshakes (capture → hash → extract)

* The monitor writes `<SSID>_<BSSID>.pcap` (frames) and appends a hashcat 22000 line to `<SSID>_<BSSID>.hc22000` when a 4-way handshake completes. It registers the **raw `WPA*02*…` line** (not the file path) in the `hashes` table (`type="WPA handshake"`, `hascat_mode="22000"`); the same BSSID seen again updates that row with the latest line.
* `credential_db.repair_handshake_hashes()` (called once at startup) rewrites legacy rows that stored the `.hc22000` path with the last line of that file.
* `wifi_monitor.extract_handshakes_from_pcap(path)` parses a `.pcap` and returns the handshakes it holds (`{bssid, client, ssid, keyver, messages, message_pair, line}`); the ESSID comes from the live networks, the sibling `.hc22000`, or the filename.
* The **Handshakes view** lists `.pcap` files. Clicking a name opens `ExtractHashDialog` with that pcap preselected; the **Extract hash** button opens it with the first pcap. The dialog derives the 22000 line, lets the user select a handshake, and saves it (`origin="manual extract"`).
* Console: `delete handshake <file|all>` removes the `.pcap` and its `.hc22000` sibling; its autocomplete lists every pcap plus `all`. In the Inventory, **Handshakes** sits right below **Hashes**.

**Rules for changes:**
* Never let macOS code run on Linux or vice versa — every platform branch must early-return.
* New scan fields must be added to both backends with identical keys.
* Keep `wifi_macos` free of tkinter and of module-level CoreWLAN imports (so Linux never touches it).

---

## Evidence Collection

Elwand includes mechanisms for recording and preserving evidence generated during assessments.

Evidence is stored under:

```
~/.local/share/elwand/evidence/
```

Purpose:

* Preserve artifacts generated during operations.
* Support later analysis by Large Language Models (LLMs).
* Maintain a reproducible assessment trail.

Guidelines:

* Store evidence in a structured and consistent manner.
* Prefer machine-readable formats when practical.
* Avoid modifying existing evidence unless explicitly required.
* Preserve timestamps and contextual metadata whenever possible.

---

### LLM Integration (`src/llm/`)

Elwand integrates with LLMs via an extensible provider system supporting any OpenAI-compatible API (OpenAI, Anthropic, DeepSeek, Ollama, OpenRouter, etc.).

**Architecture:**

* `config.py` — Persists provider configs to `~/.local/share/elwand/llm.json`. Each provider key doubles as its display name (no separate `name` field). Per-provider `base_url`, `api_key`, `models`, and optional `context_limit` (manual override; blank = auto). Active model is per-provider (`active_models` dict, not global — avoids cross-provider model confusion). System prompts stored in `prompts` dict (deep-merged from defaults on load). Built-in default providers: `opencode` (free tier at `https://opencode.ai/zen/v1`, empty `api_key` — the free models don't require a key, but a user with an opencode zen subscription can fill their own key) and `ollama` (local). New installs start with `opencode` active and `big-pickle` as the model.
* `models_catalog.py` — resolves the model's real context window the way opencode does: downloads the **models.dev** catalog (`https://models.dev/api.json`) with `urllib.request` (no new deps), caches it to `~/.local/share/elwand/databases/models_catalog.json` (TTL 24h), and exposes `lookup_context_limit(model_name)`. `refresh_async()` prefetches in a daemon thread (never blocks the GUI). The OpenAI `/models` endpoint does **not** return context limits — that's why the catalog is used.
* `client.py` — `LLMClient` wraps `openai.OpenAI`. `chat()` / `chat_stream()` / `chat_with_tools()`. Prepends purpose-specific system prompt unless messages already contain a `system` role. Timeout: 300s. `chat_with_tools()` is fully streaming (`stream=True` + `stream_options={"include_usage": True}`), checks `stop_event` per chunk, and returns the accumulated final `content` string (or `None`).
* `settings.py` — Settings dialog: **Models** tab (provider cards, click to edit/set active) + **Prompts** tab (editable system prompts per purpose).

**Opencode Headers Mimic (`client.py`):**

Elwand identifies itself as the official OpenCode client to the opencode zen API. This ensures compatibility and avoids spurious `FreeUsageLimitError` (429) from servers that validate the client identity.

When the active provider is `opencode`:

1. **API Key**: `api_key` defaults to `"public"` (the opencode free-tier credential) if left empty. Users with a subscription can override it in Settings.
2. **SDK Suppression**: The Python openai SDK injects `x-stainless-*` headers identifying it as an OpenAI Python SDK consumer. These are removed **per request** by passing them with `Omit()` in `extra_headers` (`_opencode_headers()`); `default_headers` only overrides `User-Agent`.
3. **Request Headers**: Every API call includes `extra_headers` with:
   - `x-opencode-project`: project id. Real opencode sends the sha1 of the git remote (or the root commit), or `global` when there is no repo. Elwand has no project concept, so a fixed plausible sha1 is used as the default (`_OPENCODE_PROJECT`); it is overridable per client via `LLMClient(project_id=...)`, persisted in `session.json`, and rotated with `debug rotate_opencode_headers`.
   - `x-opencode-session`: the **session** id (`ses_` prefix), **stable for the whole Elwand session**, persisted in `session.json` and rotated only on `reset`.
   - `x-opencode-request`: the **user-turn** id (`msg_` prefix), generated once per user prompt and reused by every tool-call round-trip within that turn.
   - `x-opencode-client`: Always `"cli"`.
4. **ID Format**: IDs follow OpenCode's `identifier.ts` format: prefix + 6 bytes hex (timestamp; `descending` = inverted, used for `ses_`; ascending for `msg_`) + 14 random alphanumeric chars (`[0-9A-Za-z]`). Generated by `_generate_opencode_id()`.
5. **User-Agent**: Set to `opencode/latest/1.2.3/cli`.
6. **Reset**: `reset` clears `_llm_session_id`, `_llm_project_id`, and `_llm_request_id`, so the next call gets a fresh session, project, and turn id. The stable session id is stored by `App._llm_session()` and persisted via `session.save(..., session_id=..., project_id=...)`. The `debug rotate_opencode_headers` command rotates the session and project ids on demand (the request id already rotates per turn).
7. **DICMA tools**: `dicma_find_related` also applies the same opencode headers when the active provider is `opencode`.

For all other providers (ollama, custom), the behavior is unchanged — no headers are injected, no API key is forced.

**Console integration:**

* **Consultor / Agent modes** are entered via the **Tab mode cycle** (Normal → Consultor → Agent). The old `consultor`/`agent` console commands were removed, and there is no one-shot `<mode> <prompt>` form anymore.
  * **Consultor** turns the prompt yellow (`Consultor>`); all input is sent to the LLM, which may call only read-only tools (`chat_with_tools(allowed_tools=CONSULTOR_TOOLS)`).
  * **Agent** turns the prompt blue (`Agent>`) with full tool access.
  * Both modes accept the same inline commands: `exit`, `stop`, `reset`, `compact`, `clear`, `menu`, and `debug`.
* `settings` — opens LLM configuration dialog.

Both modes display the model output in white, marked with a colored `▣` (blue for agent, orange for consultor); the echoed prompt is `User prompt > ` colored by mode.

**Markdown rendering:** the agent/consultor output is rendered as markdown, following opencode's dark-theme colors: headers (`#`–`######`) and `**bold**` in bold white; `*italic*`/`_italic_` in yellow; inline `` `code` `` in green; blockquotes (`>`) in yellow; links `[text](url)` show the text in cyan; list markers `-`/`*`/`+` in blue and `1.` in cyan; horizontal rules (`---`) in grey; fenced code blocks (```) with a dark background; tables are aligned with `│`/`─` box-drawing. Only agent/consultor output is rendered; all other console messages (info, warnings, `[tool]`, `User prompt >`) stay plain. The markdown logic lives in `MarkdownRenderer` (`src/gui/markdown.py`), a standalone class that renders into any `tk.Text` widget — the console delegates to it (`Console._insert_markdown` → `MarkdownRenderer.insert_line`), and the report detail view uses it directly (`render()`). State (`_in_code_block`, `_table_buffer`) is tracked per line and reset at the start of each exchange (`reset_markdown_state()`), flushed at the end (`flush_markdown()`), and preserved across restarts by re-rendering `"__md__"` segments in `restore_segments()`.

**Markdown toggle:** the setting `console_markdown` (default `true`, persisted in `settings.json`) controls whether `"__md__"` segments render as markdown or plain white text. It is toggled from **Settings → Console → Markdown interpretation** (ON green / OFF grey, same Label-switch pattern as the Safety tab). The console checks the setting on every write (`Console._markdown_enabled()`), so new output switches instantly without restart; toggling also re-renders existing history via `restore_segments(get_segments())`. Segments are always stored as `"__md__"` regardless of the toggle, so sessions remain re-renderable when the setting changes.

**Rules:**

* All LLM calls run in daemon threads. Output dispatched to main thread via `app._safe_after(callback, *args)`.
* The `openai` library is used for all providers by setting a custom `base_url`.
* System prompts are configurable per purpose (`system`, `investigate_interests`).

**Provider Edit Dialog:**

The provider editor (`_open_provider_dialog` in `src/gui/dialogs/settings.py`) uses these design patterns:

* **Single "Name" field** — the provider key doubles as its display name. Changing the name renames the provider (updates `active_provider` and `active_models` references automatically).
* **Models** — an editable `ttk.Combobox`. Auto-detection triggers on `<FocusOut>` of the Base URL or API Key fields, running the OpenAI `models.list()` API call in a daemon thread. A "Detect" button provides manual fallback. Callbacks catch `tk.TclError` to avoid crashes if the dialog is closed before detection completes.
* **Provider selector** — uses `tk.OptionMenu` (not `ttk.Combobox` with `state="readonly"`) because macOS Aqua ignores ttk dark theme styling on readonly comboboxes, displaying a bright white background.

### Debug Commands

`debug` is a console command available in **all three prompts** (`Elwand>`, `Consultor>`, `Agent>`). In agent/consultor modes it is intercepted by `App._maybe_debug_command()` only for known subcommands, so a prompt that merely starts with the word "debug" falls through to the model.

* `debug ctx_screenshot` — writes a JSON snapshot of the current LLM context to `runtime_logs_dir()`.
* `debug rotate_opencode_headers` — generates a new opencode session id and a new project id (40-hex sha1), resets the request id, and persists them via `_save_session()`. See "Opencode Headers Mimic".

### Agent Tool-Calling (`src/llm/client.py` → `chat_with_tools()`)

The agent mode gives the LLM the ability to call **60 tools** that read and modify application state and trigger network operations. It is activated by cycling into agent mode with **Tab** (see "Console integration").

**Tool-calling loop** (fully streaming):

`chat_with_tools()` issues a single streaming request (`stream=True` + `stream_options={"include_usage": True}`, with a fallback when the provider rejects `include_usage`), iterating chunks and:
- checking `stop_event` **per chunk** (aborts immediately and closes the stream — opencode-style interruption),
- emitting text deltas via `on_text` as they arrive,
- accumulating `tool_calls` by `index` from the streaming delta format,
- reading `usage.prompt_tokens` from the final chunk into `_total_api_tokens`.

When the stream ends with `finish_reason == "tool_calls"`, it appends the assistant message (with `tool_calls`), executes each tool (respecting `allowed_tools`), appends the tool results, calls `on_flush()`, and loops. Otherwise it calls `on_flush()` and returns the accumulated final `content` string (or `None` if stopped/no response).

**Method signature:**

```python
def chat_with_tools(self, messages, on_tool=None, model=None, tool_context=None, on_text=None, stop_event=None, on_warning=None, allowed_tools=None, on_flush=None):
```

- `on_tool(name, args, result)` — callback invoked after each tool execution (used for console logging).
- `on_text(text)` — callback invoked with each text delta (used for live streaming display).
- `on_flush()` — callback invoked at the end of each stream (flushes any buffered line; resets the `▣` first-line marker).
- `stop_event` — `threading.Event` to cancel the loop cleanly (checked per chunk).
- `on_warning(msg)` — callback invoked when the model outputs invalid XML tool call syntax (corrected via system message injection).
- `allowed_tools` — a `set` of tool names allowed to execute; `None` = all (agent). In consultor mode this is `CONSULTOR_TOOLS`; non-allowed tools return a "not available in consultor mode" string (the tool schemas are still sent so context stays equivalent).
- `tool_context` — passed through to tool handlers. In agent/consultor mode this is the `App` instance.

### Tool Definitions (`src/llm/tools.py`)

Tools are defined as a list of OpenAI function-calling schemas in the `TOOLS` variable. Each entry follows the `{"type": "function", "function": {...}}` format with `name`, `description`, and `parameters` (JSON Schema).

**60 tools** in eight categories:

**Data tools** (24) — query and manipulate inventory, no `tool_context` needed:

**Query tools:**

| Tool | Description |
|---|---|
| `check_status` | Get current Elwand state summary: all machine IPs with hostname, domain, device type, and port counts; all domain names; plus counts of users, credentials, passwords, hashes, evidence sessions, shell sessions |
| `check_machine` | Get all known info about a machine (IP, hostname, IPv6, MAC, model, device type, OS, domain, timestamps, ports, banners, web services, users) |
| `check_domain` | Get all known info about a domain (subdomains, directories, web services, machines) |
| `check_inventory` | Get full inventory: users, credentials, passwords, hashes, people, tickets, dictionaries, rules |
| `check_hash` | List all hashes (truncated). With `hash_id`: return full hash value and details |
| `check_shells` | List all shell sessions with ID, type, status, active flag, IP, ports, OS, timestamps |
| `check_evidences` | List evidence sessions with metadata (no file contents). Without `name`: sessions list, paginated via offset/limit (default 20). With `name`: that session's files + request dirs, paginated via offset/limit (default 60). |
| `read_evidence` | Read a specific file from an evidence session (`session.json`, `request.json`, `response.json`, `body.html`) with offset/limit pagination or regex search (`context_before`/`context_after`). Path-traversal protected via `_resolve_evidence_path`. Bounded like `read_cache`. |
| `check_fuzz_results` | Retrieve fuzz results for a machine: saved directories and subdomains discovered via fuzzing. Uses offset/limit pagination (default: 60 entries per section). |

**Mutation tools:**

| Tool | Description |
|---|---|
| `add_user` | Add a user to inventory (`username`, `utype`, `machine`, `domain`, `origin`) |
| `delete_user` | Delete a user by username |
| `add_machine` | Add a machine (IP) to network inventory |
| `add_domain` | Add a domain to inventory |
| `add_subdomain` | Add a subdomain to an existing domain (`domain`, `subdomain`) |
| `add_credential` | Add credential (username + password or 32-char NT hash). Auto-detects NT hash vs plaintext; computes NTLM hash for plaintext passwords |
| `add_hash` | Add hash entry to inventory (`hash_type`, `hash_value`, `hascat_mode` optional) |
| `delete_hash` | Delete hash by ID |
| `add_password` | Add password to inventory |
| `delete_credential` | Delete credential by username |
| `delete_machine` | Delete machine by IP or ID |
| `delete_domain` | Delete domain by name |
| `delete_password` | Delete password from inventory |
| `add_person` | Add a person to the people inventory (`first_name`, `last_name`, `company`, `domain`, `username`, `role`, `linkedin_url`, `source`, `interests`) |
| `delete_person` | Delete a person by ID |

**Network tools** (10) — trigger operations, require `tool_context` (App instance):

| Tool | Description |
|---|---|
| `list_interfaces` | List available network interfaces (skips `lo0`) |
| `scan_interface` | Scan local network on an interface (`iface`). Long-running async — results arrive via event bus |
| `scan_ip` | Scan a specific IP for OS/device identification. Synchronous — returns result directly |
| `stop_scan` | Stop the active network scan |
| `port_scan` | Scan TCP or UDP ports on an IP (method: "tcp" or "udp"). Returns common ports immediately; full 65535 scan continues in background (results via `check_machine`) |
| `ping` | Ping an IP address. Synchronous — returns time + TTL directly |
| `nslookup` | DNS lookup on a hostname. Synchronous — returns resolved addresses directly |
| `port_inspector` | Inspect a TCP port by sending service-specific probes. Synchronous — returns identified service banners directly |
| `bannergrab` | Open a raw TCP connection to an IP:port and wait up to 2s for a banner/response. Synchronous — returns received data directly |
| `nmap` | Run custom nmap scan with arbitrary arguments against a target. Returns raw output and auto-saves open ports to machine inventory. Disabled by default; respects the "Agent can run nmap" safety setting (Settings > Safety). |

**Web tools** (3) — fetch URLs, search the web, and browse GitHub repos, no `tool_context` needed:

| Tool | Description |
|---|---|
| `webfetch` | Fetch a URL as markdown or raw (`url`, optional `format`, `method`, `body`, `content_type`, `headers`, `antibot`). Uses `curl_cffi` with Chrome impersonation to defeat TLS fingerprinting. Default GET; use POST only when submitting data with explicit content_type. Use headers for custom HTTP headers (Cookie, Authorization, etc.). Ignores self-signed TLS certificates. Markdown auto-strips navigation, footers, and cookie banners. Raw format returns HTTP status, all headers, and first 60 lines of untouched body (full body saved to cache). Auto-saves URL path to `directories` table if the host matches a known machine or domain. With `antibot=true`, it detects anti-bot challenges (Akamai, Cloudflare) and solves them in a real browser via CDP, falling back to a full browser render when cookie replay is rejected (cookie bound to TLS fingerprint). |
| `websearch` | Search the web via Exa MCP (primary) or DuckDuckGo Lite (fallback) and return results with title, URL, and snippet (`query`, optional `num_results`) |
| `list_repo` | List files and directories in a public GitHub repository using the GitHub REST API (`owner`, `repo`, optional `path`). Returns file names, sizes, and raw download URLs. No authentication needed. |

**DICMA tools** (4) — generate wordlists and rules, no `tool_context` needed:

| Tool | Description |
|---|---|
| `dicma_generate_users` | Generate username permutations from a person's full name (`full_name`, optional `output_name`) |
| `dicma_find_related` | Find semantically related words via LLM expansion (`words`, optional `n1`/`n2`/`n3`, `output_name`). Uses active LLM config from Elwand settings |
| `dicma_generate_passwords` | Generate password permutations from seed words (`words`, optional `mode`, `output_name`) |
| `dicma_generate_rules` | Generate hashcat rules from built-in patterns or a custom dictionary (`dictionary` optional, `mode`, `output_name`) |

**Attack tools** (3) — trigger attacks, require `tool_context`:

| Tool | Description |
|---|---|
| `hashcat_crack` | Crack a hash with hashcat (`hash_value` must be in inventory, `wordlist`) |
| `bruteforce_start` | Start a brute force attack (`protocol`, `target`, optional `port`) |
| `fuzz_start` | Start directory/vhost/DNS fuzzing (`method`, `target`, `wordlist`, optional `port`, `scheme`, `skip_codes`, `hide_size`, `workers`). Performs wildcard detection before scanning — aborts if catch-all found. Runs asynchronously — results are saved to the `directories` and `subdomains` tables. Use `check_fuzz_results` to retrieve them. |

**Infrastructure tools** (10) — manage services, files, evidence, and shell sessions:

| Tool | Description |
|---|---|
| `listener` | Start or stop a background service (action: "start" or "stop", service: "shells-listener" or "mdns-listener"). Requires `tool_context` |
| `list_files` | List available files by type: dictionary, rule, poc, or cache |
| `delete_file` | Delete a dictionary, rule, POC, or cache file (`file_type`, `filename`) |
| `read_cache` | Read a cached tool output file from `cache/` with optional offset/limit pagination, or regex search with context lines (`regex`, `context_before`, `context_after`) |
| `delete_evidence` | Delete an evidence session by name, or `"all"` |
| `delete_shell` | Delete a shell session by ID, or `"all"` |
| `shell_exec` | Send a command to a shell session and wait for output |
| `shell_wait` | Wait for more output from a running shell command |
| `shell_interrupt` | Interrupt a running shell command (sends Ctrl+C) |
| `connect` | Connect to a remote machine via SSH, SFTP, FTP, or WinRM using stored credentials (protocol arg) |

**POC tools** (4) — create, read, edit, and execute proof-of-concept scripts in the `pocs/` directory, no `tool_context` needed:

| Tool | Description |
|---|---|
| `poc_write` | Create or overwrite a `.py` file in the `pocs/` directory (`filename`, `content`). Rejects filenames without `.py` extension. Path-traversal protected via `_resolve_poc_path()`. |
| `poc_read` | Read a POC file from the `pocs/` directory (`filename`, optional `offset`/`limit`). Returns content with line count header. Maximum 50,000 chars per read. |
| `poc_edit` | Edit a POC file by exact string replacement (`filename`, `old_string`, `new_string`, optional `replace_all`, optional `new_filename` to rename the file). If `old_string` is not found, returns an error with instructions. If multiple matches found without `replace_all=true`, returns the count and asks for more context. Path-traversal protected. |
| `poc_exec` | Execute a POC Python script (`filename`) and return its output. Output truncated to last 5000 chars if too large. Respects the "Agent can execute POCs" safety setting. |

**Report tools** (2) — create and read markdown reports in the `reports/` directory, no `tool_context` needed:

| Tool | Description |
|---|---|
| `report_write` | Create or overwrite a `.md` report in the `reports/` directory (`filename`, `content`). Rejects filenames without `.md` extension. Path-traversal protected via `_resolve_report_path()`. Rules in the system prompt: only generate a report when requested by the user; markdown usage recommended. |
| `report_read` | Read a report with `offset`/`limit` (default 150 lines) or `regex` search (`context_before`/`context_after`, same semantics as `read_cache`). Output capped at 5,000 chars. Read-only, so included in `CONSULTOR_TOOLS`. |

**POC system overview:**

POCs (Proof of Concept) are Python scripts generated by the LLM agent to demonstrate security vulnerabilities or exploit techniques. They are stored in the `pocs/` directory under `~/.local/share/elwand/pocs/`.

**Directory and path resolution:**
- `src/elwand_paths.py` — `pocs_dir()` returns `Path` to `~/.local/share/elwand/pocs/`, created lazily with `os.makedirs(exist_ok=True)`.
- Unlike `lst_dir()` and `rules_dir()`, `pocs_dir()` does not seed initial files from the package — POCs are created on-demand by the agent.

**GUI integration:**
- `PocsView` (`src/gui/views/pocs.py`) — lists POC files with icon (`poc.png`), size, and delete button. Same poll-based pattern as `DictionarysView` and `RulesView`.
- `PocDialog` (`src/gui/views/file_detail.py`) — modal dialog (`tk.Toplevel`) opened via `open_file_search(..., file_type="poc")`. Features:
  - **Line numbers** — left panel synced with editor scroll via a single `Scrollbar`. `yscrollcommand` uses `yview_moveto(float)` for cross-platform compatibility.
  - **Editable code** — `Text` widget with undo/redo (max 100 levels), full content shown.
  - **Search bar** — regex toggle, Prev/Next with match counter, Go to line. Supports `Ctrl+F` shortcut.
  - **Draggable divider** — `tk.PanedWindow(orient=tk.VERTICAL)` with `stretch="always"` between code and output panels. Initial output height is 120px.
  - **Execute button** — runs `python3 <file>` in a background thread. Output streams stdout (white) and stderr (red) in real-time. Stop button sends `SIGTERM`.
  - **Auto-save** — saves on Execute if dirty, and on Close if dirty. Dirty indicator (`•`) in info bar.
  - **Keyboard shortcuts** — `Ctrl+F` (search), `Ctrl+S` (save), `F5` (execute), `Esc` (focus editor).
  - **Cross-platform** — `wait_visibility()` before `grab_set()`. Synced scroll uses `_on_editor_scroll` / `_on_scrollbar_move` separation to avoid recursion. `yview_moveto` used for line numbers because `yview(float)` without `moveto` fails on some Tk versions.

**Inventory integration:**
- Added as a category in `InventoryView` (`src/gui/views/inventory.py`): `{"name": "Pocs", "action": "pocs", "icon": "poc.png", "enabled": True}`
- Clicking "Pocs" navigates to `PocsView`, which lists files in the `pocs/` directory.

**Console commands:**
- `view poc` — shows the `PocsView` listing
- `view poc <filename>` — opens the POC in `PocDialog`
- `delete poc <filename|all>` — deletes POC files
- `delete all` — wipes all operational data (machines, domains, users/credentials/passwords/hashes/tickets, people, shells, evidence, POCs, cache, mDNS cache). Preserves dictionaries (`lst/`), rules (`rules/`), and reports (`reports/`), and leaves the LLM session (`session.json`) untouched.

**Context injection:**
- `check_status` tool provides a machine/domain overview and inventory counts.
- `check_inventory` tool provides full user, credential, password, hash, people, dictionary, and POC listings. Lists POC files alongside other inventory items.

**System prompt:**
- POC generation rules (Python 3.11+, standard library, global variables, no dedicated listener, filename comment) are part of the main `system` prompt in `src/llm/config.py`. The agent receives them automatically.

**Path traversal protection:**
- `_resolve_poc_path(filename)` in `tools.py` validates that the resolved path is within the `pocs/` directory, rejecting `../` attacks.

### Reports System

Reports are markdown documents (`.md`) that record findings. They are stored in the `reports/` directory under `~/.local/share/elwand/reports/` (created lazily, no package seeding). They can be created/edited manually through the GUI, or generated by the agent via the `report_write`/`report_read` tools.

**Directory and path resolution:**
- `src/elwand_paths.py` — `reports_dir()` returns `Path` to `~/.local/share/elwand/reports/`, created lazily.

**GUI integration:**
- `ReportsView` (`src/gui/views/reports.py`) — lists report files with icon (`report.png`), size, and delete button (same poll-based pattern as `PocsView`). Has a **Back** button (→ `inventory`) and a **New** button that opens `ReportDialog` to create a report manually.
- `ReportView` (`src/gui/views/report_detail.py`) — read-only detail view that renders the report's markdown via `MarkdownRenderer` (`src/gui/markdown.py`). Has **Edit** (opens `ReportDialog` in edit mode) and **Back** (→ `reports`) buttons. Re-reads and re-renders the file on `on_activate()`.
- `ReportDialog` (`src/gui/views/report_dialog.py`) — modal dialog (`tk.Toplevel`) with a filename entry (`.md` suffix forced) and a markdown `Text` editor. Handles both "new" (empty) and "edit" (preloaded) modes. Follows the `wait_visibility()` before `grab_set()` pattern.

**Inventory integration:**
- Added as a category in `InventoryView` (`src/gui/views/inventory.py`): `{"name": "Reports", "action": "reports", "icon": "report.png", "enabled": True}`.

**Console commands:**
- `view report` — shows the `ReportsView` listing
- `view report <filename>` — opens the report in `ReportView`
- `delete report <filename|all>` — deletes report files
- `delete all` preserves the `reports/` directory (reports are user findings, not transient operational data).

**Agent tools:**
- `report_write` — create/overwrite a `.md` report in `reports/` (`filename`, `content`). Path-traversal protected via `_resolve_report_path()`. Rules in the system prompt: only generate a report when requested by the user; markdown usage recommended.
- `report_read` — read a report with `offset`/`limit` (default 150 lines) or `regex` search (`context_before`/`context_after`, same semantics as `read_cache`). Output capped at 5,000 chars. It is read-only, so it is included in `CONSULTOR_TOOLS` (like `poc_read`).
- Reports are listed in `check_inventory` and `check_status` alongside POCs.

**Implementation details for POC tools** (`src/llm/tools.py`):

- `fetch_url()` uses `curl_cffi` (Chrome impersonation) with a Chrome 143 User-Agent.
- On Cloudflare 403 challenges (`cf-mitigated: challenge` header), retries with `"opencode/Elwand"` User-Agent.
- TLS certificate verification is disabled (`verify=False`) to support self-signed certificates on internal targets. `urllib3.disable_warnings()` suppresses insecure request warnings (for the fallback DuckDuckGo search).
- HTML content is converted to markdown via `html2text` or to plain text via `html.parser` (stdlib).
- Response size is capped at 5MB; timeout defaults to 30 seconds.
- `web_search()` uses Exa MCP (`mcp.exa.ai`) as primary, with DuckDuckGo Lite as fallback on failure.
- Exa MCP is called via JSON-RPC 2.0 over HTTP (see `src/llm/mcp.py`), with Server-Sent Events (SSE) response parsing. No API key required — Exa's MCP endpoint has an unauthenticated free tier (same approach as opencode).
- Both handlers are synchronous (blocking HTTP calls) — they run inside the agent's daemon thread.
- `webfetch` automatically saves the URL path to the `directories` table when the host matches a known machine or domain in the inventory.

### Anti-Bot Browser Solver (`src/llm/browser_solver.py`)

`webfetch` supports an optional `antibot` parameter that bypasses JavaScript-based anti-bot challenges (Akamai, Cloudflare) by executing them in a real Chromium-family browser and harvesting the solved cookies.

**Architecture:**

- `detect_protection(status_code, headers, cookies)` — classifies the active challenge as `"akamai"`, `"cloudflare"`, `"perimeterx"`, `"datadome"`, or `None`. Detection is challenge-agnostic and only fires on *solvable* signals: Akamai by an unsolved `_abck` cookie (flag `~-1~`; the `AkamaiGHost` server header alone is a hard "Access Denied" IP/UA/geo block and is intentionally NOT detected); Cloudflare by an explicit challenge signal (`cf-mitigated: challenge` header, or `403`/`503` + `cloudflare` server without `cf_clearance`) — a `200` with `__cf_bm` is not flagged; PerimeterX by `_px*` cookies / `x-px-*` headers; DataDome by `x-datadome` header / `datadome*` cookies.
- `SOLVED_PREDICATES` — a registry mapping each challenge type to a predicate that recognises the solved state (Akamai: `_abck` flag `~0~`; Cloudflare: `cf_clearance` present). Providers without a predicate (perimeterx, datadome) are detected and rendered via `browser_fetch` for an accurate note, but `solve()` returns `None` immediately for them. Adding a new provider means adding a detection rule + a predicate.
- `solve(url, challenge_type)` — launches a browser (headless `--headless=new`, falling back to headed on failure), navigates, polls `Network.getAllCookies` via CDP until the solved predicate holds, then harvests and returns the cookies.
- `CookieBank` — per-host, thread-safe cache of solved cookies with a ~40 min TTL, so repeated fetches don't re-launch the browser.
- `browser_fetch(url)` — full-browser fetch fallback: renders the page (waits for `document.readyState === "complete"` and network idle) and returns the rendered HTML. Used when replaying solved cookies still fails (Akamai/Cloudflare configs that bind the cookie to the TLS fingerprint).

**Flow in `webfetch` (`_curl_resolve` in `src/llm/web.py`):**

1. Perform the `curl_cffi` request (Chrome impersonation).
2. If `antibot=true` and `detect_protection` reports a challenge: reuse `CookieBank` cookies or call `solve()`.
3. Retry with the solved cookies injected into the `curl_cffi` session.
4. If still challenged, fall back to `browser_fetch()` (full browser render).

**Cross-platform browser discovery** is in `src/tools/webrecorder/browser_finder.py` (GUI-free: Chrome, Chromium, Brave, Edge via `shutil.which` + known macOS/Windows paths, so it also works on Linux). `src/tools/webrecorder/browsers.py` re-exports `find_browsers` for backward compatibility.

**Safety:** a browser is launched only when `webfetch` is called with `antibot=true`. The solver runs in the agent's daemon thread and never touches tkinter; CDP runs on a dedicated port (9333) with a dedicated profile (`~/.local/share/elwand/antibot_profile/`), separate from the webrecorder's 9222/`chrome_profile`.

**Known limitations:**

- IP-reputation / geo blocks (Akamai "Access Denied" without a challenge, Cloudflare "Attention Required") are **not** solvable — they require a different IP/proxy.
- Interactive challenges (Cloudflare Turnstile checkbox, CAPTCHAs) may require human interaction.
- Client-side-rendered SPAs may return an empty `<body>` shell; their content lives in XHR calls to protected API endpoints, which must be fetched separately.

### Context Management & Compaction

Elwand automatically manages LLM context to prevent overflow during long agent or consultor sessions.

**Context limit resolution** (`_get_model_context_limit()` in `src/gui/app.py`) — priority order:
1. Manual override: the active provider's `context_limit` field in `llm.json`.
2. `models_catalog.lookup_context_limit(model_name)` — the models.dev catalog (cached, auto-prefetched at startup).
3. Hardcoded `_MODEL_CONTEXT_LIMITS` table (exact match first, then substring), fallback `_DEFAULT_CONTEXT_LIMIT`.

**Automatic Compaction:**
- Triggers when the actual `prompt_tokens` (`_total_api_tokens`, reported by the API) reach `context_limit - 20,000` (configurable buffer via `DEFAULT_BUFFER` in `src/llm/compaction.py`). Falls back to a chars/4 estimate before the first API response.
- Calls the LLM to generate an incremental summary of old messages using a structured template
- Replaces summarized messages with a single compaction message (`_is_compaction: true`) that includes the summary text and recent verbatim messages
- Recent messages (~8K tokens worth, configurable via `DEFAULT_KEEP_TOKENS`) are preserved intact
- Subsequent compactions update the existing summary (anchored incremental summarization)
- Limits summary output to 4,096 tokens (`SUMMARY_OUTPUT_TOKENS`)
- Manual compaction available via `compact` command in Agent and Consultor modes (forces compaction regardless of overflow)

**Compaction Summary Template** (sections preserved across all compactions):
```
## Goal
## Constraints & Preferences
## Targets Discovered
## Credentials & Access
## Progress (Done, In Progress, Blocked)
## Key Findings
## Previously Fetched URLs
## Search Queries Made
## Cache Files Available
## Next Steps
```

The summarizer receives the current cache file listing (with associated URLs where available) to ensure the model knows what resources are available after compaction.

**Tool Output Bounding (`_bound_tool_output`):**
- All tool results pass through `_bound_tool_output()` in `src/llm/tools.py` before entering context
- Checks two thresholds: byte limit and line limit
- Per-tool byte limits in `TOOL_BYTE_LIMITS`; per-tool line limits in `TOOL_LINE_LIMITS`
- If output exceeds limits, full content is saved to `~/.local/share/elwand/cache/` and a truncated preview is returned
- The truncation marker includes the exact `read_cache("filename")` command to expand
- Preview format: first half of lines (head) + truncation marker + last half of lines (tail)

**Current Tool Limits:**

| Tool | Byte Limit | Line Limit | Rationale |
|------|:---:|:---:|---|
| poc_exec | 1,000 | default (2,000) | POC output is often repetitive; full file available in `pocs/` |
| port_inspector | 2,000 | default | Service probes return verbose protocol banners |
| websearch | 8,000 | default | ~20 results at ~300 bytes each; larger searches cache automatically |
| check_machine | 3,000 | default | Machine info with banners; full data via `check_machine` again |
| webfetch | 3,000 | 60 | Pages after HTML cleaning are compact; 30 head + 29 tail lines |
| Other tools | 50,000 | 2,000 | Default; most tool outputs fit comfortably |

**Tool Output Truncation in Compaction:**
- During compaction serialization, tool outputs are truncated to 2,000 chars (`TOOL_OUTPUT_MAX_CHARS`) to keep the summary prompt manageable
- This is compression for summarization only — the original tool results in current messages are preserved

**Cache System:**
- Directory: `~/.local/share/elwand/cache/` (created lazily)
- Files named `tool_{timestamp}_{tool_name}.txt`
- Cleaned on `reset` command or `delete cache`
- Tools: `list_files(cache)` to list, `read_cache(filename, offset=1, limit=200)` to read, or `read_cache(filename, regex="pattern", context_before=2, context_after=10)` to search within cached files. Use `delete cache` or `delete_file(cache, filename)` to remove.

**Webfetch HTML Cleaning:**
- Before HTML-to-markdown conversion, non-content elements are stripped via `_strip_html_non_content()` in `src/llm/web.py`
- Removed: `<nav>`, `<footer>`, `<aside>`, and elements with cookie-consent classes (`cookie`, `consent`, `gdpr`, `banner`, `popup`, `sidebar`)
- Preserved: `<header>` (may contain business/title info), `<main>`, `<article>`, `<section>`, and all text content
- If the server responds with a `Set-Cookie` header, the cookie is shown to the model at the top of the output in markdown mode (already visible in raw mode headers)
- The cleaned markdown focuses on page content without navigation noise, menus, or cookie banners
- If the full original page is needed, the uncached raw response is not available (design tradeoff for cleaner context)

**Websearch Exa Response Cleaning:**
- Exa MCP returns raw highlight text that includes verbose metadata and formatting artifacts
- `_parse_exa_results()` in `src/llm/web.py` extracts only title, URL, and compact snippets
- Strips `Published: N/A`, `Author: N/A`, `>` prefix, and `...` separators from highlights
- Snippet duplicates of the page title are removed from snippet text
- Snippets capped at 150 chars; `--` and `#` artifacts cleaned

**Context Repair:**
- When the API returns a 400 error about `tool_calls`/`tool_call_id` mismatch, `_repair_messages()` automatically cleans orphaned tool messages
- Walks backwards through messages to find the last structurally valid conversation boundary
- Logs the repair operation for debugging via `ctx_debug.log`

**Registration pattern** — decorator-based with a `_HANDLERS` dict:

```python
_HANDLERS = {}

def register(name):
    def decorator(fn):
        _HANDLERS[name] = fn
        return fn
    return decorator

def execute(name, args_dict, tool_context=None):
    handler = _HANDLERS.get(name)
    if not handler:
        return f"Unknown tool: {name}"
    try:
        return handler(args_dict, tool_context)
    except Exception as e:
        return f"Tool error: {e}"

@register("add_user")
def _add_user(args, ctx=None):
    from src.machines.credential_db import save_user
    save_user(..., origin="agent")
    return f"User '{args.get('username')}' added."
```

**Rules for adding new tools:**

1. Add the OpenAI function schema to the `TOOLS` list with `name`, `description`, and `parameters` (including `required` fields).
2. Write a handler using `@register("tool_name")` decorator. Signature: `def _handler(args, ctx=None):`.
3. Handlers must **always return a string** — this becomes the tool result sent back to the LLM.
4. Data tools use `origin="agent"` to mark agent-created records.
5. Network tools check `if not ctx: return "Cannot X: no tool context available."` — this guards against usage outside agent mode.
6. Network tools call existing App methods (`ctx._scan_interface(iface)`, `ctx._cmd_tcpscan([ip])`, etc.) — do not duplicate scan logic in tool handlers.
7. Tools that are inherently slow (full port scan, network scanning, fuzzing) should run asynchronously and store results in the database for later retrieval via query tools. Tools that complete quickly (<5s) may run synchronously and return results directly to the LLM (e.g., `ping`, `nslookup`, `port_inspector`, `scan_ip`). Mixed-mode tools (e.g., `port_scan`) return common-port results immediately and continue full scan in background.

### Agent Mode in `app.py`

The agent mode is a **console mode handler**, similar to `consultor`. The `App` class manages the full lifecycle:

**State variables** (initialized in `App.__init__`):

```python
self._agent_mode = False
self._consultor_mode = False
self._closing = False         # set in _on_close; guards worker-thread work during shutdown
self._llm_running = False     # guards against concurrent agent/consultor exchanges
self._agent_stop_event = None
self._llm_messages = []        # shared conversation history (agent + consultor)
self._llm_request_id = None    # opencode per-turn request id (msg_)
self._llm_session_id = None    # opencode session id (ses_, stable + persisted)
self._llm_project_id = None    # opencode project id (overrides the fixed default)
self._context_injected = False # one-shot: injected on first prompt only
self._total_api_tokens = 0     # last known prompt_tokens reported by the API
```

**Entry:**

There is no `agent`/`consultor` console command. Modes are entered through the **Tab mode cycle**: `Console.set_mode_cycle_callback(self._cycle_mode)` → `_cycle_mode()` → `_enter_agent_mode()` / `_enter_consultor_mode()` (the prompt turns blue/yellow).

**Lifecycle:**

```python
# Interactive handler — all console input routed here while in agent mode
def _agent_handler(self, text):
    if text.strip().lower() == "exit":
        self._on_close()             # closes the app (not just leaving mode)
        return
    if text.strip().lower() == "stop":
        self._agent_stop_event.set()
        return
    # reset / compact / clear / menu / debug are handled here too
    self._agent_ask(text)

# Core request — runs in daemon thread, dispatches to main via _safe_after()
def _agent_ask(self, prompt):
    if self._llm_running:            # reject concurrent exchanges (also stops typos)
        self.console.warning("Still processing...")
        return
    self._llm_running = True
    self._agent_stop_event = threading.Event()
    self._inject_context()           # injects context on first call only
    self._llm_messages.append({"role": "user", "content": prompt})
    self._save_session()
    def _run():
        client = LLMClient(purpose="agent")   # uses "agent" system prompt
        def _on_tool(name, args, result):
            self._safe_after(lambda: ...)
        _emit, _flush = self._make_stream_emitter("#5ba3ec", self.console.agent, clean_fn=_clean)
        content = client.chat_with_tools(
            self._llm_messages, on_tool=_on_tool, tool_context=self,
            on_text=_emit, on_flush=_flush,
            on_warning=lambda msg: self._safe_after(...),
            stop_event=stop)
        _flush()
        if stop.is_set(): ...        # "Agent stopped."
        if content is None: ...      # "(no response)"
        self._llm_messages.append({"role": "assistant", "content": _clean(content)})
        self._llm_running = False    # reset in finally
    threading.Thread(target=_run, daemon=True).start()
```

### Context Injection (`_inject_context`, `_build_model_context`)

On the **first** agent or consultor call of a session, a lightweight state summary is injected at position 0 of `_llm_messages`:

```
Elwand state: Machines: #1 10.0.0.1, #2 10.0.0.2. Domains: acme.local.
Use check_status for details, check_inventory for inventory.
```

This gives the LLM a snapshot of available targets. After the first injection, `_context_injected` is set to `True` and `_inject_context()` returns immediately on all subsequent calls — zero overhead.

**`_build_model_context()`** now returns only machine IPs/IDs and domain names in a single line (~50-200 tokens). The heavy per-machine SQLite queries (ports, banners, web services) and inventory details (users, credentials, hashes, evidence, shells, dictionaries, rules, POCs) are no longer injected — the LLM uses tools (`check_status`, `check_inventory`, `check_machine`, `check_domain`) to query them on demand.

The `reset` command clears `_llm_messages`, resets `_context_injected = False` and `_total_api_tokens = 0`, rotates the opencode ids (`_llm_session_id`/`_llm_project_id`/`_llm_request_id`), clears the cache, and deletes the persisted session (`_clear_session()`), so the next prompt re-injects the current state snapshot.

**Comparison with previous design:**

| Aspect | Old design | New design |
|---|---|---|
| Injection timing | Every agent/consultor call | First call only |
| Context size | ~800-2000 tokens | ~50-200 tokens |
| MD5 hashing | Yes, on every call | Removed |
| Delta messages | Computed via `difflib`, appended | Removed |
| SQLite queries per injection | ~100+ (N+1 per machine/domain) | 1 (in-memory `store.get_all()` + `os.listdir`) |
| Duplicate delta filtering | List comprehension on every change | Not needed |

**`check_status`** (new tool) provides the detailed state overview that `_build_model_context()` used to include: machine IPs with hostname, device type, domain, and port counts; all domain names; inventory counts (users, credentials, passwords, hashes); evidence sessions; shell sessions; dictionary/rule/POC file counts. Use `check_machine` or `check_domain` for per-target details.

This mechanism is **shared** between agent and consultor modes via the shared `self._llm_messages` list.

### Agent vs Consultor Comparison

| Feature | **Agent** mode | **Consultor** mode |
|---|---|---|
| Entry | Tab mode cycle | Tab mode cycle |
| Purpose | `"agent"` | `"consultor"` |
| System prompt | Shared `system` prompt + `[MODE: AGENT]` message | Shared `system` prompt + `[MODE: CONSULTOR]` message (lists read-only tools) |
| Tool calling | **Yes** — `chat_with_tools()` (all 60 tools) | **Yes** — `chat_with_tools(allowed_tools=CONSULTOR_TOOLS)` (23 read-only tools; the rest are sent but denied) |
| Prompt color | Blue (`#5ba3ec`) | Yellow (`#e6b422`) |
| Context injection | Yes | Yes |
| Shared history | Yes (`self._llm_messages`) | Yes (`self._llm_messages`) |
| Context % display | Yes (`Agent (45%)>`) | Yes (`Consultor (45%)>`) |
| Spinner while processing | Yes | Yes |
| Commands | `exit`, `stop`, `reset`, `compact`, `clear`, `menu`, `debug` | `exit`, `stop`, `reset`, `compact`, `clear`, `menu`, `debug` |
| Tab mode cycle | Cycles without interrupting agent | Cycles without interrupting consultor |

**Rules for agent development:**

- All tool handlers must be in `src/llm/tools.py`. Do not scatter tool logic across the codebase.
- Tool definitions and handlers are statically registered at import time via the `@register` decorator — no dynamic registration needed.
- `tool_context` is always the `App` instance. Tool handlers should only call methods that are safe to invoke from a background thread (scanner start methods, CRUD operations on databases).
- New tools that perform network operations MUST trigger async processes and return immediately — never block the daemon thread.
- Web tools (`webfetch`, `websearch`) are exceptions: they run synchronously inside the daemon thread because the LLM needs the fetched content to reason about it. HTTP requests complete quickly (timeout ≤ 30s).
- Tool results are strings returned to the LLM. Keep them concise and factual.
- The `_llm_messages` list accumulates the full conversation including tool call/result messages. It is **shared** between agent and consultor modes and **persists** across restarts (via `session.json`); it is only cleared by the `reset` command.
- When the LLM outputs invalid XML tool call syntax (e.g. `<invoke>`, `<function_calls>`) instead of proper function calling, the system detects it via regex (`<[^>]*DSML`), warns the model, and retries. A consecutive error counter (`consecutive_xml_errors`, local to `chat_with_tools()`, max 5 followed by abort) prevents infinite loops.
- Pressing Tab cycles through Normal → Consultor → Agent without interrupting the currently running agent thread, **when the input is empty OR is a multi-word prompt whose first word is not a command**. If the first word matches a command (or its prefix), Tab performs command/argument autocomplete. A braille spinner (⠋⠙⠹...) appears next to the prompt while the LLM is processing, visible in all modes.
- The prompt shows context usage percentage for both agent and consultor (e.g. `Agent (45%)>`, `Consultor (45%)>`), updated via `_update_mode_prompt()`. The percentage uses the actual `prompt_tokens` (`_total_api_tokens`) with a chars/4 estimate fallback.
- All GUI updates from agent/consultor daemon threads must use `app._safe_after(callback, *args)` instead of bare `self.after(0, ...)`. This wrapper catches `RuntimeError` if the widget has been destroyed between scheduling and execution.
- `_on_close()` sets `_closing = True`, then `_agent_stop_event`, and calls `console.stop_thinking()` before `destroy()` to prevent agent/consultor threads from accessing dead widgets. `_save_session()` and `chat_with_tools()`'s `after()` call both check `_closing` and skip work during shutdown. The `exit` command handlers in both modes call `_on_close()` to ensure proper cleanup.

---

## Guidelines for AI Agents

When modifying this project:

* Understand the existing architecture before making changes.
* Prefer incremental modifications over large rewrites.
* Respect the separation between console functionality and GUI functionality.
* Preserve the relationship between persisted data and views.
* Keep debugging additions isolated and purposeful.
* Minimize dependencies.
* Maintain pipx compatibility.
* Ensure bundled assets continue to work after packaging.
* Write code suitable for real-world penetration testing workflows.
* Favor reliability, traceability, and portability.
* **Always test installed code via `pipx install --force .`** — running from the project root with `python main.py` does not exercise the same code paths (package data, paths, permissions).

If uncertain about a design decision, choose the approach that is simpler, more maintainable, and introduces the least amount of unnecessary complexity.
