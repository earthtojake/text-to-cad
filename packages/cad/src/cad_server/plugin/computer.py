"""This computer, as the install sees it (``Here``): its home folder, its environment, its platform, where a command
is found and how one runs; and the files it reads and replaces -- a person's config of any shape read as a table
(``read_json``, ``read_toml``, ``table``), and nothing removed or replaced by half (``discard``, ``copy_tree``,
``swap``).

Every rename goes through ``rename``, which ``cad plugin`` sets to cad's own. A command an app's row runs is given
nothing to read but its answer, its output captured, and is stopped with every
process it started after ``COMMAND_SECONDS`` (``Here.run``). A run that has a deadline of its own (``Here.until``:
the one a server began) gives each command what is left of it and starts none past it. How a step failed is a word
chosen where it failed (``Failed.reason``, ``REASONS``), never its message.

The standard library alone.
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
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

try:  # Python 3.11 and later; before it, ``read_toml`` reads the little of TOML it needs itself
    import tomllib
except ImportError:  # pragma: no cover - a checkout's development install on an older Python
    tomllib = None  # type: ignore[assignment]

# How long one app command may take before it is stopped (with every process it started). The slowest is a
# clone of the `latest` branch (1.4 MB, about a second measured); three minutes is that a hundredfold on a slow
# line, and a CLI that hangs (a prompt it should not show, a lock) costs the run three minutes, not fifteen.
COMMAND_SECONDS = 180
# Where Homebrew puts the commands it installs (Apple silicon's, Intel macOS's, Linux's): not on the PATH of a
# shell an app opened, so earlier releases looked there too.
HOMEBREW = ("/opt/homebrew/bin", "/usr/local/bin", "/home/linuxbrew/.linuxbrew/bin")
# How a step failed, in a word chosen where it failed: a command did not answer in time and was stopped; a command
# ended with a non-zero exit status (or could not start); GitHub could not be reached (by us, or by a command that
# said so: ``NETWORK_SAID``); an error no row foresaw; or anything else (a copy that is not ours in the way, a file
# that cannot be edited safely).
TIMEOUT, COMMAND, NETWORK, EXCEPTION, OTHER = "timeout", "command", "network", "exception", "other"
REASONS = (TIMEOUT, COMMAND, NETWORK, EXCEPTION, OTHER)
# The exit status of a command stopped because it did not answer in time, as ``timeout(1)`` says one.
STOPPED = 124
# What git, curl and Node say where the network failed them (``Ran.reason``): a command that said one of these failed
# for want of the network (``NETWORK``), not by itself (``COMMAND``).
NETWORK_SAID = re.compile(r"could not resolve host|failed to connect|unable to access|connection refused"
                          r"|connection timed out|network is unreachable|\bssl|econnrefused|enotfound|etimedout"
                          r"|getaddrinfo", re.IGNORECASE)
# The words of a line that says what went wrong (``Ran.last``): an app's command often ends with advice after it.
ERROR_SAID = re.compile(r"\b(?:error|failed|fatal|unable|could not|denied|not found)", re.IGNORECASE)
# How much of that line a reason keeps.
LAST_CHARACTERS = 200
# How a file or a folder is renamed into place (``discard``, ``swap``, an app's config written): the standard
# library's, unless what runs these modules gives a more patient one -- ``cad plugin`` gives cad's own (``run``), which
# waits out a file another program holds for a moment on Windows.
rename: Callable[[Any, Any], None] = os.replace


# --- the computer ---------------------------------------------------------------------------------


@dataclass
class Ran:
    code: int
    out: str = ""
    stopped: bool = False  # it did not answer in time, and was stopped

    @property
    def ok(self) -> bool:
        return self.code == 0

    @property
    def reason(self) -> str:
        """Why it failed, in a word (``REASONS``): ``timeout`` where it was stopped for not answering in time,
        ``network`` where what it printed says the network failed it (``NETWORK_SAID``), else ``command``."""
        if self.stopped:
            return TIMEOUT
        return NETWORK if NETWORK_SAID.search(self.out) else COMMAND

    def last(self) -> str:
        """The line it printed that says most, as a reason: the first that reads as an error (``ERROR_SAID``), else
        its last, ``LAST_CHARACTERS`` of it at most. A command's error often runs over several lines and ends in
        advice ("... and the repository exists."), which alone says nothing."""
        lines = [line.strip() for line in self.out.splitlines() if line.strip()]
        line = next((line for line in lines if ERROR_SAID.search(line)), lines[-1] if lines else "")
        return line[:LAST_CHARACTERS] if line else f"exit status {self.code}"


class Failed(Exception):
    """One app's step failed: the message says why, in a few words, and ``reason`` in one (``REASONS``)."""

    def __init__(self, message: str, reason: str = OTHER) -> None:
        super().__init__(message)
        self.reason = reason


class Here:
    """This computer: its home folder, its environment, its platform, and how a command runs."""

    def __init__(self, environ: Optional[Dict[str, str]] = None, platform: str = sys.platform) -> None:
        self.environ = dict(os.environ if environ is None else environ)
        self.platform = platform
        self.home = Path(self.environ.get("USERPROFILE") if self.windows and self.environ.get("USERPROFILE")
                         else self.environ.get("HOME") or Path.home())
        # Told each command ``run`` starts, and None before one that writes to the terminal itself (``Live.watch``).
        self.watch: Callable[[Optional[Sequence[Any]]], None] = lambda argv: None
        # When this run must have ended, by the monotonic clock (the run a server began), or None: no deadline.
        self.until: Optional[float] = None

    @property
    def expired(self) -> bool:
        """Whether this run's deadline (``until``) has passed."""
        return self.until is not None and time.monotonic() >= self.until

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
        it started, after ``timeout`` seconds, or at this run's deadline where that comes first (``until``); past the
        deadline, it is not started."""
        env = {**self.environ, "GIT_TERMINAL_PROMPT": "0", **(environ or {})}
        if self.until is not None:
            timeout = min(timeout, self.until - time.monotonic())
            if timeout <= 0:
                return Ran(STOPPED, "not started: this run's time is up", stopped=True)
        self.watch(argv)
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
            return Ran(STOPPED, f"no answer in {int(timeout)} s: stopped", stopped=True)
        return Ran(process.returncode, (out or b"").decode("utf-8", "replace"))

    def must(self, argv: Sequence[Any], **options: Any) -> Ran:
        ran = self.run(argv, **options)
        if not ran.ok:
            raise Failed(f"`{' '.join(str(word) for word in argv[1:3])}` said: {ran.last()}", ran.reason)
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
        pass
    try:
        if process.poll() is None:  # taskkill refused ("Access denied" with no interactive logon) or failed
            process.kill()
    except OSError:
        pass
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
    if tomllib is not None:
        try:
            found = tomllib.loads(text)
        except ValueError:
            return {}
        return found if isinstance(found, dict) else {}
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
    rename(str(path), str(trash / path.name))
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
        rename(str(staged), str(target))
        return False
    held = Path(tempfile.mkdtemp(prefix=".text-to-cad-old-", dir=str(target.parent)))
    try:
        rename(str(target), str(held / target.name))
        try:
            rename(str(staged), str(target))
        except OSError:
            rename(str(held / target.name), str(target))
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
