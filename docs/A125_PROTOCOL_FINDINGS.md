# A125 / A78 LCD Protocol Findings

## Scope

This document records offline analysis of QNAP TVS-X71 firmware
version 5.2.9.3499.

Recovered binaries examined:

- `lcd_tool`
- `lcd_hwtest`
- `lcdmond`

No recovered QNAP binaries were executed.

## Packet framing

A125/A78 packets use the `0x4D` preamble.

## Display text

```text
4D 0C <line> <length> <text bytes...>
```

The vendor display routine writes `length + 4` bytes. The text
bytes are copied directly into the packet. No character-bitmap
translation or CGRAM upload path was found.

## Recovered commands

| Opcode | Purpose | Packet | Evidence |
|---|---|---|---|
| `0x00` | Get board ID | `4D 00` | Verified live |
| `0x02` | Set LED value | `4D 02 <value_hi> <value_lo>` | Vendor constructor |
| `0x03` | Unknown fixed command | `4D 03` | Vendor command table |
| `0x06` | Get buttons | `4D 06` | Verified live |
| `0x07` | Get protocol version | `4D 07` | Verified live |
| `0x09` | Set RTC time | `4D 09 <six date/time bytes>` | Vendor constructor |
| `0x0B` | Unknown fixed command | `4D 0B` | Vendor command table |
| `0x0C` | Display text | `4D 0C <line> <length> <text>` | Verified live |
| `0x0D` | Clear display | `4D 0D` | Verified live |
| `0x28` | Stop RTC display | `4D 28` | Vendor disassembly |
| `0x29` | Start RTC display | `4D 29` | Vendor disassembly |
| `0x35` | Manual adjustment toggle | `4D 35 <00|01>` | Vendor constructor |
| `0x5E` | Backlight control | `4D 5E <00|01>` | Verified live |
| `0xFF` | Reset | `4D FF` | Verified live; forbidden for experimental probing |

## Deterministic header-only NACKs

The following opcodes produced deterministic NACKs when probed as
header-only commands:

- `0x08`
- `0x0A`
- `0x0E`
- `0x0F`
- `0x10`

These results do not override static evidence that `0x09` and `0x0B`
are used by the vendor stack. Those commands require payloads and are
not valid header-only probes.

## Command table

The recovered command dispatcher uses 28-byte records:

- Command identifier at offset `+0x00`
- Packet buffer begins at offset `+0x04`
- Packet length at offset `+0x18`
- Record size `0x1C`

Recovered fixed records:

- ID 1 → `4D 03`
- ID 2 → `4D 07`
- ID 3 → `4D 0B`
- ID 4 → `4D 0D`
- ID 5 → `4D 28`
- ID 6 → `4D 29`
- ID 7 → `4D 5E 01`
- ID 8 → `4D 5E 00`

## Recovered function mappings

- `A78_Start_RTC_Display()` → command ID 6 → `4D 29`
- `A78_Stop_RTC_Display()` → command ID 5 → `4D 28`
- `A78_Set_LED(value)` → `4D 02 <value_hi> <value_lo>`
- `A78_Manual_Adjustment(enabled)` → `4D 35 <00|01>`
- `A78_Set_Clock_Time()` → `4D 09 <six date/time bytes>`
- `A78_Display_Char_On_LCD(line, text)` → opcode `0x0C`

## Custom-glyph finding

No CGRAM, custom-character, glyph-definition, or bitmap-upload
packet constructor was found in the official QNAP LCD utility,
hardware-test utility, or daemon.

No recovered routine sends a payload resembling:

```text
<glyph slot> <row 1> <row 2> ... <row 8>
```

The official QNAP software stack therefore does not implement
custom glyphs for this controller.

This does not prove that the A125 microcontroller firmware lacks an
undocumented command. Discovering such a command would require a
separate, safety-gated live-probing investigation.

## Safety boundary

All findings in this document came from offline firmware extraction,
string analysis, command-table inspection, and disassembly.

No recovered executable was run, and no undocumented command was
sent to the live controller.
