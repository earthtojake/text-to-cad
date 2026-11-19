"""The docs site is deployed only while PyPI's newest cad has the command the install command hands over to.

The site serves the install command (``scripts/install/``), which gets PyPI's newest cad and hands the agent apps to
its ``cad plugin install``. ``scripts/release/newest_cad.py`` asks that cad, by uv, for the command's help before a
production deploy (``.github/workflows/deploy-docs.yml``); here it is run with a stand-in ``uv`` on PATH, which notes
how it was called and answers as a test says: no real uv, cad or network. What the workflow does with it is held by
its text, the one part no test can run.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from tests.python.support.paths import REPO_ROOT

SCRIPT = REPO_ROOT / "scripts" / "release" / "newest_cad.py"
spec = importlib.util.spec_from_file_location("newest_cad", SCRIPT)
newest_cad = importlib.util.module_from_spec(spec)
spec.loader.exec_module(newest_cad)

WORKFLOW = (REPO_ROOT / ".github/workflows/deploy-docs.yml").read_text(encoding="utf-8")
ASKED = ["tool", "run", "--no-config", "--managed-python", "--python", "3.14", "cad@latest", "plugin", "install",
         "--help"]
VERSION = ["tool", "run", "--no-config", "--managed-python", "--python", "3.14", "cad@latest", "--version"]
# What 0.11.13, which has no such command, says to it (read from PyPI's own, November 2026), after uv's lines.
REFUSED = ("Installed 8 packages in 9ms\nusage: cad plugin [-h] {update} ...\n"
           "cad plugin: error: argument {update}: invalid choice: 'install' (choose from 'update')\n")
# A stand-in uv: it notes its words and the folders its environment names, then answers the command's help with
# FAKE_SAID and FAKE_EXIT, and `--version` with FAKE_VERSION.
UV = textwrap.dedent('''\
    #!{python}
    import json, os, sys
    with open(os.environ["FAKE_LOG"], "a", encoding="utf-8") as log:
        log.write(json.dumps({{"argv": sys.argv[1:], "home_there": os.path.isdir(os.environ.get("HOME", "")),
                               "env": {{key: os.environ.get(key) for key in (
                                   "HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "DO_NOT_TRACK", "CAD_STATE_DIR",
                                   "XDG_STATE_HOME", "XDG_CONFIG_HOME", "HTTPS_PROXY", "UV_CACHE_DIR")}}}}) + "\\n")
    if sys.argv[-1] == "--version":
        print("Installed 8 packages in 9ms", file=sys.stderr)
        print("cad " + os.environ["FAKE_VERSION"])
        sys.exit(0)
    sys.stderr.write(os.environ.get("FAKE_SAID", ""))
    sys.exit(int(os.environ.get("FAKE_EXIT", "0")))
''')


@unittest.skipIf(os.name == "nt", "the stand-in is a script run by its #! line")
class NewestCad(unittest.TestCase):
    def setUp(self) -> None:
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name).resolve()
        self.bin, self.home, self.log = self.root / "bin", self.root / "home", self.root / "log.jsonl"
        self.bin.mkdir()
        self.home.mkdir()
        uv = self.bin / "uv"
        uv.write_text(UV.format(python=sys.executable), encoding="utf-8")
        uv.chmod(0o755)

    def check(self, path: str | None = None, **extra: str) -> subprocess.CompletedProcess:
        """The check run as the workflow runs it, on a machine whose own folders are the test's."""
        environ = {"PATH": str(self.bin) if path is None else path, "HOME": str(self.home), "FAKE_LOG": str(self.log),
                   "CAD_STATE_DIR": str(self.home / "state"), "XDG_STATE_HOME": str(self.home / ".local" / "state"),
                   "XDG_CONFIG_HOME": str(self.home / ".config"), "HTTPS_PROXY": "http://127.0.0.1:9",
                   "UV_CACHE_DIR": str(self.root / "uv-cache"), "FAKE_VERSION": "0.11.13", **extra}
        return subprocess.run([sys.executable, str(SCRIPT)], env=environ, capture_output=True, text=True,
                              encoding="utf-8", timeout=120)

    def calls(self) -> list:
        lines = self.log.read_text(encoding="utf-8").splitlines() if self.log.exists() else []
        return [json.loads(line) for line in lines]

    def test_a_newest_cad_with_the_command_lets_the_deploy_go_on(self) -> None:
        done = self.check(FAKE_VERSION="0.12.0", FAKE_SAID="usage: cad plugin install [-h]\n")
        self.assertEqual((done.returncode, done.stdout), (0, "PyPI's newest cad (cad 0.12.0) has `cad plugin "
                                                             "install`: the install command can hand over to it.\n"))
        self.assertNotIn("error", done.stderr)
        # Asked for the command's help, by the words the install command hands over with; then which release it is.
        asked, version = self.calls()
        self.assertEqual((asked["argv"], version["argv"]), (ASKED, VERSION))
        # In a home of its own, which is gone afterwards: never the machine's, nor a folder of cad's or of a person's
        # settings there. uv's own variables and the proxy stay, so it reaches PyPI as it would.
        for call in (asked, version):
            env = call["env"]
            self.assertTrue(call["home_there"])
            self.assertEqual(env["HOME"], env["USERPROFILE"])
            self.assertNotEqual(env["HOME"], str(self.home))
            self.assertFalse(Path(env["HOME"]).exists())
            self.assertTrue(env["APPDATA"].startswith(env["HOME"]) and env["LOCALAPPDATA"].startswith(env["HOME"]))
            self.assertEqual([env["CAD_STATE_DIR"], env["XDG_STATE_HOME"], env["XDG_CONFIG_HOME"]], [None] * 3)
            self.assertEqual((env["DO_NOT_TRACK"], env["HTTPS_PROXY"], env["UV_CACHE_DIR"]),
                             ("1", "http://127.0.0.1:9", str(self.root / "uv-cache")))
        self.assertEqual(list(self.home.iterdir()), [])

    def test_a_newest_cad_without_the_command_stops_the_deploy_in_one_line_that_says_what_to_do(self) -> None:
        done = self.check(FAKE_EXIT="2", FAKE_SAID=REFUSED)
        self.assertEqual((done.returncode, done.stdout), (1, ""))
        # What uv and cad said, then the one line: why, and what to do.
        self.assertTrue(done.stderr.startswith(REFUSED))
        line, = done.stderr[len(REFUSED):].splitlines()
        self.assertEqual(line, "error: PyPI's newest cad (cad 0.11.13) has no `cad plugin install`, which this ref's "
                               "install command hands the agent apps to: deployed now, every install from the site "
                               "would fail. Ship the release of cad that carries the command first (Publish Release "
                               "deploys the site itself, once PyPI lists it); nothing is deployed.")
        self.assertEqual([call["argv"] for call in self.calls()], [ASKED, VERSION])

    def test_a_cad_that_could_not_be_asked_stops_the_deploy_too_and_is_not_called_one_without_the_command(self) -> None:
        # PyPI not reached (uv's own exit status is 2 too), a newest cad that does not start, uv stopped: no answer
        # is no yes. Which release it was is not asked: nothing answered.
        for extra, why in (({"FAKE_EXIT": "2", "FAKE_SAID": "error: Failed to fetch: `https://pypi.org/simple/cad/`\n"},
                            "exit status 2; what it said is above"),
                           ({"FAKE_EXIT": "1", "FAKE_SAID": "ImportError: cannot import name 'run'\n"},
                            "exit status 1; what it said is above"),
                           ({"FAKE_EXIT": "1", "FAKE_SAID": REFUSED}, "exit status 1; what it said is above")):
            with self.subTest(extra=extra):
                self.log.unlink(missing_ok=True)
                done = self.check(**extra)
                self.assertEqual((done.returncode, done.stdout), (1, ""))
                self.assertTrue(done.stderr.startswith(extra["FAKE_SAID"]))
                line, = done.stderr[len(extra["FAKE_SAID"]):].splitlines()
                self.assertEqual(line, "error: PyPI's newest cad could not be asked whether it has `cad plugin "
                                       f"install` (`uv {' '.join(ASKED)}`: {why}), and this ref's install command "
                                       "hands the agent apps to it: nothing is deployed. Where PyPI or uv's downloads "
                                       "were not reached, run this again; where the newest cad does not start, ship "
                                       "a release that does first.")
                self.assertEqual([call["argv"] for call in self.calls()], [ASKED])
        self.assertIn("no answer in 10 minutes", newest_cad.verdict(124, "", "its release was not read"))
        # No uv at all: one line, and nothing run.
        self.log.unlink()
        done = self.check(path=str(self.root / "nowhere"))
        self.assertEqual((done.returncode, done.stdout, self.calls()), (1, "", []))
        line, = done.stderr.splitlines()
        self.assertTrue(line.startswith("error: uv is not on PATH"), line)

    def test_the_deploy_asks_before_anything_is_built_and_only_where_production_gets_this_ref_s_install_command(
            self) -> None:
        steps = dict(re.findall(r"(?ms)^      - name: (.+?)\n(.*?)(?=^      (?:- name: |# )|\Z)",
                                WORKFLOW.split("\n    steps:\n", 1)[1]))
        names = list(steps)
        check = "Check PyPI's newest cad has the command the install command hands over to"
        self.assertIn("        run: python3 scripts/release/newest_cad.py\n", steps[check])
        # After the checkout it reads the script from, with uv set up for it, and before the site is built or sent.
        self.assertEqual(names.index("Set up uv") + 1, names.index(check))
        self.assertLess(names.index("Check out deploy ref"), names.index("Set up uv"))
        for later in ("Set up Node.js", "Install Vercel CLI", "Deploy docs app to Vercel"):
            self.assertLess(names.index(check), names.index(later), later)
        # Production alone (a release's call has no `preview`: it is asked), and a ref that carries the check: the
        # workflow is the dispatching branch's, the checkout may be a past release's tag.
        only = "        if: ${{ !inputs.preview && hashFiles('scripts/release/newest_cad.py') != '' }}\n"
        for name in ("Set up uv", check):
            self.assertIn(only, steps[name], name)
        self.assertNotRegex(WORKFLOW.split("workflow_call:", 1)[1].split("\npermissions:", 1)[0], r"\bpreview:")
        self.assertNotIn("continue-on-error", WORKFLOW)
        # The one job deploys: no other could send the site unasked.
        self.assertEqual(re.findall(r"(?m)^  (\w[\w-]*):$", WORKFLOW.split("\njobs:\n", 1)[1]), ["deploy"])


if __name__ == "__main__":
    unittest.main()
