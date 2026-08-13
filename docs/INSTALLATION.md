# TruePanel Installation

## Scope

The native installer deploys TruePanel to an operator-selected persistent dataset path under `/mnt/`. The examples in this guide use `/mnt/POOL/DATASET/TruePanel`. The installer creates the CLI wrapper inside that installation root, installs the primary LCD and Mission Control service units, and lays down the dormant marker-gated standalone Host Agent unit without starting it.

The reference platform is TrueNAS SCALE on a QNAP TVS-671. The installer may also work on compatible Debian-based systems, but physical hardware support must be verified separately.

## TrueNAS support boundary

TrueNAS warns that configuration changes should be made through its Web UI, CLI, or API. TruePanel therefore remains outside the operating system's officially supported application path. Persistent application state belongs under the explicitly selected `/mnt/...` installation root. System integration uses `/etc/systemd/system`, `/etc/default`, `/run/truepanel`, `/usr/local/bin`, and, for the reference POSTINIT deployment, transient `/opt` state.

Use TruePanel with a current configuration backup and expect major TrueNAS upgrades to require service verification or reinstallation.

## Requirements

- Root access
- Python 3.11 or newer
- `rsync`
- `systemctl`
- `smartctl` for SMART telemetry
- ZFS command-line tools
- Access to the relevant serial, SMBus, and sysfs hardware paths
- Network access to PyPI while the installer prepares the isolated Python runtime

## Compatibility check before installation

Unknown or unverified hardware should be surveyed before TruePanel services are installed.

```bash
git clone https://github.com/johnnyvontruant/TruePanel.git
cd TruePanel
python3 truepanel.py compatibility
```

The compatibility survey is passive. It inspects platform and hardware evidence without opening the LCD controller, changing fan PWM state, operating bay LEDs, modifying storage pools, or granting active hardware-control authority.

Compatibility classifications are:

- `SUPPORTED` - passive capabilities required by the current platform were detected
- `PARTIAL` - some useful capabilities were detected but expected interfaces are missing
- `REVIEW` - manual compatibility review is required
- `UNSUPPORTED` - a required platform condition is not supported

A `SUPPORTED` result does not authorize fan, LCD, LED, or other active hardware control. Hardware control remains locked until the relevant interfaces have been separately verified and commissioned.

For compatibility review, generate a privacy-safe support bundle:

```bash
python3 truepanel.py compatibility \
  --support-bundle \
  --output truepanel-support.json
```

The support bundle excludes hostnames, IP addresses, drive serial numbers, WWIDs, MAC addresses, usernames, configuration secrets, and pool contents.

## Native installation

For verified hardware, or after reviewing the compatibility survey:

```bash
git clone https://github.com/johnnyvontruant/TruePanel.git
cd TruePanel
python3 truepanel.py compatibility
sudo bash install.sh \
  --root /mnt/POOL/DATASET/TruePanel
```

The installer:

1. copies the repository to `/mnt/POOL/DATASET/TruePanel`;
2. creates an isolated Python virtual environment;
3. when TrueNAS lacks `ensurepip`, creates the venv with `--without-pip`, downloads a pinned, hash-verified pip wheel from PyPI, and runs pip from that wheel inside the venv;
4. installs `requirements.txt` inside the isolated venv and verifies `pyserial`, `psutil`, and `PyYAML`;
5. does not install TruePanel dependencies into system Python;
6. creates the CLI wrapper;
7. creates the primary LCD and Mission Control service units;
8. creates the dormant standalone Host Agent unit with its cutover-marker condition and no `[Install]` section;
9. leaves all services stopped so activation remains an explicit operator action;
10. runs `truepanel doctor`.

## Service management

The installer does not start services automatically. Enable and start the two application services explicitly when the installation is ready to become active:

```bash
sudo systemctl enable --now truepanel.service
sudo systemctl enable --now truepanel-mission-control.service
```

Primary LCD service operations remain available individually:

```bash
sudo systemctl restart truepanel.service
sudo systemctl stop truepanel.service
sudo systemctl status truepanel.service
sudo journalctl -u truepanel.service -f
```

`truepanel-host-agent.service` is installed only as a dormant future process boundary. Do not enable or start it during normal embedded operation. Its service unit requires `/run/truepanel/standalone-host-agent.enabled`, and standalone production activation remains separately locked in Python.

The primary LCD service executes:

```text
/mnt/POOL/DATASET/TruePanel/bin/truepanel run
```

with `/mnt/POOL/DATASET/TruePanel` as its working directory.

## Configuration

The installed configuration is:

```text
/mnt/POOL/DATASET/TruePanel/truepanel.yaml
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

Do not upgrade an existing deployment by switching to `develop` and rerunning `install.sh` over the active tree.

TruePanel provides a guarded lifecycle manager for upgrades.

Begin by verifying the current installation:

```bash
truepanel verify --root /mnt/POOL/DATASET/TruePanel
```

Then preview the desired source tree:

```bash
python3 truepanel.py upgrade \
  --source ~/TruePanel \
  --root /mnt/POOL/DATASET/TruePanel \
  --dry-run
```

The full lifecycle supports validated staging, guarded promotion, automatic rollback after failed promotion verification, retained backup generations, explicit operator rollback, cleanup, and repair.

See [Upgrade and rollback](UPGRADING.md) for the complete procedure and required confirmation phrases.
## Manual verification

```bash
sudo /bin/python3 -m compileall -q /mnt/POOL/DATASET/TruePanel/truepanel
sudo /mnt/POOL/DATASET/TruePanel/bin/truepanel version
sudo /mnt/POOL/DATASET/TruePanel/bin/truepanel doctor
sudo /mnt/POOL/DATASET/TruePanel/bin/truepanel host readiness
sudo /mnt/POOL/DATASET/TruePanel/bin/truepanel host fan-safety \
  --config /mnt/POOL/DATASET/TruePanel/truepanel.yaml
sudo /mnt/POOL/DATASET/TruePanel/bin/truepanel host cutover-plan
systemctl is-active truepanel.service
sudo journalctl -u truepanel.service -n 80 --no-pager
```

On the TVS-671 reference system, also verify:

```bash
ls -l /dev/ttyS1 /dev/i2c-0
```

## Uninstall

```bash
cd ~/TruePanel
sudo bash uninstall.sh \
  --root /mnt/POOL/DATASET/TruePanel
```

The uninstaller stops the standalone Host Agent, primary LCD service, and Mission Control before cleanup. It refuses destructive cleanup while a managed service remains active or while the cross-process Host ownership lease is still held. After ownership is released, it runs the passive `host fan-safety` verifier and requires every configured controlled fan channel to be confirmed in motherboard Automatic mode before removing service files, runtime state, CLI wrappers, or the installation tree.

If fan restoration cannot be verified, uninstall fails closed and leaves the installation in place for diagnosis. Do not bypass that gate with manual file removal.

After a successful safety check, uninstall removes all three TruePanel service units, the Mission Control environment file, known `/run/truepanel` marker/lock/socket/status artifacts, both current and legacy CLI wrapper paths, reloads systemd, and deletes `/mnt/POOL/DATASET/TruePanel`. Local repository clones, external firmware archives, and Git history are not removed.

For the full clean-room uninstall/reinstall and reboot validation procedure, see [Clean-install validation](CLEAN_INSTALL_VALIDATION.md).

## Docker

Docker files remain available as an experimental deployment surface. Direct access to LCD, SMBus, GPIO, sysfs, SMART, and ZFS resources requires broad host permissions and may not behave like native deployment. Native installation is the reference path for physical front-panel hardware.

## Mission Control companion service

Mission Control runs as a separate systemd companion service. It does not replace or share the process of the primary LCD TruePanel service.

The installer places these files:

- `/etc/systemd/system/truepanel-mission-control.service`
- `/etc/default/truepanel-mission-control`
- `/mnt/POOL/DATASET/TruePanel/truepanel/web/`

The service is installed with conservative defaults:

```text
TRUEPANEL_MC_HOST=127.0.0.1
TRUEPANEL_MC_PORT=8787
TRUEPANEL_MC_CONFIG_PATH=/mnt/POOL/DATASET/TruePanel/truepanel.yaml
TRUEPANEL_MC_ALLOW_CONFIG_WRITES=false
```

Enable and start the companion service:

```bash
sudo systemctl enable --now truepanel-mission-control
```

Check its state:

```bash
sudo /mnt/POOL/DATASET/TruePanel/bin/truepanel mission-control status
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

Write mode permits validated Night Mode changes to `/mnt/POOL/DATASET/TruePanel/truepanel.yaml`. Each save uses atomic replacement and creates a timestamped backup. Mission Control does not automatically restart the primary TruePanel service after a save.

Keep write mode disabled unless remote configuration is specifically required. The web service never writes directly to the LCD serial interface, I2C devices, sysfs controls, or other hardware endpoints.

### Service separation

The two application services are independent:

```bash
sudo systemctl status truepanel.service
sudo systemctl status truepanel-mission-control.service
```

Restarting Mission Control does not restart the primary LCD service. Restarting the primary LCD service does not require restarting Mission Control. The separately installed `truepanel-host-agent.service` remains dormant while embedded Host ownership is in use.

## TVS-671 reference POSTINIT deployment

The current reference installation is stored at:

    /mnt/SSDs/Applications/TruePanel

TrueNAS starts the deployment with POSTINIT tasks rather
than persistent, hand-edited systemd unit files.

### Fintek hardware-monitor driver

The TVS-671 fan controller requires the `f71882fg`
kernel module. Create an enabled POSTINIT command:

    /sbin/modprobe f71882fg

Load it before the TruePanel startup script:

    /mnt/SSDs/Applications/TruePanel/start-truepanel.sh

Verify the driver:

    lsmod | grep '^f71882fg'
    modinfo f71882fg

Safe motherboard automatic-control values are:

    pwm1_enable = 2
    pwm2_enable = 2

A value of `2` indicates motherboard automatic control.

### Reference services

The POSTINIT script creates the two active application service units plus the dormant standalone Host Agent unit:

    truepanel.service
    truepanel-mission-control.service
    truepanel-host-agent.service

The standalone Host Agent unit remains marker-gated and inactive during the embedded reference deployment.

Confirm their active runtime paths:

    systemctl show truepanel.service \
      -p WorkingDirectory \
      -p ExecStart

    systemctl show truepanel-mission-control.service \
      -p WorkingDirectory \
      -p ExecStart

### Production verification

    systemctl is-active \
      truepanel.service \
      truepanel-mission-control.service

    curl -fsS \
      http://127.0.0.1:8787/api/v1/status \
      | python3 -m json.tool

A healthy reference contract includes:

    fans.available = true
    fans.control.connected = true
    fans.control.active_profile = automatic
    fans.control.control_authority = automatic
    fans.control.safety_hold = false
    thermal_control_readiness.armed = false
