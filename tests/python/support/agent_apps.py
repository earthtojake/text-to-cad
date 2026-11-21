"""A computer with agent apps on it, for a test: a fresh temporary home (HOME, XDG_*, APPDATA) and stand-in programs
on PATH -- the agent apps' CLIs, git, uv, pipx, curl, a ``cad`` -- that record how they were called and change nothing
else (git clone writes a small copy of the plugin; gemini's uninstall removes its extension's folder; uv's tool
install records the tool in a file of the test's and writes a stand-in ``cad`` in the home's ~/.local/bin). No real
app, network, uv or cad runs: PATH holds only the stand-ins, the app table is told not to search Homebrew's or npm's
folders or app bundles (``CAD_INSTALL_PATH_ONLY``), and every proxy is a closed port.

``AgentApps`` is the test case the install command's tests and the tests of cad's own table of apps
(``cad_server.plugin``) both stand on; ``PluginRuns`` adds the ``cad plugin`` command run on that computer. A test
case of another kind that can reach that command's code (one mock, or one change of its parser, away from a run of it)
stands on ``a_home_of_its_own``: no test may be one mistake away from the agent apps of the computer it runs on.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import textwrap
import types
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

LATEST = "a" * 40  # the commit of `latest`, as the stand-in git names it
# How Codex adds our catalog: from GitHub at `latest`, checking out only what its plugin needs.
CODEX_ADD = ["plugin", "marketplace", "add", "earthtojake/text-to-cad", "--ref", "latest", "--sparse", ".claude-plugin",
             "--sparse", ".codex-plugin", "--sparse", "skills", "--sparse", "codex.mcp.json"]
OURS = "---\nname: {name}\ndescription: x\nmetadata:\n  repository: earthtojake/text-to-cad\n---\n"
# A skill of 0.5.0-0.8.4: no metadata, our provenance line in its body.
OURS_OLD = ("---\nname: {name}\ndescription: x\nlicense: MIT\n---\n\n# X\n\n"
            "Provenance: maintained in [earthtojake/text-to-cad](https://github.com/earthtojake/text-to-cad).\n")
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
# writes its record; `copilot plugin` keeps its catalogs in ~/.copilot/settings.json and its plugins in
# ~/.copilot/config.json as Copilot CLI does, its `marketplace add` failing for a catalog it has already, `install`
# for one it has not, and `update` for a plugin not installed (as 1.0.114 does); with FAKE_SIGNED_OUT, `devin plugins`
# refuses as Devin CLI does with nobody signed in. Each call notes its folder and Gemini's trust.
#
# For the install command: each call also notes the variables FAKE_LOG_ENV names and whether the file FAKE_LOG_EXISTS
# names is there. `cad update` says a line on each stream and the lines FAKE_UPDATE_SAID names (split at `|`), waits
# FAKE_UPDATE_SLEEP seconds, makes the tool FAKE_CAD_UPDATES (uv's record of it, else pipx's) and exits
# FAKE_UPDATE_EXIT. `cad plugin install`, and `uv tool run ... plugin install`
# (the newest cad's), says a line on each stream, writes FAKE_PLUGIN_APPS as the report CAD_PLUGIN_REPORT names (no
# report without it, nor from a cad with no such command: exit 2) and exits FAKE_PLUGIN_EXIT_CAD, or
# FAKE_PLUGIN_EXIT_UV. `cad plugin install --help` exits FAKE_PLUGIN_HELP_CAD, else 2 (argparse's usage error, on
# stderr) where FAKE_PLUGIN_EXIT_CAD is 2, a cad with no such command, else 0. With FAKE_UV_RUNS, `uv run <script>` runs
# the script (this Python, UV naming the stand-in). `curl <url>/install.py -o <file>` writes the file FAKE_INSTALL_PY
# names, and `curl -d <body> <url>` posts the body to a loopback address, as curl would.
STAND_IN = textwrap.dedent('''\
    #!{python}
    import json, os, shutil, sys
    from pathlib import Path
    name = Path(sys.argv[0]).name
    with open(os.environ["FAKE_LOG"], "a", encoding="utf-8") as log:
        log.write(json.dumps({{"name": name, "argv": sys.argv[1:], "cwd": os.getcwd(), "path": sys.argv[0],
                               "trust": os.environ.get("GEMINI_CLI_TRUST_WORKSPACE"),
                               "env": {{key: os.environ.get(key) for key in os.environ.get("FAKE_LOG_ENV", "").split(",")
                                       if key}},
                               "exists": os.path.exists(os.environ.get("FAKE_LOG_EXISTS") or os.devnull + "/none")}})
                  + "\\n")
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
    if name == "curl" and "-d" in sys.argv:
        if sys.argv[-1].startswith("http://127.0.0.1:"):
            import urllib.request
            sent = urllib.request.Request(sys.argv[-1], data=sys.argv[sys.argv.index("-d") + 1].encode(), method="POST",
                                          headers=dict([sys.argv[sys.argv.index("-H") + 1].split(": ", 1)]))
            urllib.request.build_opener(urllib.request.ProxyHandler({{}})).open(sent, timeout=10).close()
    elif name == "curl" and "-o" in sys.argv:
        hosted = os.environ.get("FAKE_INSTALL_PY") if any(word.endswith("/install.py") for word in sys.argv) else None
        Path(sys.argv[sys.argv.index("-o") + 1]).write_text(
            Path(hosted).read_text(encoding="utf-8") if hosted else os.environ.get("FAKE_UV_INSTALLER", "exit 1\\n"),
            encoding="utf-8")
    if name == "uv" and sys.argv[1:2] == ["run"] and os.environ.get("FAKE_UV_RUNS"):
        import subprocess
        sys.exit(subprocess.call([sys.executable, sys.argv[-1]], env={{**os.environ, "UV": sys.argv[0]}}))
    if name == "cad" and sys.argv[1:] == ["plugin", "install", "--help"]:
        missing = os.environ.get("FAKE_PLUGIN_EXIT_CAD") == "2"
        code = int(os.environ.get("FAKE_PLUGIN_HELP_CAD") or (2 if missing else 0))
        if code == 2:
            print("usage: cad plugin [-h] {{update}} ...", file=sys.stderr)
            print("cad plugin: error: argument {{update}}: invalid choice: 'install' (choose from 'update')",
                  file=sys.stderr)
        else:
            print("usage: cad plugin install [-h]")
        sys.exit(code)
    if sys.argv[-2:] == ["plugin", "install"] and (name == "cad" or (name == "uv" and sys.argv[1:3] == ["tool", "run"])):
        print(f"{{name}} (stand-in): the plugin, on stdout", flush=True)
        print(f"{{name}} (stand-in): the plugin, on stderr", file=sys.stderr, flush=True)
        code = int(os.environ.get(f"FAKE_PLUGIN_EXIT_{{name.upper()}}", "0"))
        if os.environ.get("FAKE_PLUGIN_APPS") and os.environ.get("CAD_PLUGIN_REPORT") and code != 2:
            Path(os.environ["CAD_PLUGIN_REPORT"]).write_text(json.dumps(
                {{"schema": "cad plugin install/1", "apps": json.loads(os.environ["FAKE_PLUGIN_APPS"])}}), encoding="utf-8")
        sys.exit(code)
    if name == "cad" and sys.argv[1:] == ["update"]:
        import time
        print("cad (stand-in): update", flush=True)
        print("cad (stand-in): update, on stderr", file=sys.stderr, flush=True)
        for said in filter(None, os.environ.get("FAKE_UPDATE_SAID", "").split("|")):
            print(said, flush=True)
        time.sleep(float(os.environ.get("FAKE_UPDATE_SLEEP", "0")))
        state = Path(os.environ["FAKE_UV_STATE"])
        tools = json.loads(state.read_text()) if state.exists() else {{}}
        if os.environ.get("FAKE_CAD_UPDATES") and "cad" in tools:
            state.write_text(json.dumps({{**tools, "cad": os.environ["FAKE_CAD_UPDATES"]}}))
        elif os.environ.get("FAKE_CAD_UPDATES"):
            metadata = Path(os.environ["FAKE_PIPX_VENVS"]) / "cad" / "pipx_metadata.json"
            found = json.loads(metadata.read_text())
            found["main_package"]["package_version"] = os.environ["FAKE_CAD_UPDATES"]
            metadata.write_text(json.dumps(found))
        sys.exit(int(os.environ.get("FAKE_UPDATE_EXIT", "0")))
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
    if name == "devin" and sys.argv[1:2] == ["plugins"] and os.environ.get("FAKE_SIGNED_OUT"):
        print("Error: You must be logged in to manage plugins. Run `devin auth login` first.")
        sys.exit(1)
    if name == "copilot" and sys.argv[1:2] == ["plugin"]:
        home = Path(os.environ["HOME"]) / ".copilot"
        settings, config = home / "settings.json", home / "config.json"
        known = json.loads(settings.read_text()) if settings.exists() else {{}}
        installed = json.loads(config.read_text()) if config.exists() else {{"installedPlugins": []}}
        catalogs = known.setdefault("extraKnownMarketplaces", {{}})
        home.mkdir(parents=True, exist_ok=True)
        if sys.argv[2:4] == ["marketplace", "add"]:
            repo, _, ref = sys.argv[4].partition("#")
            if "earthtojake" in catalogs:
                print('Failed to add marketplace: Marketplace "earthtojake" already registered')
                sys.exit(1)
            catalogs["earthtojake"] = {{"source": {{"source": "github", "repo": repo, **({{"ref": ref}} if ref else {{}})}}}}
            settings.write_text(json.dumps(known))
        elif sys.argv[2] == "install":
            plugin, _, catalog = sys.argv[3].partition("@")
            if catalog not in catalogs:
                print(f'Failed to install plugin: Marketplace "{{catalog}}" not found')
                sys.exit(1)
            installed["installedPlugins"].append({{"name": plugin, "marketplace": catalog}})
            config.write_text(json.dumps(installed))
        elif sys.argv[2] == "update":
            if not any(entry["name"] == sys.argv[3] for entry in installed["installedPlugins"]):
                print(f'Failed to update plugin: Plugin "{{sys.argv[3]}}" is not installed')
                sys.exit(1)
    if name == "git" and "clone" in sys.argv:
        target = Path(sys.argv[-1])
        (target / ".git").mkdir(parents=True)
        (target / ".git" / "config").write_text('[remote "origin"]\\n\\turl = ' + sys.argv[-2] + "\\n")
        for skill in ("cad", "pcb"):
            (target / "skills" / skill).mkdir(parents=True)
            (target / "skills" / skill / "SKILL.md").write_text(
                f"---\\nname: {{skill}}\\nmetadata:\\n  repository: earthtojake/text-to-cad\\n---\\nnew\\n")
''')


# Where an agent app, or what installs one, says its folder is: none of them names this computer's in a test.
ELSEWHERE = ("CLAUDE_CONFIG_DIR", "CODEX_HOME", "GEMINI_CLI_HOME", "HERMES_HOME", "NPM_CONFIG_PREFIX",
             "npm_config_prefix")


def a_home_of_its_own(case: unittest.TestCase, home: Path, path: Path) -> None:
    """This process's environment, for the rest of ``case``, that of a computer with no agent app on it: ``home``, a
    folder of the test's, as HOME and USERPROFILE, with the XDG folders and Windows' two inside it; PATH the folder
    ``path`` alone (the test's stand-ins); the table of apps told to look nowhere but PATH
    (``CAD_INSTALL_PATH_ONLY``, and Codex's command by its name); and no variable left that names an app's folder
    elsewhere (``ELSEWHERE``). What
    ``AgentApps.environ`` gives a run, for a test case that changes this process's environment and keeps the rest of
    it."""
    home.mkdir(parents=True, exist_ok=True)
    own = mock.patch.dict(os.environ, {
        "HOME": str(home), "USERPROFILE": str(home), "PATH": str(path), "CAD_INSTALL_PATH_ONLY": "1",
        "XDG_CONFIG_HOME": str(home / ".config"), "XDG_STATE_HOME": str(home / ".local" / "state"),
        "APPDATA": str(home / "AppData" / "Roaming"), "LOCALAPPDATA": str(home / "AppData" / "Local"),
        "CODEX_CLI": "codex"})
    own.start()
    case.addCleanup(own.stop)  # the whole environment as it was, what is taken out below too
    for name in ELSEWHERE:
        os.environ.pop(name, None)


class AgentApps(unittest.TestCase):
    """A fresh home with stand-in programs on PATH (see the module). ``PROGRAMS``: the stand-ins every test of the
    class starts with."""

    PROGRAMS: tuple = ("git",)

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
        self.programs(*self.PROGRAMS)

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

    def forget_calls(self) -> None:
        if self.log.exists():
            self.log.unlink()

    def calls(self, name: str = None) -> list:
        lines = self.log.read_text(encoding="utf-8").splitlines() if self.log.exists() else []
        found = [json.loads(line) for line in lines]
        return [call["argv"] for call in found if name is None or call["name"] == name]

    def claude_records(self, plugins: dict, catalogs: dict) -> None:
        self.write(".claude/plugins/installed_plugins.json",
                   {"version": 2, "plugins": {key: [{"scope": "user"}] for key in plugins}})
        self.write(".claude/plugins/known_marketplaces.json", {name: {"source": source} for name, source in catalogs.items()})


# ``cad <argv>`` in a process of its own, as the cad of the environment named first: a global install's.
AS_THE_TOOL = ("import sys\nsys.prefix = sys.argv.pop(1)\nfrom cad_server.cli import main\n"
               "sys.exit(main(sys.argv[1:]))\n")


class PluginRuns(AgentApps):
    """``cad plugin`` run on that computer (``cad_plugin``, in this process, its environment the computer's alone;
    ``child``, a process of its own): cad's state folder is the home's, and its engine folder one where no server
    runs, so the command keeps its switch and its record itself, there. The cad that runs is that computer's global
    install (``tool``, a uv tool's environment as uv's receipt says one), the one whose release a run keeps;
    ``from_elsewhere`` is a cad that is not."""

    def setUp(self) -> None:
        super().setUp()
        self.tool = self.root / "tools" / "cad"
        self.tool.mkdir(parents=True)
        (self.tool / "uv-receipt.toml").write_text('[tool]\nrequirements = [{ name = "cad" }]\n', encoding="utf-8")
        installed = mock.patch.object(sys, "prefix", str(self.tool))
        installed.start()
        self.addCleanup(installed.stop)
        # A short path of its own: a server's door is a socket, whose path has a limit.
        self.engine = Path(tempfile.mkdtemp(prefix="eng-", dir="/tmp" if os.name != "nt" else None))
        self.addCleanup(shutil.rmtree, self.engine, ignore_errors=True)
        # In this process the closed proxies of ``environ`` are not enough: urllib keeps the proxies it first saw.
        offline = mock.patch("urllib.request.urlopen", side_effect=urllib.error.URLError("no network in a test"))
        offline.start()
        self.addCleanup(offline.stop)

    def environ(self, **extra: str) -> dict:
        return super().environ(**{"CAD_STATE_DIR": str(self.state), "CAD_ENGINE_DIR": str(self.engine), **extra})

    @contextlib.contextmanager
    def on_this_computer(self, **extra: str):
        """This process's environment the computer's alone (``environ``), and what it prints kept: yields its output
        and its error output, each an ``io.StringIO``."""
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.dict(os.environ, self.environ(**extra), clear=True), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            yield out, err

    def cad_plugin(self, *argv: str, **extra: str) -> types.SimpleNamespace:
        """``cad plugin <argv>`` run here: its ``returncode``, ``stdout`` and ``stderr``."""
        from cad_server.cli import plugin as command

        self.forget_calls()
        with self.on_this_computer(**extra) as (out, err):
            try:
                code = command.main(list(argv))
            except SystemExit as leaving:
                code = leaving.code
        return types.SimpleNamespace(returncode=code, stdout=out.getvalue(), stderr=err.getvalue())

    def run_install(self, **extra: str) -> types.SimpleNamespace:
        return self.cad_plugin("install", **extra)

    def child(self, *argv: str, **extra: str) -> tuple:
        """The command line of ``cad plugin <argv>`` as a process of its own, and its environment: this computer's,
        with the path this process imports cad by."""
        return ([sys.executable, "-c", AS_THE_TOOL, str(self.tool), "plugin", *argv],
                self.environ(**{"PYTHONPATH": os.pathsep.join(entry for entry in sys.path if entry), **extra}))

    def from_elsewhere(self):
        """For the ``with``, the cad that runs in this process is no global install: one run from uv's cache, a
        project's, a checkout's."""
        return mock.patch.object(sys, "prefix", str(self.root))

    def kept(self) -> dict:
        """What cad keeps of the plugin: ``switch``, whether ``cad plugin update auto`` is on, and ``record``, its
        record (``{}`` where there is none)."""
        def read(name: str) -> dict:
            try:
                return json.loads((self.state / name).read_text(encoding="utf-8"))
            except OSError:
                return {}

        return {"switch": read("settings.json").get("plugin", {}).get("auto_update") is True,
                "record": read("install-command.json")}

    def keep(self, **record) -> None:
        """cad's record of the plugin, written as ``record``."""
        self.state.mkdir(parents=True, exist_ok=True)
        (self.state / "install-command.json").write_text(json.dumps(record), encoding="utf-8")

    @contextlib.contextmanager
    def another_run(self):
        """The lock of a run of ``cad plugin install`` or ``cad plugin update``, held for the ``with`` as another run
        holds it. A run in this process takes it as that run's without trying for it a while first
        (``plugin_catch_up.SETTLE_SECONDS``); one in a process of its own tries as long as any run does."""
        from cad_server._internal import file_lock, plugin_catch_up

        self.state.mkdir(parents=True, exist_ok=True)
        with file_lock.exclusive(self.state / plugin_catch_up.LOCK), \
                mock.patch.object(plugin_catch_up, "SETTLE_SECONDS", 0.0):
            yield
