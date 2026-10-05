"""Publish Release ships only a tree a run tested in full, and names it only once PyPI has it.

The gate looks up the record a Test run made of the release commit's tree
(scripts/github-workflows/tested_tree.py). Found, the tests are not run again; not found,
the workflow runs every Test job on the commit first, and the publish job runs only after
one of the two. The branches installers follow get the release only after PyPI's index lists
it, and the docs feed and the tag only after them.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import os
import re
import unittest
from unittest import mock

from tests.python.support.paths import REPO_ROOT

WORKFLOW = (REPO_ROOT / ".github/workflows/release-publish.yml").read_text(encoding="utf-8")
PREPARE_WORKFLOW = (REPO_ROOT / ".github/workflows/release-prepare.yml").read_text(encoding="utf-8")
JOBS = dict(re.findall(r"^  ([a-z][\w-]*):\n(.*?)(?=^  [a-z][\w-]*:\n|\Z)", WORKFLOW.split("\njobs:\n", 1)[1], re.M | re.S))

def load(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


tested_tree = load("tested_tree", "scripts/github-workflows/tested_tree.py")

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
    def test_merging_a_bump_starts_a_release_and_a_dispatch_resumes_one(self):
        push = re.search(r"^  push:\n(.*?)^  workflow_dispatch:", WORKFLOW, re.M | re.S)[1]
        self.assertRegex(push, r"paths:\n\s+- VERSION\n")
        self.assertIn('sha="$GITHUB_SHA"', JOBS["gate"])
        self.assertIn("git log -1 --first-parent --format=%H -- VERSION", JOBS["gate"])

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

    def test_installers_get_the_version_only_once_pypi_serves_it(self):
        # The upload, then PyPI's index -- what uv resolves a pin through -- listing it, both in the
        # publish job, which the branches job needs. The docs feed and the tag follow the branches.
        publish = JOBS["publish"]
        self.assertLess(publish.index("pypa/gh-action-pypi-publish"), publish.index("https://pypi.org/simple/cadgen/"))
        branches = condition("branches")
        self.assertTrue(evaluate(branches, {"publish": "success"}, {"is_main": "true"}))
        self.assertFalse(evaluate(branches, {"publish": "success"}, {"is_main": "false"}))
        for result in ("failure", "skipped", "cancelled"):
            self.assertFalse(evaluate(branches, {"publish": result}, {"is_main": "true"}))
        for job in ("deploy-docs", "tag-release"):
            with self.subTest(job=job):
                self.assertTrue(evaluate(condition(job), {"branches": "success"}, {}))
                for result in ("skipped", "failure", "cancelled"):
                    self.assertFalse(evaluate(condition(job), {"branches": result}, {}))

    def test_the_branches_get_their_copies_of_the_plugin(self):
        # latest, and plugin, its old name, get one copy; claude.ai's claude-plugin the other.
        body = JOBS["branches"]
        self.assertIn("plugin_branch.py --commit --copy latest", body)
        self.assertIn("plugin_branch.py --commit --copy directory", body)
        self.assertIn('"$latest:refs/heads/latest" "$latest:refs/heads/plugin"', body)
        self.assertIn('"$directory:refs/heads/claude-plugin"', body)
        # latest grew out of plugin, so a clone of plugin fast-forwards onto it.
        self.assertIn('latest_parent="$(tip latest || tip plugin || true)"', body)


class PrepareRelease(unittest.TestCase):
    def test_it_opens_the_pull_request_and_never_merges_it(self):
        # A pull request the workflow's own token opened would start no checks.
        opened = PREPARE_WORKFLOW.split("- name: Open the release pull request", 1)[1]
        self.assertIn("GH_TOKEN: ${{ secrets.PREPARE_RELEASE_TOKEN }}", opened)
        self.assertIn("scripts/release/bump-version.sh", PREPARE_WORKFLOW)
        self.assertNotRegex(PREPARE_WORKFLOW, r"gh pr merge|/merge\b|workflow run release-publish")


if __name__ == "__main__":
    unittest.main()
