#!/usr/bin/env bash
set -euo pipefail

echo "== TruePanel Hardware Detection =="
echo

echo "-- System --"
hostnamectl 2>/dev/null | grep -E "Operating System|Kernel|Architecture" || true
echo

echo "-- Serial Ports --"
ls -l /dev/ttyS* 2>/dev/null || echo "No ttyS ports found"
echo

echo "-- LCD Guess --"
if [[ -e /dev/ttyS1 ]]; then
  echo "✓ Possible QNAP LCD: /dev/ttyS1"
else
  echo "✗ /dev/ttyS1 not found"
fi
echo

echo "-- Fan Controller --"
FOUND=0
for d in /sys/class/hwmon/hwmon*/device; do
  [[ -e "$d/name" ]] || continue
  name=$(cat "$d/name" 2>/dev/null || true)

  if [[ "$name" == f718* ]] || [[ -e "$d/fan1_input" && -e "$d/pwm1" ]]; then
    FOUND=1
    echo "✓ Found: $name"
    echo "  Path: $d"
    echo "  Fan1: $(cat "$d/fan1_input" 2>/dev/null || echo '?') RPM"
    echo "  Fan2: $(cat "$d/fan2_input" 2>/dev/null || echo '?') RPM"
    echo "  PWM1: $(cat "$d/pwm1" 2>/dev/null || echo '?')"
    echo "  PWM2: $(cat "$d/pwm2" 2>/dev/null || echo '?')"
  fi
done

if [[ "$FOUND" -eq 0 ]]; then
  echo "✗ No supported fan controller found"
fi
echo

echo "-- Temperatures --"
sensors 2>/dev/null | grep -E "temp|fan|Composite|Package|Core" | head -40 || echo "sensors command not available"
echo

echo "Detection complete."
