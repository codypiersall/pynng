"""Tests for scripts/check_nng_updates.py and CMake patch resolution."""

import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest
from packaging.version import parse

from scripts.check_nng_updates import (
    TagInfo,
    TrackUpdateInfo,
    close_superseded_pre_releases,
    evaluate_track,
    find_target_release,
    get_current_tracking_rev,
    is_already_handled,
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
    assert target == TagInfo(version=parse("2.0.0"), raw_tag="v2.0.0")
    assert stable == TagInfo(version=parse("2.0.0"), raw_tag="v2.0.0")


def test_find_target_release_tracks_new_rc_when_no_stable():
    tags = [
        TagInfo(version=parse("2.1.0rc1"), raw_tag="v2.1.0-rc.1"),
        TagInfo(version=parse("2.0.0"), raw_tag="v2.0.0"),
    ]
    target, stable = find_target_release(tags)
    assert target == TagInfo(version=parse("2.1.0rc1"), raw_tag="v2.1.0-rc.1")
    assert stable == TagInfo(version=parse("2.0.0"), raw_tag="v2.0.0")


def test_close_superseded_pre_releases_dry_run_and_cross_major_isolation():
    stable_v2 = TagInfo(version=parse("2.0.0"), raw_tag="v2.0.0")
    existing_issues = [
        {"number": 188, "title": "nng update available: v2.0.0-rc.2", "state": "OPEN"},
        {
            "number": 176,
            "title": "nng update available: v2.0.0-rc.2",
            "state": "CLOSED",
        },
        {"number": 190, "title": "nng update available: v2.1.0-rc.1", "state": "OPEN"},
        {"number": 191, "title": "nng update available: v2.0.0", "state": "OPEN"},
        {"number": 192, "title": "nng update available: v1.13.0-rc.1", "state": "OPEN"},
    ]
    closed_v2 = close_superseded_pre_releases(
        "dummy/repo", stable_v2, existing_issues, dry_run=True
    )
    # Only #188 (open v2 RC <= 2.0.0) should be closed; #192 is v1 track and must not be closed by v2
    assert closed_v2 == [188]

    stable_v1 = TagInfo(version=parse("1.13.0"), raw_tag="v1.13.0")
    closed_v1 = close_superseded_pre_releases(
        "dummy/repo", stable_v1, existing_issues, dry_run=True
    )
    # Only #192 (open v1 RC <= 1.13.0) should be closed; v2 RCs (#188, #190) are untouched
    assert closed_v1 == [192]


def test_evaluate_track_patch_minor_and_prerelease_detection():
    tag_1_12_6 = TagInfo(version=parse("1.12.6"), raw_tag="v1.12.6")
    tag_1_12_5 = TagInfo(version=parse("1.12.5"), raw_tag="v1.12.5")
    v1_tags = [tag_1_12_6, tag_1_12_5]

    tag_2_1_0 = TagInfo(version=parse("2.1.0"), raw_tag="v2.1.0")
    tag_2_0_0 = TagInfo(version=parse("2.0.0"), raw_tag="v2.0.0")
    v2_tags = [tag_2_1_0, tag_2_0_0]

    # Patch update on v1 track
    v1_info = evaluate_track("v1", "NNG_REV", "v1.12.5", v1_tags)
    assert v1_info == TrackUpdateInfo(
        track_name="v1",
        target_var="NNG_REV",
        current_rev="v1.12.5",
        target_tag=tag_1_12_6,
        latest_stable=tag_1_12_6,
        is_update_available=True,
        is_patch_update=True,
    )

    # Minor update on v2 track (is_patch_update must be False)
    v2_minor = evaluate_track("v2", "NNG_V2_REV", "v2.0.0", v2_tags)
    assert v2_minor == TrackUpdateInfo(
        track_name="v2",
        target_var="NNG_V2_REV",
        current_rev="v2.0.0",
        target_tag=tag_2_1_0,
        latest_stable=tag_2_1_0,
        is_update_available=True,
        is_patch_update=False,
    )

    # Already up to date on v2 track
    v2_current = evaluate_track("v2", "NNG_V2_REV", "v2.1.0", v2_tags)
    assert v2_current == TrackUpdateInfo(
        track_name="v2",
        target_var="NNG_V2_REV",
        current_rev="v2.1.0",
        target_tag=tag_2_1_0,
        latest_stable=tag_2_1_0,
        is_update_available=False,
        is_patch_update=False,
    )

    # Negative control: patch pre-release (v2.1.0 -> v2.1.1-rc.1) must have is_patch_update=False
    tag_2_1_1_rc1 = TagInfo(version=parse("2.1.1rc1"), raw_tag="v2.1.1-rc.1")
    v2_rc = evaluate_track("v2", "NNG_V2_REV", "v2.1.0", [tag_2_1_1_rc1, tag_2_1_0])
    assert v2_rc == TrackUpdateInfo(
        track_name="v2",
        target_var="NNG_V2_REV",
        current_rev="v2.1.0",
        target_tag=tag_2_1_1_rc1,
        latest_stable=tag_2_1_0,
        is_update_available=True,
        is_patch_update=False,
    )


def test_is_already_handled_pr_and_issue_deduplication():
    existing_issues = [
        {
            "number": 200,
            "title": "nng update available: v2.1.0-rc.1",
            "state": "CLOSED",
        },
    ]
    existing_prs = [
        {
            "number": 201,
            "title": "build(deps): bump NNG_V2_REV from v2.0.0 to v2.1.0-rc.1",
            "headRefName": "chore/bump-nng-v2.1.0-rc.1",
            "state": "CLOSED",
        },
        {
            "number": 202,
            "title": "build(deps): bump NNG_V2_REV from v2.1.0 to v2.2.0",
            "headRefName": "chore/bump-nng-v2.2.0",
            "state": "OPEN",
        },
    ]

    # Stable v2.1.0 must NOT be suppressed by a v2.1.0-rc.1 PR/issue or a "from v2.1.0 to v2.2.0" PR
    assert is_already_handled("v2.1.0", existing_issues, existing_prs) is False

    # Exact RC issue or PR matches
    assert is_already_handled("v2.1.0-rc.1", existing_issues, existing_prs) is True
    assert is_already_handled("v2.2.0", existing_issues, existing_prs) is True

    # Exact target in PR title matches
    prs_with_exact_title = [
        *existing_prs,
        {
            "number": 203,
            "title": "build(deps): bump NNG_V2_REV from v2.0.0 to v2.1.0",
            "headRefName": "custom-branch",
            "state": "OPEN",
        },
    ]
    assert is_already_handled("v2.1.0", existing_issues, prs_with_exact_title) is True


def test_cmake_resolve_latest_patch_crlf_and_no_downgrade(tmp_path):
    """Verify _pynng_resolve_latest_patch in CMakeLists.txt handles CRLF and refuses downgrades."""
    cmake_bin = shutil.which("cmake")
    if not cmake_bin:
        pytest.skip("cmake executable not available")

    repo_root = Path(__file__).resolve().parent.parent
    cmakelists_text = (repo_root / "CMakeLists.txt").read_text(encoding="utf-8")
    start = cmakelists_text.index("function(_pynng_resolve_latest_patch ")
    end = cmakelists_text.index("endfunction()", start) + len("endfunction()")
    fn_block = cmakelists_text[start:end]

    # Create a fake git script that outputs Windows CRLF (\r\n) tag lines
    fake_git = tmp_path / "fake_git.py"
    fake_git.write_text(
        "#!/usr/bin/env python3\n"
        "import sys\n"
        "if '--version' in sys.argv:\n"
        "    print('git version 2.40.0')\n"
        "    sys.exit(0)\n"
        "sys.stdout.buffer.write(\n"
        "    b'aaaa\\trefs/tags/v1.12.4\\r\\n'\n"
        "    b'bbbb\\trefs/tags/v1.12.7\\r\\n'\n"
        "    b'cccc\\trefs/tags/v1.12.5\\r\\n'\n"
        "    b'dddd\\trefs/tags/v1.11.4\\r\\n'\n"
        ")\n",
        encoding="utf-8",
    )
    fake_git.chmod(fake_git.stat().st_mode | stat.S_IEXEC)

    if sys.platform == "win32":
        fake_git_bat = tmp_path / "fake_git.bat"
        fake_git_bat.write_text(
            f'@echo off\r\n"{sys.executable}" "{fake_git}" %*\r\n',
            encoding="utf-8",
        )
        fake_git_exec = fake_git_bat
    else:
        fake_git_exec = fake_git

    harness = tmp_path / "test_resolve.cmake"
    harness.write_text(
        f"{fn_block}\n"
        "set(GIT_FOUND TRUE)\n"
        f'set(GIT_EXECUTABLE "{fake_git_exec.as_posix()}")\n'
        'set(REV_UPGRADE "v1.12.5")\n'
        '_pynng_resolve_latest_patch("https://example.invalid/nng" REV_UPGRADE)\n'
        'message(STATUS "RESULT_UPGRADE=${REV_UPGRADE}")\n'
        'set(REV_NO_DOWNGRADE "v1.12.9")\n'
        '_pynng_resolve_latest_patch("https://example.invalid/nng" REV_NO_DOWNGRADE)\n'
        'message(STATUS "RESULT_NO_DOWNGRADE=${REV_NO_DOWNGRADE}")\n'
        'set(REV_TWO_PART "v1.11")\n'
        '_pynng_resolve_latest_patch("https://example.invalid/nng" REV_TWO_PART)\n'
        'message(STATUS "RESULT_TWO_PART=${REV_TWO_PART}")\n'
        'set(REV_BRANCH "main")\n'
        '_pynng_resolve_latest_patch("https://example.invalid/nng" REV_BRANCH)\n'
        'message(STATUS "RESULT_BRANCH=${REV_BRANCH}")\n',
        encoding="utf-8",
    )

    out = subprocess.check_output(
        [cmake_bin, "-P", str(harness)],
        stderr=subprocess.STDOUT,
        text=True,
    )
    assert "RESULT_UPGRADE=v1.12.7" in out
    assert "RESULT_NO_DOWNGRADE=v1.12.9" in out
    assert "RESULT_TWO_PART=v1.11.4" in out
    assert "RESULT_BRANCH=main" in out
    assert "Skipping REV_BRANCH (main)" in out
