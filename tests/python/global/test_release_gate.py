"""Publish Release ships only a tree a run tested in full, and puts its pin on main last.

The gate looks up the record a Test run made of the release commit's tree
(scripts/github-workflows/tested_tree.py). Found, the tests are not run again; not found,
the workflow runs every Test job on the commit first, and the publish job runs only after
one of the two. A released pull request merges only after its wheel is on PyPI
(scripts/release/release_pr.py), and nothing announces the release until PyPI's index has
had ten minutes to show it.
"""
from __future__ import annotations

import contextlib
import datetime
import importlib.util
import io
import os
import re
import unittest
from unittest import mock

from tests.python.support.paths import REPO_ROOT

WORKFLOW = (REPO_ROOT / ".github/workflows/release-publish.yml").read_text(encoding="utf-8")
VERSION_WORKFLOW = (REPO_ROOT / ".github/workflows/version.yml").read_text(encoding="utf-8")
PREPARE_WORKFLOW = (REPO_ROOT / ".github/workflows/release-prepare.yml").read_text(encoding="utf-8")
JOBS = dict(re.findall(r"^  ([a-z][\w-]*):\n(.*?)(?=^  [a-z][\w-]*:\n|\Z)", WORKFLOW.split("\njobs:\n", 1)[1], re.M | re.S))

def load(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


tested_tree = load("tested_tree", "scripts/github-workflows/tested_tree.py")
release_pr = load("release_pr", "scripts/release/release_pr.py")

REPO_ID = 42


def run(**overrides) -> dict:
    run = {
        "id": 7, "path": ".github/workflows/test.yml", "status": "completed", "conclusion": "success",
        "repository": {"id": REPO_ID}, "head_repository": {"id": REPO_ID},
    }
    run.update(overrides)
    return run


def fake_api(*runs: dict, artifact_repo_id: int = REPO_ID):
    by_id = {entry["id"]: entry for entry in runs}

    def api(path: str) -> dict:
        if "/actions/artifacts?" in path:
            return {"artifacts": [
                {"workflow_run": {"id": entry["id"], "head_repository_id": artifact_repo_id}} for entry in runs
            ]}
        return by_id[int(path.rsplit("/", 1)[1])]

    return api


def condition(job: str) -> str:
    match = re.search(r"^    if: (?:\$\{\{ )?(.+?)(?: \}\})?$", JOBS[job], re.M)
    return match[1]


def evaluate(expression: str, results: dict[str, str], outputs: dict[str, str]) -> bool:
    """A job condition, given the needed jobs' results and the gate's outputs."""
    expression = re.sub(r"needs\.(\w+)\.result (==|!=) '(\w*)'",
                        lambda m: str((results[m[1]] == m[3]) == (m[2] == "==")), expression)
    expression = re.sub(r"needs\.gate\.outputs\.(\w+) (==|!=) '(\w*)'",
                        lambda m: str((outputs.get(m[1], "") == m[3]) == (m[2] == "==")), expression)
    expression = expression.replace("!cancelled()", "True").replace("&&", " and ").replace("||", " or ")
    if not re.fullmatch(r"(?:True|False|and|or|not|\s|[()])+", expression):
        raise AssertionError(f"unhandled condition: {expression}")
    return eval(expression, {"__builtins__": {}}, {})


class TestedTreeRecords(unittest.TestCase):
    def test_a_successful_test_run_of_this_repository_counts(self):
        self.assertEqual(tested_tree.find("tested-t-full", "o/r", REPO_ID, fake_api(run()))["id"], 7)

    def test_a_fork_run_never_counts(self):
        # A fork's pull request runs its own copy of test.yml, so its record proves nothing.
        api = fake_api(run(head_repository={"id": 99}), artifact_repo_id=99)
        self.assertIsNone(tested_tree.find("tested-t-full", "o/r", REPO_ID, api))
        self.assertIsNone(tested_tree.find("tested-t-full", "o/r", REPO_ID, fake_api(run(head_repository={"id": 99}))))

    def test_only_a_completed_successful_test_workflow_run_counts(self):
        for overrides in ({"conclusion": "failure"}, {"status": "in_progress", "conclusion": None},
                          {"path": ".github/workflows/release-publish.yml"}):
            with self.subTest(**{key: str(value) for key, value in overrides.items()}):
                self.assertIsNone(tested_tree.find("tested-t-full", "o/r", REPO_ID, fake_api(run(**overrides))))

    def test_a_lookup_that_fails_is_not_a_record(self):
        def broken(path: str) -> dict:
            raise OSError("api down")

        environment = {"GITHUB_REPOSITORY": "o/r", "GITHUB_REPOSITORY_ID": str(REPO_ID), "GITHUB_TOKEN": "t"}
        with mock.patch.object(tested_tree, "_api", broken), mock.patch.dict(os.environ, environment), \
                contextlib.redirect_stderr(io.StringIO()) as stderr:
            self.assertEqual(tested_tree.main(["tested-t-full"]), 1)
        self.assertIn("api down", stderr.getvalue())


class PublishGate(unittest.TestCase):
    def test_only_a_push_that_moves_version_starts_a_release(self):
        push = re.search(r"^  push:\n(.*?)^  workflow_dispatch:", WORKFLOW, re.M | re.S)[1]
        self.assertRegex(push, r"paths:\n\s+- VERSION\n")

    def test_the_gate_asks_for_a_full_record_of_the_release_tree(self):
        self.assertIn("tested-$(git rev-parse 'HEAD^{tree}')-full", JOBS["gate"])
        self.assertIn("tested_tree.py", JOBS["gate"])

    def test_untested_trees_run_every_test_job_on_the_release_commit(self):
        body = JOBS["test"]
        self.assertIn("uses: ./.github/workflows/test.yml", body)
        self.assertRegex(body, r"full: true")
        self.assertIn("ref: ${{ needs.gate.outputs.release_sha }}", body)
        outputs = {"should_publish": "true"}
        self.assertTrue(evaluate(condition("test"), {}, {**outputs, "tested": "false"}))
        self.assertFalse(evaluate(condition("test"), {}, {**outputs, "tested": "true"}))

    def test_publish_runs_after_a_record_or_a_full_test_and_never_otherwise(self):
        publish = condition("publish")
        cases = [
            # (test job result, gate found a record, publish runs)
            ("skipped", "true", True),
            ("success", "false", True),
            ("failure", "false", False),
            ("cancelled", "false", False),
            ("skipped", "false", False),
        ]
        for result, tested, expected in cases:
            with self.subTest(test=result, tested=tested):
                self.assertEqual(evaluate(publish, {"test": result}, {"should_publish": "true", "tested": tested}), expected)
        self.assertFalse(evaluate(publish, {"test": "skipped"}, {"should_publish": "false", "tested": "true"}))

    def test_a_dispatch_names_the_pull_request_it_releases(self):
        self.assertRegex(WORKFLOW, r"workflow_dispatch:\n    inputs:\n      pr:")
        self.assertIn("release_pr.py resolve --pr", JOBS["gate"])
        # Its head must already hold the branch, so the tree tested is the tree that lands.
        self.assertIn('git merge-base --is-ancestor "origin/$GITHUB_REF_NAME" "$sha"', JOBS["gate"])

    def test_the_pull_request_merges_only_after_a_successful_publish(self):
        merge = condition("merge")
        self.assertTrue(evaluate(merge, {"publish": "success"}, {"pr": "554"}))
        self.assertFalse(evaluate(merge, {"publish": "success"}, {"pr": ""}))
        for result in ("failure", "skipped", "cancelled"):
            self.assertFalse(evaluate(merge, {"publish": result}, {"pr": "554"}))
        # On main the merge waits for PyPI and the held Version Check; a rehearsal uploads nothing.
        self.assertIn('[ "$IS_MAIN" = "true" ] && args+=(--version "$VERSION")', JOBS["merge"])
        self.assertIn('"$(git rev-parse "$merged^{tree}")" != "$(git rev-parse "$SHA^{tree}")"', JOBS["merge"])
        # The PyPI upload is in the publish job, which the merge job needs: PyPI first, main after.
        self.assertIn("pypa/gh-action-pypi-publish", JOBS["publish"])
        self.assertRegex(JOBS["merge"], r"needs:\n      - gate\n      - publish\n")

    def test_nothing_announces_a_release_before_the_index_settles(self):
        settle = condition("settle")
        self.assertTrue(evaluate(settle, {"publish": "success", "merge": "success"}, {"is_main": "true"}))
        self.assertTrue(evaluate(settle, {"publish": "success", "merge": "skipped"}, {"is_main": "true"}))
        self.assertFalse(evaluate(settle, {"publish": "success", "merge": "failure"}, {"is_main": "true"}))
        self.assertFalse(evaluate(settle, {"publish": "failure", "merge": "skipped"}, {"is_main": "true"}))
        self.assertFalse(evaluate(settle, {"publish": "success", "merge": "skipped"}, {"is_main": "false"}))
        self.assertIn("release_pr.py settle", JOBS["settle"])
        for job in ("deploy-docs", "plugin-branch", "tag-release"):
            with self.subTest(job=job):
                expression = condition(job)
                self.assertTrue(evaluate(expression, {"settle": "success"}, {}))
                for result in ("skipped", "failure", "cancelled"):
                    self.assertFalse(evaluate(expression, {"settle": result}, {}))
                # What a release announces is the commit main got: the merge, or the pushed commit.
                self.assertIn("${{ needs.merge.outputs.sha || needs.gate.outputs.release_sha }}", JOBS[job])

    def test_version_check_holds_a_release_until_its_wheel_is_on_pypi(self):
        hold = VERSION_WORKFLOW.split("- name: Hold the merge until PyPI has the release", 1)[1]
        self.assertIn("if: steps.release.outputs.version != '' && github.base_ref == 'main'", hold)
        self.assertIn('release_pr.py published "$VERSION"', hold)
        self.assertIn("name: Version Check", VERSION_WORKFLOW)
        self.assertNotIn("name: Version Check", (REPO_ROOT / ".github/workflows/test.yml").read_text(encoding="utf-8"))


class FakeGitHub:
    """GitHub's REST API, as release_pr.py uses it, with a call log."""

    def __init__(self, pull: dict | None = None, check: dict | None = None, rerun: dict | None = None):
        self.calls = []
        self.pull = pull or {}
        self.check = check or {"id": 9, "status": "completed", "conclusion": "failure", "run_attempt": 1}
        self.rerun = rerun or {"id": 9, "status": "completed", "conclusion": "success", "run_attempt": 2}
        self.reran = False

    def __call__(self, method: str, path: str, body: dict | None = None) -> dict:
        self.calls.append((method, path.split("?", 1)[0]))
        if method == "GET" and path.endswith("/pulls/554"):
            return self.pull
        if method == "GET" and "/workflows/version.yml/runs" in path:
            return {"workflow_runs": [self.check]}
        if method == "GET" and path.endswith("/runs/9"):
            return self.rerun if self.reran else self.check
        if method == "POST" and path.endswith("/rerun-failed-jobs"):
            self.reran = True
            return {}
        if method == "PUT" and path.endswith("/pulls/554/merge"):
            assert body == {"merge_method": "squash", "sha": "abc"}, body
            return {"merged": True, "sha": "def"}
        raise AssertionError(f"unexpected {method} {path}")


class Clock:
    def __init__(self, now: float = 1_000_000.0):
        self.now = now
        self.slept = []

    def time(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


def on_pypi(after_polls: int = 0, uploaded: str = "2026-10-05T04:52:00Z"):
    state = {"polls": 0}

    def pypi(version: str) -> dict | None:
        state["polls"] += 1
        if state["polls"] <= after_polls:
            return None
        return {"urls": [{"upload_time_iso_8601": uploaded}, {"upload_time_iso_8601": "2026-10-05T04:53:00Z"}]}

    return pypi


class ReleasePullRequests(unittest.TestCase):
    PULL = {"state": "open", "draft": False, "title": "Release", "base": {"ref": "main"},
            "head": {"sha": "abc", "repo": {"id": REPO_ID}}}

    def test_only_an_open_ready_pull_request_of_this_repository_into_the_branch_is_released(self):
        github = FakeGitHub(pull=self.PULL)
        self.assertEqual(release_pr.resolve(554, "main", "o/r", REPO_ID, github)["sha"], "abc")
        for change, reason in ((
            {"state": "closed"}, "closed"), ({"draft": True}, "draft"),
            ({"base": {"ref": "build-test"}}, "targets build-test"),
            ({"head": {"sha": "abc", "repo": {"id": 99}}}, "fork"),
        ):
            with self.subTest(reason=reason), self.assertRaisesRegex(release_pr.ReleaseError, reason):
                release_pr.resolve(554, "main", "o/r", REPO_ID, FakeGitHub(pull={**self.PULL, **change}))

    def test_a_release_merges_only_once_pypi_serves_it_and_its_version_check_passes(self):
        github, clock = FakeGitHub(), Clock()
        sha = release_pr.land(554, "abc", "o/r", "0.7.15", github=github, pypi=on_pypi(after_polls=2),
                              clock=clock.time, sleep=clock.sleep)
        self.assertEqual(sha, "def")
        # Polled PyPI until it served the version, then re-ran the held check, then merged.
        self.assertEqual(clock.slept[:2], [release_pr.POLL_SECONDS] * 2)
        methods = [method for method, _ in github.calls]
        self.assertLess(methods.index("POST"), methods.index("PUT"))
        self.assertEqual(github.calls[-1], ("PUT", "repos/o/r/pulls/554/merge"))

    def test_a_version_check_that_still_fails_stops_the_merge(self):
        github = FakeGitHub(rerun={"id": 9, "status": "completed", "conclusion": "failure", "run_attempt": 2})
        clock = Clock()
        with self.assertRaisesRegex(release_pr.ReleaseError, "concluded failure"):
            release_pr.land(554, "abc", "o/r", "0.7.15", github=github, pypi=on_pypi(), clock=clock.time, sleep=clock.sleep)
        self.assertNotIn("PUT", [call[0] for call in github.calls])

    def test_a_version_pypi_never_serves_is_never_merged(self):
        github, clock = FakeGitHub(), Clock()
        with self.assertRaisesRegex(release_pr.ReleaseError, "PyPI to serve"):
            release_pr.land(554, "abc", "o/r", "0.7.15", github=github, pypi=lambda version: None,
                            clock=clock.time, sleep=clock.sleep)
        self.assertEqual(github.calls, [])

    def test_a_rehearsal_merges_without_pypi(self):
        github = FakeGitHub()
        self.assertEqual(release_pr.land(554, "abc", "o/r", github=github), "def")
        self.assertEqual(github.calls, [("PUT", "repos/o/r/pulls/554/merge")])

    def test_the_announcements_wait_out_the_index_cache_from_the_first_upload(self):
        # Two files, uploaded a minute apart: the wait counts from the first.
        uploaded = datetime.datetime(2026, 10, 5, 4, 52, tzinfo=datetime.timezone.utc).timestamp()
        pypi = on_pypi(uploaded="2026-10-05T04:52:00Z")
        clock = Clock(now=uploaded + 120)
        waited = release_pr.settle("0.7.15", pypi=pypi, clock=clock.time, sleep=clock.sleep)
        self.assertEqual(waited, release_pr.INDEX_MAX_AGE + release_pr.SETTLE_MARGIN - 120)
        # A resume long after the upload does not wait at all.
        clock = Clock(now=uploaded + 3600)
        self.assertEqual(release_pr.settle("0.7.15", pypi=pypi, clock=clock.time, sleep=clock.sleep), 0.0)
        self.assertEqual(clock.slept, [])


class AwaitGitHub:
    """A release pull request whose base moves on `behind` times, then whose Test run ends `conclusion`."""

    def __init__(self, behind: int = 0, conclusion: str = "success", state: str = "open"):
        self.calls, self.head, self.behind, self.conclusion, self.state = [], "h0", behind, conclusion, state
        self.polls, self.updating = 0, 0

    def __call__(self, method: str, path: str, body: dict | None = None) -> dict:
        self.calls.append((method, path.split("?", 1)[0], body))
        if path.endswith("/pulls/9"):
            # GitHub updates a branch after it answers: the head moves a poll later.
            if self.updating:
                self.updating -= 1
                if not self.updating:
                    self.behind -= 1
                    self.head = f"h{int(self.head[1:]) + 1}"
            return {"state": self.state, "head": {"sha": self.head}, "base": {"ref": "main"}}
        if "/compare/main..." in path:
            return {"behind_by": 1 if self.behind else 0}
        if path.endswith("/update-branch"):
            assert body == {"expected_head_sha": self.head} and not self.updating, body
            self.updating = 2
            return {}
        if "/workflows/test.yml/runs" in path:
            self.polls += 1
            if self.polls == 1:
                return {"workflow_runs": [{"status": "in_progress", "conclusion": None}]}
            return {"workflow_runs": [{"status": "completed", "conclusion": self.conclusion, "html_url": "u"}]}
        raise AssertionError(f"unexpected {method} {path}")


class ExplicitReleasePullRequests(unittest.TestCase):
    def test_it_releases_the_head_test_passed_on(self):
        github, clock = AwaitGitHub(), Clock()
        self.assertEqual(release_pr.await_tested(9, "o/r", github, clock.time, clock.sleep), "h0")

    def test_it_keeps_the_branch_up_to_date_and_waits_for_the_new_head(self):
        github, clock = AwaitGitHub(behind=2), Clock()
        self.assertEqual(release_pr.await_tested(9, "o/r", github, clock.time, clock.sleep), "h2")
        self.assertEqual([call[2] for call in github.calls if call[0] == "PUT"],
                         [{"expected_head_sha": "h0"}, {"expected_head_sha": "h1"}])

    def test_a_failing_test_run_or_a_base_that_will_not_settle_stops_it(self):
        clock = Clock()
        with self.assertRaisesRegex(release_pr.ReleaseError, "Test concluded failure"):
            release_pr.await_tested(9, "o/r", AwaitGitHub(conclusion="failure"), clock.time, clock.sleep)
        with self.assertRaisesRegex(release_pr.ReleaseError, "kept moving on"):
            release_pr.await_tested(9, "o/r", AwaitGitHub(behind=release_pr.AWAIT_UPDATES + 1), clock.time, clock.sleep)
        with self.assertRaisesRegex(release_pr.ReleaseError, "is closed"):
            release_pr.await_tested(9, "o/r", AwaitGitHub(state="closed"), clock.time, clock.sleep)

    def test_prepare_release_opens_the_pull_request_and_never_merges_it(self):
        # Its own token's pull request would start no checks, so a token that starts workflows opens it.
        opened = PREPARE_WORKFLOW.split("- name: Open the release pull request", 1)[1].split("- name:", 1)[0]
        self.assertIn("GH_TOKEN: ${{ secrets.PREPARE_RELEASE_TOKEN }}", opened)
        self.assertIn("scripts/release/bump-version.sh", PREPARE_WORKFLOW)
        self.assertNotRegex(PREPARE_WORKFLOW, r"gh pr merge|/merge\b")
        # It releases only through Publish Release, after Test passed on the pull request.
        wait, release = (PREPARE_WORKFLOW.index("- name: Wait for Test to pass on it"),
                         PREPARE_WORKFLOW.index("- name: Release it"))
        self.assertLess(wait, release)
        self.assertIn("release_pr.py await", PREPARE_WORKFLOW[wait:release])
        self.assertIn('gh workflow run release-publish.yml --repo "$GITHUB_REPOSITORY" --ref "$TARGET" -f pr="$PR"',
                      PREPARE_WORKFLOW[release:])


if __name__ == "__main__":
    unittest.main()
