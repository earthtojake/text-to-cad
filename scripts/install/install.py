"""text-to-cad's installer: the program `install.sh` and `install.ps1` download from beside themselves and
run with uv's Python (the standard library alone, nothing imported from this repository).

    curl -fsSL https://texttocad.dev/install.sh | sh          # macOS and Linux
    irm https://www.texttocad.dev/install.ps1 | iex           # Windows PowerShell

It takes no options and does five things, in order:

1. finds the newest release (the version feed; ``FALLBACK``, the release it was published with, when the
   feed cannot be read or names an older one);
2. runs that release's ``cad setup`` through uvx, which installs text-to-cad and the ``cad`` command (where
   that fails because the shell is an agent's sandbox, exit status 3, it stops: the apps' commands would fail
   there too);
3. installs or updates the plugin in each agent app it finds, with that app's own command, from the GitHub
   repository's ``latest`` branch, or copies the skills into the agent's own skills folder;
4. only then removes what earlier releases left in that app (each row of ``APPS``), Claude Desktop's server,
   and the loose copies of our skills (``remove_loose_skills``): the new copy is in place before an old one
   goes, so a failed download or a GitHub outage leaves every app with what it had;
5. prints one line per app as it finishes. One app failing, even with an error no row foresaw, never stops
   the others. It exits nonzero when ``cad setup`` failed or every app it found failed.

What it removes is only what is provably ours: our names AND a sign that it is ours (our catalog, a path in
cad's state folder, a git origin naming our repository, a SKILL.md whose front matter or provenance line
names our repository: ``our_skill``). A store's copy (claude.ai's directory, Codex's directory) and every
plugin or skill of someone else's are never touched. What is provably ours is deleted (a link to it unlinked,
never followed); a git clone of ours only where it has no change of its own.

``APPS`` is the one table of apps: a row says how the app is found, how ours is installed and updated
(from GitHub, and from a local folder for ``scripts/install/dev_install.py``), and how our old copies
there are found and removed. A correction is one row. Each row's comment says how its commands were
checked: by the vendor's documentation (its address), by the CLI's own ``--help``, by superpowers'
practice, or not at all.

Test hooks, never documented to people: ``CAD_INSTALL_FEED`` (the version feed's address),
``CAD_INSTALL_FROM`` (what uvx runs ``cad setup`` from instead of ``cad-server==<release>``: a wheel, for the
installer rehearsals), ``CODEX_CLI`` (the codex command, as earlier installers took it),
``CAD_INSTALL_PATH_ONLY`` (look for the apps' commands on PATH and in ``~/.local/bin`` alone: never in
Homebrew's or npm's folders or an app's bundle, where a test would find a real CLI).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import signal
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

# The release this file was published with (stamped by scripts/release/sync-version.mjs): installed when the
# version feed cannot be read, and never anything older.
FALLBACK = "0.11.10"
FEED = "https://api.texttocad.dev/v1/versions"
REPOSITORY = "earthtojake/text-to-cad"
URL = f"https://github.com/{REPOSITORY}"
BRANCH = "latest"
PLUGIN = "text-to-cad"
CATALOG = "earthtojake"          # the repository's catalog: a GitHub copy is text-to-cad@earthtojake
DEV_CATALOG = "earthtojake-dev"  # a checkout's development install (dev_install.py)
LOCAL_CATALOG = "text-to-cad"    # the folder catalog 0.10.0-0.11.10's installer wrote, <state>/plugin
# Every catalog of ours an app may hold. Of these, the one the source installs from is kept and brought up to date;
# the others are removed with their plugins, once ours is in.
OUR_CATALOGS = (LOCAL_CATALOG, CATALOG, DEV_CATALOG)
# The plugin names we ever used: `cad` until 0.7.6, `text-to-cad` since.
OUR_PLUGINS = ("text-to-cad", "cad")
SKILLS = ("cad", "engineering-drawing", "fea", "pcb", "print3d", "render", "robot-simulation", "sendcutsend")
# Skills an earlier release shipped and this one does not (implicit-cad: releases before 0.5).
RETIRED_SKILLS = ("bambu-labs", "dfam-check", "dfm", "dxf", "gcode", "pcb-dfm", "sdf", "simulation", "srdf",
                  "step-parts", "urdf", "cad-viewer", "cad-mcp-setup", "implicit-cad")
# How a SKILL.md of ours says so, checked in every release tagged from v0.5.0 to v0.11.10 (every skill of each):
# 0.10.0 and later, its front matter's `metadata:` block holds `repository: earthtojake/text-to-cad`; 0.5.0 to
# 0.8.4, its body has this line, word for word. A skill that merely mentions the repository is not ours.
PROVENANCE_LINE = "Provenance: maintained in [earthtojake/text-to-cad](https://github.com/earthtojake/text-to-cad)."
# Marks earlier installers wrote: in Cursor's plain copy (0.10.0-0.11.10), in a development install's copy.
COPY_MARK = ".text-to-cad-copy"
DEV_MARK = ".text-to-cad-dev"
UVX_ARGS = ("--no-config", "--managed-python", "--python", "3.14")
# `cad setup`'s exit status for "this version cannot be installed from this shell" (an agent's sandbox).
SETUP_SANDBOXED = 3
# How long one app command may take before it is stopped (with every process it started). The slowest is a
# clone of the `latest` branch (1.4 MB, about a second measured); three minutes is that a hundredfold on a slow
# line, and a CLI that hangs (a prompt it should not show, a lock) costs the run three minutes, not fifteen.
COMMAND_SECONDS = 180
# Where Homebrew puts the commands it installs (Apple silicon's, Intel macOS's, Linux's): not on the PATH of a
# shell an app opened, so earlier releases looked there too.
HOMEBREW = ("/opt/homebrew/bin", "/usr/local/bin", "/home/linuxbrew/.linuxbrew/bin")
# The CLI the Codex app bundles (macOS).
CODEX_BUNDLED = "/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex"
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

    @property
    def path_only(self) -> bool:
        return bool(self.environ.get("CAD_INSTALL_PATH_ONLY"))

    def search_path(self) -> str:
        """PATH, then ~/.local/bin (where many CLIs install themselves before a new shell has it on PATH), then
        Homebrew's folders and npm's global folder, which a shell an app opened may lack."""
        folders = [self.environ.get("PATH", os.defpath), str(self.home / ".local" / "bin")]
        if not self.path_only:
            if not self.windows:
                folders += HOMEBREW
            prefix = self.environ.get("NPM_CONFIG_PREFIX") or self.environ.get("npm_config_prefix")
            if prefix:
                folders.append(prefix if self.windows else str(Path(prefix) / "bin"))
            if self.windows:
                folders.append(str(Path(self.environ.get("APPDATA") or self.home / "AppData" / "Roaming") / "npm"))
            else:
                folders.append(str(self.home / ".npm-global" / "bin"))
        return os.pathsep.join(folder for folder in folders if folder)

    def which(self, name: str) -> Optional[str]:
        return shutil.which(name, path=self.search_path()) if name else None

    def config_home(self) -> Path:
        return Path(self.environ.get("XDG_CONFIG_HOME") or self.home / ".config")

    def shown(self, path: Any) -> str:
        """``path`` as a person reads it: the home folder spelled ``~``."""
        text, home = str(path), str(self.home).rstrip("/\\")
        return "~" + text[len(home):] if home and (text == home or text.startswith(home + os.sep)) else text

    def run(self, argv: Sequence[Any], cwd: Optional[Path] = None, answer: Optional[str] = None,
            timeout: float = COMMAND_SECONDS, environ: Optional[Dict[str, str]] = None) -> Ran:
        """``argv`` run with nothing to read but ``answer``, what it printed captured; stopped, with every process
        it started, after ``timeout`` seconds."""
        env = {**self.environ, "GIT_TERMINAL_PROMPT": "0", **(environ or {})}
        group = ({"creationflags": getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)} if os.name == "nt"
                 else {"start_new_session": True})
        try:
            process = subprocess.Popen([str(part) for part in argv], cwd=str(cwd) if cwd else None, env=env,
                                       stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, **group)
        except OSError as error:
            return Ran(127, f"{type(error).__name__}: {error}")
        try:
            out, _ = process.communicate((answer or "").encode("utf-8"), timeout=timeout)
        except subprocess.TimeoutExpired:
            _stop(process)
            return Ran(124, f"no answer in {int(timeout)} s: stopped")
        return Ran(process.returncode, (out or b"").decode("utf-8", "replace"))

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


def _stop(process: "subprocess.Popen[bytes]") -> None:
    """A command that did not answer stopped, with what it started (its process group; on Windows its tree)."""
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(process.pid)], stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=30)
        else:
            os.killpg(process.pid, signal.SIGKILL)
    except (OSError, subprocess.SubprocessError):
        process.kill()
    try:
        process.communicate(timeout=10)
    except (OSError, ValueError, subprocess.SubprocessError):
        pass


def version_key(text: Any) -> Tuple[int, ...]:
    found = re.match(r"\d+(?:\.\d+)*", text if isinstance(text, str) else "")
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
    except (OSError, ValueError):
        return {}
    try:
        import tomllib  # type: ignore[import-not-found]

        found = tomllib.loads(text)
        return found if isinstance(found, dict) else {}
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
                found = table.setdefault(part[0] or part[1], {})
                table = found if isinstance(found, dict) else {}
            continue
        pair = re.fullmatch(r'([A-Za-z0-9_-]+)\s*=\s*"([^"]*)"', line)
        if pair:
            table[pair.group(1)] = pair.group(2)
    return data


def table(value: Any) -> Dict[str, Any]:
    """``value`` where it is a table (a dict), else an empty one: a config is a person's file, of any shape."""
    return value if isinstance(value, dict) else {}


# --- removing, never half ---------------------------------------------------------------------------


def _rmtree(path: Path) -> None:
    """A folder deleted, read-only files too (Windows will not delete a read-only file, and git marks its packs
    read-only): each one refused is made writable and tried again."""
    def again(function: Callable[[str], Any], name: str, *_error: Any) -> None:
        try:
            os.chmod(name, stat.S_IWRITE | stat.S_IREAD | (stat.S_IEXEC if os.path.isdir(name) else 0))
            parent = os.path.dirname(name)
            os.chmod(parent, os.stat(parent).st_mode | stat.S_IWRITE)
        except OSError:
            pass
        function(name)

    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=again)
    else:  # the 3.11 and earlier spelling
        shutil.rmtree(path, onerror=again)


def discard(path: Path) -> None:
    """A link unlinked (never what it points at), a file deleted, a folder moved out of its place in one rename
    and then deleted: never half a folder left where an app reads it. The folder is moved into a hidden folder
    beside it, one level down, where no app looks for a plugin or a skill; if deleting it there fails, what is
    left is out of the way."""
    path = Path(path)
    if path.is_symlink() or path.is_file():
        path.unlink()
        return
    if not path.exists():
        return
    trash = Path(tempfile.mkdtemp(prefix=".text-to-cad-trash-", dir=str(path.parent)))
    os.replace(str(path), str(trash / path.name))
    try:
        _rmtree(trash)
    except OSError:
        pass


def copy_tree(source: Path, target: Path) -> bool:
    """``source`` copied to ``target``: real files, links followed, caches left out. Staged in a hidden folder
    beside the target, then swapped in (``swap``): the old one, which the caller has found to be ours, goes only
    once the new one is whole, and comes back if the swap fails. Whether there was an old one."""
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".text-to-cad-new-", dir=str(target.parent)))
    try:
        staged = staging / target.name
        shutil.copytree(str(source), str(staged), symlinks=False,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store", ".git"))
        return swap(staged, target)
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def swap(staged: Path, target: Path) -> bool:
    """``staged`` put in ``target``'s place in two renames on one disk: the old ``target`` moved out (into a hidden
    folder beside it), the new one in, the old one put back where that fails. Then the old one, which the caller has
    found to be ours, is deleted (a link unlinked, never followed). Whether there was an old one."""
    if not (target.exists() or target.is_symlink()):
        os.replace(str(staged), str(target))
        return False
    held = Path(tempfile.mkdtemp(prefix=".text-to-cad-old-", dir=str(target.parent)))
    try:
        os.replace(str(target), str(held / target.name))
        try:
            os.replace(str(staged), str(target))
        except OSError:
            os.replace(str(held / target.name), str(target))
            raise
        discard(held / target.name)
    finally:
        try:
            held.rmdir()  # only where it is empty: never the old copy, should it still be there
        except OSError:
            pass
    return True


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
    if not path or not isinstance(path, (str, Path)):
        return False
    if any(within(path, state) for state in here.state_dirs()):
        return True
    parts = Path(str(path)).parts
    if len(parts) >= 2 and parts[-1] == "plugin" and parts[-2] in ("cad", "cad-state"):
        return True
    for manifest in (".claude-plugin/marketplace.json", ".claude-plugin/plugin.json", "gemini-extension.json"):
        try:
            if URL in (Path(path) / manifest).read_text(encoding="utf-8", errors="replace"):
                return True
        except OSError:
            continue
    return False


def front_matter(text: str) -> Optional[List[str]]:
    """The lines of a SKILL.md's front matter, between its first two ``---`` lines."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    for index, line in enumerate(lines[1:], 1):
        if line.strip() == "---":
            return lines[1:index]
    return None


def skill_name(text: str) -> Optional[str]:
    """The ``name`` in a SKILL.md's front matter."""
    for line in front_matter(text) or ():
        if line.startswith("name:"):
            return line[len("name:"):].strip().strip("\"'")
    return None


def _metadata_repository(header: Sequence[str]) -> Optional[str]:
    """``metadata.repository`` in front matter lines: the indented ``repository:`` under a ``metadata:`` line."""
    inside = False
    for line in header:
        if not line.strip():
            continue
        if not line[:1].isspace():
            inside = line.split("#", 1)[0].strip() == "metadata:"
            continue
        if inside and line.strip().startswith("repository:"):
            return line.strip()[len("repository:"):].split(" #", 1)[0].strip().strip("\"'")
    return None


def our_skill(folder: Path) -> Optional[bool]:
    """Whether a skill folder is ours: its SKILL.md has one of our skills' names (current or retired) and says it
    is ours as our releases wrote it (``PROVENANCE_LINE``): its front matter's ``metadata.repository`` is our
    repository, or its body has our provenance line. None where it holds no readable SKILL.md (a link to nowhere, an
    empty folder): not ours to judge."""
    try:
        text = (Path(folder) / "SKILL.md").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    header = front_matter(text)
    if header is None or skill_name(text) not in (*SKILLS, *RETIRED_SKILLS):
        return False
    return (_metadata_repository(header) == REPOSITORY
            or any(line.strip() == PROVENANCE_LINE for line in text.splitlines()))


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
    _reachable: Optional[str] = None

    @property
    def local(self) -> bool:
        return self.folder is not None

    def words(self) -> Dict[str, str]:
        return {"repo": REPOSITORY, "url": URL, "branch": BRANCH, "plugin": PLUGIN, "catalog": self.catalog,
                "folder": str(self.folder or "")}

    def reachable(self, here: Here) -> None:
        """Before anything of ours is taken out to be replaced: that the ``latest`` branch can be reached
        (``git ls-remote``, else the branch's archive answering). ``Failed`` where it cannot, nothing changed."""
        if self.local:
            return
        if self._reachable is None:
            git = here.which("git")
            if git:
                ran = here.run([git, "ls-remote", "--exit-code", "--heads", URL, BRANCH], timeout=60)
                self._reachable = "" if ran.ok else ran.last()
            else:
                try:
                    request = urllib.request.Request(f"https://codeload.github.com/{REPOSITORY}/tar.gz/refs/heads/{BRANCH}",
                                                     method="HEAD")
                    with urllib.request.urlopen(request, timeout=20):
                        self._reachable = ""
                except Exception as error:  # noqa: BLE001 - any failure means not reachable
                    self._reachable = type(error).__name__
        if self._reachable:
            raise Failed(f"GitHub could not be reached ({self._reachable}): the copy there was left as it was")

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
        shutil.rmtree(target, ignore_errors=True)
        archive = Path(self._scratch) / "latest.tar.gz"
        try:
            with urllib.request.urlopen(f"https://codeload.github.com/{REPOSITORY}/tar.gz/refs/heads/{BRANCH}",
                                        timeout=60) as answer, open(archive, "wb") as out:
                shutil.copyfileobj(answer, out)
            with tarfile.open(archive) as tar:
                members = [member for member in tar.getmembers() if member.isfile() or member.isdir()]
                if any(member.name.startswith("/") or ".." in Path(member.name).parts for member in members):
                    raise Failed("the downloaded archive is not a plain folder")
                tar.extractall(target, members=members, **({"filter": "data"} if hasattr(tarfile, "data_filter") else {}))
        except (OSError, tarfile.TarError, ValueError) as error:
            raise Failed(f"could not download the skills ({type(error).__name__}): nothing was changed") from error
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
    """What one run knows as it goes: the source, and whether Claude Code now has our plugin (Cursor and Grok Build
    load Claude Code's plugins, so they then need none of their own)."""

    source: Source
    claude_has_ours: bool = False
    claude_found: bool = False


@dataclass
class Outcome:
    status: str  # installed, updated, removed, skipped, failed; or note: the words alone, nothing done
    words: str = ""
    removed: List[str] = field(default_factory=list)
    has_ours: Optional[bool] = None  # whether the app now has our plugin; by default, installed or updated

    @property
    def ours(self) -> bool:
        return self.has_ours if self.has_ours is not None else self.status in ("installed", "updated")

    def line(self, name: str) -> str:
        if self.status == "note":
            return f"{name}: {self.words}"
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
    copies need more than its commands (Claude Code, Codex, Cursor, Gemini CLI, Grok Build, Claude Desktop,
    Hermes Agent, Antigravity).
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
    """An app installed and updated by its own commands alone (nothing of ours is removed)."""
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
                    plugins: Sequence[str], verbs: Dict[str, Any]) -> Outcome:
    """Claude Code's and Codex's flow. First ours is put in: the source's catalog added (or brought up to date) and
    our plugin installed (or updated) from it. Only once that worked do our other catalogs and plugins go. Where a
    catalog of ours under the source's name points elsewhere (``main``, a checkout) it must be replaced: GitHub is
    checked first, and if the new one cannot be added and installed, the old one is put back. ``verbs``: the app's
    commands, by what they do; ``verbs["readd"]`` makes the command that adds a recorded catalog again."""
    if not cli:
        return NOT_FOUND
    source = context.source
    target = source.catalog
    ours = f"{PLUGIN}@{target}"
    words = source.words()

    def do(key: str) -> None:
        for argv in verbs[key]:
            here.must([cli, *[part.format(**words) for part in argv]])

    def ids(name: str) -> List[str]:
        return [plugin for plugin in plugins if plugin.endswith(f"@{name}") and plugin.split("@")[0] in OUR_PLUGINS]

    present = catalogs.get(target)
    if present is not None and not present.ours(here):
        raise Failed(f"the {target} catalog is another source's ({present.where or present.kind}): left alone")
    replaced = False
    if present is not None and present.matches(here, source):
        do("refresh")
        do("update" if ours in plugins else "install")
        status = "updated" if ours in plugins else "installed"
    elif present is not None:
        # Ours, from another source: replaced, and put back if the new one does not go in.
        source.reachable(here)
        had = ours in plugins
        for plugin in ids(target):
            here.must([cli, *verbs["remove"][0], plugin])
        here.must([cli, *verbs["forget"][0], target])
        replaced = True
        try:
            do("add_local" if source.local else "add")
            do("install")
        except Failed as error:
            try:
                here.must([cli, *verbs["readd"](present)])
                if had:
                    here.must([cli, *[part.format(**words) for part in verbs["install"][0]]])
                back = "the earlier copy was put back"
            except Failed as again:
                back = f"the earlier copy could not be put back ({again}): run this again"
            raise Failed(f"{error}; {back}") from error
        status = "updated" if had else "installed"
    else:
        do("add_local" if source.local else "add")
        do("install")
        status = "installed"
    # Ours is in: now our other copies go. One that cannot be removed is said, and ours stays installed.
    removed, notes = [], []
    for name in OUR_CATALOGS:
        catalog = catalogs.get(name)
        found = ids(name)
        if name == target:
            for plugin in ([] if replaced else [plugin for plugin in found if plugin != ours]):
                try:
                    here.must([cli, *verbs["remove"][0], plugin])
                    removed.append(plugin)
                except Failed as error:
                    notes.append(f"{plugin} stays ({error})")
            continue
        if catalog is not None and not catalog.ours(here):
            if found:
                notes.append(f"{', '.join(found)} left alone: the {name} catalog is another source's "
                             f"({catalog.where or catalog.kind})")
            continue
        try:
            for plugin in found:
                here.must([cli, *verbs["remove"][0], plugin])
                removed.append(plugin)
            if catalog is not None:
                here.must([cli, *verbs["forget"][0], name])
        except Failed as error:
            notes.append(f"the {name} catalog stays ({error})")
    return Outcome(status, "; ".join(notes), removed)


def claude_dir(here: Here) -> Path:
    return Path(here.environ.get("CLAUDE_CONFIG_DIR") or here.home / ".claude")


def claude_code(app: App, here: Here, context: Context) -> Outcome:
    """Claude Code, from its records (``plugins/installed_plugins.json``, ``plugins/known_marketplaces.json``):
    only the user scope's plugins are ours to change; a project's, an administrator's, and claude.ai's synced
    copies are left. Its command is ``claude``, and only that: never the private copy another app (Claude Desktop)
    keeps for itself. Verified: `claude plugin --help` and its subcommands
    (2.1.316, 2.1.325: `marketplace remove --scope user`); docs https://code.claude.com/docs/en/discover-plugins
    (`owner/repo#ref` pins a branch; `marketplace remove` uninstalls its plugins; `plugin update
    <plugin>@<marketplace>`)."""
    cli = here.which("claude")
    context.claude_found = bool(cli)
    folder = claude_dir(here) / "plugins"
    recorded = table(read_json(folder / "installed_plugins.json"))
    plugins = [name for name, entries in table(recorded.get("plugins")).items()
               if any((entry.get("scope") or "user") == "user"
                      for entry in (entries if isinstance(entries, list) else [entries]) if isinstance(entry, dict))]
    catalogs = {}
    for name, entry in table(read_json(folder / "known_marketplaces.json")).items():
        source = table(entry).get("source")
        if not isinstance(source, dict):
            continue
        kind = source.get("source")
        where = source.get("path") if kind == "directory" else source.get("repo") or source.get("url") or ""
        catalogs[name] = Catalog(name, kind if kind in ("github", "git", "directory") else "other", str(where or ""),
                                 str(source.get("ref") or ""))

    def readd(catalog: Catalog) -> List[str]:
        place = catalog.where + (f"#{catalog.ref}" if catalog.ref and catalog.kind != "directory" else "")
        return ["plugin", "marketplace", "add", place]

    verbs = {
        "remove": [["plugin", "uninstall"]],
        "forget": [["plugin", "marketplace", "remove", "--scope", "user"]],
        "add": [["plugin", "marketplace", "add", "{repo}#{branch}"]],
        "add_local": [["plugin", "marketplace", "add", "{folder}"]],
        "refresh": [["plugin", "marketplace", "update", "{catalog}"]],
        "install": [["plugin", "install", "{plugin}@{catalog}"]],
        "update": [["plugin", "update", "{plugin}@{catalog}"]],
        "readd": readd,
    }
    outcome = marketplace_app(app, here, context, cli, catalogs, plugins, verbs)
    context.claude_has_ours = outcome.ours
    return outcome


def _codex_version(path: str, here: Here) -> Tuple[int, ...]:
    """A ``codex`` command's version: from the metadata its package keeps beside it (the app's bundle's
    ``codex-package.json``, the npm package's ``package.json``), else asked of the command, with ``CODEX_HOME`` a
    folder thrown away after (Codex writes into it as it starts, even for ``--version``). As 0.11.10 did."""
    real = Path(os.path.realpath(path))
    for manifest, (key, value) in ((Path(path).parent.parent / "codex-package.json", ("variant", "codex")),
                                   (real.parent.parent / "package.json", ("name", "@openai/codex"))):
        data = table(read_json(manifest))
        if data.get(key) == value and version_key(data.get("version")):
            return version_key(data["version"])
    thrown_away = tempfile.mkdtemp(prefix="cad-codex-home-")
    try:
        ran = here.run([path, "--version"], timeout=60, environ={"CODEX_HOME": thrown_away})
    finally:
        shutil.rmtree(thrown_away, ignore_errors=True)
    words = ran.out.split()
    return version_key(words[-1]) if ran.ok and words else ()


def codex_cli(here: Here) -> Optional[str]:
    """``CODEX_CLI``, else the newer of the ``codex`` on PATH and the one the Codex app bundles (macOS), as 0.11.10
    chose: both write the ``~/.codex`` the app, the CLI and the IDE extension share, so an install must come from a
    CLI at least as new as the app that reads it."""
    named = here.environ.get("CODEX_CLI")
    if named:
        return here.which(named)
    candidates = [here.which("codex")]
    if here.platform == "darwin" and not here.path_only:
        candidates.append(CODEX_BUNDLED)
    found = list(dict.fromkeys(path for path in candidates if path and os.access(path, os.X_OK)))
    if len(found) < 2:
        return found[0] if found else None
    versions = {path: _codex_version(path, here) for path in found}
    return max(found, key=lambda path: versions[path])


def codex(app: App, here: Here, context: Context) -> Outcome:
    """Codex, from its config (``$CODEX_HOME/config.toml``: ``[marketplaces.<name>]`` with ``source_type``,
    ``source`` and ``ref``; ``[plugins."<id>"]``). A copy from OpenAI's directory (``openai-*``) is left.
    Verified: `codex plugin --help` and its subcommands (0.169: `marketplace add <owner/repo> --ref`, `marketplace
    upgrade`, `add`, `remove`); docs https://developers.openai.com/codex/plugins/build (`--ref`, `upgrade`). `add`
    again after `upgrade` copies the plugin again: Codex keeps a copy, and the docs do not say an upgrade refreshes
    it."""
    config = read_toml(Path(here.environ.get("CODEX_HOME") or here.home / ".codex") / "config.toml")
    plugins = list(table(config.get("plugins")).keys())
    catalogs = {}
    for name, entry in table(config.get("marketplaces")).items():
        if isinstance(entry, dict):
            local = entry.get("source_type") == "local"
            catalogs[name] = Catalog(name, "directory" if local else "git", str(entry.get("source") or ""),
                                     str(entry.get("ref") or ""))

    def readd(catalog: Catalog) -> List[str]:
        return ["plugin", "marketplace", "add", catalog.where,
                *(["--ref", catalog.ref] if catalog.ref and catalog.kind != "directory" else [])]

    verbs = {
        "remove": [["plugin", "remove"]],
        "forget": [["plugin", "marketplace", "remove"]],
        "add": [["plugin", "marketplace", "add", "{repo}", "--ref", "{branch}"]],
        "add_local": [["plugin", "marketplace", "add", "{folder}"]],
        "refresh": [] if context.source.local else [["plugin", "marketplace", "upgrade", "{catalog}"]],
        "install": [["plugin", "add", "{plugin}@{catalog}"]],
        "update": [["plugin", "add", "{plugin}@{catalog}"]],
        "readd": readd,
    }
    return marketplace_app(app, here, context, codex_cli(here), catalogs, plugins, verbs)


def git_origin(folder: Path) -> Optional[str]:
    """The ``origin`` URL in a git working copy's config, read as bytes (a config holds any encoding a person's
    name came in)."""
    try:
        config = (Path(folder) / ".git" / "config").read_bytes().decode("utf-8", "replace")
    except OSError:
        return None
    found = re.search(r'\[remote "origin"\][^\[]*?url\s*=\s*(\S+)', config)
    return found.group(1) if found else None


def clone_problem(here: Here, path: Path) -> Optional[str]:
    """Why a git clone of ours may not be updated or removed, or None: it must have no change of its own (``git
    status --porcelain`` empty), be on the ``latest`` branch, tracking it, with no commit of its own."""
    git = here.which("git")
    if not git:
        return "git is needed to check it"
    ran = here.run([git, "-C", path, "status", "--porcelain=v1", "--branch"], timeout=60)
    if not ran.ok:
        return f"git could not read it ({ran.last()})"
    lines = ran.out.splitlines()
    head = lines[0] if lines and lines[0].startswith("## ") else ""
    branch = head[3:].split("...", 1)[0].strip()
    if branch != BRANCH:
        return f"it is on {branch or 'no branch'}, not {BRANCH}"
    if "..." not in head:
        return f"its {BRANCH} tracks no branch on GitHub"
    if "[ahead" in head or "ahead " in head.partition("[")[2]:
        return "it has commits of its own"
    if [line for line in lines[1:] if line.strip()]:
        return "it has changes not committed"
    return None


def cursor(app: App, here: Here, context: Context) -> Outcome:
    """Cursor: a clone of the ``latest`` branch in its local plugins folder (``~/.cursor/plugins/local``). Where
    Claude Code has our plugin, Cursor loads that one (as earlier releases measured), so its own copy of ours goes.
    Earlier copies: 0.10.0-0.11.10's plain copy (marked ``.text-to-cad-copy``), a development copy
    (``.text-to-cad-dev``), both deleted once ours is in. A clone is updated or removed only when it has
    nothing of its own (``clone_problem``); a link there is never followed or changed. Verified: docs
    https://cursor.com/docs/plugins (a plugin is a folder in ~/.cursor/plugins/local; a symlink there is skipped).
    That Cursor loads Claude Code's plugins is not in its docs: earlier releases' observation."""
    base = here.home / ".cursor"
    if not base.is_dir() and not here.which("cursor-agent"):
        return NOT_FOUND
    local = base / "plugins" / "local"
    source = context.source
    target = local / (f"{PLUGIN}-dev" if source.local else PLUGIN)
    removed, notes = [], []

    def kind(path: Path) -> Tuple[str, str]:
        if path.is_symlink():
            return "link", f"{here.shown(path)} is a link: left alone"
        if not path.exists():
            return "absent", ""
        if (path / COPY_MARK).is_file() or (path / DEV_MARK).is_file():
            return "copy", ""
        if our_repository(git_origin(path)):
            problem = clone_problem(here, path)
            return ("clone", "") if problem is None else ("kept", f"{here.shown(path)} left alone: {problem}")
        return "other", ""

    def clear(path: Path) -> None:
        """An earlier copy of ours out, once ours is in (or Claude Code's is)."""
        what, why = kind(path)
        if what in ("link", "kept"):
            notes.append(why)
        elif what == "clone":
            discard(path)
            removed.append(here.shown(path))
        elif what == "copy":
            discard(path)
            removed.append(here.shown(path))

    if context.claude_has_ours and not source.local:
        for path in (local / PLUGIN, local / f"{PLUGIN}-dev"):
            clear(path)
        return Outcome("skipped", "; ".join(["it loads Claude Code's plugin", *notes]), removed, has_ours=True)
    if source.local:
        what, why = kind(target)
        if what in ("link", "kept"):
            return Outcome("skipped", why)
        if what == "other":
            raise Failed(f"{here.shown(target)} holds something else: left alone (move it away, then run this again)")
        copy_tree(source.folder, target)
        (target / DEV_MARK).write_text(f"{source.folder}\n", encoding="utf-8")
        clear(local / PLUGIN)
        return Outcome("installed", "; ".join([f"a copy of {source.folder}", *notes]), removed)
    what, why = kind(target)
    git = here.which("git")
    if what == "link":
        return Outcome("skipped", f"{why} (Cursor does not load a link: put a clone there to use it)")
    if what == "kept":
        return Outcome("skipped", why, has_ours=True)
    if what == "other":
        raise Failed(f"{here.shown(target)} holds something else: left alone (move it away, then run this again)")
    if not git:
        raise Failed("git is needed to install it")
    if what == "clone":
        here.must([git, "-C", target, "fetch", "--quiet", "--depth", "1", "origin", BRANCH])
        here.must([git, "-C", target, "checkout", "--quiet", "-B", BRANCH, "FETCH_HEAD"])
        status = "updated"
    else:  # absent, or an earlier plain copy: the clone made beside it, then swapped in
        local.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=".text-to-cad-new-", dir=str(local)))
        try:
            here.must([git, "clone", "--quiet", "--depth", "1", "--branch", BRANCH, URL, staging / PLUGIN])
            if swap(staging / PLUGIN, target):
                removed.append(f"{here.shown(target)}, the earlier plain copy")
        finally:
            shutil.rmtree(staging, ignore_errors=True)
        status = "updated" if what == "copy" else "installed"
    clear(local / f"{PLUGIN}-dev")
    return Outcome(status, "; ".join(notes), removed)


def gemini(app: App, here: Here, context: Context) -> Outcome:
    """Gemini CLI: its extension, installed from GitHub at ``latest`` (a copy), and installed again to update it:
    ``extensions update`` asks twice (to clone, since GitHub has no release ``latest``; to accept the skills) and
    takes no ``--consent``, so with no one to answer it waits for ever (measured, 0.62.0).
    0.10.0-0.11.10 linked ``<state>/plugin`` under the same name, which must go for ours to come in: GitHub is
    checked first, the old extension's folder and the enablement file are kept aside, and put back where the new
    one does not install. Read from ``~/.gemini/extensions/text-to-cad/.gemini-extension-install.json`` (``type``,
    ``source``, ``ref``). Verified: `gemini extensions --help` and its subcommands (`install <source> --ref
    --consent`, `update <name>`, `uninstall`, `link <path> --consent`); docs
    https://geminicli.com/docs/extensions/reference/."""
    cli = here.which("gemini")
    if not cli:
        return NOT_FOUND
    extensions = Path(here.environ.get("GEMINI_CLI_HOME") or here.home) / ".gemini" / "extensions"
    folder = extensions / PLUGIN
    source = context.source

    def record() -> Dict[str, Any]:
        return table(read_json(folder / ".gemini-extension-install.json"))

    def ours_now() -> bool:
        found = record()
        if source.local:
            return found.get("type") == "link" and same_path(found.get("source"), source.folder)
        return found.get("type") == "git" and our_repository(found.get("source")) and found.get("ref") == BRANCH

    def run(argv: List[Any], answer: Optional[str] = None) -> Ran:
        """A gemini command, run in an empty folder of its own that it is told to trust for that run alone: run in the
        person's folder (their home, often), ``--consent`` records that folder as trusted in trustedFolders.json."""
        neutral = tempfile.mkdtemp(prefix="text-to-cad-gemini-run-")
        try:
            return here.run([cli, *argv], cwd=Path(neutral), answer=answer,
                            environ={"GEMINI_CLI_TRUST_WORKSPACE": "true"})
        finally:
            shutil.rmtree(neutral, ignore_errors=True)

    def put_in() -> Ran:
        if source.local:
            return run(["extensions", "link", source.folder, "--consent"], answer="y\n")
        return run(["extensions", "install", URL, "--ref", BRANCH, "--consent"])

    if not (folder.exists() or folder.is_symlink()):
        ran = put_in()
        if not ran.ok and not ours_now():
            raise Failed(ran.last())
        return Outcome("installed")
    found = record()
    same = ours_now()  # ours from GitHub already: installed again, below
    if same and source.local:
        return Outcome("updated", f"linked to {source.folder}")
    linked = found.get("type") == "link" and our_folder(here, found.get("source"))
    if not (same or linked or our_repository(found.get("source"))):
        raise Failed(f"another extension named {PLUGIN} is installed (from {found.get('source') or 'elsewhere'}): "
                     "left alone")
    source.reachable(here)
    aside = Path(tempfile.mkdtemp(prefix="text-to-cad-gemini-"))
    try:
        shutil.copytree(str(folder), str(aside / PLUGIN), symlinks=True)
        enablement = extensions / "extension-enablement.json"
        kept = enablement.read_bytes() if enablement.is_file() else None
        removed = run(["extensions", "uninstall", PLUGIN])
        if not removed.ok:
            raise Failed(f"`extensions uninstall` said: {removed.last()}")
        ran = put_in()
        if not ran.ok and not ours_now():
            if folder.exists() or folder.is_symlink():
                discard(folder)
            shutil.copytree(str(aside / PLUGIN), str(folder), symlinks=True)
            if kept is not None:
                enablement.write_bytes(kept)
            raise Failed(f"{ran.last()}; the earlier copy was put back")
    finally:
        shutil.rmtree(aside, ignore_errors=True)
    if same:
        return Outcome("updated")
    old = ("linked to " + str(found.get("source")) if linked else
           f"from {found.get('source')} at {found.get('ref') or 'its default branch'}")
    return Outcome("updated", removed=[f"{PLUGIN} {old}"])


def grok_plugins(here: Here) -> List[Dict[str, str]]:
    """Grok Build's installed plugins, from its registry (``~/.grok/installed-plugins/registry.json``): name, where
    from, git ref. A registry of another shape gives none."""
    repos = table(table(read_json(here.home / ".grok" / "installed-plugins" / "registry.json")).get("repos"))
    found = []
    for entry in repos.values():
        entry = table(entry)
        kind, path = entry.get("kind"), entry.get("path")
        if not isinstance(kind, dict) or not isinstance(path, str):
            continue
        named = entry.get("plugins")
        names = list(named) if isinstance(named, dict) else [
            table(read_json(Path(path) / ".grok-plugin" / "plugin.json") or read_json(Path(path) / "plugin.json")).get("name")]
        for name in names:
            found.append({"name": str(name), "source": str(kind.get("url") or kind.get("path") or ""),
                          "ref": str(kind.get("git_ref") or ""), "path": path})
    return found


def grok(app: App, here: Here, context: Context) -> Outcome:
    """Grok Build: ``grok plugin install earthtojake/text-to-cad@latest --trust``, then enabled; updated by ``grok
    plugin update``. Grok Build loads Claude Code's plugins (its docs), so where Claude Code has ours its own copy of
    ours goes. Removed, once ours is in: a plugin named ``cad`` from our repository (0.5.0-0.7.6). A copy of ours from
    another source is replaced (same name), GitHub checked first and the old one put back where the new one fails.
    Verified: `grok plugin --help` and its subcommands (`install <source>` with `@ref`, `--trust`; `enable`; `update
    [name]`; `uninstall`); docs https://docs.x.ai/build/features/skills-plugins-marketplaces (it reads Claude Code's
    marketplaces and plugins)."""
    cli = here.which("grok")
    if not cli:
        return NOT_FOUND
    source = context.source
    removed: List[str] = []
    old_cad, mine, other = False, None, None
    for plugin in grok_plugins(here):
        ours = our_repository(plugin["source"]) or our_folder(here, plugin["source"])
        if plugin["name"] == "cad" and ours:
            old_cad = True
        elif plugin["name"] == PLUGIN:
            if not ours:
                raise Failed(f"another plugin named {PLUGIN} is installed (from {plugin['source']}): left alone")
            current = (same_path(plugin["source"], source.folder) if source.local
                       else our_repository(plugin["source"]) and plugin["ref"] == BRANCH)
            mine, other = (plugin, None) if current else (None, plugin)

    def drop_cad() -> None:
        if old_cad:
            here.must([cli, "plugin", "uninstall", "cad"])
            removed.append("cad")

    if context.claude_has_ours and not source.local:
        for plugin in (mine, other):
            if plugin is not None:
                here.must([cli, "plugin", "uninstall", PLUGIN])
                removed.append(PLUGIN)
        drop_cad()
        return Outcome("skipped", "it loads Claude Code's plugin", removed, has_ours=True)
    if mine is not None:
        here.must([cli, "plugin", "update", PLUGIN])
        drop_cad()
        return Outcome("updated", removed=removed)
    install = [cli, "plugin", "install", str(source.folder) if source.local else f"{REPOSITORY}@{BRANCH}", "--trust"]
    if other is not None:
        source.reachable(here)
        here.must([cli, "plugin", "uninstall", PLUGIN])
        try:
            here.must(install)
            here.must([cli, "plugin", "enable", PLUGIN])
        except Failed as error:
            back = [cli, "plugin", "install", other["source"] + (f"@{other['ref']}" if other["ref"] else ""), "--trust"]
            put = here.run(back).ok and here.run([cli, "plugin", "enable", PLUGIN]).ok
            raise Failed(f"{error}; the earlier copy was {'put back' if put else 'not put back: run this again'}") from error
        removed.append(f"{PLUGIN} from {other['source']}" + (f"@{other['ref']}" if other["ref"] else ""))
        drop_cad()
        return Outcome("updated", removed=removed)
    here.must(install)
    here.must([cli, "plugin", "enable", PLUGIN])
    drop_cad()
    return Outcome("installed", removed=removed)


def antigravity_plugins(here: Here, cli: str) -> Optional[List[Dict[str, Any]]]:
    """``agy plugin list --json``'s plugins (name, source, path), or None where it gives none to read."""
    ran = here.run([cli, "plugin", "list", "--json"], timeout=60)
    if not ran.ok:
        return None
    starts = [index for index in (ran.out.find("["), ran.out.find("{")) if index >= 0]
    try:
        data = json.loads(ran.out[min(starts):]) if starts else None
    except ValueError:
        return None
    entries = data if isinstance(data, list) else table(data).get("plugins")
    return [entry for entry in entries if isinstance(entry, dict)] if isinstance(entries, list) else None


def antigravity(app: App, here: Here, context: Context) -> Outcome:
    """Antigravity. Docs https://antigravity.google/docs/plugins: ``agy plugin install <repo URL or path>``,
    ``uninstall <name>``, ``list --json`` (each plugin's ``source`` and ``path``; installed into
    ``~/.gemini/config/plugins/<name>``); no update command, no ref (``main``); it reads
    ``.antigravity-plugin/plugin.json``. The docs do not say whether installing again replaces a plugin, so an update
    installs again first; only where that fails, and only a copy ``list`` shows is ours, is it uninstalled and
    installed again, its folder kept aside and put back where the new one does not install. Not run."""
    cli = here.which("agy")
    if not cli:
        return NOT_FOUND
    source = context.source
    install = [cli, "plugin", "install", str(source.folder) if source.local else URL]
    listed = antigravity_plugins(here, cli)
    mine = next((entry for entry in listed or () if entry.get("name") == PLUGIN), None)
    if mine is not None and not (our_repository(mine.get("source")) or our_folder(here, mine.get("source"))
                                 or our_folder(here, mine.get("path"))):
        raise Failed(f"another plugin named {PLUGIN} is installed (from {mine.get('source') or 'elsewhere'}): left alone")
    ran = here.run(install)
    if ran.ok:
        return Outcome("updated" if mine is not None else "installed")
    if mine is None:
        raise Failed(ran.last())
    source.reachable(here)
    folder = Path(str(mine.get("path") or here.home / ".gemini" / "config" / "plugins" / PLUGIN))
    aside = Path(tempfile.mkdtemp(prefix="text-to-cad-agy-"))
    try:
        if folder.is_dir():
            shutil.copytree(str(folder), str(aside / PLUGIN), symlinks=True)
        here.must([cli, "plugin", "uninstall", PLUGIN])
        again = here.run(install)
        if not again.ok:
            if (aside / PLUGIN).is_dir() and not folder.exists():
                shutil.copytree(str(aside / PLUGIN), str(folder), symlinks=True)
            raise Failed(f"{again.last()}; the earlier copy was put back")
    finally:
        shutil.rmtree(aside, ignore_errors=True)
    return Outcome("updated")


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


def unused_kept_name(path: Path) -> Path:
    """A name beside ``path`` no file has: ``<name>.<date-time>.bak``, numbered where that is taken."""
    stamp = time.strftime("%Y%m%d-%H%M%S")
    candidate, number = path.with_name(f"{path.name}.{stamp}.bak"), 1
    while candidate.exists() or candidate.is_symlink():
        number += 1
        candidate = path.with_name(f"{path.name}.{stamp}-{number}.bak")
    return candidate


# What the run says for Claude Desktop where no `claude` command is here: its Code tab runs Claude Code, whose plugin
# manager takes the plugin.
DESKTOP_NO_CLAUDE = ("install the `claude` command to have the install command add text-to-cad, or add it in Claude "
                     "Code's plugin manager: claude plugin marketplace add earthtojake/text-to-cad#latest, then claude "
                     "plugin install text-to-cad@earthtojake")


def claude_desktop(app: App, here: Here, context: Context) -> Outcome:
    """Claude Desktop: nothing is installed in it (its Code tab runs Claude Code, which gets the plugin above).
    Releases 0.7.6-0.11.10 wrote our server into its config as ``mcpServers.cad``: that one member is taken out where
    it runs text-to-cad, every other byte of the file kept, the file as it was kept beside it under a name no file
    has (``unused_kept_name``); a config that is a link is edited where it points. A ``cad`` that is another
    server's, or a file that is not plain JSON, is left. Where no ``claude`` command was found to install the plugin
    with, it says what to do (``DESKTOP_NO_CLAUDE``); it runs nothing of Claude Desktop's own. Verified: docs https://modelcontextprotocol.io/quickstart/user (servers are keys of
    ``mcpServers`` in claude_desktop_config.json)."""
    path = desktop_config(here)
    if not path.parent.is_dir():
        return QUIET
    ours = context.claude_has_ours  # its Code tab has the plugin where Claude Code does
    hint = "" if context.claude_found else DESKTOP_NO_CLAUDE
    try:
        text = path.read_text(encoding="utf-8") if path.exists() else ""
        data = json.loads(text) if text.strip() else {}
    except (OSError, ValueError):
        return Outcome("skipped", "; ".join(filter(None, [f"{path.name} is not plain JSON: left alone", hint])),
                       has_ours=ours)
    servers = data.get("mcpServers") if isinstance(data, dict) else None
    if not isinstance(servers, dict) or not runs_text_to_cad(servers.get("cad")):
        return Outcome("note", hint, has_ours=ours) if hint else QUIET
    edited = without_member(text, ["mcpServers", "cad"])
    expected = dict(data)
    expected["mcpServers"] = {key: value for key, value in servers.items() if key != "cad"}
    if json.loads(edited) != expected:
        raise Failed(f"{path.name} could not be edited safely: remove mcpServers.cad by hand")
    real = Path(os.path.realpath(path))
    kept = unused_kept_name(real)
    shutil.copy2(real, kept)
    handle, temporary = tempfile.mkstemp(dir=str(real.parent), prefix=f".{real.name}.")
    with os.fdopen(handle, "w", encoding="utf-8", newline="") as out:
        out.write(edited)
    os.chmod(temporary, real.stat().st_mode & 0o777)
    os.replace(temporary, real)
    words = f"the old cad server in its settings ({kept.name} keeps the file as it was)"
    return Outcome("removed", "; ".join(filter(None, [words, hint])), has_ours=ours)


def copy_skills(app: App, here: Here, context: Context) -> Outcome:
    """An agent with no plugin command: our skills copied into its own skills folder (only ours are replaced; a
    folder of that name that is someone else's stays)."""
    if not any(path.exists() for path in (app.marks(here) if app.marks else [])):
        return NOT_FOUND
    return put_skills(app.folder(here), here, context)


def put_skills(target: Path, here: Here, context: Context) -> Outcome:
    """Our skills copied into ``target``, a skills folder, each in place of ours there (``copy_tree``: staged, then
    swapped in, the old one deleted); a folder of that name that is not provably ours (``our_skill``) is kept. The skills are fetched before anything is touched."""
    source = context.source.skills(here)
    target.mkdir(parents=True, exist_ok=True)
    copied, kept, existed = [], [], False
    for skill in sorted(path for path in source.iterdir() if (path / "SKILL.md").is_file()):
        there = target / skill.name
        if (there.exists() or there.is_symlink()) and not our_skill(there):
            kept.append(skill.name)
            continue
        existed = copy_tree(skill, there) or existed
        copied.append(skill.name)
    words = f"{len(copied)} skills in {here.shown(target)}"
    if kept:
        words += f"; left {', '.join(kept)}: someone else's skill of that name"
    return Outcome("updated" if existed else "installed", words)


# The skill folders every earlier release may have left a loose copy of ours in: the shared ~/.agents/skills, each
# app's own, the per-agent folders 0.8.4-0.11.4's installer wrote through the Skills CLI, and the folders of the
# agents the Skills CLI served since. Each with the key of the app that reads it (None: a folder several apps read).
def loose_skill_folders(here: Here) -> List[Tuple[Path, Optional[str]]]:
    home, config = here.home, here.config_home()
    folders = [
        (home / ".agents" / "skills", None),
        (claude_dir(here) / "skills", "claude"),
        (Path(here.environ.get("CODEX_HOME") or home / ".codex") / "skills", "codex"),
        (home / ".cursor" / "skills", "cursor"),
        (home / ".grok" / "skills", "grok"),
        (Path(here.environ.get("GEMINI_CLI_HOME") or home) / ".gemini" / "skills", "gemini"),
        (home / ".copilot" / "skills", "copilot"),
        (config / "agents" / "skills", None),
        (home / ".gemini" / "antigravity" / "skills", "antigravity"),
        (home / ".gemini" / "antigravity-cli" / "skills", "antigravity"),
        (home / ".factory" / "skills", "droid"),
        (home / ".kilo" / "skills", "kilo"),
        (home / ".kilocode" / "skills", "kilo"),
        (config / "opencode" / "skills", "opencode"),
        (home / ".codeium" / "windsurf" / "skills", "windsurf"),
        (home / ".openclaw" / "skills", "openclaw"),
        (home / ".clawdbot" / "skills", "openclaw"),
        (home / ".moltbot" / "skills", "openclaw"),
        (config / "goose" / "skills", "goose"),
        (home / ".kiro" / "skills", "kiro"),
        (hermes_home(here) / "skills", "hermes"),
        (home / ".roo" / "skills", "roo"),
        (home / ".trae" / "skills", "trae"),
        (home / ".cline" / "skills", "cline"),
        (config / "amp" / "skills", "amp"),
    ]
    return list(dict(folders).items())


def copied_folders(here: Here, apps: Sequence[App]) -> List[Path]:
    """The skills folders the table copies our skills into: there our current skills are replaced in place
    (``put_skills``), so the loose cleanup takes only the retired ones."""
    found = [app.folder(here) for app in apps if app.folder is not None]
    return found + ([hermes_home(here) / "skills"] if any(app.key == "hermes" for app in apps) else [])


def skills_locks(here: Here) -> List[Path]:
    """The Skills CLI's records of what it installed globally: in ``$XDG_STATE_HOME/skills`` where that is set,
    else ``~/.agents`` (both read, whichever the CLI used)."""
    state = here.environ.get("XDG_STATE_HOME")
    return ([Path(state) / "skills" / ".skill-lock.json"] if state else []) + [here.home / ".agents" / ".skill-lock.json"]


def remove_loose_skills(here: Here, context: Context, outcomes: Dict[str, Outcome],
                        apps: Sequence[App] = ()) -> Outcome:
    """The loose copies of our skills (``our_skill``: one of our names AND our repository as our releases wrote
    it), after the apps, so an app loses its loose copies only once it has ours: a folder one app reads only where
    that app now has our plugin; a folder several apps read only where every app found has it; a folder the table
    copies into only its retired names (its current ones were replaced in place). A link to ours is unlinked, never
    followed; a copy deleted. The Skills CLI's record of a
    skill (``skills_locks``) goes once no copy is left in ``~/.agents/skills``, only an entry whose source is our
    repository or the plugin folder 0.10.0-0.11.10 wrote in cad's state folder. No ``npx skills remove``: it removes
    by name alone, from folders this does not read, and our names are common words."""
    found = [outcome for outcome in outcomes.values() if outcome is not NOT_FOUND and outcome is not QUIET]
    # A shared folder only after a run over every app (dev_install.py may name a few).
    every = bool(found) and all(outcome.ours for outcome in found) and {app.key for app in (apps or APPS)} >= {app.key for app in APPS}
    copied = [os.path.normcase(os.path.realpath(path)) for path in copied_folders(here, APPS)]
    names = {app.key: app.name for app in APPS}
    chosen: List[Path] = []
    waiting = []
    for folder, owner in loose_skill_folders(here):
        if not folder.is_dir():
            continue
        copies_into = os.path.normcase(os.path.realpath(folder)) in copied
        if copies_into:
            allowed = RETIRED_SKILLS
        elif (every if owner is None else table(outcomes).get(owner, NOT_FOUND).ours):
            allowed = (*SKILLS, *RETIRED_SKILLS)
        else:
            allowed = RETIRED_SKILLS
        for name in (RETIRED_SKILLS if copies_into else (*SKILLS, *RETIRED_SKILLS)):
            path = folder / name
            if not (path.exists() or path.is_symlink()) or not our_skill(path):
                continue
            if name in allowed:
                chosen.append(path)
            else:
                waiting.append((folder, owner))
    for path in chosen:
        discard(path)  # a link unlinked, never followed
    for lock in skills_locks(here):
        record = read_json(lock)
        entries = record.get("skills") if isinstance(record, dict) else None
        if not isinstance(entries, dict):
            continue
        shared = here.home / ".agents" / "skills"
        mine = [name for name, entry in entries.items() if name in (*SKILLS, *RETIRED_SKILLS) and isinstance(entry, dict)
                and not ((shared / name).exists() or (shared / name).is_symlink())
                and any(our_repository(entry.get(key)) or (isinstance(entry.get(key), str) and os.path.isabs(entry[key])
                                                            and any(within(entry[key], state) for state in here.state_dirs()))
                        for key in ("source", "sourceUrl"))]
        if mine:
            for name in mine:
                del entries[name]
            lock.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    notes = []
    for folder, owner in dict.fromkeys(waiting):
        who = names.get(owner, owner) if owner else "every app found here"
        notes.append(f"kept the ones in {here.shown(folder)} until {who} has the plugin")
    if not chosen:
        return Outcome("skipped", "; ".join(notes)) if notes else QUIET
    places = sorted({here.shown(path.parent) for path in chosen})
    words = f"{len(chosen)} old copies of our skills, in {', '.join(places)}"
    return Outcome("removed", "; ".join([words, *notes]))


def hermes_home(here: Here) -> Path:
    return Path(here.environ.get("HERMES_HOME") or here.home / ".hermes")


def hermes(app: App, here: Here, context: Context) -> Outcome:
    """Hermes Agent: our skills copied into its own skills folder, ``$HERMES_HOME/skills`` (default
    ``~/.hermes/skills``), where Hermes reads a user's skills, each a folder with its SKILL.md; copied again to
    update. Found by the ``hermes`` command or its home folder. Then, once the skills are in, the plugin of ours
    0.11.x's installer installed with ``hermes plugins install`` (``plugins/text-to-cad``, ours by Hermes's install
    record or our repository in its manifests) is removed with ``hermes plugins remove``, where the command is here.
    No plugin: Hermes takes a plugin only by the Agent Plugins standard's root ``plugin.json``, which Codex would read
    in place of its own manifest. Verified: docs https://hermes-agent.nousresearch.com/docs/user-guide/features/skills
    (``~/.hermes/skills`` is the skills folder); its source (``tools/skills_tool.py``: ``HERMES_HOME/skills``, every
    SKILL.md beneath it); ``hermes skills list`` listing the copied skills with HERMES_HOME in a scratch folder."""
    cli = here.which("hermes")
    home = hermes_home(here)
    if not cli and not home.is_dir():
        return NOT_FOUND
    outcome = put_skills(home / "skills", here, context)
    plugin = home / "plugins" / PLUGIN
    if plugin.is_dir():
        entry = table(table(read_json(home / "plugins" / ".install-metadata.json")).get(PLUGIN))
        if our_repository(entry.get("source")) or our_folder(here, plugin):
            removal = here.run([cli, "plugins", "remove", PLUGIN]) if cli else None
            if removal is not None and removal.ok:
                outcome.removed = [f"the {PLUGIN} plugin"]
            elif removal is not None:
                outcome.words += f"; the old {PLUGIN} plugin stays (hermes said: {removal.last()})"
            else:
                outcome.words += (f"; the old {PLUGIN} plugin in {here.shown(plugin)} stays until the hermes command "
                                  f"removes it: hermes plugins remove {PLUGIN}")
    return outcome


def _pi_installed(here: Here) -> bool:
    try:
        return f"github.com/{REPOSITORY}" in (here.home / ".pi" / "agent" / "settings.json").read_text(
            encoding="utf-8", errors="replace")
    except OSError:
        return False


def _qwen_installed(here: Here) -> bool:
    return (here.home / ".qwen" / "extensions" / PLUGIN).is_dir()


def _folder_agent(key: str, name: str, folder: Callable[[Here], Path], *marks: Callable[[Here], Path]) -> App:
    return App(key, name, folder=folder, marks=lambda here: [mark(here) for mark in marks])


# THE TABLE. Order matters only where it says: Claude Code first (Cursor and Grok Build load its plugin; Claude
# Desktop says what to do where no `claude` command was found).
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
    # Hermes Agent (``hermes``, above): the skills in its own folder, and the plugin of ours 0.11.x installed removed.
    App("hermes", "Hermes Agent", command="hermes", handler=hermes),
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
    # Antigravity (``antigravity``, above): installed again to update; uninstalled only where that fails. Not run.
    App("antigravity", "Antigravity", command="agy", handler=antigravity),
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
    # Windsurf and Goose, the Skills CLI's agent table and our earlier installers) say it reads them. Kilo: docs
    # https://kilo.ai/docs/features/skills (global skills in ~/.kilo/skills; ~/.kilocode is the older extension's
    # folder, which finds it too). Not run.
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


def cad_setup(here: Here, release: str) -> int:
    """That release's ``cad setup`` through uvx, its output shown as it runs. Its exit status (127: no uvx)."""
    uvx = here.which("uvx")
    if not uvx:
        print("cad setup: failed: uvx was not found (install uv: https://docs.astral.sh/uv/)", flush=True)
        return 127
    named = here.environ.get("CAD_INSTALL_FROM")
    requirement = ["--from", named] if named else ["--refresh-package", "cad-server", "--refresh-package", "cad",
                                                    "--from", f"cad-server=={release}"]
    try:
        code = subprocess.call([uvx, *UVX_ARGS, *requirement, "cad", "setup"], env=here.environ,
                               stdin=subprocess.DEVNULL)
    except OSError as error:
        print(f"cad setup: failed: {error}", flush=True)
        return 127
    if code:
        print(f"cad setup: failed (exit status {code}); what it said is above", flush=True)
    return code


@dataclass
class Report:
    """What the app phase did: its lines, in the order printed, and each app's outcome by key."""

    lines: List[str]
    outcomes: Dict[str, Outcome]

    def __contains__(self, line: str) -> bool:
        return line in self.lines

    @property
    def found(self) -> List[Outcome]:
        return [outcome for outcome in self.outcomes.values() if outcome is not NOT_FOUND and outcome is not QUIET]

    @property
    def changed(self) -> bool:
        return any(outcome.status in ("installed", "updated") for outcome in self.found)

    @property
    def all_failed(self) -> bool:
        return bool(self.found) and all(outcome.status == "failed" for outcome in self.found)


def install_apps(here: Here, source: Source, apps: Sequence[App] = APPS,
                 say: Callable[[str], None] = lambda line: print(line, flush=True)) -> Report:
    """Steps 3 and 4 for ``apps``: ours in, then old copies out, each app's line said as it finishes; one line for
    the loose skills, one counting the apps not found."""
    context = Context(source)
    lines: List[str] = []
    outcomes: Dict[str, Outcome] = {}
    missing = []

    def tell(line: str) -> None:
        lines.append(line)
        try:
            say(line)
        except (OSError, ValueError):  # a line the output cannot take is lost, never the apps after it
            pass

    for app in apps:
        try:
            outcome = app.run(here, context)
        except Failed as error:
            outcome = Outcome("failed", str(error))
        except Exception as error:  # noqa: BLE001 - one app's surprise is that app's failure, never the run's
            outcome = Outcome("failed", f"{type(error).__name__}: {error}")
        outcomes[app.key] = outcome
        if outcome is NOT_FOUND:
            missing.append(app.name)
        elif outcome is not QUIET:
            tell(outcome.line(app.name))
    try:
        loose = remove_loose_skills(here, context, outcomes, apps)
    except Exception as error:  # noqa: BLE001
        loose = Outcome("failed", f"{type(error).__name__}: {error}")
    if loose is not QUIET:
        tell(loose.line("Loose skills"))
    if missing:
        tell(f"{len(missing)} other supported apps were not found here.")
    return Report(lines, outcomes)


def main(argv: Optional[Sequence[str]] = None) -> int:
    # A character the output's encoding has not (an app's own mark, on Windows' code page) is printed as `?`, never
    # raised: the encoding itself stays as it is.
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(errors="replace")
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv:
        print("This installer takes no options: run it as it is to install or update text-to-cad in every agent app "
              "on this computer. To remove text-to-cad, run `cad uninstall`, and each app's own remove command.",
              file=sys.stderr)
        return 2
    here = Here()
    release = latest(here)
    print(f"Installing text-to-cad {release}. The first run downloads it, which takes a minute.", flush=True)
    code = cad_setup(here, release)
    if code == SETUP_SANDBOXED:
        print("cad setup could not install from this shell (an agent's sandbox, no network, or a folder it may not "
              "write), and the agent apps' commands would fail here too: nothing was changed in them. Run this again "
              "in a terminal of your own, outside the sandbox.", flush=True)
        return 1
    print("", flush=True)
    print("Setting up the plugin in each agent app found here:", flush=True)
    source = Source()
    try:
        report = install_apps(here, source)
    finally:
        source.close()
    print("", flush=True)
    if code:
        print(f"text-to-cad itself was not installed (cad setup exit status {code}; what it said is above), and the "
              "plugin's commands need it: run this again.", flush=True)
    elif report.all_failed:
        print("No app got the plugin: see each app's line above, then run this again.", flush=True)
    if report.changed:
        print("Start a new session in each app to use it.", flush=True)
    return 1 if code or report.all_failed else 0


if __name__ == "__main__":
    sys.exit(main())
