"""The install script: scripts/install/install.py, and the two thin scripts that run it.

Each test runs install.py in a fresh temporary home (HOME, XDG_*, APPDATA) with stand-in programs on PATH --
the agent apps' CLIs, uv, npx, git -- that record how they were called and change nothing else (git clone writes a
small copy of the plugin; gemini's uninstall removes its extension's folder; uv's tool install records the tool in
a file of the test's and writes a stand-in `cad` in the home's ~/.local/bin). No real app, network, uv or cad runs:
PATH holds only the stand-ins, install.py is told not to search Homebrew's or npm's folders or app bundles
(CAD_INSTALL_PATH_ONLY), and every proxy is a closed port.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest
from unittest import mock
import zipfile

from tests.python.support.paths import REPO_ROOT

INSTALL = REPO_ROOT / "scripts" / "install"
spec = importlib.util.spec_from_file_location("text_to_cad_install", INSTALL / "install.py")
install = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = install
spec.loader.exec_module(install)

LATEST = "a" * 40  # the commit of `latest`, as the stand-in git names it
OURS = "---\nname: {name}\ndescription: x\nmetadata:\n  repository: earthtojake/text-to-cad\n---\n"
# A skill of 0.5.0-0.8.4: no metadata, our provenance line in its body.
OURS_OLD = "---\nname: {name}\ndescription: x\nlicense: MIT\n---\n\n# X\n\n" + install.PROVENANCE_LINE + "\n"
THEIRS = "---\nname: {name}\ndescription: someone else's\n---\n"

# A stand-in: records {name, argv} as a JSON line; fails (exit FAKE_EXIT, default 1) where FAKE_FAIL names it
# (`name`, or `name:word` for a call whose arguments hold that word); `git clone` writes a small plugin folder with our
# skills, `git ls-remote` names the commit LATEST, `git status` prints FAKE_GIT_STATUS (a clean clone of `latest` by
# default); `uv --version` says the version in a file `uv-version` beside it, else FAKE_UV_VERSION; `curl -o <file>` writes
# FAKE_UV_INSTALLER there (a stand-in of uv's own installer); uv's tools are FAKE_UV_STATE's ({name: version}), their commands in
# FAKE_UV_BIN: `uv tool list` lists them, `uv tool install` records one (`cad`, unversioned: FAKE_PYPI; at
# FAKE_NO_COMMAND, a release with no command, it fails and takes the tool away, as uv does) and writes its command, a
# stand-in (its receipt names an `editable` requirement where it was one); `pipx environment --value` says
# FAKE_PIPX_VENVS (PIPX_LOCAL_VENVS) and FAKE_PIPX_BIN (PIPX_BIN_DIR), or fails as pipx 1.0 does (FAKE_PIPX_1_0), whose
# `pipx list --json` names cad's command in FAKE_PIPX_VENVS, and `pipx install --force cad` sets the release in pipx's
# metadata of cad (FAKE_PYPI); `gemini extensions uninstall
# <name>` removes that extension's folder, and, with FAKE_GEMINI_RECORD, `gemini extensions install <url> --ref <ref>`
# writes its record. Each call notes its folder and Gemini's trust.
STAND_IN = textwrap.dedent('''\
    #!{python}
    import json, os, shutil, sys
    from pathlib import Path
    name = Path(sys.argv[0]).name
    with open(os.environ["FAKE_LOG"], "a", encoding="utf-8") as log:
        log.write(json.dumps({{"name": name, "argv": sys.argv[1:], "cwd": os.getcwd(), "path": sys.argv[0],
                               "trust": os.environ.get("GEMINI_CLI_TRUST_WORKSPACE"),
                               "failed": os.environ.get("CAD_INSTALL_FAILED")}}) + "\\n")
    if any(fail == name or (fail.partition(":")[0] == name and fail.partition(":")[2] in sys.argv[1:])
           for fail in os.environ.get("FAKE_FAIL", "").split(",")):
        print(f"{{name}}: something went wrong")
        sys.exit(int(os.environ.get("FAKE_EXIT", "1")))
    if name == "git" and "ls-remote" in sys.argv:
        print("{latest}\\trefs/heads/latest")
    if name == "git" and "status" in sys.argv:
        print(os.environ.get("FAKE_GIT_STATUS", "## latest...origin/latest"))
    if name == "uv" and sys.argv[1:] == ["--version"]:
        told = Path(sys.argv[0]).with_name("uv-version")
        print("uv " + (told.read_text().strip() if told.exists() else os.environ.get("FAKE_UV_VERSION", "0.11.0")) + " (stand-in)")
    if name == "curl" and "-o" in sys.argv:
        Path(sys.argv[sys.argv.index("-o") + 1]).write_text(os.environ.get("FAKE_UV_INSTALLER", "exit 1\\n"))
    if name == "uv" and sys.argv[1:3] in (["tool", "dir"], ["tool", "list"], ["tool", "install"], ["tool", "uninstall"]):
        state, tools_dir = Path(os.environ["FAKE_UV_STATE"]), Path(os.environ["FAKE_UV_STATE"]).with_suffix(".tools")
        tools = json.loads(state.read_text()) if state.exists() else {{}}
        command = Path(os.environ["FAKE_UV_BIN"]) / "cad"
        if sys.argv[2] == "dir":
            print(command.parent if "--bin" in sys.argv else tools_dir)
        elif sys.argv[2] == "list":
            for tool, version in tools.items():
                print(f"{{tool}} v{{version}} ({{tools_dir / tool}})")
                print(f"- cad ({{command}})")
            print("" if tools else "No tools installed")
        elif sys.argv[2] == "uninstall":
            tools.pop(sys.argv[-1], None)
            command.unlink()
        elif sys.argv[-1].partition("==")[2] == os.environ.get("FAKE_NO_COMMAND"):  # as uv: the whole tool goes
            print("No executables are provided by package `cad`; removing tool")
            tools.pop("cad", None)
            command.unlink(missing_ok=True)
            state.write_text(json.dumps(tools))
            sys.exit(2)
        else:
            tools["cad"] = sys.argv[-1].partition("==")[2] or os.environ.get("FAKE_PYPI", "0.13.0")
            command.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(sys.argv[0], command)
            (tools_dir / "cad").mkdir(parents=True, exist_ok=True)
            (tools_dir / "cad" / "uv-receipt.toml").write_text("editable = 1" if "--editable" in sys.argv else "")
        state.write_text(json.dumps(tools))
    if name == "cad" and sys.argv[1:] == ["--version"]:
        print("cad (stand-in)")
    if name == "pipx" and sys.argv[1] == "environment" and os.environ.get("FAKE_PIPX_1_0"):
        print("pipx: error: argument command: invalid choice: 'environment'")
        sys.exit(2)
    if name == "pipx" and sys.argv[1:3] == ["environment", "--value"]:
        print(os.environ[{{"PIPX_LOCAL_VENVS": "FAKE_PIPX_VENVS", "PIPX_BIN_DIR": "FAKE_PIPX_BIN"}}[sys.argv[3]]])
    if name == "pipx" and sys.argv[1:3] == ["install", "--force"]:
        metadata = Path(os.environ["FAKE_PIPX_VENVS"]) / "cad" / "pipx_metadata.json"
        found = json.loads(metadata.read_text())
        found["main_package"]["package_version"] = os.environ.get("FAKE_PYPI", "0.13.0")
        metadata.write_text(json.dumps(found))
    if name == "pipx" and sys.argv[1:] == ["list", "--json"]:
        own = str(Path(os.environ["FAKE_PIPX_VENVS"]) / "cad" / "bin" / "cad")
        print("nothing to see here")
        print(json.dumps({{"venvs": {{"cad": {{"metadata": {{"main_package": {{"app_paths": [{{"__Path__": own}}]}}}}}}}}}}))
    if name == "gemini" and "uninstall" in sys.argv:
        shutil.rmtree(Path(os.environ["HOME"]) / ".gemini" / "extensions" / sys.argv[-1], ignore_errors=True)
    if name == "gemini" and sys.argv[1:3] == ["extensions", "install"] and os.environ.get("FAKE_GEMINI_RECORD"):
        record = Path(os.environ["HOME"]) / ".gemini" / "extensions" / "text-to-cad" / ".gemini-extension-install.json"
        record.parent.mkdir(parents=True, exist_ok=True)
        ref = sys.argv[sys.argv.index("--ref") + 1]
        record.write_text(json.dumps({{"source": sys.argv[3], "type": "git", "ref": ref}}))
    if name == "git" and "clone" in sys.argv:
        target = Path(sys.argv[-1])
        (target / ".git").mkdir(parents=True)
        (target / ".git" / "config").write_text('[remote "origin"]\\n\\turl = ' + sys.argv[-2] + "\\n")
        for skill in ("cad", "pcb"):
            (target / "skills" / skill).mkdir(parents=True)
            (target / "skills" / skill / "SKILL.md").write_text(
                f"---\\nname: {{skill}}\\nmetadata:\\n  repository: earthtojake/text-to-cad\\n---\\nnew\\n")
''')


def exe(path: Path, main: str) -> Path:
    """A cad.exe as 0.11 wrote it: distlib's launcher, a shebang naming the ``cad-launcher`` beside it, then a zip whose
    ``__main__.py`` is ``main`` (0.11's carries the mark)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("__main__.py", main)
    path.write_bytes(b"MZ launcher\n#!<launcher_dir>\\cad-launcher\\Scripts\\python.exe -I\n" + path.read_bytes())
    return path


@unittest.skipIf(os.name == "nt", "the stand-ins are scripts run by their #! line")
class InstallScriptTests(unittest.TestCase):
    def setUp(self) -> None:
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name).resolve()
        self.home = self.root / "home"
        self.home.mkdir()
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.log = self.root / "log.jsonl"
        self.state = self.home / ".local" / "state" / "cad"
        self.uv_bin = self.home / ".local" / "bin"
        self.programs("uv", "git")

    def programs(self, *names: str) -> None:
        for name in names:
            path = self.bin / name
            path.write_text(STAND_IN.format(python=sys.executable, latest=LATEST), encoding="utf-8")
            path.chmod(0o755)

    def write(self, relative: str, value) -> Path:
        path = self.home / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value if isinstance(value, str) else json.dumps(value), encoding="utf-8")
        return path

    def environ(self, **extra: str) -> dict:
        closed = "http://127.0.0.1:9"
        return {"HOME": str(self.home), "PATH": str(self.bin), "FAKE_LOG": str(self.log),
                "XDG_CONFIG_HOME": str(self.home / ".config"), "XDG_STATE_HOME": str(self.home / ".local" / "state"),
                "APPDATA": str(self.home / "AppData" / "Roaming"), "CODEX_CLI": "codex", "CAD_INSTALL_PATH_ONLY": "1",
                "https_proxy": closed, "http_proxy": closed, "HTTPS_PROXY": closed, "HTTP_PROXY": closed, "no_proxy": "",
                "FAKE_UV_STATE": str(self.root / "uv.json"),
                "FAKE_UV_BIN": str(self.uv_bin), **extra}

    def run_install(self, *argv: str, **extra: str) -> subprocess.CompletedProcess:
        if self.log.exists():
            self.log.unlink()
        return subprocess.run([sys.executable, str(INSTALL / "install.py"), *argv], env=self.environ(**extra),
                              capture_output=True, text=True, encoding="utf-8", timeout=120)

    def calls(self, name: str = None) -> list:
        lines = self.log.read_text(encoding="utf-8").splitlines() if self.log.exists() else []
        found = [json.loads(line) for line in lines]
        return [call["argv"] for call in found if name is None or call["name"] == name]

    def switched(self) -> list:
        """What each ``cad plugin update auto on`` was told of how the run is ending (``CAD_INSTALL_FAILED``)."""
        lines = self.log.read_text(encoding="utf-8").splitlines() if self.log.exists() else []
        return [call["failed"] for call in map(json.loads, lines)
                if call["name"] == "cad" and call["argv"] == ["plugin", "update", "auto", "on"]]

    def desktop(self) -> str:
        """Claude Desktop's config, where install.py looks for it on this platform, relative to the home."""
        return str(install.desktop_config(install.Here(self.environ())).relative_to(self.home))

    def tools(self, **versions: str) -> None:
        """uv's tools, as the stand-in uv keeps them, each with its command in ~/.local/bin."""
        (self.root / "uv.json").write_text(json.dumps(versions), encoding="utf-8")
        for name in versions:
            self.uv_bin.mkdir(parents=True, exist_ok=True)
            (self.uv_bin / "cad").write_text(STAND_IN.format(python=sys.executable, latest=LATEST), encoding="utf-8")
            (self.uv_bin / "cad").chmod(0o755)

    def no_tools(self) -> None:
        """uv with no tools, and no cad command in ~/.local/bin."""
        (self.root / "uv.json").unlink(missing_ok=True)
        (self.uv_bin / "cad").unlink(missing_ok=True)

    def installs(self) -> list:
        """The `uv tool install` calls, each without its first two words."""
        return [argv[2:] for argv in self.calls("uv") if argv[:2] == ["tool", "install"]]

    def claude_records(self, plugins: dict, catalogs: dict) -> None:
        self.write(".claude/plugins/installed_plugins.json",
                   {"version": 2, "plugins": {key: [{"scope": "user"}] for key in plugins}})
        self.write(".claude/plugins/known_marketplaces.json", {name: {"source": source} for name, source in catalogs.items()})

    def test_a_fresh_computer_gets_cad_and_the_plugin_in_every_app_found(self) -> None:
        self.programs("claude", "codex", "gemini", "grok", "muse")
        (self.home / ".cursor").mkdir()
        (self.home / ".cline").mkdir()
        # Muse has no copy yet: its update fails, and it installs from the `latest` branch fetched once.
        done = self.run_install(FAKE_FAIL="muse:update")
        self.assertEqual(0, done.returncode, done.stdout + done.stderr)
        # cad: PyPI's newest, as a uv tool; then the plugin's automatic updates turned on, by that cad.
        self.assertEqual(self.installs(), [["--managed-python", "--python", "3.14", "cad"]])
        self.assertIn("Installing cad with uv.", done.stdout)
        self.assertEqual(self.calls("cad"), [["plugin", "update", "auto", "on"]])
        self.assertEqual(self.switched(), [""], "told the run is ending well: cad keeps this release")
        self.assertEqual(self.calls("claude"), [["plugin", "marketplace", "add", "earthtojake/text-to-cad#latest"],
                                                ["plugin", "install", "text-to-cad@earthtojake"]])
        self.assertEqual(self.calls("codex"), [["plugin", "marketplace", "add", "earthtojake/text-to-cad", "--ref", "latest"],
                                               ["plugin", "add", "text-to-cad@earthtojake"]])
        self.assertEqual(self.calls("gemini"), [["extensions", "install", install.URL, "--ref", "latest", "--consent"]])
        # Cursor and Grok Build load Claude Code's plugin: none of their own.
        self.assertEqual(self.calls("grok"), [])
        self.assertFalse((self.home / ".cursor/plugins/local/text-to-cad").exists())
        # An agent with no plugin command gets the skills in its own folder, from `latest`.
        self.assertIn("new", (self.home / ".cline/skills/cad/SKILL.md").read_text(encoding="utf-8"))
        self.assertEqual(self.calls("git")[0][:6], ["clone", "--quiet", "--depth", "1", "--branch", "latest"])
        self.assertEqual(len(self.calls("git")), 1)
        fetched = self.calls("git")[0][-1]
        self.assertEqual(self.calls("muse"), [["plugins", "update", "text-to-cad"], ["plugins", "install", fetched],
                                              ["plugins", "approve", "text-to-cad"]])
        for line in ("Claude Code: installed", "Codex: installed", "Gemini CLI: installed",
                     "Grok Build: skipped: it loads Claude Code's plugin", "Cursor: skipped: it loads Claude Code's plugin",
                     "Cline: installed: 2 skills in ~/.cline/skills", "Muse: installed",
                     "other supported apps were not found here.", "Start a new session in each app to use it."):
            self.assertIn(line, done.stdout)
        self.assertNotIn("removed", done.stdout)

    def test_with_no_cad_the_newest_is_installed_and_a_cad_there_is_left_alone_whatever_its_release(self) -> None:
        done = self.run_install()
        self.assertEqual(0, done.returncode, done.stdout + done.stderr)
        self.assertEqual(self.installs(), [["--managed-python", "--python", "3.14", "cad"]])
        self.assertEqual(json.loads((self.root / "uv.json").read_text(encoding="utf-8")), {"cad": "0.13.0"})
        # Nothing found, nothing installed: no word of a new session.
        self.assertNotIn("Start a new session", done.stdout)
        # A cad tool here that starts, older or newer than PyPI's newest: left as it is (cad updates itself), and its
        # plugin switch turned on all the same.
        for there in ("0.13.0", "0.1.0", "99.0.0"):
            self.tools(cad=there)
            done = self.run_install(FAKE_PYPI="5.0.0")
            self.assertEqual(0, done.returncode, done.stdout + done.stderr)
            self.assertEqual(self.installs(), [], there)
            self.assertIn(f"cad {there} is installed already: it is left as it is, and updates itself.", done.stdout)
            self.assertEqual(self.calls("cad"), [["--version"], ["plugin", "update", "auto", "on"]])
            self.assertEqual(json.loads((self.root / "uv.json").read_text(encoding="utf-8")), {"cad": there})

    def test_a_cad_that_does_not_start_is_installed_again(self) -> None:
        # Windows can leave a tool half-replaced: running the install command again is how it is repaired.
        self.tools(cad="1.0.0")
        report = self.root / "report.json"
        done = self.run_install(FAKE_PYPI="5.0.0", FAKE_FAIL="cad:--version", CAD_INSTALL_REPORT=str(report))
        self.assertEqual(0, done.returncode, done.stdout + done.stderr)
        self.assertIn("cad 1.0.0 is installed but does not start: installing it again with uv.", done.stdout)
        self.assertNotIn("Installing cad with uv.", done.stdout)
        self.assertEqual(self.installs(), [["--reinstall", *install.UV_TOOL_ARGS, "cad"]])
        self.assertEqual(json.loads((self.root / "uv.json").read_text(encoding="utf-8")), {"cad": "5.0.0"})
        self.assertEqual(self.calls("cad"), [["--version"], ["plugin", "update", "auto", "on"]])
        found = json.loads(report.read_text(encoding="utf-8"))
        self.assertEqual((found["release"], found["setup"]), ("5.0.0", 0))
        # The reinstall fails too: the run fails, and says which cad the computer still has.
        self.tools(cad="1.0.0")
        done = self.run_install(FAKE_FAIL="cad:--version,uv:install", CAD_INSTALL_REPORT=str(report))
        self.assertEqual(1, done.returncode)
        self.assertIn("cad: failed (uv tool install exit status 1; what uv said is above).", done.stdout)
        found = json.loads(report.read_text(encoding="utf-8"))
        self.assertEqual((found["release"], found["setup"]), ("1.0.0", 1))

    def pipx_cad(self, version: str = "0.13.0", link: bool = True) -> dict:
        """cad as ``pipx install cad`` leaves it: pipx's environment of cad (its metadata, its own ``cad``, a stand-in)
        and, with ``link``, its command in ~/.local/bin, a link to that (pipx's bin folder by default, and uv's). What
        the stand-in pipx says."""
        venvs = self.home / ".local" / "share" / "pipx" / "venvs"
        own = venvs / "cad" / "bin" / "cad"
        own.parent.mkdir(parents=True)
        (venvs / "cad" / "pipx_metadata.json").write_text(json.dumps(
            {"main_package": {"package": "cad", "package_or_url": "cad", "package_version": version}}), encoding="utf-8")
        own.write_text(STAND_IN.format(python=sys.executable, latest=LATEST), encoding="utf-8")
        own.chmod(0o755)
        if link:
            self.uv_bin.mkdir(parents=True, exist_ok=True)
            (self.uv_bin / "cad").symlink_to(own)
        return {"FAKE_PIPX_VENVS": str(venvs), "FAKE_PIPX_BIN": str(self.uv_bin)}

    def test_a_cad_pipx_installed_is_left_alone_as_uv_s_is_and_uv_installs_no_second(self) -> None:
        said = self.pipx_cad()
        self.programs("pipx")
        report = self.root / "report.json"
        done = self.run_install(CAD_INSTALL_REPORT=str(report), **said)
        self.assertEqual(0, done.returncode, done.stdout + done.stderr)
        self.assertEqual(self.installs(), [])
        self.assertIn("cad 0.13.0 is installed already: it is left as it is, and updates itself.", done.stdout)
        self.assertNotIn("another program's", done.stdout)
        self.assertEqual(self.calls("pipx"), [["environment", "--value", "PIPX_LOCAL_VENVS"],
                                              ["environment", "--value", "PIPX_BIN_DIR"]])
        self.assertEqual(self.calls("cad"), [["--version"], ["plugin", "update", "auto", "on"]])
        self.assertEqual({key: json.loads(report.read_text(encoding="utf-8"))[key] for key in ("release", "setup")},
                         {"release": "0.13.0", "setup": 0})
        # pipx 1.0, which has no `pipx environment`, and no link in ~/.local/bin: its list says where its cad is.
        (self.uv_bin / "cad").unlink()
        done = self.run_install(FAKE_PIPX_1_0="1", **said)
        self.assertEqual(0, done.returncode, done.stdout + done.stderr)
        self.assertIn("cad 0.13.0 is installed already: it is left as it is, and updates itself.", done.stdout)
        self.assertEqual((self.installs(), self.calls("pipx")[-1]), ([], ["list", "--json"]))
        # pipx not found: its link in ~/.local/bin says whose cad it is.
        (self.uv_bin / "cad").symlink_to(self.home / ".local" / "share" / "pipx" / "venvs" / "cad" / "bin" / "cad")
        (self.bin / "pipx").unlink()
        done = self.run_install(**said)
        self.assertEqual(0, done.returncode, done.stdout + done.stderr)
        self.assertEqual((self.installs(), self.calls("pipx")), ([], []))
        self.assertIn("cad 0.13.0 is installed already: it is left as it is, and updates itself.", done.stdout)
        self.assertEqual(self.calls("cad"), [["--version"], ["plugin", "update", "auto", "on"]])
        # uv's cad is there too: uv's is the one, and pipx is not asked.
        self.programs("pipx")
        (self.root / "uv.json").write_text(json.dumps({"cad": "0.12.0"}), encoding="utf-8")
        done = self.run_install(**said)
        self.assertIn("cad 0.12.0 is installed already", done.stdout)
        self.assertEqual((self.installs(), self.calls("pipx")), ([], []))

    def test_a_cad_pipx_installed_that_does_not_start_is_installed_again_by_pipx_never_by_uv(self) -> None:
        said = self.pipx_cad("0.12.0")
        self.programs("pipx")
        (self.home / ".cline").mkdir()
        report = self.root / "report.json"
        done = self.run_install(FAKE_FAIL="cad:--version", FAKE_PYPI="0.14.0", CAD_INSTALL_REPORT=str(report), **said)
        self.assertEqual(0, done.returncode, done.stdout + done.stderr)
        self.assertIn("cad 0.12.0 is installed with pipx but does not start: installing it again with pipx.",
                      done.stdout)
        self.assertEqual(self.installs(), [], "never with uv")
        self.assertEqual(self.calls("pipx")[-1], ["install", "--force", "cad"])
        self.assertEqual(self.calls("cad"), [["--version"], ["plugin", "update", "auto", "on"]])
        self.assertEqual({key: json.loads(report.read_text(encoding="utf-8"))[key] for key in ("release", "setup")},
                         {"release": "0.14.0", "setup": 0})
        # pipx's install fails, or pipx is not found: said in one line, and the apps are done all the same.
        for fail, line in (("cad:--version,pipx:install", "cad: failed (pipx install exit status 1; what pipx said is "
                                                          "above), so cad 0.14.0 could not be installed again."),
                           ("cad:--version", "cad 0.14.0, installed with pipx, does not start, and pipx was not found "
                                             "here, so it could not be installed again.")):
            with self.subTest(fail=fail):
                if "pipx" not in fail:
                    (self.bin / "pipx").unlink()
                done = self.run_install(FAKE_FAIL=fail, CAD_INSTALL_REPORT=str(report), **said)
                self.assertEqual(1, done.returncode)
                self.assertIn(line, done.stdout)
                self.assertNotIn("run `pipx", done.stdout)
                self.assertEqual(self.installs(), [])
                self.assertIn("Cline: updated", done.stdout)
                self.assertEqual(json.loads(report.read_text(encoding="utf-8"))["setup"], 1)

    def test_pipx_without_a_cad_or_a_link_into_another_of_its_environments_is_no_cad(self) -> None:
        said = self.pipx_cad(link=False)
        (self.home / ".local" / "share" / "pipx" / "venvs" / "cad" / "pipx_metadata.json").write_text(json.dumps(
            {"main_package": {"package": "other", "package_version": "1.0"}}), encoding="utf-8")
        self.programs("pipx")
        done = self.run_install(**said)
        self.assertEqual(0, done.returncode, done.stdout + done.stderr)
        self.assertEqual(self.installs(), [["--managed-python", "--python", "3.14", "cad"]], "uv's cad, as on any")
        self.no_tools()
        other = self.home / ".local" / "share" / "pipx" / "venvs" / "other" / "bin" / "cad"
        other.parent.mkdir(parents=True)
        other.write_text("#!/bin/sh\n", encoding="utf-8")
        (self.uv_bin / "cad").symlink_to(other)
        done = self.run_install(**said)
        self.assertEqual(1, done.returncode)
        self.assertIn("is another program's cad command", done.stdout)

    def test_the_old_cad_command_goes_and_another_program_s_stops_the_cad_step(self) -> None:
        # 0.10.0-0.11.11 wrote ~/.local/bin/cad, an sh script with our mark: set aside before uv puts its own there,
        # and put back where uv fails, so the computer keeps a cad command.
        text = "#!/bin/sh\n# cad proxy: 9\n# The cad command: runs ...\nexit 1\n"
        old = self.write(".local/bin/cad", text)
        done = self.run_install(FAKE_FAIL="uv:install")
        self.assertEqual(1, done.returncode)
        self.assertEqual(old.read_text(encoding="utf-8"), text)
        self.assertNotIn("Removed the cad command", done.stdout)
        done = self.run_install()
        self.assertEqual(0, done.returncode, done.stdout + done.stderr)
        self.assertIn("Removed the cad command of an earlier release (~/.local/bin/cad).", done.stdout)
        self.assertEqual(self.installs(), [["--managed-python", "--python", "3.14", "cad"]])
        self.assertNotIn("cad proxy", old.read_text(encoding="utf-8"))  # uv's command in its place
        # Someone else's cad there: kept, and cad is not installed; the apps are done all the same.
        (self.root / "uv.json").unlink()
        mine = self.write(".local/bin/cad", "#!/bin/sh\necho my own cad\n")
        (self.home / ".cline").mkdir()
        done = self.run_install()
        self.assertEqual(1, done.returncode)
        self.assertEqual(mine.read_text(encoding="utf-8"), "#!/bin/sh\necho my own cad\n")
        self.assertEqual(self.installs(), [])
        self.assertIn("cad: not installed: ~/.local/bin/cad is another program's cad command, which uv will not "
                      "replace. Move it away, then run this again.", done.stdout)
        self.assertIn("Cline: installed", done.stdout)
        self.assertIn("cad itself was not installed", done.stdout)
        self.assertEqual(self.calls("cad"), [])

    def test_the_old_windows_commands_are_known_by_their_mark(self) -> None:
        # 0.11's cad.exe (``exe``); 0.10's cad.cmd. uv's own cad.exe is a launcher and a zip too, with no mark.
        bin_ = self.home / ".local/bin"
        bin_.mkdir(parents=True)
        old = exe(bin_ / "cad.exe", "# cad proxy: 11\n# The cad command on Windows (cad.exe)\nimport json\n")
        cmd = self.write(".local/bin/cad.cmd", "@echo off\r\nrem cad proxy: 9\r\nrem The cad command\r\n")
        uv_made = exe(self.root / "uv-cad.exe", "import sys\nfrom cad_server.cli import main\nsys.exit(main())\n")
        self.assertEqual([install.old_launcher(path) for path in (old, cmd, uv_made)], [True, True, False])
        # And the Python 0.11's cad.exe ran: cad-launcher beside it, a virtual environment its shebang names.
        self.write(".local/bin/cad-launcher/pyvenv.cfg", "home = C:\\Python314\nuv = 0.9.5\n")
        self.write(".local/bin/cad-launcher/Scripts/python.exe", "MZ")
        here = install.Here(self.environ(), platform="win32")
        everything = [".cad.cmd.text-to-cad-old", ".cad.exe.text-to-cad-old", ".cad-launcher.text-to-cad-old"]
        problem, moved = install.make_room(here, bin_, {})
        self.assertIsNone(problem)
        self.assertEqual(sorted(path.name for path in bin_.iterdir()), sorted(everything))
        install.settle(here, moved, False)  # uv's cad did not go in: all of it back as it was
        self.assertEqual(sorted(path.name for path in bin_.iterdir()), ["cad-launcher", "cad.cmd", "cad.exe"])
        self.assertTrue((bin_ / "cad-launcher/Scripts/python.exe").is_file())
        problem, moved = install.make_room(here, bin_, {})
        install.settle(here, moved, True)
        self.assertEqual(sorted(path.name for path in bin_.iterdir()), [])
        # A cad-launcher that is no virtual environment, or beside a cad.exe of ours that does not name it, stays.
        for shebang, cfg in ((b"#!<launcher_dir>\\cad-launcher\\Scripts\\python.exe", False),
                             (b"#!C:\\elsewhere\\python.exe", True)):
            (bin_ / "cad-launcher").mkdir()
            if cfg:
                self.write(".local/bin/cad-launcher/pyvenv.cfg", "home = C:\\Python314\n")
            exe(bin_ / "cad.exe", "# cad proxy: 11\n").write_bytes(
                (bin_ / "cad.exe").read_bytes().replace(b"#!<launcher_dir>\\cad-launcher\\Scripts\\python.exe", shebang))
            problem, moved = install.make_room(here, bin_, {})
            install.settle(here, moved, True)
            self.assertEqual(sorted(path.name for path in bin_.iterdir()), ["cad-launcher"], shebang)
            install.discard(bin_ / "cad-launcher")
        # Someone else's cad.exe stops it; one uv lists as its own does not.
        uv_made.rename(bin_ / "cad.exe")
        self.assertIn("is another program's cad command", install.make_room(here, bin_, {})[0])
        self.assertEqual(install.make_room(here, bin_, {"cad": install.Tool("1.0.0", {"cad": str(bin_ / "cad.exe")})}),
                         (None, []))

    def test_on_windows_a_cad_exe_in_uv_s_way_is_set_aside_and_uv_s_folder_goes_on_the_path(self) -> None:
        # uv cannot replace a cad.exe that runs (it fails halfway, measured), but one that runs can be renamed: uv's
        # cad.exe and the tool environment's own go aside, into uv's bin folder (never the environment, which uv
        # deletes), under cad's own update's name; back where uv fails, deleted where it is in.
        folder = self.uv_bin
        env = self.home / "AppData/Roaming/uv/tools/cad"
        mine = [self.write(".local/bin/cad.exe", "uv's"), self.write("AppData/Roaming/uv/tools/cad/Scripts/cad.exe", "env's")]
        tool = install.Tool("1.0.0", {"cad": str(mine[0])}, str(env))
        moved = install.set_aside(folder, tool)
        self.assertEqual([path for path, _aside in moved], mine)
        self.assertTrue(all(aside.parent == folder and aside.is_file() and not path.exists() for path, aside in moved))
        self.assertEqual(len(list(folder.glob(install.ASIDE.format(stamp="*", n="*")))), 2)
        install.put_back(moved, False)
        self.assertEqual([path.read_text(encoding="utf-8") for path in mine], ["uv's", "env's"])
        install.put_back(install.set_aside(folder, tool), True)
        self.assertEqual(sorted(path.name for path in folder.iterdir()), [])
        # Where uv has no cad tool, a cad.exe there is not its: never moved.
        theirs = self.write(".local/bin/cad.exe", "another program's")
        self.assertEqual(install.set_aside(folder, None), [])
        self.assertEqual(theirs.read_text(encoding="utf-8"), "another program's")

    def test_uv_s_folder_goes_on_the_path_by_uv_s_own_command_on_every_system(self) -> None:
        # A shell whose PATH lacks uv's bin folder (winget's or Homebrew's uv puts its own folder there): uv's own
        # `uv tool update-shell` puts it on the PATH for new terminals, as uv's and Codex's installers do; nothing of
        # ours edits a profile. UV_NO_MODIFY_PATH, uv's own switch, stops it; where it fails, a line says what to do.
        uv = str(self.bin / "uv")
        put = ("~/.local/bin is on your PATH now for new terminals (uv tool update-shell): apps and terminals opened "
               "before this one see it once restarted.\n")
        not_put = ("~/.local/bin is not on this shell's PATH: open a new terminal to use cad (where it is still not "
                   "found, run `uv tool update-shell`).\n")
        for platform, separator in (("darwin", ":"), ("linux", ":"), ("win32", ";")):
            for extra, called, line in (({}, True, put), ({"UV_NO_MODIFY_PATH": "1"}, False, not_put),
                                        ({"FAKE_FAIL": "uv:update-shell", "FAKE_EXIT": "2"}, True, not_put),
                                        ({"PATH": f"{self.bin}{separator}{self.uv_bin}"}, False, "")):
                if self.log.exists():
                    self.log.unlink()
                said = io.StringIO()
                with contextlib.redirect_stdout(said):
                    install.on_path(install.Here(self.environ(**extra), platform=platform), uv, self.uv_bin)
                self.assertEqual(self.calls("uv"), [["tool", "update-shell"]] if called else [], (platform, extra))
                self.assertEqual(said.getvalue(), line, (platform, extra))
        self.assertFalse((self.home / ".zshenv").exists(), "the stand-in uv edits no profile; nor does install.py")

    def test_on_windows_a_running_cad_exe_never_stops_the_install_and_a_later_run_removes_what_it_left(self) -> None:
        # Measured on Windows 11 (0.11.0 and 0.11.10): a person's agent types the old `cad update`, whose cad.exe (0.11's
        # launcher) runs the install command. The launcher and its Python go aside, uv's cad goes in, and what was set
        # aside, still running, cannot be deleted (Windows refuses): it stays, and nothing is said of it. The next run
        # deletes it, quietly, and nothing else in uv's bin folder.
        here = install.Here(self.environ(UV=str(self.bin / "uv")), platform="win32")
        exe(self.uv_bin / "cad.exe", "# cad proxy: 11\n# The cad command on Windows (cad.exe)\n")
        self.write(".local/bin/cad-launcher/pyvenv.cfg", "home = C:\\Python314\n")
        discard = install.discard

        def running(path: Path) -> None:  # Windows deletes no file that runs, nor a folder holding one
            if path.name == ".cad.exe.text-to-cad-old":
                raise PermissionError(13, "Access is denied")
            discard(path)

        def busy(_path: Path) -> None:
            raise PermissionError(13, "The process cannot access the file")

        said = io.StringIO()
        with mock.patch.object(install, "discard", running), mock.patch.object(install, "_rmtree", busy), \
                contextlib.redirect_stdout(said):
            cad = install.install_cad(here)
        self.assertEqual((cad.code, cad.release), (0, "0.13.0"), said.getvalue())
        self.assertIn("Installing cad with uv.", said.getvalue())
        self.assertNotIn("not installed", said.getvalue())
        self.assertNotIn("Removed the cad command", said.getvalue())
        left = sorted(path.name for path in self.uv_bin.iterdir())
        self.assertEqual([name for name in left if not name.startswith(".text-to-cad-trash-")],
                         [".cad.exe.text-to-cad-old", "cad"])
        self.assertEqual(len(left), 3, left)
        # The next run: cad is here and starts; what was left goes, quietly. Someone else's files stay.
        self.write(".local/bin/notes.old", "mine")
        self.write(".local/bin/.cad.exe.backup", "mine")
        self.write(".local/bin/" + install.ASIDE.format(stamp="123-456", n=0), "cad's own update's")
        said = io.StringIO()
        with contextlib.redirect_stdout(said):
            cad = install.install_cad(here)
        self.assertEqual(cad.code, 0)
        self.assertEqual(said.getvalue(), "cad 0.13.0 is installed already: it is left as it is, and updates itself.\n")
        self.assertEqual(sorted(path.name for path in self.uv_bin.iterdir()), [".cad.exe.backup", "cad", "notes.old"])
        # Where a cad command of 0.10.0-0.11.11 is still there (its install did not happen), nothing set aside goes.
        kept = self.write(".local/bin/.cad-launcher.text-to-cad-old/pyvenv.cfg", "home = C:\\Python314\n")
        exe(self.uv_bin / "cad.exe", "# cad proxy: 11\n")
        install.tidy(here, self.uv_bin)
        self.assertTrue(kept.is_file())

    def test_the_plugin_switch_is_tolerated_where_cad_does_not_know_it(self) -> None:
        # A cad with no `cad plugin update auto` (a usage error, exit 2): one line, and the install has not failed.
        self.tools(cad="0.11.10")
        done = self.run_install(FAKE_FAIL="cad:plugin", FAKE_EXIT="2")
        self.assertEqual(0, done.returncode, done.stdout + done.stderr)
        self.assertEqual(self.calls("cad"), [["--version"], ["plugin", "update", "auto", "on"]])
        said = [line for line in done.stdout.splitlines() if "update auto" in line]
        self.assertEqual(said, ["cad 0.11.10 has no `cad plugin update auto`: the plugin will not follow cad's updates. "
                                "Run this command again to update the plugin."])
        # Any other failure: what cad said, in one line.
        done = self.run_install(FAKE_FAIL="cad:plugin")
        self.assertEqual(0, done.returncode, done.stdout + done.stderr)
        self.assertIn("The plugin's automatic updates were not turned on (cad said: cad: something went wrong). Run "
                      "this command again to update the plugin.", done.stdout)

    def test_run_again_it_updates_each_app_s_github_copy_with_the_app_s_own_command(self) -> None:
        self.programs("claude", "codex", "gemini")
        github = {"source": "github", "repo": "earthtojake/text-to-cad", "ref": "latest"}
        self.claude_records({"text-to-cad@earthtojake": 1}, {"earthtojake": github})
        self.write(".codex/config.toml", '[marketplaces.earthtojake]\nsource_type = "git"\n'
                                         'source = "https://github.com/earthtojake/text-to-cad.git"\nref = "latest"\n'
                                         '[plugins."text-to-cad@earthtojake"]\nenabled = true\n')
        self.write(".gemini/extensions/text-to-cad/.gemini-extension-install.json",
                   {"type": "git", "source": install.URL, "ref": "latest"})
        done = self.run_install()
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(self.calls("claude"), [["plugin", "marketplace", "update", "earthtojake"],
                                                ["plugin", "update", "text-to-cad@earthtojake"]])
        self.assertEqual(self.calls("codex"), [["plugin", "marketplace", "upgrade", "earthtojake"],
                                               ["plugin", "add", "text-to-cad@earthtojake"]])
        self.assertEqual(self.calls("gemini"), [["extensions", "uninstall", "text-to-cad"],
                                                ["extensions", "install", install.URL, "--ref", "latest", "--consent"]])
        for name in ("Claude Code", "Codex", "Gemini CLI"):
            self.assertIn(f"{name}: updated\n", done.stdout)

    def test_gemini_s_github_copy_is_installed_again_never_asked_to_update(self) -> None:
        # `extensions update` asks twice and takes no --consent: with no one to answer, it waits for ever.
        self.programs("gemini")
        github = {"type": "git", "source": install.URL, "ref": "latest"}
        self.write(".gemini/extensions/text-to-cad/.gemini-extension-install.json", github)
        done = self.run_install(FAKE_GEMINI_RECORD="1")
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertNotIn(["extensions", "update", "text-to-cad"], self.calls("gemini"))
        self.assertEqual(self.calls("gemini"), [["extensions", "uninstall", "text-to-cad"],
                                                ["extensions", "install", install.URL, "--ref", "latest", "--consent"]])
        self.assertIn("Gemini CLI: updated\n", done.stdout)
        self.assertEqual([path.name for path in (self.home / ".gemini/extensions").iterdir()], ["text-to-cad"])
        record = self.home / ".gemini/extensions/text-to-cad/.gemini-extension-install.json"
        self.assertEqual(json.loads(record.read_text(encoding="utf-8")), github)

    def test_gemini_s_github_copy_is_put_back_where_installing_it_again_fails(self) -> None:
        self.programs("gemini")
        github = {"type": "git", "source": install.URL, "ref": "latest"}
        record = self.write(".gemini/extensions/text-to-cad/.gemini-extension-install.json", github)
        skill = self.write(".gemini/extensions/text-to-cad/skills/cad/SKILL.md", OURS.format(name="cad"))
        enablement = self.write(".gemini/extensions/extension-enablement.json", {"text-to-cad": {"overrides": []}})
        done = self.run_install(FAKE_FAIL="gemini:install", FAKE_GEMINI_RECORD="1")
        self.assertEqual(1, done.returncode, done.stdout)
        self.assertEqual(self.calls("gemini")[0], ["extensions", "uninstall", "text-to-cad"])
        self.assertIn("Gemini CLI: failed", done.stdout)
        self.assertIn("the earlier copy was put back", done.stdout)
        self.assertEqual(json.loads(record.read_text(encoding="utf-8")), github)
        self.assertEqual(skill.read_text(encoding="utf-8"), OURS.format(name="cad"))
        self.assertEqual(json.loads(enablement.read_text(encoding="utf-8")), {"text-to-cad": {"overrides": []}})

    def test_gemini_s_commands_run_in_a_folder_of_their_own_never_the_person_s(self) -> None:
        # Run in the person's folder, `--consent` records it as trusted in Gemini's trustedFolders.json.
        self.programs("gemini")
        person = self.home / "projects"
        person.mkdir()
        if self.log.exists():
            self.log.unlink()
        done = subprocess.run([sys.executable, str(INSTALL / "install.py")], env=self.environ(), cwd=person,
                              capture_output=True, text=True, encoding="utf-8", timeout=120)
        self.assertEqual(0, done.returncode, done.stderr)
        self.write(".gemini/extensions/text-to-cad/.gemini-extension-install.json",
                   {"type": "git", "source": install.URL, "ref": "latest"})
        again = subprocess.run([sys.executable, str(INSTALL / "install.py")], env=self.environ(), cwd=person,
                               capture_output=True, text=True, encoding="utf-8", timeout=120)
        self.assertEqual(0, again.returncode, again.stderr)
        found = [json.loads(line) for line in self.log.read_text(encoding="utf-8").splitlines()]
        runs = [call for call in found if call["name"] == "gemini"]
        self.assertEqual(len(runs), 3)  # the install, then the uninstall and the install again
        for call in runs:
            with self.subTest(argv=call["argv"]):
                where = Path(call["cwd"]).resolve()
                self.assertNotEqual(where, person.resolve())
                self.assertFalse(where.is_relative_to(self.home.resolve()))
                self.assertFalse(where.exists())  # made for the command, and removed after it
                self.assertEqual(call["trust"], "true")

    def test_a_second_run_removes_nothing_it_installed_and_says_nothing_of_removing(self) -> None:
        (self.home / ".cline").mkdir()
        (self.home / ".hermes").mkdir()
        self.write(".agents/skills/fea/SKILL.md", OURS.format(name="fea"))  # a 0.8.4-0.11.4 loose copy
        first = self.run_install()
        self.assertIn("Loose skills: removed: 1 old copies of our skills, in ~/.agents/skills", first.stdout)
        second = self.run_install()
        self.assertEqual(0, second.returncode, second.stderr)
        self.assertIn("Cline: updated: 2 skills in ~/.cline/skills\n", second.stdout)
        self.assertIn("Hermes Agent: updated: 2 skills in ~/.hermes/skills\n", second.stdout)
        self.assertNotIn("removed", second.stdout)
        self.assertFalse((self.home / ".agents/skills/fea").exists())
        self.assertEqual(sorted(path.name for path in (self.home / ".cline/skills").iterdir()), ["cad", "pcb"])

    def test_a_person_s_own_skill_of_our_name_that_mentions_the_repository_stays(self) -> None:
        mine = ("---\nname: gcode\ndescription: My own G-code notes\n---\n"
                "For modelling parts I use https://github.com/earthtojake/text-to-cad (earthtojake/text-to-cad).\n")
        self.write(".claude/skills/gcode/SKILL.md", mine)
        self.write(".claude/skills/gcode/notes.md", "months of notes\n")
        (self.home / ".cline").mkdir()
        self.write(".cline/skills/cad/SKILL.md", mine.replace("gcode", "cad"))
        done = self.run_install()
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual((self.home / ".claude/skills/gcode/SKILL.md").read_text(encoding="utf-8"), mine)
        self.assertTrue((self.home / ".claude/skills/gcode/notes.md").is_file())
        self.assertIn("left cad: someone else's skill of that name", done.stdout)
        self.assertNotIn("new", (self.home / ".cline/skills/cad/SKILL.md").read_text(encoding="utf-8"))

    def test_an_edited_copy_of_ours_is_deleted_and_replaced(self) -> None:
        (self.home / ".cline").mkdir()
        self.run_install()
        # The person edits the copy the first run made (its provenance kept) and adds a file; a 0.8 copy (its
        # provenance line) sits in a retired name.
        edited = self.home / ".cline/skills/cad/SKILL.md"
        edited.write_text(edited.read_text(encoding="utf-8") + "my own change\n", encoding="utf-8")
        self.write(".cline/skills/cad/extra.md", "added by hand\n")
        self.write(".cline/skills/dxf/SKILL.md", OURS_OLD.format(name="dxf"))
        done = self.run_install()
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertIn("Cline: updated: 2 skills in ~/.cline/skills\n", done.stdout)
        self.assertNotIn("my own change", edited.read_text(encoding="utf-8"))
        self.assertFalse((self.home / ".cline/skills/cad/extra.md").exists())
        self.assertFalse((self.home / ".cline/skills/dxf").exists())
        # Nothing of the old copies is kept anywhere: no folder beside the skills, nothing new in the home.
        self.assertEqual(sorted(path.name for path in (self.home / ".cline/skills").iterdir()), ["cad", "pcb"])
        self.assertEqual(sorted(path.name for path in self.home.iterdir() if path.name.startswith(".text-to-cad")), [])

    def test_github_failing_leaves_every_app_with_what_it_had(self) -> None:
        self.programs("claude", "codex", "gemini")
        folder = str(self.state / "plugin")
        self.claude_records({"text-to-cad@text-to-cad": 1}, {"text-to-cad": {"source": "directory", "path": folder}})
        self.write(".codex/config.toml", f'[marketplaces.text-to-cad]\nsource_type = "local"\nsource = "{folder}"\n'
                                         '[plugins."text-to-cad@text-to-cad"]\nenabled = true\n')
        record = self.write(".gemini/extensions/text-to-cad/.gemini-extension-install.json", {"type": "link", "source": folder})
        copy = self.write(".cursor/plugins/local/text-to-cad/.text-to-cad-copy", {"from": folder})
        self.write(".agents/skills/cad/SKILL.md", OURS.format(name="cad"))
        (self.home / ".cline").mkdir()
        old = self.write(".cline/skills/pcb/SKILL.md", OURS.format(name="pcb"))
        done = self.run_install(FAKE_FAIL="claude:add,codex:add,gemini:install,git:clone")
        # Every app it found failed: the run says so, and fails; it turns the switch on all the same (cad is here), so
        # the plugin is kept on a computer whose runs keep failing, and tells cad the run is ending badly, so cad keeps
        # no release of the install command's for it (``plugin_catch_up``) and its server runs it again.
        self.assertEqual(1, done.returncode, done.stdout)
        self.assertIn("No app got the plugin", done.stdout)
        self.assertEqual(self.switched(), ["1"])
        self.assertNotIn("Start a new session", done.stdout)
        self.assertEqual(self.calls("claude"), [["plugin", "marketplace", "add", "earthtojake/text-to-cad#latest"]])
        self.assertEqual(self.calls("codex"), [["plugin", "marketplace", "add", "earthtojake/text-to-cad", "--ref", "latest"]])
        # Gemini CLI's linked extension had to go for ours to come in: it is put back as it was.
        self.assertEqual(self.calls("gemini")[-1][:2], ["extensions", "install"])
        self.assertEqual(json.loads(record.read_text(encoding="utf-8")), {"type": "link", "source": folder})
        self.assertIn("the earlier copy was put back", done.stdout)
        self.assertTrue(copy.is_file())
        self.assertTrue((self.home / ".agents/skills/cad/SKILL.md").is_file())
        self.assertEqual(old.read_text(encoding="utf-8"), OURS.format(name="pcb"))
        for name in ("Claude Code", "Codex", "Gemini CLI", "Cursor", "Cline"):
            self.assertIn(f"{name}: failed", done.stdout)
        # A same-named catalog of ours from elsewhere is replaced only once GitHub answers; where the new one fails,
        # the old one is put back.
        github_main = {"source": "github", "repo": "earthtojake/text-to-cad"}
        self.claude_records({"text-to-cad@earthtojake": 1}, {"earthtojake": github_main})
        done = self.run_install(FAKE_FAIL="git:ls-remote")
        self.assertEqual(self.calls("claude"), [])
        done = self.run_install(FAKE_FAIL="claude:install")
        self.assertEqual(self.calls("claude"), [["plugin", "uninstall", "text-to-cad@earthtojake"],
                                                ["plugin", "marketplace", "remove", "--scope", "user", "earthtojake"],
                                                ["plugin", "marketplace", "add", "earthtojake/text-to-cad#latest"],
                                                ["plugin", "install", "text-to-cad@earthtojake"],
                                                ["plugin", "marketplace", "add", "earthtojake/text-to-cad"],
                                                ["plugin", "install", "text-to-cad@earthtojake"]])

    def test_hermes_gets_the_skills_in_its_own_folder_and_our_old_plugin_goes(self) -> None:
        # Hermes Agent is a skills-folder agent: our skills in $HERMES_HOME/skills, no plugin command of its own.
        self.programs("hermes")
        hermes = self.root / "hermes-home"
        done = self.run_install(HERMES_HOME=str(hermes))
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertIn("new", (hermes / "skills/cad/SKILL.md").read_text(encoding="utf-8"))
        self.assertEqual(self.calls("hermes"), [])
        self.assertIn(f"Hermes Agent: installed: 2 skills in {hermes / 'skills'}", done.stdout)
        # Found by its folder alone too; someone else's plugin of that name stays.
        (self.bin / "hermes").unlink()
        self.write(".hermes/plugins/text-to-cad/plugin.json", {"name": "text-to-cad"})
        self.write(".hermes/plugins/.install-metadata.json", {"text-to-cad": {"source": "someone/text-to-cad"}})
        done = self.run_install()
        self.assertIn("Hermes Agent: installed: 2 skills in ~/.hermes/skills\n", done.stdout)
        self.assertTrue((self.home / ".hermes/skills/pcb/SKILL.md").is_file())
        # Ours, from 0.11.x: without the hermes command the skills still come in, and the line says how to remove it.
        self.write(".hermes/plugins/.install-metadata.json",
                   {"text-to-cad": {"source": "https://github.com/earthtojake/text-to-cad.git", "pinned": True}})
        done = self.run_install()
        self.assertIn("Hermes Agent: updated: 2 skills in ~/.hermes/skills; the old text-to-cad plugin in "
                      "~/.hermes/plugins/text-to-cad stays until the hermes command removes it", done.stdout)
        self.programs("hermes")
        done = self.run_install()
        self.assertEqual(self.calls("hermes"), [["plugins", "remove", "text-to-cad"]])
        self.assertIn("Hermes Agent: updated: 2 skills in ~/.hermes/skills (removed old copies: the text-to-cad plugin)",
                      done.stdout)

    def test_without_claude_code_cursor_s_clean_clone_and_grok_s_plugin_are_updated(self) -> None:
        self.programs("grok")
        clone = self.home / ".cursor/plugins/local/text-to-cad"
        self.write(".cursor/plugins/local/text-to-cad/.git/config", f'[remote "origin"]\n\turl = {install.URL}.git\n')
        self.write(".grok/installed-plugins/registry.json", {"repos": {"x": {
            "kind": {"type": "Git", "url": install.URL, "git_ref": "latest"}, "path": "/x",
            "plugins": {"text-to-cad": {"version": "0.11.10"}}}}})
        done = self.run_install()
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(self.calls("grok"), [["plugin", "update", "text-to-cad"]])
        self.assertEqual(self.calls("git"), [["-C", str(clone), "status", "--porcelain=v1", "--branch"],
                                             ["-C", str(clone), "fetch", "--quiet", "--depth", "1", "origin", "latest"],
                                             ["-C", str(clone), "checkout", "--quiet", "-B", "latest", "FETCH_HEAD"]])
        self.assertIn("Cursor: updated", done.stdout)
        self.assertIn("Grok Build: updated", done.stdout)

    def test_a_cursor_clone_with_work_of_its_own_or_a_link_is_left_alone(self) -> None:
        clone = self.home / ".cursor/plugins/local/text-to-cad"
        self.write(".cursor/plugins/local/text-to-cad/.git/config", f'[remote "origin"]\n\turl = {install.URL}.git\n')
        for status, why in (("## latest...origin/latest\n M skills/cad/SKILL.md", "it has changes not committed"),
                            ("## latest...origin/latest [ahead 1]", "it has commits of its own"),
                            ("## main...origin/main", "it is on main, not latest")):
            done = self.run_install(FAKE_GIT_STATUS=status)
            self.assertEqual(self.calls("git"), [["-C", str(clone), "status", "--porcelain=v1", "--branch"]], status)
            self.assertIn(f"Cursor: skipped: ~/.cursor/plugins/local/text-to-cad left alone: {why}", done.stdout)
        # Where Claude Code has our plugin, a clean clone of ours goes; one with work of its own stays.
        self.programs("claude")
        done = self.run_install(FAKE_GIT_STATUS="## latest...origin/latest\n?? my-notes.md")
        self.assertTrue((clone / ".git/config").is_file())
        self.assertIn("left alone: it has changes not committed", done.stdout)
        # A link there (a checkout of ours, say) is never followed, changed or removed.
        checkout = self.root / "checkout"
        (clone / ".git").rename(self.root / "moved-git")
        clone.rmdir()
        (checkout / ".git").mkdir(parents=True)
        (checkout / ".git/config").write_text(f'[remote "origin"]\n\turl = {install.URL}.git\n', encoding="utf-8")
        clone.symlink_to(checkout)
        for claude in (True, False):
            if not claude:
                (self.bin / "claude").unlink()
            done = self.run_install()
            self.assertTrue(clone.is_symlink())
            self.assertEqual(self.calls("git"), [])
            self.assertIn("~/.cursor/plugins/local/text-to-cad is a link: left alone", done.stdout)

    def test_a_character_the_output_cannot_encode_stops_no_app(self) -> None:
        # An output in a code page that has no ✘ (cp1252, as Python writes a pipe on Windows): the line is printed
        # with a `?`, and the run goes on to the next app and the loose skills. On Windows itself the pipe is UTF-8
        # (`install.utf8`), whatever PYTHONIOENCODING says, and the mark goes through.
        self.programs("claude", "gemini")
        stand_in = self.bin / "claude"
        stand_in.write_text(stand_in.read_text(encoding="utf-8").replace(
            "    sys.exit(int(", "    sys.stdout.flush()\n    sys.stdout.buffer.write('\u2718 Failed to add marketplace\\n'.encode())\n    sys.exit(int(", 1),
            encoding="utf-8")
        done = self.run_install(FAKE_FAIL="claude", PYTHONIOENCODING="cp1252")
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertNotIn("Traceback", done.stderr)
        self.assertIn("Claude Code: failed: ", done.stdout)
        self.assertIn(("\u2718" if os.name == "nt" else "?") + " Failed to add marketplace", done.stdout)
        self.assertIn("Gemini CLI: installed", done.stdout)

    def test_its_output_is_utf_8_on_windows_where_it_is_no_console(self) -> None:
        # As `cad setup`'s, which it runs on the same streams: a pipe or a file on Windows; never a console, never
        # another system.
        class Stream:
            def __init__(self, console: bool) -> None:
                self.console = console

            def isatty(self) -> bool:
                return self.console

        self.assertTrue(install.utf8(Stream(False), "nt"))
        self.assertEqual([install.utf8(Stream(True), "nt"), install.utf8(Stream(False), "posix"),
                          install.utf8(Stream(True), "posix"), install.utf8(None, "nt")], [False] * 4)

    def test_what_past_releases_left_is_removed_once_ours_is_in_and_nothing_else(self) -> None:
        self.programs("claude", "codex", "gemini", "grok", "npx")
        folder = str(self.state / "plugin")
        github = {"source": "github", "repo": "earthtojake/text-to-cad", "ref": "latest"}
        # Claude Code: 0.10-0.11.11's local catalog and its plugin, and 0.7.6's cad@earthtojake; someone else's plugin.
        self.claude_records({"text-to-cad@text-to-cad": 1, "cad@earthtojake": 1, "other@acme": 1},
                            {"text-to-cad": {"source": "directory", "path": folder}, "earthtojake": github,
                             "acme": {"source": "github", "repo": "acme/plugins"}})
        # Codex: the local catalog's copy, and a copy from OpenAI's directory, which stays.
        self.write(".codex/config.toml", f'[marketplaces.text-to-cad]\nsource_type = "local"\nsource = "{folder}"\n'
                                         '[plugins."text-to-cad@text-to-cad"]\nenabled = true\n'
                                         '[plugins."text-to-cad@openai-curated"]\nenabled = true\n')
        # Gemini CLI: the extension linked to the plugin folder.
        self.write(".gemini/extensions/text-to-cad/.gemini-extension-install.json", {"type": "link", "source": folder})
        # Grok Build: the plugin of 0.5-0.7.6, `cad`, from our repository.
        self.write(".grok/installed-plugins/registry.json", {"repos": {"x": {
            "kind": {"type": "Git", "url": install.URL, "git_ref": ""}, "path": "/x", "plugins": {"cad": {}}}}})
        # Cursor: 0.10-0.11.11's marked plain copy.
        self.write(".cursor/plugins/local/text-to-cad/.text-to-cad-copy", {"from": folder})
        # Loose skills: ours (current and retired, one a link to ours), and someone else's of a retired name.
        self.write(".agents/skills/cad/SKILL.md", OURS.format(name="cad"))
        self.write(".claude/skills/dxf/SKILL.md", OURS_OLD.format(name="dxf"))
        (self.home / ".cursor/skills").mkdir(parents=True)
        (self.home / ".cursor/skills/cad").symlink_to(self.home / ".agents/skills/cad")
        self.write(".codex/skills/urdf/SKILL.md", THEIRS.format(name="urdf"))
        self.write(".agents/.skill-lock.json", {"version": 3, "skills": {
            "cad": {"source": "earthtojake/text-to-cad"}, "urdf": {"source": "someone/robots"},
            "pcb": {"source": "someone/boards"}}})

        done = self.run_install()
        self.assertEqual(0, done.returncode, done.stdout + done.stderr)
        # Ours in first, then the old ones out.
        claude = self.calls("claude")
        self.assertEqual(claude, [["plugin", "marketplace", "update", "earthtojake"],
                                  ["plugin", "install", "text-to-cad@earthtojake"],
                                  ["plugin", "uninstall", "text-to-cad@text-to-cad"],
                                  ["plugin", "marketplace", "remove", "--scope", "user", "text-to-cad"],
                                  ["plugin", "uninstall", "cad@earthtojake"]])
        self.assertEqual(self.calls("codex"), [["plugin", "marketplace", "add", "earthtojake/text-to-cad", "--ref", "latest"],
                                               ["plugin", "add", "text-to-cad@earthtojake"],
                                               ["plugin", "remove", "text-to-cad@text-to-cad"],
                                               ["plugin", "marketplace", "remove", "text-to-cad"]])
        self.assertEqual(self.calls("gemini"), [["extensions", "uninstall", "text-to-cad"],
                                                ["extensions", "install", install.URL, "--ref", "latest", "--consent"]])
        self.assertEqual(self.calls("grok"), [["plugin", "uninstall", "cad"]])
        self.assertFalse((self.home / ".cursor/plugins/local/text-to-cad").exists())
        # Loose skills: ours deleted (the link unlinked), someone else's kept, the lock likewise; never through
        # `npx skills remove`, which removes by name alone.
        self.assertEqual(self.calls("npx"), [])
        self.assertFalse((self.home / ".agents/skills/cad").exists())
        self.assertFalse((self.home / ".claude/skills/dxf").exists())
        self.assertFalse(os.path.lexists(self.home / ".cursor/skills/cad"))
        self.assertTrue((self.home / ".codex/skills/urdf/SKILL.md").is_file())
        self.assertEqual(list(json.loads((self.home / ".agents/.skill-lock.json").read_text(encoding="utf-8"))["skills"]),
                         ["urdf", "pcb"])
        self.assertFalse(os.path.lexists(self.home / ".cursor/plugins/local/text-to-cad"))
        self.assertEqual(sorted(path.name for path in self.home.iterdir() if path.name.startswith(".text-to-cad")), [])
        self.assertIn("Loose skills: removed: 3 old copies of our skills", done.stdout)
        self.assertIn("removed old copies: text-to-cad@text-to-cad, cad@earthtojake", done.stdout)

    def test_claude_desktop_s_old_server_goes_through_a_link_and_no_earlier_copy_is_overwritten(self) -> None:
        self.programs("claude")
        dotfiles = self.root / "dotfiles" / "claude_desktop_config.json"
        dotfiles.parent.mkdir()
        dotfiles.write_text('{\n    "mcpServers": {\n        "cad": {"command": "uvx", "args": ["--from", '
                            '"cad-mcp==0.11.10", "cad-mcp"]},\n        "notes": {"command": "notes-server"}\n    },\n'
                            '    "theme": "dark"\n}\n', encoding="utf-8")
        before = dotfiles.read_text(encoding="utf-8")
        config = self.home / self.desktop()
        config.parent.mkdir(parents=True)
        config.symlink_to(dotfiles)
        earlier = self.write(self.desktop() + ".bak", "an earlier copy\n")
        done = self.run_install()
        self.assertEqual(0, done.returncode, done.stderr)
        # Only our member gone, every other byte as it was, edited where the link points; the link stays a link.
        self.assertTrue(config.is_symlink())
        self.assertEqual(dotfiles.read_text(encoding="utf-8"),
                         '{\n    "mcpServers": {\n        "notes": {"command": "notes-server"}\n    },\n    "theme": "dark"\n}\n')
        self.assertEqual(earlier.read_text(encoding="utf-8"), "an earlier copy\n")
        kept = [path for path in dotfiles.parent.iterdir() if path.name.endswith(".bak")]
        self.assertEqual([path.read_text(encoding="utf-8") for path in kept], [before])
        self.assertIn(f"Claude Desktop: removed: the old cad server in its settings ({kept[0].name} keeps", done.stdout)

    def test_claude_desktop_without_the_claude_command_says_what_to_do_and_runs_nothing(self) -> None:
        self.write(self.desktop(), "{}")
        # The Claude Code Claude Desktop keeps for its Code tab is that app's own: never run.
        build = (self.home / self.desktop()).parent / "claude-code" / "2.1.325" / "485fdac4332e"
        executable = build / ("claude.app/Contents/MacOS/claude" if sys.platform == "darwin" else "claude")
        executable.parent.mkdir(parents=True)
        executable.write_text(STAND_IN.format(python=sys.executable, latest=LATEST), encoding="utf-8")
        executable.chmod(0o755)
        done = self.run_install()
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(self.calls("claude"), [])
        self.assertIn("Claude Desktop: " + install.DESKTOP_NO_CLAUDE + "\n", done.stdout)
        self.assertIn("claude plugin marketplace add earthtojake/text-to-cad#latest, then claude plugin install "
                      "text-to-cad@earthtojake", done.stdout)
        # With the command, Claude Code gets the plugin, and Claude Desktop needs no line.
        self.programs("claude")
        done = self.run_install()
        self.assertEqual(self.calls("claude"), [["plugin", "marketplace", "add", "earthtojake/text-to-cad#latest"],
                                                ["plugin", "install", "text-to-cad@earthtojake"]])
        self.assertNotIn("Claude Desktop:", done.stdout)

    def test_someone_else_s_server_and_folder_of_our_names_are_left(self) -> None:
        desktop = self.write(self.desktop(),
                             json.dumps({"mcpServers": {"cad": {"command": "freecad-mcp"}}}))
        before = desktop.read_text(encoding="utf-8")
        self.write(".cursor/plugins/local/text-to-cad/plugin.json", {"name": "text-to-cad"})
        done = self.run_install()
        self.assertEqual(before, desktop.read_text(encoding="utf-8"))
        self.assertEqual([path.name for path in desktop.parent.iterdir()], [desktop.name])
        self.assertTrue((self.home / ".cursor/plugins/local/text-to-cad/plugin.json").is_file())
        self.assertIn("Cursor: failed: ", done.stdout)
        self.assertIn("holds something else", done.stdout)

    def test_one_app_failing_stops_no_other_and_a_failed_cad_install_fails_the_run(self) -> None:
        self.programs("codex", "gemini")
        done = self.run_install(FAKE_FAIL="codex")
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertIn("Codex: failed: `plugin marketplace` said: codex: something went wrong", done.stdout)
        self.assertIn("Gemini CLI: installed", done.stdout)
        self.no_tools()
        done = self.run_install(FAKE_FAIL="uv:install")
        self.assertEqual(1, done.returncode)
        self.assertIn("cad: failed (uv tool install exit status 1; what uv said is above). Where this ran inside an "
                      "app or an agent's sandbox, run it again in a terminal of your own.", done.stdout)
        self.assertIn("Gemini CLI: installed", done.stdout)
        self.assertIn("cad itself was not installed", done.stdout)
        self.assertEqual(self.calls("cad"), [], "no cad to switch on")

    def test_the_report_cad_s_hand_over_reads_changes_nothing_the_run_says(self) -> None:
        # CAD_INSTALL_REPORT (set by cad's own hand-over, cad_server._internal.install_script): what the run did, each
        # app by its key, written whole; the run's output and exit status as without it, and a report that cannot be
        # written fails nothing.
        self.programs("codex", "gemini")
        self.tools(cad="0.13.0")
        plain = self.run_install(FAKE_FAIL="codex")
        report = self.root / "report.json"
        done = self.run_install(FAKE_FAIL="codex", CAD_INSTALL_REPORT=str(report))
        self.assertEqual((done.returncode, done.stdout, done.stderr), (plain.returncode, plain.stdout, plain.stderr))
        found = json.loads(report.read_text(encoding="utf-8"))
        self.assertEqual({key: found[key] for key in ("schema", "release", "setup")},
                         {"schema": "text-to-cad install report/1", "release": "0.13.0", "setup": 0})
        self.assertEqual(set(found["apps"]), {app.key for app in install.APPS})
        self.assertEqual((found["apps"]["codex"], found["apps"]["gemini"], found["apps"]["claude"]),
                         ("failed", "installed", "not found"))
        self.assertEqual(sorted(path.name for path in self.root.iterdir() if "report" in path.name), ["report.json"])
        self.no_tools()
        done = self.run_install(FAKE_FAIL="uv:install", FAKE_EXIT="3", CAD_INSTALL_REPORT=str(report))
        self.assertEqual((json.loads(report.read_text(encoding="utf-8"))["setup"],
                          json.loads(report.read_text(encoding="utf-8"))["release"]), (3, None))
        self.tools(cad="0.13.0")
        nowhere = self.run_install(FAKE_FAIL="codex", CAD_INSTALL_REPORT=str(self.root / "no folder" / "report.json"))
        self.assertEqual((nowhere.returncode, nowhere.stdout, nowhere.stderr),
                         (plain.returncode, plain.stdout, plain.stderr))

    def test_an_error_no_row_foresaw_is_that_app_s_failure_and_every_other_app_runs(self) -> None:
        def broken(app, here, context):
            raise KeyError("plugins")

        (self.home / ".cline").mkdir()
        apps = (install.App("broken", "Broken App", handler=broken),
                *[app for app in install.APPS if app.key == "cline"])
        said = []
        source = install.Source(skills_dir=self.root / "skills")
        self.write("../skills/cad/SKILL.md", OURS.format(name="cad"))
        report = install.install_apps(install.Here(self.environ()), source, apps, say=said.append)
        self.assertEqual(said[:2], ["Broken App: failed: KeyError: 'plugins'",
                                    "Cline: installed: 1 skills in ~/.cline/skills"])
        self.assertFalse(report.all_failed)
        # The spots a person's file broke before: a git config not in UTF-8, a Grok registry that is a list, a Codex
        # config whose tables are not tables.
        (self.home / "clone/.git").mkdir(parents=True)
        (self.home / "clone/.git/config").write_bytes(b'[remote "origin"]\n\turl = https://x/y\n[user]\n\tname = Jos\xe9\n')
        self.assertEqual(install.git_origin(self.home / "clone"), "https://x/y")
        self.write(".grok/installed-plugins/registry.json", [1, 2])
        self.assertEqual(install.grok_plugins(install.Here(self.environ())), [])
        self.write(".codex/config.toml", 'plugins = "none"\nmarketplaces = 3\n')
        self.programs("codex")
        outcome = install.codex(install.APPS[2], install.Here(self.environ()),
                                install.Context(install.Source()))
        self.assertEqual(outcome.status, "installed")

    def test_it_takes_no_options_and_does_nothing_when_given_one(self) -> None:
        # Old releases' docs piped options to install.sh (`sh -s -- --dry-run`, `--uninstall`, `--add X`).
        done = self.run_install("--uninstall")
        self.assertEqual(2, done.returncode)
        self.assertIn("takes no options", done.stderr)
        script = subprocess.run(["/bin/sh", "-s", "--", "--add", "0.11.11"], input=(INSTALL / "install.sh").read_text(encoding="utf-8"),
                                env=self.environ(PATH=f"{self.bin}:/usr/bin:/bin"), capture_output=True, text=True,
                                timeout=60)
        self.assertEqual(2, script.returncode)
        self.assertIn("takes no options", script.stderr)
        self.assertEqual(self.calls(), [])

    def run_sh(self, **extra: str) -> subprocess.CompletedProcess:
        if self.log.exists():
            self.log.unlink()
        return subprocess.run(["/bin/sh"], input=(INSTALL / "install.sh").read_text(encoding="utf-8"), capture_output=True,
                              text=True, env=self.environ(CAD_INSTALL_PY=str(INSTALL / "install.py"),
                                                          PATH=f"{self.bin}:/usr/bin:/bin", **extra), timeout=60)

    def test_install_sh_runs_install_py_with_uv_s_python(self) -> None:
        self.programs("uv")
        script = self.run_sh()
        self.assertEqual(0, script.returncode, script.stderr)
        run = self.calls("uv")[-1]
        self.assertEqual(run[:-1], ["run", "--no-config", "--managed-python", "--python", "3.14", "--no-project"])
        self.assertEqual(Path(run[-1]).name, "install.py")

    def uvs(self) -> list:
        """Each uv call: the program that ran (its path) and its first word."""
        lines = self.log.read_text(encoding="utf-8").splitlines() if self.log.exists() else []
        return [(Path(call["path"]), call["argv"][0]) for call in map(json.loads, lines) if call["name"] == "uv"]

    def test_install_sh_installs_a_newer_uv_where_uv_is_too_old_for_python_3_14_and_runs_with_it(self) -> None:
        # A uv older than 0.9.0 that cannot update itself (Homebrew's, pip's: no receipt of uv's own installer): uv's
        # own installer runs, as where uv is missing, with nothing added, and the run goes on with the uv it put in
        # its folder (~/.local/bin here), never the old one first on PATH. The person is never asked to update uv.
        self.programs("uv", "curl")
        old, new = self.bin / "uv", self.uv_bin / "uv"
        installer = ('echo "$#" > "$HOME/installer-args"\nmkdir -p "$HOME/.local/bin"\n'
                     f'cp "{old}" "$HOME/.local/bin/uv"\necho "$NEW_UV" > "$HOME/.local/bin/uv-version"\n')
        refused = "uv 0.8.24 is older than 0.9.0, and uv's installer did not install a newer uv (what it said is above)."
        # Its installer could not be downloaded, or put in a uv still too old: one line says so, and nothing runs.
        for extra in ({"FAKE_FAIL": "curl"}, {"NEW_UV": "0.8.30"}):
            script = self.run_sh(FAKE_UV_VERSION="0.8.24", FAKE_UV_INSTALLER=installer, **extra)
            self.assertEqual(1, script.returncode, extra)
            self.assertIn(refused, script.stderr)
            self.assertNotIn("brew", script.stderr)
            self.assertNotIn("run", [word for _path, word in self.uvs()], extra)
        script = self.run_sh(FAKE_UV_VERSION="0.8.24", FAKE_UV_INSTALLER=installer, NEW_UV="0.13.9")
        self.assertEqual(0, script.returncode, script.stderr)
        self.assertIn("uv 0.8.24 is older than 0.9.0, the first that installs Python 3.14: installing a newer uv with "
                      "uv's own installer (https://docs.astral.sh/uv/).", script.stderr)
        self.assertEqual([argv[1] for argv in self.calls("curl")], ["https://astral.sh/uv/install.sh"])
        self.assertEqual((self.home / "installer-args").read_text(encoding="utf-8").strip(), "0")
        self.assertEqual(self.uvs(), [(old, "--version"), (new, "--version"), (new, "run")])
        # uv from its own installer (its receipt) updates itself first; where it is still too old, the installer runs.
        self.write(".config/uv/uv-receipt.json", "{}")
        script = self.run_sh(FAKE_UV_VERSION="0.8.24", FAKE_UV_INSTALLER=installer, NEW_UV="0.13.9")
        self.assertEqual(0, script.returncode, script.stderr)
        self.assertIn("updating it (uv self update)", script.stderr)
        self.assertEqual(self.uvs(), [(old, "--version"), (old, "self"), (old, "--version"), (new, "--version"),
                                      (new, "run")])

    def test_the_development_install_puts_the_checkout_in_place_of_the_published_copy(self) -> None:
        dev_spec = importlib.util.spec_from_file_location("text_to_cad_dev_install", INSTALL / "dev_install.py")
        dev_install = importlib.util.module_from_spec(dev_spec)
        dev_spec.loader.exec_module(dev_install)
        folder = self.root / "dev-plugin" / "text-to-cad"
        release = (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip()
        dev_install.assemble(folder, f"{release}-dev.1")
        self.assertEqual(json.loads((folder / ".claude-plugin/marketplace.json").read_text(encoding="utf-8"))["name"], "earthtojake-dev")
        self.assertEqual(json.loads((folder / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))["version"],
                         f"{release}-dev.1")
        # Codex's server, the one there is, runs the editable tool's cad under a bare command (Codex has dropped,
        # with no error, a server whose command is a path), and keeps its start allowance.
        self.assertEqual(sorted(path.name for path in folder.glob("*mcp*.json")), ["codex.mcp.json"])
        server = json.loads((folder / "codex.mcp.json").read_text(encoding="utf-8"))["mcpServers"]["cad"]
        self.assertEqual((server["command"], server["args"], server["startup_timeout_sec"]), ("cad", ["mcp"], 300))
        # The folder's catalog comes in; then the published copy goes.
        self.programs("claude")
        self.claude_records({"text-to-cad@earthtojake": 1},
                            {"earthtojake": {"source": "github", "repo": "earthtojake/text-to-cad", "ref": "latest"}})
        source = install.Source(folder=folder, catalog=install.DEV_CATALOG, skills_dir=folder / "skills")
        claude = [app for app in install.APPS if app.key == "claude"]
        lines = install.install_apps(install.Here(self.environ()), source, claude, say=lambda line: None)
        self.assertEqual(self.calls("claude"), [["plugin", "marketplace", "add", str(folder)],
                                                ["plugin", "install", "text-to-cad@earthtojake-dev"],
                                                ["plugin", "uninstall", "text-to-cad@earthtojake"],
                                                ["plugin", "marketplace", "remove", "--scope", "user", "earthtojake"]])
        self.assertIn("Claude Code: installed (removed old copies: text-to-cad@earthtojake)", lines)
        # cad: the checkout, an editable uv tool, its automatic updates off; --release puts the published one back.
        with mock.patch.dict(os.environ, self.environ(), clear=True):
            self.assertEqual(dev_install.install_checkout(str(self.bin / "uv")), 0)
            self.assertEqual(self.installs(), [[*install.UV_TOOL_ARGS, "--reinstall-package", "cad", "--editable",
                                                str(REPO_ROOT / "packages" / "cad")]])
            self.assertEqual(self.calls("cad"), [["update", "auto", "off"]])
            self.assertTrue(dev_install.editable(str(self.bin / "uv")))
            self.log.unlink()
            with mock.patch.object(sys, "stdout", new=open(os.devnull, "w", encoding="utf-8")) as quiet:
                self.addCleanup(quiet.close)
                self.assertEqual(dev_install.main(["--release"]), 0)
            self.assertEqual([argv for argv in self.calls("uv") if argv[1] in ("install", "uninstall")],
                             [["tool", "uninstall", "cad"], ["tool", "install", *install.UV_TOOL_ARGS, "cad"]])
            # The install command leaves cad's own automatic updates as they are: --release turns them on again.
            self.assertEqual(self.calls("cad"), [["plugin", "update", "auto", "on"], ["update", "auto", "on"]])
            self.assertFalse(dev_install.editable(str(self.bin / "uv")))

    def test_install_ps1_ends_a_failure_in_a_terminating_error(self) -> None:
        # Not runnable here: the Windows install jobs run it. `powershell -Command "irm ... | iex"` exits 1 only on a
        # terminating error; Write-Error left it at 0 (measured on Windows 11), and `exit` closes a person's window.
        text = (INSTALL / "install.ps1").read_text(encoding="utf-8")
        self.assertRegex(text, r'\nif \(\$LASTEXITCODE\) \{\n    throw "[^"]+"\n\}\n?$')
        code = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
        self.assertNotIn("Write-Error", code)
        self.assertNotRegex(code, r"(?m)^\s*exit\b")
        # Where uv's Python could not be set up (inside an app's package, first time), the person is told what to do.
        self.assertIn("& $uv python find --no-config --system --managed-python 3.14", text)
        self.assertIn("open PowerShell from the Start menu, run the install command there once", text)
        # A uv too old for Python 3.14 that cannot update itself (winget's, pip's): uv's own installer, as install.sh
        # runs it, and the run goes on with the uv it put in its folder; the person is never asked to update uv.
        self.assertIn("$null = Install-Uv\n            $version = $null\n            $uv = Find-InstalledUv", text)
        self.assertNotIn("winget upgrade", text)

    def test_the_installer_names_no_release(self) -> None:
        # Nothing in the install command changes with a release: no fallback, no pin, nothing a release stamps.
        for name in ("install.sh", "install.ps1", "install.py"):
            text = (INSTALL / name).read_text(encoding="utf-8")
            self.assertNotIn("FALLBACK", text, name)
            self.assertNotRegex(text, r"(cad|cad-server|cad-mcp)==[0-9]", name)
            self.assertNotIn("api.texttocad.dev", text, f"{name} reads no version feed")
        for name in ("sync-version.mjs", "check-version.sh"):
            self.assertNotIn("install", (REPO_ROOT / "scripts/release" / name).read_text(encoding="utf-8").replace(
                "installers clone", ""), name)

if __name__ == "__main__":
    unittest.main()
