"""
Display Widgets

Small reusable helpers for formatting LCD-friendly display elements.
"""


def clamp(value, minimum=0, maximum=100):
    return max(minimum, min(maximum, value))


def progress_bar(percent, width=10, filled="■", empty="□"):
    try:
        percent = int(round(float(percent)))
    except Exception:
        percent = 0

    percent = clamp(percent, 0, 100)
    filled_count = round((percent / 100) * width)
    empty_count = width - filled_count

    return filled * filled_count + empty * empty_count
