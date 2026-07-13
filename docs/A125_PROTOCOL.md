# A125 Serial Protocol

**Project:** TruePanel Project Stargate  
**Status:** Living engineering reference  
**Transport:** Serial  
**Known BattleStation settings:** `/dev/ttyS1`, 1200 baud

## Scope

This document describes the verified host-to-controller commands and
controller-to-host responses used by TruePanel's QNAP A125 front-panel board.

Unknown or undocumented commands must not be sent to production hardware
without a reviewed probe plan.

## Packet direction

Host packets begin with `4D`.

Observed controller replies begin with `53` or `83`.

## Verified commands

| Command | Name | Packet | Status |
|---|---|---|---|
| `0x00` | Get board ID | `4D 00` | Verified in driver |
| `0x06` | Get buttons | `4D 06` | Verified in driver |
| `0x07` | Get protocol version | `4D 07` | Verified in driver |
| `0x0C` | Display write | `4D 0C ROW LENGTH DATA...` | Verified |
| `0x0D` | Clear display | `4D 0D` | Verified |
| `0x5E` | Backlight | `4D 5E STATE` | Verified |
| `0xFF` | Reset | `4D FF` | Verified |

## Display write

Packet:

`4D 0C ROW LENGTH DATA...`

| Field | Size | Meaning |
|---|---:|---|
| Preamble | 1 byte | `0x4D` |
| Command | 1 byte | `0x0C` |
| Row | 1 byte | `0x00` first row, `0x01` second row |
| Length | 1 byte | Number of following character bytes |
| Data | 0–16 bytes | Raw LCD character bytes |

TruePanel supports raw display bytes. Text is encoded with a single-byte
encoding so it does not expand into UTF-8 sequences.

## Backlight

`4D 5E 01` enables the backlight.

`4D 5E 00` disables the backlight.

## Verified responses

| Response | Name | Payload | Status |
|---|---|---:|---|
| `0x01` | Board ID | 2 bytes | Verified in driver |
| `0x05` | Button status | 2 bytes | Verified in driver |
| `0x08` | Protocol version | 2 bytes | Verified in driver |
| `0xAA` | Reset complete | none | Verified in driver |
| `0xFA` | Acknowledge | none | Verified in driver |
| `0xFB` | Negative acknowledge | 1 byte command ID | Verified in driver |

Two-byte values are interpreted as unsigned big-endian integers.

## Graphics capability

### Raw character bytes

Supported by TruePanel's driver.

### Character ROM graphics

Not yet mapped.

### Custom CGRAM characters

Software support is prepared, but the A125 transport command for programming
CGRAM has not been verified.

Current status:

- Custom glyph definitions: ready
- Raw glyph-slot display bytes: ready
- CGRAM programming command: unknown
- Production custom mode: disabled

## Safety rules

1. Stop the TruePanel service before exclusive serial diagnostics.
2. Never probe while another process owns `/dev/ttyS1`.
3. Prefer known read-only queries.
4. Unknown commands require logging and a strict timeout.
5. NACK is evidence of unsupported behavior, not permission to continue.
6. Reset must remain available as a recovery command.
7. Every verified discovery must gain a protocol test and documentation entry.

## Reference implementation

Protocol encoding and decoding:

`truepanel/diagnostics/protocol.py`

High-level controller:

`truepanel/hardware/a125.py`

Offline tests:

`tests/test_a125_protocol.py`
