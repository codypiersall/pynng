"""Tests for scripts/check_nng_updates.py."""

from packaging.version import parse

from scripts.check_nng_updates import (
    TagInfo,
    close_superseded_pre_releases,
    find_target_release,
    get_current_tracking_rev,
)


def test_get_current_tracking_rev(tmp_path):
    cmake = tmp_path / "CMakeLists.txt"
    cmake.write_text('set(NNG_REV "v1.11" CACHE STRING "Revision of NNG to use")\n')
    assert get_current_tracking_rev(str(cmake)) == "v1.11"


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
