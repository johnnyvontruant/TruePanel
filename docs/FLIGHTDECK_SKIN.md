# Flightdeck Skin

The Flightdeck skin is Mission Control's presentation layer. It combines two
ideas, the **Faceplate** (TruePanel drawn as physical hardware) and the
**Cockpit** (airliner alerting rules). The concept board it came from is the
"C+A2" direction on the TruePanel Dream Board.

## The story

TruePanel is the instrument panel for a machine that lives in a closet. The
physical LCD on the NAS tells the truth, and Mission Control is that front panel
extended into a browser. Each section is a panel screwed into an enclosure.
Things you can press are raised keys. Faults light up the way they do on a
flight deck.

Promise: **calm when it's fine, loud when it isn't, and it always says what to
do next.**

## Color code

These are the avionics conventions. A color means the same thing everywhere,
on every page and in every companion script.

| Color | Meaning | Examples |
|---|---|---|
| **Red** | Warning: act now | Master Warning, a DEGRADED or CRITICAL annunciator, a failed drive |
| **Amber** | Caution: you need to know | Master Caution, an ATTENTION annunciator, a wearing drive |
| **Cyan** | Something you can select or act on | Primary buttons, the selected mode, checklist actions, focus rings |
| **White / ink** | Labels and information | Panel placards, readouts |
| **Green** | A system is actively working | "Mission ready" link lamp, a Loadmaster copy in progress, a completed step |
| **Magenta** | A target value | Fan target RPM (future gauge work) |
| **No light** | Normal | A healthy annunciator is dark |

Green never means "fine". In this skin `--good` resolves to the ink color, so
a healthy state stays unlit. Use `--fd-active` for something that is actually
running.

On the light (Day) panel, amber and red text use darker shades so they still
meet WCAG AA contrast (4.5:1). On lit lenses and inside dark glass displays,
the full-strength colors are used.

## Materials

| Material | Where | Tokens |
|---|---|---|
| Enclosure plastic | The page | `--bg` |
| Panel module | Every `.card`, `.topbar`, `.lcd-faceplate`, `.ff-hero`, `.ff-card` | `--panel-solid`, `--fd-hi`, `--fd-lo` |
| Screws | Four per panel, each slot at its own angle | `fd-screw`, `--fd-screw-a/b` |
| Raised key | Every button | `--fd-key`, `--fd-key-shadow` |
| Dark key | LCD BACK key, chassis | `--fd-dark-key` |
| Unlit lens | Annunciators, master lights when normal | `--fd-lens-off`, `--fd-lens-legend` |
| Recessed well | Inputs, instrument boxes, drawers | `--fd-well` |
| Glass display | Fault advisory, fault hero | `--fd-glass`, `--fd-glass-*` |

## Type

| Role | Font | Notes |
|---|---|---|
| Panel placards, key legends | Barlow Condensed 600/700 | Uppercase, letter-spacing .14–.16em |
| Sentences, titles | Chivo 400/700/800 | Plain-English fault text stays sentence case |
| Readouts, codes | Chivo Mono 400/600/700 | Tabular numbers |

Fonts are vendored in `truepanel/web/static/fonts/` under the SIL Open Font
License 1.1 (license files sit alongside them). They are served from `/fonts/`
by a whitelisted route, so the dashboard looks the same on the LAN or over
Tailscale with no internet access. They cost nothing and pull nothing from a
CDN.

## Lighting

**Day** lighting is the light theme and **Night** lighting is the dark theme.
The existing theme toggle, its `truepanel-theme` localStorage key and the
theme bootstrap script are unchanged. The skin only relabels the toggle as
`LIGHTING · DAY` / `LIGHTING · NIGHT`.

## Components

- **Master WARNING / CAUTION:** two keys in the top bar. They light from the
  same subsystem states that `renderHealth()` already draws (`degraded` or
  `critical` lights Warning, `attention` lights Caution). Pressing a lit
  master acknowledges it for the browser session. A *new* set of faults lights
  it again. They are presentation only, with no API calls.
- **Annunciators:** `.health-subsystem` and the top-bar `.gc-annunciator`
  pills render as lenses. They stay dark when normal. A caution lights amber
  and a warning lights red, and a lit lens sits pressed into the panel.
- **LCD keys:** `virtualLcdEnter` shows **BACK** and `virtualLcdSelect` shows
  **NEXT**, matching what `lcd-menu.py` does with buttons 0x01 and 0x02. While
  Loadmaster owns the LCD, button 0x01 ejects the USB drive, so the left key
  reads **EJECT** in amber. Ids, click handlers and the `pressed` class are
  unchanged.
- **Fault displays:** `.health-advisory` and a warning or bad `.ff-hero`
  become dark glass displays set into the panel. The kicker is amber or red,
  the text is white, and the actions are cyan.

## How it is built

- `truepanel/web/static/flightdeck-skin.js` holds everything. Pathfinder
  injects it as the **last** companion script (marker
  `<!-- truepanel-flightdeck-skin -->`).
- It injects one `<style id="flightdeckSkin">` and keeps it last in `<head>`,
  because every companion script appends its own styles at runtime.
- All rules are scoped to `html[data-skin="flightdeck"]`.
- It never changes a DOM id, never rewrites telemetry text and never calls
  `fetch`. `tests/test_flightdeck_skin.py` guards those rules.
- Screws are `<fd-screw aria-hidden="true">` custom elements, so they can't
  match any existing `span` or `div` selector. A MutationObserver re-adds
  them when a companion script re-renders a panel.

## Rollback

| Want | Do |
|---|---|
| Classic look in one browser | Open `/?skin=classic` (remembered in localStorage) |
| Flightdeck back on | Open `/?skin=flightdeck` |
| Remove for everyone | Revert the PR, or delete the `_FLIGHTDECK_SKIN_*` injection in `pathfinder_server.py` |

## Roadmap

The skin ships in phases. Each phase is its own PR.

1. **Foundation (this PR):** tokens, materials, fonts, screws, keys,
   annunciators, masters, Day/Night lighting, LCD BACK/NEXT/EJECT, fault
   displays.
2. **Dial instruments:** CPU, memory, hottest drive and network as round
   gauges with caution bands and red lines. The fan gauge gets a magenta
   target bug.
3. **Drive chassis:** the bay mirror drawn as the TVS-671's six trays on a
   dark chassis, with LED and status chip per bay.
4. **Cooling selector:** the fan profile as a rotary knob, with
   **AFTERBURNERS** behind warning stripes.
5. **Glareshield layout:** master lights and annunciators in one strip
   directly under the LCD, with the fault display dropping in below it.
6. **ID plate:** a tail-number style plate and a "last flight" line (uptime
   and last checkride) in the header.
