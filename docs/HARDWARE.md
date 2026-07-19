# TruePanel Hardware Support

## Support levels

### Verified

A hardware path is verified when the command or observation has been reproduced on physical hardware, its state restoration is understood, and automated tests protect the production implementation.

### Experimental

A path is experimental when evidence exists but has not completed the full verification process.

### Unsupported

A path is unsupported when it depends on guessing, generic scanning, random writes, destructive probing, or unverified model assumptions.

## Reference system

### QNAP TVS-671

- Operating system: TrueNAS SCALE
- LCD controller family: A125
- Serial device: `/dev/ttyS1`
- Baud rate: 1200
- Host preamble: `0x4D`
- Drive bays: six
- Bay identify controller: Intel I801 SMBus
- SMBus device: `/dev/i2c-0`
- SMBus address: `0x33`

## A125 front panel

Verified capabilities include:

- text writes
- clear
- backlight
- automatic display ownership
- button query and monitoring
- board identity query
- protocol version query
- native ROM graphics
- custom CGRAM glyphs
- repeatability and timing experiments

See [A125 protocol](A125_PROTOCOL.md).

## Drive-bay identify LEDs

The TVS-671 uses SMBus Write Byte commands with no additional data payload.

| Bay | Identify on | Identify off |
|---:|---:|---:|
| 1 | `0x02` | `0x03` |
| 2 | `0x04` | `0x05` |
| 3 | `0x06` | `0x07` |
| 4 | `0x08` | `0x09` |
| 5 | `0x0A` | `0x0B` |
| 6 | `0x0C` | `0x0D` |

Production implementation:

```text
truepanel/hardware/bay_leds.py
truepanel/mission_control/storage_bay_indicator.py
```

The LEDs are used as fault locators, while the LCD storage page provides the detailed reason.

Do not generic-scan the SMBus. Address `0x4E` is associated with power-supply control on the investigated platform and must not be probed casually.

## Chassis status LEDs

Firmware research identified TVS-671 status LED control through the Fintek F71869 Super I/O path. Reproducible C probes are retained under `development/tools/`.

Production use should remain constrained to exact verified register maps and restored states.

## Storage devices

TruePanel reads SMART, temperature, inventory, topology, and enclosure information. It does not write to storage devices.

On the reference system, `/dev/sdf` is the TrueNAS boot module and must never be mounted, formatted, or destructively probed by laboratory tooling.

## Buzzer

The buzzer is exposed through the hardware abstraction layer and can be tested through guarded CLI commands. Audible alerts remain separate from bay identify LEDs and LCD routing.

## Fans and thermal paths

TruePanel reads fan, PWM, and thermal data through sysfs and hwmon providers. Hardware paths differ across kernels and models, so hard-coded control writes are not portable.

## Adding another model

A new model should progress through:

1. passive inventory;
2. firmware profile research;
3. simulation;
4. read-only hardware queries;
5. repeatability captures;
6. exact command-map verification;
7. state restoration tests;
8. production abstraction;
9. automated tests;
10. documentation.

Never assume two QNAP models share identical serial ports, SMBus addresses, bay maps, Super I/O registers, or GPIO polarity.
