#!/usr/bin/env bash
set -euo pipefail

host="${1:-host0}"
hold="${2:-8}"

base="/sys/class/scsi_host/$host"
control="$base/em_message"
supported="$base/em_message_supported"

if [[ ! -d "$base" ]]; then
    echo "SCSI host not found: $host" >&2
    exit 1
fi

if [[ ! -r "$supported" ]] || ! grep -qw led "$supported"; then
    echo "$host does not advertise AHCI LED messages." >&2
    exit 2
fi

if [[ ! -r "$control" ]] || [[ ! -w "$control" ]]; then
    echo "LED message control is unavailable: $control" >&2
    exit 3
fi

original="$(cat "$control")"

restore() {
    printf '%s\n' "$original" | tee "$control" >/dev/null || true
    echo "Restored $host em_message=$original"
}

trap restore EXIT INT TERM

echo "Host:          $host"
echo "Supported:     $(cat "$supported")"
echo "Original:      $original"
echo "Test message:  0x10000"
echo
echo "Watch every drive bay for $hold seconds."

printf '%s\n' '0x10000' | tee "$control" >/dev/null

printf 'Readback:      '
cat "$control"

sleep "$hold"
