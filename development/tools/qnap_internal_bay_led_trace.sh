#!/usr/bin/env bash
set -euo pipefail

sysroot="development/firmware/lab/TVS-X71_20260514-5.2.9.3499/sysroot"
hal_app="$sysroot/sbin/hal_app"
hal_lib="$sysroot/lib64/libuLinux_hal.so"
modules="$sysroot/lib/hal_modules/modules.list"
report="development/firmware/lab/TVS-X71_20260514-5.2.9.3499/qnap_internal_bay_led_trace.log"

{
    echo "================================================================"
    echo "TRUEPANEL PROJECT STARGATE"
    echo "TVS-671 Internal Drive-Bay LED Trace"
    echo "Generated: $(date --iso-8601=seconds)"
    echo "================================================================"

    echo
    echo "===== HAL MODULE SELECTION TABLE ====="

    if [[ -f "$modules" ]]; then
        /bin/cat "$modules"
    else
        echo "Missing: $modules"
    fi

    echo
    echo "===== TVS-X71 MODULE REFERENCES ====="

    /usr/bin/grep -aEin -C4 \
        'TVS-671|TVS-X71|QW830|tl_xx10tc4|tl_rxx00pes' \
        "$modules" \
        "$sysroot"/etc/*.conf 2>/dev/null ||
        true

    echo
    echo "===== REAL COMMAND INVOCATIONS ====="

    /usr/bin/grep -RIna -C8 \
        --exclude='*.js' \
        --exclude='*.css' \
        --exclude='*.xml' \
        -- \
        '--set_disk_green_led_status|--set_disk_error_led_status|--pd_sys_set_active_led|/var/ledvalue' \
        "$sysroot/etc" \
        "$sysroot/sbin" \
        "$sysroot/usr/share" 2>/dev/null |
        /usr/bin/head -1600 ||
        true

    echo
    echo "===== HAL_APP LED SYMBOLS ====="

    /usr/bin/readelf -Ws "$hal_app" 2>/dev/null |
        /usr/bin/grep -iE \
            'set_disk_(green|error)|pd_sys_set_active|active_led|disk.*led|ledvalue' |
        /usr/bin/sort -k8,8 ||
        true

    echo
    echo "===== HAL LIBRARY INTERNAL-DISK SYMBOLS ====="

    /usr/bin/readelf -Ws "$hal_lib" 2>/dev/null |
        /usr/bin/grep -iE \
            'pd_.*active.*led|set_disk_(green|error)|set_hdd_led|ahci|ledvalue|sata.*led' |
        /usr/bin/sort -k8,8 ||
        true

    echo
    echo "===== HAL_APP COMMAND STRING OFFSETS ====="

    /usr/bin/strings -a -t x -n 5 "$hal_app" |
        /usr/bin/grep -iE \
            -- '--set_disk_green_led_status|--set_disk_error_led_status|--pd_sys_set_active_led|/var/ledvalue|id=%d,enable=%d' ||
        true

    echo
    echo "===== HAL LIBRARY LEDVALUE REFERENCES ====="

    /usr/bin/strings -a -t x -n 5 "$hal_lib" |
        /usr/bin/grep -iE \
            '/var/ledvalue|ledvalue_formatting_count|pd_sys_is_driver_ahci|set_disk_green_led|set_disk_error_led|set_active_led' ||
        true

    echo
    echo "===== LEDVALUE INITIALIZATION ====="

    for candidate in \
        "$sysroot/etc/init.d/init_check.sh" \
        "$sysroot/etc/init.d/init_disk.sh"
    do
        [[ -f "$candidate" ]] || continue

        echo
        echo "FILE: $candidate"

        /usr/bin/grep -nE -C20 \
            'ledvalue|set_disk_green_led|set_disk_error_led|active_led' \
            "$candidate" ||
            true
    done

    echo
    echo "===== LIKELY INTERNAL LED FUNCTIONS ====="

    mapfile -t functions < <(
        /usr/bin/readelf -Ws "$hal_lib" 2>/dev/null |
            /usr/bin/awk '
                /FUNC/ &&
                /GLOBAL/ &&
                /(active.*led|disk.*green.*led|disk.*error.*led|hdd.*led|ahci.*led|ledvalue)/ {
                    print $8
                }
            ' |
            /usr/bin/sed 's/@.*//' |
            /usr/bin/sort -u
    )

    for function in "${functions[@]}"; do
        [[ -n "$function" ]] || continue

        echo
        echo "================================================"
        echo "FUNCTION: $function"
        echo "================================================"

        /usr/bin/objdump \
            -d \
            -M intel \
            --disassemble="$function" \
            "$hal_lib" 2>/dev/null ||
            true
    done

    echo
    echo "===== END REPORT ====="
} | /usr/bin/tee "$report"

echo
echo "Saved report:"
echo "$report"
