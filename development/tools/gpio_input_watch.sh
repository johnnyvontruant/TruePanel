#!/bin/bash
set -u

GPIO_SYS=/sys/class/gpio
OUTPUT="${1:-development/beacon/gpio_input_events.txt}"
DURATION="${2:-60}"
INTERVAL="${3:-0.05}"

INPUTS=(
    512 513 514 515 516 517
    518 519 520 521 522 523 524 525
    526 527 528 529 530 531 532 533
    542 543 544 545 546 547 548 549
    559 560 561 562
    563 564 567 568 569 570
)

declare -A EXPORTED_BY_US
declare -A LAST
declare -A NAMES

gpio_name() {
    case "$1" in
        512) echo GPIO00;; 513) echo GPIO01;; 514) echo GPIO02;;
        515) echo GPIO03;; 516) echo GPIO04;; 517) echo GPIO05;;

        518) echo GPIO10;; 519) echo GPIO11;; 520) echo GPIO12;;
        521) echo GPIO13;; 522) echo GPIO14;; 523) echo GPIO15;;
        524) echo GPIO16;; 525) echo GPIO17;;

        526) echo GPIO20;; 527) echo GPIO21;; 528) echo GPIO22;;
        529) echo GPIO23;; 530) echo GPIO24;; 531) echo GPIO25;;
        532) echo GPIO26;; 533) echo GPIO27;;

        542) echo GPIO40;; 543) echo GPIO41;; 544) echo GPIO42;;
        545) echo GPIO43;; 546) echo GPIO44;; 547) echo GPIO45;;
        548) echo GPIO46;; 549) echo GPIO47;;

        559) echo GPIO64;; 560) echo GPIO65;;
        561) echo GPIO66;; 562) echo GPIO67;;

        563) echo GPIO70;; 564) echo GPIO71;;
        567) echo GPIO74;; 568) echo GPIO75;;
        569) echo GPIO76;; 570) echo GPIO77;;

        *) echo "GPIO?";;
    esac
}

cleanup() {
    for gpio in "${!EXPORTED_BY_US[@]}"; do
        echo "$gpio" > "$GPIO_SYS/unexport" 2>/dev/null || true
    done
}

trap cleanup EXIT INT TERM

for gpio in "${INPUTS[@]}"; do
    path="$GPIO_SYS/gpio$gpio"

    if [ ! -d "$path" ]; then
        if echo "$gpio" > "$GPIO_SYS/export" 2>/dev/null; then
            EXPORTED_BY_US["$gpio"]=1
        fi

        for attempt in {1..20}; do
            [ -d "$path" ] && break
            sleep 0.01
        done
    fi

    if [ ! -d "$path" ]; then
        echo "Unable to access GPIO $gpio" >&2
        continue
    fi

    direction=$(cat "$path/direction" 2>/dev/null || echo unknown)

    if [ "$direction" != "in" ]; then
        echo "Skipping GPIO $gpio: direction is $direction" >&2
        continue
    fi

    NAMES["$gpio"]="$(gpio_name "$gpio")"
    LAST["$gpio"]="$(cat "$path/value" 2>/dev/null || echo '?')"
done

{
    echo "Project Beacon GPIO Input Watch"
    echo "Started: $(date --iso-8601=seconds)"
    echo "Duration: ${DURATION}s"
    echo "Interval: ${INTERVAL}s"
    echo
    echo "Operate one physical control at a time."
    echo "Timestamp                         GPIO    Name     Old  New"
    echo "----------------------------------------------------------"
} | tee "$OUTPUT"

end=$((SECONDS + DURATION))

while [ "$SECONDS" -lt "$end" ]; do
    for gpio in "${!LAST[@]}"; do
        path="$GPIO_SYS/gpio$gpio"
        current=$(cat "$path/value" 2>/dev/null || echo '?')
        previous="${LAST[$gpio]}"

        if [ "$current" != "$previous" ]; then
            printf '%-33s %-7s %-8s %-4s %-4s\n' \
                "$(date --iso-8601=ns)" \
                "$gpio" \
                "${NAMES[$gpio]}" \
                "$previous" \
                "$current" | tee -a "$OUTPUT"

            LAST["$gpio"]="$current"
        fi
    done

    sleep "$INTERVAL"
done

{
    echo
    echo "Finished: $(date --iso-8601=seconds)"
} | tee -a "$OUTPUT"
