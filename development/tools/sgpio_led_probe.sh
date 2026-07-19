#!/usr/bin/env bash
set -euo pipefail

slot_number="${1:-05}"
mode="${2:-locate}"
hold="${3:-5}"

base="/sys/class/enclosure/6:0:0:0"
slot="$base/Slot $slot_number"
control="$slot/$mode"

if [[ ! -d "$slot" ]]; then
    echo "Slot not found: $slot" >&2
    exit 1
fi

if [[ "$mode" != "locate" && "$mode" != "fault" ]]; then
    echo "Mode must be locate or fault." >&2
    exit 1
fi

if [[ ! -w "$control" ]]; then
    echo "Control is not writable: $control" >&2
    exit 1
fi

original="$(cat "$control")"

restore() {
    printf '%s\n' "$original" | sudo tee "$control" >/dev/null || true
    echo "Restored Slot $slot_number $mode=$original"
}

trap restore EXIT INT TERM

echo "Slot:     $slot_number"
echo "Mode:     $mode"
echo "Original: $original"
echo "Device:   $(find -L "$slot/device/block" -mindepth 1 -maxdepth 1 -printf '%f ' 2>/dev/null)"
echo
echo "Enabling for $hold seconds..."

echo 1 | sudo tee "$control" >/dev/null
echo "Current:  $(cat "$control")"

sleep "$hold"
