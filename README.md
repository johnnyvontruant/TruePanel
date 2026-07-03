# TruePanel

> **Mission control for your TrueNAS front panel.**

TruePanel is a modular front-panel monitoring platform for supported QNAP NAS systems running TrueNAS SCALE. It brings the built-in LCD back to life with a real-time dashboard, automated rotation, alert-aware display logic, theme packs, diagnostics, simulation tools, and a plugin-ready architecture.

TruePanel started as a way to revive the LCD on a QNAP TVS-671. It has grown into a small, extensible monitoring platform designed around one goal:

> **The front panel should tell you the single most important thing happening on your NAS.**

---

## Project Status

**Current release candidate:** `v1.0.0-rc0`

TruePanel has passed a clean installation test on TrueNAS SCALE:

```text
Clone repository
Run installer
Doctor reports MISSION READY
Start systemd service
Reboot
Service starts automatically

Highlights
QNAP front-panel LCD support
TrueNAS SCALE-focused monitoring
Collector-first system state architecture
Mission Control event evaluation
Alert Manager with priority handling
Display Manager with registry-driven dashboard pages
FlightDeck AutoPilot dashboard rotation
Startup sequence
Night Mode
Theme packs
Plugin registry and plugin manager
Simulator collector
truepanel doctor diagnostics
truepanel plugins registry view
truepanel simulate scenarios
systemd service installer
Docker support foundation
Supported Hardware
Tested
QNAP TVS-671
TrueNAS SCALE
LCD serial port: /dev/ttyS1

Additional QNAP models may work, but community testing is needed.

Quick Start

Clone the development branch:

git clone -b develop https://github.com/johnnyvontruant/TruePanel.git
cd TruePanel

Run the installer:

sudo ./install.sh

Run diagnostics:

/opt/truepanel/bin/truepanel doctor

Start the service:

sudo systemctl start truepanel

Enable startup on boot:

sudo systemctl enable truepanel

View logs:

journalctl -u truepanel -f
CLI

After installation, use:

/opt/truepanel/bin/truepanel doctor
/opt/truepanel/bin/truepanel plugins
/opt/truepanel/bin/truepanel version
/opt/truepanel/bin/truepanel simulate thermal --steps 5 --delay 0.2

The service uses:

/opt/truepanel/bin/truepanel run
Simulator

The simulator lets you test TruePanel without creating real NAS problems.

Available scenarios:

normal
thermal
pool
smart
resilver
network
capacity
quiet-night
everything

Example:

/opt/truepanel/bin/truepanel simulate everything --steps 10 --delay 0.2
Doctor

truepanel doctor checks:

Python runtime
Configuration
Theme pack
Plugin registry
Required system commands
TrueNAS collector import
Simulator state generation
Mission stack imports

A healthy install ends with:

MISSION READY
Architecture
                           TruePanel
                               │
                         truepanel CLI
                               │
      ┌────────────────────────┼────────────────────────┐
      │                        │                        │
   Doctor                 Simulator               Plugin Manager
      │                        │                        │
      └────────────────────────┼────────────────────────┘
                               │
                        Plugin Registry
      ┌──────────────┬─────────┼──────────┬─────────────┐
      │              │         │          │             │
 Collectors      Dashboard   Themes   Startup      Hardware
      │            Pages                  │
      └───────────────────────────────────┘
                      │
              Collector Factory
                      │
              Mission Control
                      │
              Alert Manager
                      │
             Display Manager
                      │
                 FlightDeck
                      │
                  AutoPilot
                      │
                 LCD Hardware
Configuration

TruePanel uses truepanel.yaml.

Example:

theme_pack: default

flightdeck:
  rotation_interval: 5
  pause_after_button: 60
  idle_slowdown_after: 3600
  idle_interval: 30

  transitions:
    enabled: true

  startup:
    enabled: true
    delay: 0.75
    diagnostics: true

  night_mode:
    enabled: true
    idle_after: 1800
    rotation_interval: 60
    suppress_info: true
    dashboard_pages:
      - home
      - storage
Theme Packs

Included theme packs:

default
tactical
quiet

Theme packs live in:

truepanel/themes/packs/
Plugins

TruePanel includes a plugin registry and manager.

Built-in plugins:

Core
Simulator
Plugin Status

Current plugin-provided capabilities include:

dashboard pages
collectors
theme pack registration
Development

Run syntax checks:

python3 -m py_compile truepanel.py collector.py truepanel/**/*.py

Run the simulator from the repository:

python3 truepanel.py simulate thermal --steps 3 --delay 0.1

Run doctor from the repository:

python3 truepanel.py doctor
Roadmap
v1.0
Release hardening
Documentation polish
Installer polish
Logging polish
Final clean install test
v1.1
Configuration validation
Plugin examples
Better installer wizard
Expanded logging
Additional hardware compatibility reports
Future
Web Mission Console
Multiple display backends
MQTT/Home Assistant integration
Remote collector support
Multi-NAS monitoring
Acknowledgements

TruePanel builds on the work of the QNAP LCD and TrueNAS community. The project exists because those early hardware and serial interface experiments made it possible to give these front panels a second life.

License

Released under the MIT License.


Test:

```bash
python3 -m py_compile truepanel.py truepanel/cli.py truepanel/logging.py
python3 truepanel.py version
python3 truepanel.py doctor
python3 truepanel.py plugins
