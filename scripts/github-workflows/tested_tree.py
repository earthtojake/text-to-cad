"""Find the successful Test run that already tested a tree.

Every Test run records what it tested as an artifact named by `select_checks.py`:
`tested-<tree>-<scope>`, where <tree> is the git tree of the checked-out commit and
<scope> is `full` when every job ran, or a digest of the jobs and suites it selected.
The name is the whole record, so a lookup is one artifact listing, filtered by name,
and one read per candidate run.

A record counts only when its run is a completed, successful run of
.github/workflows/test.yml in THIS repository: runs from a fork's branch are skipped,
because a fork controls the workflow file its pull request runs. Any API error is "not
found" -- the caller then runs the tests rather than trusting a record it could not read.

Usage (GITHUB_TOKEN with actions:read, GITHUB_REPOSITORY and GITHUB_REPOSITORY_ID set,
as Actions sets them):

    python3 scripts/github-workflows/tested_tree.py tested-<tree>-<scope> [...]

Prints the run that tested the tree and exits 0, or exits 1. With several names, any
one of them is enough.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

TEST_WORKFLOW = ".github/workflows/test.yml"


def _api(path: str) -> dict:
    base = os.environ.get("GITHUB_API_URL", "https://api.github.com").rstrip("/")
    request = urllib.request.Request(f"{base}/{path}", headers={
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def counts(run: dict, repository_id: int) -> bool:
    """A run whose record can stand in for running the tests again."""
    return (
        (run.get("repository") or {}).get("id") == repository_id
        and (run.get("head_repository") or {}).get("id") == repository_id
        and run.get("path", "").split("@", 1)[0] == TEST_WORKFLOW
        and run.get("status") == "completed"
        and run.get("conclusion") == "success"
    )


def find(name: str, repository: str, repository_id: int, api=None) -> dict | None:
    """The newest successful same-repository Test run that recorded `name`, or None."""
    api = api or _api
    query = urllib.parse.urlencode({"name": name, "per_page": 100})
    artifacts = api(f"repos/{repository}/actions/artifacts?{query}").get("artifacts", [])
    seen = set()
    for artifact in artifacts:
        run_ref = artifact.get("workflow_run") or {}
        run_id = run_ref.get("id")
        if run_id in seen or run_ref.get("head_repository_id") != repository_id:
            continue
        seen.add(run_id)
        run = api(f"repos/{repository}/actions/runs/{run_id}")
        if counts(run, repository_id):
            return run
    return None


def main(argv: list[str]) -> int:
    names = [name for name in argv if name]
    if not names:
        print("usage: tested_tree.py tested-<tree>-<scope> [...]", file=sys.stderr)
        return 2
    repository = os.environ["GITHUB_REPOSITORY"]
    repository_id = int(os.environ["GITHUB_REPOSITORY_ID"])
    for name in names:
        try:
            run = find(name, repository, repository_id)
        except (urllib.error.URLError, OSError, ValueError, KeyError) as error:
            print(f"Could not look up {name}: {error}", file=sys.stderr)
            return 1
        if run is not None:
            print(f"{name}: tested by {run.get('html_url')} ({run.get('event')}, {run.get('head_branch')})")
            return 0
    print(f"No successful Test run of this repository recorded {' or '.join(names)}.")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
