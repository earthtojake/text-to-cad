"""The workflow's actual job conditions follow the shared-package graph."""
from __future__ import annotations

import re
import unittest

from tests.python.support.paths import REPO_ROOT

WORKFLOW = (REPO_ROOT / ".github/workflows/test.yml").read_text(encoding="utf-8")
JOBS = dict(re.findall(r"^  ([a-z][\w-]*):\n(.*?)(?=^  [a-z][\w-]*:\n|\Z)", WORKFLOW.split("\njobs:\n", 1)[1], re.M | re.S))
CLASSES = {"cadgen", "core", "ui", "viewer", "desktop", "skills", "docs", "infra"}


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
    def test_ui_change_reaches_both_hosts_without_engine_or_docs_suites(self):
        self.assertEqual(selected_jobs("ui"), {"viewer", "desktop", "skills", "packaging"})

    def test_web_change_does_not_run_desktop(self):
        self.assertEqual(selected_jobs("viewer"), {"viewer", "skills", "packaging"})

    def test_desktop_change_stays_in_desktop_and_policy(self):
        self.assertEqual(selected_jobs("desktop"), {"desktop", "skills"})

    def test_docs_change_stays_in_docs(self):
        self.assertEqual(selected_jobs("docs"), {"docs"})

    def test_core_and_infrastructure_reach_every_consumer(self):
        expected = set(JOBS) - {"changes", "version"}
        self.assertEqual(selected_jobs("core"), expected)
        self.assertEqual(selected_jobs("infra"), expected)

    def test_python_change_does_not_run_core_unit_tests(self):
        self.assertEqual(selected_jobs("cadgen"), set(JOBS) - {"changes", "version", "cadgen-js"})

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
        self.assertIn("'apps/desktop/**'", JOBS["changes"])

    def test_existing_required_check_names_remain_available(self):
        names = {re.search(r"^    name: (.+)$", body, re.M)[1] for body in JOBS.values()}
        self.assertTrue({"Version Check", "cadgen (Linux)", "cadgen (Windows)", "cadgen-js", "viewer", "skills", "docs", "packaging"} <= names)


if __name__ == "__main__":
    unittest.main()
