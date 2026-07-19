#!/usr/bin/env bash
set -u

sysroot="development/firmware/lab/TVS-X71_20260514-5.2.9.3499/sysroot"
library="$sysroot/lib64/libuLinux_hal.so"
model="$sysroot/etc/model_QW560_QW830_10_10.conf"
report="development/firmware/lab/TVS-X71_20260514-5.2.9.3499/qnap_i2c_led_trace.log"

functions=(
    GPIO_Enable_HDD_ERR_LED
    GPIO_Enable_HDD_Present_LED
    GPIO_Enable_HDD_Ident_LED
    GPIO_Enable_HDD_Active_LED
    comm_sys_parse_c_i2c
    comm_sys_parse_c_i2c_led
    common_sys_set_i2clib
    i2c_sys_write
    i2c_sys_write_byte
    i2c_sys_write_byte_data
)

{
    echo "================================================================"
    echo "TRUEPANEL PROJECT STARGATE"
    echo "TVS-671 I2C Drive LED Trace"
    echo "Generated: $(date --iso-8601=seconds)"
    echo "================================================================"

    echo
    echo "===== EXACT TVS-671 LED MAP ====="

    grep -nE \
        '^\[System Disk|ERR_LED|PRESENT_LED|LOCATE_LED' \
        "$model"

    echo
    echo "===== I2C AND SMBUS SYMBOLS ====="

    readelf -Ws "$library" 2>/dev/null |
        grep -iE \
            'i2c|smbus|I2C_SMBUS|ioctl|parse_c_i2c|set_i2c' |
        sort -k8,8 |
        head -1200 ||
        true

    echo
    echo "===== RELEVANT IMPORTS ====="

    readelf -Ws "$library" 2>/dev/null |
        awk '
            $7 == "UND" &&
            tolower($8) ~ /(i2c|smbus|ioctl|open|write)/ {
                print
            }
        ' |
        head -500 ||
        true

    echo
    echo "===== TARGET FUNCTION DISASSEMBLY ====="

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
    echo "===== I2C CONFIGURATION STRINGS ====="

    strings -a -t x -n 5 "$library" |
        grep -iE \
            'I2C:|i2c-[0-9]|/dev/i2c|I2C_SLAVE|I2C_SMBUS|write byte|write_byte|smbus|ERR_LED|PRESENT_LED|LOCATE_LED|comm_sys_parse_c_i2c' |
        sort -u |
        head -1200 ||
        true

    echo
    echo "===== CALLS FROM HDD LED FUNCTIONS ====="

    for function in \
        GPIO_Enable_HDD_ERR_LED \
        GPIO_Enable_HDD_Present_LED \
        GPIO_Enable_HDD_Ident_LED
    do
        echo
        echo "--- $function ---"

        objdump \
            -d \
            -M intel \
            --disassemble="$function" \
            "$library" 2>/dev/null |
            grep -E 'call|mov.*0x33|0x82|0x83|0x42|0x43|0x02|0x03' ||
            true
    done

    echo
    echo "===== END REPORT ====="
} | tee "$report"

echo
echo "Saved report:"
echo "$report"
