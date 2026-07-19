# Project Stargate

Project Stargate is TruePanel's guarded hardware research program. It exists because appliance front panels often expose undocumented serial, SMBus, GPIO, Super I/O, ACPI, and firmware-controlled interfaces.

The laboratory converts uncertain observations into reproducible evidence before any command enters the production hardware layer.

## Principles

1. Observe before writing.
2. Simulate before going live.
3. Use exact command catalogs.
4. Separate safe, caution, and dangerous operations.
5. Require explicit authorization for stateful experiments.
6. Capture bytes, timing, state, and restoration.
7. Stop the production service before claiming shared hardware.
8. Promote only reproducible findings.

## A125 laboratory

The A125 laboratory supports:

- service lock checks
- board identity
- protocol version
- button state
- raw capture
- repeatability studies
- response classification
- opcode safety policy
- survey planning
- fingerprints
- capability providers
- clear, row, and frame timing
- ROM graphics
- CGRAM glyph experiments
- session and execution records

The reference controller has shown stable query latency near 50 ms. Display operations are slower and are characterized separately.

## Safety architecture

### Execution modes

- simulation
- live

### Danger levels

- safe
- caution
- dangerous

### Interlocks

Live execution is catalog-bound. Stateful experiments can require an exact authorization phrase. Cooldowns prevent dense command bursts. Exclusive ownership prevents the service and laboratory from using the serial controller simultaneously.

### Response ownership

Commands that produce replies must consume their own frames. This prevents delayed responses from contaminating later queries. A125 automatic display ownership is explicitly claimed and restored around laboratory sessions.

## Firmware archaeology

Reusable tools under `development/tools/` inspect:

- model profiles
- firmware image signatures
- HAL and LED references
- ACPI and embedded-controller paths
- AHCI and SGPIO behavior
- Fintek Super I/O registers
- QNAP drive LED command maps

Extracted firmware, compiled tools, logs, and captures are excluded from Git and stored externally.

## Graduation to production

A finding graduates when:

- the command is exact;
- the hardware target is known;
- physical behavior is repeatable;
- off or restoration behavior is known;
- unrelated hardware is not affected;
- tests protect the implementation;
- documentation records the boundary.

The TVS-671 bay identify LED map followed this process and now powers production storage fault indication.

## Related documents

- [A125 protocol](A125_PROTOCOL.md)
- [Stargate discoveries](STARGATE_DISCOVERIES.md)
- [Hardware support](HARDWARE.md)
- [`development/tools/README.md`](../development/tools/README.md)
