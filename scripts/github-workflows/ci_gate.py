"""The one required check: every Test job that ran passed.

`test.yml`'s last job, `CI`, needs every other job and runs this whatever became of them
(`if: always()`). main's branch protection requires `CI` alone, so a job can be added, renamed,
split or sharded without touching it, and no job is left that can fail without stopping a merge.

    NEEDS='<toJSON(needs)>' python3 scripts/github-workflows/ci_gate.py

A job passes by succeeding, or by being skipped: its flag did not select it
(select_checks.py). The run fails when

- `changes` did not succeed: nothing was selected, so every job it gates was skipped having
  tested nothing (GitHub counts a skipped check as passing; this is where that stops);
- a job failed;
- a job was cancelled, which is also what a job that ran out its `timeout-minutes` reports.

One cancelled run passes: a pull request's run that a newer push superseded, which the
workflow's concurrency group cancels. Its commit is no longer the pull request's head, so its
check gates nothing, and failing it would only mail a failure for every push made while a run
was in flight. Whether the head has moved is read from the repository itself
(`git ls-remote refs/pull/<n>/head`, which needs no more than the read of contents every
caller of this workflow has); failing to read it is "not superseded", and the run fails.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import Callable

SELECTION = "changes"


def verdict(results: dict[str, str], superseded: Callable[[], bool]) -> tuple[int, str]:
    """The exit code and the line that says why, for each needed job's result."""
    if results.get(SELECTION) not in ("success", "cancelled"):
        return 1, (f"Changed paths ended {results.get(SELECTION, 'unknown')}: nothing was selected and no "
                   "test ran. Re-run the workflow.")
    failed = sorted(job for job, result in results.items() if result == "failure")
    if failed:
        return 1, f"Failed: {', '.join(failed)}."
    cancelled = sorted(job for job, result in results.items() if result == "cancelled")
    if cancelled:
        if superseded():
            return 0, "Superseded by a newer push to the pull request, whose run decides: not judged."
        return 1, f"Cancelled or timed out, so not tested: {', '.join(cancelled)}."
    unknown = sorted(job for job, result in results.items() if result not in ("success", "skipped"))
    if unknown:
        return 1, f"No result for: {', '.join(unknown)}."
    ran = sum(result == "success" for result in results.values())
    return 0, f"Passed: {ran} job(s) ran and {len(results) - ran} had nothing to test."


def pull_request_head(repository: str, number: str, token: str) -> str | None:
    """The pull request's head commit as the repository has it now, or None when it cannot be read."""
    server = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
    remote = f"{server.replace('://', f'://x-access-token:{token}@', 1)}/{repository}.git"
    try:
        listed = subprocess.run(["git", "ls-remote", remote, f"refs/pull/{number}/head"],
                                capture_output=True, text=True, timeout=60, check=True).stdout.split()
    except (subprocess.SubprocessError, OSError):
        return None
    return listed[0] if listed else None


def superseded() -> bool:
    if os.environ.get("GITHUB_EVENT_NAME") != "pull_request":
        return False
    number, tested = os.environ.get("PULL_REQUEST", ""), os.environ.get("HEAD_SHA", "")
    if not (number and tested):
        return False
    head = pull_request_head(os.environ["GITHUB_REPOSITORY"], number, os.environ.get("GITHUB_TOKEN", ""))
    return head is not None and head != tested


def main() -> int:
    results = {job: need.get("result", "") for job, need in json.loads(os.environ["NEEDS"]).items()}
    code, why = verdict(results, superseded)
    table = ["| Job | Result |", "| --- | --- |", *(f"| `{job}` | {result} |" for job, result in sorted(results.items()))]
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as handle:
            handle.write("\n".join([why, "", *table]) + "\n")
    for job, result in sorted(results.items()):
        print(f"{result:>10}  {job}")
    print(why, file=sys.stderr if code else sys.stdout)
    return code


if __name__ == "__main__":
    sys.exit(main())
