"""Every test runs in CI, and a change runs what can break: test.yml against its selector.

scripts/github-workflows/select_checks.py maps each changed path to the tests that read it;
test.yml runs each job on the selector's flag for it. These tests hold the two together and
the table to the tree, and pin how each kind of change is routed.
"""
from __future__ import annotations

import importlib.util
import os
import re
import subprocess
import sys
import unittest
from pathlib import Path

from tests.python.support.paths import REPO_ROOT
from tests.python.support.tmp_root import temporary_directory

WORKFLOW = (REPO_ROOT / ".github/workflows/test.yml").read_text(encoding="utf-8")
JOBS = dict(re.findall(r"^  ([a-z][\w-]*):\n(.*?)(?=^  [a-z][\w-]*:\n|\Z)", WORKFLOW.split("\njobs:\n", 1)[1], re.M | re.S))

_spec = importlib.util.spec_from_file_location("select_checks", REPO_ROOT / "scripts/github-workflows/select_checks.py")
selector = importlib.util.module_from_spec(_spec)
sys.modules.setdefault("select_checks", selector)
_spec.loader.exec_module(selector)

GATED = set(JOBS) - {"changes", "version"}
TRACKED = subprocess.run(["git", "ls-files"], cwd=REPO_ROOT, capture_output=True, text=True, check=True).stdout.split()
CADGEN, POLICY, SKILLS = selector.CADGEN_SUITE, selector.POLICY_SUITE, selector.SKILL_SUITES


def route(*paths: str) -> dict[str, str]:
    return selector.outputs(selector.select_paths(paths), changed=bool(paths))


def condition(job: str) -> str:
    return re.search(r"^    if: .*?needs\.changes\.outputs\.(\w+) == 'true'", JOBS[job], re.M)[1]


def jobs_for(*paths: str) -> set[str]:
    """The jobs test.yml runs for a change to `paths`, read from each job's own condition."""
    selected = route(*paths)
    return {job for job in GATED if selected[condition(job)] == "true"}


def tests_for(*paths: str) -> dict[str, list[str]]:
    selected = route(*paths)
    return {key: selected[key].split() for key in ("cadgen_tests", "skills_policy", "skills_tests")}


class EveryTestRunsInCI(unittest.TestCase):
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
            r"^apps/docs/src/lib/api/[^/]*\.test\.mjs$",          # apps/docs `check` (node --test)
            r"^scripts/brand/[^/]*\.test\.mjs$",                          # test-docs.sh
            r"^scripts/bench/viewer-memory/[^/]*\.test\.mjs$",          # test-js.sh --select core
            r"^scripts/test/check-(dependencies|kit-boundaries)\.test\.mjs$",  # test-js.sh
            r"^tests/python/packages/cadgen/(.*/)?test_[^/]*\.py$",      # test-python.sh cadgen
            r"^tests/python/skills/[^/]+/(.*/)?test_[^/]*\.py$",         # test-python.sh skills
            r"^tests/python/global/test_[^/]*\.py$",                     # test-global.sh
            r"^tests/browser/viewer-e2e\.mjs$",                          # test-viewer-browser.sh
        ]
        test_like = re.compile(r"(\.test\.|\.spec\.|(^|/)test_[^/]*\.py$|(^|/)e2e-[^/]*\.m?[jt]s$|^tests/browser/)")
        tests = [path for path in TRACKED if not path.startswith("models/") and test_like.search(path)]
        self.assertTrue(tests)
        self.assertEqual([path for path in tests if not any(re.search(pattern, path) for pattern in collected)], [])

    def test_a_full_run_runs_every_job_and_every_suite_whole(self):
        selected = selector.outputs(selector.EVERYTHING)
        self.assertEqual(jobs_for("VERSION"), GATED)
        self.assertEqual(selected["cadgen_tests"], CADGEN)
        self.assertEqual(selector.scope(selected), "full")
        # Light tests run in the light phase, every other test in the heavy one: together, all.
        policy = set(selected["light_policy"].split()) | set(selected["skills_policy"].split())
        self.assertEqual(policy, {path.relative_to(REPO_ROOT).as_posix() for path in (REPO_ROOT / POLICY).glob("test_*.py")})
        suites = set(selected["light_tests"].split()) | set(selected["skills_tests"].split())
        self.assertEqual(suites, {f"{SKILLS}/{path.name}" for path in (REPO_ROOT / SKILLS).iterdir() if path.is_dir()})

    def test_the_light_contracts_run_on_every_change_and_install_nothing(self):
        for path in ("models/examples/src/part.py", "README.md", "packages/cadgen/src/cadgen/step.py"):
            with self.subTest(path=path):
                selected = route(path)
                self.assertEqual(selected["skills"], "true")
                self.assertEqual(selected["light_policy"].split(), selector.light_policy())
        light = JOBS["skills"].split("- name: Set up dependencies", 1)[0]
        self.assertIn('PYTHON_TEST_RUNTIME: "0"', light)
        self.assertNotIn("setup-deps", light)


class TheTableHoldsToTheTree(unittest.TestCase):
    def test_every_test_path_a_rule_names_exists(self):
        # A misspelt test path would select nothing, silently.
        for rule in selector.RULES:
            if isinstance(rule.selects, selector.Select):
                for path in rule.selects.cadgen | rule.selects.policy | rule.selects.skills:
                    with self.subTest(path=path):
                        self.assertTrue((REPO_ROOT / path).exists())
        for name in selector.HEAVY_POLICY:
            self.assertTrue((REPO_ROOT / POLICY / name).is_file(), name)
        for path in selector.LIGHT_SKILL_TESTS:
            self.assertTrue((REPO_ROOT / path).is_dir(), path)

    def test_every_heavy_policy_test_has_a_rule_that_runs_it(self):
        # The light contracts run on every change; a heavy one runs only when a rule names it,
        # so one no rule names would run only when everything does.
        named = set()
        for rule in selector.RULES:
            if isinstance(rule.selects, selector.Select) and not rule.selects.full:
                named |= rule.selects.policy
        self.assertEqual(sorted(f"{POLICY}/{name}" for name in selector.HEAVY_POLICY if f"{POLICY}/{name}" not in named), [])

    def test_every_rule_matches_a_tracked_path(self):
        present = TRACKED + [path.relative_to(REPO_ROOT).as_posix() for path in (REPO_ROOT / "scripts").rglob("*")]
        for rule in selector.RULES:
            for pattern in rule.patterns:
                if pattern in selector.ABSENT_ON_PURPOSE:
                    continue
                with self.subTest(pattern=pattern):
                    compiled = selector.compile_glob(pattern)
                    self.assertTrue(any(compiled.match(path) for path in present), "a rule for nothing")

    def test_every_tracked_path_is_known(self):
        # A path the table does not know runs everything; none should be unknown today.
        compiled = [[selector.compile_glob(pattern) for pattern in rule.patterns] for rule in selector.rules()]
        unknown = [path for path in TRACKED if not any(p.match(path) for patterns in compiled for p in patterns)]
        self.assertEqual(unknown, [])

    def test_light_tests_never_skip_for_a_missing_dependency(self):
        # The light phase installs nothing; a test that skipped itself without a dependency
        # would pass there having tested nothing.
        light = [REPO_ROOT / path for path in selector.light_policy()]
        light += [file for path in selector.LIGHT_SKILL_TESTS for file in sorted((REPO_ROOT / path).rglob("test*.py"))]
        for file in light:
            with self.subTest(file=file.name):
                self.assertNotRegex(file.read_text(encoding="utf-8"), r"except (ImportError|ModuleNotFoundError)")


class TheWorkflowFollowsTheSelector(unittest.TestCase):
    def test_every_gated_job_runs_on_its_own_flag(self):
        flags = set(route())
        for job in GATED:
            with self.subTest(job=job):
                self.assertIn(condition(job), flags)

    def test_every_output_the_jobs_read_is_one_the_selector_writes(self):
        written = set(route()) | {"record"}
        exposed = dict(re.findall(r"^      (\w+): \$\{\{ steps\.select\.outputs\.(\w+) \}\}$", JOBS["changes"], re.M))
        self.assertTrue(exposed)
        self.assertTrue(all(name == source and name in written for name, source in exposed.items()))
        self.assertLessEqual(set(re.findall(r"needs\.changes\.outputs\.(\w+)", WORKFLOW)), set(exposed))
        self.assertEqual(written - {"record", "full"}, set(exposed))

    def test_a_manual_or_called_run_selects_everything_and_records_it(self):
        self.assertIn("FULL: ${{ github.event_name == 'workflow_dispatch' || inputs.full }}", JOBS["changes"])
        self.assertIn("name: ${{ steps.select.outputs.record }}", JOBS["changes"])
        # A record only saves a re-run: failing to upload one must not fail the run.
        self.assertIn("continue-on-error: true", JOBS["changes"].split("- name: Record the tree this run tests", 1)[1])
        # A pull request is diffed on its merge commit; only a push reads `before`.
        self.assertIn("BEFORE: ${{ github.event_name == 'push' && github.event.before || '' }}", JOBS["changes"])
        script = REPO_ROOT / "scripts/github-workflows/select_checks.py"
        environment = {key: value for key, value in os.environ.items() if not key.startswith("GITHUB_")}
        with temporary_directory(prefix="select-checks-") as temp:
            output = Path(temp) / "output"
            environment.update({"FULL": "true", "GITHUB_OUTPUT": str(output), "RUNNER_TEMP": temp})
            result = subprocess.run([sys.executable, str(script)], cwd=REPO_ROOT, env=environment,
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            values = dict(line.split("=", 1) for line in output.read_text(encoding="utf-8").splitlines())
        self.assertTrue(values["record"].startswith("tested-") and values["record"].endswith("-full"))
        self.assertEqual({job for job in GATED if values[condition(job)] == "true"}, GATED)

    def test_a_selection_that_failed_fails_a_required_check(self):
        # Every job waits on Changed paths, and GitHub counts a job skipped for a failed dependency
        # as a passing required check. skills is required and runs for every change, so it also runs
        # when Changed paths failed -- and fails.
        skills = JOBS["skills"]
        self.assertRegex(skills, r"(?m)^    if: \$\{\{ !cancelled\(\) && \(needs\.changes\.result != 'success' \|\| ")
        guard = skills.split("steps:", 1)[1].split("- name:", 2)[1]
        self.assertIn("if: needs.changes.result != 'success'", guard)
        self.assertIn("exit 1", guard)
        self.assertTrue(all(route(path)["skills"] == "true" for path in ("README.md", "skills/cad/SKILL.md", "VERSION")))

    def test_required_check_names_are_the_jobs(self):
        # main's branch protection requires exactly these names (CONTRIBUTING.md, Repository settings).
        names = {re.search(r"^    name: (.+)$", body, re.M)[1] for body in JOBS.values()}
        self.assertTrue({"Version Check", "cadgen (Linux)", "cadgen (Windows)", "core-js", "web", "skills", "docs",
                         "packaging"} <= names)


class ChangesRunWhatCanBreak(unittest.TestCase):
    def test_what_runs_everything(self):
        for path in ("VERSION", "package-lock.json", "requirements-dev.txt", ".github/workflows/test.yml",
                     ".github/actions/setup-deps/action.yml", "scripts/github-workflows/select_checks.py",
                     "scripts/test/common.sh", "tests/python/support/paths.py", "packages/core/src/common/camera.js",
                     "somewhere/new.thing"):
            with self.subTest(path=path):
                self.assertEqual(jobs_for(path), GATED)
                self.assertEqual(route(path)["full"], "true")

    def test_prose_and_metadata_run_only_the_contracts_that_read_them(self):
        for path in ("README.md", "CONTRIBUTING.md", "AGENTS.md", "LICENSE", ".claude-plugin/plugin.json",
                     "claude.mcp.json", "skills.sh.json", "skills/urdf/SKILL.md", "skills/urdf/references/joints.md",
                     "skills/step-parts/agents/openai.yaml", "packages/core/README.md", "packages/ui/docs/lod.md",
                     "docs/migrations/migrating-0.4-to-0.5.md", "models/examples/src/part.py",
                     ".github/workflows/release-publish.yml", ".github/workflows/release-prepare.yml",
                     "scripts/release/bump-version.sh", "scripts/release/plugin_branch.py"):
            with self.subTest(path=path):
                self.assertEqual(jobs_for(path) - {"skills"}, set())
                self.assertEqual(route(path)["skills_runtime"], "false")

    def test_skill_prose_that_documents_runnable_code_runs_that_code(self):
        self.assertEqual(tests_for("skills/cad/references/positioning.md")["skills_tests"],
                         [f"{SKILLS}/cad/test_documented_models.py", f"{SKILLS}/cad/test_documented_project.py"])
        self.assertEqual(tests_for("skills/dxf/SKILL.md")["skills_tests"], [f"{SKILLS}/dxf/test_documented_commands.py"])
        snapshot_review = tests_for("skills/cad/references/snapshot-review.md")
        self.assertEqual(snapshot_review["cadgen_tests"], [f"{CADGEN}/test_snapshot_requests.py"])
        self.assertEqual(jobs_for("skills/cad/references/snapshot-review.md"), {"cadgen-linux", "cadgen-windows", "skills"})

    def test_a_skill_script_runs_its_suite(self):
        self.assertEqual(tests_for("skills/dfm/scripts/mold_tool.py")["skills_tests"], [f"{SKILLS}/dfm"])
        # gcode's suite is light, so it already runs on every change.
        self.assertEqual(jobs_for("skills/gcode/scripts/orca_presets.py"), {"skills"})

    def test_a_test_file_runs_itself(self):
        self.assertEqual(tests_for(f"{CADGEN}/test_settings.py")["cadgen_tests"], [f"{CADGEN}/test_settings.py"])
        self.assertEqual(jobs_for(f"{CADGEN}/test_settings.py"), {"cadgen-linux", "cadgen-windows", "skills"})
        self.assertEqual(tests_for(f"{POLICY}/test_cli_stream_contract.py")["skills_policy"],
                         [f"{POLICY}/test_cli_stream_contract.py"])
        self.assertEqual(tests_for(f"{SKILLS}/dxf/test_drawing_checks.py")["skills_tests"], [f"{SKILLS}/dxf/test_drawing_checks.py"])
        self.assertEqual(tests_for(f"{SKILLS}/cad/__init__.py")["skills_tests"], [f"{SKILLS}/cad"])

    def test_cadgen_runs_its_suites_its_hosts_and_the_wheel(self):
        self.assertEqual(jobs_for("packages/cadgen/src/cadgen/step.py"), GATED - {"core-js", "mcp", "docs"})
        chosen = tests_for("packages/cadgen/src/cadgen/step.py")
        self.assertEqual(chosen["cadgen_tests"], [CADGEN])
        self.assertEqual(chosen["skills_tests"], [f"{SKILLS}/cad", f"{SKILLS}/dxf"])
        self.assertEqual(set(chosen["skills_policy"]), {f"{POLICY}/{name}" for name in selector.HEAVY_POLICY})
        self.assertEqual(route("packages/cadgen/src/cadgen/step.py")["web_ui"], "false")

    def test_the_viewer_and_the_mcp_server_reach_only_what_reaches_them(self):
        viewer = tests_for("packages/cadgen/src/cadgen/viewer/scanner.py")
        self.assertIn(f"{CADGEN}/viewer/test_launcher.py", viewer["cadgen_tests"])
        self.assertIn(f"{CADGEN}/mcp/test_server.py", viewer["cadgen_tests"])
        self.assertNotIn(f"{CADGEN}/test_step_publication.py", viewer["cadgen_tests"])
        self.assertIn(f"{CADGEN}/test_cli_from_function.py", viewer["cadgen_tests"])  # imports every command
        self.assertIn(f"{CADGEN}/test_atomic_replace.py", viewer["cadgen_tests"])  # reads every source
        self.assertEqual(viewer["skills_tests"], [])
        self.assertEqual(jobs_for("packages/cadgen/src/cadgen/viewer/scanner.py"),
                         {"cadgen-linux", "cadgen-windows", "web", "skills", "packaging"})
        mcp = tests_for("packages/cadgen/src/cadgen/mcp/server.py")
        self.assertIn(f"{CADGEN}/mcp/test_server.py", mcp["cadgen_tests"])
        self.assertNotIn(f"{CADGEN}/viewer/test_launcher.py", mcp["cadgen_tests"])
        self.assertEqual(jobs_for("packages/cadgen/src/cadgen/mcp/server.py"),
                         {"cadgen-linux", "cadgen-windows", "skills", "packaging"})
        # The state directory's one definition is shared with the rest of cadgen.
        self.assertEqual(tests_for("packages/cadgen/src/cadgen/viewer/recents.py")["cadgen_tests"], [CADGEN])

    def test_ui_reaches_both_hosts_and_the_wheel_not_the_engine(self):
        self.assertEqual(jobs_for("packages/ui/src/index.ts"), {"web", "mcp", "skills", "packaging"})
        selected = route("packages/ui/src/index.ts")
        self.assertEqual((selected["web_ui"], selected["web_client"], selected["web_viewer"]), ("true", "true", "true"))
        # ...but the DXF suite reads ui's fixture and its JavaScript.
        self.assertEqual(tests_for("packages/ui/src/renderers/dxf/__fixtures__/sample.dxf")["skills_tests"],
                         [f"{SKILLS}/dxf/test_snapshot_render.py"])
        self.assertEqual(tests_for("packages/ui/src/renderers/dxf/DxfRenderer.js")["skills_tests"],
                         [f"{SKILLS}/dxf/test_drawing_checks.py"])

    def test_each_app_runs_its_own_job(self):
        self.assertEqual(jobs_for("apps/web/src/main.tsx"), {"web", "skills", "packaging"})
        self.assertEqual(route("apps/web/src/main.tsx")["web_ui"], "false")
        self.assertEqual(jobs_for("apps/mcp/src/App.tsx"), {"mcp", "skills", "packaging"})
        self.assertEqual(jobs_for("apps/docs/src/app/page.tsx"), {"docs", "core-js", "skills"})
        self.assertEqual(jobs_for("apps/docs/public/brand/logo.svg"), {"docs", "skills"})
        # apps/web's tests resolve the links in its Markdown, so what they link to is web input.
        self.assertEqual(jobs_for("apps/web/README.md"), {"web", "skills"})
        for target in selector.web_link_targets():
            with self.subTest(target=target):
                self.assertEqual(route(target)["web_client"], "true")

    def test_scripts_run_what_runs_them(self):
        cases = {
            "scripts/test/test-viewer-launch.sh": {"web", "skills"},
            "scripts/test/test-installed.sh": {"packaging", "skills"},
            "scripts/test/test-docs.sh": {"docs", "skills"},
            "scripts/test/test-js.sh": {"core-js", "web", "mcp", "skills"},
            "scripts/test/check-dependencies.mjs": {"core-js", "web", "mcp", "skills"},
            "scripts/test/test-global.sh": {"skills"},
            "scripts/test/test-python.sh": {"cadgen-linux", "cadgen-windows", "skills"},
            "scripts/release/sync-version.mjs": {"packaging", "skills"},
            "scripts/github-workflows/check-builds.sh": {"packaging", "skills"},
            "scripts/bundle/bundle.sh": GATED - {"core-js", "mcp", "docs"},
            "scripts/brand/generate-logos.mjs": {"docs", "skills"},
            "scripts/bench/viewer-memory/helpers.mjs": {"core-js", "skills"},
        }
        for path, expected in cases.items():
            with self.subTest(path=path):
                self.assertEqual(jobs_for(path), expected)
        self.assertEqual(tests_for("scripts/test/test-global.sh")["skills_policy"],
                         [f"{POLICY}/{name}" for name in sorted(selector.HEAVY_POLICY)])

    def test_a_deleted_test_file_has_nothing_left_to_run(self):
        self.assertEqual(jobs_for(f"{CADGEN}/test_gone_for_good.py"), {"skills"})

    def test_mixed_changes_take_the_union(self):
        self.assertEqual(jobs_for("apps/docs/src/app/page.tsx", "apps/mcp/src/App.tsx"),
                         {"docs", "core-js", "mcp", "skills", "packaging"})


if __name__ == "__main__":
    unittest.main()
