# TruePanel CLI Reference

The installed CLI wrapper is:

```text
/opt/truepanel/bin/truepanel
```

From a repository checkout, the equivalent launcher is:

```bash
python3 truepanel.py
```

Use `truepanel --help` and each command's `--help` output as the source of truth for the exact options supported by the current checkout.

## Runtime

```bash
truepanel run
```

Starts the production LCD runtime. The systemd service uses this command.

## Diagnostics

```bash
truepanel doctor
truepanel version
```

`doctor` checks the runtime environment and reports whether TruePanel is mission ready or degraded. `version` reports TruePanel, Python, system, and plugin information.

## Plugins

```bash
truepanel plugins
truepanel plugins --help
```

Plugin commands inspect installed extensions and their registered capabilities. Local plugin runtime state is intentionally excluded from Git.

## Themes

```bash
truepanel themes list
truepanel themes preview <theme>
truepanel themes set <theme>
```

Theme selection updates `theme_pack` in the configuration. Restart the service after changing the active theme.

## Simulation

```bash
truepanel simulate --help
```

Simulation runs collectors and scenarios without requiring the production LCD path. It is useful for dashboards, watcher behavior, plugins, and optional history recording.

## Hardware commands

```bash
truepanel hardware --help
```

The hardware command surface exposes registered inventory, topology, health, and controller operations through guarded handlers.

Use read-only commands before any active test. Model-specific controls must remain disabled on unverified hardware.

## Buzzer

The CLI includes a guarded buzzer test path. Use the available help output to list supported patterns.

## Project Stargate laboratory

```bash
truepanel lab --help
```

Project Stargate provides the controlled experimental command surface. Available command families include identity, status, board, version, buttons, display, repeatability, survey, planning, fingerprinting, capabilities, timing, and other cataloged experiments.

Important rules:

- stop `truepanel.service` before live serial experiments;
- prefer simulation first;
- use only cataloged operations;
- honor danger levels and authorization requirements;
- preserve capture logs outside Git;
- restore automatic display ownership after experiments.

## Examples

```bash
truepanel doctor
truepanel version
truepanel themes list
truepanel plugins
truepanel hardware --help
truepanel lab status
truepanel lab fingerprint --help
```

## Service logs

```bash
systemctl status truepanel
journalctl -u truepanel -n 80 --no-pager
journalctl -u truepanel -f
```

## Mission Control

Mission Control operator commands manage and inspect the web companion service.

```bash
truepanel mission-control
truepanel mission-control status
```

Both forms display:

- systemd load, enablement, and runtime state
- HTTP health
- configured bind address and port
- an operator-friendly dashboard URL
- read-only or guarded-write configuration mode

Available actions:

| Command | Purpose |
| --- | --- |
| `truepanel mission-control status` | Display service configuration and HTTP health |
| `truepanel mission-control start` | Start the companion service |
| `truepanel mission-control stop` | Stop the companion service |
| `truepanel mission-control restart` | Restart the companion service |
| `truepanel mission-control logs` | Follow the companion service journal |

Examples:

```bash
sudo truepanel mission-control restart
sudo truepanel mission-control logs
```

The status command does not load plugins, access LCD hardware, or modify configuration. Service-changing commands invoke systemd and may require root privileges.

When the configured bind address is `0.0.0.0`, status displays this friendly URL:

```text
http://<BattleStation-IP>:8787
```

Use the actual TrueNAS management address in a browser.
