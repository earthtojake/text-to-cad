"""Release a pull request: PyPI first, then main.

A pull request that changes VERSION is a release, and a pin must never reach anything an
installer tracks before its wheel is on PyPI. Codex's and Claude Code's marketplaces, Grok,
the Skills CLI and the Cursor Marketplace all read main, so the bump reaches main only after
the upload: Publish Release builds the pull request's tested tree, uploads it, and then this
script merges the pull request. Until the version is on PyPI, the pull request's Version Check
fails (`published`), so nobody merges it early by hand.

PyPI's simple index is served with `max-age=600`, and uv keeps the page it fetched for that
long. A uv that read the page minutes before the upload would still not see the new version,
so the announcements -- the docs site's version feed and update notice, the GitHub Release
Gemini installs from, the plugin branch -- wait until the upload is ten minutes old
(`settle`).

    release_pr.py published VERSION                        # exit 0 once PyPI serves it
    release_pr.py await --pr N                              # wait for Test to pass on it; print its head
    release_pr.py resolve --pr N --base BRANCH              # check the pull request; print its head
    release_pr.py land --pr N --sha HEAD [--version X]      # (wait for PyPI,) unblock and merge
    release_pr.py settle VERSION                            # wait until the upload is 10 min old

`await` is Prepare Release's: the explicit release pull request it opens is released once Test
passes on it, and kept up to date with its base meanwhile. Run it with a token whose pushes
start workflows (not the workflow's own), or the branch update would start no Test run.

GITHUB_TOKEN, GITHUB_REPOSITORY and GITHUB_REPOSITORY_ID come from Actions.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import time
import urllib.error
import urllib.request

PYPI = "https://pypi.org/pypi/cadgen/{version}/json"
INDEX_MAX_AGE = 600       # PyPI's simple index: cache-control max-age=600
SETTLE_MARGIN = 60        # and the CDN's purge after an upload
VERSION_CHECK = "version.yml"
TEST = "test.yml"
WAIT_SECONDS = 600        # for PyPI to serve an upload, or a Version Check to finish
AWAIT_SECONDS = 90 * 60   # for Test on a release pull request, through a few branch updates
AWAIT_UPDATES = 3         # times the base may move on before the release gives up
POLL_SECONDS = 10


class ReleaseError(Exception):
    pass


def _github(method: str, path: str, body: dict | None = None) -> dict:
    base = os.environ.get("GITHUB_API_URL", "https://api.github.com").rstrip("/")
    request = urllib.request.Request(
        f"{base}/{path}", method=method,
        data=None if body is None else json.dumps(body).encode("utf-8"),
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            text = response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        raise ReleaseError(f"{method} {path}: {error.code} {error.read().decode('utf-8', 'replace')}") from error
    return json.loads(text) if text else {}


def _pypi(version: str) -> dict | None:
    """PyPI's record of cadgen VERSION, or None while it serves none."""
    try:
        with urllib.request.urlopen(PYPI.format(version=version), timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None
        raise


def published(version: str, pypi=_pypi) -> bool:
    record = pypi(version)
    return bool(record and record.get("urls"))


def uploaded_at(version: str, pypi=_pypi) -> float:
    """When the version's first file reached PyPI, in epoch seconds."""
    record = pypi(version)
    if not record or not record.get("urls"):
        raise ReleaseError(f"PyPI serves no cadgen {version}")
    return min(dt.datetime.fromisoformat(item["upload_time_iso_8601"].replace("Z", "+00:00")).timestamp()
               for item in record["urls"])


def resolve(number: int, base: str, repository: str, repository_id: int, github=_github) -> dict:
    """The pull request, if it may be released into `base` from here."""
    pull = github("GET", f"repos/{repository}/pulls/{number}")
    head = pull.get("head") or {}
    problems = []
    if pull.get("state") != "open":
        problems.append(f"it is {pull.get('state')}")
    if pull.get("draft"):
        problems.append("it is a draft")
    if (pull.get("base") or {}).get("ref") != base:
        problems.append(f"it targets {(pull.get('base') or {}).get('ref')}, not {base}")
    if ((head.get("repo") or {}).get("id")) != repository_id:
        problems.append("its branch is a fork's, and only a branch of this repository releases")
    if problems:
        raise ReleaseError(f"pull request #{number} cannot be released: " + "; ".join(problems))
    return {"number": number, "sha": head["sha"], "title": pull.get("title", "")}


def _wait(condition, what: str, clock, sleep, seconds: int = WAIT_SECONDS) -> None:
    deadline = clock() + seconds
    while not condition():
        if clock() >= deadline:
            raise ReleaseError(f"gave up waiting for {what}")
        sleep(POLL_SECONDS)


def land(number: int, sha: str, repository: str, version: str | None = None,
         github=_github, pypi=_pypi, clock=time.time, sleep=time.sleep) -> str:
    """Merge the released pull request once nothing stands in the way; the merge commit's sha.

    With `version`, first wait until PyPI serves it, then re-run the pull request's Version
    Check, which held the merge until now.
    """
    if version is not None:
        _wait(lambda: published(version, pypi), f"PyPI to serve cadgen {version}", clock, sleep)
        runs = github("GET", f"repos/{repository}/actions/workflows/{VERSION_CHECK}/runs"
                             f"?event=pull_request&head_sha={sha}&per_page=5").get("workflow_runs", [])
        if not runs:
            raise ReleaseError(f"no Version Check ran on {sha}")
        run_id = runs[0]["id"]

        def latest() -> dict:
            return github("GET", f"repos/{repository}/actions/runs/{run_id}")

        _wait(lambda: latest().get("status") == "completed", "the pull request's Version Check", clock, sleep)
        run = latest()
        if run.get("conclusion") != "success":
            # It ran before PyPI served the version. A re-run is a new attempt of the same run.
            attempt = run.get("run_attempt", 1)
            github("POST", f"repos/{repository}/actions/runs/{run_id}/rerun-failed-jobs")

            def rerun_finished() -> bool:
                now = latest()
                return now.get("run_attempt", 1) > attempt and now.get("status") == "completed"

            _wait(rerun_finished, "the pull request's Version Check to run again", clock, sleep)
            run = latest()
            if run.get("conclusion") != "success":
                raise ReleaseError(f"Version Check on {sha} concluded {run.get('conclusion')}: {run.get('html_url')}")
    merged = github("PUT", f"repos/{repository}/pulls/{number}/merge", {"merge_method": "squash", "sha": sha})
    if not merged.get("merged"):
        raise ReleaseError(f"pull request #{number} did not merge: {merged.get('message')}")
    return merged["sha"]


def await_tested(number: int, repository: str, github=_github, clock=time.time, sleep=time.sleep) -> str:
    """Wait until Test passes on the pull request's head; the head it passed on.

    A release must be up to date with its base (Publish Release's gate refuses one that is
    behind), so whenever the base moves on, the branch is brought up to date and the wait
    starts over on the new head. GitHub makes that update after it answers, so until the
    head moves, the old one is not looked at again.
    """
    deadline = clock() + AWAIT_SECONDS
    updates, updated = 0, None
    while True:
        pull = github("GET", f"repos/{repository}/pulls/{number}")
        if pull.get("state") != "open":
            raise ReleaseError(f"pull request #{number} is {pull.get('state')}")
        head, base = pull["head"]["sha"], pull["base"]["ref"]
        if head == updated:
            pass
        elif github("GET", f"repos/{repository}/compare/{base}...{head}").get("behind_by", 0):
            if updates >= AWAIT_UPDATES:
                raise ReleaseError(f"{base} kept moving on; release pull request #{number} by hand once it is up to date")
            github("PUT", f"repos/{repository}/pulls/{number}/update-branch", {"expected_head_sha": head})
            updates, updated = updates + 1, head
        else:
            runs = github("GET", f"repos/{repository}/actions/workflows/{TEST}/runs"
                                 f"?event=pull_request&head_sha={head}&per_page=5").get("workflow_runs", [])
            if runs and runs[0].get("status") == "completed":
                if runs[0].get("conclusion") == "success":
                    return head
                raise ReleaseError(f"Test concluded {runs[0].get('conclusion')} on pull request #{number}: "
                                   f"{runs[0].get('html_url')}")
        if clock() >= deadline:
            raise ReleaseError(f"gave up waiting for Test on pull request #{number}")
        sleep(POLL_SECONDS * 3)


def settle(version: str, pypi=_pypi, clock=time.time, sleep=time.sleep) -> float:
    """Wait until every index page cached before the upload has expired; the seconds waited."""
    remaining = uploaded_at(version, pypi) + INDEX_MAX_AGE + SETTLE_MARGIN - clock()
    if remaining > 0:
        sleep(remaining)
    return max(remaining, 0.0)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="release_pr.py")
    commands = parser.add_subparsers(dest="command", required=True)
    command = commands.add_parser("published")
    command.add_argument("version")
    command = commands.add_parser("await")
    command.add_argument("--pr", type=int, required=True)
    command = commands.add_parser("resolve")
    command.add_argument("--pr", type=int, required=True)
    command.add_argument("--base", required=True)
    command = commands.add_parser("land")
    command.add_argument("--pr", type=int, required=True)
    command.add_argument("--sha", required=True)
    command.add_argument("--version")
    command = commands.add_parser("settle")
    command.add_argument("version")
    arguments = parser.parse_args(argv)

    try:
        if arguments.command == "published":
            if published(arguments.version):
                print(f"PyPI serves cadgen {arguments.version}.")
                return 0
            print(f"PyPI does not serve cadgen {arguments.version} yet.")
            return 1
        repository = os.environ.get("GITHUB_REPOSITORY", "")
        if arguments.command == "await":
            print(await_tested(arguments.pr, repository))
        elif arguments.command == "resolve":
            pull = resolve(arguments.pr, arguments.base, repository, int(os.environ["GITHUB_REPOSITORY_ID"]))
            print(json.dumps(pull))
        elif arguments.command == "land":
            print(land(arguments.pr, arguments.sha, repository, arguments.version))
        else:
            waited = settle(arguments.version)
            print(f"cadgen {arguments.version} has been on PyPI past its index's max-age (waited {waited:.0f} s).")
    except ReleaseError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
