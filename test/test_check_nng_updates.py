"""Tests for scripts/check_nng_updates.py."""

from packaging.version import parse

from scripts.check_nng_updates import (
    TagInfo,
    close_superseded_pre_releases,
    evaluate_track,
    find_target_release,
    find_untracked_release,
    get_current_tracking_rev,
)


def test_get_current_tracking_rev(tmp_path):
    cmake = tmp_path / "CMakeLists.txt"
    cmake.write_text(
        'set(NNG_REV "v1.11" CACHE STRING "Revision of NNG to use")\n'
        'set(NNG_V2_REV "v2.1.0" CACHE STRING "Revision of NNG v2 to use")\n'
    )
    assert get_current_tracking_rev(str(cmake)) == "v1.11"
    assert get_current_tracking_rev(str(cmake), var_name="NNG_V2_REV") == "v2.1.0"


def test_find_target_release_stable_supersedes_rc():
    tags = [
        TagInfo(version=parse("2.0.0"), raw_tag="v2.0.0"),
        TagInfo(version=parse("2.0.0rc2"), raw_tag="v2.0.0-rc.2"),
        TagInfo(version=parse("2.0.0rc1"), raw_tag="v2.0.0-rc.1"),
        TagInfo(version=parse("1.12.3"), raw_tag="v1.12.3"),
    ]
    target, stable = find_target_release(tags)
    assert target is not None
    assert target.raw_tag == "v2.0.0"
    assert stable is not None
    assert stable.raw_tag == "v2.0.0"


def test_find_target_release_tracks_new_rc_when_no_stable():
    tags = [
        TagInfo(version=parse("2.1.0rc1"), raw_tag="v2.1.0-rc.1"),
        TagInfo(version=parse("2.0.0"), raw_tag="v2.0.0"),
    ]
    target, stable = find_target_release(tags)
    assert target is not None
    assert target.raw_tag == "v2.1.0-rc.1"
    assert stable is not None
    assert stable.raw_tag == "v2.0.0"


def test_close_superseded_pre_releases_dry_run():
    stable_tag = TagInfo(version=parse("2.0.0"), raw_tag="v2.0.0")
    existing_issues = [
        {"number": 188, "title": "nng update available: v2.0.0-rc.2", "state": "OPEN"},
        {"number": 176, "title": "nng update available: v2.0.0-rc.2", "state": "CLOSED"},
        {"number": 190, "title": "nng update available: v2.1.0-rc.1", "state": "OPEN"},
        {"number": 191, "title": "nng update available: v2.0.0", "state": "OPEN"},
    ]
    closed = close_superseded_pre_releases(
        "dummy/repo", stable_tag, existing_issues, dry_run=True
    )
    # Only #188 (open RC <= 2.0.0) should be closed; #176 is closed, #190 is > 2.0.0, #191 is stable
    assert closed == [188]


def test_find_untracked_release_v1_and_v2_tracks():
    tags = [
        TagInfo(version=parse("2.1.0"), raw_tag="v2.1.0"),
        TagInfo(version=parse("2.0.0"), raw_tag="v2.0.0"),
        TagInfo(version=parse("1.12.6"), raw_tag="v1.12.6"),
        TagInfo(version=parse("1.12.5"), raw_tag="v1.12.5"),
    ]
    # When v2 is behind (v2.0.0 < v2.1.0), selects v2 track
    target, stable, var_name, curr_rev = find_untracked_release(tags, "v1.12.5", "v2.0.0")
    assert target is not None and target.raw_tag == "v2.1.0"
    assert stable is not None and stable.raw_tag == "v2.1.0"
    assert var_name == "NNG_V2_REV"
    assert curr_rev == "v2.0.0"

    # When v2 is up to date (v2.1.0) and v1 is behind (v1.12.5 < v1.12.6), selects v1 track
    target, stable, var_name, curr_rev = find_untracked_release(tags, "v1.12.5", "v2.1.0")
    assert target is not None and target.raw_tag == "v1.12.6"
    assert stable is not None and stable.raw_tag == "v1.12.6"
    assert var_name == "NNG_REV"
    assert curr_rev == "v1.12.5"


def test_evaluate_track_patch_and_minor_detection():
    v1_tags = [
        TagInfo(version=parse("1.12.6"), raw_tag="v1.12.6"),
        TagInfo(version=parse("1.12.5"), raw_tag="v1.12.5"),
    ]
    v2_tags = [
        TagInfo(version=parse("2.1.0"), raw_tag="v2.1.0"),
        TagInfo(version=parse("2.0.0"), raw_tag="v2.0.0"),
    ]

    v1_info = evaluate_track("v1", "NNG_REV", "v1.12.5", v1_tags)
    assert v1_info.is_update_available is True
    assert v1_info.is_patch_update is True
    assert v1_info.target_tag is not None and v1_info.target_tag.raw_tag == "v1.12.6"

    v2_minor = evaluate_track("v2", "NNG_V2_REV", "v2.0.0", v2_tags)
    assert v2_minor.is_update_available is True
    assert v2_minor.is_patch_update is False
    assert v2_minor.target_tag is not None and v2_minor.target_tag.raw_tag == "v2.1.0"

    v2_current = evaluate_track("v2", "NNG_V2_REV", "v2.1.0", v2_tags)
    assert v2_current.is_update_available is False
    assert v2_current.is_patch_update is False
