"""The workflow's actual job conditions follow the shared-package graph."""
from __future__ import annotations

import importlib.util
import json
import os
import re
import sys
import tempfile
import subprocess
import unittest

from tests.python.support.paths import REPO_ROOT

WORKFLOW = (REPO_ROOT / ".github/workflows/test.yml").read_text(encoding="utf-8")
JOBS = dict(re.findall(r"^  ([a-z][\w-]*):\n(.*?)(?=^  [a-z][\w-]*:\n|\Z)", WORKFLOW.split("\njobs:\n", 1)[1], re.M | re.S))
def load_script(name, path):
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


selector = load_script("select_checks", "scripts/github-workflows/select_checks.py")
doc_contracts = load_script("skill_doc_contracts", "scripts/test/skill_doc_contracts.py")


def evaluate(condition: str, changed: set[str]) -> bool:
    expression = re.sub(
        r"needs\.changes\.outputs\.(\w+) == 'true'",
        lambda match: str(match[1] in changed), condition,
    ).replace("||", "or").replace("&&", "and").replace("!", "not ")
    if not re.fullmatch(r"(?:True|False|or|and|not|\s|[()])+", expression):
        raise AssertionError(f"unhandled workflow condition: {condition}")
    return eval(expression, {"__builtins__": {}}, {})


def selected_jobs(*changed: str) -> set[str]:
    return {
        job for job, body in JOBS.items()
        if (condition := re.search(r"^    if: (.+)$", body, re.M))
        and evaluate(condition[1], set(changed))
    }


def selected_paths(*paths: str) -> set[str]:
    return selected_jobs(*(name for name, enabled in selector.select(list(paths)).items() if enabled is True))


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

    def test_ui_change_reaches_the_web_host_without_engine_or_docs_suites(self):
        self.assertEqual(selected_jobs("ui"), {"web", "skills", "packaging"})

    def test_web_change_runs_only_web_policy_and_packaging(self):
        self.assertEqual(selected_jobs("web"), {"web", "skills", "packaging"})

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

    def test_path_selection_reaches_actual_workflow_conditions(self):
        cases = {
            "skills/urdf/SKILL.md": {"skills"},
            "skills/cad/references/step-generation.md": {"skills"},
            "skills/cad-viewer/SKILL.md": {"skills"},  # also valid after deletion
            "skills/step-parts/agents/openai.yaml": {"skills"},
            "skills/cad/requirements.txt": {"skills"},
            "skills/gcode/scripts/gcode_tool.py": {"skills"},
            "skills/new-skill/template.json": {"skills"},
            "skills/new-skill/agents/helper.py": {"skills"},
            "tests/python/skills/dxf/test_cli.py": {"skills"},
            "tests/python/global/test_skill_requirements.py": {"skills"},
            ".codex-plugin/plugin.json": {"skills"},
            ".github/workflows/release-publish.yml": {"skills", "packaging"},
            ".github/workflows/release-prepare.yml": {"skills"},
            ".github/workflows/deploy-docs.yml": {"docs"},
            "scripts/test/test-docs.sh": {"docs"},
            "scripts/test/test-viewer-launch.sh": {"web", "skills", "packaging"},
            "scripts/test/test-installed.sh": {"packaging"},
            "scripts/test/test-global.sh": {"skills"},
            "apps/web/src/App.tsx": {"web", "skills", "packaging"},
            "packages/ui/src/index.ts": {"web", "skills", "packaging"},
            "CONTRIBUTING.md": set(),
            "models/fixture.step": set(),
        }
        for path, expected in cases.items():
            with self.subTest(path=path):
                self.assertEqual(selected_paths(path), expected)

    def test_prose_runs_contracts_without_runtime_suites(self):
        skill_job = JOBS["skills"]
        docs = re.search(r"- name: Run skill documentation contracts\n        if: (.+)", skill_job)[1]
        runtime = re.search(r"- name: Run every skill suite\n        if: (.+)", skill_job)[1]
        for paths, prose in [
            (["skills/urdf/SKILL.md", "skills/cad-viewer/references/review.md"], True),
            (["skills/gcode/scripts/gcode_tool.py"], False),
            (["skills/cad/requirements.txt"], False),
            (["skills/urdf/SKILL.md", "packages/cadgen/src/cadgen/cli/urdf_validate.py"], False),
        ]:
            flags = selector.select(paths)
            changed = {name for name, enabled in flags.items() if enabled is True}
            self.assertEqual(evaluate(docs, changed), prose)
            self.assertEqual(evaluate(runtime, changed), not prose)
        self.assertEqual(selector.select(["skills/urdf/SKILL.md", "scripts/test/skill_doc_contracts.py"])["skill_names"], [])
        self.assertFalse(selector.select(["skills/urdf/SKILL.md"])["skill_examples"])
        self.assertTrue(selector.select(["skills/cad/SKILL.md"])["skill_examples"])
        self.assertTrue(selector.select(["skills/dxf/references/generator-templates.md"])["skill_examples"])

    def test_prose_setup_installs_only_its_contract_dependencies(self):
        body = JOBS["skills"]
        python = re.search(r"python: \$\{\{ \((.+)\) && 'true'", body)[1]
        npm = re.search(r"npm: \$\{\{ \((.+)\) && 'packages/core'", body)[1]
        browser = re.search(r"playwright: \$\{\{ (.+) \}\}", body)[1]
        for path, dependencies, chromium in [
            ("skills/urdf/SKILL.md", False, False),
            ("skills/step-parts/agents/openai.yaml", False, False),
            ("skills/cad/SKILL.md", True, False),
            ("skills/dxf/references/generator-templates.md", True, False),
            ("skills/cad/requirements.txt", True, True),
            ("packages/core/src/index.js", True, True),
        ]:
            flags = selector.select([path])
            changed = {name for name, enabled in flags.items() if enabled is True}
            with self.subTest(path=path):
                self.assertEqual(evaluate(python, changed), dependencies)
                self.assertEqual(evaluate(npm, changed), dependencies)
                self.assertEqual(evaluate(browser, changed), chromium)

    def test_shared_inputs_and_unknown_infrastructure_stay_conservative(self):
        every = set(JOBS) - {"changes", "version"}
        for path in ("packages/core/src/index.js", "scripts/bundle/lib/node_builders.sh",
                     "scripts/test/common.sh", "scripts/test/test-js.sh", "package-lock.json",
                     "scripts/release/sync-version.mjs", ".github/workflows/test.yml",
                     ".github/actions/setup-deps/action.yml", ".github/workflows/new.yml",
                     "scripts/new-tool.sh", "scripts/release/new-tool.sh",
                     "scripts/utils/new-tool.sh", "scripts/install/new-tool.sh"):
            with self.subTest(path=path):
                self.assertEqual(selected_paths(path), every)
        for path in ("packages/cadgen/src/cadgen/cli/viewer.py", "requirements-dev.txt",
                     "tests/python/packages/cadgen/viewer/test_launcher.py", "tests/python/support/paths.py"):
            self.assertEqual(selected_paths(path), every - {"core-js"})

    def test_selector_output_protocol_and_manual_dispatch(self):
        with tempfile.TemporaryDirectory() as directory:
            output = os.path.join(directory, "outputs")
            result = subprocess.run(
                [sys.executable, str(REPO_ROOT / "scripts/github-workflows/select_checks.py")],
                env={**os.environ, "CHANGED_PATHS": json.dumps(["skills/a name/SKILL.md"]),
                     "EVENT_NAME": "workflow_dispatch", "GITHUB_OUTPUT": output},
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            with open(output, encoding="utf-8") as handle:
                values = dict(line.rstrip().split("=", 1) for line in handle)
            for name in selector.FLAGS:
                self.assertEqual(values[name], "true")
            self.assertEqual(json.loads(values["skill_names"]), [])
            self.assertEqual(selector.select(["skills/a name/SKILL.md"])["skill_names"], ["a name"])
            self.assertEqual(selected_jobs(*selector.FLAGS), set(JOBS) - {"changes", "version"})
        referenced = set(re.findall(r"needs\.changes\.outputs\.(\w+)", WORKFLOW))
        self.assertEqual(referenced, set(selector.FLAGS) | {"skill_names"})
        for name in referenced:
            self.assertIn("${{ steps.select.outputs." + name + " }}", JOBS["changes"])
        self.assertIn("list-files: json", JOBS["changes"])
        self.assertIn("CHANGED_PATHS: ${{ steps.filter.outputs.changed_files }}", JOBS["changes"])
        self.assertIn("EVENT_NAME: ${{ github.event_name }}", JOBS["changes"])

    def test_document_contracts_keep_real_examples_and_dependency_checks(self):
        files = doc_contracts.contract_files(REPO_ROOT, [])
        self.assertTrue(files)
        self.assertTrue(all(path.is_file() for path in files))
        names = {path.name for path in files}
        self.assertTrue({"test_documented_commands.py", "test_documented_models.py",
                         "test_documented_project.py", "test_skill_requirements.py",
                         "test_plugin_manifests.py", "test_skill_self_containment.py"} <= names)
        urdf = doc_contracts.contract_files(REPO_ROOT, ["urdf"])
        self.assertTrue(all("cad" not in path.parts and "dxf" not in path.parts for path in urdf))
        cad = doc_contracts.contract_files(REPO_ROOT, ["cad"])
        self.assertIn(REPO_ROOT / "tests/python/skills/cad/test_documented_models.py", cad)
        # Prose does not import the expensive generation/snapshot/daemon suites.
        self.assertFalse(any("cadgen_daemon" in path.parts or "snapshot" in path.parts for path in files))

    def test_required_check_names_are_the_jobs(self):
        # main's branch protection requires exactly these names (CONTRIBUTING.md, Repository settings).
        names = {re.search(r"^    name: (.+)$", body, re.M)[1] for body in JOBS.values()}
        self.assertTrue({"Version Check", "cadgen (Linux)", "cadgen (Windows)", "core-js", "web", "skills", "docs", "packaging"} <= names)


if __name__ == "__main__":
    unittest.main()
