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

Choose a persistent validation-artifact directory **outside** the TruePanel installation root. It must survive uninstall and reboot. For example:

```bash
export TRUEPANEL_VALIDATION_ARTIFACTS=/mnt/POOL/DATASET/TruePanel-clean-install-artifacts
sudo mkdir -p "$TRUEPANEL_VALIDATION_ARTIFACTS"
```

Do not place this directory inside `/mnt/POOL/DATASET/TruePanel`; uninstall intentionally deletes that tree.

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

Before any destructive step, preserve the working configuration outside the installation root. These copies are recovery evidence only. **Do not restore them during the fresh-install acceptance phases**, because doing so would hide installer or default-configuration defects.

```bash
test -n "${TRUEPANEL_VALIDATION_ARTIFACTS:-}"
test "$TRUEPANEL_VALIDATION_ARTIFACTS" != /mnt/POOL/DATASET/TruePanel

sudo cp -a \
  /mnt/POOL/DATASET/TruePanel/truepanel.yaml \
  "$TRUEPANEL_VALIDATION_ARTIFACTS/truepanel.yaml.before-clean-install"

if [ -f /etc/default/truepanel-mission-control ]; then
  sudo cp -a \
    /etc/default/truepanel-mission-control \
    "$TRUEPANEL_VALIDATION_ARTIFACTS/truepanel-mission-control.env.before-clean-install"
fi
```

Confirm the preserved configuration exists before continuing:

```bash
sudo test -f \
  "$TRUEPANEL_VALIDATION_ARTIFACTS/truepanel.yaml.before-clean-install"
```

If the clean-install test later exposes a defect, stop and fix the repository or documentation first. Use the preserved files only when deliberately returning the NAS to its previous known-good configuration after diagnosis; never copy them into the fresh installation merely to make acceptance pass.

From the currently installed TruePanel tree:

```bash
cd /mnt/POOL/DATASET/TruePanel
sudo ./bin/truepanel verify \
  --root /mnt/POOL/DATASET/TruePanel
sudo ./bin/truepanel compatibility
sudo ./bin/truepanel host readiness
sudo ./bin/truepanel host fan-safety \
  --config /mnt/POOL/DATASET/TruePanel/truepanel.yaml
sudo ./bin/truepanel host acceptance \
  --root / \
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

Capture a privacy-safe compatibility support bundle outside the installation root so the baseline survives uninstall:

```bash
sudo ./bin/truepanel compatibility \
  --support-bundle \
  --output \
  "$TRUEPANEL_VALIDATION_ARTIFACTS/truepanel-pre-clean-install.json"

sudo test -f \
  "$TRUEPANEL_VALIDATION_ARTIFACTS/truepanel-pre-clean-install.json"
```

## Phase 2: Clean uninstall

Run the uninstall preview first from the external source checkout, not from the installed tree:

```bash
bash uninstall.sh \
  --dry-run \
  --root /mnt/POOL/DATASET/TruePanel
```

Inspect the complete plan and confirm the install root, services, Host ownership gate, fan Automatic verification gate, runtime files, and install tree are the intended targets. The preview must report that no services were stopped, no fan state changed, and no files were removed.

Then run the real uninstall with the same root:

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

TruePanel historical telemetry and control-event history are durable user data under `/var/lib/truepanel`; uninstall intentionally does not delete them. For this graduation test, quarantine that durable state rather than destroying it so the fresh install starts with no inherited TruePanel history:

```bash
if [ -e /var/lib/truepanel ]; then
  test ! -e \
    "$TRUEPANEL_VALIDATION_ARTIFACTS/var-lib-truepanel.before-clean-install"
  sudo mv \
    /var/lib/truepanel \
    "$TRUEPANEL_VALIDATION_ARTIFACTS/var-lib-truepanel.before-clean-install"
fi

test ! -e /var/lib/truepanel
```

Do not delete the quarantined history and do not restore it during fresh-install acceptance. The newly installed runtime may create a new `/var/lib/truepanel` as it records fresh telemetry. Keep the old history with the validation artifacts until the graduation result has been reviewed and a deliberate retention/restore decision is made.

## Phase 4: Fresh install from the recorded main commit

From the clean external source checkout, rehearse the install before writing anything:

```bash
git status --short
git rev-parse HEAD
python3 truepanel.py compatibility
bash install.sh \
  --dry-run \
  --root /mnt/POOL/DATASET/TruePanel
```

Inspect the plan and confirm the source tree, persistent install root, configuration behavior, Python runtime setup, CLI wrapper, all three service units, Mission Control environment, systemd reload, and Doctor step are expected. The preview must report that no directories were created, no files were copied or written, no dependencies were installed, and no services were changed.

For a genuinely fresh target, the installer must **not** import `truepanel.yaml`, `.env`, virtual environments, caches, local history, or plugin state from the source checkout. Source-local state is excluded from synchronization. Because Phase 3 proved the target config is absent, the installer must create its generic safe `truepanel.yaml` rather than copying machine-specific source configuration.

Then run the real installer with the same root:

```bash
sudo bash install.sh \
  --root /mnt/POOL/DATASET/TruePanel
```


The canonical successful installer banner is exactly
`TruePanel Install Complete`. Validation harnesses should match that
literal wording.

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

The native `truepanel verify` command is an **operational verifier**.
It expects the LCD service and Mission Control to be active, the
Mission Control API to respond, and LCD transport to be healthy.

Run it only after the explicit application-service activation commands
in Phase 4. Running it while those services are intentionally dormant
is expected to report failures.

Run the installed lifecycle and Host checks:

```bash
cd /mnt/POOL/DATASET/TruePanel
sudo ./bin/truepanel verify \
  --root /mnt/POOL/DATASET/TruePanel
sudo ./bin/truepanel compatibility
sudo ./bin/truepanel host readiness
sudo ./bin/truepanel host fan-safety \
  --config /mnt/POOL/DATASET/TruePanel/truepanel.yaml
sudo ./bin/truepanel host acceptance \
  --root / \
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
- `host acceptance` reports `Host acceptance: PASS`;
- `host cutover-plan` reports `Cutover execution: DISABLED`.

Verify the marker directly:

```bash
test ! -e /run/truepanel/standalone-host-agent.enabled
```

Capture the fresh-install compatibility state beside the preserved baseline:

```bash
sudo ./bin/truepanel compatibility \
  --support-bundle \
  --output \
  "$TRUEPANEL_VALIDATION_ARTIFACTS/truepanel-post-clean-install.json"

sudo test -f \
  "$TRUEPANEL_VALIDATION_ARTIFACTS/truepanel-post-clean-install.json"
```

Keep both support bundles with the recorded `main` SHA and validation notes. Do not place either bundle inside the managed TruePanel tree.

## Phase 6: Functional application checks

### LCD

Confirm on physical hardware:

- the startup display completes normally;
- page rotation works;
- front-panel buttons respond;
- fan telemetry pages render expected RPM/status data;
- shutdown/restart does not leave stale LCD command or status behavior.

When reading `/run/truepanel/lcd-reader-status.json`, reader fields are
nested beneath the `reader` mapping. For example,
`payload["reader"]["connected"]` and
`payload["reader"]["button_reports"]` are valid reader-state paths.

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
sudo ./bin/truepanel host acceptance \
  --root / \
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
sudo ./bin/truepanel host acceptance \
  --root / \
  --config /mnt/POOL/DATASET/TruePanel/truepanel.yaml

test ! -e /run/truepanel/standalone-host-agent.enabled
```

Post-reboot `host acceptance` must report `Host acceptance: PASS`. Also re-check the physical LCD, front-panel buttons, Mission Control status API, and recent service logs.

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
- Host acceptance result;
- primary and Mission Control service state before and after reboot;
- standalone Host Agent state before and after reboot;
- LCD/button result;
- Mission Control API result;
- any warnings or deviations.

A clean-install validation is complete only when the documented procedure works without manual edits to the installed tree and all safety gates pass.

## Failure rule

A failure is useful evidence, not a reason to bypass the lifecycle.

Do not patch the installed deployment by hand to finish the checklist. Capture the failure, correct the repository or documentation, run the normal CI suite, and repeat the affected lifecycle from a known state. That is how the clean-install drill proves TruePanel is installable by somebody who does not already know its internal history.
