# Security Policy

TruePanel controls physical NAS hardware and must treat security and hardware safety as one problem.

## Supported versions

| Version | Security support |
| --- | --- |
| 1.0.x | Supported |
| Earlier releases | Upgrade recommended |

## Reporting a vulnerability

Use the repository Security tab to submit a private GitHub security advisory.

Do not open a public issue for:

- credential exposure
- command injection
- unsafe privilege boundaries
- unauthorized hardware writes
- a method that bypasses a Project Stargate interlock
- a destructive storage or firmware path

Include the affected version, platform, reproduction steps, impact, and any proposed mitigation. Remove secrets, serial numbers, private addresses, and personal data from logs.

## Hardware safety

TruePanel intentionally avoids blind hardware discovery.

Security fixes must preserve these rules:

- Never perform generic I2C scans on production QNAP hardware.
- Never write to an undocumented address or register without model-specific evidence.
- Never perform destructive operations against storage devices.
- Never touch the TrueNAS boot device during hardware experiments.
- Stop `truepanel.service` before taking direct ownership of the A125 serial controller.
- Keep dangerous or stateful experiments behind explicit authorization and cooldown controls.
- Restore display, LED, and controller state after a laboratory operation.

## Privilege model

The production service requires access to system telemetry and selected hardware devices. Run only reviewed TruePanel code with elevated privileges. Plugins should be treated as trusted local code and reviewed before installation.

## Response process

Confirmed reports will be triaged, reproduced when safe, fixed on a private branch when necessary, covered by regression tests, and disclosed with the corresponding release.
