#!/usr/bin/env python3
"""Read-only checkpoint-10 hardware preflight; NEVER starts a USB write."""
import json
import sys

from truepanel.cargo.independent_ro_watchdog import host_ro_preflight


def main():
    try:
        print(json.dumps(host_ro_preflight(), indent=2))
        return 0
    except Exception as error:
        print(f'RO_WATCHDOG_PREFLIGHT_HOLD: {type(error).__name__}: {error}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
