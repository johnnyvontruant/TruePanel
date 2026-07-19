#!/usr/bin/env bash
set -uo pipefail

sysroot="development/firmware/lab/TVS-X71_20260514-5.2.9.3499/sysroot"
library="$sysroot/lib64/libuLinux_hal.so"
report="development/firmware/lab/TVS-X71_20260514-5.2.9.3499/qnap_i2c_command_deep_trace.log"

functions=(
    pd_sys_set_err_led
    pd_sys_set_present_led
    pd_sys_set_ident_led
    comm_sys_parse_each_i2c
    comm_sys_parse_c_i2c
    comm_sys_parse_c_i2c_start_stop
    common_sys_get_system_i2c_num
    i2c_sys_send_byte
    i2c_sys_send_command_byte
)

{
    echo "================================================================"
    echo "TRUEPANEL PROJECT STARGATE"
    echo "TVS-671 I2C Command Deep Trace"
    echo "Generated: $(date --iso-8601=seconds)"
    echo "================================================================"

    echo
    echo "===== TARGET SYMBOLS ====="

    for function in "${functions[@]}"; do
        echo
        echo "--- $function ---"

        readelf -Ws "$library" 2>/dev/null |
        awk -v target="$function" '
            $8 == target || index($8, target "@") == 1 {
                print
            }
        '
    done

    echo
    echo "===== FUNCTION DISASSEMBLY ====="

    for function in "${functions[@]}"; do
        echo
        echo "================================================"
        echo "FUNCTION: $function"
        echo "================================================"

        if readelf -Ws "$library" 2>/dev/null |
           awk -v target="$function" '
               $8 == target || index($8, target "@") == 1 {
                   found=1
               }
               END {
                   exit !found
               }
           '
        then
            objdump \
                -d \
                -M intel \
                --disassemble="$function" \
                "$library" 2>/dev/null ||
                true
        else
            echo "Symbol not present."
        fi
    done

    echo
    echo "===== I2C STRINGS AND PATHS ====="

    strings -a -t x -n 4 "$library" |
    grep -iE \
        '/dev/i2c-%d|I2C_SLAVE|I2C_SMBUS|send_command_byte|send_byte|System I2C|SYS:I2C|ERR_LED|PRESENT_LED|LOCATE_LED|failed.*i2c|open.*i2c' |
    sort -u |
    head -1200 ||
    true

    echo
    echo "===== IMPORTANT CALLS ====="

    for function in \
        pd_sys_set_err_led \
        pd_sys_set_present_led \
        pd_sys_set_ident_led \
        i2c_sys_send_command_byte \
        i2c_sys_send_byte
    do
        echo
        echo "--- CALLS FROM $function ---"

        objdump \
            -d \
            -M intel \
            --disassemble="$function" \
            "$library" 2>/dev/null |
        grep -E \
            'call|0x703|0x720|ioctl|open|write|send_byte|send_command|parse_c_i2c|get_system_i2c' ||
            true
    done

    echo
    echo "===== END REPORT ====="
} | tee "$report"

echo
echo "Saved report:"
echo "$report"
