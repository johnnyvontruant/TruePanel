#!/usr/bin/env bash
set -euo pipefail

# ================================================================
# TruePanel Project Stargate
# QNAP LCD / A125 / LCM Firmware Hunt
#
# qnap_hal_hunt.sh already searches the extracted TVS-X71 sysroot
# for LED, GPIO, and Super I/O material. This script searches the
# SAME already-extracted sysroot for the LCD/front-panel side of
# the HAL instead: the binaries and strings most likely to contain
# the real A125 command table, including any CGRAM/custom-character
# opcode that has not been found through serial probing.
#
# This does not extract firmware and does not touch the A125 serial
# controller. It only reads files already produced by
# qnap_hal_hunt.sh / qnap_firmware_census.sh.
# ================================================================

fwdir="development/firmware/decrypted/TVS-X71_20260514-5.2.9.3499"
lab="development/firmware/lab/TVS-X71_20260514-5.2.9.3499"
sysroot="$lab/sysroot"
report="$lab/qnap_lcd_hal_hunt.log"

if [[ ! -d "$sysroot" ]]; then
    echo "Sysroot does not exist:"
    echo "  $sysroot"
    echo
    echo "Run qnap_hal_hunt.sh first (or extract $fwdir/rootfs_ext.tgz"
    echo "into $sysroot yourself) before running this tool."
    exit 1
fi

if [[ -z "$(find "$sysroot" -maxdepth 1 -mindepth 1 2>/dev/null)" ]]; then
    echo "Sysroot is empty:"
    echo "  $sysroot"
    echo
    echo "Run qnap_hal_hunt.sh first so the rootfs is extracted."
    exit 1
fi

{
    echo "================================================================"
    echo "TRUEPANEL PROJECT STARGATE"
    echo "QNAP LCD / A125 / LCM Hunt"
    echo "Generated: $(date --iso-8601=seconds)"
    echo "================================================================"

    echo
    echo "===== SYSROOT SUMMARY ====="
    printf 'Files:       '
    find "$sysroot" -type f 2>/dev/null | wc -l
    printf 'Directories: '
    find "$sysroot" -type d 2>/dev/null | wc -l

    echo
    echo "===== EXACT LCD / PANEL / A125 FILENAMES ====="
    echo "(QNAP's own documentation calls the physical connector"
    echo " 'COM2 LCM' -- LCM material is included alongside LCD/panel.)"

    find "$sysroot" \
        \( -type f -o -type l \) \
        \( \
            -name 'hal_app' -o \
            -name 'hal_daemon' -o \
            -name 'libuLinux_hal.so' -o \
            -name 'libuLinux_hal.so.*' -o \
            -name 'lcd_tool' -o \
            -name 'lcdd' -o \
            -name 'lcd_app' -o \
            -iname '*lcm*' -o \
            -iname '*a125*' -o \
            -iname '*a106*' -o \
            -iname '*panelapp*' -o \
            -iname '*frontpanel*' -o \
            -iname '*front_panel*' -o \
            -iname '*fp_lcd*' -o \
            -iname '*qpanel*' -o \
            -iname '*buzzer*' \
        \) \
        -printf '%y %m %10s %p -> %l\n' 2>/dev/null |
        sort

    echo
    echo "===== LIKELY LCD / DISPLAY BINARIES (by path + name) ====="

    find "$sysroot" \
        -type f \
        \( \
            -path '*/sbin/*' -o \
            -path '*/bin/*' -o \
            -path '*/lib/*' -o \
            -path '*/lib64/*' \
        \) \
        \( \
            -iname '*hal*' -o \
            -iname '*lcd*' -o \
            -iname '*lcm*' -o \
            -iname '*panel*' -o \
            -iname '*display*' -o \
            -iname '*icp*' -o \
            -iname '*buzzer*' \
        \) \
        -printf '%m %10s %p\n' 2>/dev/null |
        sort |
        head -500

    echo
    echo "===== CONFIG FILES REFERENCING LCD / LCM / PANEL ====="

    find "$sysroot" \
        -type f \
        \( \
            -name '*.conf' -o \
            -name '*.cfg' -o \
            -name '*.ini' \
        \) \
        -size -10M \
        -print0 2>/dev/null |
    while IFS= read -r -d '' file; do
        matches="$(
            grep -aEin \
                'LCD|LCM|A125|A106|Panel|BackLight|Buzzer|COM2|ttyS1' \
                "$file" 2>/dev/null |
            cut -c1-260 |
            head -30 ||
            true
        )"

        if [[ -n "$matches" ]]; then
            echo
            echo "FILE: $file"
            printf '%s\n' "$matches"
        fi
    done

    echo
    echo "===== STRING MATCHES IN BINARIES / LIBRARIES ====="
    echo "(command-table and opcode literals, not just filenames)"

    find "$sysroot" \
        -type f \
        -size -80M \
        ! -path '*/home/httpd/*' \
        ! -path '*/www/*' \
        ! -path '*/share/doc/*' \
        ! -path '*/share/locale/*' \
        \( \
            -perm /111 -o \
            -name '*.so' -o \
            -name '*.so.*' \
        \) \
        -print0 2>/dev/null |
    while IFS= read -r -d '' file; do
        kind="$(file -b "$file" 2>/dev/null || true)"

        case "$kind" in
            *ELF*|*ASCII*|*Unicode*|*script*|*text*)
                ;;
            *)
                continue
                ;;
        esac

        matches="$(
            strings -a -n 5 "$file" 2>/dev/null |
            grep -iE \
                'A125|A106|\bLCM\b|front.?panel|/dev/ttyS1|CGRAM|user.?defined.?char|custom.?char|define.?char|glyph|lcd_tool|se_lcd|se_buzzer|se_panel|auto.?display|panel.?display' |
            cut -c1-240 |
            head -60 ||
            true
        )"

        if [[ -n "$matches" ]]; then
            echo
            echo "FILE: $file"
            echo "TYPE: $kind"
            printf '%s\n' "$matches"
        fi
    done

    echo
    echo "===== hal_app / hal_daemon EXPORTED SYMBOL NAMES ====="
    echo "(GPIO_Does_Copy_Button_Press-style function names have"
    echo " previously revealed hardware call paths on other models --"
    echo " looking for an LCD/CGRAM/glyph equivalent here.)"

    find "$sysroot" \
        \( -name 'hal_app' -o -name 'hal_daemon' -o -name 'libuLinux_hal.so*' \) \
        -type f \
        -print0 2>/dev/null |
    while IFS= read -r -d '' file; do
        symbols="$(
            { nm -D --defined-only "$file" 2>/dev/null ||
              objdump -T "$file" 2>/dev/null; } |
            grep -iE 'lcd|lcm|panel|a125|a106|cgram|glyph|char|display|buzzer' |
            cut -c1-200 |
            head -80 ||
            true
        )"

        if [[ -n "$symbols" ]]; then
            echo
            echo "FILE: $file"
            printf '%s\n' "$symbols"
        fi
    done

    echo
    echo "===== END REPORT ====="
} | tee "$report"

echo
echo "Saved report:"
echo "$report"
echo
echo "Next step: any ELF file that shows up in the string-match or"
echo "symbol sections above is a candidate for"
echo "a125_opcode_byte_scanner.py, which looks for the 0x4D host"
echo "preamble byte directly in the binary and tallies the opcode"
echo "bytes that follow it."
