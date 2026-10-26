from __future__ import annotations

import json

from truepanel.loadmaster.identity import folder_keys, library_index, title_key
from truepanel.loadmaster.plan import build_plan
from truepanel.loadmaster.scan import Fingerprint

T = 1_700_000_000_000_000_000


def fp(size: int, mtime: int = T) -> Fingerprint:
    return Fingerprint(size, mtime)


def ops(result):
    return [(a["op"], a["path"], a["reason"]) for a in result["actions"]]


def held(result):
    return sorted(
        (n["reason"], n["path"], tuple(n.get("other", ()))) for n in result["notices"]
    )


# Folder names from the BattleStation first syncs, 2026-10-24.
def test_title_key_ignores_punctuation_articles_and_word_order():
    pairs = [
        ("Hail Caesar (2016)", "Hail, Caesar (2016)"),
        ("Love, Rosie (2014)", "Love Rosie (2014)"),
        ("Nitro Circus The Movie (2012)", "Nitro Circus - The Movie (2012)"),
        (
            "Book of Shadows Blair Witch 2 (2000)",
            "Blair Witch 2 - Book of Shadows (2000)",
        ),
        ("The Matchmaker's Playbook (2018)", "The Matchmaker’s Playbook (2018)"),
    ]
    for a, b in pairs:
        assert title_key(a) == title_key(b) is not None
    # A different cut or a different year is a different title.
    assert title_key(
        "The Blair Witch Project 2 - The Book of Shadows (Re-cut) (2000)"
    ) != title_key("Blair Witch 2 - Book of Shadows (2000)")
    assert title_key("Heat (1995)") != title_key("Heat (1986)")
    assert title_key("Featurettes") is None


def test_library_index_reads_identity_files(tmp_path):
    movies = tmp_path / "Movies 1-D"
    (movies / "Blair Witch 2 - Book of Shadows (2000)").mkdir(parents=True)
    (
        movies / "Blair Witch 2 - Book of Shadows (2000)" / ".media-identity.json"
    ).write_text(json.dumps({"tmdb_id": 11531, "radarr_id": 476}))
    (movies / ".loadmaster-replaced").mkdir()
    library = library_index([("Movies 1-D", movies)])
    assert library["tmdb:11531"] == [
        ("Movies 1-D", "Blair Witch 2 - Book of Shadows (2000)")
    ]
    assert not any(
        folder == ".loadmaster-replaced" for v in library.values() for _, folder in v
    )

    drive = tmp_path / "usb"
    (drive / "Shadows Book (2000)").mkdir(parents=True)
    (drive / "Shadows Book (2000)" / ".media-identity.json").write_text(
        json.dumps({"tmdb_id": 11531})
    )
    assert "tmdb:11531" in folder_keys(drive)["Shadows Book (2000)"]


def plan_with_library(
    nas, usb, record=None, drive="Movies E-I", nas_folders=(), other=()
):
    library = {}
    for d, folder in [(drive, f) for f in nas_folders] + list(other):
        library.setdefault(title_key(folder), []).append((d, folder))
    usb_folders = {
        p.split("/")[0]: {title_key(p.split("/")[0])} for p in usb if "/" in p
    }
    return build_plan(
        drive_name=drive,
        nas=nas,
        usb=usb,
        record=record,
        usb_fstype="exfat",
        library=library,
        usb_folders=usb_folders,
    )


def test_renamed_folder_on_the_same_drive_is_held():
    nas = {"Hail, Caesar (2016)/Hail, Caesar (2016).mp4": fp(17)}
    usb = {**nas, "Hail Caesar (2016)/Hail Caesar (2016).mp4": fp(24)}
    result = plan_with_library(nas, usb, nas_folders=["Hail, Caesar (2016)"])
    assert result["actions"] == []
    assert held(result) == [
        (
            "SAME_TITLE_ON_NAS",
            "Hail Caesar (2016)/Hail Caesar (2016).mp4",
            ("Movies E-I/Hail, Caesar (2016)",),
        )
    ]


def test_movie_filed_on_the_wrong_drive_is_held():
    usb = {
        "The Matchmaker's Playbook (2018)/The Matchmaker's Playbook (2018).mkv": fp(6)
    }
    result = plan_with_library(
        {},
        usb,
        drive="Movies 1-D",
        other=[("Movies T-Z", "The Matchmaker's Playbook (2018)")],
    )
    assert result["actions"] == []
    assert [n["other"] for n in result["notices"]] == [
        ["Movies T-Z/The Matchmaker's Playbook (2018)"]
    ]


def test_genuinely_new_movie_still_comes_to_the_nas():
    usb = {"Matchbox - The Movie (2026)/Matchbox - The Movie (2026).mkv": fp(20)}
    result = plan_with_library(
        {}, usb, drive="Movies J-S", nas_folders=["Love Rosie (2014)"]
    )
    assert ops(result) == [
        (
            "to_nas",
            "Matchbox - The Movie (2026)/Matchbox - The Movie (2026).mkv",
            "NEW_ON_USB",
        )
    ]


def test_new_file_in_a_folder_the_nas_has_is_not_a_title_match():
    # Same folder on both sides: ordinary rules (here a new subtitle) apply.
    nas = {"Heat (1995)/Heat (1995).mkv": fp(5)}
    usb = {**nas, "Heat (1995)/Heat (1995).en.srt": fp(1)}
    result = plan_with_library(
        nas, usb, drive="Movies E-I", nas_folders=["Heat (1995)"]
    )
    assert ops(result) == [("to_nas", "Heat (1995)/Heat (1995).en.srt", "NEW_ON_USB")]


def test_old_version_beside_a_synced_movie_is_held():
    # Casino on Movies 1-D: the 86 GB mkv is in sync, an old mpg sits beside it.
    nas = {"Casino (1995)/Casino (1995).mkv": fp(86)}
    usb = {**nas, "Casino (1995)/Casino (1995).mpg": fp(1)}
    result = build_plan(drive_name="Movies 1-D", nas=nas, usb=usb, record=None)
    assert result["actions"] == []
    assert held(result) == [
        (
            "EXTRA_VERSION",
            "Casino (1995)/Casino (1995).mpg",
            ("Casino (1995)/Casino (1995).mkv",),
        )
    ]


def test_edition_tagged_version_is_deliberate():
    nas = {"Heat (1995)/Heat (1995).mkv": fp(5)}
    usb = {**nas, "Heat (1995)/Heat (1995) {edition-Director's Cut}.mkv": fp(9)}
    result = build_plan(drive_name="Movies E-I", nas=nas, usb=usb, record=None)
    assert ops(result) == [
        ("to_nas", "Heat (1995)/Heat (1995) {edition-Director's Cut}.mkv", "NEW_ON_USB")
    ]


def test_extra_version_is_per_episode():
    nas = {"Show/1x01 - A.mkv": fp(1), "Show/1x02 - B.mkv": fp(2)}
    usb = {**nas, "Show/1x01 - A Remux.mkv": fp(9), "Show/1x03 - C.mkv": fp(3)}
    result = build_plan(drive_name="TV A-M", nas=nas, usb=usb, record=None)
    assert ops(result) == [("to_nas", "Show/1x03 - C.mkv", "NEW_ON_USB")]
    assert [n["reason"] for n in result["notices"]] == ["EXTRA_VERSION"]


def test_laptop_upgrade_is_still_a_replacement_not_an_extra_version():
    record = {"Heat (1995)/Heat 720p.mkv": fp(5)}
    result = build_plan(
        drive_name="Movies E-I",
        nas=dict(record),
        usb={"Heat (1995)/Heat 2160p.mkv": fp(50)},
        record=record,
    )
    assert ops(result) == [
        ("to_nas", "Heat (1995)/Heat 2160p.mkv", "NEW_ON_USB"),
        ("retire_nas", "Heat (1995)/Heat 720p.mkv", "REPLACED_ON_USB"),
    ]
