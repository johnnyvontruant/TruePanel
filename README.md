# TruePanel

<p align="center">
  <img src="assets/logo/truepanel-logo.svg" alt="TruePanel Logo" width="180">
</p>

<h1 align="center">TruePanel</h1>

<h3 align="center">
Mission Control for TrueNAS LCD Dashboards
</h3>

<p align="center">
Transform compatible QNAP LCD hardware into a modern, modular dashboard for TrueNAS SCALE.
</p>

<p align="center">

![Status](https://img.shields.io/badge/status-active-success.svg)
![Python](https://img.shields.io/badge/python-3.11+-blue.svg)
![Platform](https://img.shields.io/badge/platform-TrueNAS%20SCALE-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)

</p>

---

# Overview

TruePanel breathes new life into compatible QNAP LCD front panels by transforming them into a dedicated Mission Control dashboard for TrueNAS SCALE.

Instead of letting the front-panel LCD sit unused, TruePanel continuously displays the health and status of your NAS, giving you instant visibility into the information that matters most.

Current dashboard capabilities include:

- Storage Pool Health
- CPU Utilization
- Memory Usage
- Network Activity
- Drive Temperatures
- SMART Alerts
- Plugin Pages
- Theme-aware Display Layouts

TruePanel is designed around a modern modular architecture that allows new collectors, pages, plugins, themes, and hardware support to be added without changing the core application.

---

# Why TruePanel?

Most LCD projects simply display a handful of system statistics.

TruePanel is designed to become an extensible dashboard platform.

Its architecture emphasizes:

- Clean software design
- Modular components
- Hardware abstraction
- Plugin support
- Reliability
- Easy customization
- Long-term maintainability

Whether you're managing a home NAS or a rack of servers, TruePanel keeps critical information where it belongs:

Right on the front panel.

---

# Features

## 🚀 Mission Control

Coordinates collectors, shared state, page scheduling, and display rendering through a centralized control engine.

---

## ✈️ FlightDeck

Automatically rotates dashboard pages while allowing future support for priorities, alerts, and user customization.

---

## 🔌 Plugin Framework

Extend TruePanel by creating new dashboard pages without modifying the core project.

---

## 📊 Collector Framework

Independent collectors gather system information, making new data sources easy to add and maintain.

---

## 🎨 Theme Engine

Support multiple display themes and future community-created layouts.

---

## 🖥 Hardware Abstraction

Designed to support additional LCD hardware with minimal changes to the application itself.

---

# Architecture

```
                +----------------------+
                |      Collectors      |
                +----------+-----------+
                           |
                           v
                +----------------------+
                |   Mission Control    |
                +----------+-----------+
                           |
                           v
                +----------------------+
                |     Shared State     |
                +----------+-----------+
                           |
                           v
                +----------------------+
                |      FlightDeck      |
                +----------+-----------+
                           |
                           v
                +----------------------+
                |   Display Manager    |
                +----------+-----------+
                           |
                           v
                +----------------------+
                |      LCD Driver      |
                +----------------------+
```

Each component has a single responsibility, making TruePanel easier to understand, test, and extend.

---

# Project Structure

```
truepanel/
├── collectors/
├── config/
├── display/
├── doctor/
├── flightdeck/
├── mission_control/
├── pages/
├── plugins/
├── themes/
├── utils/
└── ...
```

---

# Compatibility

| Component | Status |
|-----------|--------|
| TrueNAS SCALE | ✅ Supported |
| Python 3.11 | ✅ Supported |
| Debian 12 | ✅ Tested |
| QNAP LCD Hardware | ✅ Supported |

---

# Supported Hardware

### Currently Supported

- Compatible QNAP LCD front panels

### Planned

- Additional QNAP models
- USB LCD devices
- OLED displays
- Character LCD modules

---

# Quick Start

Clone the repository.

```bash
git clone https://github.com/johnnyvontruant/TruePanel.git
cd TruePanel
bash install.sh
```

Start the service.

```bash
systemctl start truepanel
```

Enable automatic startup.

```bash
systemctl enable truepanel
```

Watch the live log.

```bash
journalctl -u truepanel -f
```

> **TrueNAS SCALE Note**
>
> Use `bash install.sh` instead of `./install.sh`. Some TrueNAS SCALE systems mount directories using the `noexec` option, preventing scripts from executing directly.

---

# Tested Installation

The installer has been validated on a clean TrueNAS SCALE installation using a fresh clone of the GitHub repository.

Current installer features include:

- Automatic installation
- TrueNAS SCALE compatible virtual environment
- Automatic systemd service creation
- Automatic service enablement
- Safe reinstall support
- Clean upgrade path

---

# Screenshots

🚧 Coming Soon

The Mission Control dashboard is evolving rapidly.

Screenshots will be added as the interface reaches its first stable release.

---

# Roadmap

## ✅ Current

- Mission Control
- FlightDeck
- Collector Framework
- Plugin Framework
- Theme Engine
- Hardware Abstraction

---

## 🚧 In Progress

- AutoPilot
- Configuration Manager
- Documentation
- Installer Improvements
- Additional Dashboard Pages

---

## 🛰 Planned

- Sentinel Monitoring
- REST API
- Web Dashboard
- Community Plugin Repository
- Community Themes
- Docker Images
- Multiple LCD Hardware Targets

---

# Contributing

Contributions are always welcome.

Whether you enjoy writing code, improving documentation, testing hardware, or sharing ideas, your help is appreciated.

To contribute:

1. Fork the repository
2. Create a feature branch
3. Commit your work
4. Open a Pull Request

---

# Design Philosophy

TruePanel follows a few simple principles.

- One component, one responsibility.
- Reliability over complexity.
- Keep the display readable.
- Build for extensibility.
- Document decisions.
- Make contributions approachable.
- Build software people enjoy using.

---

# License

Released under the MIT License.

See the `LICENSE` file for details.

---

# Acknowledgements

Special thanks to everyone experimenting with QNAP LCD hardware, TrueNAS SCALE, and the home lab community.

Your ideas, testing, bug reports, and feedback continue to shape the future of TruePanel.

---

<p align="center">

**Built by home lab enthusiasts, for home lab enthusiasts.**

**Build cool things. Share what you create. Help the next person build something even better.**

</p>
