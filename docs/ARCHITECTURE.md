# TruePanel Architecture

TruePanel is a modular monitoring and display platform for TrueNAS SCALE systems with supported front-panel LCD hardware.

The project began as an LCD menu, but has evolved into an event-driven appliance interface.

---

## High-Level Flow

```text
TrueNAS SCALE
     |
     v
Collector
     |
     v
Shared System State
     |
     v
Mission Control
     |
     v
MissionEvent
     |
     v
Alert Manager
     |
     v
Display Manager
     |
     v
DisplayFrame
     |
     v
LCD Driver
     |
     v
QNAP Front Panel
