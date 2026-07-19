#!/usr/bin/env bash
set -euo pipefail

sysroot="development/firmware/lab/TVS-X71_20260514-5.2.9.3499/sysroot"
library="$sysroot/lib64/libuLinux_hal.so"
report="development/firmware/lab/TVS-X71_20260514-5.2.9.3499/qnap_led_static_trace.log"

if [[ ! -f "$library" ]]; then
    echo "HAL library not found:"
    echo "  $library"
    exit 1
fi

functions=(
    hal_adapter_se_sys_set_status_led
    module_se_sys_set_status_led
    se_sys_set_status_led
    sio_sys_set_status_led
    sio_sys_blink_status_led
    sio_sys_set_GPIO_led
    sio_sys_set_gpio_val
    sio_sys_get_gpio_val
    GPIO_Set_NAS_Status_LED
    common_sys_set_gpio_led_blink
)

{
    echo "================================================================"
    echo "TRUEPANEL PROJECT STARGATE"
    echo "QNAP TVS-X71 LED Static Trace"
    echo "Generated: $(date --iso-8601=seconds)"
    echo "================================================================"

    echo
    echo "===== LIBRARY IDENTITY ====="
    /bin/ls -lh "$library"
    /usr/bin/file "$library"
    /usr/bin/sha256sum "$library"

    echo
    echo "===== TARGET SYMBOLS ====="

    for function in "${functions[@]}"; do
        echo
        echo "--- $function ---"

        /usr/bin/readelf -Ws "$library" |
            /usr/bin/awk -v target="$function" \
                '$8 == target { print }' ||
            true
    done

    echo
    echo "===== TARGET DISASSEMBLY ====="

    for function in "${functions[@]}"; do
        if /usr/bin/readelf -Ws "$library" |
            /usr/bin/awk -v target="$function" \
                '$8 == target { found=1 } END { exit !found }'
        then
            echo
            echo "================================================"
            echo "FUNCTION: $function"
            echo "================================================"

            /usr/bin/objdump \
                -d \
                -M intel \
                --disassemble="$function" \
                "$library" ||
                true
        else
            echo
            echo "MISSING FUNCTION: $function"
        fi
    done

    echo
    echo "===== RELEVANT STRING OFFSETS ====="

    /usr/bin/strings -a -t x -n 5 "$library" |
        /usr/bin/grep -iE \
            'F71869A|GPIO_Set_NAS_Status_LED|sio_sys_set_status_led|sio_sys_set_GPIO_led|STATUS_LED_G|GPIO_OUT_|GPIO_IN_|LED_BV_GPIO|System GPIO|SIO:' |
        /usr/bin/head -500 ||
        true

    echo
    echo "===== END REPORT ====="
} | /usr/bin/tee "$report"

echo
echo "Saved report:"
echo "$report"
