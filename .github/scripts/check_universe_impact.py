"""
Check whether the latest universe release changes a published project DB.

A project DB embeds the universe data its terms link to. When the universe
is released, a project with no change of its own may still need a rebuild.
This script rebuilds the project from the *same* source commit as its latest
published release, against the latest universe release, and compares the
project terms of both DBs (``esgvoc.admin.term_diff``). Only a difference in
the project terms means the project needs a new release.

Usage:
    python check_universe_impact.py --project-id cmip6 --project-repo WCRP-CMIP/CMIP6_CVs \
        --project-ref esgvoc --work-dir /tmp/impact

Writes ``<work-dir>/report.json`` and ``<work-dir>/report.md``, and, under
GitHub Actions, the outputs ``status`` (up-to-date | not-affected | affected |
error) and ``title``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

UNIVERSE_REPO = "WCRP-CMIP/WCRP-universe"
REGISTRY_REPO = "WCRP-CMIP/esgvoc_registry"
MAX_TERMS_LISTED = 50


def latest_stable(index_file: Path) -> dict:
    """The latest stable release of an index file (releases are listed newest first)."""
    releases = json.loads(index_file.read_text())["releases"]
    for release in releases:
        if release.get("version") != "dev-latest" and not release.get("is_prerelease"):
            return release
    raise SystemExit(f"No stable release in {index_file}")


def same_version(a: str | None, b: str | None) -> bool:
    return (a or "").lstrip("v") == (b or "").lstrip("v")


def download(url: str, dest: Path, sha256: str | None) -> None:
    with urllib.request.urlopen(url) as response, open(dest, "wb") as f:  # noqa: S310 (registry URL)
        f.write(response.read())
    if sha256:
        actual = hashlib.sha256(dest.read_bytes()).hexdigest()
        if actual != sha256:
            raise RuntimeError(f"Checksum mismatch for {url}: {actual} != {sha256}")


def clone_at(repo: str, sha: str, dest: Path) -> None:
    subprocess.run(
        ["git", "clone", "--quiet", "--filter=blob:none", "--no-checkout", f"https://github.com/{repo}.git", str(dest)],
        check=True,
    )
    subprocess.run(["git", "-C", str(dest), "checkout", "--quiet", sha], check=True)


def commits_since(repo_dir: Path, sha: str, ref: str) -> int | None:
    """Number of commits on origin/<ref> after <sha> (None if it can't be told)."""
    result = subprocess.run(
        ["git", "-C", str(repo_dir), "rev-list", "--count", f"{sha}..origin/{ref}"],
        capture_output=True,
        text=True,
        check=False,
    )
    return int(result.stdout.strip()) if result.returncode == 0 else None


def publish_command(project_id: str, project_repo: str, project_ref: str) -> str:
    return (
        f"gh workflow run publish.yml -R {REGISTRY_REPO} \\\n"
        f"  -f project_id={project_id} -f bump_type=patch \\\n"
        f"  -f project_repo={project_repo} -f project_ref={project_ref}"
    )


def terms_details(diff: dict) -> list[str]:
    lines = []
    for collection_id, change in diff["collections"].items():
        items = [f"+ {t}" for t in change["added"]] + [f"- {t}" for t in change["removed"]]
        items += [f"~ {t} ({', '.join(fields)})" for t, fields in change["modified"].items()]
        shown = items[:MAX_TERMS_LISTED]
        more = f" … and {len(items) - len(shown)} more" if len(items) > len(shown) else ""
        lines.append(f"- **{collection_id}**: " + "; ".join(shown) + more)
    return lines


def check(project_id: str, project_repo: str, project_ref: str, index_dir: Path, work_dir: Path) -> dict:
    project = latest_stable(index_dir / f"{project_id}.json")
    universe = latest_stable(index_dir / "universe.json")
    report = {
        "project_id": project_id,
        "project_repo": project_repo,
        "project_ref": project_ref,
        "published_version": project["version"],
        "published_universe_version": project.get("universe_version"),
        "universe_version": universe["version"],
        "source_sha": project.get("source_sha"),
    }
    if same_version(project.get("universe_version"), universe["version"]):
        return report | {"status": "up-to-date"}

    work_dir.mkdir(parents=True, exist_ok=True)
    published_db, rebuilt_db = work_dir / "published.db", work_dir / "rebuilt.db"
    download(project["url"], published_db, project.get("checksum_sha256"))

    project_dir, universe_dir = work_dir / "project", work_dir / "universe"
    clone_at(project_repo, project["source_sha"], project_dir)
    clone_at(UNIVERSE_REPO, universe["source_sha"], universe_dir)
    report["new_project_commits"] = commits_since(project_dir, project["source_sha"], project_ref)

    build = subprocess.run(
        [
            "esgvoc",
            "admin",
            "build",
            "--project-path",
            str(project_dir),
            "--universe-path",
            str(universe_dir),
            "--project-id",
            project_id,
            "--cv-version",
            "universe-impact-check",
            "--universe-version",
            universe["version"],
            "--output",
            str(rebuilt_db),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if build.returncode != 0 or not rebuilt_db.exists():
        tail = "\n".join((build.stdout + build.stderr).splitlines()[-30:])
        return report | {"status": "error", "error": f"Rebuild against universe {universe['version']} failed:\n{tail}"}

    from esgvoc.admin.term_diff import diff_project_terms

    diff = diff_project_terms(published_db, rebuilt_db).to_dict()
    report["terms"] = diff
    return report | {"status": "affected" if diff["has_changes"] else "not-affected"}


def markdown(report: dict) -> str:
    p, status = report["project_id"], report["status"]
    head = (
        f"**{p}** {report['published_version']} (universe {report['published_universe_version']}) "
        f"→ universe **{report['universe_version']}**"
    )
    if status == "up-to-date":
        return f"{head}: already built with this universe."
    if status == "not-affected":
        return f"{head}: no project term changed, no release needed."
    if status == "error":
        return f"{head}: ⚠️ check failed.\n\n```\n{report['error']}\n```"

    terms = report["terms"]
    lines = [
        f"{head}: the project terms change, **{p} needs a new release**.",
        "",
        (
            f"Rebuilt from the published source commit `{report['source_sha']}` of `{report['project_repo']}` "
            "against the new universe, and compared with the published DB (`esgvoc admin diff --terms`)."
        ),
        "",
        "### Changelog",
        "",
        f"Rebuild for universe {report['universe_version']}:",
        *terms["changelog"],
        "",
        "<details><summary>Changed terms</summary>",
        "",
        *terms_details(terms),
        "",
        "</details>",
        "",
        "### Publish",
        "",
        "```bash",
        publish_command(p, report["project_repo"], report["project_ref"]),
        "```",
    ]
    new_commits = report.get("new_project_commits")
    if new_commits:
        lines += [
            "",
            (
                f"⚠️ `{report['project_ref']}` has {new_commits} commit(s) since the published release: the publish "
                "builds the branch head, so it includes them too. Usually the project's own release handles those first."
            ),
        ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--project-repo", required=True)
    parser.add_argument("--project-ref", required=True, help="Prod branch, used in the publish command.")
    parser.add_argument("--index-dir", type=Path, default=Path("."))
    parser.add_argument("--work-dir", type=Path, required=True)
    args = parser.parse_args()

    try:
        report = check(args.project_id, args.project_repo, args.project_ref, args.index_dir, args.work_dir)
    except Exception as e:  # noqa: BLE001 (any failure goes into the report)
        report = {
            "project_id": args.project_id,
            "status": "error",
            "error": f"{type(e).__name__}: {e}",
            "published_version": "?",
            "published_universe_version": "?",
            "universe_version": "?",
        }

    args.work_dir.mkdir(parents=True, exist_ok=True)
    (args.work_dir / "report.json").write_text(json.dumps(report, indent=2))
    body = markdown(report)
    (args.work_dir / "report.md").write_text(body)
    print(body)

    title = f"[universe-impact] {args.project_id}: rebuild for universe {report['universe_version']}"
    if github_output := os.environ.get("GITHUB_OUTPUT"):
        with open(github_output, "a") as f:
            f.write(f"status={report['status']}\ntitle={title}\n")
    return 1 if report["status"] == "error" else 0


if __name__ == "__main__":
    sys.exit(main())
