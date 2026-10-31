#!/usr/bin/env python3
"""Check for new nng releases, respecting SemVer and superseding pre-releases."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from typing import NamedTuple

from packaging.version import InvalidVersion, Version, parse


class TagInfo(NamedTuple):
    version: Version
    raw_tag: str


def get_current_tracking_rev(
    cmakelists_path: str = "CMakeLists.txt",
    var_name: str = "NNG_REV",
) -> str | None:
    """Extract NNG_REV (or NNG_V2_REV) from CMakeLists.txt without greedy regex bugs."""
    if not os.path.exists(cmakelists_path):
        return None
    with open(cmakelists_path, "r", encoding="utf-8") as f:
        content = f.read()
    m = re.search(rf'set\({re.escape(var_name)}\s+"([^"]+)"', content)
    return m.group(1) if m else None


def fetch_tags(repo_url: str) -> list[TagInfo]:
    """Fetch all v* tags from a remote git repository and parse as SemVer."""
    try:
        output = subprocess.check_output(
            ["git", "ls-remote", "--tags", repo_url, "v*"],
            stderr=subprocess.DEVNULL,
        ).decode("utf-8")
    except subprocess.CalledProcessError:
        return []

    tags: list[TagInfo] = []
    for line in output.strip().splitlines():
        if not line:
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        ref = parts[1]
        tag = ref.replace("refs/tags/", "")
        if tag.endswith("^{}"):
            continue
        try:
            v_str = tag.removeprefix("v")
            v = parse(v_str)
            tags.append(TagInfo(version=v, raw_tag=tag))
        except InvalidVersion:
            continue

    tags.sort(key=lambda x: x.version, reverse=True)
    return tags


class TrackUpdateInfo(NamedTuple):
    track_name: str  # "v1" or "v2"
    target_var: str  # "NNG_REV" or "NNG_V2_REV"
    current_rev: str | None
    target_tag: TagInfo | None
    latest_stable: TagInfo | None
    is_update_available: bool
    is_patch_update: bool


def evaluate_track(
    track_name: str,
    target_var: str,
    current_rev: str | None,
    track_tags: list[TagInfo],
) -> TrackUpdateInfo:
    """Evaluate a single NNG version track (v1 or v2) for updates."""
    target, stable = find_target_release(track_tags)
    if not target:
        return TrackUpdateInfo(
            track_name=track_name,
            target_var=target_var,
            current_rev=current_rev,
            target_tag=None,
            latest_stable=None,
            is_update_available=False,
            is_patch_update=False,
        )

    is_update = True
    is_patch = False
    if current_rev:
        try:
            curr_v = parse(current_rev.removeprefix("v"))
            if target.version <= curr_v:
                is_update = False
            elif (
                not target.version.is_prerelease
                and target.version.major == curr_v.major
                and target.version.minor == curr_v.minor
                and target.version.micro > curr_v.micro
            ):
                is_patch = True
        except InvalidVersion:
            pass

    return TrackUpdateInfo(
        track_name=track_name,
        target_var=target_var,
        current_rev=current_rev,
        target_tag=target,
        latest_stable=stable,
        is_update_available=is_update,
        is_patch_update=is_patch,
    )


def find_untracked_release(
    tags: list[TagInfo],
    current_v1_rev: str | None,
    current_v2_rev: str | None,
) -> tuple[TagInfo | None, TagInfo | None, str, str | None]:
    """
    Find a release tag (checking v2.x and v1.x tracks) that is newer than
    the currently tracked revision in CMakeLists.txt.

    Returns (target_tag, latest_stable_tag, target_var, current_rev).
    """
    if not tags:
        return None, None, "NNG_REV", current_v1_rev

    v2_tags = [t for t in tags if t.version.major >= 2]
    v1_tags = [t for t in tags if t.version.major == 1]

    v2_info = evaluate_track("v2", "NNG_V2_REV", current_v2_rev, v2_tags)
    v1_info = evaluate_track("v1", "NNG_REV", current_v1_rev, v1_tags)

    for info in (v2_info, v1_info):
        if info.is_update_available and info.target_tag is not None:
            return info.target_tag, info.latest_stable, info.target_var, info.current_rev

    for info in (v2_info, v1_info):
        if info.target_tag is not None:
            return info.target_tag, info.latest_stable, info.target_var, info.current_rev

    return None, None, "NNG_REV", current_v1_rev


def find_target_release(tags: list[TagInfo]) -> tuple[TagInfo | None, TagInfo | None]:
    """
    Find the latest candidate release tag and latest stable release tag.

    If the latest tag is a pre-release (e.g. v2.0.0-rc.2), but a stable release
    greater than or equal to that pre-release already exists (e.g. v2.0.0 >= v2.0.0-rc.2),
    the pre-release is superseded by the stable release.
    """
    if not tags:
        return None, None

    latest_tag = tags[0]
    stables = [t for t in tags if not t.version.is_prerelease]
    latest_stable = stables[0] if stables else None

    if (
        latest_tag.version.is_prerelease
        and latest_stable is not None
        and latest_stable.version >= latest_tag.version
    ):
        # Superseded by stable release
        return latest_stable, latest_stable

    return latest_tag, latest_stable


def get_existing_issues(repo: str) -> list[dict]:
    """Fetch all update issues (open and closed) for deduplication."""
    try:
        cmd = [
            "gh",
            "issue",
            "list",
            "--repo",
            repo,
            "--state",
            "all",
            "--limit",
            "200",
            "--json",
            "number,title,state",
        ]
        output = subprocess.check_output(cmd, stderr=subprocess.DEVNULL).decode("utf-8")
        return json.loads(output)
    except (subprocess.CalledProcessError, FileNotFoundError, json.JSONDecodeError):
        return []


def get_existing_prs(repo: str) -> list[dict]:
    """Fetch all pull requests (open and closed) for deduplication."""
    try:
        cmd = [
            "gh",
            "pr",
            "list",
            "--repo",
            repo,
            "--state",
            "all",
            "--limit",
            "200",
            "--json",
            "number,title,state,headRefName",
        ]
        output = subprocess.check_output(cmd, stderr=subprocess.DEVNULL).decode("utf-8")
        return json.loads(output)
    except (subprocess.CalledProcessError, FileNotFoundError, json.JSONDecodeError):
        return []


def close_superseded_pre_releases(
    repo: str,
    stable_tag: TagInfo,
    existing_issues: list[dict],
    dry_run: bool = False,
) -> list[int]:
    """Close any open pre-release issues within the same major version superseded by this stable release."""
    closed_issue_numbers: list[int] = []
    for issue in existing_issues:
        if issue.get("state") != "OPEN":
            continue
        title = issue.get("title", "")
        m = re.search(r"(?:NNG|nng)\s+update\s+available:\s+(\S+)", title, re.IGNORECASE)
        if not m:
            continue
        issue_tag = m.group(1)
        try:
            v_str = issue_tag.removeprefix("v")
            issue_v = parse(v_str)
        except InvalidVersion:
            continue

        if (
            issue_v.major == stable_tag.version.major
            and issue_v.is_prerelease
            and issue_v <= stable_tag.version
        ):
            num = issue["number"]
            print(
                f"Closing open issue #{num} ({issue_tag}) as superseded by stable {stable_tag.raw_tag}"
            )
            if not dry_run:
                try:
                    subprocess.run(
                        [
                            "gh",
                            "issue",
                            "close",
                            str(num),
                            "--repo",
                            repo,
                            "--comment",
                            f"Superseded by stable release `{stable_tag.raw_tag}`.",
                        ],
                        check=True,
                    )
                    closed_issue_numbers.append(num)
                except subprocess.CalledProcessError as e:
                    print(f"Failed to close issue #{num}: {e}", file=sys.stderr)
            else:
                closed_issue_numbers.append(num)

    return closed_issue_numbers


def write_github_output(outputs: dict[str, str]) -> None:
    """Write outputs to GITHUB_OUTPUT environment file."""
    output_file = os.environ.get("GITHUB_OUTPUT")
    if not output_file:
        return
    with open(output_file, "a", encoding="utf-8") as f:
        f.writelines(f"{k}={v}\n" for k, v in outputs.items())


def main() -> int:
    parser = argparse.ArgumentParser(description="Check for new nng updates")
    parser.add_argument(
        "--repo",
        default=os.environ.get("GITHUB_REPOSITORY", "codypiersall/pynng"),
        help="GitHub repository to check issues in",
    )
    parser.add_argument(
        "--upstream-url",
        default="https://github.com/nanomsg/nng",
        help="Upstream nng git repository",
    )
    parser.add_argument(
        "--fork-url",
        default="https://github.com/elijahr/nng",
        help="Fork nng git repository",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not close or create issues",
    )
    args = parser.parse_args()

    current_v1_rev = get_current_tracking_rev(var_name="NNG_REV")
    current_v2_rev = get_current_tracking_rev(var_name="NNG_V2_REV")
    print(f"Current nng v1 revision: {current_v1_rev}")
    print(f"Current nng v2 revision: {current_v2_rev}")

    upstream_tags = fetch_tags(args.upstream_url)
    fork_tags = fetch_tags(args.fork_url)
    fork_latest_tag = fork_tags[0].raw_tag if fork_tags else ""
    print(f"Latest fork nng tag: {fork_latest_tag}")

    if not upstream_tags:
        print("No upstream tags found.")
        write_github_output({"should_notify": "false", "updates_json": "[]"})
        return 0

    v2_tags = [t for t in upstream_tags if t.version.major >= 2]
    v1_tags = [t for t in upstream_tags if t.version.major == 1]

    v2_info = evaluate_track("v2", "NNG_V2_REV", current_v2_rev, v2_tags)
    v1_info = evaluate_track("v1", "NNG_REV", current_v1_rev, v1_tags)

    # Check existing issues and PRs across all states (open and closed)
    existing_issues = get_existing_issues(args.repo)
    existing_prs = get_existing_prs(args.repo)

    pending_updates: list[dict[str, str]] = []

    for info in (v2_info, v1_info):
        if info.latest_stable:
            close_superseded_pre_releases(
                args.repo, info.latest_stable, existing_issues, dry_run=args.dry_run
            )

        if not info.target_tag:
            continue

        t_tag = info.target_tag.raw_tag
        t_v = info.target_tag.version
        print(
            f"Track {info.track_name} ({info.target_var}): current={info.current_rev}, "
            f"latest={t_tag} ({t_v}), update={info.is_update_available}, patch={info.is_patch_update}"
        )

        if not info.is_update_available:
            print(
                f"Current tracking revision {info.target_var}={info.current_rev} is already >= {t_tag}. Skipping."
            )
            continue

        already_handled = False
        for issue in existing_issues:
            title = issue.get("title", "")
            m = re.search(r"(?:NNG|nng)\s+update\s+available:\s+(\S+)", title, re.IGNORECASE)
            if m and m.group(1) == t_tag:
                already_handled = True
                print(
                    f"Issue #{issue['number']} ({issue.get('state')}) already exists for {t_tag}. Skipping."
                )
                break

        if not already_handled:
            branch_name = f"chore/bump-nng-{t_tag}"
            for pr in existing_prs:
                if pr.get("headRefName") == branch_name or t_tag in pr.get("title", ""):
                    already_handled = True
                    print(
                        f"PR #{pr['number']} ({pr.get('state')}) already exists for {t_tag}. Skipping."
                    )
                    break

        if not already_handled:
            pending_updates.append(
                {
                    "track": info.track_name,
                    "target_var": info.target_var,
                    "current_rev": info.current_rev or "",
                    "latest_tag": t_tag,
                    "is_patch": "true" if info.is_patch_update else "false",
                    "fork_latest_tag": fork_latest_tag,
                }
            )

    primary = pending_updates[0] if pending_updates else None
    should_notify = "true" if primary is not None else "false"

    write_github_output(
        {
            "should_notify": should_notify,
            "current_rev": primary["current_rev"] if primary else (current_v2_rev or current_v1_rev or ""),
            "target_var": primary["target_var"] if primary else "NNG_REV",
            "latest_tag": primary["latest_tag"] if primary else "",
            "is_patch": primary["is_patch"] if primary else "false",
            "fork_latest_tag": fork_latest_tag,
            "updates_json": json.dumps(pending_updates),
        }
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
