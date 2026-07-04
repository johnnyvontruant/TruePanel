# TruePanel Roadmap

TruePanel is being developed in small, focused milestones. Each release has a specific objective that moves the project closer to a polished, production-ready front panel for TrueNAS SCALE.

---

# Current Development

## Version 0.6.0-dev "Sentinel"

Current focus:

* Collector architecture
* Shared system state
* CPU and memory monitoring
* ZFS pool health
* Storage usage
* Drive temperature monitoring
* ARC cache statistics
* ZFS scrub and resilver detection

Status: **In Development**

---

# Version 0.7.0 "Mission Control"

Objective:

Teach TruePanel to understand what matters.

Planned features:

* Decision Engine
* Mission Control home screen
* Priority-based alert system
* Live network throughput
* Improved page management

Instead of cycling through information equally, TruePanel will learn to display the most important system status automatically.

---

# Version 0.8.0 "Watchtower"

Objective:

Expand hardware awareness.

Planned features:

* SMART health reporting
* CPU temperature
* Fan speed monitoring (supported hardware)
* Additional storage statistics
* Improved hardware compatibility

---

# Version 0.9.0 "Polaris"

Objective:

Customization and refinement.

Planned features:

* Configuration file
* Custom page ordering
* User-selectable refresh rates
* Night mode and backlight options
* Diagnostics mode
* Improved logging

---

# Version 1.0.0 "Beacon"

Objective:

First stable public release.

Goals:

* Complete documentation
* Automated installation
* Stable architecture
* Community-tested hardware support
* Long-term maintenance plan

Version 1.0 represents the first feature-complete release of TruePanel.

---

# Beyond 1.0

Possible future enhancements include:

* Web dashboard
* Home Assistant integration
* REST API
* MQTT publishing
* OLED and USB display support
* Plugin architecture
* Multiple display themes
* Localization
* Additional NAS platform support

---

# Guiding Principle

Every release should make TruePanel more useful, more reliable, and easier to maintain.

Features will never be added simply because they are possible. Every addition should improve the experience of understanding the health of a TrueNAS system at a glance.

The ultimate goal remains unchanged:

> **Build the front panel that TrueNAS deserves.**
