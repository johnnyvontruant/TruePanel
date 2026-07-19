#!/usr/bin/env bash
set -euo pipefail

disk="${1:-sdb}"
mode="${2:-1}"
megabytes="${3:-1024}"

control="/sys/block/$disk/device/sw_activity"
device="/dev/$disk"

if [[ "$mode" != "1" && "$mode" != "2" ]]; then
    echo "Mode must be 1 or 2." >&2
    exit 1
fi

if [[ ! -b "$device" ]]; then
    echo "Block device not found: $device" >&2
    exit 1
fi

if [[ ! -e "$control" ]]; then
    echo "sw_activity is not exposed for $disk:" >&2
    echo "$control" >&2
    exit 2
fi

original="$(cat "$control")"

restore() {
    printf '%s\n' "$original" > "$control" 2>/dev/null || true
    echo
    echo "Restored $disk sw_activity=$original"
}

trap restore EXIT INT TERM

echo "Disk:          $disk"
echo "Control:       $control"
echo "Original mode: $original"
echo "Test mode:     $mode"
echo
echo "Mode 1: LED normally dark, flashes during activity."
echo "Mode 2: LED normally lit, goes dark during activity."
echo
echo "Setting mode..."

printf '%s\n' "$mode" > "$control"

echo "Readback: $(cat "$control")"
echo
echo "Watch every physical drive bay."
echo "Beginning read-only disk activity..."

dd \
    if="$device" \
    of=/dev/null \
    bs=4M \
    count="$((megabytes / 4))" \
    iflag=direct \
    status=progress

echo
echo "Disk read complete. Watching idle state for five seconds..."
sleep 5
