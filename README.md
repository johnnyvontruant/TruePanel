# TruePanel

<p align="center">
  <img src="assets/logo/truepanel-logo.svg" alt="TruePanel logo" width="180">
</p>

<h3 align="center">Hardware-aware mission control for TrueNAS SCALE</h3>

TruePanel turns supported QNAP front-panel hardware into a live operational dashboard for TrueNAS SCALE. It combines a rotating LCD Flight Deck, structured health monitoring, historical telemetry, guarded hardware controls, plugins, and a reverse-engineering laboratory built around reproducible safety rules.

TruePanel began by adapting earlier QNAP LCD utilities, but the current project is an independently developed platform. The original lineage remains preserved in Git history and acknowledgements.

## What TruePanel does

- Rotates system, storage, network, thermal, and ZFS pages on a 16x2 front-panel LCD
- Renders native A125 ROM graphics and custom CGRAM instruments
- Tracks pool health, SMART state, drive temperatures, storage topology, and ZFS operations
- Records historical telemetry for trends and diagnostics
- Routes drive-specific faults to the matching physical bay identify LED
- Keeps detailed storage information available on the LCD without redundant interrupt pages
- Supports buttons, backlight, buzzer patterns, themes, plugins, simulation, and diagnostics
- Provides Project Stargate tools for guarded A125 and QNAP hardware research

## Verified platform

The production reference system is:

- QNAP TVS-671
- TrueNAS SCALE
- Python 3.11
- A125 LCD controller on `/dev/ttyS1` at 1200 baud
- Six drive-bay identify LEDs through `/dev/i2c-0`, SMBus address `0x33`

Other QNAP systems may share parts of this hardware design, but they must be treated as unverified until their controller paths and command maps are reproduced safely.

## Architecture at a glance

```text
Collectors and hardware providers
              |
              v
       Shared system state
              |
              v
 Mission Control and watchers
              |
       +------+------+
       |             |
       v             v
 Alert policy   Hardware indicators
       |             |
       +------+------+
              v
       Display Manager
              |
              v
     Flight Deck / A125 LCD
```

The normal runtime is launched through:

```text
truepanel.py -> truepanel.cli -> lcd-menu.py
```

Production installation lives under `/opt/truepanel`, with the service started through `/opt/truepanel/bin/truepanel run`.

## Installation

```bash
git clone https://github.com/johnnyvontruant/TruePanel.git
cd TruePanel
sudo bash install.sh
```

Then verify:

```bash
sudo /opt/truepanel/bin/truepanel doctor
sudo systemctl status truepanel
sudo journalctl -u truepanel -f
```

TrueNAS administrators should read [Installation](docs/INSTALLATION.md) before deployment. TruePanel installs files under `/opt` and creates a systemd service, which may fall outside the configuration mechanisms officially supported by TrueNAS.

## Command line

```bash
truepanel doctor
truepanel version
truepanel plugins
truepanel themes list
truepanel hardware --help
truepanel lab --help
truepanel simulate --help
```

See [CLI Reference](docs/CLI.md).

## Documentation

- [Documentation map](docs/README.md)
- [Installation](docs/INSTALLATION.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Hardware support](docs/HARDWARE.md)
- [CLI reference](docs/CLI.md)
- [Project Stargate](docs/STARGATE.md)
- [A125 protocol](docs/A125_PROTOCOL.md)
- [Plugin API](docs/PLUGIN_API.md)
- [Historical telemetry](docs/HISTORICAL_TELEMETRY.md)
- [Development guide](docs/DEVELOPMENT.md)
- [Project history](docs/HISTORY.md)
- [Roadmap](docs/ROADMAP.md)
- [Philosophy](docs/PHILOSOPHY.md)

## Repository structure

```text
truepanel/                 Production package
tests/                     Automated test suite
docs/                      User and developer documentation
development/tools/         Reproducible Stargate laboratory tools
examples/plugins/          External plugin examples
plugins/                   Locally installed plugins and runtime state
collector.py               TrueNAS state collector used by the live service
lcd-menu.py                Production Flight Deck runtime
truepanel.py               CLI compatibility launcher
truepanel.yaml             Reference configuration
install.sh                 Native installer
uninstall.sh               Native uninstaller
```

Generated captures, extracted firmware, compiled probes, caches, backups, runtime plugin state, and local telemetry are intentionally excluded from Git.

## Safety

TruePanel can communicate with serial, SMBus, GPIO, Super I/O, buzzer, and enclosure hardware. Production controls are constrained to verified command maps. Project Stargate uses explicit interlocks, simulation modes, exclusive ownership, and narrow command catalogs.

Do not perform generic I2C scans, random register writes, or destructive storage experiments on production hardware.

## Project status

TruePanel is active software. The consolidated platform passed 861 automated tests on July 19, 2026. Hardware support beyond the TVS-671 reference system remains experimental until independently verified.

## License and lineage

TruePanel is distributed under the repository license. Earlier QNAP LCD work provided the initial spark; the modern architecture, Flight Deck, Mission Control, Project Stargate laboratory, telemetry, hardware abstraction, and TVS-671 controls were developed as TruePanel. Git history preserves the full lineage.

## Stable release

TruePanel 1.0.0 is the first stable release of the independent TruePanel platform.

Release resources:

- [Changelog](CHANGELOG.md)
- [Installation guide](docs/INSTALLATION.md)
- [Upgrade and rollback guide](docs/UPGRADING.md)
- [Security policy](SECURITY.md)
- [Contributing guide](CONTRIBUTING.md)
