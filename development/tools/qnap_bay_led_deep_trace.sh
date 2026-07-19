#!/usr/bin/env bash
set -euo pipefail

sysroot="development/firmware/lab/TVS-X71_20260514-5.2.9.3499/sysroot"
library="$sysroot/lib64/libuLinux_hal.so"
hal_app="$sysroot/sbin/hal_app"
model="$sysroot/etc/model_QW560_QW830_10_10.conf"
report="development/firmware/lab/TVS-X71_20260514-5.2.9.3499/qnap_bay_led_deep_trace.log"

dump_symbol() {
    local binary="$1"
    local symbol="$2"
    local info
    local address_hex
    local size_dec
    local start
    local stop

    info="$(
        /usr/bin/readelf -Ws "$binary" 2>/dev/null |
        /usr/bin/awk -v target="$symbol" '
            $8 == target || index($8, target "@") == 1 {
                print $2, $3
                exit
            }
        '
    )"

    echo
    echo "================================================"
    echo "FUNCTION: $symbol"
    echo "BINARY:   $binary"
    echo "================================================"

    if [[ -z "$info" ]]; then
        echo "Symbol not found."
        return
    fi

    read -r address_hex size_dec <<< "$info"

    start=$((16#$address_hex))
    stop=$((start + size_dec))

    printf 'Address: 0x%X\n' "$start"
    printf 'Size:    %d bytes\n' "$size_dec"
    printf 'End:     0x%X\n' "$stop"

    /usr/bin/objdump \
        -d \
        -M intel \
        --start-address="$start" \
        --stop-address="$stop" \
        "$binary" 2>/dev/null ||
        true
}

{
    echo "================================================================"
    echo "TRUEPANEL PROJECT STARGATE"
    echo "TVS-671 Drive-Bay LED Deep Trace"
    echo "Generated: $(date --iso-8601=seconds)"
    echo "================================================================"

    echo
    echo "===== MODEL DRIVE MAP ====="

    /usr/bin/awk '
        /^\[/ {
            relevant = ($0 ~ /^\[(System Enclosure|System Disk|Disk)/)
        }

        relevant {
            printf "%5d  %s\n", NR, $0
        }
    ' "$model"

    echo
    echo "===== IMPORTANT MODEL VALUES ====="

    /usr/bin/grep -nE \
        'MAX_DISK_NUM|DISK_DRV_TYPE|DEV_BUS|DEV_PORT|DEV_PATH|SLOT|PORT|AHCI|SGPIO|SIO_DEVICE' \
        "$model" ||
        true

    echo
    echo "===== LIBRARY CONTROL FUNCTIONS ====="

    dump_symbol "$library" pd_sys_is_driver_ahci
    dump_symbol "$library" pd_sys_set_active_led
    dump_symbol "$library" sio_sys_set_hdd_err_led
    dump_symbol "$library" hal_adapter_pd_sys_set_hdd_leds

    echo
    echo "===== HAL_APP DISK COMMAND WRAPPERS ====="

    dump_symbol "$hal_app" disk_sys_set_err_led
    dump_symbol "$hal_app" disk_sys_set_ident_led
    dump_symbol "$hal_app" disk_sys_set_present_led
    dump_symbol "$hal_app" disk_sys_set_blink_led

    echo
    echo "===== PD ACTIVE-LED CALLS ONLY ====="

    /usr/bin/objdump \
        -d \
        -M intel \
        --disassemble=pd_sys_set_active_led \
        "$library" 2>/dev/null |
        /usr/bin/grep -E \
            'call|AHCI|SGPIO|hdd|disk|led|module|sio|soc|mcu|emcu|qm2|enclos' ||
        true

    echo
    echo "===== SIO INTERNAL HELPER REGION ====="

    # sio_sys_set_hdd_err_led and the generic SIO GPIO functions
    # converge on internal code near these addresses.
    /usr/bin/objdump \
        -d \
        -M intel \
        --start-address=0x17fb40 \
        --stop-address=0x17ff80 \
        "$library" 2>/dev/null ||
        true

    echo
    echo "===== SIO CONFIGURATION STRINGS ====="

    /usr/bin/objdump \
        -s \
        -j .rodata \
        --start-address=0x2ccf80 \
        --stop-address=0x2cd100 \
        "$library" 2>/dev/null ||
        true

    echo
    echo "===== ACTIVE-LED CONFIGURATION STRINGS ====="

    /usr/bin/objdump \
        -s \
        -j .rodata \
        --start-address=0x2d7600 \
        --stop-address=0x2d79c0 \
        "$library" 2>/dev/null ||
        true

    echo
    echo "===== LED AND ENCLOSURE STRING INDEX ====="

    /usr/bin/strings -a -t x -n 5 "$library" |
        /usr/bin/grep -iE \
            'pd_sys_set_active_led|pd_sys_is_driver_ahci|sio_sys_set_hdd_err_led|hal_adapter_pd_sys_set_hdd_leds|AHCI|SGPIO|enclosure management|em_message|ledvalue|SET_HDD_LED|SET_SPECIFY_HDD_LED|active_led|error_led|ident_led|present_led|/sys/class/scsi_host|/sys/class/enclosure' |
        /usr/bin/sort -u |
        /usr/bin/head -1200 ||
        true

    echo
    echo "===== CALLERS OF KEY FUNCTIONS ====="

    for target in \
        pd_sys_set_active_led \
        sio_sys_set_hdd_err_led \
        hal_adapter_pd_sys_set_hdd_leds
    do
        echo
        echo "--- CALLERS: $target ---"

        /usr/bin/objdump -d -M intel "$library" 2>/dev/null |
            /usr/bin/grep -B5 -A4 -E \
                "call.*<${target}(@@Base)?>" |
            /usr/bin/head -500 ||
            true
    done

    echo
    echo "===== END REPORT ====="
} | /usr/bin/tee "$report"

echo
echo "Saved report:"
echo "$report"
