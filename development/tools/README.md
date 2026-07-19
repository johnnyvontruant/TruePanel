# Project Stargate Laboratory Tools

This directory contains the reusable hardware-discovery and reverse-engineering tools developed while building TruePanel.

These tools are not part of the normal TruePanel service. They exist to reproduce verified discoveries, investigate additional QNAP models, and preserve the methodology behind the production hardware layer.

## Safety model

- Stop `truepanel.service` before accessing the A125 serial controller.
- Never perform generic I2C scans on production QNAP hardware.
- Use only documented SMBus addresses and commands.
- Do not write to storage devices or the TrueNAS boot device.
- Treat firmware images as external laboratory inputs. Extracted firmware is intentionally excluded from Git.
- Compile C probes locally. Compiled binaries are intentionally excluded from Git.
- Prefer passive observation before active writes.
- Use the smallest possible command surface and restore hardware state after every experiment.

## Tool groups

### Firmware archaeology

Tools beginning with `qnap_`, along with the ACPI extraction utilities, inspect firmware packages, model profiles, binaries, scripts, and hardware-control call paths.

Firmware packages and extracted files belong under the ignored `development/firmware/` directory or in an external archive.

### A125 and front-panel discovery

The production A125 protocol implementation lives under `truepanel/hardware/` and `truepanel/lab/`.

Standalone development probes remain here only when they provide reproducible hardware characterization that is not already available through the guarded `truepanel lab` command surface.

### Status and drive LEDs

The F71869, AHCI, SGPIO, embedded-controller, and QNAP tracing tools document the path that led to verified TVS-671 status and bay LED control.

The production bay LED implementation is:

- `truepanel/hardware/bay_leds.py`
- `truepanel/mission_control/storage_bay_indicator.py`

### GPIO observation

`gpio_input_watch.sh` and `gpio_passive_map.sh` perform passive GPIO observation. Captured output is not committed and should be stored with other laboratory evidence.

## Build artifacts

Compiled executables, object files, logs, captures, extracted firmware, and timestamped backups are excluded through `.gitignore`.

## Verified TVS-671 findings

- A125 serial controller: `/dev/ttyS1` at 1200 baud
- Host command preamble: `0x4D`
- Drive identify controller: `/dev/i2c-0`, SMBus address `0x33`
- Bay identify commands:
  - Bay 1: on `0x02`, off `0x03`
  - Bay 2: on `0x04`, off `0x05`
  - Bay 3: on `0x06`, off `0x07`
  - Bay 4: on `0x08`, off `0x09`
  - Bay 5: on `0x0A`, off `0x0B`
  - Bay 6: on `0x0C`, off `0x0D`

See `docs/A125_PROTOCOL.md` and `docs/STARGATE_DISCOVERIES.md` for durable findings.
