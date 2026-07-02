# TruePanel

> **Bring your QNAP front panel back to life on TrueNAS SCALE.**

TruePanel is a native front-panel dashboard for supported QNAP NAS systems running TrueNAS SCALE. Rather than recreating the original QTS LCD interface, TruePanel is designed specifically for TrueNAS, transforming the built-in LCD into a real-time system monitor for storage, performance, and overall system health.

Built around a collector-first architecture, TruePanel gathers system information once and shares it across the entire application, resulting in a fast, responsive, and easily extensible dashboard.

---

## Features

Current development includes:

* LCD communication and backlight control
* Front-panel button navigation
* Automatic page rotation
* CPU utilization
* Memory utilization
* ZFS pool health
* Storage usage with progress bar
* Drive temperature monitoring (SATA and NVMe)
* ARC cache statistics
* ZFS scrub and resilver activity detection
* Collector-based backend architecture

---

## Why TruePanel?

Many QNAP systems include an excellent front-panel LCD that becomes largely unused after installing TrueNAS SCALE.

TruePanel gives that display a new purpose by turning it into a live operations dashboard that provides useful information at a glance, without requiring a monitor or web browser.

The long-term vision is simple:

> **The front panel should tell you the single most important thing happening on your NAS.**

---

## Design Philosophy

TruePanel follows a few core principles:

### One Glance

The most important information should be understandable in under one second.

### Collector First

System data is collected once and shared across the application rather than having each display page execute its own commands.

### Native

TruePanel is designed specifically for TrueNAS SCALE rather than attempting to emulate the original QTS firmware.

### Reliable

The dashboard should be capable of running continuously for months with minimal resource usage.

### Extensible

Adding new monitoring pages should be straightforward without requiring major architectural changes.

---

## Architecture

```text
                TrueNAS SCALE
                      │
                      ▼
            TruePanel Collector
                      │
              Shared System State
                      │
          ┌───────────┼───────────┐
          │           │           │
          ▼           ▼           ▼
      Storage      Hardware    Network
          │           │           │
          └───────────┼───────────┘
                      ▼
              Decision Engine
                      ▼
                 LCD Renderer
                      ▼
               QNAP Front Panel
```

The collector continuously gathers system telemetry and exposes a shared state that can be consumed by display pages and future interfaces.

---

## Roadmap

### Version 0.7 — Mission Control

* Decision Engine
* Mission Control home screen
* Priority-based status display
* Live network throughput

### Version 0.8

* SMART health monitoring
* CPU temperature
* Fan speed monitoring (supported hardware)
* TrueNAS alerts

### Version 0.9

* Configuration file
* Custom page ordering
* Night mode
* Diagnostics mode

### Version 1.0

* Automated installer
* Complete documentation
* Stable public release

---

## Supported Hardware

### Currently Tested

* **QNAP TVS-671**
* **TrueNAS SCALE**

Current LCD serial port:

```text
/dev/ttyS1
```

Support for additional QNAP models is planned. Community testing and feedback are welcome.

---

## Installation

Clone the repository:

```bash
git clone https://github.com/johnnyvontruant/TruePanel.git
cd TruePanel
```

Verify LCD communication:

```bash
sudo python3 preinit.py
```

Launch the dashboard:

```bash
sudo python3 lcd-menu.py
```

Documentation for automatic startup through TrueNAS Init/Shutdown scripts will continue to evolve as the project matures.

---

## Project Status

**Current Version**

**0.6.0-dev** *(Codename: Sentinel)*

TruePanel is under active development. The project is already stable enough for experimentation, but additional features and architectural improvements are planned before the first production release.

---

## Contributing

Bug reports, hardware compatibility reports, feature ideas, and pull requests are all welcome.

If you've successfully tested TruePanel on another QNAP model, please open an issue and let us know your hardware configuration.

---

## Acknowledgements

TruePanel builds upon the excellent work of the QNAP LCD community, particularly the original LCD interface and TrueNAS adaptation projects that made this effort possible.

---

## License

Released under the MIT License.
