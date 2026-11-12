from __future__ import annotations

from truepanel.loadmaster.plan import build_plan, pending_to_usb
from truepanel.loadmaster.scan import Fingerprint

T = 1_700_000_000_000_000_000
HOUR = 3600 * 10**9


def fp(size: int, mtime: int = T) -> Fingerprint:
    return Fingerprint(size, mtime)


def plan(nas, usb, record=None, **kwargs):
    return build_plan(drive_name="TV A-M", nas=nas, usb=usb, record=record, **kwargs)


def ops(result):
    return [(a["op"], a["path"], a["reason"]) for a in result["actions"]]


def test_identical_is_clear():
    files = {"Show/S01E01.mkv": fp(10)}
    result = plan(files, dict(files), dict(files))
    assert result["state"] == "CLEAR"
    assert result["summary"]["in_sync_files"] == 1


def test_first_sync_copies_both_ways_and_never_deletes():
    result = plan(
        {"a/new-on-nas.mkv": fp(1), "both.mkv": fp(2)},
        {"b/new-on-usb.mkv": fp(3), "both.mkv": fp(2)},
        record=None,
    )
    assert result["first_sync"] is True
    assert ops(result) == [
        ("to_usb", "a/new-on-nas.mkv", "NEW_ON_NAS"),
        ("to_nas", "b/new-on-usb.mkv", "NEW_ON_USB"),
    ]


def test_sonarr_import_goes_to_usb():
    record = {"Show/S01E01.mkv": fp(10)}
    nas = {**record, "Show/S01E02.mkv": fp(11)}
    result = plan(nas, dict(record), record)
    assert ops(result) == [("to_usb", "Show/S01E02.mkv", "NEW_ON_NAS")]


def test_radarr_upgrade_mirrors_to_usb_and_removes_old():
    record = {"Heat (1995)/Heat 720p.mkv": fp(5)}
    nas = {"Heat (1995)/Heat 2160p.mkv": fp(50)}
    result = plan(nas, dict(record), record)
    assert ops(result) == [
        ("delete_usb", "Heat (1995)/Heat 720p.mkv", "REMOVED_FROM_NAS"),
        ("to_usb", "Heat (1995)/Heat 2160p.mkv", "NEW_ON_NAS"),
    ]


def test_same_name_upgrade_on_nas_overwrites_usb():
    record = {"Heat (1995)/Heat.mkv": fp(5)}
    nas = {"Heat (1995)/Heat.mkv": fp(50, T + HOUR)}
    result = plan(nas, dict(record), record)
    assert ops(result) == [("to_usb", "Heat (1995)/Heat.mkv", "UPDATED_ON_NAS")]


def test_laptop_upgrade_with_same_name_comes_to_nas():
    record = {"Heat (1995)/Heat.mkv": fp(5)}
    usb = {"Heat (1995)/Heat.mkv": fp(50, T + HOUR)}
    result = plan(dict(record), usb, record)
    assert ops(result) == [("to_nas", "Heat (1995)/Heat.mkv", "UPDATED_ON_USB")]


def test_laptop_upgrade_with_new_name_retires_old_nas_file():
    old, new = "Heat (1995)/Heat 720p.mkv", "Heat (1995)/Heat 2160p.mkv"
    record = {old: fp(5), "Heat (1995)/Heat.srt": fp(1)}
    nas = dict(record)
    usb = {new: fp(50), "Heat (1995)/Heat.srt": fp(1)}
    result = plan(nas, usb, record)
    assert ops(result) == [
        ("to_nas", new, "NEW_ON_USB"),
        ("retire_nas", old, "REPLACED_ON_USB"),
    ]


def test_tv_laptop_upgrade_only_retires_the_matching_episode():
    record = {
        "Show/Season 1/Show S01E03 720p.mkv": fp(3),
        "Show/Season 1/Show S01E05 720p.mkv": fp(5),
    }
    usb = {
        "Show/Season 1/Show S01E05 1080p.mkv": fp(55),
    }
    result = plan(dict(record), usb, record)
    assert ops(result) == [
        ("to_usb", "Show/Season 1/Show S01E03 720p.mkv", "MISSING_ON_USB"),
        ("to_nas", "Show/Season 1/Show S01E05 1080p.mkv", "NEW_ON_USB"),
        ("retire_nas", "Show/Season 1/Show S01E05 720p.mkv", "REPLACED_ON_USB"),
    ]


def test_file_deleted_from_usb_alone_is_restored():
    record = {"Elf (2003)/Elf.mkv": fp(5)}
    result = plan(dict(record), {}, record)
    assert ops(result) == [("to_usb", "Elf (2003)/Elf.mkv", "MISSING_ON_USB")]


def test_both_changed_newest_wins():
    record = {"x.mkv": fp(1)}
    nas = {"x.mkv": fp(2, T + HOUR)}
    usb = {"x.mkv": fp(3, T + 2 * HOUR)}
    assert ops(plan(nas, usb, record)) == [("to_nas", "x.mkv", "NEWER_ON_USB")]
    usb = {"x.mkv": fp(3, T + HOUR // 2)}
    assert ops(plan(nas, usb, record)) == [("to_usb", "x.mkv", "NEWER_ON_NAS")]


def test_no_record_differing_files_newest_wins():
    result = plan({"x.mkv": fp(2, T)}, {"x.mkv": fp(3, T + HOUR)}, None)
    assert ops(result) == [("to_nas", "x.mkv", "NEWER_ON_USB")]


def test_same_age_different_size_is_a_conflict():
    result = plan({"x.mkv": fp(2, T)}, {"x.mkv": fp(3, T + 10**9)}, None)
    assert result["state"] == "HOLD"
    assert result["conflicts"][0]["reason"] == "SAME_AGE_DIFFERENT_SIZE"


def test_mtime_within_two_seconds_is_in_sync():
    result = plan({"x.mkv": fp(2, T)}, {"x.mkv": fp(2, T + 2 * 10**9)}, None)
    assert result["state"] == "CLEAR"


def test_empty_nas_folder_holds_instead_of_deleting_everything():
    record = {f"m{i}.mkv": fp(i) for i in range(5)}
    result = plan({}, dict(record), record)
    assert result["state"] == "HOLD"
    assert "mounted" in result["reason"]
    assert result["actions"] == []


def test_large_removals_need_confirmation():
    record = {f"m{i}.mkv": fp(i) for i in range(10)}
    nas = {"keep.mkv": fp(1)}
    record["keep.mkv"] = fp(1)
    result = plan(nas, dict(record), record, large_delete_files=5)
    assert result["state"] == "READY"
    assert result["needs_confirmation"] is True
    assert result["summary"]["delete_usb_files"] == 10


def test_names_illegal_on_exfat_are_skipped_with_notice():
    result = plan({"What? (2020)/What?.mkv": fp(1)}, {}, None, usb_fstype="exfat")
    assert result["actions"] == []
    assert result["notices"][0]["reason"] == "NAME_NOT_STORABLE_ON_USB"
    assert plan({"What? (2020)/What?.mkv": fp(1)}, {}, None, usb_fstype="ext4")[
        "actions"
    ]


def test_case_only_rename_on_nas_is_in_sync_on_exfat():
    nas = {"Modern Family (2009)/1x21 - Travels.mp4": fp(7)}
    usb = {"Modern Family (2009)/1X21 - Travels.mp4": fp(7)}
    for record in (None, dict(usb)):
        result = plan(nas, usb, record, usb_fstype="exfat")
        assert result["actions"] == []
        assert result["state"] == "CLEAR"
        assert list(result["in_sync"]) == ["Modern Family (2009)/1x21 - Travels.mp4"]
        assert result["notices"] == [
            {
                "path": "Modern Family (2009)/1x21 - Travels.mp4",
                "reason": "CASE_DIFFERS_ON_USB",
                "usb_path": "Modern Family (2009)/1X21 - Travels.mp4",
            }
        ]
    # The record keeps the old spelling only until this sync rewrites it.
    result = plan(nas, usb, dict(usb), usb_fstype="exfat")
    assert result["forget"] == ["Modern Family (2009)/1X21 - Travels.mp4"]


def test_case_is_significant_on_case_sensitive_drives():
    result = plan({"a/1x01.srt": fp(1)}, {"a/1X01.srt": fp(1)}, None, usb_fstype="ext4")
    assert ops(result) == [
        ("to_usb", "a/1x01.srt", "NEW_ON_NAS"),
        ("to_nas", "a/1X01.srt", "NEW_ON_USB"),
    ]


def test_case_twin_actions_carry_the_drive_spelling():
    record = {"a/1X01.mkv": fp(1), "a/1X02.mkv": fp(2), "keep.mkv": fp(3)}
    nas = {"a/1x01.mkv": fp(9, T + HOUR), "keep.mkv": fp(3)}
    usb = {"A/1X01.mkv": fp(1), "A/1X02.mkv": fp(2), "keep.mkv": fp(3)}
    result = plan(nas, usb, record, usb_fstype="exfat")
    actions = {
        a["path"]: (a["op"], a["reason"], a["usb_path"]) for a in result["actions"]
    }
    assert actions == {
        "a/1X02.mkv": ("delete_usb", "REMOVED_FROM_NAS", "A/1X02.mkv"),
        "a/1x01.mkv": ("to_usb", "UPDATED_ON_NAS", "A/1X01.mkv"),
    }


def test_two_nas_names_for_one_drive_name_copy_once():
    nas = {"a/Pilot.mkv": fp(1), "a/pilot.mkv": fp(2)}
    result = plan(nas, {}, None, usb_fstype="exfat")
    assert ops(result) == [("to_usb", "a/Pilot.mkv", "NEW_ON_NAS")]
    assert result["notices"] == [
        {"path": "a/pilot.mkv", "reason": "NAME_DIFFERS_ONLY_BY_CASE_ON_NAS"}
    ]


DARIA = ("Daria (1997)",)


def protected_ops(result):
    return sorted(
        (n["path"], n["would"]) for n in result["notices"] if n["reason"] == "PROTECTED"
    )


def test_protected_folder_only_fills_gaps_on_the_drive():
    nas = {"Daria (1997)/S01E01.mkv": fp(1), "Other/S01E01.mkv": fp(2)}
    usb = {"Daria (1997)/Fan cut.mkv": fp(3), "Other/New.mkv": fp(4)}
    result = plan(nas, usb, None, protected=DARIA)
    assert ops(result) == [
        ("to_usb", "Daria (1997)/S01E01.mkv", "NEW_ON_NAS"),
        ("to_usb", "Other/S01E01.mkv", "NEW_ON_NAS"),
        ("to_nas", "Other/New.mkv", "NEW_ON_USB"),
    ]
    assert protected_ops(result) == [("Daria (1997)/Fan cut.mkv", "to_nas NEW_ON_USB")]


def test_protected_folder_is_never_overwritten_retired_or_deleted():
    record = {
        "daria (1997)/S01E01.mkv": fp(1),
        "Daria (1997)/S01E02.mkv": fp(2),
        "Daria (1997)/S01E03.mkv": fp(3),
        "Daria (1997)/S01E04.mkv": fp(4),
        "keep.mkv": fp(9),
    }
    nas = {
        "daria (1997)/S01E01.mkv": fp(10, T + HOUR),  # changed on the NAS
        "Daria (1997)/S01E02.mkv": fp(2),
        "Daria (1997)/S01E04.mkv": fp(4),
        "keep.mkv": fp(9),
    }  # S01E03 removed from the NAS
    usb = {
        "daria (1997)/S01E01.mkv": fp(1),
        "Daria (1997)/S01E02.mkv": fp(20, T + HOUR),  # changed on the drive
        "Daria (1997)/S01E03.mkv": fp(3),
        "Daria (1997)/S01E04 Remux.mkv": fp(40),  # replaced on the laptop
        "keep.mkv": fp(9),
    }
    result = plan(nas, usb, record, protected=DARIA)
    assert result["actions"] == []
    assert protected_ops(result) == [
        ("Daria (1997)/S01E02.mkv", "to_nas UPDATED_ON_USB"),
        ("Daria (1997)/S01E03.mkv", "delete_usb REMOVED_FROM_NAS"),
        ("Daria (1997)/S01E04 Remux.mkv", "to_nas NEW_ON_USB"),
        ("Daria (1997)/S01E04.mkv", "retire_nas REPLACED_ON_USB"),
        ("daria (1997)/S01E01.mkv", "to_usb UPDATED_ON_NAS"),
    ]


def test_protected_folder_restores_a_missing_drive_copy():
    record = {"Daria (1997)/S01E01.mkv": fp(1)}
    result = plan(dict(record), {}, record, protected=DARIA)
    assert ops(result) == [("to_usb", "Daria (1997)/S01E01.mkv", "MISSING_ON_USB")]


def test_radarr_upgrade_the_drive_never_saw_is_not_doubled():
    # Torn Curtain on Movies T-Z: Radarr replaced the AVI on the NAS before the
    # drive's first sync. Copying both ways would put both on both sides.
    nas = {"Torn Curtain (1966)/Torn Curtain (1966).mp4": fp(8, T + HOUR)}
    usb = {"Torn Curtain (1966)/Torn Curtain (1966).avi": fp(1)}
    result = plan(nas, usb, None, usb_fstype="exfat")
    assert result["actions"] == []
    assert sorted((n["reason"], n["path"], n["other"]) for n in result["notices"]) == [
        (
            "TWO_VERSIONS_NAS",
            "Torn Curtain (1966)/Torn Curtain (1966).mp4",
            ["Torn Curtain (1966)/Torn Curtain (1966).avi"],
        ),
        (
            "TWO_VERSIONS_USB",
            "Torn Curtain (1966)/Torn Curtain (1966).avi",
            ["Torn Curtain (1966)/Torn Curtain (1966).mp4"],
        ),
    ]


def test_two_versions_is_per_episode_and_ignores_other_files():
    nas = {"Show/S01E01.mkv": fp(1), "Show/S01E02.mkv": fp(2), "Show/S01E02.nfo": fp(3)}
    usb = {"Show/S01E01 Remux.mkv": fp(9), "Show/S01E03.mkv": fp(4)}
    result = plan(nas, usb, None)
    assert ops(result) == [
        ("to_usb", "Show/S01E02.mkv", "NEW_ON_NAS"),
        ("to_usb", "Show/S01E02.nfo", "NEW_ON_NAS"),
        ("to_nas", "Show/S01E03.mkv", "NEW_ON_USB"),
    ]
    assert {n["reason"] for n in result["notices"]} == {
        "TWO_VERSIONS_NAS",
        "TWO_VERSIONS_USB",
    }


def test_two_versions_only_for_files_neither_side_has_synced():
    # A known NAS file replaced on the laptop is still the laptop-upgrade rule.
    record = {"Heat (1995)/Heat.mkv": fp(5)}
    result = plan(dict(record), {"Heat (1995)/Heat Remux.mkv": fp(50)}, record)
    assert ops(result) == [
        ("to_nas", "Heat (1995)/Heat Remux.mkv", "NEW_ON_USB"),
        ("retire_nas", "Heat (1995)/Heat.mkv", "REPLACED_ON_USB"),
    ]


def test_1x05_names_are_episodes():
    # Sonarr's "1x05" style: a laptop upgrade of one episode retires only that
    # episode, not every episode in the folder.
    record = {"Show/1x05 - A.mkv": fp(5), "Show/1x06 - B.mkv": fp(6)}
    nas = dict(record)
    usb = {"Show/1x05 - A Remux.mkv": fp(50)}
    result = plan(nas, usb, record)
    assert ops(result) == [
        ("to_usb", "Show/1x06 - B.mkv", "MISSING_ON_USB"),
        ("to_nas", "Show/1x05 - A Remux.mkv", "NEW_ON_USB"),
        ("retire_nas", "Show/1x05 - A.mkv", "REPLACED_ON_USB"),
    ]
    # A title that only looks like NxN is not an episode.
    assert plan({"4x4 (2019)/4x4 (2019).mkv": fp(1)}, {}, None)["actions"]


def test_usb_changed_after_nas_removal_is_kept():
    record = {"x.mkv": fp(1), "y.mkv": fp(1)}
    nas = {"y.mkv": fp(1)}
    usb = {"x.mkv": fp(9, T + HOUR), "y.mkv": fp(1)}
    result = plan(nas, usb, record)
    assert ops(result) == [("to_nas", "x.mkv", "UPDATED_ON_USB_AFTER_NAS_REMOVAL")]


def test_digest_is_stable_and_sensitive():
    a = plan({"x.mkv": fp(1)}, {}, None)
    b = plan({"x.mkv": fp(1)}, {}, None)
    c = plan({"x.mkv": fp(1, T + HOUR)}, {}, None)
    assert a["digest"] == b["digest"] != c["digest"]


def test_pending_counts_without_the_drive():
    record = {"a.mkv": fp(1)}
    assert pending_to_usb({"a.mkv": fp(1), "b.mkv": fp(7)}, record) == (1, 7)
