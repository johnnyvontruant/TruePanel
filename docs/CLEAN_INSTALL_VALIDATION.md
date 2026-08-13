# TruePanel Clean-Install Validation Runbook

## Purpose

This runbook is the graduation test for the native TruePanel lifecycle. It validates a clean uninstall, a fresh installation from a known `main` commit, first boot, runtime health, and reboot recovery without relying on private operator knowledge or hand edits inside the installed tree.

If any step fails, stop at that step. Capture the command output and relevant logs, fix the repository or documentation, run CI, and repeat the documented procedure. Do not repair the installed tree by hand to make the test pass.

The standalone Host Agent remains activation-locked throughout this validation. Do not create `/run/truepanel/standalone-host-agent.enabled` during this runbook.

Examples use:

```text
/mnt/POOL/DATASET/TruePanel
```

Replace that path with the actual persistent installation root.

## Safety invariants

The validation must preserve all of these conditions:

- only one process may own the privileged Host hardware boundary;
- the standalone Host Agent remains dormant and activation-locked;
- the standalone cutover marker remains absent;
- uninstall must stop all TruePanel services and release Host ownership before runtime cleanup;
- destructive uninstall cleanup must not begin until `host fan-safety` confirms motherboard Automatic mode for every configured fan-control channel;
- no manual sysfs fan writes are part of this procedure;
- no manual edits are made inside the installed TruePanel tree.

## Phase 0: Prepare an external source checkout

The source checkout used for reinstall must live outside the installation root because uninstall deletes the installed tree.

From that external checkout:

```bash
git status --short
git branch --show-current
git rev-parse HEAD
```

For the graduation run, use a clean checkout of the intended `main` commit. Record the commit SHA with the test results.

## Phase 1: Capture the known-good baseline

From the currently installed TruePanel tree:

```bash
cd /mnt/POOL/DATASET/TruePanel
sudo ./bin/truepanel verify \
  --root /mnt/POOL/DATASET/TruePanel
sudo ./bin/truepanel compatibility
sudo ./bin/truepanel host readiness
sudo ./bin/truepanel host fan-safety \
  --config /mnt/POOL/DATASET/TruePanel/truepanel.yaml
sudo ./bin/truepanel host cutover-plan
```

Record service state and recent logs:

```bash
sudo systemctl status truepanel.service --no-pager
sudo systemctl status truepanel-mission-control.service --no-pager
sudo systemctl status truepanel-host-agent.service --no-pager
sudo journalctl -u truepanel.service -n 80 --no-pager
sudo journalctl -u truepanel-mission-control.service -n 80 --no-pager
```

Expected Host boundary before cutover work is enabled:

- the primary LCD service may own the embedded Host runtime;
- Mission Control may be active independently;
- `truepanel-host-agent.service` is dormant;
- `/run/truepanel/standalone-host-agent.enabled` is absent;
- `host readiness` reports standalone activation locked;
- `host fan-safety` reports motherboard fan control `AUTOMATIC` when configured fan control is enabled.

Capture the runtime footprint for comparison:

```bash
if [ -d /run/truepanel ]; then
  sudo find /run/truepanel \
    -mindepth 1 \
    -maxdepth 1 \
    -printf '%f\n' \
    | sort
fi
```

Optional but recommended before destructive testing:

```bash
python3 truepanel.py compatibility \
  --support-bundle \
  --output truepanel-pre-clean-install.json
```

## Phase 2: Clean uninstall

Run uninstall from the external source checkout, not from the installed tree:

```bash
sudo bash uninstall.sh \
  --root /mnt/POOL/DATASET/TruePanel
```

The uninstaller must stop all potential TruePanel owners, prove the Host ownership lease is free, and run the passive fan-safety verifier before destructive cleanup.

If uninstall reports that motherboard Automatic mode cannot be confirmed, stop. Do not delete service files, runtime files, or the install tree manually. Preserve the remaining installation for diagnosis.

## Phase 3: Prove known residue is gone

After a successful uninstall, verify the installed tree and known integration artifacts are absent:

```bash
test ! -e /mnt/POOL/DATASET/TruePanel
test ! -e /etc/systemd/system/truepanel.service
test ! -e /etc/systemd/system/truepanel-mission-control.service
test ! -e /etc/systemd/system/truepanel-host-agent.service
test ! -e /etc/default/truepanel-mission-control
test ! -e /run/truepanel/standalone-host-agent.enabled
test ! -e /run/truepanel/host-owner.lock
test ! -e /run/truepanel/fan-control.sock
test ! -e /run/truepanel/fan-control-status.json
test ! -e /run/truepanel/lcd-command.sock
test ! -e /run/truepanel/lcd-reader-status.json
test ! -e /run/truepanel/lcd-display-status.json
```

The `/run/truepanel` directory itself is removed only when empty. If it remains, inspect it rather than deleting unknown contents blindly:

```bash
if [ -d /run/truepanel ]; then
  sudo find /run/truepanel \
    -mindepth 1 \
    -maxdepth 1 \
    -printf '%f\n' \
    | sort
fi
```

Reloaded systemd should no longer have TruePanel unit files to display:

```bash
sudo systemctl daemon-reload
sudo systemctl cat truepanel.service || true
sudo systemctl cat truepanel-mission-control.service || true
sudo systemctl cat truepanel-host-agent.service || true
```

## Phase 4: Fresh install from the recorded main commit

From the clean external source checkout:

```bash
git status --short
git rev-parse HEAD
python3 truepanel.py compatibility
sudo bash install.sh \
  --root /mnt/POOL/DATASET/TruePanel
```

A successful fresh install lays down:

- the persistent TruePanel tree and installed CLI wrapper;
- `truepanel.service`;
- `truepanel-mission-control.service` and its environment file;
- the dormant, marker-gated `truepanel-host-agent.service`.

The installer does not start the primary LCD service, Mission Control, or the standalone Host Agent. Start only the two application services explicitly:

```bash
sudo systemctl enable --now truepanel.service
sudo systemctl enable --now truepanel-mission-control.service
```

Do not enable or start `truepanel-host-agent.service` during this validation.

## Phase 5: Immediate post-install verification

Run the installed lifecycle and Host checks:

```bash
cd /mnt/POOL/DATASET/TruePanel
sudo ./bin/truepanel verify \
  --root /mnt/POOL/DATASET/TruePanel
sudo ./bin/truepanel compatibility
sudo ./bin/truepanel host readiness
sudo ./bin/truepanel host fan-safety \
  --config /mnt/POOL/DATASET/TruePanel/truepanel.yaml
sudo ./bin/truepanel host cutover-plan
```

Verify service state:

```bash
sudo systemctl is-active truepanel.service
sudo systemctl is-active truepanel-mission-control.service
sudo systemctl is-active truepanel-host-agent.service || true
sudo systemctl cat truepanel-host-agent.service
```

Expected results:

- `truepanel.service` is active;
- `truepanel-mission-control.service` is active after the explicit start above;
- `truepanel-host-agent.service` remains inactive;
- the Host Agent unit contains `ConditionPathExists=/run/truepanel/standalone-host-agent.enabled`;
- the Host Agent unit has no `[Install]` section;
- the standalone cutover marker is absent;
- `host readiness` reports the dormant deployment prepared safely and standalone activation locked;
- `host fan-safety` confirms motherboard Automatic mode when fan control is enabled;
- `host cutover-plan` reports `Cutover execution: DISABLED`.

Verify the marker directly:

```bash
test ! -e /run/truepanel/standalone-host-agent.enabled
```

## Phase 6: Functional application checks

### LCD

Confirm on physical hardware:

- the startup display completes normally;
- page rotation works;
- front-panel buttons respond;
- fan telemetry pages render expected RPM/status data;
- shutdown/restart does not leave stale LCD command or status behavior.

Review the service log for unexpected hardware or ownership errors:

```bash
sudo journalctl -u truepanel.service -n 120 --no-pager
```

### Mission Control

Verify the local status API:

```bash
curl -fsS \
  http://127.0.0.1:8787/api/v1/status \
  | python3 -m json.tool
```

Confirm the dashboard presents current telemetry and that guarded fan/thermal state agrees with the LCD and CLI observations.

### Fan restoration

After any approved bounded manual fan-control commissioning test, return to Automatic and re-run:

```bash
sudo ./bin/truepanel host fan-safety \
  --config /mnt/POOL/DATASET/TruePanel/truepanel.yaml
```

Do not continue to reboot validation unless this reports motherboard fan control `AUTOMATIC`.

## Phase 7: Reboot validation

Before reboot, confirm the standalone marker is still absent:

```bash
test ! -e /run/truepanel/standalone-host-agent.enabled
```

Reboot the NAS using the normal TrueNAS administrative mechanism. After the system returns, repeat:

```bash
sudo systemctl is-active truepanel.service
sudo systemctl is-active truepanel-mission-control.service
sudo systemctl is-active truepanel-host-agent.service || true

cd /mnt/POOL/DATASET/TruePanel
sudo ./bin/truepanel verify \
  --root /mnt/POOL/DATASET/TruePanel
sudo ./bin/truepanel host readiness
sudo ./bin/truepanel host fan-safety \
  --config /mnt/POOL/DATASET/TruePanel/truepanel.yaml

test ! -e /run/truepanel/standalone-host-agent.enabled
```

Also re-check the physical LCD, front-panel buttons, Mission Control status API, and recent service logs.

The standalone Host Agent must still be dormant after reboot.

## Phase 8: Record the result

Record at least:

- TrueNAS version;
- TruePanel `main` commit SHA;
- installation root;
- compatibility classification;
- `verify` result;
- Host readiness result;
- fan-safety result;
- primary and Mission Control service state before and after reboot;
- standalone Host Agent state before and after reboot;
- LCD/button result;
- Mission Control API result;
- any warnings or deviations.

A clean-install validation is complete only when the documented procedure works without manual edits to the installed tree and all safety gates pass.

## Failure rule

A failure is useful evidence, not a reason to bypass the lifecycle.

Do not patch the installed deployment by hand to finish the checklist. Capture the failure, correct the repository or documentation, run the normal CI suite, and repeat the affected lifecycle from a known state. That is how the clean-install drill proves TruePanel is installable by somebody who does not already know its internal history.
