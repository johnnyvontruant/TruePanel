# TruePanel

<p align="center">
  <img src="assets/logo/truepanel-logo.svg" alt="TruePanel Logo" width="180">
</p>

<h3 align="center">
Mission Control for TrueNAS LCD Dashboards
</h3>

<p align="center">
Transform compatible QNAP LCD hardware into a modern, plugin-driven dashboard for TrueNAS SCALE.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/status-active-success.svg">
  <img src="https://img.shields.io/badge/python-3.11+-blue.svg">
  <img src="https://img.shields.io/badge/license-MIT-green.svg">
  <img src="https://img.shields.io/badge/platform-TrueNAS%20SCALE-blue.svg">
</p>

---

## Overview

TruePanel brings aging QNAP LCD hardware back to life by turning it into a dedicated system dashboard for TrueNAS SCALE.

Instead of becoming another forgotten display, the LCD becomes a live mission console for your NAS, showing the information that matters most:

- Storage pool health
- CPU utilization
- Memory usage
- Network activity
- Drive temperatures
- System alerts
- Plugin-provided pages
- Theme-aware layouts

TruePanel was designed from the ground up around a modular architecture, allowing new pages, collectors, themes, and hardware support to be added without changing the core application.

---

## Why TruePanel?

Most LCD projects stop at displaying a few system statistics.

TruePanel aims to become a flexible dashboard platform.

Its design focuses on:

- Clean architecture
- Modular components
- Hardware abstraction
- Expandability
- Reliability
- Easy customization

Whether you're running a single home NAS or maintaining multiple systems, TruePanel provides a lightweight dashboard that always keeps your server's status within view.

---

## Features

### Mission Control

The central engine that coordinates data collection, state updates, and page rendering.

### FlightDeck

Automatically manages page rotation and prioritization.

### Plugin Framework

Create new dashboard pages without modifying the core application.

### Collector Framework

System information is gathered through independent collectors, making it easy to extend and maintain.

### Theme Engine

Support for multiple display themes and future community-created designs.

### Hardware Abstraction

Designed so additional LCD hardware can be supported with minimal changes.

---

## Architecture

```
                +--------------------+
                |    Collectors      |
                +---------+----------+
                          |
                          v
                +--------------------+
                |  Mission Control   |
                +---------+----------+
                          |
                          v
                +--------------------+
                |   Shared State     |
                +---------+----------+
                          |
                          v
                +--------------------+
                |    FlightDeck      |
                +---------+----------+
                          |
                          v
                +--------------------+
                | Display Manager    |
                +---------+----------+
                          |
                          v
                +--------------------+
                |      LCD Driver    |
                +--------------------+
```

Each component has a single responsibility, making the project easier to understand, test, and extend.

---

## Project Structure

```
truepanel/
│
├── collectors/
├── mission_control/
├── hardware/
├── display/
├── pages/
├── plugins/
├── themes/
├── shared_state/
└── utils/
```

---

## Quick Start

Clone the repository.

```bash
git clone https://github.com/JohnnyvonTruant/TruePanel.git
cd TruePanel
```

Install dependencies.

```bash
./install.sh
```

Launch TruePanel.

```bash
python3 run.py
```

---

## Screenshots

Coming soon.

We are actively developing the next generation dashboard interface.

---

## Roadmap

### Current

- Modular architecture
- Plugin system
- Theme support
- Mission Control
- FlightDeck
- Collector framework

### In Progress

- AutoPilot enhancements
- Additional dashboard pages
- Improved installer
- Configuration manager

### Planned

- Sentinel monitoring
- REST API
- Web dashboard
- Community plugin repository
- Docker support
- Multiple LCD hardware targets

---

## Contributing

Contributions are always welcome.

Ideas, bug reports, documentation improvements, testing, and pull requests all help move the project forward.

If you're interested in contributing:

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Submit a Pull Request

---

## Design Philosophy

TruePanel follows a few simple principles:

- One component, one responsibility.
- Keep the display readable.
- Reliability over complexity.
- Build for extensibility.
- Make contributions approachable.
- Document decisions.
- Have fun building cool things.

---

## License

Released under the MIT License.

See `LICENSE` for details.

---

## Acknowledgements

Special thanks to everyone experimenting with QNAP LCD hardware, TrueNAS SCALE, and open-source home lab projects.

Your ideas and feedback continue to shape the future of TruePanel.

