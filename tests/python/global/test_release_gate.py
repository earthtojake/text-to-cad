"""Publish Release ships only a tree a run tested in full, and names it only once PyPI has it.

The gate looks up the record a Test run made of the release commit's tree
(scripts/github-workflows/tested_tree.py). Found, the tests are not run again; not found,
the workflow runs every Test job on the commit first, and the publish job runs only after
one of the two. The branches installers follow get the release only after PyPI's index lists
it, and the docs and the tag only after them; nothing purges the version feed.
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


def evaluate(expression: str, results: dict[str, str], outputs: dict[str, str], ref: str = "refs/heads/main") -> bool:
    """A job condition, given the needed jobs' results, the gate's outputs and the run's ref."""
    expression = re.sub(r"needs\.([\w-]+)\.result (==|!=) '(\w*)'",
                        lambda m: str((results[m[1]] == m[3]) == (m[2] == "==")), expression)
    expression = re.sub(r"github\.ref (==|!=) '([^']*)'", lambda m: str((ref == m[2]) == (m[1] == "==")), expression)
    expression = re.sub(r"needs\.gate\.outputs\.(\w+) (==|!=) '(\w*)'",
                        lambda m: str((outputs.get(m[1], "") == m[3]) == (m[2] == "==")), expression)
    # Another job's output, given as "job.name".
    expression = re.sub(r"needs\.([\w-]+)\.outputs\.(\w+) (==|!=) '(\w*)'",
                        lambda m: str((outputs.get(f"{m[1]}.{m[2]}", "") == m[4]) == (m[3] == "==")), expression)
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

    def test_the_release_bundles_the_viewer_and_the_cad_app_as_the_release(self):
        # The bundle step names the version it releases in the variable the apps' build reads
        # (packages/ui/scripts/build-id.mjs): their app menu then shows `v<VERSION>`, where every
        # other build shows `v<VERSION>-dev.<commit>`.
        helper = (REPO_ROOT / "packages/ui/scripts/build-id.mjs").read_text(encoding="utf-8")
        variable = re.search(r'^export const RELEASE_ENV = "(\w+)";$', helper, re.M)[1]
        step = JOBS["publish"].split("- name: Bundle production outputs\n", 1)[1].split("\n      - name: ", 1)[0]
        self.assertIn(f"{variable}: ${{{{ needs.gate.outputs.version }}}}", step)
        self.assertIn("run: scripts/bundle/bundle.sh --clean", step)

    def test_the_wheel_s_smoke_check_starts_no_engine(self):
        # CI runs doctor on the built wheel to prove it answers; an engine it started would linger in
        # the job. Doctor asks whether one runs and never starts it, and takes no option to say so.
        doctors = [line.strip() for line in WORKFLOW.splitlines() if re.search(r"\bcad\"? doctor\b", line)]
        self.assertTrue(doctors, "the release smoke-tests doctor")
        for line in doctors:
            self.assertRegex(line, r"\bdoctor$")

    def test_the_release_builds_the_four_projects_and_installs_its_three_wheels_together(self):
        publish = JOBS["publish"]
        self.assertIn("for project in cad aliases/cad-server aliases/cad-mcp aliases/cadgen; do\n"
                      "            python3 -m build --outdir dist \"packages/$project\"", publish)
        # Exactly the four projects' wheels and sdists at the release, nothing else.
        check = publish.split("- name: Check the distributions are the release's\n", 1)[1].split("\n      - name: ", 1)[0]
        self.assertIn("for name in cad cad_server cad_mcp cadgen; do", check)
        self.assertEqual({project.replace("-", "_") for project in pypi_release.PROJECTS},
                         set(re.search(r"for name in ([\w ]+); do", check)[1].split()))
        install = publish.split("- name: Install the built wheels and exercise them\n", 1)[1].split("\n      - name: ", 1)[0]
        self.assertIn("dist/cad-[0-9]*.whl", install)
        self.assertIn("dist/cad_server-*.whl dist/cad_mcp-*.whl", install)
        self.assertIn("scripts/test/test-installed.sh --wheels dist", install)
        self.assertIn('"$RUNNER_TEMP/install-test/bin/cad-mcp" --help', install)
        self.assertIn("find dist -name 'cad-[0-9]*.whl'", publish)

    def test_installers_get_the_version_only_once_pypi_serves_it(self):
        # The library uploaded and listed by PyPI's index -- what uv resolves a pin through -- before the others,
        # which pin it at the release; cad-server and cad-mcp together, in one upload, both listed before cadgen,
        # the alias the version feed reads, goes last (apps/api: a release cadgen lists installs by every name).
        # All in the pypi job, which the install branches, the tag and the docs follow.
        pypi = JOBS["pypi"]
        self.assertEqual(pypi_release.PROJECTS, ("cad", "cad-server", "cad-mcp", "cadgen"))
        steps = [
            'pypi_release.py --project cad --version "$VERSION" --built',
            "packages-dir: upload-to-pypi/cad\n",
            'pypi_release.py --project cad --version "$VERSION" --wait',
            'pypi_release.py --project cad-server --version "$VERSION" --built',
            'pypi_release.py --project cad-mcp --version "$VERSION" --built',
            "packages-dir: upload-to-pypi/servers\n",
            'pypi_release.py --project cad-server --version "$VERSION" --wait',
            'pypi_release.py --project cad-mcp --version "$VERSION" --wait',
            'pypi_release.py --project cadgen --version "$VERSION" --built',
            "packages-dir: upload-to-pypi/cadgen\n",
            'pypi_release.py --project cadgen --version "$VERSION" --wait',
        ]
        at = 0
        for step in steps:
            with self.subTest(step=step):
                at = pypi.index(step, at)
        self.assertEqual(pypi.count("uses: pypa/gh-action-pypi-publish@"), 3)
        self.assertEqual(pypi.count("--upload upload-to-pypi/servers"), 2, "cad-server and cad-mcp share one upload")
        # The branches and the tag follow PyPI, on main, in one job.
        tag = condition("tag-release")
        self.assertTrue(evaluate(tag, {"pypi": "success"}, {"is_main": "true"}))
        self.assertFalse(evaluate(tag, {"pypi": "success"}, {"is_main": "false"}))
        for result in ("failure", "skipped", "cancelled"):
            self.assertFalse(evaluate(tag, {"pypi": result}, {"is_main": "true"}))
        # The docs deploy follows the branches' push, and only it: a tag that fails after the push holds
        # nothing back, and a job that never pushed deploys nothing.
        docs = condition("deploy-docs")
        self.assertTrue(evaluate(docs, {}, {"tag-release.branches": "pushed"}))
        self.assertFalse(evaluate(docs, {}, {"tag-release.branches": ""}))
        self.assertIn("branches: ${{ steps.branches.outputs.pushed == 'true' && 'pushed' || '' }}", JOBS["tag-release"])
        self.assertNotIn("branches", JOBS, "the branches move in the tag's job: one runner, not two")

    def test_only_the_pypi_job_on_main_in_its_environment_may_mint_a_pypi_token(self):
        # PyPI's trusted publisher names this workflow and the `release` environment, which deploys from
        # main alone: the token-minting permission lives in that one job, and nowhere else.
        minting = [job for job, body in JOBS.items() if re.search(r"^\s+id-token: write$", body, re.M)]
        self.assertEqual(minting, ["pypi"])
        self.assertRegex(JOBS["pypi"], re.compile(r"^    environment: release$", re.M))
        self.assertNotRegex(WORKFLOW, re.compile(r"^permissions:(?:\n  .*)*\n  id-token", re.M), "no workflow-wide token")
        pypi = condition("pypi")
        self.assertTrue(evaluate(pypi, {"publish": "success"}, {"is_main": "true"}))
        self.assertFalse(evaluate(pypi, {"publish": "success"}, {"is_main": "true"}, ref="refs/heads/build-test"))
        self.assertFalse(evaluate(pypi, {"publish": "success"}, {"is_main": "false"}))
        for result in ("failure", "skipped", "cancelled"):
            self.assertFalse(evaluate(pypi, {"publish": result}, {"is_main": "true"}))
        # A file PyPI already holds is never uploaded again unchecked: no skip-existing, and the
        # release attaches what PyPI serves.
        self.assertNotIn("skip-existing", WORKFLOW)
        self.assertIn("scripts/release/pypi_release.py", JOBS["pypi"])
        self.assertIn("name: dist-${{ needs.gate.outputs.version }}-released", JOBS["tag-release"])

    def test_the_branches_get_their_copies_of_the_plugin(self):
        # latest gets one copy and claude.ai's claude-plugin the other, in one push: both or neither. It is the
        # tag job's first step after the checkout, so the tag follows it.
        job = JOBS["tag-release"]
        body = job.split("- name: Commit the plugin onto latest, claude-plugin and codex-plugin and push them\n", 1)[1]
        body = body.split("\n      - name: ", 1)[0]
        self.assertLess(job.index("- name: Commit the plugin onto latest"), job.index("- name: Configure tag push credentials"))
        self.assertLess(job.index("- name: Commit the plugin onto latest"), job.index("- name: Create release tag and GitHub Release"))
        self.assertIn("plugin_branch.py --commit --copy latest", body)
        self.assertIn("plugin_branch.py --commit --copy directory", body)
        self.assertIn('git push --atomic "$remote" "$latest:refs/heads/latest" "$directory:refs/heads/claude-plugin"',
                      body)
        self.assertIn('echo "pushed=true" >> "$GITHUB_OUTPUT"', body)
        self.assertNotIn("refs/heads/plugin", body)
        # Only a deploy key may update those branches, so the push goes over SSH with the release's own key,
        # checked against GitHub's host keys, and nothing else -- not the token the tag's later step uses; the
        # gate checks for the key on main, before the PyPI upload.
        self.assertIn("INSTALL_BRANCHES_KEY: ${{ secrets.INSTALL_BRANCHES_KEY }}", body)
        self.assertIn('remote="git@github.com:${GITHUB_REPOSITORY}.git"', body)
        self.assertIn("StrictHostKeyChecking=yes", body)
        self.assertNotIn("x-access-token", body)
        check = JOBS["gate"].split("- name: Check the install branches' deploy key", 1)[1]
        self.assertIn("if: steps.gate.outputs.should_publish == 'true' && steps.gate.outputs.is_main == 'true'", check)
        self.assertIn("INSTALL_BRANCHES_KEY: ${{ secrets.INSTALL_BRANCHES_KEY }}", check)
        self.assertNotIn("PUBLISH_PUSH_TOKEN", WORKFLOW)

    def test_nothing_purges_the_version_feed(self):
        # The feed (apps/api) names a release only once every file of it has been on PyPI an hour, and its edge keeps
        # an answer five minutes: a purge when the release ships finds the feed not naming it yet, and one later saves
        # minutes at most. No job purges it, and no job holds the Vercel API project's id for that.
        self.assertNotIn("feed", JOBS)
        self.assertNotIn("vercel cache purge", WORKFLOW)
        self.assertNotIn("VERCEL_API_PROJECT_ID", WORKFLOW)

    def test_the_release_carries_the_installer_and_its_checksums(self):
        # releases/download/v<VERSION>/ keeps the release's installer files for the record, checked against the
        # SHA256SUMS beside them (install.sh, run from anywhere, downloads the newest install.py from
        # texttocad.dev); a rehearsal lists the same.
        body = JOBS["tag-release"]
        gather = body.split("- name: Gather the installer scripts and their checksums\n", 1)[1].split("\n      - name: ", 1)[0]
        self.assertIn("cp scripts/install/install.sh scripts/install/install.ps1 scripts/install/install.py", gather)
        self.assertIn("sha256sum install.sh install.ps1 install.py > SHA256SUMS", gather)
        attach = body.split("- name: Create release tag and GitHub Release\n", 1)[1]
        for name in ("install.sh", "install.ps1", "install.py", "SHA256SUMS"):
            self.assertIn(f'"$RUNNER_TEMP"/installer/{name}', attach)
        self.assertIn('"$RUNNER_TEMP"/installer/*', JOBS["publish"].split("- name: Rehearsal summary (build-test)", 1)[1])

    def test_the_release_carries_cad_s_distributions_not_the_empty_aliases(self):
        # The aliases (cad-server, cad-mcp, cadgen) are empty and PyPI keeps them: the release page carries cad's
        # wheel and sdist alone, in a release and a rehearsal alike. `cad-*` names cad's files and none of the
        # aliases' (cad_server-, cad_mcp-, cadgen-).
        import fnmatch

        attach = JOBS["tag-release"].split("- name: Create release tag and GitHub Release\n", 1)[1]
        rehearsal = JOBS["publish"].split("- name: Rehearsal summary (build-test)", 1)[1]
        for body, folder in ((attach, '"$RUNNER_TEMP"/dist/'), (rehearsal, "dist/")):
            self.assertIn(f"{folder}cad-*.whl", body)
            self.assertIn(f"{folder}cad-*.tar.gz", body)
            self.assertNotIn(f"{folder}*", body.replace(f"{folder}cad-*", ""))
        built = ["cad-0.11.13-py3-none-any.whl", "cad-0.11.13.tar.gz", "cad_server-0.11.13-py3-none-any.whl",
                 "cad_server-0.11.13.tar.gz", "cad_mcp-0.11.13-py3-none-any.whl", "cad_mcp-0.11.13.tar.gz",
                 "cadgen-0.11.13-py3-none-any.whl", "cadgen-0.11.13.tar.gz"]
        attached = [name for name in built if fnmatch.fnmatch(name, "cad-*.whl") or fnmatch.fnmatch(name, "cad-*.tar.gz")]
        self.assertEqual(attached, ["cad-0.11.13-py3-none-any.whl", "cad-0.11.13.tar.gz"])


pypi_release = load("pypi_release", "scripts/release/pypi_release.py")


class PypiRelease(unittest.TestCase):
    def test_a_release_uploads_only_what_pypi_lacks_and_attaches_what_pypi_holds(self):
        built = ["cadgen-1.0.0-py3-none-any.whl", "cadgen-1.0.0.tar.gz"]
        self.assertEqual(pypi_release.plan(built, {}), (built, [], []))
        held = {"cadgen-1.0.0-py3-none-any.whl": {"sha256": "a", "url": "u"}}
        self.assertEqual(pypi_release.plan(built, held), (["cadgen-1.0.0.tar.gz"], ["cadgen-1.0.0-py3-none-any.whl"], []))
        held["cadgen-1.0.0-cp312-cp312-linux_x86_64.whl"] = {"sha256": "b", "url": "v"}
        self.assertEqual(pypi_release.plan(built, held)[2], ["cadgen-1.0.0-cp312-cp312-linux_x86_64.whl"])

    def test_each_call_is_one_project_s_files_at_the_release(self):
        built = ["cad-1.0.0-py3-none-any.whl", "cad-1.0.0.tar.gz", "cad_server-1.0.0-py3-none-any.whl",
                 "cad_server-1.0.0.tar.gz", "cad_mcp-1.0.0.tar.gz",
                 "cadgen-1.0.0-py3-none-any.whl", "cad-0.9.9.tar.gz", "cad-1.0.0rc1.tar.gz"]
        self.assertEqual(pypi_release.files_of("cad", "1.0.0", built),
                         ["cad-1.0.0-py3-none-any.whl", "cad-1.0.0.tar.gz"])
        self.assertEqual(pypi_release.files_of("cad-server", "1.0.0", built),
                         ["cad_server-1.0.0-py3-none-any.whl", "cad_server-1.0.0.tar.gz"])
        self.assertEqual(pypi_release.files_of("cadgen", "1.0.0", built), ["cadgen-1.0.0-py3-none-any.whl"])

    def test_waiting_ends_once_the_index_lists_the_release_and_fails_when_it_never_does(self):
        answers = iter([False, False, True])
        with mock.patch.object(pypi_release, "listed", side_effect=lambda *_: next(answers)) as listed, \
                contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(pypi_release.wait("cad", "1.0.0", tries=5, pause=0), 0)
        self.assertEqual(listed.call_count, 3)
        with mock.patch.object(pypi_release, "listed", return_value=False) as listed, \
                contextlib.redirect_stderr(io.StringIO()) as said:
            self.assertEqual(pypi_release.wait("cad", "1.0.0", tries=3, pause=0), 1)
        self.assertEqual(listed.call_count, 3)
        self.assertIn("does not list cad 1.0.0", said.getvalue())

    def test_a_file_from_pypi_that_does_not_match_its_listed_sha256_is_refused(self):
        import hashlib
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "served.whl"
            source.write_bytes(b"wheel bytes")
            target = Path(folder) / "cadgen-1.0.0-py3-none-any.whl"
            good = hashlib.sha256(b"wheel bytes").hexdigest()
            pypi_release.download(source.as_uri(), good, target)
            self.assertEqual(target.read_bytes(), b"wheel bytes")
            target.unlink()
            with self.assertRaises(SystemExit):
                pypi_release.download(source.as_uri(), "0" * 64, target)
            self.assertEqual(sorted(path.name for path in Path(folder).iterdir()), ["served.whl"])


class PrepareRelease(unittest.TestCase):
    def test_it_opens_the_pull_request_and_never_merges_it(self):
        # A pull request the workflow's own token opened would start no checks.
        opened = PREPARE_WORKFLOW.split("- name: Open the release pull request", 1)[1]
        self.assertIn("GH_TOKEN: ${{ secrets.PREPARE_RELEASE_TOKEN }}", opened)
        self.assertIn("scripts/release/bump-version.sh", PREPARE_WORKFLOW)
        self.assertNotRegex(PREPARE_WORKFLOW, r"gh pr merge|/merge\b|workflow run release-publish")


if __name__ == "__main__":
    unittest.main()
