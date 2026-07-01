#!/usr/bin/env python3

"""
TruePanel launcher.

This will eventually replace lcd-menu.py as the main entry point.
For now, it safely runs the existing working menu.
"""

import runpy

runpy.run_path("lcd-menu.py", run_name="__main__")
