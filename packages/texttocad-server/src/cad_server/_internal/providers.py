"""The agent apps text-to-cad installs into, read and changed the way each one keeps its plugins.

``cad setup`` (``cad_server.cli.setup``) asks this module what is on the machine and what to do
about it, and a checkout's development installer loads this same file by its path: both installers
find every app, every copy of the plugin and every app's own commands the same way. Six apps:

- **Claude Code**: the plugin ``text-to-cad@earthtojake``, from the repository's catalog on its
  ``latest`` branch, through ``claude plugin``. Cursor and Grok Build load the plugins Claude Code
  installed as well as their own (``FED_BY``), so where Claude Code has the plugin they need none
  of their own, and a copy of theirs is a second copy.
- **Claude Desktop** (its chat): CAD's server alone, ``mcpServers.cad`` in its config file, run by
  ``uvx`` at its absolute path, since an app opened from the Dock has no shell's PATH.
- **Codex**: the same catalog through its own ``plugin`` command; the app bundles a CLI of its own.
- **Cursor**: a clone of the ``latest`` branch in its local plugins folder.
- **Grok Build**: ``grok plugin``, from the repository's ``latest``.
- **Gemini CLI**: its extension, installed from the repository at ``latest``, never auto-updated:
  an update is the person's (``cad update``, the install command, the update button).

Every other agent the Skills CLI (``npx skills``) knows and that is installed here gets the skills
alone, copied into that agent's own skills folder by one ``npx skills add`` for all of them
(``SKILLS_AGENTS``: each one's folder and how it is detected, as that CLI reads them). The CLI keeps
no versions, so the receipt says which agents got which skills (those its ``--json`` says it
installed) from which release; a later run adds them again for an agent when that release is not
this one or one of those skills is missing from its folder.
An app with a plugin path is never one of them.

A second copy loads every skill twice: the plugin from another catalog (a checkout's development
install), this repository's skills installed loose, a server someone added by hand that runs
cadgen. The plan removes it, the loose skills moved aside rather than deleted. A loose skill is
ours when its ``SKILL.md`` names one of this repository's skills (``SKILLS``) and says where it is
maintained (``PROVENANCE``). The one folder two kinds of agent share, ``~/.agents/skills`` (Codex and
Gemini CLI read it; it is Cline's and Zed's own), is the Skills CLI agent's while one that uses it is
here: Codex and Gemini CLI then list those skills beside their plugin's, which the plan says. A store's copy
(claude.ai's directory, the app directory of Codex's maker, the Cursor Marketplace) is the store's
to update and to remove: it is reported, never touched, and no copy of ours is added beside it.

Nothing here imports cadgen, and the file parses on any Python 3 the development installer may run
on. Every path comes from a :class:`Machine` -- its home, its environment, its platform and how it
runs a command -- so a test reads a temporary home with fake commands on a temporary PATH.
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
# The branch every install follows: the plugin alone, one commit per release, never ahead of PyPI.
BRANCH = "latest"
# The repository's catalog, as Claude Code and Codex name it, and the plugin's id in it.
MARKETPLACE = "earthtojake"
PLUGIN_ID = f"{PLUGIN}@{MARKETPLACE}"
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
    "codex": "Codex: restart the app, and any terminal or IDE session",
    "cursor": "Cursor: reload the window",
    "grok": "Grok Build: start a new session",
    "gemini": "Gemini CLI: start a new session",
}
# The CLIs an app bundles, for an app whose terminal command may be missing or older.
BUNDLED = {"codex": ("/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex",)}
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
    apps' commands), the platform, the CLIs apps bundle, and the runner. :meth:`here` is this one."""

    def __init__(self, home: Any, environ: Mapping[str, str], platform: str = sys.platform,
                 bundled: Optional[Mapping[str, Sequence[str]]] = None,
                 runner: Optional[Callable[[List[str], Dict[str, str], float], Ran]] = None) -> None:
        self.home = Path(home)
        self.environ = dict(environ)
        self.platform = platform
        self.bundled = BUNDLED if bundled is None else bundled
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
        "gemini": [home / ".gemini" / "skills", shared_skills(machine)],
    }[host]


def shared_skills(machine: Optional[Machine] = None) -> Path:
    """``~/.agents/skills``: Codex and Gemini CLI read it, and it is some Skills CLI agents' own."""
    return _machine(machine).home / ".agents" / "skills"


# The skill folders each app owns: a loose skill found in one is that app's to move aside, unless
# the folder is a Skills CLI agent's here (``_claimed``).
def _own_skill_folders(host: str, machine: Machine) -> List[Path]:
    return {"claude": [claude_dir(machine) / "skills"], "codex": [codex_home(machine) / "skills", shared_skills(machine)],
            "cursor": [machine.home / ".cursor" / "skills"], "grok": [machine.home / ".grok" / "skills"],
            "gemini": [machine.home / ".gemini" / "skills", shared_skills(machine)]}.get(host, [])


# --- the agents without a plugin: the skills through the Skills CLI ----------------------------

# The command, and what it adds: the plugin's branch, every skill in it.
SKILLS_CLI = ("npx", "-y", "skills@latest")
SKILLS_SOURCE = f"{REPOSITORY}#{BRANCH}"
NEED_NODE = "the skills need Node (npx): install Node, then run this again"


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


def uvx(machine: Optional[Machine] = None) -> Optional[str]:
    """uvx at its absolute path, which an app opened from the Dock or the Start menu needs: on PATH,
    else where uv's installer puts it."""
    machine = _machine(machine)
    name = "uvx.exe" if machine.windows else "uvx"
    found = machine.which("uvx")
    if found:
        return os.path.abspath(found)
    environ, home = machine.environ, machine.home
    for folder in (environ.get("UV_INSTALL_DIR"), environ.get("XDG_BIN_HOME"), str(home / ".local" / "bin"),
                   str(home / ".cargo" / "bin")):
        for candidate in ((Path(folder) / name, Path(folder) / "bin" / name) if folder else ()):
            if candidate.is_file() and os.access(candidate, os.X_OK):
                return str(candidate)
    return None


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
    ours: bool = False  # the copy the release installs: the catalog on `latest`
    store: bool = False  # a store's: reported, never touched
    removable: bool = True  # False: another scope's (a project's), reported and left
    entry: Optional[Dict[str, Any]] = None  # a server's entry, as its config holds it

    def words(self, machine: Optional[Machine] = None) -> str:
        what = {"server": f"the server {self.name}", "skills": f"loose skill {shown(self.name, machine)}",
                "folder": shown(self.name, machine), "store": shown(self.name, machine)}.get(self.kind, self.name)
        version = f" {self.version}" if self.version and self.kind not in ("skills", "folder", "store") else ""
        return f"{what}{version}" + (f" ({self.detail})" if self.detail else "")


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


def _detect_claude(machine: Machine) -> App:
    app = App("claude", command=find_cli("claude", machine))
    folder = claude_dir(machine)
    if app.command:
        app.seen.append("the claude command")
    if folder.is_dir():
        app.seen.append(shown(folder, machine))
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
                    app.marketplaces[market["name"]] = {"repo": market.get("repo"), "ref": market.get("ref")}
        except (CommandFailed, ValueError) as error:
            app.notes.append(f"could not list its plugins: {_failure(error)}")
            plugins = None
    if plugins is None:  # no command: the records Claude Code keeps
        recorded, _problem = _json(folder / "plugins" / "installed_plugins.json")
        table = recorded.get("plugins") if isinstance(recorded, dict) else None
        plugins = [{"id": key, **entry} for key, entries in (table.items() if isinstance(table, dict) else ())
                   for entry in (entries if isinstance(entries, list) else []) if isinstance(entry, dict)]
        known, _problem = _json(folder / "plugins" / "known_marketplaces.json")
        for name, entry in (known.items() if isinstance(known, dict) else ()):
            source = entry.get("source") if isinstance(entry, dict) else None
            if isinstance(source, dict):
                app.marketplaces[name] = {"repo": source.get("repo"), "ref": source.get("ref")}
    for plugin in plugins if isinstance(plugins, list) else []:
        identifier = str(plugin.get("id", "")) if isinstance(plugin, dict) else ""
        if identifier.split("@")[0] != PLUGIN:
            continue
        market = identifier.split("@", 1)[1] if "@" in identifier else ""
        scope = plugin.get("scope") or "user"
        store = market in CLAUDE_STORES or scope in CLAUDE_STORE_SCOPES
        detail = ("a development install" if market == DEV_MARKETPLACE else "claude.ai's" if store
                  else f"{scope} scope" if scope != "user" else f"the {market} catalog" if market != MARKETPLACE else "")
        app.copies.append(Copy("claude", "plugin", identifier, version=plugin.get("version"),
                               path=plugin.get("installPath"), detail=detail, store=store,
                               ours=market == MARKETPLACE and scope == "user", removable=scope == "user"))
    servers, _problem = _json(claude_json(machine))
    if isinstance(servers, dict):
        _servers(app, servers.get("mcpServers"), claude_json(machine))
    _loose(app, machine)
    return app


def _codex_version(home: Path, market: str) -> Optional[str]:
    cache = home / "plugins" / "cache" / market / PLUGIN
    versions = [path.name for path in cache.iterdir() if path.is_dir()] if cache.is_dir() else []
    return max(versions, key=version_key) if versions else None


def _detect_codex(machine: Machine) -> App:
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
            app.marketplaces[name] = {"repo": entry.get("source"), "ref": entry.get("ref")}
    for identifier, entry in (data.get("plugins") or {}).items():
        if identifier.split("@")[0] != PLUGIN or "@" not in identifier:
            continue
        market = identifier.split("@", 1)[1]
        store = market.startswith(CODEX_STORE_PREFIX)
        enabled = not isinstance(entry, dict) or entry.get("enabled", True) is not False
        detail = ("a development install" if market == DEV_MARKETPLACE else "its app directory's" if store
                  else f"the {market} catalog" if market != MARKETPLACE else "")
        if not enabled:
            detail = ", ".join(word for word in (detail, "disabled") if word)
        app.copies.append(Copy("codex", "plugin", identifier, version=_codex_version(home, market), detail=detail,
                               store=store, ours=market == MARKETPLACE))
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


def _detect_cursor(machine: Machine) -> App:
    app = App("cursor")
    folder = machine.home / ".cursor"
    if folder.is_dir():
        app.seen.append(shown(folder, machine))
    if machine.which("cursor-agent"):
        app.seen.append("the cursor-agent command")
    app.present = bool(app.seen)
    if not app.present:
        return app
    app.command = machine.which("git")
    for path in cursor_installed(machine):
        origin, branch = _git_head(path)
        ours = _same_repository(origin) and branch == BRANCH
        detail = ("a development install" if (path / DEV_MARK).is_file() else "" if ours
                  else f"a clone of {origin}" + (f" at {branch}" if branch else "") if origin else "copied by hand")
        app.copies.append(Copy("cursor", "folder", str(path), path=str(path), ours=ours, detail=detail,
                               version=_manifest_version(path, ".cursor-plugin/plugin.json", "plugin.json")))
    cache = folder / "plugins" / "cache"
    for path in sorted(cache.glob(f"*/{PLUGIN}")) if cache.is_dir() else []:
        app.copies.append(Copy("cursor", "store", str(path), path=str(path), store=True, detail=CURSOR_STORE + "'s"))
    servers, problem = _json(folder / "mcp.json")
    if problem:
        app.notes.append(f"{shown(folder / 'mcp.json', machine)} {problem}")
    elif isinstance(servers, dict):
        _servers(app, servers.get("mcpServers"), folder / "mcp.json")
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


def _detect_grok(machine: Machine) -> App:
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


def _detect_gemini(machine: Machine) -> App:
    app = App("gemini", command=find_cli("gemini", machine))
    folder = machine.home / ".gemini"
    if app.command:
        app.seen.append("the gemini command")
    if folder.is_dir():
        app.seen.append(shown(folder, machine))
    app.present = bool(app.seen)
    if not app.present:
        return app
    extensions = folder / "extensions"
    for path in sorted(extensions.iterdir()) if extensions.is_dir() else []:
        install, _problem = _json(path / ".gemini-extension-install.json")
        install = install if isinstance(install, dict) else {}
        root = Path(install["source"]) if install.get("type") == "link" and isinstance(install.get("source"), str) else path
        manifest, _problem = _json(root / "gemini-extension.json")
        if not isinstance(manifest, dict) or manifest.get("name") != PLUGIN:
            continue
        ours = install.get("type") == "git" and _same_repository(install.get("source")) and install.get("ref") == BRANCH
        source = install.get("source")
        detail = ("" if ours else "a linked folder" if install.get("type") == "link"
                  else f"from {source}" + (f" at {install.get('ref')}" if install.get("ref") else "") if source else "")
        app.copies.append(Copy("gemini", "extension", PLUGIN, version=manifest.get("version"), path=str(path),
                               detail=detail, ours=ours))
    settings, problem = _json(folder / "settings.json")
    if problem:
        app.notes.append(f"{shown(folder / 'settings.json', machine)} {problem}")
    elif isinstance(settings, dict):
        _servers(app, settings.get("mcpServers"), folder / "settings.json")
    _loose(app, machine)
    return app


def _detect_desktop(machine: Machine) -> App:
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


DETECTORS: Dict[str, Callable[[Machine], App]] = {
    "claude": _detect_claude, "claude-desktop": _detect_desktop, "codex": _detect_codex, "cursor": _detect_cursor,
    "grok": _detect_grok, "gemini": _detect_gemini,
}


def detect(machine: Optional[Machine] = None, apps: Sequence[str] = APPS) -> Dict[str, App]:
    """Every app in ``apps``: whether it is here, and every copy of the plugin it loads. An app whose
    folders cannot be read is here, and left alone (``unreadable``)."""
    machine = _machine(machine)
    found = {}
    for name in apps:
        try:
            found[name] = DETECTORS[name](machine)
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


def _follows(market: Optional[Dict[str, Any]]) -> bool:
    """Whether a catalog the app knows is this repository's on ``latest``."""
    return bool(market) and _same_repository(market.get("repo")) and market.get("ref") == BRANCH


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
    return Step(app.id, action, words, commands=[[cli, *argv] for argv in commands])


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


def _catalog(app: App, cli: str, flavour: str) -> Tuple[List[List[str]], bool]:
    """The commands that make the app's catalog this repository's on ``latest``, and whether one is
    added: refreshed when it follows ``latest``, else removed (which takes its plugins with it) and
    added again, since neither app re-points a catalog in place."""
    market = app.marketplaces.get(MARKETPLACE)
    if _follows(market):
        return [[cli, "plugin", "marketplace", "update" if flavour == "claude" else "upgrade", MARKETPLACE]], False
    added = ([cli, "plugin", "marketplace", "add", f"{REPOSITORY}#{BRANCH}"] if flavour == "claude"
             else [cli, "plugin", "marketplace", "add", REPOSITORY, "--ref", BRANCH])
    return ([[cli, "plugin", "marketplace", "remove", MARKETPLACE]] if market else []) + [added], True


def _plan_catalog(app: App, release: str, machine: Machine, flavour: str) -> List[Step]:
    """Claude Code and Codex: the catalog and its plugin, ``text-to-cad@earthtojake``."""
    steps = _stores(app, machine) + _duplicates(app, machine)
    ours = app.ours()
    if app.stores():
        if ours:
            steps.append(_removal(app, ours, machine))
        return steps
    if not app.command:
        steps.append(_leave(app, f"no {flavour} command on this PATH: "
                                 + ("update" if ours else "install") + f" {PLUGIN} from {app.label} itself"))
        return steps
    cli, market = app.command, app.marketplaces.get(MARKETPLACE)
    add = [cli, "plugin", "install" if flavour == "claude" else "add", PLUGIN_ID]
    if ours is not None and _follows(market):
        status = _status(ours, release)
        if status == "current":
            return steps + [_leave(app, f"{PLUGIN_ID} {ours.version}: up to date")]
        if status == "newer":
            return steps + [_leave(app, f"{PLUGIN_ID} {ours.version}: newer than {release}, left alone")]
        refresh = [cli, "plugin", "update", PLUGIN_ID] if flavour == "claude" else add
        commands, _added = _catalog(app, cli, flavour)
        steps.append(Step(app.id, "update", f"{PLUGIN_ID} {ours.version or '?'} -> {release}", commands + [refresh]))
        return steps
    commands, _added = _catalog(app, cli, flavour)
    where = f"from {REPOSITORY} at {BRANCH}"
    if ours is not None:  # installed from the catalog on another branch: re-pointed at latest
        steps.append(Step(app.id, "update", f"{PLUGIN_ID} {ours.version or '?'} -> {release}, {where}",
                          commands + [add]))
    else:
        steps.append(Step(app.id, "install", f"{PLUGIN_ID} {where}", commands + [add]))
    return steps


def _plan_claude(app: App, release: str, machine: Machine, **_: Any) -> List[Step]:
    return _plan_catalog(app, release, machine, "claude")


def _plan_codex(app: App, release: str, machine: Machine, **_: Any) -> List[Step]:
    return _plan_catalog(app, release, machine, "codex")


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


def _plan_cursor(app: App, release: str, machine: Machine, fed: bool = False, **_: Any) -> List[Step]:
    if fed:
        return _served(app, machine)
    steps = _stores(app, machine) + _duplicates(app, machine)
    ours = app.ours()
    if app.stores():
        if ours:
            steps.append(_removal(app, ours, machine))
        return steps
    target = cursor_plugins(machine) / PLUGIN
    if ours is not None:
        status = _status(ours, release)
        if status != "older":
            return steps + [_leave(app, f"{shown(ours.name, machine)} {ours.version}: "
                                        + ("up to date" if status == "current" else f"newer than {release}, left alone"))]
        if not app.command:
            return steps + [_leave(app, "no git command on this PATH to update it with")]
        return steps + [Step(app.id, "update", f"{shown(ours.name, machine)} {ours.version or '?'} -> {release}",
                             [[app.command, "-C", ours.name, "pull", "--ff-only"]])]
    occupied = target.exists() and not any(copy.path == str(target) for copy in app.copies)
    if occupied:
        return steps + [_leave(app, f"{shown(target, machine)} holds something else: move it away, then run this again")]
    if not app.command:
        return steps + [_leave(app, "no git command on this PATH to clone the plugin with")]
    return steps + [Step(app.id, "install", f"{shown(target, machine)}, a clone of {REPOSITORY} at {BRANCH}",
                         [[app.command, "clone", "--depth", "1", "--branch", BRANCH, REPOSITORY_URL, str(target)]])]


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


def _plan_gemini(app: App, release: str, machine: Machine, **_: Any) -> List[Step]:
    steps = _duplicates(app, machine)
    if not app.command:
        return steps + [_leave(app, f"no gemini command on this PATH: install {PLUGIN} with Gemini CLI")]
    ours = app.ours()
    if ours is not None:
        status = _status(ours, release)
        if status != "older":
            return steps + [_leave(app, f"the {PLUGIN} extension {ours.version}: "
                                        + ("up to date" if status == "current" else f"newer than {release}, left alone"))]
        return steps + [Step(app.id, "update", f"the {PLUGIN} extension {ours.version or '?'} -> {release}",
                             [[app.command, "extensions", "update", PLUGIN]])]
    # Never auto-updated: no update arrives but the one the person asks for (``cad update``).
    return steps + [Step(app.id, "install", f"the {PLUGIN} extension from {REPOSITORY_URL} at {BRANCH}",
                         [[app.command, "extensions", "install", REPOSITORY_URL, "--ref", BRANCH, "--consent"]])]


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


def _plan_skills(release: str, machine: Machine, agents: Sequence[str],
                 record: Optional[Mapping[str, Any]]) -> List[Step]:
    """The Skills CLI agents here among ``agents``: one ``npx skills add`` for every one whose folder
    lacks a skill of ours or got them from another release (``record``, the receipt's), the rest
    up to date."""
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
        elif had or have:
            why = (f"{', '.join(missing[:3])}{f' +{len(missing) - 3}' if len(missing) > 3 else ''} missing"
                   if before == release else f"from text-to-cad {before or '?'} -> {release}")
            due.append(Step(agent, "update", f"the skills in {where}" + (": " if before == release else ", ") + why))
            steps.append(due[-1])
        else:
            due.append(Step(agent, "install", f"the skills, copied into {where} by the Skills CLI"))
            steps.append(due[-1])
    if due:
        argv = [npx, *SKILLS_CLI[1:], "add", SKILLS_SOURCE, "-g"]
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


def plan(apps: Mapping[str, App], *, release: str, desktop_entry: Optional[Dict[str, Any]] = None,
         only: Optional[Sequence[str]] = None, machine: Optional[Machine] = None,
         skills: Optional[Mapping[str, Any]] = None) -> List[Step]:
    """What to do for every selected app that is here, in ``APPS`` order: each app's duplicates
    taken out before its copy is installed or updated, so two copies never load at once; then the
    skills for the Skills CLI agents here (``skills``: the receipt's record of them)."""
    machine = _machine(machine)
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
        steps += PLANNERS[name](app, release, machine, fed=fed and name in FED_BY, desktop_entry=desktop_entry)
    steps += _plan_skills(release, machine, [agent for agent in SKILLS_AGENTS if not only or agent in only], skills)
    return _once(steps) + _shared_note(apps, steps, machine)


# --- taking it out ------------------------------------------------------------------------------


def touched(receipt: Optional[Mapping[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """What a receipt says the installer did to each app, in the order it first did it: ``installed``
    (it installed or updated our copy), ``added`` (it added the catalog), ``clone`` (Cursor's folder),
    and ``edit`` (Claude Desktop's config: the first edit's ``.bak``, or that it made the file, and
    the last edit's hash and server entry)."""
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
                   only: Optional[Sequence[str]] = None, machine: Optional[Machine] = None) -> List[Step]:
    """The removals: with a receipt, what it says the installer did, in reverse; without one, every
    copy found but a store's."""
    machine = _machine(machine)
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
            commands = []
            if ours is not None and app.command:
                commands.append([app.command, "plugin", "uninstall" if name == "claude" else "remove", PLUGIN_ID])
            if record.get("added") and MARKETPLACE in app.marketplaces and app.command:
                commands.append([app.command, "plugin", "marketplace", "remove", MARKETPLACE])
            if commands:
                steps.append(Step(name, "remove", PLUGIN_ID, commands))
        elif name in ("gemini", "grok"):
            if ours is not None and app.command:
                argv = ["extensions", "uninstall", PLUGIN] if name == "gemini" else ["plugin", "uninstall", PLUGIN]
                steps.append(Step(name, "remove", ours.words(machine), [[app.command, *argv]]))
        elif name == "cursor":
            clone = record.get("clone")
            if clone and any(copy.ours and copy.path == clone for copy in app.copies):
                steps.append(Step(name, "remove", shown(clone, machine), edit={"op": "remove", "path": clone}))
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
        if step.agents and argv[3:4] == ["add"]:  # the skills the Skills CLI says it installed
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
        elif edit["op"] == "move":
            folder = Path(aside or tempfile.gettempdir()) / step.app
            target = move_aside(edit["path"], folder)
            say(f"move {shown(edit['path'], machine)} to {shown(target, machine)}")
            record.update({"kind": "move", "path": edit["path"], "to": str(target)})
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
