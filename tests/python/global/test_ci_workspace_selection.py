"""Every test runs in CI, and a change runs what can break: test.yml against its selector.

scripts/github-workflows/select_checks.py maps each changed path to the jobs and suites that have
to see it; test.yml runs each job whole on the selector's one flag for it, and its last job, `CI`,
is the one required check (scripts/github-workflows/ci_gate.py). These tests hold the properties
whose loss is a defect -- a test nothing runs, a job that can fail without stopping a merge, a
change that runs less than it can break -- and nothing of the workflow's layout beyond them: a
job is added, renamed, split or retimed without an edit here.
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
REHEARSALS = ("install-linux.yml", "install-windows.yml")


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


def route(*paths: str) -> dict[str, str]:
    return selector.outputs(selector.select_paths(paths), paths)


def condition(job: str) -> str:
    """The one flag a job runs on: its whole `if:`."""
    return re.search(r"^    if: needs\.changes\.outputs\.(\w+) == 'true'$", JOBS[job], re.M)[1]


def jobs_for(*paths: str) -> set[str]:
    """The jobs test.yml runs for a change to `paths`, read from each job's own condition."""
    selected = route(*paths)
    return {job for job in GATED if selected[condition(job)] == "true"}


def jobs_on(*flags: str) -> set[str]:
    return {job for job in GATED if condition(job) in flags}


def a_test_in(folder: str) -> str:
    """Some test file under a suite's folder: whichever the tree has, so none is named here."""
    return sorted(path for path in TRACKED if re.fullmatch(rf"{re.escape(folder)}/test_[^/]*\.py", path))[0]


class EveryTestRunsInCI(unittest.TestCase):
    def test_every_test_runner_runs_in_ci(self):
        # A runner no job calls is a suite that never runs. `test.sh` only chains the others.
        runners = sorted(path.name for path in (REPO_ROOT / "scripts/test").glob("test-*.sh"))
        self.assertTrue(runners)
        self.assertEqual([name for name in runners if f"scripts/test/{name}" not in WORKFLOW], [])

    def test_every_test_file_is_collected_by_a_ci_runner(self):
        # A test-like file outside every runner's collection is one nothing runs. Each pattern
        # restates where a runner looks; a runner that moves must move its pattern here too.
        collected = [
            r"^packages/(core|ui)/(src|scripts)/.*\.test\.[cm]?js$",  # packages/*/scripts/run-tests.mjs
            r"^packages/ui/src/.*\.test\.tsx?$",                        # packages/ui vitest.config.ts
            r"^apps/web/(src|scripts)/.*\.test\.[cm]?js$",              # apps/web/scripts/run-tests.mjs
            r"^apps/mcp/src/.*\.test\.tsx?$",                          # apps/mcp vitest.config.mjs
            r"^apps/api/src/[^/]*\.test\.mjs$",                         # test-api.sh (node --test)
            r"^scripts/test/check-(dependencies|kit-boundaries|ui-strings)\.test\.mjs$",  # test-js.sh
            r"^tests/python/packages/cad(_server|_mcp)?/(.*/)?test_[^/]*\.py$",  # test-python.sh, test-floor.sh
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
        self.assertEqual({job for job in GATED if selected[condition(job)] == "true"}, GATED)
        self.assertEqual(selected["packages_tests"], PACKAGES)
        self.assertEqual(selector.scope(selected), "full")
        # Light tests run in static, every other test in the skills job: together, all.
        policy = set(selector.light_policy()) | set(selected["skills_policy"].split())
        self.assertEqual(policy, {path.relative_to(REPO_ROOT).as_posix() for path in (REPO_ROOT / POLICY).glob("test_*.py")})
        suites = set(selector.LIGHT_SKILL_TESTS) | set(selected["skills_tests"].split())
        self.assertEqual(suites, {f"{SKILLS}/{path.name}" for path in (REPO_ROOT / SKILLS).iterdir() if path.is_dir()})

    def test_static_runs_on_every_change_waits_on_nothing_and_installs_nothing(self):
        # No flag and no selection to wait for: it runs when Changed paths fails, and on a push
        # whose tree was already tested. Its lists of light tests are the selector's own.
        static = JOBS["static"]
        self.assertNotRegex(static, r"(?m)^    (if|needs):")
        self.assertNotIn("needs.changes", static)
        self.assertNotIn("setup-deps", static)
        for name, expected in (("policy", selector.light_policy()), ("skills", list(selector.LIGHT_SKILL_TESTS))):
            with self.subTest(name=name), contextlib.redirect_stdout(io.StringIO()) as said:
                self.assertIn(f"select_checks.py --light {name})", static)
                self.assertEqual(selector.main(["--light", name]), 0)
                self.assertEqual(said.getvalue().split(), expected)
                self.assertTrue(expected)
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(selector.main(["--light"]), 2)

    def test_light_tests_never_skip_for_a_missing_dependency(self):
        # static installs nothing; a test that skipped itself without a dependency would pass
        # there having tested nothing.
        light = [REPO_ROOT / path for path in selector.light_policy()]
        light += [file for path in selector.LIGHT_SKILL_TESTS for file in sorted((REPO_ROOT / path).rglob("test*.py"))]
        for file in light:
            with self.subTest(file=file.name):
                self.assertNotRegex(file.read_text(encoding="utf-8"), r"except (ImportError|ModuleNotFoundError)")

    def test_the_shards_of_a_suite_are_all_of_it(self):
        # A matrix written by hand could leave a shard out, and its tests with it: the packages
        # jobs take theirs from the selector, which names every shard of however many there are.
        for selected in (route(), selector.outputs(selector.EVERYTHING), route(a_test_in(f"{PACKAGES}/cad_mcp"))):
            for platform in selector.SHARDS:
                shards = json.loads(selected[f"{platform}_shards"])
                self.assertEqual(shards, [f"{index}/{len(shards)}" for index in range(1, len(shards) + 1)])
        whole = selector.outputs(selector.EVERYTHING)
        self.assertEqual({platform: len(json.loads(whole[f"{platform}_shards"])) for platform in selector.SHARDS},
                         selector.SHARDS)
        for job in jobs_on("packages"):
            with self.subTest(job=job):
                self.assertRegex(JOBS[job], r"shard: \$\{\{ fromJSON\(needs\.changes\.outputs\.\w+_shards\) \}\}")
                self.assertIn("CAD_TEST_SHARD: ${{ matrix.shard }}", JOBS[job])
        # The UI's tests are two halves of one runner group, a job each.
        runner = (REPO_ROOT / "scripts/test/test-js.sh").read_text(encoding="utf-8")
        parts = re.search(r"part: \[([\w, ]+)\]", JOBS["js-ui"])[1].split(", ")
        self.assertEqual(sorted(parts), ["browser", "units"])
        self.assertIn("--select ui-${{ matrix.part }}", JOBS["js-ui"])
        for part in parts:
            self.assertIn(f"UI_TEST_PASS={part} npm --prefix packages/ui test", runner)


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

    def test_every_heavy_test_has_a_rule_that_runs_it(self):
        # The light contracts run on every change; a heavy one runs only when a rule selects it,
        # so one no rule selects would run only when everything does.
        policy: set[str] = set()
        skills: set[str] = set()
        for rule in selector.RULES:
            if isinstance(rule.selects, selector.Select) and not rule.selects.full:
                policy |= rule.selects.policy
                skills |= rule.selects.skills
        everything = selector.outputs(selector.EVERYTHING)
        self.assertEqual(selector.outputs(selector.Select(policy=frozenset(policy)))["skills_policy"], everything["skills_policy"])
        self.assertEqual(selector.outputs(selector.Select(skills=frozenset(skills)))["skills_tests"], everything["skills_tests"])

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


class TheWorkflowFollowsTheSelector(unittest.TestCase):
    def test_one_flag_one_job(self):
        # A job runs whole on its own flag, after the selection, or is skipped; and every flag
        # the selector writes starts a job: none is left that nothing reads.
        flags = set(route())
        started = set()
        for job in GATED:
            with self.subTest(job=job):
                self.assertRegex(JOBS[job], r"(?m)^    needs: changes$")
                self.assertEqual(len(re.findall(r"(?m)^    if: ", JOBS[job])), 1)
                self.assertIn(condition(job), flags)
                started.add(condition(job))
        self.assertEqual(started, set(selector.FLAGS) | {"packages", "skills"})

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
        full = re.search(r"^          FULL: (.+)$", JOBS["changes"], re.M)[1]
        for source in ("github.event_name == 'workflow_dispatch'", "github.event_name == 'schedule'", "inputs.full"):
            self.assertIn(source, full)
        # A pull request is diffed on its merge commit; only a push reads `before`.
        self.assertIn("BEFORE: ${{ github.event_name == 'push' && github.event.before || '' }}", JOBS["changes"])
        # A record only saves a re-run: failing to upload one must not fail the run.
        self.assertIn("continue-on-error: true", JOBS["changes"].split("steps.select.outputs.record != ''", 1)[1])
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


class TheOneRequiredCheck(unittest.TestCase):
    """main's branch protection requires `CI` alone (CONTRIBUTING.md, Repository settings)."""

    def test_the_gate_needs_every_job_and_runs_whatever_became_of_them(self):
        ci = JOBS["ci"]
        self.assertEqual([job for job, body in JOBS.items() if re.search(r"(?m)^    name: CI$", body)], ["ci"])
        needed = set(re.findall(r"^      - ([a-z][\w-]*)$", ci.split("    needs:\n", 1)[1].split("    if:", 1)[0], re.M))
        self.assertEqual(needed, set(JOBS) - {"ci"})
        # always(): a job skipped for a failed dependency would satisfy the required check.
        self.assertRegex(ci, r"(?m)^    if: always\(\)$")
        self.assertIn("NEEDS: ${{ toJSON(needs) }}", ci)
        self.assertIn("scripts/github-workflows/ci_gate.py", ci)
        self.assertEqual(route("scripts/github-workflows/ci_gate.py")["full"], "true")

    def test_no_job_asks_for_more_than_publish_release_grants_the_call(self):
        # A called workflow's job may ask for no permission its caller lacks: one that did would
        # stop Publish Release's call before a job ran.
        publish = (WORKFLOWS / "release-publish.yml").read_text(encoding="utf-8")
        call = publish.split("\n  test:\n", 1)[1].split("\n  publish:\n", 1)[0]
        granted = dict(re.findall(r"^      (\w[\w-]*): (\w+)$", call.split("    permissions:\n", 1)[1].split("    uses:", 1)[0], re.M))
        self.assertTrue(granted)
        for name in ("test.yml", *REHEARSALS):
            text = (WORKFLOWS / name).read_text(encoding="utf-8")
            # Only the block form: a one-line `permissions: write-all` (or read-all, or {}) asks for
            # what the block's names would not show.
            self.assertNotRegex(text, r"(?m)^ *permissions:[ \t]*[^\s#]", name)
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

    def test_a_result_the_gate_does_not_know_fails_it(self):
        code, why = gate.verdict({"changes": "success", "static": "success", "fea": "neutral"}, lambda: False)
        self.assertEqual(code, 1)
        self.assertIn("fea", why)

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
        # What the gate reads a pull request's head by is what the workflow hands it.
        for name in ("PULL_REQUEST", "HEAD_SHA"):
            self.assertRegex(JOBS["ci"], rf"(?m)^          {name}: \$\{{\{{ github\.event\.pull_request\.")

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


class NothingWaitsLong(unittest.TestCase):
    """A stalled mirror fails in minutes: an `apt-get update` once ran 39 minutes to its job's timeout."""

    def test_every_job_has_a_timeout_and_every_setup_step_its_own(self):
        for job, body in JOBS.items():
            with self.subTest(job=job):
                if not re.search(r"(?m)^    uses: ", body):  # a called workflow's jobs have theirs, below
                    self.assertRegex(body, r"(?m)^    timeout-minutes: \d+$")
        for name in ("test.yml", *REHEARSALS):
            text = (WORKFLOWS / name).read_text(encoding="utf-8")
            self.assertEqual(len(re.findall(r"(?m)^    runs-on: ", text)), len(re.findall(r"(?m)^    timeout-minutes: \d+$", text)), name)
            setups = re.findall(r"      - name: ([^\n]+)\n((?:        .*\n)*?)        uses: (\./\.github/actions/setup-deps"
                                r"|actions/setup-python@\S+|actions/setup-node@\S+)\n", text)
            self.assertTrue(setups, name)
            for step, before, _action in setups:
                with self.subTest(workflow=name, step=step):
                    self.assertRegex(before, r"timeout-minutes: \d+\n")

    def test_no_job_runs_apt_itself(self):
        # setup-deps installs what a job names, only when the image lacks it, and gives up on a
        # connection that says nothing: one step to bound, not one a job.
        self.assertNotIn("apt-get", WORKFLOW)
        action = (REPO_ROOT / ".github/actions/setup-deps/action.yml").read_text(encoding="utf-8")
        self.assertRegex(action, r"Acquire::https?::Timeout=\d+")


class TheInstallerRehearsals(unittest.TestCase):
    def test_they_are_called_here_and_start_no_other_way_but_by_hand(self):
        names = set()
        for name in REHEARSALS:
            with self.subTest(workflow=name):
                # Called on a flag: before the merge, not on the push after it, and by no list of
                # paths of the workflow's own (the selector's is the one definition).
                callers = [job for job in GATED if f"    uses: ./.github/workflows/{name}\n" in JOBS[job]]
                self.assertEqual(len(callers), 1)
                text = (WORKFLOWS / name).read_text(encoding="utf-8")
                triggers = text.split("\non:\n", 1)[1].split("\npermissions:", 1)[0]
                self.assertEqual(set(re.findall(r"^  (\w+):$", triggers, re.M)), {"workflow_dispatch", "workflow_call"})
                # One run holds both: an artifact of one name would be the other's.
                uploaded = set(re.findall(r"^          name: (\S+)$", text, re.M))
                self.assertFalse(uploaded & names)
                names |= uploaded
        self.assertLessEqual(jobs_on("installer"), jobs_for("VERSION"))  # a release rehearses them before it ships


class ChangesRunWhatCanBreak(unittest.TestCase):
    """The selector's behaviour, by property, and one change per component rule."""

    def test_an_unknown_path_runs_everything(self):
        self.assertEqual(route("some/new/kind/of.file")["full"], "true")
        self.assertEqual(jobs_for("some/new/kind/of.file"), GATED)
        # ...and so does what every job shares, and the selection itself.
        for path in ("VERSION", "package-lock.json", "requirements-dev.txt", ".github/workflows/test.yml",
                     ".github/actions/setup-deps/action.yml", "scripts/github-workflows/select_checks.py",
                     "scripts/test/unittest_files.py", "tests/python/support/paths.py", "packages/core/package.json"):
            with self.subTest(path=path):
                self.assertEqual(route(path)["full"], "true")

    def test_prose_and_metadata_select_nothing(self):
        # The light contracts read them, and static runs those on every change.
        for path in ("README.md", "CONTRIBUTING.md", "AGENTS.md", "docs/contributing/testing.md",
                     "skills/cad/SKILL.md", ".claude-plugin/plugin.json", "models/README.md",
                     "packages/cad-server/src/cad_server/engine/README.md", "apps/api/package.json",
                     ".github/workflows/release-publish.yml", "scripts/release/bump-version.sh"):
            with self.subTest(path=path):
                self.assertEqual(jobs_for(path), set())
                self.assertEqual(route(path)["full"], "false")

    def test_a_test_file_runs_itself_and_a_helper_its_suite(self):
        test = a_test_in(f"{PACKAGES}/cad_server")
        selected = route(test)
        self.assertEqual(selected["packages_tests"], test)
        self.assertEqual(jobs_for(test), jobs_on("packages"))
        self.assertEqual(json.loads(selected["linux_shards"]), ["1/1"])  # one job, not a suite's shards
        self.assertEqual(route(f"{PACKAGES}/cad/engine/formats_golden/stl.png")["packages_tests"], PACKAGES)
        heavy = f"{POLICY}/{sorted(selector.HEAVY_POLICY)[0]}"
        self.assertEqual((route(heavy)["skills_policy"], jobs_for(heavy)), (heavy, jobs_on("skills")))
        self.assertEqual(jobs_for(f"{POLICY}/test_ci_workspace_selection.py"), set())  # light: static's
        # A suite with a job of its own is that job's alone.
        for suite, flag in (("fea", "fea"), ("kicad", "kicad"), ("blender", "bpy")):
            with self.subTest(suite=suite):
                self.assertEqual(jobs_for(a_test_in(f"{PACKAGES}/{suite}")), jobs_on(flag))

    def test_a_deleted_test_file_has_nothing_left_to_run(self):
        self.assertEqual(jobs_for(f"{PACKAGES}/cad_server/test_gone_for_good.py"), set())

    def test_mixed_changes_take_the_union(self):
        test, page = a_test_in(f"{PACKAGES}/cad_mcp"), "apps/docs/src/app/page.tsx"
        self.assertEqual(jobs_for(test, page, "README.md"), jobs_for(test) | jobs_for(page))
        self.assertEqual(route("README.md", "some/new/kind/of.file")["full"], "true")

    def test_the_tests_a_change_touches_run_first(self):
        # A break in a pull request's own test reports in a minute or two, not at the suite's end.
        module, first, second = "packages/cad/src/cad/__init__.py", a_test_in(f"{PACKAGES}/cad_mcp"), a_test_in(f"{PACKAGES}/cad_server")
        self.assertEqual(route(module, first, second)["changed_tests"], f"{first} {second}")
        # ...but not when they are all the suite step runs anyway, nor a file that is gone, nor one
        # of a suite another job owns.
        self.assertEqual(route(first)["changed_tests"], "")
        self.assertEqual(route(module, f"{PACKAGES}/cad_server/test_gone_for_good.py")["changed_tests"], "")
        self.assertEqual(route(module, a_test_in(f"{PACKAGES}/fea"))["changed_tests"], "")
        self.assertEqual(route("VERSION", first)["changed_tests"], first)
        # ...nor more of them than is a quick answer: that many would be the suite run twice.
        many = sorted(path.relative_to(REPO_ROOT).as_posix() for path in (REPO_ROOT / PACKAGES / "cad").glob("test_*.py"))
        self.assertGreater(len(many), selector.CHANGED_FIRST)
        self.assertEqual(route(module, *many[: selector.CHANGED_FIRST + 1])["changed_tests"], "")
        self.assertNotEqual(route(module, *many[: selector.CHANGED_FIRST])["changed_tests"], "")
        # What runs first is no part of what was tested: the record's scope is the same.
        self.assertEqual(selector.scope(route(module, first)), selector.scope(route(module)))

    def test_each_component_reaches_what_runs_it(self):
        packages = jobs_on("packages", "skills", "packaging", "web_viewer", "fea", "kicad", "bpy", "routing")
        ui = jobs_on("web_ui", "web_client", "web_viewer", "mcp", "packaging")
        cases = {
            # The packages: their suites whole on both platforms, and every job that runs them.
            "packages/cad/src/cad/__init__.py": packages,
            "packages/cad-server/src/cad_server/viewer/__init__.py": packages,
            "packages/cad-mcp/pyproject.toml": packages,
            "scripts/bundle/bundle.sh": packages,
            # A distribution's README is its wheel's description; other prose there is no build's.
            "packages/cad/README.md": jobs_on("packaging"),
            # The UI reaches the two hosts and the wheel, never the packages' suites.
            "packages/ui/package.json": ui,
            "apps/web/package.json": jobs_on("web_client", "web_viewer", "packaging"),
            "apps/web/README.md": jobs_on("web_client"),
            "apps/mcp/package.json": jobs_on("mcp", "packaging"),
            "apps/docs/package.json": jobs_on("docs", "core_js"),
            # The documentation site sets the install guide, the migration guides and its own pages,
            # and resolves their links: its build is their check. Its copy of the registry runs the
            # registry's test.
            "docs/install.md": jobs_on("docs"),
            "docs/migrations/migrating-0.8-to-0.10.md": jobs_on("docs"),
            "apps/docs/content/skills/renders.md": jobs_on("docs"),
            "apps/docs/src/lib/docs/registry.generated.json": jobs_on("docs", "core_js", "packages"),
            "tests/browser/viewer-e2e.mjs": jobs_on("web_viewer"),
            # The installer rehearsals: the installers, their folder and the workflows; a release.
            "scripts/install/install.sh": jobs_on("installer", "docs", "packages"),
            ".github/workflows/install-windows.yml": jobs_on("installer"),
            # A runner runs what it feeds.
            "scripts/test/test-js.sh": jobs_on("core_js", "web_ui", "web_client", "mcp"),
            "scripts/test/test-floor.sh": jobs_on("floor"),
            "scripts/test/test-installed.sh": jobs_on("packaging"),
            # The fea skill's own suite needs the kernel.
            "skills/fea/SKILL.md": jobs_on("skills"),
        }
        for path, expected in cases.items():
            with self.subTest(path=path):
                self.assertTrue((REPO_ROOT / path).exists(), "a case for a path that is gone")
                self.assertEqual(jobs_for(path), expected)
        whole = route("packages/cad/src/cad/__init__.py")
        self.assertEqual(whole["packages_tests"], PACKAGES)
        self.assertEqual(whole["skills_policy"], selector.outputs(selector.EVERYTHING)["skills_policy"])
        # A fixture one language writes and another asserts is current runs that one test beside its own jobs.
        robot = route("packages/ui/src/renderers/robot/__fixtures__/anything.json")
        self.assertEqual(robot["packages_tests"], f"{PACKAGES}/cad_server/test_robot_payload.py")
        # The floor is the release tier's alone: no change to the packages selects it.
        self.assertFalse(jobs_on("floor") & packages)


if __name__ == "__main__":
    unittest.main()
