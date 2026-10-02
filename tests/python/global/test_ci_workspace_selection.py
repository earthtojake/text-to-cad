"""The workflow's actual job conditions follow the shared-package graph."""
from __future__ import annotations

import re
import subprocess
import unittest

from tests.python.support.paths import REPO_ROOT

WORKFLOW = (REPO_ROOT / ".github/workflows/test.yml").read_text(encoding="utf-8")
JOBS = dict(re.findall(r"^  ([a-z][\w-]*):\n(.*?)(?=^  [a-z][\w-]*:\n|\Z)", WORKFLOW.split("\njobs:\n", 1)[1], re.M | re.S))
CLASSES = {"cadgen", "core", "ui", "web", "mcp", "skills", "docs", "infra"}


def selected_jobs(*changed: str) -> set[str]:
    selected = set()
    for job, body in JOBS.items():
        condition = re.search(r"^    if: (.+)$", body, re.M)
        if condition is None:
            continue
        expression = re.sub(
            r"needs\.changes\.outputs\.(\w+) == 'true'",
            lambda match: str(match[1] in changed),
            condition[1],
        ).replace("||", "or").replace("&&", "and")
        if not re.fullmatch(r"(?:True|False|or|and|\s|[()])+", expression):
            raise AssertionError(f"unhandled workflow condition: {condition[1]}")
        if eval(expression, {"__builtins__": {}}, {}):
            selected.add(job)
    return selected


class WorkspaceWorkflowSelection(unittest.TestCase):
    def test_every_test_runner_runs_in_ci(self):
        # A runner no job calls is a suite that never runs: every test runs in CI (AGENTS.md).
        # `test.sh` only chains the others.
        runners = sorted(path.name for path in (REPO_ROOT / "scripts/test").glob("test-*.sh"))
        self.assertTrue(runners)
        self.assertEqual([name for name in runners if f"scripts/test/{name}" not in WORKFLOW], [])

    def test_every_test_file_is_collected_by_a_ci_runner(self):
        # Every test runs in CI (AGENTS.md): a test-like file outside every runner's collection
        # is one nothing runs. Each pattern restates where a runner looks; a runner that moves
        # must move its pattern here too.
        collected = [
            r"^packages/(core|ui)/(src|scripts)/.*\.test\.[cm]?js$",  # packages/*/scripts/run-tests.mjs
            r"^packages/ui/src/.*\.test\.tsx?$",                        # packages/ui vitest.config.ts
            r"^apps/web/(src|scripts)/.*\.test\.[cm]?js$",              # apps/web/scripts/run-tests.mjs
            r"^apps/mcp/src/.*\.test\.tsx?$",                          # apps/mcp vitest.config.mjs
            r"^apps/docs/src/lib/analytics/[^/]*\.test\.mjs$",          # apps/docs `check` (node --test)
            r"^scripts/bench/viewer-memory/[^/]*\.test\.mjs$",          # test-js.sh --select core
            r"^scripts/test/check-(dependencies|kit-boundaries)\.test\.mjs$",  # test-js.sh
            r"^tests/python/packages/cadgen/(.*/)?test_[^/]*\.py$",      # test-python.sh cadgen
            r"^tests/python/skills/[^/]+/(.*/)?test_[^/]*\.py$",         # test-python.sh skills
            r"^tests/python/global/test_[^/]*\.py$",                     # test-global.sh
            r"^tests/browser/viewer-e2e\.mjs$",                          # test-viewer-browser.sh
        ]
        test_like = re.compile(r"(\.test\.|\.spec\.|(^|/)test_[^/]*\.py$|(^|/)e2e-[^/]*\.m?[jt]s$|^tests/browser/)")
        tracked = subprocess.run(["git", "ls-files"], cwd=REPO_ROOT, capture_output=True, text=True, check=True).stdout.split()
        tests = [path for path in tracked if not path.startswith("models/") and test_like.search(path)]
        self.assertTrue(tests)
        self.assertEqual([path for path in tests if not any(re.search(pattern, path) for pattern in collected)], [])

    def test_ui_change_reaches_both_hosts_without_engine_or_docs_suites(self):
        self.assertEqual(selected_jobs("ui"), {"web", "mcp", "skills", "packaging"})

    def test_web_change_runs_only_web_policy_and_packaging(self):
        self.assertEqual(selected_jobs("web"), {"web", "skills", "packaging"})

    def test_mcp_app_change_runs_only_its_own_suite_policy_and_packaging(self):
        self.assertEqual(selected_jobs("mcp"), {"mcp", "skills", "packaging"})

    def test_docs_change_stays_in_docs(self):
        self.assertEqual(selected_jobs("docs"), {"docs"})

    def test_core_and_infrastructure_reach_every_consumer(self):
        expected = set(JOBS) - {"changes", "version"}
        self.assertEqual(selected_jobs("core"), expected)
        self.assertEqual(selected_jobs("infra"), expected)

    def test_python_change_does_not_run_core_unit_tests(self):
        self.assertEqual(selected_jobs("cadgen"), set(JOBS) - {"changes", "version", "core-js"})

    def test_prose_change_runs_no_conditional_suite(self):
        self.assertEqual(selected_jobs(), set())

    def test_policy_only_changes_do_not_run_skill_cli_suites(self):
        condition = re.search(r"- name: Run every skill suite\n        if: (.+)", JOBS["skills"])[1]
        names = set(re.findall(r"outputs\.(\w+)", condition))
        self.assertEqual(names, {"skills", "cadgen", "core", "infra"})

    def test_every_condition_class_has_a_filter_and_manual_override(self):
        for name in CLASSES:
            with self.subTest(name=name):
                self.assertRegex(JOBS["changes"], rf"(?m)^            {name}:$")
                self.assertIn(f"github.event_name == 'workflow_dispatch' || steps.filter.outputs.{name} == 'true'", JOBS["changes"])
        self.assertIn("'packages/core/**'", JOBS["changes"])
        self.assertIn("'packages/ui/**'", JOBS["changes"])
        self.assertIn("'apps/web/**'", JOBS["changes"])
        self.assertIn("'apps/mcp/**'", JOBS["changes"])

    def test_required_check_names_are_the_jobs(self):
        # main's branch protection requires exactly these names (CONTRIBUTING.md, Repository settings).
        names = {re.search(r"^    name: (.+)$", body, re.M)[1] for body in JOBS.values()}
        self.assertTrue({"Version Check", "cadgen (Linux)", "cadgen (Windows)", "core-js", "web", "skills", "docs", "packaging"} <= names)


if __name__ == "__main__":
    unittest.main()
