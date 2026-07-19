#!/usr/bin/env bash
set -euo pipefail

sysroot="development/firmware/lab/TVS-X71_20260514-5.2.9.3499/sysroot"
report="development/firmware/lab/TVS-X71_20260514-5.2.9.3499/qnap_model_profile_hunt.log"

{
    echo "================================================================"
    echo "TRUEPANEL PROJECT STARGATE"
    echo "QNAP TVS-X71 Model Profile Hunt"
    echo "Generated: $(date --iso-8601=seconds)"
    echo "================================================================"

    echo
    echo "===== MODEL AND PLATFORM FILES ====="

    find "$sysroot" \
        \( -type f -o -type l \) \
        \( \
            -iname '*model*.conf*' -o \
            -iname '*platform*.conf*' -o \
            -iname '*hal*.conf*' -o \
            -iname '*gpio*.conf*' -o \
            -iname '*system*io*' \
        \) \
        -printf '%y %10s %p -> %l\n' 2>/dev/null |
        sort

    echo
    echo "===== CONFIGURATION DIRECTORIES ====="

    find "$sysroot" -type d \
        \( \
            -iname '*model*' -o \
            -iname '*platform*' -o \
            -iname '*default_config*' -o \
            -iname '*hal*' \
        \) \
        -print 2>/dev/null |
        sort

    echo
    echo "===== TVS-X71 AND FINTEK REFERENCES ====="

    find "$sysroot" \
        -type f \
        -size -80M \
        ! -path '*/home/httpd/*' \
        ! -path '*/www/*' \
        ! -path '*/share/locale/*' \
        -print0 2>/dev/null |
    while IFS= read -r -d '' candidate; do
        matches="$(
            /usr/bin/strings -a -n 6 "$candidate" 2>/dev/null |
                /usr/bin/grep -iE \
                    'TVS-671|TVS-X71|F71869A|STATUS_LED_GB|GPIO_Set_NAS_Status_LED|SIO:I[0-9A-F]{2}|LED_BV_GPIO' |
                /usr/bin/head -50 ||
                true
        )"

        if [[ -n "$matches" ]]; then
            echo
            echo "FILE: $candidate"
            printf '%s\n' "$matches"
        fi
    done

    echo
    echo "===== END REPORT ====="
} | /usr/bin/tee "$report"

echo
echo "Saved report:"
echo "$report"
