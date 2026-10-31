"""The agent apps text-to-cad installs into, read and changed the way each one keeps its plugins.

``cad setup`` (``cad_server.cli.setup``) asks this module what is on the machine and what to do
about it, and a checkout's development installer loads this same file by its path: both installers
find every app, every copy of the plugin and every app's own commands the same way. Every app with a
plugin gets it from the plugin folder the server writes, ``<state>/plugin``
(``cad_server._internal.plugin``: the repository root's plugin layout, its catalog a local one,
``texttocad``), each the way that app keeps a local plugin. Six apps:

- **Claude Code**: the folder added as a local-directory marketplace and its plugin installed,
  ``text-to-cad@texttocad``, through ``claude plugin``. Its sessions read the folder in place, so a
  folder written again is what the next session reads, with no command; its cached copy, which
  ``claude plugin list`` reports and Cursor and Grok Build may read, is brought along by ``claude
  plugin update``. Cursor and Grok Build load the plugins Claude Code installed as well as their own
  (``FED_BY``), so where Claude Code has the plugin they need none of their own, and a copy of
  theirs is a second copy.
- **Claude Desktop** (its chat): CAD's server alone, ``mcpServers.cad`` in its config file, run by
  ``uvx`` at its absolute path, since an app opened from the Dock has no shell's PATH: the person's uvx
  (on PATH, else where uv's installer or Homebrew puts it), never one uv keeps in its cache or a release
  folder holds (``transient``), which go from under it.
  A switch of the engine moves it to the release it leaves current, back as much as forward
  (``refresh_plan``).
- **Codex**: the same local marketplace through its own ``plugin`` command (the app bundles a CLI of
  its own). Codex copies a local marketplace's plugin when it is added and never again by itself, so
  every update adds it again; a running session keeps the copy it started with.
- **Cursor**: a copy of the folder, real files, in its local plugins folder
  (``~/.cursor/plugins/local/text-to-cad``), copied again at every update; never where Claude Code
  feeds it.
- **Grok Build**: ``grok plugin``, from the repository's ``latest``, where Claude Code does not feed it.
- **Gemini CLI**: its extension, the folder linked (``gemini extensions link``): it reads it in place.

Nothing installed this way updates by itself: an update is the person's (``cad update``, the install
command, the update button), and the folder and the copies follow the release it makes current.
The copies an earlier release's installer made from the repository's ``latest`` branch on GitHub (the
``earthtojake`` catalog, a Cursor clone, a Gemini extension installed from it) are second copies now:
taken out, the catalog with them.

Every other agent the Skills CLI (``npx skills``) knows and that is installed here gets the skills
alone, copied from the folder's ``skills/`` into that agent's own skills folder by one ``npx skills
add`` for all of them (``SKILLS_AGENTS``: each one's folder and how it is detected, as that CLI reads
them). The CLI keeps no versions, so the receipt says which agents got which skills (those its
``--json`` says it installed) from which release; a later run adds them again for an agent when that
release is not this one or one of those skills is missing from its folder.
An app with a plugin path is never one of them.

A second copy loads every skill twice: the plugin from another catalog (a checkout's development
install, the GitHub catalog), this repository's skills installed loose, a server someone added by hand
that runs text-to-cad. The plan removes it, the loose skills moved aside rather than deleted, and out of
the Skills CLI's record where it installed them from GitHub (``unlock_skill``: its ``update`` would put
them back). A loose skill is ours when its ``SKILL.md`` names one of this repository's skills
(``SKILLS``) and says where it is maintained (``PROVENANCE``). The one folder two kinds of agent share,
``~/.agents/skills`` (Codex and Gemini CLI read it; it is Cline's and Zed's own), is the Skills CLI
agent's while one that uses it is here: Codex and Gemini CLI then list those skills beside their
plugin's, which the plan says. A store's copy (claude.ai's directory, the app directory of Codex's
maker, the Cursor Marketplace) is the store's to update and to remove: it is reported, never touched,
and no copy of ours is added beside it.

Nothing here imports the packages, and the file parses on any Python 3 the development installer may
run on. Every path comes from a :class:`Machine` -- its home, its environment, its platform and how it
runs a command -- and the plugin folder is passed in, so a test reads a temporary home with fake
commands on a temporary PATH.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

PLUGIN = "text-to-cad"
REPOSITORY = "earthtojake/text-to-cad"
REPOSITORY_URL = f"https://github.com/{REPOSITORY}"
# The branch installs by hand follow: the plugin alone, one commit per release, never ahead of PyPI.
BRANCH = "latest"
# The plugin folder's catalog, as Claude Code and Codex name it, and the plugin's id in it
# (``cad_server._internal.plugin.MARKETPLACE``: a test holds the two equal).
MARKETPLACE = "texttocad"
PLUGIN_ID = f"{PLUGIN}@{MARKETPLACE}"
# The repository's catalog on GitHub, which an earlier release's installer added: a copy from it is a
# second copy now.
GITHUB_MARKETPLACE = "earthtojake"
# The file the installer marks its copy of the folder in Cursor's local plugins folder with: where it was
# copied from, its version and when.
COPY_MARK = ".text-to-cad-copy"
# Every SKILL.md of this repository's says where it is maintained; a loose skill saying so, under
# one of this repository's skill names (its skills/ folder), is ours.
PROVENANCE = REPOSITORY
SKILLS = ("bambu-labs", "cad", "dfam-check", "dfm", "dxf", "engineering-drawing", "gcode", "sdf", "sendcutsend",
          "srdf", "step-parts", "urdf")
# Claude Desktop's server key, and the variable its server is told its install channel by.
DESKTOP_KEY = "cad"
# A checkout's development install (its installer): its catalog, and the file it marks its Cursor copy with.
DEV_MARKETPLACE = "earthtojake-dev"
DEV_MARK = ".text-to-cad-dev"
# Stores: Claude Code's official catalog, which claude.ai's directory installs from, and the scopes
# claude.ai syncs or an administrator manages; Codex's maker's directory catalogs; the Cursor
# Marketplace's cache.
CLAUDE_STORES = frozenset({"claude-plugins-official"})
CLAUDE_STORE_SCOPES = frozenset({"managed", "synced"})
CODEX_STORE_PREFIX = "openai-"
CURSOR_STORE = "the Cursor Marketplace"

APPS = ("claude", "claude-desktop", "codex", "cursor", "grok", "gemini")
# The apps pointed at the plugin folder (each reads it in place, links it or keeps a copy of it).
POINTED = ("claude", "codex", "cursor", "gemini")
LABELS = {"claude": "Claude Code", "claude-desktop": "Claude Desktop", "codex": "Codex", "cursor": "Cursor",
          "grok": "Grok Build", "gemini": "Gemini CLI"}
# Cursor and Grok Build load the plugins Claude Code installed, beside their own.
FED_BY = {"cursor": "claude", "grok": "claude"}
# The apps the doctor's report reads (its host inventory): Grok Build's own storage is not among them.
INVENTORIED = frozenset({"claude", "claude-desktop", "codex", "cursor", "gemini"})
# What a person does for an app to pick up a changed plugin: never done for them.
RESTART = {
    "claude": "Claude Code: start a new session (a running one keeps the plugin it started with)",
    "claude-desktop": "Claude Desktop: quit and reopen it",
    "codex": "Codex: restart the app, and any terminal or IDE session (a running one keeps the copy it started with)",
    "cursor": "Cursor: reload the window",
    "grok": "Grok Build: start a new session",
    "gemini": "Gemini CLI: start a new session",
}
# The CLIs an app bundles, for an app whose terminal command may be missing or older.
BUNDLED = {"codex": ("/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex",)}
# Where Homebrew puts the commands it installs (Apple silicon's, Intel macOS's, Linux's): never on the PATH of
# an app opened from the Dock or a menu, nor of the engine such an app starts (``uvx``).
HOMEBREW = ("/opt/homebrew/bin", "/usr/local/bin", "/home/linuxbrew/.linuxbrew/bin")
# A native command may clone a repository; a listing answers at once or is broken.
COMMAND_SECONDS = 900
LIST_SECONDS = 120
_RELEASE = re.compile(r"\d+(?:\.\d+)*")


# --- the machine --------------------------------------------------------------------------------


@dataclass
class Ran:
    """A command's run: what it was, its exit status and what it printed."""

    argv: List[str]
    code: int
    out: str = ""
    err: str = ""

    @property
    def ok(self) -> bool:
        return self.code == 0

    def said(self, limit: int = 4000) -> str:
        """What it printed, both streams, the last ``limit`` characters."""
        text = "\n".join(part.strip() for part in (self.out, self.err) if part and part.strip())
        return text[-limit:]


class CommandFailed(subprocess.CalledProcessError):
    """A listing that failed: a ``CalledProcessError``, as the development installer reports one."""


def _text(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return value or ""


def _subprocess(argv: List[str], environ: Dict[str, str], timeout: float) -> Ran:
    try:
        done = subprocess.run(argv, env=environ, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, timeout=timeout)
    except subprocess.TimeoutExpired as expired:
        return Ran(argv, 124, _text(expired.stdout), _text(expired.stderr) + f"\nno answer in {int(timeout)} s")
    except OSError as error:
        return Ran(argv, 127, "", f"{type(error).__name__}: {error}")
    return Ran(argv, done.returncode, _text(done.stdout), _text(done.stderr))


class Machine:
    """Where the apps live and how a command runs: the home, the environment (its PATH finds the
    apps' commands), the platform, the CLIs apps bundle, Homebrew's folders, and the runner.
    :meth:`here` is this one."""

    def __init__(self, home: Any, environ: Mapping[str, str], platform: str = sys.platform,
                 bundled: Optional[Mapping[str, Sequence[str]]] = None,
                 runner: Optional[Callable[[List[str], Dict[str, str], float], Ran]] = None,
                 homebrew: Optional[Sequence[str]] = None) -> None:
        self.home = Path(home)
        self.environ = dict(environ)
        self.platform = platform
        self.bundled = BUNDLED if bundled is None else bundled
        self.homebrew = HOMEBREW if homebrew is None else homebrew
        self._runner = runner or _subprocess

    @classmethod
    def here(cls) -> "Machine":
        return cls(Path.home(), os.environ)

    @property
    def windows(self) -> bool:
        return self.platform == "win32"

    def which(self, name: str) -> Optional[str]:
        return shutil.which(name, path=self.environ.get("PATH", os.defpath))

    def run(self, argv: Sequence[str], timeout: float = COMMAND_SECONDS) -> Ran:
        return self._runner([str(part) for part in argv], dict(self.environ), timeout)

    def listing(self, argv: Sequence[str]) -> str:
        """What a listing command prints; ``CommandFailed`` when it fails."""
        ran = self.run(argv, LIST_SECONDS)
        if not ran.ok:
            raise CommandFailed(ran.code, ran.argv, ran.out, ran.err)
        return ran.out


def _machine(machine: Optional[Machine]) -> Machine:
    return machine if machine is not None else Machine.here()


def shown(path: Any, machine: Optional[Machine] = None) -> str:
    """``path`` as a person reads it: the home folder spelled ``~``."""
    text, home = str(path), str(_machine(machine).home)
    if home and (text == home or text.startswith(home.rstrip("/\\") + os.sep)):
        return "~" + text[len(home.rstrip("/\\")):]
    return text


def command_text(argv: Sequence[str], machine: Optional[Machine] = None) -> str:
    """A command as a person would type it: its program by name where PATH finds that one."""
    words = [str(part) for part in argv]
    if words:
        name = os.path.basename(words[0])
        stem = os.path.splitext(name)[0] if _machine(machine).windows else name
        if _machine(machine).which(stem) == words[0]:
            words[0] = stem
        else:
            words[0] = shown(words[0], machine)
    if _machine(machine).windows:
        return subprocess.list2cmdline(words)
    import shlex

    return " ".join("~/" + shlex.quote(word[2:]) if word.startswith("~/") else shlex.quote(word) for word in words)


def version_key(text: Optional[str]) -> Tuple[int, ...]:
    """A release's numbers (``0.8.3`` -> ``(0, 8, 3)``); a development build's are its release's."""
    found = _RELEASE.match(text or "")
    return tuple(int(part) for part in found.group(0).split(".")) if found else ()


def is_release(text: Optional[str]) -> bool:
    return bool(text) and _RELEASE.fullmatch(text or "") is not None


# --- where each app keeps its things ------------------------------------------------------------


def claude_dir(machine: Optional[Machine] = None) -> Path:
    machine = _machine(machine)
    return Path(machine.environ.get("CLAUDE_CONFIG_DIR") or machine.home / ".claude")


def claude_json(machine: Optional[Machine] = None) -> Path:
    """Claude Code's user-scoped servers: ``~/.claude.json``, or in ``CLAUDE_CONFIG_DIR`` when set."""
    machine = _machine(machine)
    folder = machine.environ.get("CLAUDE_CONFIG_DIR")
    return Path(folder) / ".claude.json" if folder else machine.home / ".claude.json"


def codex_home(machine: Optional[Machine] = None) -> Path:
    machine = _machine(machine)
    return Path(machine.environ.get("CODEX_HOME") or machine.home / ".codex")


def cursor_plugins(machine: Optional[Machine] = None) -> Path:
    """Cursor's local plugins folder: it follows no symlink out of it, so a plugin there is a real copy."""
    return _machine(machine).home / ".cursor" / "plugins" / "local"


def desktop_config(machine: Optional[Machine] = None) -> Path:
    """Claude Desktop's config file: ``CLAUDE_DESKTOP_CONFIG``, else its own, per platform."""
    machine = _machine(machine)
    if machine.environ.get("CLAUDE_DESKTOP_CONFIG"):
        return Path(machine.environ["CLAUDE_DESKTOP_CONFIG"])
    if machine.platform == "darwin":
        return machine.home / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    if machine.windows:
        roaming = machine.environ.get("APPDATA") or str(machine.home / "AppData" / "Roaming")
        return Path(roaming) / "Claude" / "claude_desktop_config.json"
    return machine.home / ".config" / "Claude" / "claude_desktop_config.json"


def skill_folders(host: str, machine: Optional[Machine] = None) -> List[Path]:
    """The user-level skill folders ``host`` loads skills from, as each app was seen to."""
    machine = _machine(machine)
    home, claude = machine.home, claude_dir(machine)
    return {
        # Cursor and Grok Build load Claude Code's plugins, so a Claude Code install reaches theirs too.
        "claude": [claude / "skills", home / ".cursor" / "skills", home / ".grok" / "skills"],
        "codex": [codex_home(machine) / "skills", shared_skills(machine)],
        "cursor": [home / ".cursor" / "skills"],
        "grok": [home / ".grok" / "skills", claude / "skills"],
        "gemini": [gemini_dir(machine) / "skills", shared_skills(machine)],
    }[host]


def shared_skills(machine: Optional[Machine] = None) -> Path:
    """``~/.agents/skills``: Codex and Gemini CLI read it, and it is some Skills CLI agents' own."""
    return _machine(machine).home / ".agents" / "skills"


# The skill folders each app owns: a loose skill found in one is that app's to move aside, unless
# the folder is a Skills CLI agent's here (``_claimed``).
def _own_skill_folders(host: str, machine: Machine) -> List[Path]:
    return {"claude": [claude_dir(machine) / "skills"], "codex": [codex_home(machine) / "skills", shared_skills(machine)],
            "cursor": [machine.home / ".cursor" / "skills"], "grok": [machine.home / ".grok" / "skills"],
            "gemini": [gemini_dir(machine) / "skills", shared_skills(machine)]}.get(host, [])


# --- the agents without a plugin: the skills through the Skills CLI ----------------------------

# The command, which npx takes from its cache where it has it (no network for an update), and what it
# adds: the plugin folder's skills, every one (``skills_source``). Never ``--all``, which is every
# agent too, the apps with a plugin among them: every skill twice there.
SKILLS_CLI = ("npx", "--prefer-offline", "-y", "skills@latest")
NEED_NODE = "the skills need Node (npx): install Node, then run this again"


def skills_source(folder: Any) -> str:
    """What ``npx skills add`` copies the skills from: the plugin folder's ``skills/``."""
    return str(Path(folder) / "skills")


def _config_home(machine: Machine) -> Path:
    """The Skills CLI's ``configHome``: ``XDG_CONFIG_HOME``, else ``~/.config``, on every platform."""
    return Path(machine.environ.get("XDG_CONFIG_HOME") or machine.home / ".config")


def _hermes_home(machine: Machine) -> Path:
    return Path((machine.environ.get("HERMES_HOME") or "").strip() or machine.home / ".hermes")


def _openclaw(machine: Machine) -> Path:
    """OpenClaw's folder: the first of its three names that exists, else ``~/.openclaw``."""
    names = [machine.home / name for name in (".openclaw", ".clawdbot", ".moltbot")]
    return next((path for path in names if path.exists()), names[0])


def _zed(machine: Machine) -> List[Path]:
    appdata, flatpak = (machine.environ.get(key, "").strip() for key in ("APPDATA", "FLATPAK_XDG_CONFIG_HOME"))
    return [_config_home(machine) / "zed"] + ([Path(appdata) / "Zed"] if appdata else []) \
        + ([Path(flatpak) / "zed"] if flatpak else [])


# The agents the Skills CLI knows that have no plugin of ours, as its agent table has them (skills
# 1.7.4, dist/cli.mjs): its id, its display name, its global skills folder (``globalSkillsDir``),
# and the paths any one of which, existing, is the agent installed (``detectInstalled``). Never
# Claude Code, Cursor, Codex, Gemini CLI or Grok Build: they have the plugin.
SKILLS_AGENTS: Dict[str, Tuple[str, Callable[[Machine], Path], Callable[[Machine], List[Path]]]] = {
    # VS Code's agent is GitHub Copilot: it reads ~/.copilot/skills as well.
    "github-copilot": ("GitHub Copilot", lambda m: m.home / ".copilot" / "skills", lambda m: [m.home / ".copilot"]),
    "windsurf": ("Windsurf", lambda m: m.home / ".codeium" / "windsurf" / "skills",
                 lambda m: [m.home / ".codeium" / "windsurf"]),
    "cline": ("Cline", shared_skills, lambda m: [m.home / ".cline"]),
    "amp": ("Amp", lambda m: _config_home(m) / "agents" / "skills", lambda m: [_config_home(m) / "amp"]),
    "antigravity": ("Antigravity", lambda m: m.home / ".gemini" / "antigravity" / "skills",
                    lambda m: [m.home / ".gemini" / "antigravity"]),
    "antigravity-cli": ("Antigravity CLI", lambda m: m.home / ".gemini" / "antigravity-cli" / "skills",
                        lambda m: [m.home / ".gemini" / "antigravity-cli"]),
    "openclaw": ("OpenClaw", lambda m: _openclaw(m) / "skills",
                 lambda m: [m.home / name for name in (".openclaw", ".clawdbot", ".moltbot")]),
    "droid": ("Droid", lambda m: m.home / ".factory" / "skills", lambda m: [m.home / ".factory"]),
    "goose": ("Goose", lambda m: _config_home(m) / "goose" / "skills", lambda m: [_config_home(m) / "goose"]),
    "kilo": ("Kilo Code", lambda m: m.home / ".kilo" / "skills", lambda m: [m.home / ".kilo", m.home / ".kilocode"]),
    "kiro-cli": ("Kiro CLI", lambda m: m.home / ".kiro" / "skills", lambda m: [m.home / ".kiro"]),
    "hermes-agent": ("Hermes Agent", lambda m: _hermes_home(m) / "skills", lambda m: [_hermes_home(m)]),
    "opencode": ("OpenCode", lambda m: _config_home(m) / "opencode" / "skills", lambda m: [_config_home(m) / "opencode"]),
    "roo": ("Roo Code", lambda m: m.home / ".roo" / "skills", lambda m: [m.home / ".roo"]),
    "trae": ("Trae", lambda m: m.home / ".trae" / "skills", lambda m: [m.home / ".trae"]),
    "zed": ("Zed", shared_skills, _zed),
}


def label(name: str) -> str:
    """An app's or a Skills CLI agent's name as a person reads it."""
    return LABELS.get(name) or (SKILLS_AGENTS[name][0] if name in SKILLS_AGENTS else name)


def skills_folder(agent: str, machine: Optional[Machine] = None) -> Path:
    return SKILLS_AGENTS[agent][1](_machine(machine))


def skills_agents(machine: Optional[Machine] = None) -> Dict[str, Path]:
    """The Skills CLI agents installed here, each with its skills folder, in ``SKILLS_AGENTS`` order."""
    machine = _machine(machine)
    return {agent: folder(machine) for agent, (_label, folder, marks) in SKILLS_AGENTS.items()
            if any(path.exists() for path in marks(machine))}


def _claimed(machine: Machine) -> set:
    """The skills folders that are a Skills CLI agent's here: never another app's second copy."""
    return {str(folder) for folder in skills_agents(machine).values()}


def ours_in(folder: Path) -> List[Path]:
    """This repository's skills in ``folder``, in ``SKILLS`` order."""
    found = set(loose_skills([folder]))
    return [path for path in (Path(folder) / name for name in SKILLS) if path in found]


def skills_installed(printed: str) -> Optional[List[str]]:
    """The skills ``npx skills add --json`` says it installed (``"status": "installed"``), or
    ``None`` when what it printed is not that list."""
    text = printed.strip()
    try:
        results = json.loads(text[text.find("["):] if "[" in text else text)
    except ValueError:
        return None
    if not isinstance(results, list):
        return None
    return [item["name"] for item in results if isinstance(item, dict) and item.get("status") == "installed"
            and isinstance(item.get("name"), str)]


# --- the commands -------------------------------------------------------------------------------


def find_cli(name: str, machine: Optional[Machine] = None) -> Optional[str]:
    """``<NAME>_CLI``, else ``name`` on PATH."""
    machine = _machine(machine)
    return machine.environ.get(f"{name.upper()}_CLI") or machine.which(name)


# uv keeps the environments uvx makes in its cache's ``archive-v<N>`` folder, which ``uv cache clean`` (or
# prune) removes; a release folder of text-to-cad's has its marker at its root, and an update removes the ones
# it no longer needs (``cad_server._internal.releases``).
_UV_ARCHIVE = re.compile(r"archive-v\d+")
RELEASE_MARKER = "cadgen-release.json"


def _within(path: str, folder: str) -> bool:
    path, folder = os.path.normcase(path), os.path.normcase(folder.rstrip("/\\"))
    return bool(folder) and (path == folder or path.startswith(folder + os.sep))


def transient(path: Any) -> bool:
    """Whether ``path`` (a program, or a folder on PATH) is in an environment that comes and goes, never one
    the person keeps: this process's own virtual environment (``sys.prefix``: uvx's, as the install command
    runs ``cad setup``), one uv keeps in its cache (``archive-v<N>``), or a release folder of text-to-cad's.
    A command named by its path there may be gone tomorrow."""
    plain = os.path.abspath(str(path))
    own = {sys.prefix, os.path.realpath(sys.prefix)} if sys.prefix != sys.base_prefix else set()
    for where in {plain, os.path.realpath(plain)}:
        if any(_within(where, prefix) for prefix in own):
            return True
        if any(_UV_ARCHIVE.fullmatch(part) for part in Path(where).parts):
            return True
        parent = os.path.dirname(where)
        if any(os.path.isfile(os.path.join(folder, RELEASE_MARKER)) for folder in (parent, os.path.dirname(parent))):
            return True
    return False


def lasting(path: str) -> str:
    """A PATH without its transient folders (``transient``): where the person's own commands are found."""
    return os.pathsep.join(entry for entry in path.split(os.pathsep) if entry and not transient(entry))


def uvx(machine: Optional[Machine] = None) -> Optional[str]:
    """uvx at its absolute path, which an app opened from the Dock or the Start menu needs, and one that
    stays (never ``transient``: a ``uv cache clean`` or an update would take it from under the app): the
    first on PATH, else where uv's own installer puts it, else where Homebrew does (``uv_folders``) --
    an engine a GUI app started has none of the person's PATH."""
    machine = _machine(machine)
    name = "uvx.exe" if machine.windows else "uvx"
    for folder in lasting(machine.environ.get("PATH", os.defpath)).split(os.pathsep):
        found = shutil.which("uvx", path=folder) if folder else None
        if found and not transient(found):
            return os.path.abspath(found)
    for folder in uv_folders(machine):
        for candidate in (Path(folder) / name, Path(folder) / "bin" / name):
            if candidate.is_file() and os.access(candidate, os.X_OK) and not transient(candidate):
                return str(candidate)
    return None


def uv_folders(machine: Optional[Machine] = None) -> List[str]:
    """Where uv is when PATH has no say, in order: where its own installer puts it (``UV_INSTALL_DIR``,
    ``XDG_BIN_HOME``, ``$XDG_DATA_HOME/../bin``, ``~/.local/bin``; ``~/.cargo/bin`` before uv 0.5), then
    Homebrew's folders (``Machine.homebrew``), but on Windows."""
    machine = _machine(machine)
    environ, home = machine.environ, machine.home
    data = environ.get("XDG_DATA_HOME")
    folders = [environ.get("UV_INSTALL_DIR"), environ.get("XDG_BIN_HOME"), str(Path(data).parent / "bin") if data else None,
               str(home / ".local" / "bin"), str(home / ".cargo" / "bin"), *(() if machine.windows else machine.homebrew)]
    return [folder for folder in folders if folder]


def codex_cli(machine: Optional[Machine] = None) -> Optional[str]:
    """``CODEX_CLI``, else the newer of the ``codex`` on PATH and the one the app bundles.

    Both write the same ``~/.codex``, which the app, the terminal CLI and the IDE extension share,
    so an install must come from a CLI at least as new as the app that reads it.
    """
    machine = _machine(machine)
    if machine.environ.get("CODEX_CLI"):
        candidates = [machine.environ["CODEX_CLI"]]
    else:
        candidates = [path for path in (machine.which("codex"), *machine.bundled.get("codex", ()))
                      if path and os.access(path, os.X_OK)]
    versions = {}
    for path in candidates:
        ran = machine.run([path, "--version"], LIST_SECONDS)
        words = ran.out.split()
        if ran.ok and words and version_key(words[-1]):
            versions[path] = version_key(words[-1])
    return max(versions, key=versions.get) if versions else None


# --- reading files ------------------------------------------------------------------------------


def _json(path: Path) -> Tuple[Any, Optional[str]]:
    """``(data, problem)``: a file's JSON, ``None`` with no problem for a missing or empty file."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None, None
    except (OSError, UnicodeError) as error:
        return None, f"cannot be read ({type(error).__name__})"
    if not text.strip():
        return None, None
    try:
        return json.loads(text), None
    except ValueError:
        return None, "is not plain JSON (comments or a syntax error); edit it by hand"


def _toml(path: Path) -> Tuple[Optional[dict], Optional[str]]:
    try:
        import tomllib
    except ImportError:  # Python 3.10 and before: the development installer reads no TOML
        return None, "cannot be read by this Python"
    try:
        with open(path, "rb") as handle:
            return tomllib.load(handle), None
    except FileNotFoundError:
        return None, None
    except (OSError, ValueError) as error:
        return None, f"cannot be read ({type(error).__name__})"


# What a server entry of text-to-cad's names: the requirement uvx runs it from -- this release's transport
# (``texttocad-mcp==X``), or an earlier release's server (``cadgen==X``) --, the command it runs (``cad-mcp``,
# an earlier release's ``cadgen``), or the module a checkout's Python runs (``python -m cad_mcp``; an earlier
# one's ``cad_server.cli`` or ``cadgen.cli``, with ``mcp``).
PINS = ("texttocad-mcp==", "texttocad-server==", "cadgen==")
ENTRY_WORDS = ("cad-mcp", "cadgen", "cad_mcp", "cad_server.cli", "cadgen.cli")


def runs_cadgen(entry: Any) -> bool:
    """Whether a server entry is text-to-cad's: its command is its transport's or an earlier release's
    server's, or its arguments name one (``PINS``, ``ENTRY_WORDS``)."""
    if not isinstance(entry, dict):
        return False
    command = entry.get("command")
    arguments = entry.get("args") if isinstance(entry.get("args"), list) else []
    if isinstance(command, str) and ("cadgen" in os.path.basename(command)
                                     or os.path.basename(command).lower().removesuffix(".exe") == "cad-mcp"):
        return True
    return any(isinstance(word, str) and (word.startswith(PINS) or word in ENTRY_WORDS) for word in arguments)


def server_pin(entry: Any) -> Optional[str]:
    """The release a server entry runs (``texttocad-mcp==X``, or an earlier release's ``cadgen==X``, in its
    arguments), or ``None``."""
    for word in (entry or {}).get("args") or []:
        if isinstance(word, str) and word.startswith(PINS):
            return word.partition("==")[2]
    return None


def _same_repository(source: Any) -> bool:
    """Whether a git source names this repository: ``owner/repo``, its URL, with or without ``.git``."""
    if not isinstance(source, str):
        return False
    text = source.strip().rstrip("/")
    if text.endswith(".git"):
        text = text[:-4]
    return text in (REPOSITORY, REPOSITORY_URL, f"git@github.com:{REPOSITORY}", f"github.com/{REPOSITORY}")


def _skill_name(text: str) -> Optional[str]:
    """The ``name`` in a ``SKILL.md``'s front matter."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    for line in lines[1:]:
        if line.strip() == "---":
            return None
        if line.startswith("name:"):
            return line[len("name:"):].strip().strip("\"'")
    return None


def loose_skills(folders: Iterable[Path]) -> List[Path]:
    """This repository's skills installed loose in ``folders`` (by the Skills CLI, or copied or linked
    by hand): a ``SKILL.md`` naming one of ``SKILLS`` that says where it is maintained."""
    found = []
    for folder in folders:
        for skill in sorted(Path(folder).glob("*/SKILL.md")) if Path(folder).is_dir() else []:
            try:
                text = skill.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if PROVENANCE in text and _skill_name(text) in SKILLS:
                found.append(skill.parent)
    return found


# --- what each app has: the development installer's listings ------------------------------------


def claude_installed(machine: Optional[Machine] = None, name: str = PLUGIN) -> List[str]:
    """The plugin ids Claude Code has installed for this plugin, any catalog."""
    machine = _machine(machine)
    claude = find_cli("claude", machine)
    if not claude:
        return []
    plugins = json.loads(machine.listing([claude, "plugin", "list", "--json"]) or "[]")
    return [plugin["id"] for plugin in plugins if str(plugin.get("id", "")).split("@")[0] == name]


def grok_installed(machine: Optional[Machine] = None, name: str = PLUGIN) -> List[str]:
    """Where each of Grok Build's installs of this plugin came from."""
    machine = _machine(machine)
    grok = find_cli("grok", machine)
    if not grok:
        return []
    plugins = json.loads(machine.listing([grok, "plugin", "list", "--json"]) or "[]")
    return [plugin.get("source") or plugin.get("path", "") for plugin in plugins if plugin.get("name") == name]


def gemini_installed(gemini: str, machine: Optional[Machine] = None, name: str = PLUGIN) -> List[str]:
    """Where each of Gemini CLI's installs of this extension came from (``Source:`` in its list)."""
    machine = _machine(machine)
    sources, current = [], None
    ran = machine.run([gemini, "extensions", "list"], LIST_SECONDS)
    if not ran.ok:
        raise CommandFailed(ran.code, ran.argv, ran.out, ran.err)
    # Gemini prints the list on stderr.
    for line in (ran.out + ran.err).splitlines():
        if line[:1] in ("✓", "✗"):
            current = line[1:].strip().split(" ")[0]
        elif current == name and line.strip().startswith("Source:"):
            sources.append(line.split("Source:", 1)[1].rsplit(" (Type:", 1)[0].strip())
    return sources


def _manifest_name(folder: Path) -> Optional[str]:
    for manifest in (folder / ".cursor-plugin" / "plugin.json", folder / "plugin.json"):
        data, _problem = _json(manifest)
        if isinstance(data, dict) and isinstance(data.get("name"), str):
            return data["name"]
    return None


def _manifest_version(folder: Path, *manifests: str) -> Optional[str]:
    for relative in manifests:
        data, _problem = _json(folder / relative)
        if isinstance(data, dict) and isinstance(data.get("version"), str):
            return data["version"]
    return None


def cursor_installed(machine: Optional[Machine] = None, name: str = PLUGIN) -> List[Path]:
    """Cursor's local plugin folders that hold this plugin."""
    folder = cursor_plugins(machine)
    return [path for path in sorted(folder.glob("*")) if folder.is_dir() and _manifest_name(path) == name]


# --- copies, apps and steps ---------------------------------------------------------------------


@dataclass
class Copy:
    """One copy of the plugin, or of its skills or its server, that an app loads."""

    app: str
    kind: str  # plugin, extension, folder, server, skills, store
    name: str  # a plugin id, an extension's or server's name, a folder
    version: Optional[str] = None
    path: Optional[str] = None
    detail: str = ""
    ours: bool = False  # the copy the release installs: from the plugin folder (Grok Build: the catalog on `latest`)
    store: bool = False  # a store's: reported, never touched
    removable: bool = True  # False: another scope's (a project's), reported and left
    entry: Optional[Dict[str, Any]] = None  # a server's entry, as its config holds it
    # Ours, from the plugin folder: the folder it reads or was copied from, how the app keeps it ("in
    # place", "linked" or "copied"), when a copy was made, and the release the app recorded at its
    # install where it reads the folder itself (Claude Code's cached copy).
    source: Optional[str] = None
    via: str = ""
    when: Optional[str] = None
    recorded: Optional[str] = None

    def words(self, machine: Optional[Machine] = None) -> str:
        what = {"server": f"the server {self.name}", "skills": f"loose skill {shown(self.name, machine)}",
                "folder": shown(self.name, machine), "store": shown(self.name, machine)}.get(self.kind, self.name)
        version = f" {self.version}" if self.version and self.kind not in ("skills", "folder", "store") else ""
        return f"{what}{version}" + (f" ({self.detail})" if self.detail else "")

    def origin(self, machine: Optional[Machine] = None) -> str:
        """Where an app's copy of ours comes from, as a person reads it: ``reads ~/x/plugin in place``,
        ``linked to ~/x/plugin``, ``a copy of ~/x/plugin, made 2026-10-31 02:41``."""
        where = shown(self.source, machine) if self.source else "the plugin folder"
        if self.via == "in place":
            return f"reads {where} in place"
        if self.via == "linked":
            return f"linked to {where}"
        if self.via == "copied":
            return f"a copy of {where}" + (f", made {self.when}" if self.when else "")
        return ""


@dataclass
class App:
    """What one app has: whether it is here, its command, every copy found, and what could not be read."""

    id: str
    present: bool = False
    command: Optional[str] = None
    seen: List[str] = field(default_factory=list)
    copies: List[Copy] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    marketplaces: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    config: Optional[str] = None
    unreadable: Optional[str] = None  # a config file this cannot edit, and why

    @property
    def label(self) -> str:
        return LABELS[self.id]

    def ours(self) -> Optional[Copy]:
        return next((copy for copy in self.copies if copy.ours), None)

    def stores(self) -> List[Copy]:
        return [copy for copy in self.copies if copy.store]


@dataclass
class Step:
    """One thing the plan does for an app: ``install``, ``update``, ``remove duplicate`` or ``leave``
    (``remove`` and the rest when uninstalling), with the commands it runs and the file it edits."""

    app: str
    action: str
    subject: str
    commands: List[List[str]] = field(default_factory=list)
    edit: Optional[Dict[str, Any]] = None
    note: str = ""  # how it is done, when not by a command of its own ("in the same edit")
    agents: List[str] = field(default_factory=list)  # the Skills CLI agents its command adds the skills for

    @property
    def label(self) -> str:
        return label(self.app)

    @property
    def changes(self) -> bool:
        return self.action != "leave"

    def data(self) -> Dict[str, Any]:
        return {"app": self.app, "label": self.label, "action": self.action, "subject": self.subject,
                "commands": [list(argv) for argv in self.commands], "edit": self.edit}


# --- what is on this machine --------------------------------------------------------------------


def _loose(app: App, machine: Machine) -> None:
    claimed = _claimed(machine)
    for skill in loose_skills(folder for folder in _own_skill_folders(app.id, machine) if str(folder) not in claimed):
        app.copies.append(Copy(app.id, "skills", str(skill), path=str(skill), detail="installed loose"))


def _servers(app: App, entries: Any, path: Path, ours: Optional[str] = None) -> None:
    """The entries of a ``mcpServers`` table that run text-to-cad: hand-made copies of CAD's server."""
    for key, entry in (entries.items() if isinstance(entries, dict) else ()):
        if runs_cadgen(entry):
            app.copies.append(Copy(app.id, "server", str(key), version=server_pin(entry), path=str(path),
                                   ours=key == ours, entry=entry, detail="" if key == ours else f"in {shown(path)}"))


def same_path(one: Any, other: Any) -> bool:
    """Whether two paths name one place (symlinks resolved, case folded where the platform folds it)."""
    if not one or not other:
        return False
    return os.path.normcase(os.path.realpath(str(one))) == os.path.normcase(os.path.realpath(str(other)))


def _points(market: Optional[Dict[str, Any]], folder: Any) -> bool:
    """Whether a catalog the app knows is the plugin folder (a local one at its path)."""
    return bool(market) and folder is not None and same_path(market.get("path"), folder)


def _catalog_detail(market: str, markets: Mapping[str, Dict[str, Any]]) -> str:
    """How a person tells a catalog that is not the plugin folder's."""
    if market == DEV_MARKETPLACE:
        return "a development install"
    found = markets.get(market) or {}
    if _same_repository(found.get("repo")):
        return f"from {REPOSITORY} on GitHub" + (f" at {found['ref']}" if found.get("ref") else "")
    return f"the {market} catalog"


def _stamp(path: Path) -> Optional[str]:
    """When ``path`` was last written, as a person reads it, or None."""
    try:
        return time.strftime("%Y-%m-%d %H:%M", time.localtime(path.stat().st_mtime))
    except OSError:
        return None


def _detect_claude(machine: Machine, folder: Optional[Path] = None) -> App:
    app = App("claude", command=find_cli("claude", machine))
    config = claude_dir(machine)
    if app.command:
        app.seen.append("the claude command")
    if config.is_dir():
        app.seen.append(shown(config, machine))
    app.present = bool(app.seen)
    if not app.present:
        return app
    plugins: Any = None
    if app.command:
        try:
            plugins = json.loads(machine.listing([app.command, "plugin", "list", "--json"]) or "[]")
            markets = json.loads(machine.listing([app.command, "plugin", "marketplace", "list", "--json"]) or "[]")
            for market in markets if isinstance(markets, list) else []:
                if isinstance(market, dict) and isinstance(market.get("name"), str):
                    local = market.get("source") == "directory"
                    app.marketplaces[market["name"]] = {
                        "repo": market.get("repo"), "ref": market.get("ref"),
                        "path": (market.get("path") or market.get("installLocation")) if local else None}
        except (CommandFailed, ValueError) as error:
            app.notes.append(f"could not list its plugins: {_failure(error)}")
            plugins = None
    if plugins is None:  # no command: the records Claude Code keeps
        recorded, _problem = _json(config / "plugins" / "installed_plugins.json")
        table = recorded.get("plugins") if isinstance(recorded, dict) else None
        plugins = [{"id": key, **entry} for key, entries in (table.items() if isinstance(table, dict) else ())
                   for entry in (entries if isinstance(entries, list) else []) if isinstance(entry, dict)]
        known, _problem = _json(config / "plugins" / "known_marketplaces.json")
        for name, entry in (known.items() if isinstance(known, dict) else ()):
            source = entry.get("source") if isinstance(entry, dict) else None
            if isinstance(source, dict):
                app.marketplaces[name] = {"repo": source.get("repo"), "ref": source.get("ref"),
                                          "path": source.get("path") if source.get("source") == "directory" else None}
    for plugin in plugins if isinstance(plugins, list) else []:
        identifier = str(plugin.get("id", "")) if isinstance(plugin, dict) else ""
        if identifier.split("@")[0] != PLUGIN:
            continue
        market = identifier.split("@", 1)[1] if "@" in identifier else ""
        scope = plugin.get("scope") or "user"
        store = market in CLAUDE_STORES or scope in CLAUDE_STORE_SCOPES
        ours = market == MARKETPLACE and scope == "user"
        detail = ("claude.ai's" if store else f"{scope} scope" if scope != "user"
                  else "" if ours else _catalog_detail(market, app.marketplaces))
        if ours:
            # It reads the folder in place: the folder's version is the one its sessions load, and the one
            # it recorded at install is its cached copy's (`claude plugin update` brings that along).
            read = plugin.get("readFromFolder") or (app.marketplaces.get(MARKETPLACE) or {}).get("path")
            app.copies.append(Copy("claude", "plugin", identifier, version=plugin.get("folderVersion") or plugin.get("version"),
                                   path=read or plugin.get("installPath"), ours=True, source=read,
                                   via="in place" if read else "", recorded=plugin.get("version")))
            continue
        app.copies.append(Copy("claude", "plugin", identifier, version=plugin.get("version"),
                               path=plugin.get("installPath"), detail=detail, store=store, removable=scope == "user"))
    servers, _problem = _json(claude_json(machine))
    if isinstance(servers, dict):
        _servers(app, servers.get("mcpServers"), claude_json(machine))
    _loose(app, machine)
    return app


def _codex_cache(home: Path, market: str) -> Optional[Path]:
    """Codex's copy of a catalog's plugin: its newest version's folder in the plugin cache."""
    cache = home / "plugins" / "cache" / market / PLUGIN
    versions = [path for path in cache.iterdir() if path.is_dir()] if cache.is_dir() else []
    return max(versions, key=lambda path: version_key(path.name)) if versions else None


def _detect_codex(machine: Machine, folder: Optional[Path] = None) -> App:
    app = App("codex", command=codex_cli(machine))
    home = codex_home(machine)
    if app.command:
        app.seen.append("the codex command" if machine.which("codex") == app.command else shown(app.command, machine))
    if home.is_dir():
        app.seen.append(shown(home, machine))
    app.present = bool(app.seen)
    if not app.present:
        return app
    config = home / "config.toml"
    data, problem = _toml(config)
    if problem:
        app.notes.append(f"{shown(config, machine)} {problem}")
    data = data or {}
    for name, entry in (data.get("marketplaces") or {}).items():
        if isinstance(entry, dict):
            local = entry.get("source_type") == "local"
            app.marketplaces[name] = {"repo": None if local else entry.get("source"), "ref": entry.get("ref"),
                                      "path": entry.get("source") if local else None}
    for identifier, entry in (data.get("plugins") or {}).items():
        if identifier.split("@")[0] != PLUGIN or "@" not in identifier:
            continue
        market = identifier.split("@", 1)[1]
        store = market.startswith(CODEX_STORE_PREFIX)
        ours = market == MARKETPLACE
        enabled = not isinstance(entry, dict) or entry.get("enabled", True) is not False
        detail = "its app directory's" if store else "" if ours else _catalog_detail(market, app.marketplaces)
        if not enabled:
            detail = ", ".join(word for word in (detail, "disabled") if word)
        cache = _codex_cache(home, market)
        app.copies.append(Copy("codex", "plugin", identifier, version=cache.name if cache else None, detail=detail,
                               store=store, ours=ours, path=str(cache) if cache else None,
                               source=(app.marketplaces.get(MARKETPLACE) or {}).get("path") if ours else None,
                               via="copied" if ours else "", when=_stamp(cache) if ours and cache else None))
    _servers(app, data.get("mcp_servers"), config)
    _loose(app, machine)
    return app


def _git_head(folder: Path) -> Tuple[Optional[str], Optional[str]]:
    """A clone's ``origin`` URL and branch, read from its ``.git`` files (no git run)."""
    try:
        head = (folder / ".git" / "HEAD").read_text(encoding="utf-8").strip()
        config = (folder / ".git" / "config").read_text(encoding="utf-8")
    except OSError:
        return None, None
    branch = head[len("ref: refs/heads/"):] if head.startswith("ref: refs/heads/") else None
    found = re.search(r'\[remote "origin"\][^\[]*?url\s*=\s*(\S+)', config)
    return (found.group(1) if found else None), branch


def copy_mark(path: Path) -> Dict[str, Any]:
    """The installer's mark in a copy of the plugin folder (``COPY_MARK``): ``{from, version, copied}``,
    or an empty dict for a folder it did not copy."""
    data, _problem = _json(Path(path) / COPY_MARK)
    return data if isinstance(data, dict) else {}


def _detect_cursor(machine: Machine, folder: Optional[Path] = None) -> App:
    app = App("cursor")
    home = machine.home / ".cursor"
    if home.is_dir():
        app.seen.append(shown(home, machine))
    if machine.which("cursor-agent"):
        app.seen.append("the cursor-agent command")
    app.present = bool(app.seen)
    if not app.present:
        return app
    for path in cursor_installed(machine):
        mark = copy_mark(path)
        origin, branch = _git_head(path)
        ours = bool(mark) and folder is not None and same_path(mark.get("from"), folder)
        detail = ("a development install" if (path / DEV_MARK).is_file() else "" if ours
                  else f"a copy of {shown(mark['from'], machine)}" if isinstance(mark.get("from"), str)
                  else f"a clone of {origin}" + (f" at {branch}" if branch else "") if origin else "copied by hand")
        app.copies.append(Copy("cursor", "folder", str(path), path=str(path), ours=ours, detail=detail,
                               version=_manifest_version(path, ".cursor-plugin/plugin.json", "plugin.json"),
                               source=str(folder) if ours else None, via="copied" if ours else "",
                               when=mark.get("copied") if ours else None))
    cache = home / "plugins" / "cache"
    for path in sorted(cache.glob(f"*/{PLUGIN}")) if cache.is_dir() else []:
        app.copies.append(Copy("cursor", "store", str(path), path=str(path), store=True, detail=CURSOR_STORE + "'s"))
    servers, problem = _json(home / "mcp.json")
    if problem:
        app.notes.append(f"{shown(home / 'mcp.json', machine)} {problem}")
    elif isinstance(servers, dict):
        _servers(app, servers.get("mcpServers"), home / "mcp.json")
    _loose(app, machine)
    return app


def _grok_refs(folder: Path) -> Dict[str, str]:
    """Each Grok Build install's folder and the git ref it follows, from its registry."""
    registry, _problem = _json(folder / "installed-plugins" / "registry.json")
    refs = {}
    for entry in ((registry or {}).get("repos") or {}).values() if isinstance(registry, dict) else ():
        kind = entry.get("kind") if isinstance(entry, dict) else None
        if isinstance(kind, dict) and isinstance(entry.get("path"), str):
            refs[entry["path"]] = kind.get("git_ref") or ""
    return refs


def _detect_grok(machine: Machine, folder: Optional[Path] = None) -> App:
    """Grok Build's copies: ours is still the repository's ``latest`` (it is not pointed at the plugin
    folder), where Claude Code does not feed it."""
    app = App("grok", command=find_cli("grok", machine))
    folder = machine.home / ".grok"
    if app.command:
        app.seen.append("the grok command")
    if folder.is_dir():
        app.seen.append(shown(folder, machine))
    app.present = bool(app.seen)
    if not app.present or not app.command:
        if app.present:
            _loose(app, machine)
        return app
    try:
        plugins = json.loads(machine.listing([app.command, "plugin", "list", "--json"]) or "[]")
    except (CommandFailed, ValueError) as error:
        app.notes.append(f"could not list its plugins: {_failure(error)}")
        plugins = []
    refs = _grok_refs(folder)
    for plugin in plugins if isinstance(plugins, list) else []:
        if not isinstance(plugin, dict) or plugin.get("name") != PLUGIN:
            continue
        source, path = plugin.get("source") or "", plugin.get("path") or ""
        ours = _same_repository(source) and refs.get(path) == BRANCH
        detail = "" if ours else f"from {shown(source, machine)}" if source else ""
        app.copies.append(Copy("grok", "plugin", PLUGIN, version=plugin.get("version"), path=path or None,
                               detail=detail, ours=ours))
    _loose(app, machine)
    return app


def gemini_dir(machine: Optional[Machine] = None) -> Path:
    """Gemini CLI's folder: ``.gemini`` in ``GEMINI_CLI_HOME``, which it reads, else in the home folder."""
    machine = _machine(machine)
    return Path(machine.environ.get("GEMINI_CLI_HOME") or machine.home) / ".gemini"


def _detect_gemini(machine: Machine, folder: Optional[Path] = None) -> App:
    app = App("gemini", command=find_cli("gemini", machine))
    home = gemini_dir(machine)
    if app.command:
        app.seen.append("the gemini command")
    if home.is_dir():
        app.seen.append(shown(home, machine))
    app.present = bool(app.seen)
    if not app.present:
        return app
    extensions = home / "extensions"
    for path in sorted(extensions.iterdir()) if extensions.is_dir() else []:
        install, _problem = _json(path / ".gemini-extension-install.json")
        install = install if isinstance(install, dict) else {}
        source = install.get("source") if isinstance(install.get("source"), str) else None
        linked = install.get("type") == "link" and source is not None
        manifest, _problem = _json((Path(source) if linked else path) / "gemini-extension.json")
        if not isinstance(manifest, dict) or manifest.get("name") != PLUGIN:
            continue
        ours = linked and folder is not None and same_path(source, folder)
        detail = ("" if ours else f"linked to {shown(source, machine)}" if linked
                  else f"from {source}" + (f" at {install.get('ref')}" if install.get("ref") else "") if source else "")
        app.copies.append(Copy("gemini", "extension", PLUGIN, version=manifest.get("version"), path=str(path),
                               detail=detail, ours=ours, source=source if ours else None,
                               via="linked" if ours else ""))
    settings, problem = _json(home / "settings.json")
    if problem:
        app.notes.append(f"{shown(home / 'settings.json', machine)} {problem}")
    elif isinstance(settings, dict):
        _servers(app, settings.get("mcpServers"), home / "settings.json")
    _loose(app, machine)
    return app


def _detect_desktop(machine: Machine, folder: Optional[Path] = None) -> App:
    app = App("claude-desktop")
    path = desktop_config(machine)
    app.config = str(path)
    # The app writes its folder on first start; the config file once a setting is saved.
    if path.is_file() or path.parent.is_dir():
        app.seen.append(shown(path if path.is_file() else path.parent, machine))
    app.present = bool(app.seen)
    if not app.present:
        return app
    data, problem = _json(path)
    if problem:
        app.unreadable = f"{shown(path, machine)} {problem}"
        return app
    if data is not None and not isinstance(data, dict):
        app.unreadable = f"{shown(path, machine)} is not a JSON object; edit it by hand"
        return app
    servers = (data or {}).get("mcpServers")
    if servers is not None and not isinstance(servers, dict):
        app.unreadable = f"mcpServers in {shown(path, machine)} is not a table; edit it by hand"
        return app
    _servers(app, servers, path, ours=DESKTOP_KEY)
    if isinstance(servers, dict) and DESKTOP_KEY in servers and not runs_cadgen(servers[DESKTOP_KEY]):
        app.notes.append(f"mcpServers.{DESKTOP_KEY} in {shown(path, machine)} is another server's")
    return app


DETECTORS: Dict[str, Callable[..., App]] = {
    "claude": _detect_claude, "claude-desktop": _detect_desktop, "codex": _detect_codex, "cursor": _detect_cursor,
    "grok": _detect_grok, "gemini": _detect_gemini,
}


def detect(machine: Optional[Machine] = None, apps: Sequence[str] = APPS, *, folder: Any = None) -> Dict[str, App]:
    """Every app in ``apps``: whether it is here, and every copy of the plugin it loads. Ours is the one
    from the plugin ``folder`` (``cad_server._internal.plugin``): Claude Code's and Codex's plugin from its
    catalog (``MARKETPLACE``, wherever that points: the plan points it at ``folder``), Gemini CLI's
    extension linked to it, Cursor's copy of it; Claude Desktop's server; Grok Build's install of
    ``latest``. An app whose folders cannot be read is here, and left alone (``unreadable``)."""
    machine = _machine(machine)
    folder = Path(folder) if folder is not None else None
    found = {}
    for name in apps:
        try:
            found[name] = DETECTORS[name](machine, folder)
        except OSError as error:
            found[name] = App(name, present=True, unreadable=f"its files could not be read ({type(error).__name__}: "
                                                             f"{error.strerror or error})")
    return found


def _failure(error: BaseException) -> str:
    if isinstance(error, subprocess.CalledProcessError):
        said = _text(error.stderr).strip() or _text(error.output).strip()
        return f"exit status {error.returncode}" + (f": {said.splitlines()[-1][:200]}" if said else "")
    return f"{type(error).__name__}: {error}"


# --- the plan -----------------------------------------------------------------------------------


def _status(copy: Copy, release: str) -> str:
    """``current``, ``older`` or ``newer``: our copy against the release installing it."""
    if not copy.version or not is_release(copy.version) or version_key(copy.version) < version_key(release):
        return "older"
    return "current" if version_key(copy.version) == version_key(release) else "newer"


def _leave(app: App, subject: str) -> Step:
    return Step(app.id, "leave", subject)


def _removal(app: App, copy: Copy, machine: Machine, action: str = "remove duplicate") -> Step:
    """The step that takes ``copy`` out of ``app``, by the app's own command or as a file."""
    cli = app.command
    words = copy.words(machine)
    if copy.kind == "skills":
        return Step(app.id, action, words, edit={"op": "move", "path": copy.path})
    if copy.kind == "folder":
        return Step(app.id, action, words, edit={"op": "remove", "path": copy.path})
    if copy.kind == "server" and app.id in ("claude-desktop", "cursor"):
        return Step(app.id, action, words, edit={"op": "servers", "path": copy.path, "remove": [copy.name]})
    commands = {
        ("claude", "plugin"): [["plugin", "uninstall", copy.name]],
        ("claude", "server"): [["mcp", "remove", "--scope", "user", copy.name]],
        ("codex", "plugin"): [["plugin", "remove", copy.name]],
        ("codex", "server"): [["mcp", "remove", copy.name]],
        ("gemini", "extension"): [["extensions", "uninstall", PLUGIN]],
        ("gemini", "server"): [["mcp", "remove", "--scope", "user", copy.name]],
        ("grok", "plugin"): [["plugin", "uninstall", PLUGIN]],
    }.get((app.id, copy.kind))
    if not commands or not cli:
        return _leave(app, f"{words}: no {app.id} command here to remove it with; remove it in {app.label}")
    argv = [[cli, *arguments] for arguments in commands]
    market = copy.name.split("@", 1)[1] if copy.kind == "plugin" and "@" in copy.name else ""
    if app.id in ("claude", "codex") and market in app.marketplaces and _our_catalog(app, market):
        # Its catalog goes with it: the plugin folder's, or this repository's on GitHub, which an earlier
        # release's installer added and Codex would fetch again at every start.
        argv.append([cli, "plugin", "marketplace", "remove", market])
    return Step(app.id, action, words, commands=argv)


def _our_catalog(app: App, market: str) -> bool:
    """Whether a catalog the app knows is one of ours: the plugin folder's (``MARKETPLACE``), or this
    repository's on GitHub (``GITHUB_MARKETPLACE``)."""
    if market == MARKETPLACE:
        return True
    return market == GITHUB_MARKETPLACE and _same_repository((app.marketplaces.get(market) or {}).get("repo"))


def _github_catalog(app: App) -> List[Step]:
    """This repository's catalog on GitHub with no plugin of it left to take it out with: replaced by
    the plugin folder's (Codex fetches a Git catalog at every start)."""
    if not app.command or not _our_catalog(app, GITHUB_MARKETPLACE) or GITHUB_MARKETPLACE not in app.marketplaces:
        return []
    if any(copy.kind == "plugin" and copy.name == f"{PLUGIN}@{GITHUB_MARKETPLACE}" for copy in app.copies):
        return []  # its plugin's removal takes it, or, another scope's, it stays with it
    return [Step(app.id, "remove duplicate", f"the {GITHUB_MARKETPLACE} catalog ({REPOSITORY} on GitHub)",
                 [[app.command, "plugin", "marketplace", "remove", GITHUB_MARKETPLACE]])]


def _duplicates(app: App, machine: Machine, *, everything: bool = False) -> List[Step]:
    """Steps for every copy that is neither ours nor a store's (``everything``: ours too): removed,
    or, another scope's, reported."""
    steps = []
    for copy in app.copies:
        if copy.store or (copy.ours and not everything):
            continue
        if not copy.removable:
            steps.append(_leave(app, f"{copy.words(machine)}: another scope's, left alone; remove it there if "
                                     "skills show twice"))
            continue
        steps.append(_removal(app, copy, machine))
    return steps


def _stores(app: App, machine: Machine) -> List[Step]:
    return [_leave(app, f"{copy.words(machine)}: a store's copy, which the store updates; never removed here")
            for copy in app.stores()]


def _point(cli: str, market: Optional[Dict[str, Any]], folder: Path) -> List[List[str]]:
    """The commands that make the app's ``MARKETPLACE`` catalog the plugin folder: none when it is; else
    the one pointing elsewhere removed (its plugin with it: neither app re-points a catalog in place),
    and the folder added."""
    if _points(market, folder):
        return []
    return ([[cli, "plugin", "marketplace", "remove", MARKETPLACE]] if market else []) \
        + [[cli, "plugin", "marketplace", "add", str(folder)]]


def _against_stores(app: App, machine: Machine) -> Tuple[List[Step], bool]:
    """A store's copies reported, and second copies removed: ``(steps, whether a store's copy is here)``,
    in which case ours goes too and nothing of ours is added beside it."""
    steps = _stores(app, machine) + _duplicates(app, machine)
    if app.stores():
        ours = app.ours()
        return steps + ([_removal(app, ours, machine)] if ours else []), True
    return steps, False


def _plan_claude(app: App, release: str, machine: Machine, folder: Optional[Path] = None, **_: Any) -> List[Step]:
    """Claude Code: the plugin folder a local-directory catalog (``MARKETPLACE``) and its plugin installed.
    Its sessions read the folder in place; its cached copy, which ``claude plugin list`` reports and the
    apps it feeds may read, is brought to this release by ``claude plugin update``."""
    steps, stored = _against_stores(app, machine)
    if stored or folder is None:
        return steps
    steps += _github_catalog(app)
    here, ours = shown(folder, machine), app.ours()
    if not app.command:
        return steps + [_leave(app, f"no claude command on this PATH to add {here} to Claude Code with")]
    cli, market = app.command, app.marketplaces.get(MARKETPLACE)
    if ours is not None and _points(market, folder):
        if ours.recorded and ours.recorded != release:
            return steps + [Step(app.id, "update", f"{PLUGIN_ID}: its cached copy {ours.recorded} -> {release} "
                                                   f"(it reads {here} in place)", [[cli, "plugin", "update", PLUGIN_ID]])]
        return steps + [_leave(app, f"{PLUGIN_ID} {ours.version or '?'} reads {here} in place")]
    commands = _point(cli, market, folder) + [[cli, "plugin", "install", PLUGIN_ID]]
    if ours is not None:
        return steps + [Step(app.id, "update", f"{PLUGIN_ID}, pointed at {here}, which it reads in place", commands)]
    return steps + [Step(app.id, "install", f"{PLUGIN_ID}, which reads {here} in place", commands)]


def _plan_codex(app: App, release: str, machine: Machine, folder: Optional[Path] = None, **_: Any) -> List[Step]:
    """Codex: the plugin folder a local catalog (``MARKETPLACE``) and its plugin added, which Codex copies;
    added again for every release, since Codex never copies it again by itself."""
    steps, stored = _against_stores(app, machine)
    if stored or folder is None:
        return steps
    steps += _github_catalog(app)
    here, ours = shown(folder, machine), app.ours()
    if not app.command:
        return steps + [_leave(app, f"no codex command on this PATH to add {here} to Codex with")]
    cli, market = app.command, app.marketplaces.get(MARKETPLACE)
    add = [cli, "plugin", "add", PLUGIN_ID]
    if ours is not None and _points(market, folder):
        if ours.version == release:
            return steps + [_leave(app, f"{PLUGIN_ID} {ours.version}, {ours.origin(machine)}")]
        return steps + [Step(app.id, "update", f"{PLUGIN_ID} {ours.version or '?'} -> {release}, copied again from "
                                               f"{here}", [add])]
    commands = _point(cli, market, folder) + [add]
    if ours is not None:
        return steps + [Step(app.id, "update", f"{PLUGIN_ID}, a copy of {here}", commands)]
    return steps + [Step(app.id, "install", f"{PLUGIN_ID}, a copy of {here}", commands)]


def _served(app: App, machine: Machine) -> List[Step]:
    """An app that loads Claude Code's plugin: every copy of its own is a second copy."""
    steps = [_leave(app, f"served by the {LABELS['claude']} plugin")]
    for copy in app.copies:
        if copy.store:
            steps.append(_leave(app, f"{copy.words(machine)}: a store's copy, never removed here; {app.label} "
                                     f"loads the {LABELS['claude']} plugin too, so remove one of them in {app.label}"))
        elif not copy.removable:
            steps.append(_leave(app, f"{copy.words(machine)}: another scope's, left alone"))
        else:
            steps.append(_removal(app, copy, machine))
    return steps


def _plan_cursor(app: App, release: str, machine: Machine, folder: Optional[Path] = None, fed: bool = False,
                 **_: Any) -> List[Step]:
    """Cursor, where Claude Code does not feed it: the plugin folder copied, real files, into its local
    plugins folder, and copied again for every release."""
    if fed:
        return _served(app, machine)
    steps, stored = _against_stores(app, machine)
    if stored or folder is None:
        return steps
    here, ours = shown(folder, machine), app.ours()
    if ours is not None:
        if ours.version == release:
            return steps + [_leave(app, f"{shown(ours.name, machine)} {ours.version}, {ours.origin(machine)}")]
        return steps + [Step(app.id, "update", f"{shown(ours.name, machine)} {ours.version or '?'} -> {release}, "
                                               f"copied again from {here}",
                             edit={"op": "copy", "from": str(folder), "path": ours.name})]
    target = cursor_plugins(machine) / PLUGIN
    occupied = target.exists() and not any(copy.path == str(target) for copy in app.copies)
    if occupied:
        return steps + [_leave(app, f"{shown(target, machine)} holds something else: move it away, then run this again")]
    return steps + [Step(app.id, "install", f"{shown(target, machine)}, a copy of {here}",
                         edit={"op": "copy", "from": str(folder), "path": str(target)})]


def _plan_grok(app: App, release: str, machine: Machine, fed: bool = False, **_: Any) -> List[Step]:
    if fed:
        return _served(app, machine)
    steps = _duplicates(app, machine)
    if not app.command:
        return steps + [_leave(app, f"no grok command on this PATH: install {PLUGIN} from Grok Build itself")]
    ours = app.ours()
    if ours is not None:
        status = _status(ours, release)
        if status != "older":
            return steps + [_leave(app, f"{PLUGIN} {ours.version}: "
                                        + ("up to date" if status == "current" else f"newer than {release}, left alone"))]
        return steps + [Step(app.id, "update", f"{PLUGIN} {ours.version or '?'} -> {release}",
                             [[app.command, "plugin", "update", PLUGIN]])]
    return steps + [Step(app.id, "install", f"{PLUGIN} from {REPOSITORY}@{BRANCH}",
                         [[app.command, "plugin", "install", f"{REPOSITORY}@{BRANCH}", "--trust"],
                          [app.command, "plugin", "enable", PLUGIN]])]


def _plan_gemini(app: App, release: str, machine: Machine, folder: Optional[Path] = None, **_: Any) -> List[Step]:
    """Gemini CLI: the plugin folder linked as its extension, which it reads in place: nothing to do at
    an update. Another copy of the extension goes first (their names would collide)."""
    steps = _duplicates(app, machine)
    if folder is None:
        return steps
    here, ours = shown(folder, machine), app.ours()
    if not app.command:
        return steps + [_leave(app, f"no gemini command on this PATH to link {here} with")]
    if ours is not None:
        return steps + [_leave(app, f"the {PLUGIN} extension {ours.version or '?'}, {ours.origin(machine)}")]
    return steps + [Step(app.id, "install", f"the {PLUGIN} extension, linked to {here}",
                         [[app.command, "extensions", "link", str(folder), "--consent"]])]


def _wanted(entry: Any, desktop_entry: Dict[str, Any]) -> Dict[str, Any]:
    """``desktop_entry`` as it replaces ``entry``: the environment someone added to the entry kept
    (a ``CAD_ENGINE_PORT``, say), the release's own variables over it."""
    kept = entry.get("env") if isinstance(entry, dict) and isinstance(entry.get("env"), dict) else {}
    return {**desktop_entry, "env": {**kept, **(desktop_entry.get("env") or {})}}


def _plan_desktop(app: App, release: str, machine: Machine, desktop_entry: Optional[Dict[str, Any]] = None,
                  **_: Any) -> List[Step]:
    """Claude Desktop's config: ``mcpServers.cad`` set to ``desktop_entry``, this release's server,
    where it has none or one that runs an older release (its pin, ``texttocad-mcp==X`` or an earlier
    release's ``cadgen==X``, is what uvx runs) or differs otherwise (its uvx); one that pins a newer release
    is left alone. Every other entry that runs text-to-cad is taken out, in the same write of the file (one
    ``.bak``)."""
    path = app.config or str(desktop_config(machine))
    others = [copy for copy in app.copies if not copy.ours]
    remove = [copy.name for copy in others]
    where = f"mcpServers.{DESKTOP_KEY} in {shown(path, machine)}"
    ours, steps, change = app.ours(), [], None
    if app.notes:  # mcpServers.cad is another server's
        steps.append(_leave(app, f"{app.notes[0]}: left alone; add CAD's server by hand"))
    elif desktop_entry is None:
        steps.append(_leave(app, "no uvx found to run CAD's server with: install uv, then run this again"))
    elif ours is None:
        change = Step(app.id, "install", f"{where}: text-to-cad {release}")
    elif ours.entry == _wanted(ours.entry, desktop_entry):
        steps.append(_leave(app, f"{where}: text-to-cad {release}, up to date"))
    elif is_release(ours.version) and version_key(ours.version) > version_key(release):
        steps.append(_leave(app, f"{where}: text-to-cad {ours.version}, newer than {release}, left alone"))
    else:
        change = Step(app.id, "update", f"{where}: text-to-cad {ours.version or '?'} -> {release}")
    if change is not None:
        entry = _wanted(ours.entry, desktop_entry) if ours is not None else desktop_entry
        change.edit = {"op": "servers", "path": path, "set": {DESKTOP_KEY: entry}, "remove": remove}
        return [Step(app.id, "remove duplicate", copy.words(machine), note="in the same edit") for copy in others] \
            + steps + [change]
    if remove:
        steps.insert(0, Step(app.id, "remove duplicate", ", ".join(copy.words(machine) for copy in others),
                             edit={"op": "servers", "path": path, "remove": remove}))
    return steps


PLANNERS: Dict[str, Callable[..., List[Step]]] = {
    "claude": _plan_claude, "claude-desktop": _plan_desktop, "codex": _plan_codex, "cursor": _plan_cursor,
    "grok": _plan_grok, "gemini": _plan_gemini,
}


def feeds(apps: Mapping[str, App], selected: Iterable[str]) -> bool:
    """Whether Claude Code has the plugin after this run, so that Cursor and Grok Build load it: it
    has ours or a store's now, or it is selected and has the command that installs it."""
    claude = apps.get("claude")
    if claude is None or not claude.present:
        return False
    return claude.ours() is not None or bool(claude.stores()) or ("claude" in selected and bool(claude.command))


def _once(steps: List[Step]) -> List[Step]:
    """``steps`` with each loose skill moved once: two apps read ``~/.agents/skills``."""
    seen, kept = set(), []
    for step in steps:
        path = (step.edit or {}).get("path") if (step.edit or {}).get("op") == "move" else None
        if path in seen:
            continue
        if path:
            seen.add(path)
        kept.append(step)
    return kept


def _plan_skills(release: str, machine: Machine, agents: Sequence[str], record: Optional[Mapping[str, Any]],
                 source: Optional[Path] = None) -> List[Step]:
    """The Skills CLI agents here among ``agents``: one ``npx skills add`` of the plugin folder's skills
    (``source``) for every one whose folder lacks a skill of ours or got them from another release
    (``record``, the receipt's), the rest up to date."""
    found, npx, record = skills_agents(machine), machine.which("npx"), record or {}
    steps: List[Step] = []
    due: List[Step] = []
    for agent in agents:
        if agent not in found:
            continue
        folder = found[agent]
        where, have = shown(folder, machine), ours_in(folder)
        had = record.get(agent) if isinstance(record.get(agent), dict) else {}
        before = had.get("release")
        # Up to date: this release's, and every skill the CLI said it installed still there. A skill
        # it skipped is not asked for again on every run.
        recorded = had.get("skills") if isinstance(had.get("skills"), list) else list(SKILLS)
        missing = [name for name in recorded if folder / name not in have]
        if before == release and not missing:
            steps.append(Step(agent, "leave", f"the skills in {where}, from text-to-cad {release}: up to date"))
        elif not npx:
            steps.append(Step(agent, "leave", NEED_NODE))
        elif source is None:
            continue
        elif had or have:
            why = (f"{', '.join(missing[:3])}{f' +{len(missing) - 3}' if len(missing) > 3 else ''} missing"
                   if before == release else f"from text-to-cad {before or '?'} -> {release}")
            due.append(Step(agent, "update", f"the skills in {where}" + (": " if before == release else ", ") + why))
            steps.append(due[-1])
        else:
            due.append(Step(agent, "install", f"the skills, copied into {where} by the Skills CLI"))
            steps.append(due[-1])
    if due and source is not None:
        argv = [npx, *SKILLS_CLI[1:], "add", skills_source(source), "-g"]
        for step in due:
            argv += ["-a", step.app]
        due[0].commands = [argv + ["-s", "*", "-y", "--copy", "--json"]]
        due[0].agents = [step.app for step in due]
        for step in due[1:]:
            step.note = "in the command above"
    return steps


def _shared_note(apps: Mapping[str, App], steps: List[Step], machine: Machine) -> List[Step]:
    """A line for Codex and Gemini CLI, which read ``~/.agents/skills``, when a Skills CLI agent here
    keeps the skills there and the app has the plugin or is getting it: both copies show in it."""
    shared = shared_skills(machine)
    owners = [step.app for step in steps if step.app in SKILLS_AGENTS and skills_folder(step.app, machine) == shared
              and step.subject != NEED_NODE]
    notes = []
    for name, kind in (("codex", "plugin"), ("gemini", "extension")):
        app = apps.get(name)
        getting = any(step.app == name and step.action in ("install", "update") for step in steps)
        if owners and app is not None and app.present and (app.ours() is not None or getting):
            notes.append(Step(name, "leave", f"the skills in {shown(shared, machine)}, "
                                             f"{' and '.join(label(owner) for owner in owners)}'s folder: "
                                             f"{app.label} lists them beside its {kind}'s"))
    return notes


def plan(apps: Mapping[str, App], *, release: str, folder: Any = None, desktop_entry: Optional[Dict[str, Any]] = None,
         only: Optional[Sequence[str]] = None, machine: Optional[Machine] = None,
         skills: Optional[Mapping[str, Any]] = None) -> List[Step]:
    """What to do for every selected app that is here, in ``APPS`` order, to give it this release's
    plugin from the plugin ``folder``: each app's duplicates taken out before its copy is installed or
    updated, so two copies never load at once; then the skills for the Skills CLI agents here
    (``skills``: the receipt's record of them)."""
    machine = _machine(machine)
    folder = Path(folder) if folder is not None else None
    selected = [name for name in APPS if not only or name in only]
    fed = feeds(apps, selected)
    steps: List[Step] = []
    for name in selected:
        app = apps.get(name)
        if app is None or not app.present:
            continue
        if app.unreadable:
            steps.append(_leave(app, f"{app.unreadable}: nothing is changed there"))
            continue
        steps += PLANNERS[name](app, release, machine, folder=folder, fed=fed and name in FED_BY,
                                desktop_entry=desktop_entry)
    steps += _plan_skills(release, machine, [agent for agent in SKILLS_AGENTS if not only or agent in only], skills,
                          folder)
    return _once(steps) + _shared_note(apps, steps, machine)


def _follow_desktop(app: App, release: str, machine: Machine, desktop_entry: Optional[Dict[str, Any]]) -> List[Step]:
    """Claude Desktop's server, ours, set to ``desktop_entry`` (``release``'s) where it differs: the release a
    switch left current, ahead of the one in the config as much as behind it (a switch that went back)."""
    ours = app.ours()
    if ours is None or desktop_entry is None or app.notes or ours.entry == _wanted(ours.entry, desktop_entry):
        return []
    path = app.config or str(desktop_config(machine))
    return [Step(app.id, "update", f"mcpServers.{DESKTOP_KEY} in {shown(path, machine)}: text-to-cad "
                                   f"{ours.version or '?'} -> {release}",
                 edit={"op": "servers", "path": path, "set": {DESKTOP_KEY: _wanted(ours.entry, desktop_entry)},
                       "remove": []})]


def refresh_plan(apps: Mapping[str, App], *, release: str, folder: Any, machine: Optional[Machine] = None,
                 skills: Optional[Mapping[str, Any]] = None,
                 desktop_entry: Optional[Dict[str, Any]] = None) -> List[Step]:
    """After the plugin ``folder`` was written again for ``release``: the copies apps keep of it brought to
    it, and nothing installed anew or taken out -- Claude Code's cached copy (``claude plugin update``),
    Claude Desktop's server (``desktop_entry``, this release's), Codex's (added again), Cursor's (copied
    again) and the skills the Skills CLI copied for the agents the receipt names (``skills``). Claude Code
    and Gemini CLI read the folder itself."""
    machine = _machine(machine)
    folder = Path(folder)
    steps: List[Step] = []
    for name in ("claude", "claude-desktop", "codex", "cursor"):
        app = apps.get(name)
        ours = app.ours() if app is not None and app.present and not app.unreadable else None
        if ours is None or app.stores():
            continue
        if name == "claude-desktop":
            steps += _follow_desktop(app, release, machine, desktop_entry)
            continue
        if name != "cursor" and not _points(app.marketplaces.get(MARKETPLACE), folder):
            continue  # pointed elsewhere: `cad setup` points it here
        steps += [step for step in PLANNERS[name](app, release, machine, folder=folder) if step.action == "update"]
    agents = [agent for agent in (skills or {}) if agent in SKILLS_AGENTS]
    steps += [step for step in _plan_skills(release, machine, agents, skills, folder) if step.changes]
    return steps


# --- taking it out ------------------------------------------------------------------------------


def touched(receipt: Optional[Mapping[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """What a receipt says the installer did to each app, in the order it first did it: ``installed``
    (it installed or updated our copy), ``added`` (it added a catalog), ``copy`` (Cursor's copy of the
    plugin folder; ``clone``, an earlier release's clone), and ``edit`` (Claude Desktop's config: the
    first edit's ``.bak``, or that it made the file, and the last edit's hash and server entry)."""
    found: Dict[str, Dict[str, Any]] = {}
    for action in (receipt or {}).get("actions") or []:
        if not isinstance(action, dict) or not action.get("ok") or action.get("app") not in APPS:
            continue
        name, argv = action["app"], action.get("command") or []
        if action.get("kind") == "edit" and action.get("path"):
            entry = found.setdefault(name, {})
            edit = entry.setdefault("edit", {"path": action["path"], "backup": action.get("backup"),
                                             "created": bool(action.get("created"))})
            edit["sha256"] = action.get("sha256")
            server = (action.get("set") or {}).get(DESKTOP_KEY)
            if server is not None:
                edit["entry"], entry["installed"] = server, True
            continue
        if action.get("action") not in ("install", "update"):
            continue
        entry = found.setdefault(name, {})
        entry["installed"] = True
        if action.get("kind") == "command" and argv[1:4] == ["plugin", "marketplace", "add"]:
            entry["added"] = True
        if action.get("kind") == "command" and len(argv) > 2 and argv[1] == "clone":
            entry["clone"] = argv[-1]
        if action.get("kind") == "copy" and action.get("path"):
            entry["copy"] = action["path"]
    return found


def _unskill(agents: Sequence[str], machine: Machine, npx: Optional[str]) -> List[Step]:
    """The skills of ours taken out of ``agents``' folders: with ``npx``, by one ``npx skills remove``
    (which keeps its own records straight), and whatever of ours it leaves (it keeps a folder another
    agent here reads) removed directly; without, directly."""
    steps: List[Step] = []
    claimed: set = set()
    for agent in agents:
        folder = skills_folder(agent, machine)
        have = [] if str(folder) in claimed else ours_in(folder)
        claimed.add(str(folder))
        if have:
            steps.append(Step(agent, "remove", f"the skills in {shown(folder, machine)}",
                              edit={"op": "remove", "paths": [str(path) for path in have]}))
    if npx and steps:
        names = sorted({Path(path).name for step in steps for path in step.edit["paths"]})
        argv = [npx, *SKILLS_CLI[1:], "remove", "-g"]
        for step in steps:
            argv += ["-a", step.app]
        steps[0].commands, steps[0].agents = [argv + ["-s", *names, "-y"]], [step.app for step in steps]
        for step in steps[1:]:
            step.note = "in the command above"
    return steps


def uninstall_plan(apps: Mapping[str, App], receipt: Optional[Mapping[str, Any]] = None,
                   only: Optional[Sequence[str]] = None, machine: Optional[Machine] = None,
                   folder: Any = None) -> List[Step]:
    """The removals: with a receipt, what it says the installer did, in reverse -- each app's copy from
    the plugin ``folder`` taken out the way it was put in (Claude Code's and Codex's plugin and the
    folder's catalog, Gemini CLI's linked extension, Cursor's copy), and an earlier release's from the
    repository on GitHub; without one, every copy found but a store's."""
    machine = _machine(machine)
    folder = Path(folder) if folder is not None else None
    steps: List[Step] = []
    if receipt is None:
        for name in APPS:
            app = apps.get(name)
            if app is None or not app.present or (only and name not in only):
                continue
            for step in _duplicates(app, machine, everything=True):
                if step.changes:
                    step.action = "remove"
                steps.append(step)
        agents = [agent for agent in skills_agents(machine) if not only or agent in only]
        return _once(steps) + _unskill(agents, machine, npx=None)
    record = receipt.get("skills") if isinstance(receipt.get("skills"), dict) else {}
    steps += _unskill([agent for agent in record if agent in SKILLS_AGENTS and (not only or agent in only)],
                      machine, npx=machine.which("npx"))
    done = touched(receipt)
    for name in reversed(list(done)):
        app, record = apps.get(name), done[name]
        if app is None or (only and name not in only):
            continue
        ours = app.ours()
        if name in ("claude", "codex"):
            cli, verb, commands = app.command, "uninstall" if name == "claude" else "remove", []
            if ours is not None and cli:
                commands.append([cli, "plugin", verb, PLUGIN_ID])
            local = app.marketplaces.get(MARKETPLACE)
            if cli and local is not None and (record.get("added") or _points(local, folder)):
                commands.append([cli, "plugin", "marketplace", "remove", MARKETPLACE])
            # An earlier release's installer added the repository's catalog on GitHub, and its plugin.
            if cli and record.get("added") and GITHUB_MARKETPLACE in app.marketplaces \
                    and _our_catalog(app, GITHUB_MARKETPLACE):
                github = f"{PLUGIN}@{GITHUB_MARKETPLACE}"
                if any(copy.name == github and copy.removable for copy in app.copies):
                    commands.append([cli, "plugin", verb, github])
                commands.append([cli, "plugin", "marketplace", "remove", GITHUB_MARKETPLACE])
            if commands:
                steps.append(Step(name, "remove", PLUGIN_ID, commands))
        elif name in ("gemini", "grok"):
            if ours is not None and app.command:
                argv = ["extensions", "uninstall", PLUGIN] if name == "gemini" else ["plugin", "uninstall", PLUGIN]
                steps.append(Step(name, "remove", ours.words(machine), [[app.command, *argv]]))
        elif name == "cursor":
            # The installer's copy of the folder (or an earlier release's clone of `latest`), where it put it.
            for path in [record[key] for key in ("copy", "clone") if record.get(key)]:
                if any(copy.path == path and (copy.ours or _git_head(Path(path))[1] == BRANCH) for copy in app.copies):
                    steps.append(Step(name, "remove", shown(path, machine), edit={"op": "remove", "path": path}))
        elif name == "claude-desktop" and record.get("installed") and record.get("edit"):
            edit = record["edit"]
            steps.append(Step(name, "remove", f"mcpServers.{DESKTOP_KEY} from {shown(edit['path'], machine)}",
                              edit={"op": "restore", **edit}))
    return steps


# --- changing files -----------------------------------------------------------------------------


def _replace(source: Any, target: Any) -> None:
    """A file moved into place whole: cadgen's one atomic rename, which waits out the moment Windows
    refuses one (``cad._internal.atomic_replace``), when this file is cadgen's; the plain rename
    when the development installer loaded it by its path, without the package."""
    try:
        from cad._internal.atomic_replace import replace_atomic
    except ImportError:
        replace_atomic = os.replace
    replace_atomic(source, target)


def write_json(path: Path, value: Any, *, backup: bool = False) -> Optional[Path]:
    """Replace ``path`` whole, keeping its mode (a config may hold another server's secrets);
    with ``backup``, the file as it was is kept beside it first (``<name>.bak``), which is returned."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = path.stat().st_mode & 0o777 if path.exists() else 0o644
    kept = None
    if backup and path.is_file():
        kept = path.with_name(path.name + ".bak")
        shutil.copy2(path, kept)
    handle, temporary = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as out:
            json.dump(value, out, indent=2)
            out.write("\n")
        os.chmod(temporary, mode)
        _replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise
    return kept


def _sha256(path: Path) -> Optional[str]:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def edit_servers(path: Any, *, set_entries: Optional[Mapping[str, Any]] = None, remove: Sequence[str] = (),
                 backup: bool = True) -> Dict[str, Any]:
    """``mcpServers`` in the JSON file ``path``: ``set_entries`` written and ``remove`` taken out,
    the rest of the file as it was, written atomically, the file as it was kept as ``.bak`` when
    ``backup``. ``ValueError`` for a file that is not a JSON object, which is never rewritten."""
    path = Path(path)
    data, problem = _json(path)
    if problem:
        raise ValueError(f"{path} {problem}")
    created = not path.exists()
    data = {} if data is None else data
    if not isinstance(data, dict) or not isinstance(data.get("mcpServers", {}), dict):
        raise ValueError(f"{path} is not a JSON object with an mcpServers table; edit it by hand")
    servers = dict(data.get("mcpServers") or {})
    for key in remove:
        servers.pop(key, None)
    servers.update(set_entries or {})
    data["mcpServers"] = servers
    kept = write_json(path, data, backup=backup and not created)
    return {"path": str(path), "backup": str(kept) if kept else None, "created": created, "sha256": _sha256(path),
            "set": dict(set_entries or {}), "removed": list(remove)}


def restore_servers(edit: Mapping[str, Any]) -> str:
    """An installer's edit of a config taken back. A file still exactly as the installer last wrote it
    goes back to what it was (its ``.bak``, or nothing when the installer made it); one changed since
    loses only the installer's server, and only while it holds what was written. What was done."""
    path = Path(edit["path"])
    if not path.exists():
        return "already gone"
    if edit.get("sha256") and _sha256(path) == edit["sha256"]:
        backup = Path(edit["backup"]) if edit.get("backup") else None
        if edit.get("created"):
            path.unlink()
            return "removed the file the installer made"
        if backup is not None and backup.is_file():
            _replace(backup, path)
            return f"restored from {backup.name}"
    data, problem = _json(path)
    servers = data.get("mcpServers") if isinstance(data, dict) else None
    if problem or not isinstance(servers, dict) or DESKTOP_KEY not in servers:
        return "no server of the installer's left in it"
    if edit.get("entry") is not None and servers[DESKTOP_KEY] != edit["entry"]:
        return f"mcpServers.{DESKTOP_KEY} was changed since; left alone"
    edit_servers(path, remove=[DESKTOP_KEY])
    return f"removed mcpServers.{DESKTOP_KEY}; the rest of the file changed since, so it was kept"


def remove_path(path: Any) -> None:
    path = Path(path)
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.exists():
        shutil.rmtree(path)


def _same_file(path: Path, data: bytes, mode: int) -> bool:
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size != len(data):
            return False
        return (os.name == "nt" or path.stat().st_mode & 0o777 == mode) and path.read_bytes() == data
    except OSError:
        return False


def copy_plugin(source: Any, target: Any) -> Dict[str, Any]:
    """The plugin folder ``source`` copied into ``target`` -- real files, each that differs written whole
    beside it and renamed over it, what ``source`` does not hold taken out -- and the copy marked
    (``COPY_MARK``: where from, its version, when). The mark."""
    source, target = Path(source), Path(target)
    wanted: Dict[str, Tuple[bytes, int]] = {}
    for directory, folders, files in os.walk(source):
        folders[:] = sorted(folders)
        for name in sorted(files):
            path = Path(directory) / name
            wanted[path.relative_to(source).as_posix()] = (path.read_bytes(),
                                                           0o755 if os.stat(path).st_mode & 0o111 else 0o644)
    if not wanted:
        raise ValueError(f"{source} holds no plugin to copy")
    if target.is_symlink() or (target.exists() and not target.is_dir()):
        target.unlink()
    target.mkdir(parents=True, exist_ok=True)
    for directory, folders, files in os.walk(target, topdown=False):
        for name in files + folders:
            path = Path(directory) / name
            relative = path.relative_to(target).as_posix()
            if path.is_symlink() or (path.is_file() and relative not in wanted and relative != COPY_MARK):
                path.unlink()
            elif path.is_dir() and not any(path.iterdir()):
                path.rmdir()
    for relative, (data, mode) in sorted(wanted.items()):
        path = target / relative
        if _same_file(path, data, mode):
            continue
        if path.is_dir():
            shutil.rmtree(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        handle, temporary = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
        try:
            with os.fdopen(handle, "wb") as out:
                out.write(data)
            os.chmod(temporary, mode)
            _replace(temporary, path)
        except BaseException:
            try:
                os.unlink(temporary)
            except OSError:
                pass
            raise
    manifest, _problem = _json(source / ".cursor-plugin" / "plugin.json")
    mark = {"from": str(source), "version": manifest.get("version") if isinstance(manifest, dict) else None,
            "copied": time.strftime("%Y-%m-%d %H:%M")}
    write_json(target / COPY_MARK, mark)
    return mark


def skills_lock(machine: Optional[Machine] = None) -> Path:
    """The Skills CLI's record of the skills it installed, one entry by name with where it came from, which
    ``npx skills update`` installs again from: ``$XDG_STATE_HOME/skills/.skill-lock.json``, else
    ``~/.agents/.skill-lock.json``."""
    machine = _machine(machine)
    state = machine.environ.get("XDG_STATE_HOME")
    return Path(state) / "skills" / ".skill-lock.json" if state else machine.home / ".agents" / ".skill-lock.json"


def unlock_skill(name: str, machine: Optional[Machine] = None) -> bool:
    """The Skills CLI's entry for the skill ``name`` removed where it came from this repository on GitHub: a
    loose copy, moved aside, which ``npx skills update`` would put back once the repository's skills change.
    One it installed from the plugin folder (this installer's, for an agent without a plugin) stays. Whether
    one was removed; a record that cannot be read is left as it is."""
    path = skills_lock(machine)
    data, problem = _json(path)
    skills = data.get("skills") if isinstance(data, dict) else None
    entry = skills.get(name) if isinstance(skills, dict) else None
    if problem or not isinstance(entry, dict) or not any(_same_repository(entry.get(key)) for key in ("source", "sourceUrl")):
        return False
    del skills[name]
    write_json(path, data)
    return True


def move_aside(path: Any, folder: Any) -> Path:
    """``path`` moved into ``folder`` (a new name when one is taken): a loose skill kept, not deleted."""
    path, folder = Path(path), Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / path.name
    count = 1
    while os.path.lexists(target):
        count += 1
        target = folder / f"{path.name}-{count}"
    shutil.move(str(path), str(target))
    return target


def stamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def apply(step: Step, machine: Optional[Machine] = None, *, say: Callable[[str], None] = lambda _line: None,
          aside: Optional[Path] = None, backed_up: Optional[set] = None) -> Tuple[bool, List[Dict[str, Any]]]:
    """Run ``step``: each command, said before it runs, stopping at the first that fails (its output
    said), then its file edit. ``(ok, records)``, a record per thing done, for the receipt. ``aside``
    is where loose skills go; ``backed_up``, the files this run already kept a ``.bak`` of."""
    machine = _machine(machine)
    records: List[Dict[str, Any]] = []
    base = {"app": step.app, "action": step.action}
    for argv in step.commands:
        say(f"$ {command_text(argv, machine)}")
        ran = machine.run(argv)
        record = {**base, "kind": "command", "command": list(argv), "code": ran.code, "ok": ran.ok, "at": stamp()}
        if not ran.ok:
            record["output"] = ran.said()
            for line in (ran.said() or f"exit status {ran.code}").splitlines():
                say(f"  {line}")
            say(f"failed: exit status {ran.code}")
            records.append(record)
            return False, records
        if step.agents and argv[len(SKILLS_CLI):len(SKILLS_CLI) + 1] == ["add"]:  # the skills it says it installed
            record["skills"] = skills_installed(ran.out)
        records.append(record)
    if step.edit is None:
        return True, records
    edit, record = step.edit, {**base, "at": stamp()}
    try:
        if edit["op"] == "servers":
            fresh = backed_up is None or edit["path"] not in backed_up
            say(f"edit {shown(edit['path'], machine)}" + (" (its .bak kept beside it)" if fresh else ""))
            done = edit_servers(edit["path"], set_entries=edit.get("set"), remove=edit.get("remove") or (), backup=fresh)
            if backed_up is not None:
                backed_up.add(edit["path"])
            record.update({"kind": "edit", **done})
        elif edit["op"] == "remove" and "paths" in edit:  # skill folders, some maybe gone with a command
            left = [path for path in edit["paths"] if os.path.lexists(path)]
            for path in left:
                say(f"remove {shown(path, machine)}")
                remove_path(path)
            record.update({"kind": "remove", "paths": left})
        elif edit["op"] == "remove":
            say(f"remove {shown(edit['path'], machine)}")
            remove_path(edit["path"])
            record.update({"kind": "remove", "path": edit["path"]})
        elif edit["op"] == "copy":
            say(f"copy {shown(edit['from'], machine)} to {shown(edit['path'], machine)}")
            mark = copy_plugin(edit["from"], edit["path"])
            record.update({"kind": "copy", "path": edit["path"], "from": edit["from"], "version": mark.get("version")})
        elif edit["op"] == "move":
            folder = Path(aside or tempfile.gettempdir()) / step.app
            target = move_aside(edit["path"], folder)
            say(f"move {shown(edit['path'], machine)} to {shown(target, machine)}")
            record.update({"kind": "move", "path": edit["path"], "to": str(target)})
            # The Skills CLI's record of it goes too, so its `update` does not install it again.
            if unlock_skill(Path(edit["path"]).name, machine):
                say(f"remove {Path(edit['path']).name} from {shown(skills_lock(machine), machine)}")
                record["unlocked"] = str(skills_lock(machine))
        elif edit["op"] == "restore":
            said = restore_servers(edit)
            say(f"{shown(edit['path'], machine)}: {said}")
            record.update({"kind": "restore", "path": edit["path"], "result": said})
        else:
            raise ValueError(f"unknown edit {edit['op']!r}")
    except (OSError, ValueError) as error:
        say(f"failed: {error}")
        records.append({**record, "kind": record.get("kind", edit["op"]), "ok": False, "output": str(error)})
        return False, records
    records.append({**record, "ok": True})
    return True, records
