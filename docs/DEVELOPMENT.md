# TruePanel Development Guide

This document describes the development workflow, coding standards, and project conventions used by TruePanel.

The goal is to keep the project organized, maintainable, and enjoyable to work on as it grows.

---

# Branch Strategy

TruePanel uses two primary branches.

## `main`

The `main` branch should always represent the latest stable version of the project.

Code on `main` should:

* Build successfully
* Run correctly
* Be suitable for public use

Only completed features should be merged into `main`.

---

## `develop`

The `develop` branch is where active development occurs.

New features, experiments, and refactoring should happen here before being merged into `main`.

Future feature branches may include:

```text
feature/decision-engine
feature/network
feature/smart
feature/config
feature/alerts
```

---

# Commit Messages

Commits should describe *what* changed.

Examples:

```text
docs: add architecture guide
docs: update roadmap
feat: add decision engine
feat: implement ARC statistics
fix: correct SMART temperature parsing
refactor: simplify collector update loop
style: clean up LCD rendering
```

Small, focused commits are preferred over large commits containing unrelated changes.

---

# Versioning

TruePanel follows Semantic Versioning.

Examples:

```text
0.6.0-dev
0.6.1
0.7.0
0.8.0
1.0.0
```

Each milestone also receives a codename.

| Version | Codename        |
| ------- | --------------- |
| 0.6     | Sentinel        |
| 0.7     | Mission Control |
| 0.8     | Watchtower      |
| 0.9     | Polaris         |
| 1.0     | Beacon          |

---

# Architecture

Whenever possible, keep responsibilities separated.

## Collector

Collect system information.

Never format display text.

---

## Decision Engine

Determine which information is most important.

Never communicate directly with hardware.

---

## Renderer

Convert system state into LCD-friendly output.

Never gather system information.

---

## Display Driver

Handle LCD communication and button input.

Remain independent from monitoring logic.

---

# Coding Style

General guidelines:

* Keep functions focused on a single task.
* Prefer readable code over clever code.
* Avoid duplicated logic.
* Document unusual behavior.
* Use descriptive variable names.
* Minimize expensive shell commands.
* Fail gracefully whenever possible.

---

# Documentation

Every significant feature should update the appropriate documentation.

Examples:

* README
* CHANGELOG
* ARCHITECTURE
* ROADMAP

Documentation should evolve alongside the code.

---

# Testing

Before committing:

* Verify Python syntax.
* Confirm the LCD initializes correctly.
* Test button navigation.
* Verify collector output.
* Check new pages for display formatting.
* Ensure no existing features have regressed.

Typical commands:

```bash
python3 -m py_compile collector.py lcd-menu.py
sudo python3 collector.py
sudo python3 lcd-menu.py
```

---

# Definition of Done

A feature is considered complete when:

* The code functions correctly.
* Existing functionality remains intact.
* Documentation has been updated.
* The feature has been tested on hardware.
* The code is ready to merge into `main`.

---

# Long-Term Goal

Every change should move TruePanel toward becoming a stable, reliable monitoring platform for TrueNAS SCALE.

The project should remain approachable for new contributors while maintaining a clean and scalable architecture.

When in doubt, favor simplicity, reliability, and clarity.
