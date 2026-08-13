# Upgrading TruePanel

TruePanel provides a guarded lifecycle workflow for verifying, staging, promoting, cleaning up, repairing, and rolling back an installation.

The examples below use `/mnt/POOL/DATASET/TruePanel` for a native installation. Use the deployed root appropriate for your system.

## Lifecycle overview

The recommended sequence is:

1. verify the current deployment;
2. preview the upgrade;
3. create and validate a staging tree;
4. promote that validated stage with explicit confirmation;
5. verify the deployed result;
6. retain rollback backups until the upgrade has proven stable;
7. clean completed upgrade assets only when they are no longer needed.

Promotion and rollback are guarded operations. Do not bypass their confirmation phrases or manually replace the deployment tree while a lifecycle operation is in progress.

## 1. Verify the current deployment

```bash
truepanel verify --root /mnt/POOL/DATASET/TruePanel
```

`verify` inspects the installed lifecycle contract without modifying files, services, configuration, or hardware state.

Resolve verification failures before beginning an upgrade.

## 2. Prepare the desired source checkout

Use a clean repository checkout containing the release or commit you intend to deploy.

```bash
cd ~/TruePanel
git status --short
git fetch --tags
```

Select the desired release or commit using the normal Git workflow for your environment. The lifecycle manager treats the selected checkout as the upgrade source.

## 3. Preview the upgrade

```bash
python3 truepanel.py upgrade \
  --source ~/TruePanel \
  --root /mnt/POOL/DATASET/TruePanel \
  --dry-run
```

`--dry-run` shows the upgrade plan without writing deployment files.

Review the plan before creating a stage.

## 4. Create and validate a staging tree

Choose an explicit staging path so the same validated stage can be selected for promotion:

```bash
python3 truepanel.py upgrade \
  --source ~/TruePanel \
  --root /mnt/POOL/DATASET/TruePanel \
  --stage-root <stage-root> \
  --stage-only
```

`--stage-only` creates and validates the staging tree without replacing the active deployment.

Do not promote a stage that did not complete validation successfully.

## 5. Promote the validated stage

Promotion requires the exact confirmation phrase `PROMOTE_TRUEPANEL`.

The explicit `--backup-root` must be a sibling of the deployment root, its basename must begin with `.truepanel-backup-`, and the path must not already exist. For the example deployment, a valid path is `/mnt/POOL/DATASET/.truepanel-backup-TruePanel-before-v1.2.0-rc1`. TruePanel validates this backup location before any deployment files are copied.

```bash
python3 truepanel.py upgrade \
  --root /mnt/POOL/DATASET/TruePanel \
  --stage-root <stage-root> \
  --backup-root /mnt/POOL/DATASET/.truepanel-backup-TruePanel-before-v1.2.0-rc1 \
  --promote \
  --confirm PROMOTE_TRUEPANEL
```

Promotion creates a deployment backup, installs the validated stage, restarts the required runtime, and verifies the promoted deployment.

Installer-owned `bin/` artifacts, including `bin/truepanel`, are preserved during stage-to-deployment synchronization. Backup creation and rollback continue to copy these artifacts so a retained generation can restore the managed wrapper.

Lifecycle verification runs with the deployed generation's own `.venv/bin/python` and `truepanel.py`. Only transient Mission Control or LCD readiness failures are retried after a restart; other verification failures return immediately.

If promotion verification fails, TruePanel automatically attempts to restore the pre-upgrade deployment and verifies that rollback before returning control to the operator.

An automatic rollback during failed promotion is not the same operation as an operator-requested rollback described later in this guide.

## 6. Verify after promotion

```bash
truepanel verify --root /mnt/POOL/DATASET/TruePanel
truepanel version
truepanel doctor
systemctl is-active truepanel
systemctl is-active truepanel-mission-control
```

Also confirm normal LCD rotation, telemetry, Mission Control, and button behavior appropriate for the commissioned hardware.

Never use a successful software upgrade as evidence that previously uncommissioned hardware controls are now safe to actuate.

## Upgrade cleanup

Cleanup is deliberately separate from promotion so rollback generations remain available while an upgrade is being evaluated.

First preview the cleanup plan:

```bash
python3 truepanel.py upgrade \
  --root /mnt/POOL/DATASET/TruePanel \
  --cleanup
```

Without a confirmation phrase, cleanup reports the plan and does not remove eligible assets.

When the plan has been reviewed, execute cleanup with:

```bash
python3 truepanel.py upgrade \
  --root /mnt/POOL/DATASET/TruePanel \
  --cleanup \
  --confirm CLEAN_TRUEPANEL
```

Cleanup removes eligible completed staging assets and older or duplicate backup generations according to the retention policy. It preserves the active deployment and retained recovery generations and does not restart services.

Do not manually delete retained backups merely to make the directory look tidy. Those backups are part of the recovery system.

## Operator-requested rollback

Operator rollback restores an explicitly selected retained backup. It requires the exact confirmation phrase `ROLLBACK_TRUEPANEL`.

```bash
python3 truepanel.py upgrade \
  --root /mnt/POOL/DATASET/TruePanel \
  --backup-root <retained-backup-root> \
  --rollback \
  --confirm ROLLBACK_TRUEPANEL
```

Before replacing the current deployment, TruePanel creates a separate pre-rollback safety backup.

After restoring the selected generation, TruePanel verifies the result. If rollback verification fails, it attempts to restore and verify the pre-rollback state instead.

A rollback therefore has two recovery layers:

- the retained generation selected by the operator;
- the pre-rollback safety copy of the deployment being replaced.

The selected backup must be an explicit valid retained backup. TruePanel does not guess which historical generation the operator intended.

## Repair

`repair` is for lifecycle drift or damaged deployment plumbing. It is not an upgrade mechanism and does not select a different TruePanel release.

Preview repairs first:

```bash
truepanel repair \
  --root /mnt/POOL/DATASET/TruePanel \
  --dry-run
```

If the proposed repairs are appropriate:

```bash
truepanel repair --root /mnt/POOL/DATASET/TruePanel
```

Run verification again after repair:

```bash
truepanel verify --root /mnt/POOL/DATASET/TruePanel
```

## Configuration preservation

Treat the deployed `truepanel.yaml` and Mission Control environment as operator-owned state. Preserve the primary LCD service configuration and review release changes before adopting new configuration options.

Important deployment-specific files may include:

- `/mnt/POOL/DATASET/TruePanel/truepanel.yaml`
- `/etc/default/truepanel-mission-control`

Do not copy extracted firmware, laboratory captures, Python caches, compiled probes, or development artifacts into the production tree.

## Hardware verification after an upgrade

After lifecycle verification passes, confirm the hardware behaviors that were already commissioned for that machine.

On systems with a physical front panel, verify normal display rotation and button behavior before running any direct laboratory operation.

Never run an A125 laboratory command while `truepanel.service` owns the serial controller.

## Recovery principle

The lifecycle manager follows one rule throughout the upgrade path:

**preserve a known recovery path before replacing the state that is currently working.**
