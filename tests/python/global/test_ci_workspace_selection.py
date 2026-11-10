"""Every test runs in CI, and a change runs what can break: test.yml against its selector.

scripts/github-workflows/select_checks.py maps each changed path to the tests that read it;
test.yml runs each job whole on the selector's one flag for it, and its last job, `CI`, is the
one required check (scripts/github-workflows/ci_gate.py). These tests hold the three together
and the table to the tree, and pin how each kind of change is routed.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import re
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.paths import REPO_ROOT
from tests.python.support.tmp_root import temporary_directory

WORKFLOWS = REPO_ROOT / ".github/workflows"
WORKFLOW = (WORKFLOWS / "test.yml").read_text(encoding="utf-8")
JOBS = dict(re.findall(r"^  ([a-z][\w-]*):\n(.*?)(?=^  [a-z][\w-]*:\n|\Z)", WORKFLOW.split("\njobs:\n", 1)[1], re.M | re.S))


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / f"scripts/github-workflows/{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault(name, module)
    spec.loader.exec_module(module)
    return module


selector = _load("select_checks")
gate = _load("ci_gate")

# Every job but the selection itself, the job that waits on nothing, and the gate runs on a flag.
GATED = set(JOBS) - {"changes", "static", "ci"}
TRACKED = subprocess.run(["git", "ls-files"], cwd=REPO_ROOT, capture_output=True, text=True, check=True).stdout.split()
PACKAGES, POLICY, SKILLS = selector.PACKAGES_SUITE, selector.POLICY_SUITE, selector.SKILL_SUITES
LIBRARY, SERVER, SHIM = f"{PACKAGES}/cad", f"{PACKAGES}/cad_server", f"{PACKAGES}/cad_mcp"
# The jobs a change to the packages reaches, whatever else it reaches.
SUITES = {"packages-linux", "packages-windows"}
CONSUMERS = SUITES | {"skills", "packaging", "viewer-e2e"}
REHEARSALS = {"install-linux", "install-windows"}
JS = {"js-core", "js-ui", "js-web", "js-mcp"}


def route(*paths: str) -> dict[str, str]:
    return selector.outputs(selector.select_paths(paths), paths)


def condition(job: str) -> str:
    """The one flag a job runs on: its whole `if:`."""
    return re.search(r"^    if: needs\.changes\.outputs\.(\w+) == 'true'$", JOBS[job], re.M)[1]


def jobs_for(*paths: str) -> set[str]:
    """The jobs test.yml runs for a change to `paths`, read from each job's own condition."""
    selected = route(*paths)
    return {job for job in GATED if selected[condition(job)] == "true"}


def tests_for(*paths: str) -> dict[str, list[str]]:
    selected = route(*paths)
    return {key: selected[key].split() for key in ("packages_tests", "skills_policy", "skills_tests")}


def steps(job: str) -> dict[str, str]:
    return dict(re.findall(r"      - name: ([^\n]+)\n(.*?)(?=\n      - name: |\Z)", JOBS[job], re.S))


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
            r"^apps/api/src/[^/]*\.test\.mjs$",                   # test-api.sh (node --test)
            r"^scripts/test/check-(dependencies|kit-boundaries|ui-strings)\.test\.mjs$",  # test-js.sh
            r"^tests/python/packages/cad(_server|_mcp)?/(.*/)?test_[^/]*\.py$",  # test-python.sh cadgen (and
                                                                                 # test-floor.sh on Python 3.13)
            r"^tests/python/packages/kicad/(.*/)?test_[^/]*\.py$",       # test-kicad.sh
            r"^tests/python/packages/fea/(.*/)?test_[^/]*\.py$",         # test-fea.sh
            r"^tests/python/packages/blender/(.*/)?test_[^/]*\.py$",     # test-blender.sh
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
        self.assertEqual(selected["packages_tests"], PACKAGES)
        self.assertEqual(selector.scope(selected), "full")
        # Light tests run in static, every other test in the skills job: together, all.
        policy = set(selector.light_policy()) | set(selected["skills_policy"].split())
        self.assertEqual(policy, {path.relative_to(REPO_ROOT).as_posix() for path in (REPO_ROOT / POLICY).glob("test_*.py")})
        suites = set(selector.LIGHT_SKILL_TESTS) | set(selected["skills_tests"].split())
        self.assertEqual(suites, {f"{SKILLS}/{path.name}" for path in (REPO_ROOT / SKILLS).iterdir() if path.is_dir()})

    def test_static_runs_on_every_change_waits_on_nothing_and_installs_nothing(self):
        static = JOBS["static"]
        # No flag and no selection to wait for: it runs when Changed paths fails, and on a push
        # whose tree was already tested.
        self.assertNotRegex(static, r"(?m)^    (if|needs):")
        self.assertNotIn("needs.changes", static)
        self.assertNotIn("setup-deps", static)
        ran = steps("static")
        # The version and tree checks, on every change; what merging releases, on a pull request.
        self.assertIn("scripts/release/check-version.sh", ran["Check release version"])
        self.assertIn("node scripts/release/sync-version.mjs --check", ran["Check release version"])
        self.assertIn("if: github.event_name == 'pull_request'", ran["Check what merging releases"])
        self.assertIn("scripts/release/check-pr-version.sh", ran["Check what merging releases"])
        self.assertIn("fetch-depth: 0", ran["Check out repository"])  # the target's history, the tags
        self.assertIn("check-builds.sh --tree-only", ran["Check the tracked tree"])
        # The light contracts, their lists read from the selector itself.
        light = ran["Run the light contracts"]
        self.assertIn("scripts/test/test-global.sh $(python3 scripts/github-workflows/select_checks.py --light policy)", light)
        self.assertIn("scripts/test/test-python.sh --select skills "
                      "$(python3 scripts/github-workflows/select_checks.py --light skills)", light)
        for name, expected in (("policy", selector.light_policy()), ("skills", list(selector.LIGHT_SKILL_TESTS))):
            with self.subTest(name=name), contextlib.redirect_stdout(io.StringIO()) as said:
                self.assertEqual(selector.main(["--light", name]), 0)
                self.assertEqual(said.getvalue().split(), expected)
        self.assertTrue(selector.light_policy())
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(selector.main(["--light"]), 2)
        # The API's tests install nothing, so they run here for every change: no job, no flag.
        self.assertIn("run: scripts/test/test-api.sh", ran["Run the API tests"])


class TheTableHoldsToTheTree(unittest.TestCase):
    def test_every_test_path_a_rule_names_exists(self):
        # A misspelt test path would select nothing, silently.
        for rule in selector.RULES:
            if isinstance(rule.selects, selector.Select):
                for path in rule.selects.packages | rule.selects.policy | rule.selects.skills:
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
                with self.subTest(pattern=pattern):
                    compiled = selector.compile_glob(pattern)
                    self.assertTrue(any(compiled.match(path) for path in present), "a rule for nothing")

    def test_every_tracked_path_is_known(self):
        # A path the table does not know runs everything; none should be unknown today.
        compiled = [[selector.compile_glob(pattern) for pattern in rule.patterns] for rule in selector.rules()]
        unknown = [path for path in TRACKED if not any(p.match(path) for patterns in compiled for p in patterns)]
        self.assertEqual(unknown, [])

    def test_light_tests_never_skip_for_a_missing_dependency(self):
        # static installs nothing; a test that skipped itself without a dependency
        # would pass there having tested nothing.
        light = [REPO_ROOT / path for path in selector.light_policy()]
        light += [file for path in selector.LIGHT_SKILL_TESTS for file in sorted((REPO_ROOT / path).rglob("test*.py"))]
        for file in light:
            with self.subTest(file=file.name):
                self.assertNotRegex(file.read_text(encoding="utf-8"), r"except (ImportError|ModuleNotFoundError)")


class TheWorkflowFollowsTheSelector(unittest.TestCase):
    def test_one_flag_one_job(self):
        # A job runs whole on its own flag or is skipped; a flag starts one job -- but the
        # packages' suites, which are a job a platform, and the two installer rehearsals.
        flags = set(route())
        started: dict[str, set[str]] = {}
        for job in GATED:
            with self.subTest(job=job):
                self.assertIn(condition(job), flags)
                started.setdefault(condition(job), set()).add(job)
        several = {flag: jobs for flag, jobs in started.items() if len(jobs) > 1}
        self.assertEqual(several, {"packages": SUITES, "installer": REHEARSALS})
        # ...and every flag the selector writes starts one: none is left that nothing reads.
        self.assertEqual(set(started), set(selector.FLAGS) | {"packages", "skills"})

    def test_no_step_runs_on_a_flag(self):
        # A green job ran all of itself. A step may wait on a list being there to run (a runner
        # given no paths would run its whole suite) and on its shard, never on a flag.
        lists = {"changed_tests", "skills_policy", "skills_tests"}
        for job, body in JOBS.items():
            for line in re.findall(r"^        if: (.+)$", body, re.M):
                with self.subTest(job=job, line=line):
                    self.assertNotIn("== 'true'", line)
                    read = set(re.findall(r"needs\.changes\.outputs\.(\w+)", line))
                    self.assertLessEqual(read, lists)
                    for name in read:
                        self.assertIn(f"needs.changes.outputs.{name} != ''", line)

    def test_every_output_the_jobs_read_is_one_the_selector_writes(self):
        written = set(route()) | {"record"}
        exposed = dict(re.findall(r"^      (\w+): \$\{\{ steps\.select\.outputs\.(\w+) \}\}$", JOBS["changes"], re.M))
        self.assertTrue(exposed)
        self.assertTrue(all(name == source and name in written for name, source in exposed.items()))
        self.assertLessEqual(set(re.findall(r"needs\.changes\.outputs\.(\w+)", WORKFLOW)), set(exposed))
        self.assertEqual(written - {"record", "full"}, set(exposed))

    def test_a_manual_called_or_nightly_run_selects_everything_and_records_it(self):
        self.assertIn("FULL: ${{ github.event_name == 'workflow_dispatch' || github.event_name == 'schedule' "
                      "|| inputs.full }}", JOBS["changes"])
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

    def _selected(self, event: str, tested: bool) -> tuple[dict[str, str], list[list[str]]]:
        asked: list[list[str]] = []

        def already(names: list[str]) -> bool:
            asked.append(names)
            return tested

        with temporary_directory(prefix="select-checks-") as temp:
            output = Path(temp) / "output"
            environment = {"FULL": "true", "GITHUB_EVENT_NAME": event, "GITHUB_OUTPUT": str(output), "RUNNER_TEMP": temp}
            with mock.patch.dict(os.environ, environment), mock.patch.object(selector, "_tested", already), \
                    contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(selector.main([]), 0)
            return dict(line.split("=", 1) for line in output.read_text(encoding="utf-8").splitlines()), asked

    def test_the_nightly_run_stands_down_for_a_tree_already_tested_in_full(self):
        # Nightly, on main, off the hour (when every schedule on GitHub fires at once).
        cron = re.search(r'^  schedule:\n    - cron: "(\d+) (\d+) \* \* \*"$', WORKFLOW, re.M)
        self.assertTrue(cron and cron[1] not in ("0", "00", "30"), "a nightly schedule, off the hour")
        # A release's run tested main's tree whole, normally: nothing runs again, and no record is made.
        values, asked = self._selected("schedule", tested=True)
        self.assertEqual(len(asked), 1)
        self.assertRegex(asked[0][0], r"^tested-[0-9a-f]{40}-full$")
        self.assertEqual(values["record"], "")
        self.assertEqual({job for job in GATED if values[condition(job)] == "true"}, set())
        # No such run: everything, recorded as a full run.
        values, _asked = self._selected("schedule", tested=False)
        self.assertTrue(values["record"].endswith("-full"))
        self.assertEqual({job for job in GATED if values[condition(job)] == "true"}, GATED)
        # A manual run never stands down.
        values, asked = self._selected("workflow_dispatch", tested=True)
        self.assertEqual(asked, [])
        self.assertTrue(values["record"].endswith("-full"))

    def test_nothing_selected_skips_every_gated_job(self):
        # A push whose tree was already tested: every flag is off, and the lists are empty.
        nothing = selector.outputs(selector.NOTHING)
        self.assertEqual({job for job in GATED if nothing[condition(job)] == "true"}, set())
        self.assertEqual((nothing["packages_tests"], nothing["skills_policy"], nothing["skills_tests"],
                          nothing["changed_tests"]), ("", "", "", ""))
        # The matrices still parse: a skipped job's is never expanded, and a job's that runs is.
        self.assertEqual(json.loads(nothing["linux_shards"]), ["1/1"])


class TheOneRequiredCheck(unittest.TestCase):
    """main's branch protection requires `CI` alone (CONTRIBUTING.md, Repository settings)."""

    def test_the_gate_needs_every_job_and_runs_whatever_became_of_them(self):
        ci = JOBS["ci"]
        self.assertRegex(ci, r"(?m)^    name: CI$")
        self.assertEqual([body for body in JOBS.values() if re.search(r"(?m)^    name: CI$", body)], [ci])
        needed = set(re.findall(r"^      - ([a-z][\w-]*)$", ci.split("    needs:\n", 1)[1].split("    if:", 1)[0], re.M))
        self.assertEqual(needed, set(JOBS) - {"ci"})
        # always(): a job skipped for a failed dependency would satisfy the required check.
        self.assertRegex(ci, r"(?m)^    if: always\(\)$")
        self.assertIn("NEEDS: ${{ toJSON(needs) }}", ci)
        self.assertIn("run: python3 scripts/github-workflows/ci_gate.py", ci)
        self.assertIn("PULL_REQUEST: ${{ github.event.pull_request.number }}", ci)
        self.assertIn("HEAD_SHA: ${{ github.event.pull_request.head.sha }}", ci)
        self.assertEqual(route("scripts/github-workflows/ci_gate.py")["full"], "true")

    def test_no_job_asks_for_more_than_publish_release_grants_the_call(self):
        # A called workflow's job may ask for no permission its caller lacks: one that did would
        # stop Publish Release's call before a job ran.
        publish = (WORKFLOWS / "release-publish.yml").read_text(encoding="utf-8")
        call = publish.split("\n  test:\n", 1)[1].split("\n  publish:\n", 1)[0]
        granted = dict(re.findall(r"^      (\w[\w-]*): (\w+)$", call.split("    permissions:\n", 1)[1].split("    uses:", 1)[0], re.M))
        self.assertEqual(granted, {"contents": "read", "actions": "read"})
        for name in ("test.yml", "install-linux.yml", "install-windows.yml"):
            text = (WORKFLOWS / name).read_text(encoding="utf-8")
            for block in re.findall(r"^( *)permissions:\n((?:\1  .*\n)+)", text, re.M):
                for permission, level in re.findall(r"^\s+([\w-]+): (\w+)$", block[1], re.M):
                    with self.subTest(workflow=name, permission=permission):
                        self.assertEqual(granted.get(permission), level)

    def test_a_job_passes_by_succeeding_or_by_having_nothing_to_test(self):
        never = mock.Mock(side_effect=AssertionError("nothing was cancelled"))
        code, why = gate.verdict({"changes": "success", "static": "success", "fea": "skipped", "docs": "success"}, never)
        self.assertEqual(code, 0, why)
        # A push whose tree was already tested: everything but static skipped.
        code, why = gate.verdict({"changes": "success", "static": "success", **{job: "skipped" for job in GATED}}, never)
        self.assertEqual(code, 0, why)

    def test_a_selection_that_failed_fails_the_required_check(self):
        # Every gated job waits on Changed paths, and GitHub counts a job skipped for a failed
        # dependency as a passing check: the gate is where that stops.
        skipped = {job: "skipped" for job in GATED}
        for result in ("failure", "skipped", ""):
            with self.subTest(result=result):
                code, why = gate.verdict({"changes": result, "static": "success", **skipped}, lambda: True)
                self.assertEqual(code, 1)
                self.assertIn("nothing was selected", why)

    def test_a_failed_job_fails_it_superseded_or_not(self):
        for superseded in (True, False):
            code, why = gate.verdict({"changes": "success", "static": "success", "fea": "failure",
                                      "docs": "cancelled"}, lambda: superseded)
            self.assertEqual((code, why), (1, "Failed: fea."))

    def test_a_cancelled_job_fails_it_unless_a_newer_push_superseded_the_run(self):
        # A job that ran out its timeout reports `cancelled`, and so does every job of a run the
        # concurrency group cancelled for a newer push: only the second passes.
        results = {"changes": "success", "static": "success", "packages-windows": "cancelled", "fea": "skipped"}
        code, why = gate.verdict(results, lambda: False)
        self.assertEqual(code, 1)
        self.assertIn("packages-windows", why)
        self.assertEqual(gate.verdict(results, lambda: True)[0], 0)
        self.assertEqual(gate.verdict({"changes": "cancelled", "static": "cancelled"}, lambda: True)[0], 0)
        self.assertEqual(gate.verdict({"changes": "cancelled", "static": "cancelled"}, lambda: False)[0], 1)

    def test_only_a_pull_request_whose_head_moved_is_superseded(self):
        tested = "a" * 40
        pull_request = {"GITHUB_EVENT_NAME": "pull_request", "PULL_REQUEST": "7", "HEAD_SHA": tested,
                        "GITHUB_REPOSITORY": "someone/somewhere", "GITHUB_TOKEN": "t"}
        cases = [
            (pull_request, "b" * 40, True),                                   # a newer push
            (pull_request, tested, False),                                    # cancelled by hand, or timed out
            (pull_request, None, False),                                      # could not be read: not superseded
            ({**pull_request, "GITHUB_EVENT_NAME": "push"}, "b" * 40, False),  # a push's run is never cancelled for another
            ({**pull_request, "PULL_REQUEST": ""}, "b" * 40, False),
        ]
        for environment, head, expected in cases:
            with self.subTest(event=environment["GITHUB_EVENT_NAME"], head=head), \
                    mock.patch.dict(os.environ, environment), \
                    mock.patch.object(gate, "pull_request_head", return_value=head):
                self.assertIs(gate.superseded(), expected)

    def test_the_gate_reads_the_results_github_gives_it(self):
        needs = {"changes": {"result": "success", "outputs": {"packages": "true"}}, "static": {"result": "success"},
                 "packages-linux": {"result": "failure", "outputs": {}}}
        with temporary_directory(prefix="ci-gate-") as temp:
            summary = Path(temp) / "summary.md"
            environment = {"NEEDS": json.dumps(needs), "GITHUB_STEP_SUMMARY": str(summary), "GITHUB_EVENT_NAME": "push"}
            with mock.patch.dict(os.environ, environment), contextlib.redirect_stdout(io.StringIO()), \
                    contextlib.redirect_stderr(io.StringIO()) as said:
                self.assertEqual(gate.main(), 1)
            self.assertIn("Failed: packages-linux.", said.getvalue())
            self.assertIn("| `packages-linux` | failure |", summary.read_text(encoding="utf-8"))


class DownloadsAreBounded(unittest.TestCase):
    """A stalled mirror fails in minutes: an `apt-get update` once ran 39 minutes to its job's timeout."""

    def test_every_setup_step_has_a_timeout_of_its_own(self):
        for name in ("test.yml", "install-linux.yml", "install-windows.yml"):
            text = (WORKFLOWS / name).read_text(encoding="utf-8")
            setups = re.findall(r"      - name: ([^\n]+)\n((?:        .*\n)*?)        uses: (\./\.github/actions/setup-deps"
                                r"|actions/setup-python@\S+|actions/setup-node@\S+)\n", text)
            self.assertTrue(setups, name)
            for step, before, _action in setups:
                with self.subTest(workflow=name, step=step):
                    self.assertRegex(before, r"timeout-minutes: \d+\n")

    def test_system_packages_come_through_one_bounded_step(self):
        # No job runs apt itself: setup-deps installs what a job names, only when the image lacks
        # it, and gives up on a connection that says nothing.
        self.assertNotIn("apt-get", WORKFLOW)
        action = (REPO_ROOT / ".github/actions/setup-deps/action.yml").read_text(encoding="utf-8")
        step = action.split("- name: Install system packages\n", 1)[1].split("\n    - name: ", 1)[0]
        self.assertIn("if: inputs.apt != '' && runner.os == 'Linux'", step)
        for option in ("Acquire::Retries=3", "Acquire::http::Timeout=30", "Acquire::https::Timeout=30"):
            self.assertIn(option, step)
        self.assertIn("dpkg-query", step)
        # The display the engine's stills draw on, wherever a suite draws them.
        for job in ("packages-linux", "packages-floor", "fea"):
            with self.subTest(job=job):
                self.assertIn("apt: xvfb libgl1-mesa-dri fonts-dejavu-core", JOBS[job])
                self.assertIn("xvfb-run ", JOBS[job])

    def test_every_job_has_a_timeout(self):
        for job, body in JOBS.items():
            with self.subTest(job=job):
                if re.search(r"(?m)^    uses: ", body):
                    continue  # a called workflow: its own jobs', below
                self.assertRegex(body, r"(?m)^    timeout-minutes: \d+$")
        for name in ("install-linux.yml", "install-windows.yml"):
            text = (WORKFLOWS / name).read_text(encoding="utf-8")
            self.assertEqual(len(re.findall(r"(?m)^    runs-on: ", text)), len(re.findall(r"(?m)^    timeout-minutes: \d+$", text)), name)


class ThePackagesSuites(unittest.TestCase):
    def test_a_whole_run_is_split_over_shards_and_a_narrowed_one_is_not(self):
        whole = route("packages/cad/src/cad/engine/api.py")
        self.assertEqual(json.loads(whole["linux_shards"]), ["1/2", "2/2"])
        self.assertEqual(json.loads(whole["windows_shards"]), ["1/3", "2/3", "3/3"])
        narrowed = route(f"{SERVER}/test_settings.py")
        self.assertEqual((json.loads(narrowed["linux_shards"]), json.loads(narrowed["windows_shards"])), (["1/1"], ["1/1"]))
        for job, shards in (("packages-linux", "linux_shards"), ("packages-windows", "windows_shards")):
            with self.subTest(job=job):
                body = JOBS[job]
                self.assertIn(f"shard: ${{{{ fromJSON(needs.changes.outputs.{shards}) }}}}", body)
                # Every shard reports: one's failure does not cancel the rest.
                self.assertIn("fail-fast: false", body)
                suite = steps(job)["Run the packages' suites"]
                self.assertIn("CAD_TEST_SHARD: ${{ matrix.shard }}", suite)
                self.assertIn("TESTS: ${{ needs.changes.outputs.packages_tests }}", suite)
                self.assertRegex(suite, r"scripts/test/test-python\.sh (--keep-going )?--select cadgen --print-weights \$TESTS")
                # The types once a platform (the checker reads the win32 branches on Windows alone).
                self.assertIn("if: startsWith(matrix.shard, '1/')", steps(job)["Check the packages' types (basic)"])

    def test_the_tests_a_change_touches_run_first(self):
        # A break in a pull request's own test reports in a minute or two, not at the suite's end.
        engine, settings, protocol = "packages/cad/src/cad/engine/api.py", f"{SERVER}/test_settings.py", f"{SHIM}/test_protocol.py"
        self.assertEqual(route(engine, settings, protocol)["changed_tests"], f"{SHIM}/test_protocol.py {SERVER}/test_settings.py")
        # ...but not when they are all the suite step runs anyway, nor a file that is gone, nor one
        # of a suite another job owns.
        self.assertEqual(route(settings)["changed_tests"], "")
        self.assertEqual(route(engine, f"{SERVER}/test_gone_for_good.py")["changed_tests"], "")
        self.assertEqual(route(engine, "tests/python/packages/fea/test_fea.py")["changed_tests"], "")
        self.assertEqual(route(engine)["changed_tests"], "")
        # A release that edits a test runs it first too; a run with no diff has none to name.
        self.assertEqual(route("VERSION", settings)["changed_tests"], settings)
        self.assertEqual(selector.outputs(selector.EVERYTHING)["changed_tests"], "")
        # What runs first is no part of what was tested: the record's scope is the same.
        self.assertEqual(selector.scope(route(engine, settings)), selector.scope(route(engine)))
        for job in SUITES:
            with self.subTest(job=job):
                names = list(steps(job))
                first = steps(job)["Run the tests this change touches first"]
                self.assertLess(names.index("Run the tests this change touches first"), names.index("Run the packages' suites"))
                self.assertIn("if: startsWith(matrix.shard, '1/') && needs.changes.outputs.changed_tests != ''", first)
                self.assertIn("TESTS: ${{ needs.changes.outputs.changed_tests }}", first)
                self.assertNotIn("CAD_TEST_SHARD", first)  # all of them, in the one shard that runs them


class ChangesRunWhatCanBreak(unittest.TestCase):
    def test_what_runs_everything(self):
        for path in ("VERSION", "package-lock.json", "requirements-dev.txt", ".github/workflows/test.yml",
                     ".github/actions/setup-deps/action.yml", "scripts/github-workflows/select_checks.py",
                     "scripts/github-workflows/ci_gate.py",
                     "scripts/test/common.sh", "tests/python/support/paths.py", "packages/core/src/common/camera.js",
                     "somewhere/new.thing"):
            with self.subTest(path=path):
                self.assertEqual(jobs_for(path), GATED)
                self.assertEqual(route(path)["full"], "true")

    def test_prose_and_metadata_run_only_the_contracts_that_read_them(self):
        # static's light contracts, which every change runs: no job is selected.
        for path in ("README.md", "CONTRIBUTING.md", "AGENTS.md", "LICENSE", ".claude-plugin/plugin.json",
                     "claude.mcp.json", "skills.sh.json", "skills/robot-simulation/SKILL.md", "skills/robot-simulation/references/urdf-frames.md",
                     "skills/cad/SKILL.md", "skills/cad/references/snapshot-review.md", "skills/sendcutsend/SKILL.md",
                     "skills/print3d/agents/openai.yaml", "packages/core/README.md", "packages/ui/docs/render-mode.md",
                     "docs/migrations/migrating-0.4-to-0.5.md", "models/examples/src/part.py",
                     ".github/workflows/release-publish.yml", ".github/workflows/release-prepare.yml",
                     "scripts/release/bump-version.sh", "scripts/release/plugin_branch.py"):
            with self.subTest(path=path):
                self.assertEqual(jobs_for(path), set())

    def test_a_skill_script_runs_its_suite(self):
        # Every skill suite but fea's is light, so it already runs on every change.
        self.assertEqual(jobs_for("skills/print3d/scripts/orca_presets.py"), set())
        self.assertEqual(tests_for("skills/print3d/scripts/orca_presets.py")["skills_tests"], [])

    def test_the_manufacturing_check_runs_the_package_suites(self):
        # Its measurements are the library's trimesh integration: no skill suite reads them.
        chosen = tests_for("packages/cad/src/cad/trimesh/_molding.py")
        self.assertEqual(chosen["packages_tests"], [PACKAGES])
        self.assertEqual(chosen["skills_tests"], [])

    def test_a_test_file_runs_itself(self):
        self.assertEqual(tests_for(f"{SERVER}/test_settings.py")["packages_tests"], [f"{SERVER}/test_settings.py"])
        self.assertEqual(jobs_for(f"{SERVER}/test_settings.py"), SUITES)
        self.assertEqual(tests_for(f"{SHIM}/test_protocol.py")["packages_tests"], [f"{SHIM}/test_protocol.py"])
        self.assertEqual(tests_for(f"{POLICY}/test_cli_stream_contract.py")["skills_policy"],
                         [f"{POLICY}/test_cli_stream_contract.py"])
        self.assertEqual(jobs_for(f"{POLICY}/test_cli_stream_contract.py"), {"skills"})
        # A light policy test is static's, which every change runs.
        self.assertEqual(jobs_for(f"{POLICY}/test_ci_workspace_selection.py"), set())
        self.assertEqual(tests_for(f"{LIBRARY}/test_trimesh_molding.py")["packages_tests"],
                         [f"{LIBRARY}/test_trimesh_molding.py"])
        self.assertEqual(tests_for(f"{LIBRARY}/engine/formats_golden/stl.png")["packages_tests"], [PACKAGES])

    def test_the_packages_run_their_suites_their_hosts_and_the_wheel(self):
        # The engine is no leaf: every build, export, snapshot and served document is its. Beside
        # that, each path reaches the job of what it is part of.
        cases = {
            "packages/cad/src/cad/engine/api.py": set(),
            "packages/cad/src/cad/engine/serve.py": set(),
            "packages/aliases/cadgen/pyproject.toml": set(),
            "packages/cad/src/cad/registry.py": {"blender"},                        # bpy's line and platforms
            "packages/cad-server/src/cad_server/engine/daemon.py": {"blender"},     # starts bpy's worker
            "packages/cad-server/src/cad_server/cli/setup.py": REHEARSALS,          # what the installer runs
        }
        for path, beside in cases.items():
            with self.subTest(path=path):
                self.assertEqual(jobs_for(path), CONSUMERS | beside)
                chosen = tests_for(path)
                self.assertEqual(chosen["packages_tests"], [PACKAGES])
                self.assertEqual(chosen["skills_tests"], [])
                self.assertEqual(set(chosen["skills_policy"]), {f"{POLICY}/{name}" for name in selector.HEAVY_POLICY})

    def test_the_stress_study_runs_its_own_job_with_its_integrations_installed(self):
        self.assertIn("import cad_ccx", JOBS["fea"])  # the calculix extra's cad-ccx, from PyPI
        self.assertNotIn("git+", JOBS["fea"])
        # The netgen integration's extra, beside the development install's, with the mesher pinned to the version
        # the accuracy tests' margins were measured with; the extra keeps the floor.
        self.assertIn('"./packages/cad[build123d,trimesh,netgen,calculix]"', JOBS["fea"])
        self.assertIn('"netgen-mesher==6.2.2608"', JOBS["fea"])
        self.assertIn("scripts/test/test-fea.sh", JOBS["fea"])
        self.assertRegex(JOBS["fea"], r"(?m)^    timeout-minutes: 15$")
        # The suite and its runner are that job's alone: no package job collects them.
        suite = REPO_ROOT / "tests/python/packages/fea"
        self.assertLessEqual({"test_fea.py", "test_fea_assembly.py", "test_fea_checks.py"},
                             {path.name for path in suite.glob("test_*.py")})
        for path in ("tests/python/packages/fea/test_fea.py", "scripts/test/test-fea.sh"):
            with self.subTest(path=path):
                self.assertEqual(jobs_for(path), {"fea"})
        # The engine and shared modules a study reads and writes through run its solves too; the rest of the engine doesn't.
        for path in ("packages/cad/src/cad/engine/refs.py", "packages/cad/src/cad/engine/executables.py",
                     "packages/cad/src/cad/engine/export/glb.py", "packages/cad/src/cad/_internal/atomic_replace.py",
                     "packages/cad/src/cad/_internal/programs.py", "packages/cad/src/cad/_internal/operation.py",
                     "packages/cad-server/src/cad_server/_internal/cli_from_function.py"):
            with self.subTest(path=path):
                self.assertIn("fea", jobs_for(path))
        self.assertNotIn("fea", jobs_for("packages/cad/src/cad/engine/api.py"))
        # Its own code reaches the fea job beside what its package reaches.
        for path in (
            "packages/cad/src/cad/_internal/fea/solve.py",
            "packages/cad/src/cad/_internal/fea/operation.py",
            "packages/cad/src/cad/calculix/_program.py",
            "packages/cad/src/cad/netgen/_mesher.py",
            "packages/cad-server/src/cad_server/cli/document_types.py",
            "packages/cad-server/src/cad_server/_internal/integration_env.py",
            "packages/cad/src/cad/results.py",
        ):
            with self.subTest(path=path):
                self.assertLessEqual({"fea", "packages-linux"}, jobs_for(path))
        # The skill's pages are its own suite's, which reads them against the code they document; no solve reads them.
        self.assertEqual(jobs_for("skills/fea/SKILL.md"), {"skills"})
        self.assertEqual(tests_for("skills/fea/references/study-file.md")["skills_tests"], [f"{SKILLS}/fea"])
        self.assertEqual(tests_for("packages/cad/src/cad/_internal/fea/study.py")["skills_tests"], [f"{SKILLS}/fea"])
        self.assertNotIn("fea", jobs_for("packages/cad/src/cad/build123d/_geometry.py"))

    def test_blenders_job_runs_bpy_in_the_environment_cad_run_makes(self):
        job = JOBS["blender"]
        self.assertEqual(condition("blender"), "bpy")
        self.assertRegex(job, r"(?m)^    timeout-minutes: 15$")
        self.assertIn("run: scripts/test/test-blender.sh", steps("blender")["Run the blender suite"])
        self.assertNotIn("test-floor.sh", job)  # the floor's suites are a job of their own
        self.assertEqual(route("VERSION")["bpy"], "true")
        self.assertEqual(route()["bpy"], "false")
        # bpy's Linux wheel loads X11's client libraries and OpenGL from the system; the engine's stills draw on Xvfb.
        for package in ("libx11-6", "libxkbcommon0", "libgl1", "libegl1", "libgl1-mesa-dri", "xvfb", "fonts-dejavu-core"):
            self.assertIn(package, job)
        # On CI nothing of the bpy suite may skip: the runner fails a run in which a test did.
        runner = (REPO_ROOT / "scripts/test/test-blender.sh").read_text(encoding="utf-8")
        self.assertRegex(runner, r'if \[ "\$\{CI:-\}" = "true" \]; then\n  export PYTHON_TEST_NO_SKIPS=1\nfi')
        # The bpy suite and its runner are that job's alone: no package job collects them.
        for path in ("tests/python/packages/blender/test_load.py",
                     "tests/python/packages/blender/test_open_in_blender.py", "scripts/test/test-blender.sh"):
            with self.subTest(path=path):
                self.assertEqual(jobs_for(path), {"blender"})
        # cad.blender and the reader it reads a GLB through, bpy's environment and how cad run chooses it, the GLB,
        # how it is exported and meshed finer, and its clips reach the bpy suite beside their package's jobs.
        for path in ("packages/cad/src/cad/blender/_scene.py", "packages/cad/src/cad/engine/formats/gltf.py",
                     "packages/cad/src/cad/registry.py", "packages/cad/src/cad/_internal/integrations.py",
                     "packages/cad/pyproject.toml",
                     "packages/cad-server/src/cad_server/_internal/extras.py",
                     "packages/cad-server/src/cad_server/_internal/base.py",
                     "packages/cad-server/src/cad_server/_internal/scan.py",
                     "packages/cad-server/src/cad_server/cli/run.py",
                     "packages/cad-server/src/cad_server/engine/cli.py",
                     # A daemon on the server's Python starting a worker on bpy's: the bpy suite is its one test.
                     "packages/cad-server/src/cad_server/engine/daemon.py",
                     "packages/cad-server/src/cad_server/engine/supervisor.py",
                     "packages/cad-server/src/cad_server/_internal/open_in_blender.py",
                     "packages/cad/src/cad/engine/export/__init__.py", "packages/cad/src/cad/engine/export/mesh.py",
                     "packages/cad/src/cad/engine/export/glb.py", "packages/cad/src/cad/engine/export/motion.py",
                     "packages/cad/src/cad/engine/export/animation.py"):
            with self.subTest(path=path):
                self.assertLessEqual({"blender", "packages-linux"}, jobs_for(path))
        # ...and the rest does not: the rest of the packages and their suites -- the opener that finds a person's
        # Blender, the server's other commands among them -- and what holds no code: a package's README, the
        # render skill's pages.
        for path in ("packages/cad/src/cad/engine/api.py", "packages/cad/src/cad/engine/export/stl.py",
                     "packages/cad-mcp/src/cad_mcp/shim.py", "tests/python/packages/cad/test_registry.py",
                     "tests/python/packages/cad_mcp/test_protocol.py",
                     "packages/cad-server/src/cad_server/_internal/apps.py",
                     "packages/cad-server/src/cad_server/_internal/integration_env.py",
                     "packages/cad-server/src/cad_server/cli/doctor.py", "packages/cad-server/pyproject.toml",
                     "tests/python/packages/cad_server/test_extras.py",
                     "packages/cad/README.md", "packages/cad-server/README.md",
                     "packages/cad-server/src/cad_server/engine/README.md",
                     "skills/render/SKILL.md", "skills/render/references/shots.md",
                     "skills/render/references/scene-script.md", "skills/cad/SKILL.md"):
            with self.subTest(path=path):
                self.assertNotIn("blender", jobs_for(path))
        self.assertEqual(jobs_for("skills/render/SKILL.md"), set())

    def test_the_floor_s_suites_run_on_python_3_13_before_a_release_not_on_every_push(self):
        ran = steps("packages-floor")
        self.assertEqual(condition("packages-floor"), "floor")
        self.assertRegex(JOBS["packages-floor"], r"(?m)^    timeout-minutes: 30$")
        made = ran["Make an environment on Python 3.13, the packages' floor"]
        floor = ran["Run the library's, the server's and the shim's suites on the floor"]
        import tomllib

        declared = tomllib.loads((REPO_ROOT / "packages/cad/pyproject.toml").read_text(encoding="utf-8"))
        python = declared["project"]["requires-python"].removeprefix(">=")
        self.assertIn(f'uv venv --python {python} "$RUNNER_TEMP/floor"', made, "the Python the packages declare")
        self.assertIn("-r requirements-dev.txt", made)
        self.assertIn("PYTHON_BIN: ${{ runner.temp }}/floor/bin/python", floor)
        self.assertRegex(floor, r"run: xvfb-run [^\n]+ scripts/test/test-floor\.sh")
        # The three distributions declare the one floor, so the three suites run on it.
        runner = (REPO_ROOT / "scripts/test/test-floor.sh").read_text(encoding="utf-8")
        for suite in ("cad", "cad_server", "cad_mcp"):
            self.assertRegex(runner, rf'\nrun_python_unittest "[^"]+" "tests/python/packages/{suite}" ', suite)
        # The release tier: a third run of suites the packages jobs run on the installations' Python, for a
        # rare kind of break. A full run -- a VERSION change, so before a release ships; the nightly; a manual
        # run; Publish Release's call -- and a change to its own runner.
        self.assertEqual(route("VERSION")["floor"], "true")
        self.assertEqual(selector.outputs(selector.EVERYTHING)["floor"], "true")
        self.assertEqual(jobs_for("scripts/test/test-floor.sh"), {"packages-floor"})
        for path in ("packages/cad/src/cad/engine/api.py", "packages/cad-server/src/cad_server/cli/doctor.py",
                     "packages/cad-mcp/src/cad_mcp/shim.py", "packages/cad/pyproject.toml",
                     "tests/python/packages/cad/test_registry.py", "tests/python/packages/cad_mcp/test_protocol.py",
                     "scripts/test/test-python.sh", "packages/cad/README.md", "skills/cad/SKILL.md"):
            with self.subTest(path=path):
                self.assertEqual(route(path)["floor"], "false")

    def test_the_viewer_and_the_mcp_server_reach_only_what_reaches_them(self):
        viewer = tests_for("packages/cad-server/src/cad_server/viewer/scanner.py")
        self.assertIn(f"{SERVER}/viewer/test_launcher.py", viewer["packages_tests"])
        self.assertIn(f"{SERVER}/mcp/test_server.py", viewer["packages_tests"])
        self.assertNotIn(f"{LIBRARY}/test_flatten.py", viewer["packages_tests"])
        self.assertNotIn(f"{LIBRARY}/engine/test_memo.py", viewer["packages_tests"])
        self.assertIn(f"{SERVER}/test_cli_from_function.py", viewer["packages_tests"])  # imports every command
        self.assertIn(f"{LIBRARY}/test_atomic_replace.py", viewer["packages_tests"])  # reads every source
        self.assertEqual(viewer["skills_tests"], [])
        # ...and the wheel that ships it, and the bundled viewer served through it.
        self.assertEqual(jobs_for("packages/cad-server/src/cad_server/viewer/scanner.py"),
                         SUITES | {"packaging", "viewer-e2e"})
        mcp = tests_for("packages/cad-server/src/cad_server/mcp/server.py")
        self.assertIn(f"{SERVER}/mcp/test_server.py", mcp["packages_tests"])
        self.assertNotIn(f"{SERVER}/viewer/test_launcher.py", mcp["packages_tests"])
        self.assertEqual(jobs_for("packages/cad-server/src/cad_server/mcp/server.py"), SUITES | {"packaging"})
        # The state directory's one definition is shared with the rest of the server.
        self.assertEqual(tests_for("packages/cad-server/src/cad_server/viewer/recents.py")["packages_tests"], [PACKAGES])
        # The shim is a leaf too: its own suite and the tests that name it, and the wheels.
        shim = tests_for("packages/cad-mcp/src/cad_mcp/shim.py")
        self.assertIn(f"{SHIM}/test_shim_engine.py", shim["packages_tests"])
        self.assertIn(f"{SERVER}/test_core_imports.py", shim["packages_tests"])
        self.assertNotIn(f"{SERVER}/viewer/test_launcher.py", shim["packages_tests"])
        self.assertNotIn(f"{LIBRARY}/engine/test_memo.py", shim["packages_tests"])
        self.assertEqual(jobs_for("packages/cad-mcp/src/cad_mcp/shim.py"), SUITES | {"packaging"})

    def test_kicad_code_reaches_the_kicad_job_beside_its_package_and_its_suite_that_job_alone(self):
        # KiCad's code runs what its package runs, and the KiCad job, which installs KiCad.
        library = "packages/cad/src/cad/engine/formats/kicad/plot.py"
        self.assertEqual(jobs_for(library), CONSUMERS | {"kicad"})
        self.assertEqual(tests_for(library)["packages_tests"], [PACKAGES])
        self.assertIn("kicad", jobs_for("packages/cad/src/cad/kicad/_check.py"))
        # The KiCad suite and its runner are that job's alone: no package job collects them.
        for path in ("tests/python/packages/kicad/test_native_files.py", "scripts/test/test-kicad.sh"):
            with self.subTest(path=path):
                self.assertEqual(jobs_for(path), {"kicad"})
        # ...and nothing else reaches it: an engine change runs the package suites, not KiCad.
        self.assertNotIn("kicad", jobs_for("packages/cad/src/cad/engine/api.py"))

    def test_the_router_and_what_it_reads_a_board_through_run_its_unit_files_on_all_three_oses(self):
        # The router's copper is held to a digest (test_kicad_routing_determinism.py): Linux and Windows run it in
        # the packages jobs, macOS in the routing job, the library alone installed.
        determinism = f"{LIBRARY}/test_kicad_routing_determinism.py"
        for path in ("packages/cad/src/cad/kicad/_routing/shapes.py", "packages/cad/src/cad/kicad/_route.py",
                     "packages/cad/src/cad/engine/formats/kicad/geometry.py",
                     "packages/cad/src/cad/engine/formats/kicad/board_index.py",
                     "packages/cad/src/cad/engine/formats/kicad/sexpr.py", "packages/cad/pyproject.toml", determinism):
            with self.subTest(path=path):
                self.assertLessEqual(SUITES | {"routing-macos"}, jobs_for(path))
                self.assertTrue(set(tests_for(path)["packages_tests"]) & {PACKAGES, determinism})
        for path in (f"{LIBRARY}/test_kicad_routing.py", "scripts/test/test-routing.sh"):
            with self.subTest(path=path):
                self.assertIn("routing-macos", jobs_for(path))
        self.assertNotIn("routing-macos", jobs_for("packages/cad/src/cad/engine/formats/kicad/plot.py"))
        self.assertNotIn("routing-macos", jobs_for("packages/cad/src/cad/engine/api.py"))
        job = JOBS["routing-macos"]
        self.assertIn("runs-on: macos-latest", job)
        self.assertIn("python -m pip install --editable ./packages/cad\n", job)
        self.assertIn("run: scripts/test/test-routing.sh", job)
        self.assertNotIn("setup-deps", job)

    def test_the_library_s_project_reaches_the_job_of_every_integration_it_pins(self):
        # A change that only moves a pin moves the integration itself, and the job that installs it runs on it:
        # kicode's, netgen's and ccx's, bpy's, numpy's. Not the release tier's.
        self.assertEqual(jobs_for("packages/cad/pyproject.toml"), CONSUMERS | {"kicad", "fea", "blender", "routing-macos"})
        self.assertNotIn("kicad", jobs_for("packages/cad-server/pyproject.toml"))

    def test_the_installer_rehearsals_are_called_here_on_one_flag_and_start_no_other_way(self):
        for job, name in (("install-linux", "install-linux.yml"), ("install-windows", "install-windows.yml")):
            with self.subTest(workflow=name):
                # Called on the selector's flag, on the commit this run tests.
                self.assertEqual(condition(job), "installer")
                self.assertIn(f"    uses: ./.github/workflows/{name}\n", JOBS[job])
                self.assertIn("      ref: ${{ inputs.ref }}\n", JOBS[job])
                # No push starts one: the paths that select them are the selector's, one definition.
                text = (WORKFLOWS / name).read_text(encoding="utf-8")
                triggers = text.split("\non:\n", 1)[1].split("\npermissions:", 1)[0]
                self.assertEqual(re.findall(r"^  (\w+):$", triggers, re.M), ["workflow_dispatch", "workflow_call"])
                self.assertNotIn("paths:", triggers)
                # One run holds both: a name each for the wheels they pass between their jobs.
                wheels = set(re.findall(r"^          name: (\S*wheels)$", text, re.M))
                self.assertEqual(wheels, {f"{job}-wheels"})
        # The workflows, the installers, and what they run: each reaches both, beside what else it reaches.
        self.assertEqual(jobs_for(".github/workflows/install-linux.yml"), REHEARSALS)
        self.assertEqual(jobs_for(".github/workflows/install-windows.yml"), REHEARSALS)
        self.assertEqual(jobs_for("scripts/install/install.ps1"), REHEARSALS | SUITES | {"docs"})
        self.assertEqual(tests_for("scripts/install/install.sh")["packages_tests"], [f"{SERVER}/test_setup.py"])
        for path in selector.INSTALLER_CODE:
            with self.subTest(path=path):
                self.assertTrue((REPO_ROOT / path).is_file())
                self.assertLessEqual(REHEARSALS, jobs_for(path))
        for module in ("setup", "uninstall", "doctor"):
            self.assertIn(f"packages/cad-server/src/cad_server/cli/{module}.py", selector.INSTALLER_CODE)
        # ...and a release rehearses them before it ships. Nothing else does.
        self.assertLessEqual(REHEARSALS, jobs_for("VERSION"))
        for path in ("packages/cad-server/src/cad_server/cli/run.py", "packages/cad/src/cad/engine/api.py",
                     "scripts/install/dev_install.py", "docs/install.md"):
            with self.subTest(path=path):
                self.assertFalse(REHEARSALS & jobs_for(path))

    def test_the_installer_rehearsals_take_the_same_inputs_and_rehearse_this_tree_unless_asked(self):
        inputs = []
        for name in ("install-windows.yml", "install-linux.yml"):
            text = (WORKFLOWS / name).read_text(encoding="utf-8")
            # Dispatched by hand or called by test.yml: the same two inputs either way.
            for trigger, after in (("workflow_dispatch", "\n  workflow_call:"), ("workflow_call", "\npermissions:")):
                block = text.split(f"  {trigger}:\n    inputs:\n", 1)[1].split(after, 1)[0]
                inputs.append(re.findall(r"^      (\w+):$", block, re.M))
                self.assertRegex(block, r"published:\n(?:        .*\n)*?        default: false", name)
            self.assertIn("if: ${{ !inputs.published }}", text, name)
        self.assertEqual(inputs, [["ref", "published"]] * 4)

    def test_ui_reaches_both_hosts_and_the_wheel_not_the_engine(self):
        hosts = {"js-ui", "js-web", "js-mcp", "packaging", "viewer-e2e"}
        self.assertEqual(jobs_for("packages/ui/src/index.ts"), hosts)
        self.assertEqual(jobs_for("packages/ui/src/renderers/dxf/DxfRenderer.js"), hosts)
        # ...but the robot payload suite holds the robot renderer's browser fixtures (the server's payloads) current.
        self.assertEqual(tests_for("packages/ui/src/renderers/robot/__fixtures__/arm.urdf")["packages_tests"],
                         [f"{SERVER}/test_robot_payload.py"])

    def test_the_ui_s_browser_specs_are_split_over_two_jobs(self):
        # Each spec drives a Chromium doing WebGL in software: one at a time in a job, two jobs.
        job = JOBS["js-ui"]
        self.assertEqual(re.findall(r"- shard: (\S+)\n\s+select: (\S+)", job), [("1/2", "ui"), ("2/2", "ui-browser")])
        ran = steps("js-ui")["Run shared UI tests"]
        self.assertIn('UI_BROWSER_TEST_CONCURRENCY: "1"', ran)
        self.assertIn("UI_BROWSER_TEST_SHARD: ${{ matrix.shard }}", ran)
        self.assertIn("run: scripts/test/test-js.sh --select ${{ matrix.select }}", ran)
        # The runner's two groups for them: `ui` runs its shard's specs beside everything else, `ui-browser`
        # its shard's alone.
        runner = (REPO_ROOT / "scripts/test/test-js.sh").read_text(encoding="utf-8")
        self.assertIn("core|ui|ui-browser|web|mcp|all) ;;", runner)
        self.assertIn("UI_BROWSER_TEST_SHARD", (REPO_ROOT / "packages/ui/scripts/run-tests.mjs").read_text(encoding="utf-8"))

    def test_each_app_runs_its_own_job(self):
        self.assertEqual(jobs_for("apps/web/src/main.tsx"), {"js-web", "packaging", "viewer-e2e"})
        self.assertEqual(jobs_for("apps/mcp/src/App.tsx"), {"js-mcp", "packaging"})
        self.assertEqual(jobs_for("apps/docs/src/app/page.tsx"), {"docs", "js-core"})
        self.assertEqual(jobs_for("apps/docs/public/brand/logo.svg"), {"docs"})
        # The API's tests are static's, on every change.
        self.assertEqual(jobs_for("apps/api/src/versions.mjs"), set())
        self.assertEqual(jobs_for("apps/api/vercel.json"), set())
        # apps/web's tests resolve the links in its Markdown, so what they link to is web input.
        self.assertEqual(jobs_for("apps/web/README.md"), {"js-web"})
        for target in selector.web_link_targets():
            with self.subTest(target=target):
                self.assertEqual(route(target)["web_client"], "true")

    def test_the_docs_job_reads_no_model(self):
        # The docs site ships its committed hero GLB and nothing in its build or check reads
        # models/: the planetary model and the engine code that exports it select no docs job.
        # The committed GLB selects the docs job.
        for path in ("models/assemblies/src/planetary_gear_assembly/planetary_gear_assembly.py",
                     "packages/cad/src/cad/build123d/__init__.py",
                     "packages/cad/src/cad/engine/animations.py"):
            with self.subTest(path=path):
                self.assertEqual(route(path)["docs"], "false")
        for path in ("apps/docs/public/hero/planetary.glb",):
            with self.subTest(path=path):
                self.assertEqual(route(path)["docs"], "true")

    def test_scripts_run_what_runs_them(self):
        cases = {
            "scripts/test/test-viewer-launch.sh": {"viewer-e2e"},
            "scripts/test/test-viewer-browser.sh": {"viewer-e2e"},
            "tests/browser/viewer-e2e.mjs": {"viewer-e2e"},
            "scripts/test/test-installed.sh": {"packaging"},
            "scripts/test/test-docs.sh": {"docs"},
            "scripts/test/test-api.sh": set(),  # static's, on every change
            "scripts/test/test-js.sh": JS,
            "scripts/test/check-dependencies.mjs": JS,
            "scripts/test/test-global.sh": {"skills"},
            "scripts/test/test-python.sh": SUITES | {"skills"},
            "scripts/test/test-floor.sh": {"packages-floor"},
            "scripts/release/sync-version.mjs": {"packaging"},
            "scripts/github-workflows/check-builds.sh": {"packaging"},
            "scripts/bundle/bundle.sh": CONSUMERS,
            "scripts/brand/export-logos.mjs": {"docs"},
            "scripts/bench/occt_parity.py": set(),
            "scripts/bench/corpus.json": set(),
        }
        for path, expected in cases.items():
            with self.subTest(path=path):
                self.assertEqual(jobs_for(path), expected)
        self.assertEqual(tests_for("scripts/test/test-global.sh")["skills_policy"],
                         [f"{POLICY}/{name}" for name in sorted(selector.HEAVY_POLICY)])
        # The jobs that drive the bundled viewer build the bundle; the one that ships it does not drive it.
        self.assertIn("scripts/test/test-viewer-launch.sh", JOBS["viewer-e2e"])
        self.assertIn("scripts/test/test-viewer-browser.sh", JOBS["viewer-e2e"])
        self.assertIn("scripts/bundle/bundle.sh --clean", JOBS["viewer-e2e"])
        self.assertNotIn("test-viewer", JOBS["packaging"])

    def test_the_ui_strings_guard_runs_for_each_tree_it_reads(self):
        # test-js.sh runs the guard in its ui, web and mcp groups (never core, whose job installs
        # packages/core alone and has no Babel): each tree it reads reaches one of those jobs, and
        # so do its own files.
        groups = {"ui": "web_ui", "web": "web_client", "mcp": "mcp"}
        for path in ("packages/ui/src/i18n/locales/ja.js", "apps/web/src/App.tsx", "apps/mcp/src/Notice.tsx",
                     "scripts/test/check-ui-strings.mjs", "scripts/test/check-ui-strings.test.mjs"):
            with self.subTest(path=path):
                selected = route(path)
                self.assertTrue(any(selected[flag] == "true" for flag in groups.values()), path)
        self.assertEqual(route("apps/mcp/src/Notice.tsx")["mcp"], "true")
        self.assertEqual(route("apps/web/src/App.tsx")["web_client"], "true")
        lines = (REPO_ROOT / "scripts/test/test-js.sh").read_text(encoding="utf-8").splitlines()
        first = next(index for index, line in enumerate(lines) if "check-ui-strings" in line)
        self.assertEqual(lines[first - 1].strip(), 'if [ "$SELECT" != core ]; then')

    def test_a_deleted_test_file_has_nothing_left_to_run(self):
        self.assertEqual(jobs_for(f"{PACKAGES}/test_gone_for_good.py"), set())

    def test_mixed_changes_take_the_union(self):
        self.assertEqual(jobs_for("apps/docs/src/app/page.tsx", "apps/mcp/src/App.tsx"),
                         {"docs", "js-core", "js-mcp", "packaging"})


if __name__ == "__main__":
    unittest.main()
