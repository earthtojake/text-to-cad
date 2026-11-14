"""text-to-cad's installer: the program `install.sh` and `install.ps1` download from beside themselves and
run with uv's Python (the standard library alone, nothing imported from this repository).

    curl -fsSL https://texttocad.dev/install.sh | sh          # macOS and Linux
    irm https://www.texttocad.dev/install.ps1 | iex           # Windows PowerShell

It takes no options and does five things, in order:

1. finds the newest release (the version feed; ``FALLBACK``, the release it was published with, when the
   feed cannot be read or names an older one);
2. runs that release's ``cad setup`` through uvx, which installs text-to-cad and the ``cad`` command;
3. removes what earlier releases left in the agent apps (``cleanup`` in each row of ``APPS``, Claude
   Desktop's server, and every loose copy of our skills: ``remove_loose_skills``);
4. installs or updates the plugin in each agent app it finds, with that app's own command, from the
   GitHub repository's ``latest`` branch, or copies the skills into the agent's own skills folder;
5. prints one line per app. One app failing never stops the others; only a failed ``cad setup`` makes
   it exit nonzero.

``APPS`` is the one table of apps: a row says how the app is found, how ours is installed and updated
(from GitHub, and from a local folder for ``scripts/install/dev_install.py``), and how our old copies
there are found and removed. A correction is one row. Each row's comment says how its commands were
checked: by the vendor's documentation (its address), by the CLI's own ``--help``, by superpowers'
practice, or not at all. A store's copy (claude.ai's directory, Codex's directory) and every plugin or
skill of someone else's are never touched: only what is provably ours is removed (our names AND a sign
that it is ours: our catalog, a path in cad's state folder, a SKILL.md naming our repository).

Test hooks, never documented to people: ``CAD_INSTALL_FEED`` (the version feed's address),
``CAD_INSTALL_FROM`` (what uvx runs ``cad setup`` from instead of ``cad-server==<release>``: a wheel, for the
installer rehearsals), ``CODEX_CLI`` (the codex command, as earlier installers took it).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

# The release this file was published with (stamped by scripts/release/sync-version.mjs): installed when the
# version feed cannot be read, and never anything older.
FALLBACK = "0.11.11"
FEED = "https://api.texttocad.dev/v1/versions"
REPOSITORY = "earthtojake/text-to-cad"
URL = f"https://github.com/{REPOSITORY}"
BRANCH = "latest"
PLUGIN = "text-to-cad"
CATALOG = "earthtojake"          # the repository's catalog: a GitHub copy is text-to-cad@earthtojake
DEV_CATALOG = "earthtojake-dev"  # a checkout's development install (dev_install.py)
LOCAL_CATALOG = "text-to-cad"    # the folder catalog 0.10.0-0.11.10's installer wrote, <state>/plugin
# Every catalog of ours an app may hold. Of these, the one the source installs from is kept and brought up to date;
# the others are removed with their plugins.
OUR_CATALOGS = (LOCAL_CATALOG, CATALOG, DEV_CATALOG)
# The plugin names we ever used: `cad` until 0.7.6, `text-to-cad` since.
OUR_PLUGINS = ("text-to-cad", "cad")
SKILLS = ("cad", "engineering-drawing", "fea", "pcb", "print3d", "render", "robot-simulation", "sendcutsend")
# Skills an earlier release shipped and this one does not (implicit-cad: releases before 0.5).
RETIRED_SKILLS = ("bambu-labs", "dfam-check", "dfm", "dxf", "gcode", "pcb-dfm", "sdf", "simulation", "srdf",
                  "step-parts", "urdf", "cad-viewer", "cad-mcp-setup", "implicit-cad")
# Marks earlier installers wrote: in Cursor's plain copy (0.10.0-0.11.10), in a development install's copy.
COPY_MARK = ".text-to-cad-copy"
DEV_MARK = ".text-to-cad-dev"
UVX_ARGS = ("--no-config", "--managed-python", "--python", "3.14")
COMMAND_SECONDS = 900
_VERSION = re.compile(r"[0-9]+(\.[0-9]+)*([.+-][0-9A-Za-z.+-]*)?")


# --- the computer ---------------------------------------------------------------------------------


@dataclass
class Ran:
    code: int
    out: str = ""

    @property
    def ok(self) -> bool:
        return self.code == 0

    def last(self) -> str:
        """The last line it printed, as a reason."""
        lines = [line.strip() for line in self.out.splitlines() if line.strip()]
        return lines[-1][:200] if lines else f"exit status {self.code}"


class Failed(Exception):
    """One app's step failed: the message says why, in a few words."""


class Here:
    """This computer: its home folder, its environment, its platform, and how a command runs."""

    def __init__(self, environ: Optional[Dict[str, str]] = None, platform: str = sys.platform) -> None:
        self.environ = dict(os.environ if environ is None else environ)
        self.platform = platform
        self.home = Path(self.environ.get("USERPROFILE") if self.windows and self.environ.get("USERPROFILE")
                         else self.environ.get("HOME") or Path.home())

    @property
    def windows(self) -> bool:
        return self.platform == "win32"

    def which(self, name: str) -> Optional[str]:
        """A command on PATH, else in ~/.local/bin, where many CLIs install themselves before a new shell has it."""
        path = os.pathsep.join([self.environ.get("PATH", os.defpath), str(self.home / ".local" / "bin")])
        return shutil.which(name, path=path)

    def config_home(self) -> Path:
        return Path(self.environ.get("XDG_CONFIG_HOME") or self.home / ".config")

    def run(self, argv: Sequence[Any], cwd: Optional[Path] = None, answer: Optional[str] = None,
            timeout: float = COMMAND_SECONDS) -> Ran:
        """``argv`` run with nothing to read but ``answer``, what it printed captured."""
        environ = {**self.environ, "GIT_TERMINAL_PROMPT": "0"}
        try:
            done = subprocess.run([str(part) for part in argv], cwd=str(cwd) if cwd else None, env=environ,
                                  input=answer if answer is not None else "", stdout=subprocess.PIPE,
                                  stderr=subprocess.STDOUT, text=True, errors="replace", timeout=timeout)
        except subprocess.TimeoutExpired:
            return Ran(124, f"no answer in {int(timeout)} s")
        except OSError as error:
            return Ran(127, f"{type(error).__name__}: {error}")
        return Ran(done.returncode, done.stdout or "")

    def must(self, argv: Sequence[Any], **options: Any) -> Ran:
        ran = self.run(argv, **options)
        if not ran.ok:
            raise Failed(f"`{' '.join(str(word) for word in argv[1:3])}` said: {ran.last()}")
        return ran

    # Where cad keeps its state (cad's own `state_dir`, and Windows 0.10.0's): a plugin folder an earlier installer
    # wrote there, `<state>/plugin`, is ours.
    def state_dirs(self) -> List[Path]:
        found = [Path(self.environ["CAD_STATE_DIR"])] if self.environ.get("CAD_STATE_DIR") else []
        if self.platform == "darwin":
            found.append(self.home / "Library" / "Application Support" / "cad")
        found.append(Path(self.environ.get("XDG_STATE_HOME") or self.home / ".local" / "state") / "cad")
        if self.windows:
            found.append(Path(self.environ.get("LOCALAPPDATA") or self.home / "AppData" / "Local") / "cad-state")
        return found


def version_key(text: str) -> Tuple[int, ...]:
    found = re.match(r"\d+(?:\.\d+)*", text or "")
    return tuple(int(part) for part in found.group(0).split(".")) if found else ()


def read_json(path: Path) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def read_toml(path: Path) -> Dict[str, Any]:
    """A TOML file's tables, enough of them for Codex's config: tomllib where Python has it, else its
    ``[a.b."c"]`` headers and ``key = "string"`` lines."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError:
        return {}
    try:
        import tomllib  # type: ignore[import-not-found]

        return tomllib.loads(text)
    except ImportError:
        pass
    except ValueError:
        return {}
    data: Dict[str, Any] = {}
    table = data
    for line in text.splitlines():
        line = line.strip()
        header = re.fullmatch(r"\[([^\[\]]+)\]", line)
        if header:
            table = data
            for part in re.findall(r'"([^"]*)"|([^.\s]+)', header.group(1)):
                table = table.setdefault(part[0] or part[1], {})
            continue
        pair = re.fullmatch(r'([A-Za-z0-9_-]+)\s*=\s*"([^"]*)"', line)
        if pair:
            table[pair.group(1)] = pair.group(2)
    return data


def remove_path(path: Path) -> None:
    """A file, a link (never what it points at) or a folder, gone."""
    path = Path(path)
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.exists():
        shutil.rmtree(path)


def same_path(one: Any, other: Any) -> bool:
    if not one or not other:
        return False
    return os.path.normcase(os.path.realpath(str(one))) == os.path.normcase(os.path.realpath(str(other)))


def within(path: Any, folder: Path) -> bool:
    try:
        Path(os.path.realpath(str(path))).relative_to(os.path.realpath(str(folder)))
        return True
    except ValueError:
        return False


def our_repository(source: Any) -> bool:
    """Whether a git source names this repository: owner/repo, its URL, with or without .git."""
    if not isinstance(source, str):
        return False
    text = source.strip().rstrip("/")
    text = text[:-4] if text.endswith(".git") else text
    text = re.sub(r"^(https?://|git@)", "", text).replace("github.com:", "github.com/")
    return text in (REPOSITORY, f"github.com/{REPOSITORY}")


def our_folder(here: Here, path: Any) -> bool:
    """Whether a local plugin folder is ours: one an earlier installer wrote into cad's state folder
    (``<state>/plugin``), or one whose manifest names our repository (a checkout, a development install)."""
    if not path:
        return False
    if any(within(path, state) for state in here.state_dirs()):
        return True
    parts = Path(str(path)).parts
    if len(parts) >= 2 and parts[-1] == "plugin" and parts[-2] in ("cad", "cad-state"):
        return True
    for manifest in (".claude-plugin/marketplace.json", ".claude-plugin/plugin.json", "gemini-extension.json"):
        try:
            if URL in (Path(path) / manifest).read_text(encoding="utf-8"):
                return True
        except OSError:
            continue
    return False


def skill_name(text: str) -> Optional[str]:
    """The ``name`` in a SKILL.md's front matter."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    for line in lines[1:]:
        if line.strip() == "---":
            return None
        if line.startswith("name:"):
            return line[len("name:"):].strip().strip("\"'")
    return None


def our_skill(folder: Path) -> Optional[bool]:
    """Whether a skill folder is ours: its SKILL.md names one of our skills (current or retired) and our
    repository. None where it holds no readable SKILL.md (a link to nowhere, an empty folder): not ours to judge."""
    try:
        text = (Path(folder) / "SKILL.md").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    return REPOSITORY in text and skill_name(text) in (*SKILLS, *RETIRED_SKILLS)


# --- where the plugin comes from ---------------------------------------------------------------------


@dataclass
class Source:
    """Where the plugin comes from: the GitHub repository's ``latest`` branch, or, for dev_install.py, a local
    folder holding the plugin (``folder``) whose catalog is ``catalog``."""

    folder: Optional[Path] = None
    catalog: str = CATALOG
    skills_dir: Optional[Path] = None
    _scratch: Optional[str] = None
    _failed: str = ""

    @property
    def local(self) -> bool:
        return self.folder is not None

    def words(self) -> Dict[str, str]:
        return {"repo": REPOSITORY, "url": URL, "branch": BRANCH, "plugin": PLUGIN, "catalog": self.catalog,
                "folder": str(self.folder or "")}

    def skills(self, here: Here) -> Path:
        """The skills folder to copy from: the local one, else the ``latest`` branch's, fetched once (git, else
        the branch's tarball)."""
        if self.skills_dir is not None:
            return self.skills_dir
        if self._failed:
            raise Failed(self._failed)
        try:
            return self._fetch(here)
        except Failed as error:
            self._failed = str(error)
            raise

    def _fetch(self, here: Here) -> Path:
        self._scratch = tempfile.mkdtemp(prefix="text-to-cad-")
        target = Path(self._scratch) / "repo"
        git = here.which("git")
        if git and here.run([git, "clone", "--quiet", "--depth", "1", "--branch", BRANCH, URL, target]).ok:
            self.skills_dir = target / "skills"
            return self.skills_dir
        remove_path(target)
        archive = Path(self._scratch) / "latest.tar.gz"
        try:
            urllib.request.urlretrieve(f"https://codeload.github.com/{REPOSITORY}/tar.gz/refs/heads/{BRANCH}", archive)
            with tarfile.open(archive) as tar:
                members = [member for member in tar.getmembers() if member.isfile() or member.isdir()]
                if any(member.name.startswith("/") or ".." in Path(member.name).parts for member in members):
                    raise Failed("the downloaded archive is not a plain folder")
                tar.extractall(target, members=members)
        except (OSError, tarfile.TarError) as error:
            raise Failed(f"could not download the skills ({type(error).__name__})") from error
        roots = [path for path in target.iterdir() if (path / "skills").is_dir()]
        if not roots:
            raise Failed("the downloaded archive has no skills folder")
        self.skills_dir = roots[0] / "skills"
        return self.skills_dir

    def root(self, here: Here) -> Path:
        """The plugin's folder: the local one, else the ``latest`` branch fetched once (``skills``)."""
        return self.folder if self.folder is not None else self.skills(here).parent

    def close(self) -> None:
        if self._scratch:
            shutil.rmtree(self._scratch, ignore_errors=True)


# --- the apps -----------------------------------------------------------------------------------------


@dataclass
class Context:
    """What one run knows as it goes: the source, and whether Claude Code now has our plugin (Cursor and Grok
    Build load Claude Code's plugins, so they then need none of their own)."""

    source: Source
    claude_has_ours: bool = False


@dataclass
class Outcome:
    status: str  # installed, updated, removed, skipped, failed
    words: str = ""
    removed: List[str] = field(default_factory=list)

    def line(self, name: str) -> str:
        text = f"{name}: {self.status}" + (f": {self.words}" if self.words else "")
        if self.removed:
            text += f" (removed old copies: {', '.join(self.removed)})"
        return text


NOT_FOUND = Outcome("skipped", "not found")
QUIET = Outcome("skipped")  # nothing to do and nothing worth a line (Claude Desktop with nothing of ours)


def fill(templates: Sequence[Sequence[str]], source: Source, here: Optional[Here] = None) -> List[List[str]]:
    """The templates with their words filled in; ``{fetched}``, the ``latest`` branch fetched (``Source.root``), only
    where a template names it."""
    words = source.words()
    if here is not None and any("{fetched}" in part for argv in templates for part in argv):
        words["fetched"] = str(source.root(here))
    return [[part.format(**words) for part in argv] for argv in templates]


@dataclass
class App:
    """One row of the table. ``command``: the CLI the app is found by and run with. ``install`` and ``update``:
    its commands for a GitHub copy, ``local`` for a checkout's folder (dev_install.py), with ``{repo}``, ``{url}``,
    ``{branch}``, ``{plugin}``, ``{catalog}`` and ``{folder}`` filled in. ``installed``: whether ours is there
    already; without it, ``update`` runs first and ``install`` where that fails. ``handler``: an app whose old
    copies need more than its commands (Claude Code, Codex, Cursor, Gemini CLI, Grok Build, Claude Desktop).
    ``folder``: an agent with no plugin command, given the skills in its own folder; ``marks`` find it."""

    key: str
    name: str
    command: Optional[str] = None
    install: Sequence[Sequence[str]] = ()
    update: Sequence[Sequence[str]] = ()
    local: Sequence[Sequence[str]] = ()
    installed: Optional[Callable[[Here], bool]] = None
    handler: Optional[Callable[["App", Here, Context], Outcome]] = None
    folder: Optional[Callable[[Here], Path]] = None
    marks: Optional[Callable[[Here], List[Path]]] = None

    def run(self, here: Here, context: Context) -> Outcome:
        if self.handler is not None:
            return self.handler(self, here, context)
        if self.folder is not None:
            return copy_skills(self, here, context)
        return plugin_command(self, here, context)


def plugin_command(app: App, here: Here, context: Context) -> Outcome:
    """An app installed and updated by its own commands alone."""
    cli = here.which(app.command or "")
    if not cli:
        return NOT_FOUND
    source = context.source
    if source.local:
        if not app.local:
            return Outcome("skipped", "no install from a local folder")
        for argv in fill(app.local, source, here):
            here.must([cli, *argv])
        return Outcome("installed", f"from {source.folder}")
    update = fill(app.update, source, here)

    def run_all(commands: List[List[str]]) -> Optional[Ran]:
        for argv in commands:
            ran = here.run([cli, *argv])
            if not ran.ok:
                return ran
        return None

    known = app.installed(here) if app.installed is not None else None
    if known and update:
        failed = run_all(update)
        if failed is None:
            return Outcome("updated")
        raise Failed(failed.last())
    if known is None and update and run_all(update) is None:
        return Outcome("updated")
    install = fill(app.install, source, here)
    failed = run_all(install)
    if failed is None:
        return Outcome("installed")
    if app.installed is not None and app.installed(here):
        return Outcome("installed", f"its command said: {failed.last()}")
    raise Failed(failed.last())


# Claude Code and Codex: a plugin is name@catalog. Ours from GitHub is text-to-cad@earthtojake, from the repository's
# `latest`. Earlier: cad@text-to-cad (0.5.0-0.7.5, the catalog then named text-to-cad, on GitHub), cad@earthtojake
# (0.7.6), text-to-cad@text-to-cad (0.10.0-0.11.10's installer: a local catalog at <state>/plugin), and a checkout's
# text-to-cad@earthtojake-dev.


@dataclass
class Catalog:
    name: str
    kind: str  # github, git, directory, other
    where: str = ""  # the repository or the folder
    ref: str = ""

    def ours(self, here: Here) -> bool:
        if self.name == DEV_CATALOG:
            return True
        if self.kind in ("github", "git"):
            return our_repository(self.where)
        if self.kind == "directory":
            return our_folder(here, self.where)
        return False

    def matches(self, here: Here, source: Source) -> bool:
        """Whether it is the catalog the source installs from, as the source would add it."""
        if source.local:
            return self.kind == "directory" and same_path(self.where, source.folder)
        return self.kind in ("github", "git") and our_repository(self.where) and self.ref == BRANCH


def marketplace_app(app: App, here: Here, context: Context, cli: Optional[str], catalogs: Dict[str, Catalog],
                    plugins: Sequence[str], verbs: Dict[str, List[List[str]]]) -> Outcome:
    """Claude Code's and Codex's flow: our other catalogs removed with their plugins, ours added or brought up to
    date, our plugin installed or updated. ``verbs``: the app's commands, by what they do."""
    if not cli:
        return NOT_FOUND
    source = context.source
    target = source.catalog
    removed, left = [], []
    for name in OUR_CATALOGS:
        catalog = catalogs.get(name)
        ids = [plugin for plugin in plugins if plugin.endswith(f"@{name}") and plugin.split("@")[0] in OUR_PLUGINS]
        if catalog is not None and not catalog.ours(here):
            if ids or name == target:
                left.append(f"the {name} catalog is another source's ({catalog.where or catalog.kind})")
            continue
        if name == target:
            # Ours, but cad@<catalog> (0.7.6) goes; a catalog of that name from elsewhere is moved to the source.
            for plugin in ids:
                if plugin.split("@")[0] != PLUGIN:
                    here.must([cli, *verbs["remove"][0], plugin])
                    removed.append(plugin)
            if catalog is not None and not catalog.matches(here, source):
                for plugin in ids:
                    if plugin.split("@")[0] == PLUGIN:
                        here.must([cli, *verbs["remove"][0], plugin])
                here.must([cli, *verbs["forget"][0], name])
                catalogs.pop(name)
                plugins = [plugin for plugin in plugins if not plugin.endswith(f"@{name}")]
            continue
        for plugin in ids:
            here.must([cli, *verbs["remove"][0], plugin])
            removed.append(plugin)
        if catalog is not None:
            here.must([cli, *verbs["forget"][0], name])
    if left and target in catalogs and not catalogs[target].ours(here):
        raise Failed("; ".join(left) + ": left alone")
    ours = f"{PLUGIN}@{target}"
    words = source.words()
    if target in catalogs:
        for argv in verbs["refresh"]:
            here.must([cli, *[part.format(**words) for part in argv]])
        if ours in plugins:
            for argv in verbs["update"]:
                here.must([cli, *[part.format(**words) for part in argv]])
            outcome = Outcome("updated", removed=removed)
        else:
            here.must([cli, *[part.format(**words) for part in verbs["install"][0]]])
            outcome = Outcome("installed", removed=removed)
    else:
        for argv in verbs["add_local" if source.local else "add"]:
            here.must([cli, *[part.format(**words) for part in argv]])
        here.must([cli, *[part.format(**words) for part in verbs["install"][0]]])
        outcome = Outcome("installed", removed=removed)
    if left:
        outcome.words = "; ".join(left) + ": left alone"
    return outcome


def claude_dir(here: Here) -> Path:
    return Path(here.environ.get("CLAUDE_CONFIG_DIR") or here.home / ".claude")


def claude_code(app: App, here: Here, context: Context) -> Outcome:
    """Claude Code, from its records (``plugins/installed_plugins.json``, ``plugins/known_marketplaces.json``):
    only the user scope's plugins are ours to change; a project's, an administrator's, and claude.ai's synced
    copies are left. Verified: `claude plugin --help` and its subcommands (2.1.316); docs
    https://code.claude.com/docs/en/discover-plugins (`owner/repo#ref` pins a branch; `marketplace remove` uninstalls
    its plugins; `plugin update <plugin>@<marketplace>`)."""
    folder = claude_dir(here) / "plugins"
    recorded = read_json(folder / "installed_plugins.json")
    table = recorded.get("plugins") if isinstance(recorded, dict) else None
    plugins = [name for name, entries in (table.items() if isinstance(table, dict) else ())
               if any((entry.get("scope") or "user") == "user"
                      for entry in (entries if isinstance(entries, list) else [entries]) if isinstance(entry, dict))]
    catalogs = {}
    known = read_json(folder / "known_marketplaces.json")
    for name, entry in (known.items() if isinstance(known, dict) else ()):
        source = entry.get("source") if isinstance(entry, dict) else None
        if not isinstance(source, dict):
            continue
        kind = source.get("source")
        where = source.get("path") if kind == "directory" else source.get("repo") or source.get("url") or ""
        catalogs[name] = Catalog(name, kind if kind in ("github", "git", "directory") else "other", str(where or ""),
                                 str(source.get("ref") or ""))
    verbs = {
        "remove": [["plugin", "uninstall"]],
        "forget": [["plugin", "marketplace", "remove"]],
        "add": [["plugin", "marketplace", "add", "{repo}#{branch}"]],
        "add_local": [["plugin", "marketplace", "add", "{folder}"]],
        "refresh": [["plugin", "marketplace", "update", "{catalog}"]],
        "install": [["plugin", "install", "{plugin}@{catalog}"]],
        "update": [["plugin", "update", "{plugin}@{catalog}"]],
    }
    outcome = marketplace_app(app, here, context, here.which("claude"), catalogs, plugins, verbs)
    context.claude_has_ours = outcome.status in ("installed", "updated")
    return outcome


def codex_cli(here: Here) -> Optional[str]:
    """``CODEX_CLI``, else ``codex`` on PATH, else the one the Codex app bundles (macOS)."""
    named = here.environ.get("CODEX_CLI")
    if named:
        return here.which(named)
    found = here.which("codex")
    if found:
        return found
    bundled = Path("/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex")
    return str(bundled) if here.platform == "darwin" and os.access(bundled, os.X_OK) else None


def codex(app: App, here: Here, context: Context) -> Outcome:
    """Codex, from its config (``$CODEX_HOME/config.toml``: ``[marketplaces.<name>]`` with ``source_type``,
    ``source`` and ``ref``; ``[plugins."<id>"]``). A copy from OpenAI's directory (``openai-*``) is left.
    Verified: `codex plugin --help` and its subcommands (`marketplace add <owner/repo> --ref`, `marketplace upgrade`,
    `add`, `remove`); docs https://developers.openai.com/codex/plugins/build (`--ref`, `upgrade`). `add` again after
    `upgrade` copies the plugin again: Codex keeps a copy, and the docs do not say an upgrade refreshes it."""
    config = read_toml(Path(here.environ.get("CODEX_HOME") or here.home / ".codex") / "config.toml")
    plugins = list((config.get("plugins") or {}).keys())
    catalogs = {}
    for name, entry in (config.get("marketplaces") or {}).items():
        if isinstance(entry, dict):
            local = entry.get("source_type") == "local"
            catalogs[name] = Catalog(name, "directory" if local else "git", str(entry.get("source") or ""),
                                     str(entry.get("ref") or ""))
    verbs = {
        "remove": [["plugin", "remove"]],
        "forget": [["plugin", "marketplace", "remove"]],
        "add": [["plugin", "marketplace", "add", "{repo}", "--ref", "{branch}"]],
        "add_local": [["plugin", "marketplace", "add", "{folder}"]],
        "refresh": [] if context.source.local else [["plugin", "marketplace", "upgrade", "{catalog}"]],
        "install": [["plugin", "add", "{plugin}@{catalog}"]],
        "update": [["plugin", "add", "{plugin}@{catalog}"]],
    }
    return marketplace_app(app, here, context, codex_cli(here), catalogs, plugins, verbs)


def git_origin(folder: Path) -> Optional[str]:
    try:
        config = (Path(folder) / ".git" / "config").read_text(encoding="utf-8")
    except OSError:
        return None
    found = re.search(r'\[remote "origin"\][^\[]*?url\s*=\s*(\S+)', config)
    return found.group(1) if found else None


def cursor(app: App, here: Here, context: Context) -> Outcome:
    """Cursor: a clone of the ``latest`` branch in its local plugins folder (``~/.cursor/plugins/local``). Where
    Claude Code has our plugin, Cursor loads that one (as earlier releases measured), so its own copy of ours goes.
    Removed: 0.10.0-0.11.10's plain copy (marked ``.text-to-cad-copy``), a development copy (``.text-to-cad-dev``).
    Verified: docs https://cursor.com/docs/plugins (a plugin is a folder in ~/.cursor/plugins/local; a symlink there is
    skipped). That Cursor loads Claude Code's plugins is not in its docs: earlier releases' observation."""
    base = here.home / ".cursor"
    if not base.is_dir() and not here.which("cursor-agent"):
        return NOT_FOUND
    local = base / "plugins" / "local"
    target = local / (f"{PLUGIN}-dev" if context.source.local else PLUGIN)
    removed = []
    for path in (local / PLUGIN, local / f"{PLUGIN}-dev"):
        if not path.exists() and not path.is_symlink():
            continue
        clone = our_repository(git_origin(path))
        marked = (path / COPY_MARK).is_file() or (path / DEV_MARK).is_file()
        if not clone and not marked:
            continue
        keep = path == target and not context.claude_has_ours and (clone if not context.source.local else False)
        if not keep:
            remove_path(path)
            removed.append(str(path).replace(str(here.home), "~"))
    if context.claude_has_ours:
        return Outcome("skipped", "it loads Claude Code's plugin", removed)
    if context.source.local:
        copy_tree(context.source.folder, target)
        (target / DEV_MARK).write_text(f"{context.source.folder}\n", encoding="utf-8")
        return Outcome("installed", f"a copy of {context.source.folder}", removed)
    if target.exists():
        if not our_repository(git_origin(target)):
            raise Failed(f"{target} holds something else: move it away, then run this again")
        git = here.which("git")
        if not git:
            raise Failed("git is needed to update it")
        here.must([git, "-C", target, "fetch", "--quiet", "--depth", "1", "origin", BRANCH])
        here.must([git, "-C", target, "checkout", "--quiet", "--force", "-B", BRANCH, "FETCH_HEAD"])
        return Outcome("updated", removed=removed)
    git = here.which("git")
    if not git:
        raise Failed("git is needed to install it")
    local.mkdir(parents=True, exist_ok=True)
    here.must([git, "clone", "--quiet", "--depth", "1", "--branch", BRANCH, URL, target])
    return Outcome("installed", removed=removed)


def gemini(app: App, here: Here, context: Context) -> Outcome:
    """Gemini CLI: its extension, installed from GitHub at ``latest`` (a copy), updated by ``extensions update``.
    0.10.0-0.11.10 linked ``<state>/plugin`` under the same name: unlinked first. Read from
    ``~/.gemini/extensions/text-to-cad/.gemini-extension-install.json`` (``type``, ``source``, ``ref``).
    Verified: `gemini extensions --help` and its subcommands (`install <source> --ref --consent`, `update <name>`,
    `uninstall`, `link <path> --consent`); docs https://geminicli.com/docs/extensions/reference/."""
    cli = here.which("gemini")
    if not cli:
        return NOT_FOUND
    folder = Path(here.environ.get("GEMINI_CLI_HOME") or here.home) / ".gemini" / "extensions" / PLUGIN
    source = context.source

    def record() -> Dict[str, Any]:
        found = read_json(folder / ".gemini-extension-install.json")
        return found if isinstance(found, dict) else {}

    def ours_now() -> bool:
        found = record()
        if source.local:
            return found.get("type") == "link" and same_path(found.get("source"), source.folder)
        return found.get("type") == "git" and our_repository(found.get("source")) and found.get("ref") == BRANCH

    removed = []
    if folder.exists():
        found = record()
        if ours_now():
            if source.local:
                return Outcome("updated", f"linked to {source.folder}")
            here.must([cli, "extensions", "update", PLUGIN])
            return Outcome("updated")
        linked = found.get("type") == "link" and our_folder(here, found.get("source"))
        if not (linked or our_repository(found.get("source"))):
            raise Failed(f"another extension named {PLUGIN} is installed (from {found.get('source') or 'elsewhere'}): "
                         "left alone")
        here.must([cli, "extensions", "uninstall", PLUGIN])
        removed.append(f"{PLUGIN} " + ("linked to " + str(found.get("source")) if linked else
                                       f"from {found.get('source')} at {found.get('ref') or 'its default branch'}"))
    if source.local:
        ran = here.run([cli, "extensions", "link", source.folder, "--consent"], answer="y\n")
    else:
        ran = here.run([cli, "extensions", "install", URL, "--ref", BRANCH, "--consent"])
    if not ran.ok and not ours_now():
        raise Failed(ran.last())
    return Outcome("installed", removed=removed)


def grok_plugins(here: Here) -> List[Dict[str, str]]:
    """Grok Build's installed plugins, from its registry (``~/.grok/installed-plugins/registry.json``): name, where
    from, git ref."""
    registry = read_json(here.home / ".grok" / "installed-plugins" / "registry.json")
    found = []
    for entry in ((registry or {}).get("repos") or {}).values() if isinstance(registry, dict) else ():
        kind = entry.get("kind") if isinstance(entry, dict) else None
        path = entry.get("path") if isinstance(entry, dict) else None
        if not isinstance(kind, dict) or not isinstance(path, str):
            continue
        named = entry.get("plugins")
        names = list(named) if isinstance(named, dict) else [
            (read_json(Path(path) / ".grok-plugin" / "plugin.json") or read_json(Path(path) / "plugin.json") or {}).get("name")]
        for name in names:
            found.append({"name": str(name), "source": str(kind.get("url") or kind.get("path") or ""),
                          "ref": str(kind.get("git_ref") or ""), "path": path})
    return found


def grok(app: App, here: Here, context: Context) -> Outcome:
    """Grok Build: ``grok plugin install earthtojake/text-to-cad@latest --trust``, then enabled; updated by ``grok
    plugin update``. Grok Build loads Claude Code's plugins (its docs), so where Claude Code has ours its own copy of
    ours goes. Removed: a plugin named ``cad`` from our repository (0.5.0-0.7.6). Verified: `grok plugin --help` and
    its subcommands (`install <source>` with `@ref`, `--trust`; `enable`; `update [name]`; `uninstall`); docs
    https://docs.x.ai/build/features/skills-plugins-marketplaces (it reads Claude Code's marketplaces and plugins)."""
    cli = here.which("grok")
    if not cli:
        return NOT_FOUND
    source = context.source
    removed = []
    mine = None
    for plugin in grok_plugins(here):
        ours = our_repository(plugin["source"]) or our_folder(here, plugin["source"])
        if plugin["name"] == "cad" and ours:
            here.must([cli, "plugin", "uninstall", "cad"])
            removed.append("cad")
        elif plugin["name"] == PLUGIN:
            if not ours:
                raise Failed(f"another plugin named {PLUGIN} is installed (from {plugin['source']}): left alone")
            current = (same_path(plugin["source"], source.folder) if source.local
                       else our_repository(plugin["source"]) and plugin["ref"] == BRANCH)
            if current and not context.claude_has_ours and not source.local:
                mine = plugin
            else:
                here.must([cli, "plugin", "uninstall", PLUGIN])
                removed.append(f"{PLUGIN} from {plugin['source']}" + (f"@{plugin['ref']}" if plugin["ref"] else ""))
    if context.claude_has_ours:
        return Outcome("skipped", "it loads Claude Code's plugin", removed)
    if mine is not None:
        here.must([cli, "plugin", "update", PLUGIN])
        return Outcome("updated", removed=removed)
    here.must([cli, "plugin", "install", str(source.folder) if source.local else f"{REPOSITORY}@{BRANCH}", "--trust"])
    here.must([cli, "plugin", "enable", PLUGIN])
    return Outcome("installed", removed=removed)


def desktop_config(here: Here) -> Path:
    if here.platform == "darwin":
        return here.home / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    if here.windows:
        return Path(here.environ.get("APPDATA") or here.home / "AppData" / "Roaming") / "Claude" / "claude_desktop_config.json"
    return here.config_home() / "Claude" / "claude_desktop_config.json"


def runs_text_to_cad(entry: Any) -> bool:
    """Whether a server entry runs text-to-cad: its command is our transport's (``cad-mcp``) or an earlier server's
    (``cadgen``), or its arguments pin one of our packages or name one of our modules."""
    if not isinstance(entry, dict):
        return False
    command = os.path.basename(str(entry.get("command") or "")).lower()
    command = command[:-4] if command.endswith(".exe") else command
    if command in ("cad-mcp", "cadgen") or "cadgen" in command:
        return True
    words = entry.get("args") if isinstance(entry.get("args"), list) else []
    return any(isinstance(word, str) and (word.startswith(("cad-mcp==", "cad-server==", "cadgen=="))
                                          or word in ("cad-mcp", "cadgen", "cad_mcp", "cad_server.cli", "cadgen.cli"))
               for word in words)


def _member_spans(text: str, start: int) -> Tuple[List[Tuple[str, int, int, int]], int]:
    """The members of the JSON object whose ``{`` is at ``start``: ``(key, member start, value start, member end)``
    each, and where the object ends."""
    decoder = json.JSONDecoder()
    spaces = re.compile(r"\s*")
    members = []
    index = spaces.match(text, start + 1).end()
    if text[index] == "}":
        return members, index + 1
    while True:
        begin = index
        key, index = json.decoder.scanstring(text, index + 1)
        index = spaces.match(text, index).end()
        if text[index] != ":":
            raise ValueError("expected a colon")
        value = spaces.match(text, index + 1).end()
        _parsed, end = decoder.raw_decode(text, value)
        members.append((key, begin, value, end))
        index = spaces.match(text, end).end()
        if text[index] == "}":
            return members, index + 1
        if text[index] != ",":
            raise ValueError("expected a comma")
        index = spaces.match(text, index + 1).end()


def without_member(text: str, path: Sequence[str]) -> str:
    """``text``, a JSON object, with the member at ``path`` taken out and every other byte as it was."""
    spaces = re.compile(r"\s*")
    start = spaces.match(text).end()
    for depth, key in enumerate(path):
        members, _end = _member_spans(text, start)
        found = [member for member in members if member[0] == key]
        if not found:
            return text
        if depth < len(path) - 1:
            start = found[-1][2]
            if text[start] != "{":
                return text
            continue
        for _key, begin, _value, end in reversed(found):
            members, _end = _member_spans(text, start)
            place = next(i for i, member in enumerate(members) if member[1] == begin)
            if place + 1 < len(members):  # the comma after it, and the space up to the next member
                text = text[:begin] + text[members[place + 1][1]:]
            elif place > 0:  # the last: from the end of the one before it, so its comma goes
                text = text[:members[place - 1][3]] + text[end:]
            else:
                text = text[:begin] + text[end:]
    return text


def claude_desktop(app: App, here: Here, context: Context) -> Outcome:
    """Claude Desktop: nothing is installed (Claude gets the skills through Claude Code's plugin). Releases 0.7.6-0.11.10
    wrote our server into its config as ``mcpServers.cad``: that one member is taken out where it runs text-to-cad,
    every other byte of the file kept, the file as it was kept beside it as ``.bak``. A ``cad`` that is another
    server's, or a file that is not plain JSON, is left. Verified: docs https://modelcontextprotocol.io/quickstart/user
    (servers are keys of ``mcpServers`` in claude_desktop_config.json)."""
    path = desktop_config(here)
    if not path.parent.is_dir():
        return QUIET
    try:
        text = path.read_text(encoding="utf-8")
        data = json.loads(text) if text.strip() else {}
    except (OSError, ValueError):
        return Outcome("skipped", f"{path.name} is not plain JSON: left alone")
    servers = data.get("mcpServers") if isinstance(data, dict) else None
    if not isinstance(servers, dict) or not runs_text_to_cad(servers.get("cad")):
        return QUIET
    edited = without_member(text, ["mcpServers", "cad"])
    expected = dict(data)
    expected["mcpServers"] = {key: value for key, value in servers.items() if key != "cad"}
    if json.loads(edited) != expected:
        raise Failed(f"{path.name} could not be edited safely: remove mcpServers.cad by hand")
    shutil.copy2(path, path.with_name(path.name + ".bak"))
    handle, temporary = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.")
    with os.fdopen(handle, "w", encoding="utf-8", newline="") as out:
        out.write(edited)
    os.chmod(temporary, path.stat().st_mode & 0o777)
    os.replace(temporary, path)
    return Outcome("removed", f"the old cad server in its settings ({path.name}.bak keeps the file as it was)")


def copy_tree(source: Optional[Path], target: Path) -> None:
    """``source`` copied to ``target``, real files, links followed, caches left out; a folder there replaced."""
    staged = target.with_name(f".{target.name}.new")
    remove_path(staged)
    shutil.copytree(str(source), str(staged), symlinks=False,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store", ".git"))
    remove_path(target)
    staged.rename(target)


def copy_skills(app: App, here: Here, context: Context) -> Outcome:
    """An agent with no plugin command: our skills copied into its own skills folder (only ours are replaced; a
    folder of that name that is someone else's stays)."""
    if not any(path.exists() for path in (app.marks(here) if app.marks else [])):
        return NOT_FOUND
    target = app.folder(here)
    source = context.source.skills(here)
    target.mkdir(parents=True, exist_ok=True)
    copied, kept = [], []
    for skill in sorted(path for path in source.iterdir() if (path / "SKILL.md").is_file()):
        there = target / skill.name
        if (there.exists() or there.is_symlink()) and not our_skill(there):
            kept.append(skill.name)
            continue
        copy_tree(skill, there)
        copied.append(skill.name)
    where = str(target).replace(str(here.home), "~")
    words = f"{len(copied)} skills in {where}" + (f"; left {', '.join(kept)}: someone else's skill of that name"
                                                  if kept else "")
    return Outcome("installed", words)


# The skill folders every earlier release may have left a loose copy of ours in: the shared ~/.agents/skills, each
# app's own, the per-agent folders 0.8.4-0.11.4's installer wrote through the Skills CLI, and the folders of the
# agents the Skills CLI served since.
def loose_skill_folders(here: Here) -> List[Path]:
    home, config = here.home, here.config_home()
    hermes = Path(here.environ.get("HERMES_HOME") or home / ".hermes")
    folders = [
        home / ".agents" / "skills",
        claude_dir(here) / "skills",
        Path(here.environ.get("CODEX_HOME") or home / ".codex") / "skills",
        home / ".cursor" / "skills",
        home / ".grok" / "skills",
        Path(here.environ.get("GEMINI_CLI_HOME") or home) / ".gemini" / "skills",
        home / ".copilot" / "skills",
        config / "agents" / "skills",
        home / ".gemini" / "antigravity" / "skills",
        home / ".gemini" / "antigravity-cli" / "skills",
        home / ".factory" / "skills",
        home / ".kilo" / "skills",
        home / ".kilocode" / "skills",
        config / "opencode" / "skills",
        home / ".codeium" / "windsurf" / "skills",
        home / ".openclaw" / "skills",
        home / ".clawdbot" / "skills",
        home / ".moltbot" / "skills",
        config / "goose" / "skills",
        home / ".kiro" / "skills",
        hermes / "skills",
        home / ".roo" / "skills",
        home / ".trae" / "skills",
        home / ".cline" / "skills",
        config / "amp" / "skills",
    ]
    return list(dict.fromkeys(folders))


def skills_locks(here: Here) -> List[Path]:
    """The Skills CLI's records of what it installed globally: in ``$XDG_STATE_HOME/skills`` where that is set,
    else ``~/.agents`` (both read, whichever the CLI used)."""
    state = here.environ.get("XDG_STATE_HOME")
    return ([Path(state) / "skills" / ".skill-lock.json"] if state else []) + [here.home / ".agents" / ".skill-lock.json"]


def remove_loose_skills(here: Here) -> Outcome:
    """Every loose copy of our skills (current and retired names), in every folder an earlier release or the Skills
    CLI wrote one, that is ours (``our_skill``: our name AND our repository in its SKILL.md), deleted; a link to ours
    is unlinked, never followed. The Skills CLI's record of each (``skills_locks``) goes with it, only an entry whose
    source is our repository, or the plugin folder 0.10.0-0.11.10 wrote in cad's state folder. No ``npx skills remove``: it removes by name alone, from
    folders this does not read, and our names are common words."""
    ours: List[Path] = []
    for folder in loose_skill_folders(here):
        for name in (*SKILLS, *RETIRED_SKILLS):
            path = folder / name
            if (path.exists() or path.is_symlink()) and our_skill(path):
                ours.append(path)
    for path in ours:
        # A link to a copy removed just before it reads as nothing now: it was judged ours above.
        if (path.exists() or path.is_symlink()) and our_skill(path) is not False:
            remove_path(path)
    for lock in skills_locks(here):
        record = read_json(lock)
        entries = record.get("skills") if isinstance(record, dict) else None
        if not isinstance(entries, dict):
            continue
        mine = [name for name, entry in entries.items() if name in (*SKILLS, *RETIRED_SKILLS) and isinstance(entry, dict)
                and any(our_repository(entry.get(key)) or (isinstance(entry.get(key), str) and os.path.isabs(entry[key])
                                                            and any(within(entry[key], state) for state in here.state_dirs()))
                        for key in ("source", "sourceUrl"))]
        if mine:
            for name in mine:
                del entries[name]
            lock.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    if not ours:
        return QUIET
    places = sorted({str(path.parent).replace(str(here.home), "~") for path in ours})
    return Outcome("removed", f"{len(ours)} old copies of our skills, in {', '.join(places)}")


def _hermes_plugin(here: Here) -> bool:
    return (Path(here.environ.get("HERMES_HOME") or here.home / ".hermes") / "plugins" / PLUGIN).is_dir()


def _pi_installed(here: Here) -> bool:
    try:
        return f"github.com/{REPOSITORY}" in (here.home / ".pi" / "agent" / "settings.json").read_text(encoding="utf-8")
    except OSError:
        return False


def _qwen_installed(here: Here) -> bool:
    return (here.home / ".qwen" / "extensions" / PLUGIN).is_dir()


def _folder_agent(key: str, name: str, folder: Callable[[Here], Path], *marks: Callable[[Here], Path]) -> App:
    return App(key, name, folder=folder, marks=lambda here: [mark(here) for mark in marks])


# THE TABLE. Order matters only where it says: Claude Code first (Cursor and Grok Build load its plugin).
APPS: Tuple[App, ...] = (
    App("claude", "Claude Code", command="claude", handler=claude_code),
    App("claude-desktop", "Claude Desktop", handler=claude_desktop),
    App("codex", "Codex", command="codex", handler=codex),
    App("cursor", "Cursor", handler=cursor),
    App("gemini", "Gemini CLI", command="gemini", handler=gemini),
    App("grok", "Grok Build", command="grok", handler=grok),
    # Qwen Code. Docs https://qwenlm.github.io/qwen-code-docs/en/users/extension/introduction/ (install, update) and its
    # source, packages/cli/src/commands/extensions/install.ts (--ref, --consent). Not run. Where it keeps an extension
    # (~/.qwen/extensions/<name>) is Gemini CLI's layout, unverified.
    App("qwen", "Qwen Code", command="qwen",
        install=[["extensions", "install", "{url}", "--ref", "{branch}", "--consent"]],
        update=[["extensions", "update", "{plugin}"]],
        local=[["extensions", "install", "{folder}", "--consent"]], installed=_qwen_installed),
    # Hermes Agent. Help: `hermes plugins install --help` (owner/repo, --no-enable; --ref takes a commit SHA alone, so
    # this installs the default branch, main), `enable --no-allow-tool-override`, `update <name>`; docs
    # https://hermes-agent.nousresearch.com/docs/developer-guide/plugins. It takes the root plugin.json, skills/ and
    # mcp.json. Lane C ran install, enable and `plugins doctor` from a local copy; its install-time scan refused our
    # README while that named AGENTS.md (a failure this reports as Hermes's line).
    App("hermes", "Hermes Agent", command="hermes",
        install=[["plugins", "install", "{repo}", "--no-enable"], ["plugins", "enable", "{plugin}", "--no-allow-tool-override"]],
        update=[["plugins", "update", "{plugin}"]], installed=_hermes_plugin),
    # Factory Droid. Docs https://docs.factory.com/cli/configuration/plugins: it reads .claude-plugin/marketplace.json;
    # the catalog's name comes from the source (`owner/repo` -> the repo's name; a `#ref` is appended to it), so this
    # adds no ref (main) to keep the name text-to-cad, as superpowers does. Not run.
    App("droid", "Factory Droid", command="droid",
        install=[["plugin", "marketplace", "add", "{repo}"], ["plugin", "install", "{plugin}@text-to-cad", "--scope", "user"]],
        update=[["plugin", "marketplace", "update", "text-to-cad"], ["plugin", "update", "{plugin}@text-to-cad", "--scope", "user"]]),
    # Devin CLI. Docs https://docs.devin.ai/cli/extensibility/plugins/overview (install owner/repo -y; no ref: main;
    # update <name>; it reads .claude-plugin/plugin.json). Not run.
    App("devin", "Devin CLI", command="devin",
        install=[["plugins", "install", "{repo}", "-y"]], update=[["plugins", "update", "{plugin}"]],
        local=[["plugins", "install", "--local", "{folder}", "-y"]]),
    # Antigravity. Docs https://antigravity.google/docs/plugins (install <repo URL or path>, uninstall; no update
    # command, no ref: main; it reads .antigravity-plugin/plugin.json). Updated by installing again. Not run.
    App("antigravity", "Antigravity", command="agy",
        install=[["plugin", "install", "{url}"]],
        update=[["plugin", "uninstall", "{plugin}"], ["plugin", "install", "{url}"]],
        local=[["plugin", "install", "{folder}"]]),
    # GitHub Copilot CLI. Docs https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-plugin-reference
    # (marketplace add owner/repo#ref; the catalog is named by its marketplace.json; install name@marketplace;
    # update <name>). Superpowers installs it the same way. Not run.
    App("copilot", "GitHub Copilot CLI", command="copilot",
        install=[["plugin", "marketplace", "add", "{repo}#{branch}"], ["plugin", "install", "{plugin}@{catalog}"]],
        update=[["plugin", "update", "{plugin}"]]),
    # Pi. Docs https://docs.pi.dev/latest/packages (`pi install git:github.com/o/r@ref`; personal installs are recorded
    # in ~/.pi/agent/settings.json; `pi update` never moves a configured ref, so an update is the install again).
    # Lane C ran the install from a local copy; not run against GitHub here.
    App("pi", "Pi", command="pi",
        install=[["install", "git:github.com/{repo}@{branch}"]], update=[["install", "git:github.com/{repo}@{branch}"]],
        local=[["install", "{folder}"]], installed=_pi_installed),
    # Muse (Meta's Muse Code). From superpowers' practice and Muse's changelog; not run. It installs a plugin from a local
    # folder and copies it into its own cache (so the fetched `latest` is temporary), then `approve` lets it load;
    # `update <name>`, else the install again. It reads .muse-plugin/plugin.json.
    App("muse", "Muse", command="muse",
        install=[["plugins", "install", "{fetched}"], ["plugins", "approve", "{plugin}"]],
        update=[["plugins", "update", "{plugin}"]],
        local=[["plugins", "install", "{folder}"], ["plugins", "approve", "{plugin}"]]),
    # Agents with no plugin command: the skills copied into each one's own folder, where each one's docs (or, for
    # Windsurf and Goose, the Skills CLI's agent table and our earlier installers) say it reads them. Not run.
    _folder_agent("cline", "Cline", lambda h: h.home / ".cline" / "skills", lambda h: h.home / ".cline"),
    _folder_agent("amp", "Amp", lambda h: h.config_home() / "amp" / "skills", lambda h: h.config_home() / "amp"),
    _folder_agent("openclaw", "OpenClaw", lambda h: h.home / ".openclaw" / "skills", lambda h: h.home / ".openclaw"),
    _folder_agent("kilo", "Kilo Code", lambda h: h.home / ".kilo" / "skills", lambda h: h.home / ".kilo",
                  lambda h: h.home / ".kilocode"),
    _folder_agent("kiro", "Kiro CLI", lambda h: h.home / ".kiro" / "skills", lambda h: h.home / ".kiro"),
    _folder_agent("roo", "Roo Code", lambda h: h.home / ".roo" / "skills", lambda h: h.home / ".roo"),
    _folder_agent("trae", "Trae", lambda h: h.home / ".trae" / "skills", lambda h: h.home / ".trae"),
    _folder_agent("windsurf", "Windsurf", lambda h: h.home / ".codeium" / "windsurf" / "skills",
                  lambda h: h.home / ".codeium" / "windsurf"),
    _folder_agent("goose", "Goose", lambda h: h.config_home() / "goose" / "skills", lambda h: h.config_home() / "goose"),
    _folder_agent("opencode", "OpenCode", lambda h: h.config_home() / "opencode" / "skills",
                  lambda h: h.config_home() / "opencode"),
)


# --- the run ------------------------------------------------------------------------------------------


def latest(here: Here) -> str:
    """The newest release the feed names, never older than ``FALLBACK``; ``FALLBACK`` when it cannot be read."""
    try:
        with urllib.request.urlopen(here.environ.get("CAD_INSTALL_FEED") or FEED, timeout=5) as answer:
            named = json.loads(answer.read().decode("utf-8")).get("latest")
    except Exception:  # noqa: BLE001 - any failure to read the feed means the fallback
        return FALLBACK
    if not isinstance(named, str) or not _VERSION.fullmatch(named) or version_key(named) < version_key(FALLBACK):
        return FALLBACK
    return named


def cad_setup(here: Here, release: str) -> bool:
    """That release's ``cad setup`` through uvx, its output shown as it runs. Whether it worked."""
    uvx = here.which("uvx")
    if not uvx:
        print("cad setup: failed: uvx was not found (install uv: https://docs.astral.sh/uv/)", flush=True)
        return False
    named = here.environ.get("CAD_INSTALL_FROM")
    requirement = ["--from", named] if named else ["--refresh-package", "cad-server", "--refresh-package", "cad",
                                                    "--from", f"cad-server=={release}"]
    try:
        code = subprocess.call([uvx, *UVX_ARGS, *requirement, "cad", "setup"], env=here.environ,
                               stdin=subprocess.DEVNULL)
    except OSError as error:
        print(f"cad setup: failed: {error}", flush=True)
        return False
    if code:
        print(f"cad setup: failed (exit status {code}); what it said is above", flush=True)
    return code == 0


def install_apps(here: Here, source: Source, apps: Sequence[App] = APPS) -> List[str]:
    """Steps 3 and 4 for ``apps``: old copies out, ours in. One line per app found; one for the loose skills; one
    naming the apps not found."""
    context = Context(source)
    lines, missing = [], []
    try:
        loose = remove_loose_skills(here)
    except (OSError, Failed) as error:
        loose = Outcome("failed", str(error))
    if loose is not QUIET:
        lines.append(loose.line("Loose skills"))
    for app in apps:
        try:
            outcome = app.run(here, context)
        except Failed as error:
            outcome = Outcome("failed", str(error))
        except OSError as error:
            outcome = Outcome("failed", f"{type(error).__name__}: {error}")
        if outcome is NOT_FOUND:
            missing.append(app.name)
        elif outcome is not QUIET:
            lines.append(outcome.line(app.name))
    if missing:
        lines.append(f"Not found here: {', '.join(missing)}")
    return lines


def main(argv: Optional[Sequence[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv:
        print("This installer takes no options: run it as it is to install or update text-to-cad in every agent app "
              "on this computer. To remove text-to-cad, run `cad uninstall`, and each app's own remove command.",
              file=sys.stderr)
        return 2
    here = Here()
    release = latest(here)
    print(f"Installing text-to-cad {release}. The first run downloads it, which takes a minute.", flush=True)
    ok = cad_setup(here, release)
    source = Source()
    try:
        lines = install_apps(here, source)
    finally:
        source.close()
    print("", flush=True)
    for line in lines:
        print(line, flush=True)
    print("Start a new session in each app to use it." if ok else
          "text-to-cad itself was not installed: run this again, or see what cad setup said above.", flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
