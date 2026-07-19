# TruePanel History

## First light

TruePanel began with a small collection of scripts intended to wake a QNAP front-panel LCD under a different operating system. The initial repository contained only a handful of files and depended heavily on inherited assumptions.

## Becoming TruePanel

The project gained its own name, visual identity, installer, configuration, service, documentation, and development workflow. Collector-first design replaced scattered direct reads, while Mission Control introduced priorities, structured events, alert history, and a calm default display policy.

## Flight Deck

The LCD evolved from static pages into Flight Deck: a rotating dashboard with AutoPilot, button pauses, startup sequences, night mode, themes, transitions, native A125 ROM graphics, custom CGRAM glyphs, instruments, gauges, trends, and plugin pages.

## Platform services

TruePanel added:

- plugin API v1
- hardware abstraction
- storage inventory and topology
- SMART and storage health services
- ZFS operation watching
- historical telemetry
- simulation
- diagnostics
- guarded hardware commands

## Project Stargate

Project Stargate formalized hardware research. Captures became sessions, commands became catalog entries, and live experiments gained simulation, classification, danger levels, interlocks, cooldowns, fingerprints, timing studies, and capability reports.

This work identified and verified the A125 controller on the TVS-671, including board and protocol queries, button state, display ownership, ROM graphics, CGRAM behavior, and timing.

## Chassis integration

Firmware archaeology and supervised probes mapped TVS-671 status LEDs and all six bay identify LEDs.

The production storage path now connects logical health to physical hardware:

```text
drive fault -> matching bay LED -> rotating LCD detail page
recovery    -> bay LED off      -> detail cleared
```

This replaced a redundant drive-fault interrupt screen while preserving structured event history.

## Independence

By July 2026, TruePanel had hundreds of tracked source and documentation files, a broad automated suite, a plugin platform, a hardware laboratory, and model-specific production controls. Only one file from the 2022 root commit remained unchanged, and it was retired during consolidation.

The original lineage remains part of the Git record, but the living project is an independently developed TruePanel platform.

## Consolidation milestone

On July 19, 2026:

- the modern hardware-aware platform was consolidated;
- obsolete dashboard test generations were retired;
- 861 tests passed;
- generated artifacts and runtime state were removed;
- 1.1 GB of extracted firmware was archived outside Git;
- reusable Stargate tools were curated;
- obsolete root utilities were retired;
- the documentation was rebuilt around the current platform.
