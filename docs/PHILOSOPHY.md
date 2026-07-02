# TruePanel Philosophy

TruePanel exists to make a TrueNAS system understandable at a glance.

It is not intended to replace the TrueNAS web interface. Instead, it complements it by presenting the most important information on the front panel of the NAS.

---

# Core Principles

## One Glance

A person walking past the NAS should understand its current state in under one second.

The front panel should answer the question:

> **"Is everything okay?"**

without requiring additional interaction.

---

## Information, Not Noise

Every screen should have a purpose.

Pages that do not provide useful information should not exist simply to fill space.

The goal is confidence, not complexity.

---

## Collector First

System information should be collected once.

Display pages should consume shared data rather than execute their own commands.

This keeps the interface responsive and minimizes unnecessary system activity.

---

## Prioritize What Matters

Not every event deserves equal attention.

A degraded pool is more important than CPU utilization.

A failing drive is more important than available memory.

Future versions of TruePanel will use a Decision Engine to determine the highest-priority system state and display it automatically.

---

## Calm by Default

When everything is healthy, the display should reassure the user.

Example:

```text
BattleStation

Healthy
```

The display should communicate confidence without demanding attention.

---

## Loud When Necessary

Critical conditions should immediately stand out.

Examples include:

* Pool degraded
* SMART failures
* Failed drives
* Critical temperatures
* Resilver operations
* Scrubs requiring attention

The user should never need to hunt through multiple pages to discover an important problem.

---

## Native Experience

TruePanel should feel like a natural extension of TrueNAS SCALE.

The interface should be clean, simple, and focused on system health rather than recreating the original QNAP firmware.

---

## Extensible Architecture

New monitoring features should be easy to add.

Each component should have a single responsibility.

* Collector gathers data.
* Decision Engine evaluates data.
* Renderer formats output.
* Display Driver communicates with hardware.

This separation allows the project to grow without becoming difficult to maintain.

---

## Reliable Above All

TruePanel is intended to run continuously.

Reliability is more important than visual effects or unnecessary complexity.

If a feature compromises stability, it should be redesigned or omitted.

---

# Long-Term Vision

TruePanel aims to become the front panel that TrueNAS deserves.

Rather than simply displaying information, it should communicate the overall health of the system in a way that is immediate, useful, and trustworthy.

The best dashboard is the one that quietly reassures you everything is working, and speaks clearly when it is not.
