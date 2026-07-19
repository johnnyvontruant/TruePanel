#!/bin/bash
set -u

GPIO_SYS=/sys/class/gpio
OUTPUT=development/beacon/gpio_passive_map.txt

declare -a BANKS=(
  "512 6 0"
  "518 8 1"
  "526 8 2"
  "534 8 3"
  "542 8 4"
  "550 5 5"
  "555 8 6"
  "563 8 7"
)

cleanup() {
    for gpio_dir in "$GPIO_SYS"/gpio[0-9]*; do
        [ -e "$gpio_dir" ] || continue
        gpio=${gpio_dir##*gpio}
        echo "$gpio" > "$GPIO_SYS/unexport" 2>/dev/null || true
    done
}

trap cleanup EXIT INT TERM

{
    echo "Project Beacon GPIO Passive State Map"
    echo "Timestamp: $(date --iso-8601=seconds)"
    echo
    printf "%-7s %-7s %-8s %-10s %-7s %-7s %-8s\n" \
        "GPIO" "Name" "Bank" "Direction" "Value1" "Value2" "Changed"
    printf '%0.s-' {1..66}
    echo

    for bank_spec in "${BANKS[@]}"; do
        read -r base count group <<< "$bank_spec"

        for ((offset=0; offset<count; offset++)); do
            gpio=$((base + offset))
            logical_name="GPIO${group}${offset}"
            gpio_dir="$GPIO_SYS/gpio$gpio"

            if [ ! -d "$gpio_dir" ]; then
                echo "$gpio" > "$GPIO_SYS/export" 2>/dev/null || true

                for attempt in {1..20}; do
                    [ -d "$gpio_dir" ] && break
                    sleep 0.01
                done
            fi

            if [ ! -d "$gpio_dir" ]; then
                printf "%-7s %-7s %-8s %-10s %-7s %-7s %-8s\n" \
                    "$gpio" "$logical_name" "$group" \
                    "BUSY" "-" "-" "-"
                continue
            fi

            direction=$(cat "$gpio_dir/direction" 2>/dev/null || echo "?")
            value1=$(cat "$gpio_dir/value" 2>/dev/null || echo "?")
            sleep 0.25
            value2=$(cat "$gpio_dir/value" 2>/dev/null || echo "?")

            if [ "$value1" = "$value2" ]; then
                changed="no"
            else
                changed="YES"
            fi

            printf "%-7s %-7s %-8s %-10s %-7s %-7s %-8s\n" \
                "$gpio" "$logical_name" "$group" \
                "$direction" "$value1" "$value2" "$changed"

            echo "$gpio" > "$GPIO_SYS/unexport" 2>/dev/null || true
        done
    done
} | tee "$OUTPUT"
