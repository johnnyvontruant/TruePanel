# TruePanel Architecture

TruePanel is designed as a small monitoring platform with an LCD frontend.

The long-term architecture is:

```text
TrueNAS SCALE
     |
     v
Collector
     |
     v
Shared State
     |
     v
Decision Engine
     |
     v
Renderer
     |
     v
Display Driver
Collector

The collector gathers system telemetry from TrueNAS SCALE and Linux.

It is responsible for collecting:

CPU utilization
Memory utilization
Network activity
ZFS pool status
Storage usage
Drive temperatures
ARC cache statistics
Scrub and resilver activity

The collector should gather data once and expose it through shared state.

Display pages should not run expensive system commands directly.

Shared State

Shared state is the current snapshot of the NAS.

Examples:

state["cpu_percent"]
state["ram_percent"]
state["pools"]
state["temps"]
state["arc"]
state["zfs_activity"]

Future versions may replace dictionaries with typed models.

Decision Engine

The Decision Engine decides what matters most right now.

Examples:

Pool degraded
Drive too hot
Scrub running
Resilver running
Heavy network activity
System healthy

The LCD should not decide priority. It should only display the result.

Renderer

The renderer converts a selected state into two LCD-safe text lines.

Example:

BattleStation
All Systems OK

or:

Scrub Running
42% Complete
Display Driver

The display driver handles hardware-specific LCD communication.

Current driver:

QNAP A125-style front-panel LCD
Two-button navigation
Serial communication

Currently tested on:

QNAP TVS-671
/dev/ttyS1
Design Goal

Each layer should have one job.

Collector gathers facts.
Decision Engine chooses importance.
Renderer formats text.
Display Driver talks to hardware.

This keeps TruePanel reliable, extensible, and easier to maintain.
