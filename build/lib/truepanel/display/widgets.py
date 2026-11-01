"""
Reusable character graphics for TruePanel.
"""

from truepanel.display.charset import glyph, sanitize


def clamp(value, minimum=0, maximum=100):
    try:
        value = float(value)
    except (TypeError, ValueError):
        value = minimum

    return max(minimum, min(maximum, value))


def progress_bar(
    percent,
    width=16,
    filled=None,
    empty=None,
    brackets=False,
):
    """
    Render a fixed-width progress bar.

    Examples:
        progress_bar(50, width=8)            -> ####----
        progress_bar(50, width=10, brackets=True) -> [####----]
    """

    width = max(1, int(width))
    filled = sanitize(filled or glyph("filled"))[:1]
    empty = sanitize(empty or glyph("empty"))[:1]

    inner_width = width - 2 if brackets and width >= 3 else width
    percent = clamp(percent)
    filled_count = int(round(inner_width * percent / 100.0))
    filled_count = max(0, min(inner_width, filled_count))

    bar = (filled * filled_count) + (empty * (inner_width - filled_count))

    if brackets and width >= 3:
        bar = f"[{bar}]"

    return bar[:width]


def labeled_bar(label, percent, width=16):
    """
    Render a compact label, meter, and percentage.

    Example:
        CPU [###---] 52
    """

    width = max(8, int(width))
    label = sanitize(label).upper()[:3]
    percent = int(round(clamp(percent)))
    percent_text = f"{percent:>3}"

    fixed_width = len(label) + 1 + 1 + len(percent_text)
    bar_width = max(1, width - fixed_width)

    return (
        f"{label} "
        f"{progress_bar(percent, width=bar_width, brackets=True)} "
        f"{percent_text}"
    )[:width]


def dual_meter(
    left_label,
    left_value,
    right_label,
    right_value,
    width=16,
):
    """
    Render two compact values on one line.

    Example:
        CPU 42% RAM 71%
    """

    left_label = sanitize(left_label).upper()[:3]
    right_label = sanitize(right_label).upper()[:3]

    left_value = int(round(clamp(left_value)))
    right_value = int(round(clamp(right_value)))

    text = (
        f"{left_label} {left_value:>2}% "
        f"{right_label} {right_value:>2}%"
    )

    return text[:width]


def activity_meter(value, maximum=100, width=8):
    """
    Render a three-level activity meter.

    Unlike a standard progress bar, the active section changes character near
    the upper ranges, giving the LCD a little visual pulse.
    """

    width = max(1, int(width))

    try:
        maximum = float(maximum)
    except (TypeError, ValueError):
        maximum = 100.0

    if maximum <= 0:
        maximum = 100.0

    normalized = clamp((float(value or 0) / maximum) * 100.0)
    active = int(round(width * normalized / 100.0))
    active = max(0, min(width, active))

    if normalized >= 75:
        active_char = glyph("activity_high")
    elif normalized >= 35:
        active_char = glyph("activity_mid")
    else:
        active_char = glyph("activity_low")

    return (
        active_char * active
        + glyph("empty") * (width - active)
    )


def sparkline(values, width=8):
    """
    Render a tiny ASCII trend line from historical numeric values.

    Character displays cannot draw true vertical bars, so values are converted
    into four visual levels.
    """

    width = max(1, int(width))

    if not values:
        return glyph("empty") * width

    numeric = []

    for value in values[-width:]:
        try:
            numeric.append(float(value))
        except (TypeError, ValueError):
            numeric.append(0.0)

    low = min(numeric)
    high = max(numeric)
    spread = high - low

    levels = "._=#"

    if spread <= 0:
        rendered = levels[1] * len(numeric)
    else:
        rendered = ""

        for value in numeric:
            ratio = (value - low) / spread
            index = min(len(levels) - 1, int(ratio * len(levels)))
            rendered += levels[index]

    return rendered.rjust(width, glyph("empty"))[-width:]


def status_icon(priority):
    """Return a simple LCD-safe status marker."""

    try:
        numeric = int(priority)
    except (TypeError, ValueError):
        numeric = 0

    if numeric >= 100:
        return glyph("critical")
    if numeric >= 70:
        return glyph("warning")
    if numeric >= 40:
        return glyph("info")

    return glyph("healthy")


def spinner(frame=0):
    frames = [
        glyph("spinner_0"),
        glyph("spinner_1"),
        glyph("spinner_2"),
        glyph("spinner_3"),
    ]

    return frames[int(frame) % len(frames)]
