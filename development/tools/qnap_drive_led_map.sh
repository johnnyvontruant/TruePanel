#!/usr/bin/env bash
set -euo pipefail

sysroot="development/firmware/lab/TVS-X71_20260514-5.2.9.3499/sysroot"
model="$sysroot/etc/model_QW560_QW830_10_10.conf"
halconf="$sysroot/etc/hal_util_QW560_QW830_10_10.conf"
library="$sysroot/lib64/libuLinux_hal.so"
report="development/firmware/lab/TVS-X71_20260514-5.2.9.3499/qnap_drive_led_map.log"

{
    echo "================================================================"
    echo "TRUEPANEL PROJECT STARGATE"
    echo "QNAP TVS-671 Drive LED Map"
    echo "Generated: $(date --iso-8601=seconds)"
    echo "================================================================"

    echo
    echo "===== TVS-671 MODEL PROFILE ====="
    /bin/ls -lh "$model"
    /usr/bin/file "$model"

    echo
    echo "===== ALL MODEL SECTIONS ====="
    /usr/bin/grep -nE \
        '^\[|^[A-Za-z0-9_ -]+[[:space:]]*=' \
        "$model" |
        /usr/bin/sed -n '1,1200p'

    echo
    echo "===== DRIVE AND LED ENTRIES ====="
    /usr/bin/grep -aEin -C6 \
        'Disk|HDD|LED|LOCATE|FAULT|IDENT|ACTIVE|PRESENT|ERR|SATA|PORT|SGPIO|GPIO|SIO:' \
        "$model" |
        /usr/bin/sed -n '1,1600p' ||
        true

    echo
    echo "===== HAL UTIL PROFILE ====="
    /usr/bin/grep -aEin -C6 \
        'TVS-671|Disk|HDD|LED|LOCATE|FAULT|IDENT|ACTIVE|PRESENT|ERR|SATA|PORT|SGPIO|GPIO|SIO:' \
        "$halconf" |
        /usr/bin/sed -n '1,1600p' ||
        true

    echo
    echo "===== OTHER MATCHING MODEL FILES ====="

    find "$sysroot/etc" \
        -maxdepth 2 \
        -type f \
        \( \
            -name 'model_*.conf' -o \
            -name 'hal_util_*.conf' -o \
            -iname '*enclosure*.conf' -o \
            -iname '*disk*.conf' \
        \) \
        -print0 |
    while IFS= read -r -d '' candidate; do
        if /usr/bin/grep -aqE \
            'TVS-671|QW830|SET_HDD_LED|HDD_.*LED|PORT[0-9]+_LOCATE_LED|DISK.*LED' \
            "$candidate"
        then
            echo
            echo "FILE: $candidate"

            /usr/bin/grep -aEin -C5 \
                'TVS-671|QW830|SET_HDD_LED|HDD_.*LED|PORT[0-9]+_LOCATE_LED|DISK.*LED|SGPIO|GPIO|SIO:' \
                "$candidate" |
                /usr/bin/head -400 ||
                true
        fi
    done

    echo
    echo "===== SET_LED SCRIPT ====="

    if [[ -f "$sysroot/etc/init.d/set_led.sh" ]]; then
        /usr/bin/grep -nE -C12 \
            'HDD|DISK|LED_BV_GPIO|LOCATE|FAULT|IDENT|ACTIVE|PRESENT|ERR' \
            "$sysroot/etc/init.d/set_led.sh" |
            /usr/bin/sed -n '1,1200p' ||
            true
    fi

    echo
    echo "===== HAL DRIVE LED SYMBOLS ====="

    /usr/bin/readelf -Ws "$library" |
        /usr/bin/grep -iE \
            'hdd.*led|disk.*led|locate.*led|fault.*led|ident.*led|present.*led|active.*led|pd_sys_set_hdd' |
        /usr/bin/sort -k8,8 |
        /usr/bin/sed -n '1,800p' ||
        true

    echo
    echo "===== HAL DRIVE LED STRINGS ====="

    /usr/bin/strings -a -t x -n 5 "$library" |
        /usr/bin/grep -iE \
            'SET_HDD_LED|SET_SPECIFY_HDD_LED|HDD_.*LED|DISK_.*LED|PORT[0-9]+_LOCATE_LED|LOCATE_LED|FAULT_LED|IDENT_LED|PRESENT_LED|ACTIVE_LED|SGPIO' |
        /usr/bin/sort -u |
        /usr/bin/sed -n '1,1000p' ||
        true

    echo
    echo "===== END REPORT ====="
} | /usr/bin/tee "$report"

echo
echo "Saved report:"
echo "$report"
