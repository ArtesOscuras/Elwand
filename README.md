# Elwand — Your AI-Powered Security Workbench

A GUI and CLI pentest application to help beginners in a friendly environment.

## Requirements

- **Python ≥ 3.11**
- **Git** (to clone the repository)
- **Homebrew** (macOS only)

## Install

### Linux

```
sudo apt update && sudo apt install -y python3 python3-tk pipx fontconfig
pipx ensurepath
source ~/.bashrc

(Optional)
sudo apt install -y nmap hydra hashcat whatweb freerdp2-x11 chromium-browser

(Recommended)
sudo setcap cap_net_raw+ep $(readlink -f $(which python3))

git clone https://github.com/ArtesOscuras/Elwand.git ; cd Elwand ; pipx install .
```

### macOS

```
brew install python-tk pipx fontconfig
pipx ensurepath
source ~/.zshrc

(Optional)
brew install nmap hydra hashcat whatweb freerdp chromium

git clone https://github.com/ArtesOscuras/Elwand.git ; cd Elwand ; pipx install .
```

## Usage

`elwand`

`sudo "$(which elwand)"` (only if you need extra permissions for the scanner tools)

## Network permissions

Some scanners (passive mDNS listener, active identification) need extra network permissions on Linux. You can grant them once with:

```
sudo setcap cap_net_raw+ep $(readlink -f $(which python3))
```

This avoids having to run Elwand as root.

## Data stored

Wordlists, databases, credentials, evidence files... are stored at:

- `~/.local/share/elwand/` (default)
