#!/usr/bin/env bash
set -euo pipefail

sysroot="development/firmware/lab/TVS-X71_20260514-5.2.9.3499/sysroot"
hal="$sysroot/lib64/libuLinux_hal.so"
report="development/firmware/lab/TVS-X71_20260514-5.2.9.3499/qnap_drive_led_backend_hunt.log"

{
    echo "================================================================"
    echo "TRUEPANEL PROJECT STARGATE"
    echo "QNAP TVS-671 Drive LED Backend Hunt"
    echo "Generated: $(date --iso-8601=seconds)"
    echo "================================================================"

    echo
    echo "===== HAL ADAPTER DISASSEMBLY ====="

    /usr/bin/objdump \
        -d \
        -M intel \
        --disassemble=hal_adapter_pd_sys_set_hdd_leds \
        "$hal"

    echo
    echo "===== ADAPTER-RELATED STRINGS ====="

    /usr/bin/strings -a -t x -n 5 "$hal" |
        /usr/bin/grep -iE \
            'module_pd_sys_set_hdd_leds|pd_sys_set_hdd_leds|set_hdd_leds|dlopen|hal.*module|module.*\.so|lib.*hal.*\.so' |
        /usr/bin/sort -u ||
        true

    echo
    echo "===== FILES CONTAINING BACKEND SYMBOL ====="

    find \
        "$sysroot/lib" \
        "$sysroot/lib64" \
        "$sysroot/usr/lib" \
        "$sysroot/usr/local/lib" \
        "$sysroot/sbin" \
        "$sysroot/usr/sbin" \
        -type f \
        -size -100M \
        -print0 2>/dev/null |
    while IFS= read -r -d '' candidate; do
        if /usr/bin/grep -aFq \
            'module_pd_sys_set_hdd_leds' \
            "$candidate" 2>/dev/null
        then
            echo
            echo "------------------------------------------------"
            echo "CANDIDATE: $candidate"
            echo "------------------------------------------------"

            /bin/ls -lh "$candidate"
            /usr/bin/file "$candidate"

            echo
            echo "--- Matching symbols ---"

            /usr/bin/readelf -Ws "$candidate" 2>/dev/null |
                /usr/bin/grep -iE \
                    'module_pd_sys_set_hdd_leds|pd_sys_set_hdd_leds|hdd.*led|disk.*led' ||
                true

            echo
            echo "--- Relevant strings ---"

            /usr/bin/strings -a -n 5 "$candidate" 2>/dev/null |
                /usr/bin/grep -iE \
                    'TVS-671|TVS-X71|QW830|module_pd_sys_set_hdd_leds|SET_HDD_LED|SET_SPECIFY_HDD_LED|HDD_.*LED|DISK_.*LED|SGPIO|AHCI|ledvalue|em_message|F71869|SIO:I|GPIO' |
                /usr/bin/cut -c1-260 |
                /usr/bin/sort -u |
                /usr/bin/head -600 ||
                true
        fi
    done

    echo
    echo "===== ALL ELF DEFINITIONS OF HDD LED FUNCTIONS ====="

    find \
        "$sysroot/lib" \
        "$sysroot/lib64" \
        "$sysroot/usr/lib" \
        "$sysroot/usr/local/lib" \
        "$sysroot/sbin" \
        "$sysroot/usr/sbin" \
        -type f \
        -size -100M \
        -print0 2>/dev/null |
    while IFS= read -r -d '' candidate; do
        kind="$(/usr/bin/file -b "$candidate" 2>/dev/null || true)"

        [[ "$kind" == *ELF* ]] || continue

        symbols="$(
            /usr/bin/readelf -Ws "$candidate" 2>/dev/null |
                /usr/bin/awk '
                    /GLOBAL/ &&
                    /DEFAULT/ &&
                    /(module_pd_sys_set_hdd_leds|pd_sys_set_hdd_leds|set_hdd_led|set_disk_led)/ {
                        print
                    }
                ' ||
                true
        )"

        if [[ -n "$symbols" ]]; then
            echo
            echo "FILE: $candidate"
            printf '%s\n' "$symbols"
        fi
    done

    echo
    echo "===== TVS-671 DRIVE CONFIGURATION ====="

    find "$sysroot/etc" \
        -type f \
        -size -10M \
        -print0 2>/dev/null |
    while IFS= read -r -d '' candidate; do
        matches="$(
            /usr/bin/grep -aEin \
                'TVS-671|TVS-X71|QW830|SET_HDD_LED|SET_SPECIFY_HDD_LED|HDD_.*LED|DISK_.*LED|PORT[0-9]+_.*LED|SGPIO|SIO:I|ledvalue' \
                "$candidate" 2>/dev/null |
                /usr/bin/head -100 ||
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
