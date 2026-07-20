# TruePanel Installation

## Scope

The native installer deploys TruePanel to `/opt/truepanel`, creates `/opt/truepanel/bin/truepanel`, and installs `truepanel.service`.

The reference platform is TrueNAS SCALE on a QNAP TVS-671. The installer may also work on compatible Debian-based systems, but physical hardware support must be verified separately.

## TrueNAS support boundary

TrueNAS warns that configuration changes should be made through its Web UI, CLI, or API. TruePanel creates a systemd unit and writes under `/opt`, so it may fall outside the operating system's officially supported configuration path.

Use TruePanel with a current configuration backup and expect major TrueNAS upgrades to require service verification or reinstallation.

## Requirements

- Root access
- Python 3.11 or newer
- `rsync`
- `systemctl`
- `smartctl` for SMART telemetry
- ZFS command-line tools
- Access to the relevant serial, SMBus, and sysfs hardware paths

## Native installation

```bash
git clone https://github.com/johnnyvontruant/TruePanel.git
cd TruePanel
sudo bash install.sh
```

The installer:

1. copies the repository to `/opt/truepanel`;
2. attempts to create a Python virtual environment;
3. falls back to system Python when the TrueNAS Python environment cannot create a usable venv;
4. verifies required imports;
5. creates the CLI wrapper;
6. creates the systemd service;
7. runs `truepanel doctor`.

## Service management

```bash
sudo systemctl enable truepanel
sudo systemctl start truepanel
sudo systemctl restart truepanel
sudo systemctl stop truepanel
sudo systemctl status truepanel
sudo journalctl -u truepanel -f
```

The service executes:

```text
/opt/truepanel/bin/truepanel run
```

with `/opt/truepanel` as its working directory.

## Configuration

The installed configuration is:

```text
/opt/truepanel/truepanel.yaml
```

The repository includes `truepanel.yaml` as the reference configuration. Important sections include:

- `flightdeck`
- `mission_control`
- `hardware`
- `history`
- `buzzer`
- `theme`
- `theme_pack`

BattleStation enables TVS-671 bay LEDs under `mission_control.storage_health`. Leave model-specific controls disabled on unverified hardware.

## Upgrade

From a clean repository checkout:

```bash
cd ~/TruePanel
git checkout develop
git pull --ff-only origin develop
sudo bash install.sh
sudo systemctl restart truepanel
sudo /opt/truepanel/bin/truepanel doctor
```

Before upgrading, preserve the installed configuration and package:

```bash
sudo cp -a /opt/truepanel "/opt/truepanel.backup-$(date +%Y%m%d-%H%M%S)"
```

Do not copy extracted firmware, compiled laboratory probes, caches, or development captures into `/opt/truepanel`.

## Manual verification

```bash
sudo /bin/python3 -m compileall -q /opt/truepanel/truepanel
sudo /opt/truepanel/bin/truepanel version
sudo /opt/truepanel/bin/truepanel doctor
systemctl is-active truepanel
sudo journalctl -u truepanel -n 80 --no-pager
```

On the TVS-671 reference system, also verify:

```bash
ls -l /dev/ttyS1 /dev/i2c-0
```

## Uninstall

```bash
cd ~/TruePanel
sudo bash uninstall.sh
```

The uninstaller stops and disables the service, removes the systemd unit, removes both current and legacy CLI wrapper paths, reloads systemd, and deletes `/opt/truepanel`.

Local repository clones, external firmware archives, and Git history are not removed.

## Docker

Docker files remain available as an experimental deployment surface. Direct access to LCD, SMBus, GPIO, sysfs, SMART, and ZFS resources requires broad host permissions and may not behave like native deployment. Native installation is the reference path for physical front-panel hardware.

## Mission Control companion service

Mission Control runs as a separate systemd companion service. It does not replace or share the process of the primary LCD TruePanel service.

The installer places these files:

- `/etc/systemd/system/truepanel-mission-control.service`
- `/etc/default/truepanel-mission-control`
- `/opt/truepanel/truepanel/web/`

The service is installed with conservative defaults:

```text
TRUEPANEL_MC_HOST=127.0.0.1
TRUEPANEL_MC_PORT=8787
TRUEPANEL_MC_CONFIG_PATH=/opt/truepanel/truepanel.yaml
TRUEPANEL_MC_ALLOW_CONFIG_WRITES=false
```

Enable and start the companion service:

```bash
sudo systemctl enable --now truepanel-mission-control
```

Check its state:

```bash
sudo /opt/truepanel/bin/truepanel mission-control status
```

The default dashboard is available only from the TrueNAS host:

```text
http://127.0.0.1:8787
```

### LAN access

To make the dashboard available to trusted systems on the local network, edit `/etc/default/truepanel-mission-control`:

```text
TRUEPANEL_MC_HOST=0.0.0.0
```

Then restart only the companion service:

```bash
sudo systemctl restart truepanel-mission-control
```

Open the dashboard using the TrueNAS management address:

```text
http://<TrueNAS-IP>:8787
```

Binding to `0.0.0.0` exposes the HTTP service on every available network interface. Restrict access with trusted network boundaries and firewall policy where appropriate.

### Configuration writes

Mission Control is read-only unless configuration writes are deliberately enabled:

```text
TRUEPANEL_MC_ALLOW_CONFIG_WRITES=true
```

After changing the environment file, restart the companion service:

```bash
sudo systemctl restart truepanel-mission-control
```

Write mode permits validated Night Mode changes to `/opt/truepanel/truepanel.yaml`. Each save uses atomic replacement and creates a timestamped backup. Mission Control does not automatically restart the primary TruePanel service after a save.

Keep write mode disabled unless remote configuration is specifically required. The web service never writes directly to the LCD serial interface, I2C devices, sysfs controls, or other hardware endpoints.

### Service separation

The two production services are independent:

```bash
sudo systemctl status truepanel
sudo systemctl status truepanel-mission-control
```

Restarting Mission Control does not restart the LCD True service. Restarting the LCD True service does not require restarting Mission Control.
