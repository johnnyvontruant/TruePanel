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
    result = plan({"a/1x01.mkv": fp(1)}, {"a/1X01.mkv": fp(1)}, None, usb_fstype="ext4")
    assert ops(result) == [
        ("to_usb", "a/1x01.mkv", "NEW_ON_NAS"),
        ("to_nas", "a/1X01.mkv", "NEW_ON_USB"),
    ]


def test_case_twin_actions_carry_the_drive_spelling():
    record = {"a/1X01.mkv": fp(1), "a/1X02.mkv": fp(2), "keep.mkv": fp(3)}
    nas = {"a/1x01.mkv": fp(9, T + HOUR), "keep.mkv": fp(3)}
    usb = {"A/1X01.mkv": fp(1), "A/1X02.mkv": fp(2), "keep.mkv": fp(3)}
    result = plan(nas, usb, record, usb_fstype="exfat")
    actions = {a["path"]: (a["op"], a["reason"], a["usb_path"]) for a in result["actions"]}
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
