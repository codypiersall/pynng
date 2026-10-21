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


def get_current_tracking_rev(cmakelists_path: str = "CMakeLists.txt") -> str | None:
    """Extract NNG_REV from CMakeLists.txt without greedy regex bugs."""
    if not os.path.exists(cmakelists_path):
        return None
    with open(cmakelists_path, "r", encoding="utf-8") as f:
        content = f.read()
    m = re.search(r'set\(NNG_REV\s+"([^"]+)"', content)
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


def close_superseded_pre_releases(
    repo: str,
    stable_tag: TagInfo,
    existing_issues: list[dict],
    dry_run: bool = False,
) -> list[int]:
    """Close any open pre-release issues superseded by this stable release."""
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

        if issue_v.is_prerelease and issue_v <= stable_tag.version:
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

    current_rev = get_current_tracking_rev()
    print(f"Current nng revision: {current_rev}")

    upstream_tags = fetch_tags(args.upstream_url)
    fork_tags = fetch_tags(args.fork_url)
    fork_latest_tag = fork_tags[0].raw_tag if fork_tags else ""
    print(f"Latest fork nng tag: {fork_latest_tag}")

    target_tag_info, latest_stable_info = find_target_release(upstream_tags)
    if not target_tag_info:
        print("No upstream tags found.")
        write_github_output({"should_notify": "false"})
        return 0

    target_tag = target_tag_info.raw_tag
    target_v = target_tag_info.version
    print(f"Latest candidate upstream nng tag: {target_tag} ({target_v})")
    if latest_stable_info:
        print(
            f"Latest stable upstream nng tag: {latest_stable_info.raw_tag} ({latest_stable_info.version})"
        )

    # Check existing issues across all states (open and closed)
    existing_issues = get_existing_issues(args.repo)

    # If we have a stable release, close any open pre-release issues superseded by it
    if latest_stable_info:
        close_superseded_pre_releases(
            args.repo, latest_stable_info, existing_issues, dry_run=args.dry_run
        )

    # Check if target tag is already tracked in CMakeLists.txt
    if current_rev:
        try:
            curr_v_str = current_rev.removeprefix("v")
            curr_v = parse(curr_v_str)
            if target_v <= curr_v:
                print(
                    f"Current tracking revision {current_rev} ({curr_v}) is already >= target {target_tag} ({target_v}). Skipping."
                )
                write_github_output(
                    {
                        "should_notify": "false",
                        "current_rev": current_rev,
                        "latest_tag": target_tag,
                        "fork_latest_tag": fork_latest_tag,
                    }
                )
                return 0
        except InvalidVersion:
            pass

    # Check if issue already exists (open or closed)
    already_notified = False
    for issue in existing_issues:
        title = issue.get("title", "")
        m = re.search(r"(?:NNG|nng)\s+update\s+available:\s+(\S+)", title, re.IGNORECASE)
        if m and m.group(1) == target_tag:
            already_notified = True
            print(
                f"Issue #{issue['number']} ({issue.get('state')}) already exists for {target_tag}. Skipping."
            )
            break

    should_notify = "true" if not already_notified else "false"
    write_github_output(
        {
            "should_notify": should_notify,
            "current_rev": current_rev or "",
            "latest_tag": target_tag,
            "fork_latest_tag": fork_latest_tag,
        }
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
