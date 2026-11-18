#!/usr/bin/env python3
"""The install command run for real on a fresh private computer (``scripts/test/real_computer.py``): its own home,
uv tools and folders, the real command-line programs of Claude Code (``claude``), Codex (``codex``) and Gemini CLI
(``gemini``) each told its configuration folder there, nothing of this machine's home read or written.

The command runs the way a person runs it (macOS and Linux: ``install.sh`` piped to ``sh``; Windows: ``install.ps1``
handed to ``Invoke-Expression`` by Windows PowerShell 5.1), with this tree's ``install.py`` (``CAD_INSTALL_PY``), this
tree's wheels written again as a release no index holds, above PyPI's newest, and offered to uv (``UV_FIND_LINKS``):
uv installs the newest release it is offered, which is that one. The apps are looked for on PATH alone
(``CAD_INSTALL_PATH_ONLY``). The plugin comes from this
tree through each program's own GitHub route: the ``latest`` copy built as Publish Release builds it, in a local
repository the computer's git reads for every address of ours on GitHub. Gemini CLI asks GitHub's API for a release
named ``latest`` before it clones (there is none: it clones); that one request reaches GitHub.

1. install: exit 0 and every line the app phase prints; cad installed as a uv tool at this run's release, its command
   in uv's bin folder; ``cad --version``; cad's automatic updates on (``cad update auto``) and the plugin's turned on
   by the install (``cad plugin update auto``); no server started by the install; each program holds our plugin (``text-to-cad@earthtojake``; Gemini CLI: the extension ``text-to-cad`` from
   GitHub at ``latest``) exactly once, copied from the local repository.
2. cad: ``cad server start``; a box built by ``cad run`` and its page link answering with its token, refused without;
   a file shown by ``cad viewer`` the same way; ``cad doctor`` exit 0.
3. again: the local repository moved on as a release moves it; the command again: cad "installed already" and left
   alone, each app ``updated``, one copy each, the new commit's.
4. migrate: each program left as 0.11.10's installer left it (``<state>/plugin`` made from the v0.11.10 tree by that
   release's own ``plugin.tree``, added as the catalog ``text-to-cad`` and ``text-to-cad@text-to-cad`` installed from
   it; Gemini CLI: the folder linked); the command again: each app ends with the new plugin alone.

Every process it starts is stopped (a process left running fails the run), and the machine's own home is compared
before and after: a change to what an install of ours would touch fails it (on CI, any change). The private computer is
removed unless ``--keep``. A failure prints what the computer holds.

    scripts/test/real-install.py --wheels DIR [--require claude,codex,gemini] [--only claude,codex] [--keep]
                                 [--work DIR] [--uv-cache DIR] [--install-py FILE]

``--wheels``: the folder of this tree's wheels, as ``scripts/release/check-wheel-contents.sh`` keeps them
(``CAD_KEEP_WHEEL=1 CAD_WHEEL_OUT_DIR=DIR``): written again as release ``<major>.<minor>.<9000+n>`` of this tree's
``VERSION`` (``real_computer.stamp``), which no index holds;
without it they are built from the source (``tests/python/support/machine.py``: cad importable, no packaged client,
so a page link is checked for its token alone). A
program missing here is skipped and said, unless ``--require`` names it; ``--only`` leaves the others out. It needs the
tag v0.11.10 in this checkout (without it, the migrate step is skipped and said; on CI it fails), uv, git and a
git checkout of this tree (it stops at once, in one line, without either), and the network (PyPI, uv's Python, the
programs' own vendors). CI runs it on Windows, macOS and Linux (``.github/workflows/real-install.yml``).
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import real_computer as rc  # noqa: E402 - beside it

REPO_ROOT = rc.REPO_ROOT
# This tree as a release no index holds, above every release on PyPI (this tree's major and minor, a patch far above
# a real one: ``real_computer.stamp``), of this run alone.
VERSION = rc.stamp(9000 + os.getpid() % 900)
# The plugin's version, which its manifests carry: the tree's.
PLUGIN_VERSION = (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip()
OLD = "v0.11.10"
CATALOG, OLD_CATALOG, PLUGIN = "earthtojake", "text-to-cad", "text-to-cad"
OURS, OLD_OURS = f"{PLUGIN}@{CATALOG}", f"{PLUGIN}@{OLD_CATALOG}"
# What `cad plugin update auto on` and `status` print, the install command passing it on.
PLUGIN_SWITCH = "plugin update auto: on"
GITHUB = f"https://github.com/{rc.REPOSITORY}"
CI = rc.CI
BOX = '''from cad import model


@model
def box():
    import build123d as bd

    return bd.Box(40, 20, 6)


if __name__ == "__main__":
    box()
'''
STL = ("solid p\nfacet normal 0 0 1\nouter loop\nvertex 0 0 0\nvertex 10 0 0\nvertex 0 10 0\nendloop\nendfacet\n"
       "endsolid p\n")


def say(line: str = "") -> None:
    print(line, flush=True)


def echo(line: str) -> None:
    print(f"  | {line}", flush=True)


def load_installer():
    """``install.py``'s table of apps: the commands it looks for."""
    spec = importlib.util.spec_from_file_location("install_py", REPO_ROOT / "scripts" / "install" / "install.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["install_py"] = module
    spec.loader.exec_module(module)
    return module


class Run:
    """One run on one computer: the programs found, the steps, what each program says it holds."""

    def __init__(self, computer: rc.Computer, wheels: Path, installer: Path) -> None:
        self.computer = computer
        self.wheels = wheels
        self.installer = installer
        self.wheel = next(iter(sorted(wheels.glob(f"cad-{VERSION}-*.whl"))), None)
        if self.wheel is None:
            raise rc.Failed(f"no cad-{VERSION} wheel in {wheels}")
        with zipfile.ZipFile(self.wheel) as wheel:
            self.client = any(name.startswith("cad_server/_runtime/viewer/") for name in wheel.namelist())
        self.cad_path = computer.bin / ("cad.exe" if rc.WINDOWS else "cad")

    @property
    def names(self) -> list[str]:
        return list(self.computer.programs)

    # --- the install script, as a person runs it --------------------------------------------------------------

    def script(self, label: str) -> rc.Ran:
        hooks = {"CAD_INSTALL_PY": str(self.installer), "CAD_INSTALL_PATH_ONLY": "1"}
        if rc.WINDOWS:
            script = REPO_ROOT / "scripts" / "install" / "install.ps1"
            argv = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
                    f"Get-Content -Raw '{script}' | Invoke-Expression"]
            piped = None
        else:
            argv, piped = ["sh"], (REPO_ROOT / "scripts" / "install" / "install.sh").read_bytes()
        say(f"-- the install script ({label})")
        trusted = self.trusted()
        ran = self.computer.run(argv, stdin=piped, extra=hooks, echo=echo)
        # Gemini CLI's --consent records the folder it runs in as trusted: the script's own runs must record none of
        # the person's (the script runs from the computer's folder, as a person's from theirs).
        added = {folder: level for folder, level in self.trusted().items() if trusted.get(folder) != level}
        if any(Path(folder).exists() for folder in added):
            raise rc.Failed(f"the install script ({label}) made Gemini CLI trust a folder of the person's: {added}")
        if ran.code:
            raise rc.Failed(f"the install script ({label}) exited {ran.code}")
        return ran

    def app_lines(self, ran: rc.Ran, label: str, wanted: dict[str, str]) -> None:
        """Every line of the app phase: one per program, matching ``wanted`` (program -> pattern), the count of the
        apps not found, and the closing line; nothing else."""
        lines = ran.lines()
        start = lines.index("Setting up the plugin in each agent app found here:") + 1
        phase = [line for line in lines[start:] if line.strip()]
        expected = {rc.PROGRAMS[name].name: pattern for name, pattern in wanted.items()}
        unexpected, seen = [], set()
        for line in phase:
            app = line.split(":", 1)[0]
            if app in expected and re.fullmatch(expected[app], line):
                seen.add(app)
            elif not (re.fullmatch(r"\d+ other supported apps were not found here\.", line)
                      or line == PLUGIN_SWITCH
                      or line == "Start a new session in each app to use it."):
                unexpected.append(line)
        missing = sorted(set(expected) - seen)
        if unexpected or missing or phase[-1:] != ["Start a new session in each app to use it."]:
            raise rc.Failed(f"the install script ({label}) said what it should not: unexpected {unexpected}, "
                            f"no line for {missing}")
        say(f"ok    the install script ({label}): exit 0, " + "; ".join(line for line in phase
                                                                     if line.split(":", 1)[0] in expected))

    def trusted(self) -> dict:
        """Gemini CLI's trusted folders in the computer (trustedFolders.json)."""
        found = self.computer.home / ".gemini" / "trustedFolders.json"
        return json.loads(found.read_text(encoding="utf-8")) if found.is_file() else {}

    # --- what each program says it holds ----------------------------------------------------------------------

    def listed(self, name: str) -> dict:
        """``{"plugins": ids of ours, "catalogs": catalogs of ours, "copies": folders of ours}``, as the program's
        own list commands say it (Gemini CLI: its extensions named ours, with where each came from)."""
        if name == "claude":
            plugins = parse(self.computer.listing(["claude", "plugin", "list", "--json"]).out)
            catalogs = parse(self.computer.listing(["claude", "plugin", "marketplace", "list", "--json"]).out)
            ours = [entry for entry in plugins if entry.get("id", "").split("@")[0] in (PLUGIN, "cad")]
            mine = [entry for entry in catalogs if entry.get("name") in (CATALOG, OLD_CATALOG, "earthtojake-dev")]
            return {"plugins": sorted(entry["id"] for entry in ours),
                    "catalogs": sorted(entry["name"] for entry in mine),
                    "copies": [Path(entry["installPath"]) for entry in ours if entry.get("installPath")]
                    + [Path(entry["installLocation"]) for entry in mine if entry.get("installLocation")],
                    "said": {"plugins": ours, "catalogs": mine}}
        if name == "codex":
            plugins = parse(self.computer.listing(["codex", "plugin", "list", "--json"]).out).get("installed", [])
            catalogs = parse(self.computer.listing(["codex", "plugin", "marketplace", "list", "--json"]).out)
            ours = [entry for entry in plugins if entry.get("pluginId", "").split("@")[0] in (PLUGIN, "cad")]
            mine = [entry for entry in catalogs.get("marketplaces", [])
                    if entry.get("name") in (CATALOG, OLD_CATALOG, "earthtojake-dev")]
            cache = self.computer.home / ".codex" / "plugins" / "cache"
            return {"plugins": sorted(entry["pluginId"] for entry in ours),
                    "catalogs": sorted(entry["name"] for entry in mine),
                    "copies": [cache / entry["marketplaceName"] / entry["name"] / entry["version"] for entry in ours]
                    + [Path(entry["root"]) for entry in mine if entry.get("root")],
                    "said": {"plugins": ours, "catalogs": mine}}
        said = self.computer.listing(["gemini", "extensions", "list", "--output-format", "json"]).out
        extensions = parse(said) if re.search(r"(?m)^\[", said) else []  # none: "No extensions installed."
        ours = [entry for entry in extensions if entry.get("name") == PLUGIN]
        where = [entry.get("installMetadata") or {} for entry in ours]
        return {"plugins": [f"{PLUGIN} ({found.get('type')} {found.get('source')} {found.get('ref') or ''}".rstrip()
                            + ")" for found in where],
                "catalogs": [], "copies": [Path(entry["path"]) for entry in ours],
                "said": {"extensions": [{key: entry.get(key) for key in ("name", "version", "path", "installMetadata")}
                                        for entry in ours]}}

    def ours_alone(self, label: str, names: list[str] | None = None) -> None:
        """Each program (of ``names``) holds our plugin from GitHub's ``latest`` exactly once, and the copy is this
        run's."""
        for name in self.names if names is None else names:
            held = self.listed(name)
            wanted = ({"plugins": [f"{PLUGIN} (git {GITHUB} latest)"], "catalogs": []} if name == "gemini"
                      else {"plugins": [OURS], "catalogs": [CATALOG]})
            if {key: held[key] for key in wanted} != wanted:
                raise rc.Failed(f"{name} ({label}) holds {held['plugins']}, catalogs {held['catalogs']}, not ours "
                                f"alone: {json.dumps(held['said'], default=str)[:2000]}")
            for folder in held["copies"]:
                skill = folder / "skills" / "cad" / "SKILL.md"
                if not self.computer.local_copy(folder) or not skill.is_file():
                    raise rc.Failed(f"{name} ({label}): {folder} is not this run's copy of the local repository "
                                    f"(its mark: {self.computer.local_copy(folder)}, skills/cad: {skill.is_file()})")
            say(f"ok    {name} ({label}): {', '.join(held['plugins'] + held['catalogs'])}, once; "
                f"{len(held['copies'])} copies, each this run's")

    # --- cad ----------------------------------------------------------------------------------------------------

    def cad(self, *argv, cwd: Path | None = None) -> rc.Ran:
        return self.computer.must([self.cad_path, *argv], cwd=cwd)

    def installed(self, ran: rc.Ran) -> None:
        """What the install command's cad step left (step 1, see the module): cad a uv tool at this run's release, its
        command in uv's bin folder, its environment this run's wheel, both switches on, and no server started."""
        c = self.computer
        if "Installing cad with uv. The first run downloads it, which takes a minute." not in ran.lines():
            raise rc.Failed("the install command did not install cad")
        tool = self.tool()
        if tool is None or tool["version"] != VERSION or not rc._within(Path(tool["env"]), c.uv_tools):
            raise rc.Failed(f"uv lists no cad tool {VERSION} in the computer's tool folder: {tool}")
        if (os.path.realpath(Path(tool["command"]).parent) != os.path.realpath(c.bin)
                or not self.cad_path.exists()):
            raise rc.Failed(f"the cad command is not in uv's bin folder {c.bin}: {tool}")
        with zipfile.ZipFile(self.wheel) as wheel:
            files = {name: wheel.read(name) for name in wheel.namelist()
                     if name.startswith("cad_server/") and name.endswith(".py")}
        site = sorted(Path(tool["env"]).rglob("site-packages/cad_server"))
        differ = [name for name, data in sorted(files.items()) if not site
                  or (site[0].parent / name).read_bytes() != data] if files else ["(none in the wheel)"]
        if differ:
            raise rc.Failed(f"the cad tool's environment is not this run's wheel: {differ[:5]}")
        said = self.cad("--version").lines()[:1]
        if said != [f"cad {VERSION}"]:
            raise rc.Failed(f"cad --version said {said}")
        switches = (self.cad("update", "auto", "status").lines()
                    + self.cad("plugin", "update", "auto", "status").lines())
        if switches[-2:] != ["update auto: on", PLUGIN_SWITCH]:
            raise rc.Failed(f"cad update auto status and cad plugin update auto status said {switches}")
        status = self.cad("server", "status", "--json").out.strip().splitlines()[-1:]
        if status != ["null"]:
            raise rc.Failed(f"the install command started a server: {status}")
        say(f"ok    cad {VERSION}: a uv tool in the computer ({len(files)} modules, the wheel's), its command in uv's "
            "bin folder, cad --version, both switches on, no server started")

    def tool(self) -> dict | None:
        """uv's tool ``cad`` in the computer: its version, its environment, its ``cad`` command; None with none."""
        listed = self.computer.must(["uv", "tool", "list", "--show-paths"]).lines()
        for index, line in enumerate(listed):
            found = re.fullmatch(r"cad v(\S+) \((.+)\)", line.strip())
            if found:
                commands = [re.fullmatch(r"- cad(?:\.exe)? \((.+)\)", entry.strip()) for entry in listed[index + 1:]]
                command = next((match[1] for match in commands if match), "")
                return {"version": found[1], "env": found[2], "command": command}
        return None

    def page(self, link: str, what: str) -> None:
        """``link`` (a page link with its token) answering 200 with the page, and 403 without the token. Wheels built
        from the source carry no packaged client (``--wheels`` not given): there the token alone is checked."""
        try:
            with urllib.request.urlopen(link) as page:
                status, body = page.status, page.read()
        except urllib.error.HTTPError as error:
            status, body = error.code, b""
        try:
            urllib.request.urlopen(link.split("?", 1)[0])
            bare = 200
        except urllib.error.HTTPError as error:
            bare = error.code
        served = status == 200 and b"<html" in body.lower() if self.client else status not in (401, 403)
        if not served or bare != 403:
            raise rc.Failed(f"{what}: the page link answered {status} ({len(body)} bytes), {bare} without its token")

    def cad_works(self) -> None:
        """Step 2 (see the module)."""
        started = self.cad("server", "start").out
        if f"cad {VERSION}" not in started:
            raise rc.Failed(f"cad server start said {started!r}")
        models = self.computer.work / "models" / "box"
        models.mkdir(parents=True, exist_ok=True)
        (models / "box.py").write_text(BOX, encoding="utf-8")
        built = self.computer.must([self.cad_path, "run", "box.py"], cwd=models, echo=echo).out
        if not re.search(r"(?m)^built \S+", built) or not re.search(r"bounds 40\D+20\D+6 mm", built):
            raise rc.Failed(f"cad run box.py built no box:\n{built}")
        link = re.search(r"(?m)^\s*view:\s+(http://\S+\?token=\S+)", built)
        if not link:
            raise rc.Failed(f"cad run box.py printed no view: link with a token:\n{built}")
        self.page(link[1], "cad run box.py")
        say("ok    cad server start; cad run box.py built the box; its page answers 200 with its token, 403 without")
        (models / "part.stl").write_text(STL, encoding="ascii")
        if not self.client:
            say("note  cad viewer not run: these wheels carry no packaged client, which it refuses to start without")
            return self.doctor()
        shown = self.cad("viewer", "part.stl", "--no-open", cwd=models).out
        link = re.search(r"(http://\S+\?token=\S+)", shown)
        if not link:
            raise rc.Failed(f"cad viewer part.stl printed no link with a token:\n{shown}")
        self.page(link[1], "cad viewer part.stl")
        say("ok    cad viewer part.stl: its page answers 200 with its token, 403 without")
        self.doctor()

    def doctor(self) -> None:
        doctor = self.computer.run([self.cad_path, "doctor"])
        if doctor.code:
            raise rc.Failed(f"cad doctor exited {doctor.code}:\n{doctor.out}")
        if f"update auto on, {PLUGIN_SWITCH.replace(':', '')}; a global install by uv " not in doctor.out:
            raise rc.Failed(f"cad doctor does not say both switches are on and cad is a global install by uv:\n"
                            f"{doctor.out}")
        say("ok    cad doctor: exit 0, both switches on, a global install by uv")

    # --- 0.11.10's installer's state ------------------------------------------------------------------------------

    def as_old_installer_left_it(self) -> Path:
        """Ours removed by each program's own commands, then each program as 0.11.10's ``cad setup`` left it (see
        the module): the folder made by that release's own ``plugin.tree`` from its tree. The folder."""
        c = self.computer
        for name in self.names:
            self.remove(name)
        say("ok    each program removed ours with its own commands, and lists nothing of ours")
        module_text = rc.tagged_file(OLD, "packages/cad-server/src/cad_server/_internal/plugin.py")
        module_path = c.work / "old-plugin.py"
        module_path.write_text(module_text, encoding="utf-8")
        spec = importlib.util.spec_from_file_location("old_plugin", module_path)
        old = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(old)
        origin = rc.tagged_tree(OLD, [*old.FILES, "skills"], c.work / "v0.11.10")
        folder = c.state / "plugin"
        for relative, (data, mode) in old.tree(origin, OLD.lstrip("v")).items():
            target = folder / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            if not rc.WINDOWS:
                target.chmod(mode)
        for name in self.names:
            if name == "claude":
                c.must(["claude", "plugin", "marketplace", "add", folder])
                c.must(["claude", "plugin", "install", OLD_OURS])
            elif name == "codex":
                c.must(["codex", "plugin", "marketplace", "add", folder])
                c.must(["codex", "plugin", "add", OLD_OURS])
            else:
                c.must(["gemini", "extensions", "link", folder, "--consent"], stdin=b"y\n")
            held = self.listed(name)
            alone = (len(held["plugins"]) == 1 and held["plugins"][0].startswith(f"{PLUGIN} (link ") if name == "gemini"
                     else (held["plugins"], held["catalogs"]) == ([OLD_OURS], [OLD_CATALOG]))
            if not alone:
                raise rc.Failed(f"{name} does not hold 0.11.10's copy alone: {held['plugins']} {held['catalogs']}")
            say(f"ok    {name} as 0.11.10 left it: {', '.join(held['plugins'] + held['catalogs'])}")
        return folder

    def remove(self, name: str) -> None:
        """Our plugin and catalog removed from program ``name`` by its own commands, where it holds them."""
        c = self.computer
        held = self.listed(name)
        if name == "claude":
            if OURS in held["plugins"]:
                c.must(["claude", "plugin", "uninstall", OURS])
            if CATALOG in held["catalogs"]:
                c.must(["claude", "plugin", "marketplace", "remove", CATALOG])
        elif name == "codex":
            if OURS in held["plugins"]:
                c.must(["codex", "plugin", "remove", OURS])
            if CATALOG in held["catalogs"]:
                c.must(["codex", "plugin", "marketplace", "remove", CATALOG])
        elif held["plugins"]:
            c.must(["gemini", "extensions", "uninstall", PLUGIN])
        held = self.listed(name)
        if held["plugins"] or held["catalogs"]:
            raise rc.Failed(f"{name} still holds {held['plugins']} {held['catalogs']} after its own removal")

    # --- what the computer holds, for a failure ---------------------------------------------------------------

    def report(self) -> str:
        parts = []
        for name in self.names:
            try:
                parts.append(f"{name} lists: {json.dumps(self.listed(name)['said'], default=str)[:4000]}")
            except Exception as error:  # noqa: BLE001 - a failure's report says what it can
                parts.append(f"{name} could not list: {error}")
        state = self.computer.state
        parts.append(f"state {state}: {sorted(os.listdir(state)) if state.is_dir() else '(none)'}")
        try:
            parts.append(f"uv's tools: {self.computer.run(['uv', 'tool', 'list', '--show-paths']).out}")
        except Exception as error:  # noqa: BLE001
            parts.append(f"uv's tools could not be listed: {error}")
        parts.append("processes from the computer's folder:\n" + "\n".join(
            f"{pid} {command}" for pid, command in self.computer.processes()))
        return "\n".join(parts)


def parse(text: str):
    """The JSON a program printed, among whatever else it printed (Gemini CLI writes its list to stderr)."""
    decoder = json.JSONDecoder()
    for match in re.finditer(r"(?m)^[\[{]", text):
        try:
            return decoder.raw_decode(text[match.start():])[0]
        except ValueError:
            continue
    raise rc.Failed(f"no JSON in what the program said:\n{text[:2000]}")


def needs() -> tuple[str | None, bool]:
    """What this run needs of this machine and checkout: git (the computer's apps clone the plugin with it), and this
    tree a git checkout (the plugin's latest copy is built from what git tracks, as Publish Release builds it). The
    one line naming what is missing, else None; and whether the tag v0.11.10 is here (the migrate step builds
    0.11.10's plugin folder from it)."""
    git = shutil.which("git")
    if git is None:
        return ("git is not on PATH: this run needs it (each app clones the plugin with git, and the plugin's latest "
                "copy is built from what git tracks)"), False
    inside = subprocess.run([git, "-C", str(REPO_ROOT), "rev-parse", "--is-inside-work-tree"], capture_output=True,
                            text=True)
    if inside.returncode or inside.stdout.strip() != "true":
        return (f"{REPO_ROOT} is not a git checkout: this run builds the plugin's latest copy from what git tracks "
                "there (clone the repository; an archive of it will not do)"), False
    tag = subprocess.run([git, "-C", str(REPO_ROOT), "rev-parse", "--verify", "--quiet", f"{OLD}^{{commit}}"],
                         capture_output=True)
    return None, tag.returncode == 0


def steps(run: Run, migrate: bool = True) -> None:
    c = run.computer
    commit = c.stand_in(rc.plugin_tree())
    say(f"ok    the local repository: latest at {commit[:12]}, which {GITHUB} names in the computer's git")
    if "gemini" in run.names:
        say("note  Gemini CLI asks api.github.com for a release of ours named latest before it clones (there is "
            "none): that request goes to GitHub; the clone is the local one")

    names = run.names
    ran = run.script("install")
    run.app_lines(ran, "install", {name: rf"{re.escape(rc.PROGRAMS[name].name)}: installed" for name in names})
    run.installed(ran)
    run.ours_alone("install")
    run.cad_works()

    major, minor, patch = PLUGIN_VERSION.split(".")[:3]
    c.advance(PLUGIN_VERSION, f"{major}.{minor}.{int(patch) + 1}")
    ran = run.script("again")
    if f"cad {VERSION} is installed already: it is left as it is, and updates itself." not in ran.lines():
        raise rc.Failed(f"the install command again did not find cad {VERSION} installed already")
    if any(line.startswith("Installing cad") for line in ran.lines()) or run.tool()["version"] != VERSION:
        raise rc.Failed(f"the install command again changed cad: {run.tool()}")
    run.app_lines(ran, "again", {name: rf"{re.escape(rc.PROGRAMS[name].name)}: updated" for name in names})
    run.ours_alone("again")
    say(f"ok    the install command again: cad {VERSION} is installed already, left alone")

    if not migrate:
        say(f"skip  migrate: the tag {OLD} is not in this checkout (git fetch --depth 1 origin tag {OLD})")
        return
    run.as_old_installer_left_it()
    ran = run.script("migrate")
    removed = {"claude": rf"Claude Code: installed \(removed old copies: {re.escape(OLD_OURS)}\)",
               "codex": rf"Codex: installed \(removed old copies: {re.escape(OLD_OURS)}\)",
               "gemini": r"Gemini CLI: updated \(removed old copies: text-to-cad linked to .+\)"}
    run.app_lines(ran, "migrate", {name: removed[name] for name in names})
    run.ours_alone("migrate")
    say(f"note  0.11.10's folder after the migration: {'still there' if (c.state / 'plugin').exists() else 'gone'}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--wheels", type=Path, help="the folder of this tree's wheels (default: built from the "
                        "source, with no packaged client: tests/python/support/machine.py)")
    parser.add_argument("--require", default="", help="programs that must be here, comma-separated")
    parser.add_argument("--only", default="", help="run with these programs alone, comma-separated")
    parser.add_argument("--uv-cache", type=Path, help="uv's cache and Pythons for the computer (default: its own)")
    parser.add_argument("--keep", action="store_true", help="keep the private computer")
    parser.add_argument("--work", type=Path, help="the private computer's folder (default: a new temporary one)")
    parser.add_argument("--install-py", type=Path, default=REPO_ROOT / "scripts" / "install" / "install.py",
                        help="the install.py the script runs (default: this tree's)")
    args = parser.parse_args(argv)
    # What a program said is printed as it was read: a character this output's encoding has not (Windows' code
    # page) is printed escaped, never raised.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="backslashreplace")
        except (AttributeError, ValueError):
            pass
    required = [name for name in args.require.split(",") if name]
    only = [name for name in args.only.split(",") if name]
    unknown = [name for name in required + only if name not in rc.PROGRAMS]
    if unknown:
        parser.error(f"unknown programs {unknown}: {', '.join(rc.PROGRAMS)}")
    programs = {}
    for name, program in rc.PROGRAMS.items():
        if only and name not in only:
            say(f"skip  {name}: not asked for (--only)")
            continue
        found = program.path()
        if found:
            programs[name] = found
            say(f"found {name}: {found}")
        elif name in required:
            say(f"FAILED  {name} is required and not on PATH")
            return 1
        else:
            say(f"skip  {name}: not on PATH")
    if not programs:
        say("FAILED  none of the programs is here")
        return 1
    if not shutil.which("uv"):
        say("FAILED  uv is not on PATH")
        return 1
    missing, tagged = needs()
    if missing:
        say(f"FAILED  {missing}")
        return 1
    if not tagged and CI:
        say(f"FAILED  the tag {OLD} is not in this checkout, and CI runs every step: git fetch --depth 1 origin tag {OLD}")
        return 1

    work = (args.work or Path(tempfile.mkdtemp(prefix="real-install-"))).resolve()
    work.mkdir(parents=True, exist_ok=True)
    needles = (PLUGIN, CATALOG, str(work))
    before = rc.RealHome.here(list(rc.PROGRAMS), needles)
    sentinels = rc.Sentinels.here()
    feed = rc.Feed(VERSION)
    wheels = work / "wheels"
    if args.wheels is None:
        sys.path.insert(0, str(REPO_ROOT))
        from tests.python.support.machine import release  # noqa: PLC0415 - the source tree's wheels

        built = work / "built"
        built.mkdir(parents=True, exist_ok=True)
        release(VERSION, built)
        # Its kernel's extra as the library declares it (the source's wheel names nothing there).
        import tomllib  # noqa: PLC0415

        project = tomllib.loads((REPO_ROOT / "packages" / "cad" / "pyproject.toml").read_text(encoding="utf-8"))
        kernel = [f'{line}; extra == "build123d"' for line in project["project"]["optional-dependencies"]["build123d"]]
        for wheel in built.glob("*.whl"):
            rc.rewrite(wheel, wheels, VERSION, requires=kernel if wheel.name.startswith("cad-") else None)
        say("note  no --wheels: this tree's wheels built from the source, with no packaged client (the pages' "
            "links are checked for their token alone)")
    else:
        rc.publish(args.wheels.resolve(), VERSION, wheels)
    computer = rc.Computer(work, programs, feed=feed, wheels=wheels,
                           shared=args.uv_cache.resolve() if args.uv_cache else None)
    say(f"real-install: cad {VERSION} (this tree's wheels written again) into {computer.work}; "
        + ", ".join(f"{name} {program_version(computer, name)}" for name in programs))
    failed = ""
    began = time.monotonic()
    try:
        computer.isolation(say)
    except rc.Failed as failure:
        say(f"FAILED  {failure}")
        feed.close()
        return 1
    run = Run(computer, wheels, args.install_py.resolve())
    try:
        installer = load_installer()
        computer.check_path([app.command for app in installer.APPS if app.command] + ["cursor-agent"])
        steps(run, migrate=tagged)
    except (rc.Failed, OSError, ValueError, KeyError) as failure:
        failed = f"{type(failure).__name__}: {failure}" if not isinstance(failure, rc.Failed) else str(failure)
    if failed:
        say(f"FAILED  {failed}")
        say("-- what the computer holds")
        say(run.report())
    left = computer.stop(run.cad_path)
    feed.close()
    if left:
        failed = failed or "processes were left running"
        say("FAILED  left running, now ended:\n" + "\n".join(left))
    elif not computer.looked:
        say("note  this system did not let the run list its processes: whether anything was left running is not "
            "known")
    else:
        say("ok    nothing of the computer's is left running")
    moved = sentinels.moved(rc.Sentinels.here())
    if moved:
        failed = failed or "the machine's own files moved"
        say("FAILED  the machine's own files moved:\n" + "\n".join(moved))
    strict, other = before.changes(rc.RealHome.here(list(rc.PROGRAMS), needles))
    if strict or (CI and other):
        failed = failed or "the machine's own home changed"
        say("FAILED  the machine's own home changed:\n" + "\n".join(strict + (other if CI else [])))
    else:
        say(f"ok    the machine's own home: nothing of ours changed ({len(before.listing)} entries listed)"
            + (f"; {len(other)} other entries changed by what else runs here: {', '.join(other[:8])}" if other else ""))
    if args.keep:
        say(f"kept  {computer.work}")
    else:
        computer.remove()
    say(f"real-install: {'FAILED' if failed else 'held'} ({time.monotonic() - began:.0f} s)")
    return 1 if failed else 0


def program_version(computer: rc.Computer, name: str) -> str:
    ran = computer.run([name, "--version"])
    return ran.lines()[-1].strip() if ran.code == 0 and ran.lines() else f"(--version exited {ran.code})"


if __name__ == "__main__":
    raise SystemExit(main())
