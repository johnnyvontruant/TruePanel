from truepanel.hardware.fans import PROFILES, apply_profile

profiles = list(PROFILES.keys())
selected_index = 0


def fan_profile_page():
    name = profiles[selected_index]
    return ["Fan Profile", f"> {name}"[:16]]


def next_profile():
    global selected_index
    selected_index = (selected_index + 1) % len(profiles)


def previous_profile():
    global selected_index
    selected_index = (selected_index - 1) % len(profiles)


def apply_selected_profile():
    apply_profile(profiles[selected_index])
    return ["Applied", profiles[selected_index][:16]]
