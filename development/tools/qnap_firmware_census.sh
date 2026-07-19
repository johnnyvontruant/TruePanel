#!/usr/bin/env bash
set -euo pipefail

incoming="development/firmware/incoming"
extracted="development/firmware/extracted"
reports="development/firmware/reports"

mkdir -p "$incoming" "$extracted" "$reports"

mapfile -t firmware_files < <(
    find "$incoming" -maxdepth 1 -type f -printf '%p\n' | sort
)

if (( ${#firmware_files[@]} == 0 )); then
    echo "No firmware package found in:"
    echo "  $incoming"
    exit 1
fi

report="$reports/$(date +%Y%m%d_%H%M%S)_firmware_census.log"

{
    echo "================================================================"
    echo "TRUEPANEL PROJECT STARGATE"
    echo "QNAP TVS-671 Firmware Census"
    echo "Generated: $(date --iso-8601=seconds)"
    echo "================================================================"

    for firmware in "${firmware_files[@]}"; do
        echo
        echo "===== PACKAGE ====="
        echo "Path:   $firmware"
        echo "Name:   $(basename "$firmware")"
        echo "Size:   $(stat -c '%s bytes' "$firmware")"
        echo "SHA256: $(sha256sum "$firmware" | awk '{print $1}')"
        echo "Type:   $(file -b "$firmware")"

        echo
        echo "--- Archive listing ---"

        case "$firmware" in
            *.zip|*.ZIP)
                unzip -l "$firmware" 2>&1 || true
                ;;
            *.tar|*.tar.gz|*.tgz|*.tar.xz)
                tar -tvf "$firmware" 2>&1 || true
                ;;
            *)
                if command -v 7z >/dev/null 2>&1; then
                    7z l "$firmware" 2>&1 || true
                else
                    echo "7z unavailable; skipping generic archive listing."
                fi
                ;;
        esac

        echo
        echo "--- Embedded signatures ---"

        if command -v binwalk >/dev/null 2>&1; then
            binwalk "$firmware" 2>&1 || true
        else
            echo "binwalk not installed."
        fi

        echo
        echo "--- Interesting strings ---"

        strings -a -n 7 "$firmware" 2>/dev/null |
            grep -iE \
                'TVS-671|TVS-X71|X71|hal_app|hal_daemon|gpio|led|f71869|fintek|super.?io|disk.?led|status.?led|a125|lcd|platform.conf|model.conf' |
            head -500 ||
            true
    done

    echo
    echo "===== END REPORT ====="
} | tee "$report"

echo
echo "Saved report:"
echo "$report"
