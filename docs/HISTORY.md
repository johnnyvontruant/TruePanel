# TruePanel History

TruePanel began as a simple goal: restore the built-in LCD on a QNAP TVS-671 running TrueNAS SCALE.

What started as a front-panel display experiment quickly became a native TrueNAS monitoring project.

---

## First Light

The first milestone was getting the LCD to respond under TrueNAS SCALE.

Early testing involved identifying the correct serial device and confirming that the QNAP front-panel LCD could still receive commands outside of QTS.

After testing multiple ports, the working LCD configuration settled on:

```text
/dev/ttyS1
```

The first successful display output confirmed that the hardware was alive.

---

## Button Navigation

Once the LCD was working, the next milestone was confirming that the front-panel buttons worked.

The original menu system successfully cycled through pages and responded to button presses, proving that the LCD could become more than a static status screen.

---

## System Monitoring

TruePanel then began adding TrueNAS-specific information:

* CPU and RAM usage
* ZFS pool health
* Storage usage
* Pool capacity progress bar

This was the first step away from recreating the original QNAP menu and toward building a native TrueNAS dashboard.

---

## Drive Temperatures

The next major milestone was drive temperature support.

TruePanel learned to read both SATA and NVMe temperature formats, sort drives by temperature, and show the hottest drives first.

This made the LCD immediately more useful as a hardware health display.

---

## The Collector

The project changed direction when the collector architecture was introduced.

Instead of each LCD page running its own system commands, TruePanel gained a central collector responsible for gathering system information once and exposing it through shared state.

This became the foundation for future development.

---

## ARC and ZFS Activity

The collector then expanded to include:

* ARC cache size
* ARC hit ratio
* ZFS scrub detection
* ZFS resilver detection
* Pool activity state

This marked the point where TruePanel began evolving from an LCD menu into a telemetry engine for TrueNAS SCALE.

---

## GitHub Launch

TruePanel became its own GitHub project under:

```text
johnnyvontruant/TruePanel
```

The repository was cleaned, documentation was added, and development moved toward a more structured workflow using Git, branches, commits, and milestones.

---

## Project Identity

The project adopted the name:

```text
TruePanel
```

The name reflects the long-term goal: to become the front panel that TrueNAS deserves.

---

## Current Direction

The next major milestone is the Decision Engine.

The collector gathers facts.

The Decision Engine will decide what matters.

The LCD will display the most important system state automatically.

This is the beginning of TruePanel becoming more than a dashboard. It is becoming a small, intelligent operations console for TrueNAS SCALE.
