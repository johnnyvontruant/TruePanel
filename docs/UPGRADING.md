# Upgrading TruePanel

This guide covers upgrades for the native TrueNAS SCALE installation under `/opt/truepanel`.

## Before upgrading

Record the current release and service state:

```bash
/opt/truepanel/bin/truepanel version
systemctl status truepanel --no-pager
```

Back up the active configuration:

```bash
cp /opt/truepanel/truepanel.yaml   /root/truepanel.yaml.before-upgrade
```

Keep a repository checkpoint or release tag available for rollback.

## Upgrade from Git

From a clean checkout of the desired release:

```bash
git fetch --tags
git switch --detach v1.0.0
bash install.sh
```

The installer synchronizes the application into `/opt/truepanel`, preserves an existing `/opt/truepanel/truepanel.yaml`, creates the CLI wrapper, refreshes the systemd unit, and runs TruePanel Doctor.

Restart and verify:

```bash
systemctl restart truepanel
systemctl is-active truepanel
/opt/truepanel/bin/truepanel version
/opt/truepanel/bin/truepanel doctor
journalctl -u truepanel -n 100 --no-pager
```

## Configuration review

Compare new configuration options in the release checkout with the active `/opt/truepanel/truepanel.yaml`. The installer does not overwrite an existing configuration.

Pay particular attention to:

- serial port and baud rate
- Flight Deck timing
- night mode
- history storage
- plugins
- buzzer behavior
- storage-health thresholds
- bay LED enablement and startup clearing

## Rollback

Check out the previous known-good tag and reinstall:

```bash
git switch --detach v0.9.0
bash install.sh
systemctl restart truepanel
```

Restore the saved configuration only when the previous release cannot understand the current configuration.

## Hardware verification

After an upgrade, confirm normal LCD rotation and button behavior before running direct laboratory commands. Bay LEDs should be clear unless an active storage condition requests identification.

Never run an A125 laboratory command while `truepanel.service` owns the serial controller.
