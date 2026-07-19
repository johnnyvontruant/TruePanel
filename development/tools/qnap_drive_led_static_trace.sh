#!/usr/bin/env bash
set -euo pipefail

sysroot="development/firmware/lab/TVS-X71_20260514-5.2.9.3499/sysroot"
library="$sysroot/lib64/libuLinux_hal.so"
report="development/firmware/lab/TVS-X71_20260514-5.2.9.3499/qnap_drive_led_static_trace.log"

functions=(
    GPIO_Enable_HDD_Active_LED
    GPIO_Enable_HDD_ERR_LED
    GPIO_Enable_HDD_ERR_LEDS
    GPIO_Enable_HDD_Ident_LED
    GPIO_Enable_HDD_Present_LED
    GPIO_Enable_HDD_Present_LEDS
    hal_adapter_pd_sys_set_hdd_leds
    module_pd_sys_set_hdd_leds
    PD_Sys_Set_Disk_Err
    sas_set_hdd_err_led
    se_sys_sg16_set_disk_led
    emcu_sys_sg16_set_disk_led
    sio_sys_set_GPIO_led
)

{
    echo "================================================================"
    echo "QNAP TVS-671 Drive LED Static Trace"
    echo "================================================================"

    for function in "${functions[@]}"; do
        echo
        echo "================================================"
        echo "FUNCTION: $function"
        echo "================================================"

        if /usr/bin/readelf -Ws "$library" |
            /usr/bin/awk -v target="$function" \
                '$8 == target { found=1 } END { exit !found }'
        then
            /usr/bin/objdump \
                -d \
                -M intel \
                --disassemble="$function" \
                "$library" ||
                true
        else
            echo "Symbol not present."
        fi
    done
} | /usr/bin/tee "$report"

echo
echo "Saved report:"
echo "$report"
