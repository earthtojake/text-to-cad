#!/usr/bin/env python3
"""The install script run for real, against the real command-line programs of Claude Code (``claude``), Codex
(``codex``) and Gemini CLI (``gemini``), on a private computer (``scripts/test/real_computer.py``): its own home and
folders, each program told its configuration folder there, nothing of this machine's home read or written.

The script runs the way a person runs it (macOS and Linux: ``install.sh`` piped to ``sh``; Windows: ``install.ps1``
handed to ``Invoke-Expression`` by Windows PowerShell 5.1), with this tree's ``install.py`` and ``cad setup`` from this
tree's wheel (the install workflows' hooks, ``CAD_INSTALL_PY``, ``CAD_INSTALL_FROM``, ``UV_FIND_LINKS``), the version
feed a local stand-in, and the apps looked for on PATH alone (``CAD_INSTALL_PATH_ONLY``). The plugin comes from this
tree through each program's own GitHub route: the ``latest`` copy built as Publish Release builds it, in a local
repository the computer's git reads for every address of ours on GitHub. Gemini CLI asks GitHub's API for a release
named ``latest`` before it clones (there is none: it clones); that one request reaches GitHub.

1. install: exit 0 and every line the app phase prints (and, at each run, Gemini CLI trusting no folder of the
   person's); each program, asked by its own list command, holds our plugin (``text-to-cad@earthtojake``; Gemini CLI:
   the extension ``text-to-cad`` from GitHub at ``latest``) exactly once, copied from the local repository (the copy
   carries this run's mark and the skills' pins of this release); the cad this tree's wheel installed; ``cad
   --version`` and ``cad +<release> --version``; a box built by ``cad +<release> run`` and its page link answering
   with its token, refused without.
2. again: the local repository moved on as a release moves it (a commit whose manifests name the next version); the
   script again: exit 0, each app ``updated``, one copy each, the new commit's.
3. migrate: our plugin removed by each program's own commands, then each program left as 0.11.10's installer left it
   (``<state>/plugin`` made from the v0.11.10 tree by that release's own ``plugin.tree``, added as the catalog
   ``text-to-cad`` and ``text-to-cad@text-to-cad`` installed from it; Gemini CLI: the folder linked); the script
   again: each app ends with the new plugin alone, never neither, never both.

Every process it starts is stopped (a process left running fails the run), and the machine's own home is compared
before and after: a change to what an install of ours would touch fails it (on CI, any change). The private computer is
removed unless ``--keep``. A failure prints what the computer holds.

    scripts/test/real-install.py --wheels DIR [--require claude,codex,gemini] [--keep] [--work DIR] [--install-py FILE]

``--wheels``: the folder of this tree's wheels, as ``scripts/release/check-wheel-contents.sh`` keeps them
(``CAD_KEEP_WHEEL=1 CAD_WHEEL_OUT_DIR=DIR``). A program missing here is skipped and said, unless ``--require`` names
it. It needs the tag v0.11.10 in this checkout, uv, git, and the network (PyPI, uv's Python, the programs' own vendors).
CI runs it on Windows, macOS and Linux (``.github/workflows/real-install.yml``).
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
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
VERSION = (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip()
OLD = "v0.11.10"
CATALOG, OLD_CATALOG, PLUGIN = "earthtojake", "text-to-cad", "text-to-cad"
OURS, OLD_OURS = f"{PLUGIN}@{CATALOG}", f"{PLUGIN}@{OLD_CATALOG}"
GITHUB = f"https://github.com/{rc.REPOSITORY}"
CI = bool(os.environ.get("GITHUB_ACTIONS"))
BOX = '''from cad import model


@model
def box():
    import build123d as bd

    return bd.Box(40, 20, 6)


if __name__ == "__main__":
    box()
'''


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
        self.server_wheel = next(iter(sorted(wheels.glob(f"cad_server-{VERSION}-*.whl"))), None)
        if self.server_wheel is None:
            raise rc.Failed(f"no cad_server-{VERSION} wheel in {wheels}")
        bin_folder = computer.home / ".local" / "bin"
        self.cad = bin_folder / ("cad.exe" if rc.WINDOWS else "cad")

    @property
    def names(self) -> list[str]:
        return list(self.computer.programs)

    # --- the install script, as a person runs it --------------------------------------------------------------

    def script(self, label: str) -> rc.Ran:
        hooks = {"CAD_INSTALL_PY": str(self.installer),
                 "CAD_INSTALL_FROM": str(self.server_wheel), "UV_FIND_LINKS": str(self.wheels),
                 "CAD_INSTALL_PATH_ONLY": "1"}
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
        lines = ran.lines()
        if f"Installing text-to-cad {VERSION}. The first run downloads it, which takes a minute." not in lines:
            raise rc.Failed(f"the install script ({label}) did not install {VERSION}")
        if any("cad setup: failed" in line for line in lines):
            raise rc.Failed(f"cad setup failed ({label})")
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

    def ours_alone(self, label: str) -> None:
        """Each program holds our plugin from GitHub's ``latest`` exactly once, and the copy is this run's."""
        for name in self.names:
            held = self.listed(name)
            wanted = ({"plugins": [f"{PLUGIN} (git {GITHUB} latest)"], "catalogs": []} if name == "gemini"
                      else {"plugins": [OURS], "catalogs": [CATALOG]})
            if {key: held[key] for key in wanted} != wanted:
                raise rc.Failed(f"{name} ({label}) holds {held['plugins']}, catalogs {held['catalogs']}, not ours "
                                f"alone: {json.dumps(held['said'], default=str)[:2000]}")
            for folder in held["copies"]:
                skill = folder / "skills" / "cad" / "SKILL.md"
                pinned = skill.is_file() and f"cad +{VERSION} " in skill.read_text(encoding="utf-8", errors="replace")
                if not self.computer.local_copy(folder) or not pinned:
                    raise rc.Failed(f"{name} ({label}): {folder} is not this run's copy of the local repository "
                                    f"(its mark: {self.computer.local_copy(folder)}, the pin cad +{VERSION}: {pinned})")
            say(f"ok    {name} ({label}): {', '.join(held['plugins'] + held['catalogs'])}, once; "
                f"{len(held['copies'])} copies, each this run's")

    # --- cad ----------------------------------------------------------------------------------------------------

    def cad_works(self) -> None:
        """The server installed is this tree's wheel (every file of its package there, the same bytes: the wheel, not
        the checkout, which Windows checks out with other line ends); the command with and without a pin; a box built
        and its page answering."""
        server = self.computer.state / "versions" / VERSION / "code" / "server"
        servers = sorted(server.rglob("site-packages/cad_server"))
        with zipfile.ZipFile(self.server_wheel) as wheel:
            files = {name: wheel.read(name) for name in wheel.namelist()
                     if name.startswith("cad_server/") and not name.endswith("/")}
        installed = servers[0].parent if servers else None
        differ = [name for name, data in sorted(files.items())
                  if installed is None or not (installed / name).is_file() or (installed / name).read_bytes() != data]
        if not servers or not files or differ:
            raise rc.Failed(f"the server installed is not the wheel's: {servers[:1]}, {len(files)} files in the wheel, "
                            f"missing or differing {differ[:5]}")
        for argv in ([self.cad, "--version"], [self.cad, f"+{VERSION}", "--version"]):
            said = self.computer.must(argv).lines()[:1]
            if said != [f"cad {VERSION}"]:
                raise rc.Failed(f"{' '.join(map(str, argv[1:]))} said {said}")
        say(f"ok    cad --version and cad +{VERSION} --version: cad {VERSION}; the server is the wheel's "
            f"({len(files)} files, each the same)")
        models = self.computer.work / "models" / "box"
        models.mkdir(parents=True, exist_ok=True)
        (models / "box.py").write_text(BOX, encoding="utf-8")
        built = self.computer.must([self.cad, f"+{VERSION}", "run", "box.py"], cwd=models, echo=echo).out
        if not re.search(r"(?m)^built \S+", built) or not re.search(r"bounds 40\D+20\D+6 mm", built):
            raise rc.Failed(f"cad run box.py built no box:\n{built}")
        link = re.search(r"(?m)^\s*view:\s+(http://\S+\?token=\S+)", built)
        if not link:
            raise rc.Failed(f"cad run box.py printed no view: link with a token:\n{built}")
        with urllib.request.urlopen(link[1]) as page:
            status, body = page.status, page.read()
        try:
            urllib.request.urlopen(link[1].split("?", 1)[0])
            bare = 200
        except urllib.error.HTTPError as error:
            bare = error.code
        if status != 200 or b"<html" not in body.lower() or bare != 403:
            raise rc.Failed(f"the page link answered {status} ({len(body)} bytes), {bare} without its token")
        say(f"ok    cad +{VERSION} run box.py built the box; its page answers 200 with its token, 403 without")

    # --- 0.11.10's installer's state ------------------------------------------------------------------------------

    def as_old_installer_left_it(self) -> Path:
        """Ours removed by each program's own commands, then each program as 0.11.10's ``cad setup`` left it (see
        the module): the folder made by that release's own ``plugin.tree`` from its tree. The folder."""
        c = self.computer
        for name in self.names:
            if name == "claude":
                c.must(["claude", "plugin", "uninstall", OURS])
                c.must(["claude", "plugin", "marketplace", "remove", CATALOG])
            elif name == "codex":
                c.must(["codex", "plugin", "remove", OURS])
                c.must(["codex", "plugin", "marketplace", "remove", CATALOG])
            else:
                c.must(["gemini", "extensions", "uninstall", PLUGIN])
            held = self.listed(name)
            if held["plugins"] or held["catalogs"]:
                raise rc.Failed(f"{name} still holds {held['plugins']} {held['catalogs']} after its own removal")
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

    # --- what the computer holds, for a failure ---------------------------------------------------------------

    def report(self) -> str:
        parts = []
        for name in self.names:
            try:
                parts.append(f"{name} lists: {json.dumps(self.listed(name)['said'], default=str)[:4000]}")
            except Exception as error:  # noqa: BLE001 - a failure's report says what it can
                parts.append(f"{name} could not list: {error}")
        state = self.computer.state
        parts.append(f"state {state}: {sorted(os.listdir(state)) if state.is_dir() else '(none)'}; versions "
                     f"{sorted(os.listdir(state / 'versions')) if (state / 'versions').is_dir() else '(none)'}")
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


def steps(run: Run) -> None:
    c = run.computer
    commit = c.stand_in(rc.plugin_tree())
    say(f"ok    the local repository: latest at {commit[:12]}, which {GITHUB} names in the computer's git")
    say("note  Gemini CLI asks api.github.com for a release of ours named latest before it clones (there is none): "
        "that request goes to GitHub; the clone is the local one")

    names = run.names
    ran = run.script("install")
    run.app_lines(ran, "install", {name: rf"{re.escape(rc.PROGRAMS[name].name)}: installed" for name in names})
    run.ours_alone("install")
    run.cad_works()

    major, minor, patch = VERSION.split(".")[:3]
    c.advance(VERSION, f"{major}.{minor}.{int(patch) + 1}")
    ran = run.script("again")
    run.app_lines(ran, "again", {name: rf"{re.escape(rc.PROGRAMS[name].name)}: updated" for name in names})
    run.ours_alone("again")

    folder = run.as_old_installer_left_it()
    ran = run.script("migrate")
    removed = {"claude": rf"Claude Code: installed \(removed old copies: {re.escape(OLD_OURS)}\)",
               "codex": rf"Codex: installed \(removed old copies: {re.escape(OLD_OURS)}\)",
               "gemini": r"Gemini CLI: updated \(removed old copies: text-to-cad linked to .+\)"}
    run.app_lines(ran, "migrate", {name: removed[name] for name in names})
    run.ours_alone("migrate")
    say(f"note  0.11.10's folder after the migration: {'still there' if folder.exists() else 'gone'}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--wheels", type=Path, required=True, help="the folder of this tree's wheels")
    parser.add_argument("--require", default="", help="programs that must be here, comma-separated")
    parser.add_argument("--keep", action="store_true", help="keep the private computer")
    parser.add_argument("--work", type=Path, help="the private computer's folder (default: a new temporary one)")
    parser.add_argument("--install-py", type=Path, default=REPO_ROOT / "scripts" / "install" / "install.py",
                        help="the install.py the script runs (default: this tree's)")
    args = parser.parse_args(argv)
    required = [name for name in args.require.split(",") if name]
    unknown = [name for name in required if name not in rc.PROGRAMS]
    if unknown:
        parser.error(f"unknown programs {unknown}: {', '.join(rc.PROGRAMS)}")
    programs = {}
    for name, program in rc.PROGRAMS.items():
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

    work = (args.work or Path(tempfile.mkdtemp(prefix="real-install-"))).resolve()
    work.mkdir(parents=True, exist_ok=True)
    needles = (PLUGIN, CATALOG, str(work))
    before = rc.RealHome.here(list(rc.PROGRAMS), needles)
    feed = rc.Feed(VERSION)
    computer = rc.Computer(work, programs, feed=feed)
    say(f"real-install: cad {VERSION} into {computer.work}, default port {computer.port}; "
        + ", ".join(f"{name} {program_version(computer, name)}" for name in programs))
    run = Run(computer, args.wheels.resolve(), args.install_py.resolve())
    failed = ""
    began = time.monotonic()
    try:
        installer = load_installer()
        computer.check_path([app.command for app in installer.APPS if app.command] + ["cursor-agent"])
        steps(run)
    except (rc.Failed, OSError, ValueError, KeyError) as failure:
        failed = f"{type(failure).__name__}: {failure}" if not isinstance(failure, rc.Failed) else str(failure)
    if failed:
        say(f"FAILED  {failed}")
        say("-- what the computer holds")
        say(run.report())
    left = computer.stop(run.cad)
    feed.close()
    if left:
        failed = failed or "processes were left running"
        say("FAILED  left running, now ended:\n" + "\n".join(left))
    else:
        say("ok    nothing of the computer's is left running")
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
