# Elwand

**Your AI-Powered Security Workbench**

Elwand is a Python-based penetration-testing workbench that combines a graphical interface with an embedded interactive console. It is designed for security professionals and learners who want reconnaissance, target inventory, shell access, evidence collection and AI-assisted analysis in one session-based workspace.

> Elwand is intended for authorized security testing only. Use it exclusively against systems you own or have explicit permission to assess.

## Features

- **Unified GUI and console** — graphical views show the data Elwand has collected, while the embedded console drives the underlying operations.
- **Work sessions** — each engagement is an isolated workspace with its own machines, domains, inventory, evidence, reports, dictionaries and AI conversation.
- **Reconnaissance and enumeration** — network discovery, TCP/UDP port scanning, service and banner identification, DNS lookups, WhatWeb and host inspection.
- **Web assessment** — directory, virtual-host and DNS fuzzing, web recording, HTTP fetching and optional anti-bot challenge handling.
- **Target inventory** — machines, domains, users, credentials, passwords, hashes, tickets, people and shell sessions stored locally.
- **Shells** — reverse-shell listener plus SSH, SFTP, FTP and WinRM sessions, with a raw VT terminal for full-screen applications.
- **WiFi assessment** — monitor-mode capture, probe and handshake collection, channel control and injection on supported adapters. Linux supports monitor mode and injection; macOS supports built-in capture plus RT2800 USB adapters for capture and injection.
- **Cracking and wordlists** — Hashcat integration for background cracking and DICMA for generating wordlists and rules.
- **Evidence and reporting** — structured evidence collection, Markdown reports and Python proof-of-concept scripts with an editor and runner.
- **AI assistance** — Consultor mode for read-only analysis and Agent mode with tool calling over Elwand's inventory and operations. Works with opencode, Ollama and other OpenAI-compatible providers.
- **Local-first data** — no external database server is required; session data is stored under `~/.local/share/elwand/`.

## Requirements

- Python 3.11 or newer
- Tcl/Tk 8.6 or newer
- Linux or macOS
- `pipx` for the recommended installation

Optional external tools such as `nmap`, `hashcat`, `whatweb`, `hydra` and `freerdp` unlock additional features when available.

## Installation

See [INSTALL.md](INSTALL.md) for the full Linux and macOS instructions.

Quick start:

```sh
git clone https://github.com/ArtesOscuras/Elwand.git
cd Elwand
pipx install .
elwand
```

## Usage

Start the application with:

```sh
elwand
```

If the scanner needs raw network permissions, run:

```sh
sudo "$(which elwand)"
```

In the console, `Tab` cycles between Normal, Consultor and Agent modes, and `help` lists the available commands. The GUI is intended as a view over persisted data, so operational state remains available across restarts.

## Data and Sessions

By default, Elwand stores its data in `~/.local/share/elwand/`. Each work session has its own directory, including databases, credentials, evidence, handshakes, POCs, reports, dictionaries, rules and AI conversation state.

Set `ELWAND_HOME` to use a different runtime root.

## Documentation

- [INSTALL.md](INSTALL.md) — installation and usage manual
- [AGENTS.md](AGENTS.md) — architecture and development notes
- [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) — bundled third-party components and licenses

## Third-Party Components

Elwand bundles its own fonts and icons, and ships the source and a prebuilt binary for the RT2800 USB helper (`rt2800d`, GPL-2.0) together with its Ralink firmware. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for provenance, licenses and build instructions.
