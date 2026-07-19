#!/usr/bin/env bash
set -euo pipefail

fwdir="development/firmware/decrypted/TVS-X71_20260514-5.2.9.3499"
lab="development/firmware/lab/TVS-X71_20260514-5.2.9.3499"
sysroot="$lab/sysroot"
report="$lab/qnap_hal_hunt.log"

if [[ ! -d "$sysroot" ]]; then
    echo "Sysroot does not exist:"
    echo "  $sysroot"
    exit 1
fi

if [[ ! -f "$fwdir/rootfs_ext.tgz" ]]; then
    echo "Missing rootfs extension:"
    echo "  $fwdir/rootfs_ext.tgz"
    exit 1
fi

{
    echo "================================================================"
    echo "TRUEPANEL PROJECT STARGATE"
    echo "QNAP TVS-X71 HAL Hunt"
    echo "Generated: $(date --iso-8601=seconds)"
    echo "================================================================"

    echo
    echo "===== BEFORE ROOTFS_EXT ====="
    printf 'Files:       '
    find "$sysroot" -type f 2>/dev/null | wc -l

    printf 'Directories: '
    find "$sysroot" -type d 2>/dev/null | wc -l

    echo
    echo "===== ROOTFS_EXT TYPE ====="
    file "$fwdir/rootfs_ext.tgz"

    echo
    echo "===== EXTRACTING ROOTFS_EXT ====="
    tar -xzf "$fwdir/rootfs_ext.tgz" -C "$sysroot"
    echo "Extraction complete."

    echo
    echo "===== AFTER ROOTFS_EXT ====="
    printf 'Files:       '
    find "$sysroot" -type f 2>/dev/null | wc -l

    printf 'Directories: '
    find "$sysroot" -type d 2>/dev/null | wc -l

    echo
    echo "===== EXACT HAL AND PLATFORM FILENAMES ====="

    find "$sysroot" \
        \( -type f -o -type l \) \
        \( \
            -name 'hal_app' -o \
            -name 'hal_daemon' -o \
            -name 'libuLinux_hal.so' -o \
            -name 'libuLinux_hal.so.*' -o \
            -name 'model.conf' -o \
            -name 'platform.conf' -o \
            -name 'hal.conf' -o \
            -name 'uLinux.conf' -o \
            -iname '*f71869*' -o \
            -iname '*fintek*' \
        \) \
        -printf '%y %m %10s %p -> %l\n' 2>/dev/null |
        sort

    echo
    echo "===== LIKELY QNAP HARDWARE BINARIES ====="

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
            -iname '*led*' -o \
            -iname '*gpio*' -o \
            -iname '*sio*' -o \
            -iname '*enclosure*' \
        \) \
        -printf '%m %10s %p\n' 2>/dev/null |
        sort |
        head -500

    echo
    echo "===== PRECISE HARDWARE STRING MATCHES ====="

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
            -name '*.so.*' -o \
            -name '*.conf' -o \
            -name '*.cfg' \
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
            strings -a -n 6 "$file" 2>/dev/null |
            grep -iE \
                'TVS-671|TVS-X71|F71869A?|Fintek|Super.?IO|SIO:I[0-9A-F]{2}|disk[_ -]?led|hdd[_ -]?led|status[_ -]?led|fault[_ -]?led|locate[_ -]?led|led[_ -]?value|A125|/sbin/hal_app|--se_.*led' |
            cut -c1-240 |
            head -40 ||
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
    echo "===== MODEL AND PLATFORM CONFIG REFERENCES ====="

    find "$sysroot" \
        -type f \
        -size -10M \
        ! -path '*/home/httpd/*' \
        -print0 2>/dev/null |
    while IFS= read -r -d '' file; do
        matches="$(
            grep -aEin \
                'TVS-671|TVS-X71|System IO|STATUS.*LED|DISK.*LED|HDD.*LED|F71869|Fintek' \
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
    echo "===== END REPORT ====="
} | tee "$report"

echo
echo "Saved report:"
echo "$report"
