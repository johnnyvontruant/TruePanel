#!/usr/bin/env bash
set -u

pci_device="/sys/bus/pci/devices/0000:00:1f.3"
pci_driver="/sys/bus/pci/drivers/i801_smbus"
report="development/firmware/lab/TVS-X71_20260514-5.2.9.3499/i801_adapter_autopsy.log"

{
    echo "================================================================"
    echo "TRUEPANEL PROJECT STARGATE"
    echo "Intel I801 SMBus Adapter Autopsy"
    echo "Generated: $(date --iso-8601=seconds)"
    echo "================================================================"

    echo
    echo "===== PCI DEVICE ====="
    lspci -nnk -vv -s 00:1f.3 2>&1 || true

    echo
    echo "===== PCI DRIVER LINK ====="

    if [[ -L "$pci_device/driver" ]]; then
        ls -l "$pci_device/driver"
        echo "Resolved: $(readlink -f "$pci_device/driver")"
    else
        echo "No driver link found."
    fi

    echo
    echo "===== PCI DEVICE ATTRIBUTES ====="

    for attribute in \
        enable \
        class \
        vendor \
        device \
        subsystem_vendor \
        subsystem_device \
        irq \
        power/control \
        power/runtime_status
    do
        candidate="$pci_device/$attribute"

        if [[ -r "$candidate" ]]; then
            printf '%-24s ' "$attribute:"
            cat "$candidate"
        fi
    done

    echo
    echo "===== PCI DEVICE CHILDREN ====="

    if [[ -d "$pci_device" ]]; then
        find "$pci_device" \
            -mindepth 1 \
            -maxdepth 3 \
            -printf '%y %p -> %l\n' 2>/dev/null |
        sort
    else
        echo "Missing PCI sysfs device: $pci_device"
    fi

    echo
    echo "===== I801 DRIVER DIRECTORY ====="

    if [[ -d "$pci_driver" ]]; then
        find "$pci_driver" \
            -mindepth 1 \
            -maxdepth 2 \
            -printf '%y %p -> %l\n' 2>/dev/null |
        sort
    else
        echo "Missing driver directory: $pci_driver"
    fi

    echo
    echo "===== I2C SYSFS CLASSES ====="

    find /sys/class \
        -mindepth 1 \
        -maxdepth 1 \
        -iname '*i2c*' \
        -printf '%y %p -> %l\n' 2>/dev/null |
    sort

    echo
    echo "===== I2C BUS RECORDS ====="

    if [[ -d /sys/bus/i2c ]]; then
        find /sys/bus/i2c \
            -mindepth 1 \
            -maxdepth 3 \
            -printf '%y %p -> %l\n' 2>/dev/null |
        sort
    else
        echo "/sys/bus/i2c does not exist."
    fi

    echo
    echo "===== I2C ADAPTERS ANYWHERE IN SYSFS ====="

    find /sys/devices \
        -type d \
        -name 'i2c-*' \
        -printf '%p\n' 2>/dev/null |
    sort

    echo
    echo "===== I2C DEVICE NODES ====="

    find /dev \
        -maxdepth 1 \
        \( -name 'i2c-*' -o -name 'i2c*' \) \
        -printf '%m %u:%g %p\n' 2>/dev/null |
    sort

    echo
    echo "===== LOADED MODULES ====="

    lsmod |
    grep -E '^(i2c_dev|i2c_i801|i2c_smbus|i2c_core)' ||
    true

    echo
    echo "===== I801 MODULE PARAMETERS ====="

    if [[ -d /sys/module/i2c_i801/parameters ]]; then
        find /sys/module/i2c_i801/parameters \
            -type f \
            -maxdepth 1 \
            -print 2>/dev/null |
        sort |
        while IFS= read -r parameter; do
            printf '%-40s ' "$(basename "$parameter")"
            cat "$parameter" 2>/dev/null || echo "unreadable"
        done
    else
        echo "No i2c_i801 parameter directory."
    fi

    echo
    echo "===== PCI CONFIGURATION SPACE ====="
    lspci -xxx -s 00:1f.3 2>&1 || true

    echo
    echo "===== SMBUS KERNEL MESSAGES ====="

    dmesg --color=never 2>&1 |
    grep -iE \
        'i801|smbus|i2c|00:1f\.3|resource conflict|acpi.*resource|host.*disabled|adapter' |
    tail -300 ||
    true

    echo
    echo "===== END REPORT ====="
} | tee "$report"

echo
echo "Saved report:"
echo "$report"
