"""text-to-cad's installer: the program `install.sh` and `install.ps1` download from beside themselves and
run with uv's Python (the standard library alone, nothing imported from this repository).

    curl -fsSL https://texttocad.dev/install.sh | sh          # macOS and Linux
    irm https://www.texttocad.dev/install.ps1 | iex           # Windows PowerShell

It takes no options, carries no release of cad (nothing in it changes with one) and knows no agent app. It gets this
computer a ``cad`` that works and is current, then hands over to it: what goes into the agent apps is cad's own ``cad
plugin install``, which carries the one table of them. It does these things alone:

1. (``install.sh``, ``install.ps1``) makes sure uv is here;
2. installs the ``cad`` command only where uv has no ``cad`` tool (``install_cad``): ``uv tool install
   --managed-python --python 3.14 cad``, PyPI's newest. One that does not start (a tool Windows left half-replaced)
   is installed again, ``uv tool install --reinstall ...``, PyPI's newest. A ``cad`` pipx installed, where uv has none,
   is a global cad too (``pipx_cad``): installed again by pipx where it does not start (``repair_pipx``); uv installs
   no second cad. First the ``cad`` command 0.10.0-0.11.11 wrote in uv's bin folder goes, where it is
   provably ours (``old_launcher``); another program's ``cad`` there stops this step, in one line. On Windows a
   ``cad.exe`` that runs is renamed out of uv's way (``set_aside``), never a reason to stop; what a run set aside and
   could not delete, a later run deletes (``tidy``);
3. brings a ``cad`` that was here already, and starts, up to date, only where a person ran this (``update``): that
   tool's own ``cad update`` (never PATH's), ``UPDATE_SECONDS`` at most (cad's server begins an update only once
   nothing is in flight, and the command waits for it). It stays inside cad's major version, as ``cad update`` does:
   a higher major is the person's to ask for. What it prints is captured, never shown: one line says the update
   begins, and one line what came of it, over the first in a terminal (after it on a pipe or in a file). Its exit
   status says little (0 where it updated and where nothing is newer, non-zero where the update may still be
   queued), so the tool's release is read again from uv or pipx; where cad was not updated, that line gives cad's
   own most telling line as the reason, and the run goes on: cad updates itself. Never where cad ran this
   (``BY_CAD``), and never for a cad this run installed;
4. hands over (``hand_over``): ``<cad> plugin install`` by that tool's own command, on this process's own output, so a
   person's terminal shows what cad draws there. cad is told who began the run (``CAD_PLUGIN_BY=script``) and where
   to say what it did (``CAD_PLUGIN_REPORT``, a scratch file). That cad is asked first, its answer captured, whether
   it has the command (``<cad> plugin install --help``, which runs nothing: exit status 0 where it has it). Where it
   has none (0.11.12 and 0.11.13, which run this command themselves: argparse's usage error, exit status 2, which the
   person never sees), and where cad could not be installed, the newest release's runs instead, outside any
   installed tool, once: ``uv tool run --no-config --managed-python --python 3.14 cad@latest plugin install``, after
   one line of this command's own. Never ``cad plugin update`` (on those releases it runs this command) and never
   ``cad setup``;
5. turns on ``cad plugin update auto`` (``switch_on``), last, wherever a cad is installed: that tool's own ``cad plugin
   update auto on`` (never PATH's), with ``CAD_INSTALL_FAILED=1`` in that one call's environment where the plugin's
   step did not end with every app it found gone well: it ended non-zero, or its report names an app ``failed``
   (then cad turns the switch on and takes nothing as up to date, so its server tries again). The person ran this
   command, and the plugin following cad's updates is what they asked for by it; ``cad plugin install`` itself never
   changes the switch. Whatever that call answers, the run ends as it would have: a failure is one line.

``cad plugin install`` installs or updates the plugin in each agent app it finds and removes our older copies: nothing
of that is here. This command never starts cad's server. Nothing it starts carries the name a cad server gives its own
run (``RUN_NAMES``): see below.

It exits 0 only where the run ended well: 1 where cad was needed and could not be installed, or the plugin's step
ended non-zero or could not run at all; 75 where that step ran nothing because another run of it was going (cad's own
status for it, which only a run a cad server began gets); 2 for an option.

``CAD_INSTALL_REPORT`` names a file where the run says what it did (``write_report``), for the hand-over of cad
0.11.12 and 0.11.13 (their ``cad_server._internal.install_script``, which sets it and judges the file the moment it
is there): ``{"schema": "text-to-cad install report/1", "release": <the cad this computer has after the run; null
where it has none>, "setup": <the cad step's exit status: 0 where cad was installed, installed again, or was here
already and starts>, "apps": {<app>: "installed" | "updated" | "removed" | "skipped" | "failed" | "not found"}}``,
``apps`` as ``cad plugin install`` said them, written whole (a file beside it, renamed into place) as the very last
thing the run does. Writing it never fails the run, and nothing is printed about it. Those releases read two things
of it, and never the run's exit status: that ``setup`` is the integer 0, and that no value of ``apps`` is
``failed``. So where the plugin's step ended non-zero and named no app as failed (it raised, could not be started,
was stopped, ran nothing because another run was going, or ended badly after the apps), ``apps`` gains ``"plugin":
"failed"`` (``UNSAID``), which they read as a failure and run this command again for, later; without it they would
read the run as done. Where cad itself could not be installed, ``setup`` says so, and ``apps`` is what the newest
cad's step said, ``{}`` where it said nothing.

**One report of a failure** (``Reports``). A run that ends with a cad that works is counted by that cad. One that
fails where no cad can count it sends one anonymous report of where: ``{"schema": 1, "run": <a random id made for
this run alone, kept nowhere>, "at": <seconds>, "stage", "outcome", "code": <an exit status>, "platform", "arch",
"by": "person" | "cad", "uv": <its version, or "none">}`` to ``API``'s ``/install``. The stages here: ``cad`` (it
could not be installed), ``plugin`` (no cad could run the plugin's step) and ``script`` (this program raised:
``outcome`` is ``crashed``, with the exception type's name and up to ten of its frames in this file, each a function
and a line; never a file's name, a path or a message), after which Python prints its traceback and exits as it
would have. ``install.sh`` and ``install.ps1`` send the stages before this program runs (``uv``, ``fetch``,
``python``), and know it ran by the file it leaves as it starts (``MARK_ENV``). At most one a run, ``REPORT_SECONDS``
at most, never a line printed, never a change to the exit status. Nothing is sent where ``DO_NOT_TRACK`` is on or
``CAD_TELEMETRY`` is off (cad's own spellings), in CI, where cad's kept settings say no (``telemetry`` in the state
folder's ``settings.json``), or from a checkout (``development``); everywhere else a person's run says so first, in
one line (``NOTICE``), said by whichever of the shell and this program ran first. A run cad started (``BY_CAD``) is
read by nobody, its output a log's or thrown away: it says no such line, and sends its report only where cad's kept
settings show the person was told already what cad sends, or said yes to it, as cad itself decides (``kept``:
nothing is sent before a person was told); ``install.sh`` and ``install.ps1``, which read no settings so closely,
send nothing for such a run.

**Older releases, and why nothing loops.** Who runs this command: a person, the one it is made for; and, unattended,
cad itself. 0.11.12 and 0.11.13 run it for their own ``cad plugin update``, typed, or begun by their server once cad
got newer (named ``CAD_INSTALL_ATTEMPT``; stopped, with what it started, after 900 seconds: 124), for plain ``cad
setup``, and once from their server's tending where our setup ran before (``once``). Any release that carries the
bridge runs it in install mode for a computer coming from 0.10.0-0.11.11 (output thrown away, ``CAD_INSTALL_REPORT``
set, two hours at most), as by ``cad setup`` and ``once``; 0.10.0-0.11.11 never run it themselves. Every cad sets
``CAD_INSTALL_BY_CAD=1`` and ``UV_NO_MODIFY_PATH=1`` for it, with no input. Releases after 0.11.13 run it for the
bridge alone: their ``cad plugin install`` is their own code.

Never ``cad plugin update`` (but ``cad plugin update auto on``, the switch): on 0.11.12 and 0.11.13 that command
downloads and runs this one, which would run it again, without end. A person's run brings the cad it finds up to date
first (``update``), so the plugin comes from a current cad; a run cad started never does: cad is updating itself, or
is the one being carried, and a ``cad update`` there could replace the very cad that is waiting on this run.

The newest release's ``cad plugin install``, by ``uv tool run ... cad@latest`` outside the installed tool, runs only
where the installed cad has no ``cad plugin install`` (0.11.12, 0.11.13), or where no cad could be installed. Which cad
has it is asked first, quietly: ``<cad> plugin install --help``, its output captured, exit status 0 where it has it. On
those two releases, as on every earlier one, argparse refuses ``install`` before it reads ``--help`` (its usage error,
exit status 2): then the newest release's runs straight away, after one line of this command's own and nothing of that
cad's. Any other answer is no answer, and the installed cad's command runs for real, as it did before anything was
asked; where it ends 2 with no report written, that is taken as the same answer, once more. Nothing runs twice: the
installed cad's step and the newest's, at most one each, in that order. It is there for those two releases alone: once
no computer is left on them, it can go, and an installed cad that cannot run the step is a failure like any other. Its
release is not kept as the one the plugin is up to date for (it is no global install); the installed cad keeps its own,
by the switch's call.

What each caller reads back: a person and their shell, the exit status. Of 0.11.12 and 0.11.13, the typed ``cad plugin
update`` gives the exit status as its own and, on 0, keeps its release as the one the plugin is up to date for; the
one their server began keeps it in its record (``ok``, or ``failed`` with the status); plain ``cad setup`` gives it as
its own; ``once`` reads nothing. Install mode reads the report alone (``CAD_INSTALL_REPORT``, above), never the exit
status. That of 0.11.12 to 0.11.14 reads two fields of it, ``setup`` the integer 0 and no value of ``apps`` ``failed``
-- so ``"plugin": "failed"`` (``UNSAID``) is written wherever the plugin's step ended non-zero and named no app as
failed, or that reader would take the run as done and never run it again. Later releases' take a run whose ``setup`` is
0 as done, and any ``failed`` in ``apps``, ``UNSAID`` included, as the plugin's to run again by cad's own retry.

No loops. The edges: this command starts uv and pipx (installs only), the installed ``cad --version``, ``cad update`` (a
person's run alone), ``cad plugin install --help`` (the installed cad's, which runs nothing on any release), ``cad
plugin install`` (the installed cad's, then the newest's) and ``cad plugin update auto on``; never ``cad plugin update``
alone, ``cad setup`` or a server, and it takes ``CAD_INSTALL_ATTEMPT`` and ``CAD_PLUGIN_SERVER_RUN`` out of what each of
them inherits (``RUN_NAMES``), so no ``cad plugin install`` takes a run an older cad's server began for its own. ``cad
plugin install`` (this release's, under either name) starts each agent app's own commands and git: no install command,
no ``cad update``, no ``cad plugin``. ``cad plugin update auto on`` keeps a setting, by the running server or by itself,
and starts nothing, on every release (0.11.13's included). ``cad update`` asks the server, whose helper upgrades cad
with uv or pipx and starts the server again; on no release does it run this command or ``cad plugin``. The one way back
here is a server: an older one runs its ``cad plugin update``, so this command, at most three times for a release, an
hour or more apart, and only once cad is newer than the release the plugin is up to date for; a newer one runs its ``cad
plugin install``, which never comes here. Such a run is cad's, so it runs no ``cad update``, and whatever it reaches
ends in ``cad plugin install`` and the switch, neither of which starts anything that comes back. The bridge's runs
(install mode, ``cad setup``, ``once``) come here too, bounded by their own record, and this command never runs ``cad
setup``: nothing goes back to them.

Test hooks, never documented to people: ``CAD_INSTALL_PATH_ONLY`` (look for uv, pipx and cad on PATH and in
``~/.local/bin`` alone: never in Homebrew's or npm's folders, where a test would find a real one); ``CAD_API_URL``,
cad's own (the address the report goes to, a stand-in's). uv runs with this process's environment, so a rehearsal
offers its own wheels through uv's ``UV_FIND_LINKS``: uv installs the newest release it is offered, its own or
PyPI's, by ``uv tool install cad`` and by ``uv tool run cad@latest`` alike.
"""

from __future__ import annotations

import json
import os
import platform as _platform
import re
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import urllib.request
import uuid
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

# `uv tool install <these> cad`: uv's own Python 3.14, whatever Python the computer has. The line people are given
# carries no flags; this script is hosted, and may change them any day.
UV_TOOL_ARGS = ("--managed-python", "--python", "3.14")
# The mark in the first lines of the `cad` command 0.10.0-0.11.11 wrote in the bin folder, with its revision: `# ` in
# the sh script and in the `__main__.py` of the zip behind cad.exe's launcher (Windows, 0.11), `rem ` in cad.cmd (0.10).
OLD_LAUNCHER = re.compile(r"(#|rem) cad proxy: \d+")
# A cad.exe of uv's tool set aside in uv's bin folder before uv installs cad (``set_aside``): the name cad's own update
# gives one (``ASIDE`` in cad's ``auto_update_helper.py``), so either one's tidying removes the other's.
ASIDE = ".cad.exe.{stamp}.{n}.old"
# What a run sets aside or throws away in uv's bin folder and could not delete then (Windows keeps a file while it
# runs): ``make_room``'s names, ``discard``'s trash folders, and ``ASIDE``. A later run deletes them (``tidy``).
LEFTOVERS = (*(f".{name}.text-to-cad-old" for name in ("cad", "cad.exe", "cad.cmd", "cad-launcher")),
             ".text-to-cad-trash-*", ASIDE.format(stamp="*", n="*"))
# How long a command asked a question may take to answer (``Here.run``) before it is stopped, with every process it
# started.
ASK_SECONDS = 60
# Where Homebrew puts the commands it installs (Apple silicon's, Intel macOS's, Linux's): not on the PATH of a
# shell an app opened, so earlier releases looked there too.
HOMEBREW = ("/opt/homebrew/bin", "/usr/local/bin", "/home/linuxbrew/.linuxbrew/bin")
# What a cad that runs this command sets, one or more of them: every install command cad starts
# (``CAD_INSTALL_BY_CAD``), the run a cad server began (``CAD_INSTALL_ATTEMPT``), and where it reads what the run did
# (``CAD_INSTALL_REPORT``). With one set, cad ran this: it brings no cad up to date (``update``), and a report says so.
BY_CAD = ("CAD_INSTALL_BY_CAD", "CAD_INSTALL_ATTEMPT", "CAD_INSTALL_REPORT")
# The names a cad server gives the run it began (0.11.12 and 0.11.13: ``CAD_INSTALL_ATTEMPT``; later releases:
# ``CAD_PLUGIN_SERVER_RUN``), which a command it started inherits: read once, as this program starts (``Here.by_cad``),
# and taken out of the environment of everything it starts. Each names that server's run alone; a ``cad plugin
# install`` reached from here that took it for its own would close that run's record, under its deadline and lock.
RUN_NAMES = ("CAD_INSTALL_ATTEMPT", "CAD_PLUGIN_SERVER_RUN")
# Set to ``1`` for ``cad plugin update auto on`` where the plugin's step did not end with every app it found gone well
# (``switch_on``): cad then turns the switch on and takes nothing as up to date. Never the caller's.
FAILED_ENV = "CAD_INSTALL_FAILED"
# How long ``cad update`` may take: cad's own command waits ten minutes for a busy server, then says the update is
# still underway.
UPDATE_SECONDS = 11 * 60
# What ``cad plugin install`` reads: who began its run, and the file where it says what it did.
PLUGIN_BY_ENV = "CAD_PLUGIN_BY"
PLUGIN_REPORT_ENV = "CAD_PLUGIN_REPORT"
# ``cad plugin install``'s exit status where that cad has no such command (a usage error), and where it ran nothing
# because another run was going (cad's ``plugin_catch_up.BUSY``).
NO_COMMAND = 2
BUSY = 75
# Where a failure's one report goes (``Reports``): cad's own service, and the variable that names another for it.
API = "https://api.texttocad.dev/v1"
API_ENV = "CAD_API_URL"
REPORT_SECONDS = 2.0
# The file this program leaves as it starts, where the shell that ran it names one: by it `install.sh` and
# `install.ps1` tell a run uv could not start (theirs to report) from one that failed here.
MARK_ENV = "CAD_INSTALL_MARK"
# Said once, near the start, by a person's run that could send a report: `install.sh` and `install.ps1` say the
# same line.
NOTICE = ("If the install fails before cad can run, one anonymous report of where it failed is sent to texttocad.dev "
          "(DO_NOT_TRACK=1 turns it off).")


# --- the computer ---------------------------------------------------------------------------------


# The words of a line that says what went wrong (``Ran.last``): cad's own choice of line (its ``plugin.computer``'s
# ``ERROR_SAID``, which a test holds this to).
ERROR_SAID = re.compile(r"\b(?:error|failed|fatal|unable|could not|denied|not found)", re.IGNORECASE)


@dataclass
class Ran:
    code: int
    out: str = ""

    @property
    def ok(self) -> bool:
        return self.code == 0

    def last(self) -> str:
        """The line it printed that says most, as a reason: the first that reads as an error (``ERROR_SAID``), else
        its last, 200 characters of it at most, as cad chooses one."""
        lines = [line.strip() for line in self.out.splitlines() if line.strip()]
        line = next((line for line in lines if ERROR_SAID.search(line)), lines[-1] if lines else "")
        return line[:200] if line else f"exit status {self.code}"


class Here:
    """This computer: its home folder, its environment, its platform, and how a command runs. ``by_cad``: cad ran
    this command (``BY_CAD``), read as it starts; ``environ`` is then what everything this program starts inherits,
    without ``RUN_NAMES``."""

    def __init__(self, environ: Optional[Dict[str, str]] = None, platform: str = sys.platform) -> None:
        self.environ = dict(os.environ if environ is None else environ)
        self.by_cad = any(self.environ.get(name) for name in BY_CAD)
        for name in RUN_NAMES:
            self.environ.pop(name, None)
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
        """PATH, then ~/.local/bin (where uv and pipx put commands before a new shell has it on PATH), then
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

    def shown(self, path: Any) -> str:
        """``path`` as a person reads it: the home folder spelled ``~``."""
        text, home = str(path), str(self.home).rstrip("/\\")
        return "~" + text[len(home):] if home and (text == home or text.startswith(home + os.sep)) else text

    def run(self, argv: Sequence[Any], timeout: float = ASK_SECONDS, environ: Optional[Dict[str, str]] = None,
            apart: bool = True) -> Ran:
        """``argv`` run with nothing to read (in ``environ``, else this run's), what it printed captured; stopped,
        with every process it started, after ``timeout`` seconds. ``apart`` false: it stays in this process's group,
        as ``show``'s command does (a terminal's Ctrl-C reaches it), and only it is stopped."""
        group = ({} if not apart else {"creationflags": getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)}
                 if os.name == "nt" else {"start_new_session": True})
        try:
            process = subprocess.Popen([str(part) for part in argv], env=self.environ if environ is None else environ,
                                       stdin=subprocess.DEVNULL,
                                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, **group)
        except OSError as error:
            return Ran(127, f"{type(error).__name__}: {error}")
        try:
            out, _ = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            _stop(process, group=apart)
            return Ran(124, f"no answer in {int(timeout)} s: stopped")
        return Ran(process.returncode, (out or b"").decode("utf-8", "replace"))

    def show(self, argv: Sequence[Any], environ: Optional[Dict[str, str]] = None,
             timeout: Optional[float] = None) -> int:
        """``argv`` run on this process's own output, its lines shown as they come, with nothing to read: its exit
        status; 127 where it could not start (said in one line), 124 where it was stopped after ``timeout`` seconds.
        It stays in this process's group: whoever stops this run stops it too, and a terminal's Ctrl-C reaches it."""
        try:
            return subprocess.call([str(part) for part in argv], env=self.environ if environ is None else environ,
                                   stdin=subprocess.DEVNULL, timeout=timeout)
        except subprocess.TimeoutExpired:
            return 124
        except OSError as error:
            print(f"{Path(str(argv[0])).name}: could not be run: {error}", flush=True)
            return 127

    # Where cad keeps its state (cad's own `state_dir`, and Windows 0.10.0's): its ``settings.json`` holds the
    # person's answer about telemetry (``reporting``).
    def state_dirs(self) -> List[Path]:
        found = [Path(self.environ["CAD_STATE_DIR"])] if self.environ.get("CAD_STATE_DIR") else []
        if self.platform == "darwin":
            found.append(self.home / "Library" / "Application Support" / "cad")
        found.append(Path(self.environ.get("XDG_STATE_HOME") or self.home / ".local" / "state") / "cad")
        if self.windows:
            found.append(Path(self.environ.get("LOCALAPPDATA") or self.home / "AppData" / "Local") / "cad-state")
        return found


def _stop(process: "subprocess.Popen[bytes]", group: bool = True) -> None:
    """A command that did not answer stopped, with what it started (its process group; on Windows its tree); not
    ``group``, one in this process's own group: elsewhere than Windows, it alone."""
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(process.pid)], stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=30)
        elif group:
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


def read_json(path: Path) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
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
    and then deleted: never half a folder left under its name. The folder is moved into a hidden folder beside it
    (``LEFTOVERS``); if deleting it there fails, what is left is out of the way, and a later run deletes it
    (``tidy``)."""
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



def same_path(one: Any, other: Any) -> bool:
    if not one or not other:
        return False
    return os.path.normcase(os.path.realpath(str(one))) == os.path.normcase(os.path.realpath(str(other)))



# --- cad ----------------------------------------------------------------------------------------------


@dataclass
class Tool:
    """One of uv's tools: its version, its commands' paths by name, and its environment's folder."""

    version: str
    commands: Dict[str, str] = field(default_factory=dict)
    env: str = ""


def uv_tools(here: Here, uv: str) -> Dict[str, Tool]:
    """uv's tools, by name, as ``uv tool list --show-paths`` lists them."""
    tools: Dict[str, Tool] = {}
    current: Optional[Tool] = None
    for line in here.run([uv, "tool", "list", "--show-paths"], timeout=60).out.splitlines():
        tool = re.fullmatch(r"(\S+) v(\S+)(?: \((.*)\))?", line.strip())
        command = re.fullmatch(r"- (\S+)(?: \((.*)\))?", line.strip())
        if tool:
            current = tools[tool.group(1)] = Tool(tool.group(2), {}, tool.group(3) or "")
        elif command and current is not None:
            current.commands[command.group(1)] = command.group(2) or ""
    return tools


def old_launcher(path: Path) -> bool:
    """Whether ``path`` is the ``cad`` command 0.10.0-0.11.11 wrote: ``OLD_LAUNCHER`` in its first lines (on Windows,
    0.11's cad.exe: in the ``__main__.py`` of the zip behind its launcher). A link is never one."""
    if path.is_symlink() or not path.is_file():
        return False
    try:
        if zipfile.is_zipfile(path):
            with zipfile.ZipFile(path) as archive:
                head = archive.read("__main__.py")[:512]
        else:
            with open(path, "rb") as handle:
                head = handle.read(4096)
    except (OSError, KeyError, ValueError, zipfile.BadZipFile):
        return False
    return any(OLD_LAUNCHER.match(line.strip()) for line in head.decode("utf-8", "replace").splitlines()[:3])


def launcher_names(here: Here) -> Tuple[str, ...]:
    """The names of the ``cad`` command 0.10.0-0.11.11 wrote (on Windows 0.11's cad.exe and 0.10's cad.cmd)."""
    return ("cad.exe", "cad.cmd") if here.windows else ("cad",)


def launcher_folders(here: Here, folder: Path) -> List[Path]:
    """uv's bin folder ``folder``, and the folder 0.10.0-0.11.11 wrote their ``cad`` command in where that is another
    (``CAD_LAUNCHER_DIR``, else ``~/.local/bin``)."""
    return list(dict.fromkeys([folder, Path(here.environ.get("CAD_LAUNCHER_DIR") or here.home / ".local" / "bin")]))


def make_room(here: Here, folder: Path, tools: Dict[str, Tool]) -> Tuple[Optional[str], List[Tuple[Path, Path]]]:
    """The ``cad`` command of 0.10.0-0.11.11 (``old_launcher``) set aside, beside itself under a name no shell runs,
    in each of ``launcher_folders``; with it, on Windows, 0.10's cad.cmd (a cad.exe that runs can be renamed, not
    deleted), and the Python 0.11's cad.exe ran (``launcher_python``). ``settle`` deletes them once uv's cad is in, and
    puts them back where it is not; one still in use then stays for a later run (``tidy``). Why the
    install cannot go on, or None: another program's ``cad`` in ``folder``, which uv would not replace (one no tool of
    uv's lists), or ours that cannot be moved; and what was set aside."""
    names = launcher_names(here)
    listed = {os.path.normcase(path) for tool in tools.values() for path in tool.commands.values() if path}
    found = [where / name for where in launcher_folders(here, folder) for name in names if old_launcher(where / name)]
    command = folder / names[0]
    if command not in found and os.path.lexists(command) and os.path.normcase(str(command)) not in listed:
        return (f"cad: not installed: {here.shown(command)} is another program's cad command, which uv will not "
                "replace. Move it away, then run this again."), []
    moved: List[Tuple[Path, Path]] = []
    for path in found:
        python = launcher_python(path)
        aside = path.with_name(f".{path.name}.text-to-cad-old")
        try:
            os.replace(path, aside)
        except OSError as error:
            settle(here, moved, False)
            return (f"cad: not installed: {here.shown(path)}, an earlier release's cad command, could not be moved "
                    f"({error.strerror or error}): close what runs cad, then run this again."), []
        moved.append((path, aside))
        if python is not None:
            try:  # one whose python.exe runs cannot be moved: it stays, harmless, and nothing runs it any more
                os.replace(python, python.with_name(f".{python.name}.text-to-cad-old"))
                moved.append((python, python.with_name(f".{python.name}.text-to-cad-old")))
            except OSError:
                pass
    return None, moved


def launcher_python(path: Path) -> Optional[Path]:
    """The Python 0.11's cad.exe ran: ``cad-launcher`` beside it, a virtual environment (its ``pyvenv.cfg``) with
    nothing installed, which uv made for it (v0.11.10 ``installations.py``: ``INTERPRETER``, ``_make_interpreter``).
    Ours only where the cad.exe beside it is ours (``old_launcher``, checked by the caller) and names it: its shebang,
    after distlib's launcher, is ``#!<launcher_dir>\\cad-launcher\\Scripts\\python.exe``. None elsewhere."""
    folder = path.with_name("cad-launcher")
    if path.name != "cad.exe" or folder.is_symlink() or not (folder / "pyvenv.cfg").is_file():
        return None
    try:
        with open(path, "rb") as handle:
            named = b"#!<launcher_dir>\\cad-launcher\\Scripts\\python.exe" in handle.read(1 << 20)
    except OSError:
        return None
    return folder if named else None


def settle(here: Here, moved: List[Tuple[Path, Path]], done: bool) -> None:
    """What ``make_room`` set aside: deleted, and said, once uv's cad is in (``done``); else put back."""
    for path, aside in moved:
        try:
            if done:
                discard(aside)
            else:
                os.replace(aside, path)
        except OSError:
            continue
        if done:
            what = ("the Python of an earlier release's cad command" if path.name == "cad-launcher" else
                    "the cad command of an earlier release")
            print(f"Removed {what} ({here.shown(path)}).", flush=True)


def tidy(here: Here, folder: Path) -> None:
    """What earlier runs set aside in ``launcher_folders`` and could not delete then (``LEFTOVERS``: Windows keeps a
    file while it runs), deleted where it can be now, quietly; one still in use stays for a later run. Never in a folder
    where a cad command of 0.10.0-0.11.11 is still there (its install did not happen): what is set aside there may be
    what it runs."""
    for where in launcher_folders(here, folder):
        if any(old_launcher(where / name) for name in launcher_names(here)):
            continue
        for pattern in LEFTOVERS:
            for path in where.glob(pattern):
                try:
                    if path.is_dir() and not path.is_symlink():
                        _rmtree(path)
                    else:
                        path.unlink()
                except OSError:
                    pass


def set_aside(folder: Path, tool: Optional[Tool]) -> List[Tuple[Path, Path]]:
    """Windows, before uv installs the cad tool ``tool`` again: its ``cad.exe`` in uv's bin folder ``folder`` and its
    environment's own each renamed to a name of its own in ``folder`` (``ASIDE``), never inside the environment, which
    uv deletes as it installs again. uv cannot replace a cad.exe that runs, and fails halfway (measured, uv 0.13.8), but
    one that runs can be renamed, and runs on from its new name (measured). One that is not there, or cannot be renamed
    (another disk), is skipped. Where uv has no cad tool, nothing: a cad.exe of ours there is ``make_room``'s, and
    another program's is left alone. What was set aside, for ``put_back``."""
    if tool is None:
        return []
    stamp = f"{os.getpid()}-{time.time_ns()}"
    places = [folder / "cad.exe", *([Path(tool.env) / "Scripts" / "cad.exe"] if tool.env else [])]
    moved: List[Tuple[Path, Path]] = []
    for n, exe in enumerate(places):
        aside = folder / ASIDE.format(stamp=stamp, n=n)
        try:
            os.replace(exe, aside)
        except OSError:
            continue
        moved.append((exe, aside))
    return moved


def put_back(moved: List[Tuple[Path, Path]], done: bool) -> None:
    """What ``set_aside`` moved: deleted once uv's cad is in (``done``), else put back where nothing took its place.
    Quietly; one that still runs, or cannot go back, stays for a later run (``tidy``)."""
    for path, aside in moved:
        try:
            if done:
                aside.unlink()
            elif not os.path.lexists(path):
                os.replace(aside, path)
        except OSError:
            pass


def on_path(here: Here, uv: str, folder: Path) -> None:
    """Where uv's bin folder is not on this shell's PATH, uv's own ``uv tool update-shell`` puts it there for new
    terminals, as uv's and Codex's installers do for their own folders: on Windows the user's PATH (winget's uv puts
    its own folder there instead; ``install.ps1`` adds it to the window that ran it), elsewhere the profile of the
    shell in ``SHELL`` (zsh: ``.zshenv``; bash: ``.bashrc`` and ``.bash_profile``; measured, uv 0.13.9). Nothing of
    ours edits a profile. Not where ``UV_NO_MODIFY_PATH`` is set, uv's own switch for this. Where it does not end 0 (it
    has put it there already, and this shell was opened before: exit 2), a line says to open a new terminal."""
    entries = here.environ.get("PATH", "").split(";" if here.windows else ":")
    if any(same_path(entry, folder) for entry in entries if entry):
        return
    if not here.environ.get("UV_NO_MODIFY_PATH"):
        ran = here.run([uv, "tool", "update-shell"], timeout=60)
        if ran.ok:
            print(f"{here.shown(folder)} is on your PATH now for new terminals (uv tool update-shell): apps and "
                  "terminals opened before this one see it once restarted.", flush=True)
            return
    print(f"{here.shown(folder)} is not on this shell's PATH: open a new terminal to use cad (where it is still not "
          "found, run `uv tool update-shell`).", flush=True)


@dataclass
class Cad:
    """What the cad step left: the cad this computer has (None where it has none), the step's exit status (0: cad
    installed, or here already), and its ``cad`` command, the tool's own. ``there``: it was here already and starts,
    so this run installed nothing; ``pipx``: pipx's cad, whose environment is ``env``."""

    release: Optional[str] = None
    code: int = 0
    command: Optional[str] = None
    there: bool = False
    pipx: bool = False
    env: str = ""


def by_cad(here: Here) -> bool:
    """Whether cad ran this command (``BY_CAD``), not a person."""
    return here.by_cad


def find_uv(here: Here) -> Optional[str]:
    """uv: the one that runs this program (`uv run` names itself in ``UV``), else the one found here."""
    return here.environ.get("UV") or here.which("uv")


def already(here: Here, release: str) -> None:
    """The line for a cad that is here and starts, where cad ran this: it is left as it is. Where a person did, the
    update's own line says it (``update``), and none here."""
    if by_cad(here):
        print(f"cad {release} is installed already: it is left as it is, and updates itself.", flush=True)


def find_pipx(here: Here) -> Optional[str]:
    """pipx, where the person's ``pipx install cad`` would have found it: on PATH and in ``~/.local/bin``
    (``Here.which``); unless only PATH is searched, also ``PIPX_BIN_DIR``, ``~/Library/Python/3.*/bin`` (``pip
    install --user pipx`` on macOS), ``/usr/bin``, and on Windows the per-user Pythons' ``Scripts`` folders and Scoop's
    shims. Never ``python -m pipx``: on a Mac without its developer tools, running ``python3`` opens a dialog."""
    found = here.which("pipx")
    if found or here.path_only:
        return found
    name = "pipx.exe" if here.windows else "pipx"
    if here.windows:
        appdata = Path(here.environ.get("APPDATA") or here.home / "AppData" / "Roaming")
        local = Path(here.environ.get("LOCALAPPDATA") or here.home / "AppData" / "Local")
        patterns = [appdata / "Python", local / "Programs" / "Python"]
        folders = [here.home / "scoop" / "shims"]
        folders += sorted((path / "Scripts" for pattern in patterns if pattern.is_dir()
                           for path in pattern.glob("Python3*")), reverse=True)
    else:
        folders = [Path("/usr/bin")]
        python = here.home / "Library" / "Python"
        folders += sorted((path / "bin" for path in python.glob("3.*")), reverse=True) if python.is_dir() else []
    if here.environ.get("PIPX_BIN_DIR"):
        folders.insert(0, Path(here.environ["PIPX_BIN_DIR"]))
    return next((str(folder / name) for folder in folders if (folder / name).is_file()), None)


def pipx_release(env: Path) -> Optional[str]:
    """The release of cad in ``env`` where pipx made it for cad: pipx's ``venvs/cad``, whose ``pipx_metadata.json``
    names ``cad`` as its package; else None."""
    if env.name.lower() != "cad" or env.parent.name != "venvs":
        return None
    try:
        package = json.loads((env / "pipx_metadata.json").read_text(encoding="utf-8"))["main_package"]
        return str(package["package_version"]) if str(package["package"]).lower() == "cad" else None
    except (OSError, ValueError, KeyError, TypeError):
        return None


def pipx_cad(here: Here, folder: Path) -> Optional[Tool]:
    """The ``cad`` pipx installed here (``pipx install cad``), or None: its release, its command and its environment.
    pipx says where its environments are and where it puts their commands (``pipx environment --value``), where it is
    found (``find_pipx``); and, off Windows, where pipx links its commands, a ``cad`` in uv's bin folder ``folder`` (pipx's
    by default too) or on PATH that is a link into pipx's environment of cad is one too, pipx found or not."""
    found: List[Tuple[Path, Optional[Path]]] = []  # (the environment, its command)
    pipx = find_pipx(here)
    if pipx:
        said = {value: here.run([pipx, "environment", "--value", value], timeout=60)
                for value in ("PIPX_LOCAL_VENVS", "PIPX_BIN_DIR")}
        last = {value: ran.out.strip().splitlines()[-1].strip() if ran.ok and ran.out.strip() else ""
                for value, ran in said.items()}
        if last["PIPX_LOCAL_VENVS"]:
            command = Path(last["PIPX_BIN_DIR"]) / ("cad.exe" if here.windows else "cad") if last["PIPX_BIN_DIR"] else None
            found.append((Path(last["PIPX_LOCAL_VENVS"]) / "cad", command))
        else:  # pipx 1.0 (Ubuntu 22.04's) has no `environment`: its list names cad's commands inside its environment
            listed = here.run([pipx, "list", "--json"], timeout=60)
            try:
                paths = json.JSONDecoder().raw_decode(listed.out, listed.out.index("{"))[0]["venvs"]["cad"]["metadata"]["main_package"][
                    "app_paths"] if listed.ok else []
            except (ValueError, KeyError, TypeError):
                paths = []
            found += [(Path(path["__Path__"]).parent.parent, None) for path in paths[:1] if isinstance(path, dict)]
    if not here.windows:
        for link in (folder / "cad", here.which("cad")):
            if link and os.path.islink(link):
                found.append((Path(os.path.realpath(link)).parent.parent, Path(link)))
    for env, command in found:
        release, own = pipx_release(env), env / ("Scripts/cad.exe" if here.windows else "bin/cad")
        if release is not None and own.is_file():
            return Tool(release, {"cad": str(command if command is not None and command.is_file() else own)}, str(env))
    return None


def repair_pipx(here: Here, piped: Tool) -> Cad:
    """pipx's cad that does not start, installed again by pipx (``pipx install --force cad``, pipx found as
    ``find_pipx`` finds it), as uv's is by uv: never by uv, which would make a second cad. pipx's output shown as it
    runs. Where pipx is not found or its install fails, one line says so, and the step has failed."""
    pipx = find_pipx(here)
    if not pipx:
        print(f"cad {piped.version}, installed with pipx, does not start, and pipx was not found here, so it could not be "
              "installed again.", flush=True)
        return Cad(piped.version, 1)
    print(f"cad {piped.version} is installed with pipx but does not start: installing it again with pipx.", flush=True)
    try:
        code = subprocess.call([pipx, "install", "--force", "cad"], env=here.environ, stdin=subprocess.DEVNULL)
    except OSError as error:
        code = 127
        print(f"cad: failed: {error}", flush=True)
    release = pipx_release(Path(piped.env))
    if code:
        print(f"cad: failed (pipx install exit status {code}; what pipx said is above), so cad {piped.version} could not "
              "be installed again.", flush=True)
        return Cad(release, code)
    return Cad(release, 0, piped.commands["cad"], pipx=True, env=piped.env)


def install_cad(here: Here) -> Cad:
    """Step 2 (see the module): the ``cad`` command, a uv tool at PyPI's newest release, only where uv has no ``cad``
    tool, or one whose command does not start (installed again); one that starts, at any release, is not installed
    again (``Cad.there``: ``update`` is what brings it up to date). A ``cad`` pipx installed (``pipx install cad``),
    where uv has none, is a global cad as uv's is: the same where it starts; installed again by pipx where it does
    not (``repair_pipx``), and uv installs no second cad. uv's output shown as it runs. On Windows a ``cad.exe`` that
    runs never stops it: each one in uv's way is renamed aside first (``set_aside``), and what is left set aside is
    deleted by a later run (``tidy``)."""
    uv = find_uv(here)
    if not uv:
        print("cad: failed: uv was not found (install uv: https://docs.astral.sh/uv/)", flush=True)
        return Cad(code=127)
    said = here.run([uv, "tool", "dir", "--bin"], timeout=60)
    lines = said.out.strip().splitlines() if said.ok else []
    folder = Path(lines[-1].strip()) if lines else here.home / ".local" / "bin"
    command = str(folder / ("cad.exe" if here.windows else "cad"))
    tidy(here, folder)
    tools = uv_tools(here, uv)
    tool = tools.get("cad")
    piped = pipx_cad(here, folder) if tool is None else None
    if piped is not None:
        if here.run([piped.commands["cad"], "--version"], timeout=60).ok:
            already(here, piped.version)
            return Cad(piped.version, 0, piped.commands["cad"], there=True, pipx=True, env=piped.env)
        return repair_pipx(here, piped)
    problem, moved = make_room(here, folder, tools)
    if problem:
        print(problem, flush=True)
        return Cad(None, 1)
    again = False
    if tool is not None:
        tool_command = tool.commands.get("cad") or command
        if here.run([tool_command, "--version"], timeout=60).ok:
            settle(here, moved, True)
            already(here, tool.version)
            return Cad(tool.version, 0, tool_command, there=True, env=tool.env)
        # There, but it does not start (a tool Windows left half-replaced, say): installed again.
        print(f"cad {tool.version} is installed but does not start: installing it again with uv.", flush=True)
        again = True
    # Windows: a cad.exe that runs (the typed `cad update` of 0.11.0-0.11.11 that ran this, say) is out of uv's way.
    aside = set_aside(folder, tool) if here.windows else []
    if not again:
        print("Installing cad with uv. The first run downloads it, which takes a minute.", flush=True)
    try:
        code = subprocess.call([uv, "tool", "install", *(["--reinstall"] if again else []), *UV_TOOL_ARGS, "cad"],
                               env=here.environ, stdin=subprocess.DEVNULL)
    except OSError as error:
        code = 127
        print(f"cad: failed: {error}", flush=True)
    put_back(aside, not code)
    settle(here, moved, not code)  # the earlier command back where uv's is not in
    if code:
        print(f"cad: failed (uv tool install exit status {code}; what uv said is above). Where this ran inside an app "
              "or an agent's sandbox, run it again in a terminal of your own.", flush=True)
        left = uv_tools(here, uv).get("cad") if again else None  # a failed reinstall may leave the tool, or not
        return Cad(left.version if left else None, code)
    tool = uv_tools(here, uv).get("cad")
    on_path(here, uv, folder)
    return Cad(tool.version if tool else None, 0, (tool.commands.get("cad") if tool else None) or command)


def over_line(stream: Any, line: str) -> bool:
    """Whether a line written to ``stream`` after ``line`` can take its place, by a carriage return: a terminal, as
    wide as the line at least. A pipe or a file keeps every line."""
    try:
        return stream.isatty() and len(line) < shutil.get_terminal_size().columns
    except (AttributeError, OSError, ValueError):
        return False


def update(here: Here, cad: Cad) -> None:
    """Step 3 (see the module): the cad that was here already brought up to date by its own ``cad update``,
    ``UPDATE_SECONDS`` at most, what it prints captured; then its release read again from uv or pipx, whatever the
    command's exit status. Said in one line as it begins, then one line of what came of it, over the first where the
    terminal allows (``over_line``): updated, the newest already, or not updated now, with cad's own most telling
    line (``Ran.last``) as the reason. Never a failure of the run."""
    first = f"Updating cad {cad.release} to the newest release..."
    over = over_line(sys.stdout, first)
    print(first, end="" if over else "\n", flush=True)
    ran = here.run([cad.command, "update"], timeout=UPDATE_SECONDS, apart=False)
    if cad.pipx:
        release = pipx_release(Path(cad.env))
    else:
        uv = find_uv(here)
        tool = uv_tools(here, uv).get("cad") if uv else None
        release = tool.version if tool else None
    if release and release != cad.release:
        said = f"cad {cad.release} updated to {release}"
        cad.release = release
    elif ran.ok and release:
        # cad's own words where it said them: of its major alone, where a release of a higher major is out.
        newest = f"cad {cad.release} is the newest "
        said = next((line.strip() for line in ran.out.splitlines() if line.strip().startswith(newest)),
                    f"{newest}release")
    elif ran.ok:
        said = f"cad {cad.release} is up to date"
    else:
        why = f"no answer in {UPDATE_SECONDS // 60:.0f} minutes" if ran.code == 124 else ran.last()
        said = f"cad {cad.release} was not updated now ({why}): it updates itself."
    print("\r" + said.ljust(len(first)) if over else said, flush=True)


# --- the plugin, by cad ---------------------------------------------------------------------------------


@dataclass
class Plugin:
    """What the plugin's step left: its exit status (0: it ended well), and each app's status as ``cad plugin
    install`` said it (``{}`` where it said nothing)."""

    code: int = 0
    apps: Dict[str, str] = field(default_factory=dict)


def hand_over(here: Here, cad: Cad, reports: "Reports") -> Plugin:
    """Step 4 (see the module): ``cad plugin install`` by the cad this computer has, else, where that cad has no such
    command or there is none, by the newest release's (``uv tool run ... cad@latest``, once). That cad is asked first,
    its answer captured, whether it has the command (``cad plugin install --help``, which runs nothing: 0 where it
    has it, argparse's usage error ``NO_COMMAND`` where it has none), so a cad without it puts no usage error on the
    terminal. Any other answer is no answer: the command runs for real, and its own exit status 2 with no report
    written still means it had none. Where no cad ran it, one line says the apps were not done, and one report
    (``plugin``)."""
    scratch = tempfile.mkdtemp(prefix="text-to-cad-")
    try:
        said = Path(scratch) / "plugin-report.json"
        environ = {**here.environ, PLUGIN_BY_ENV: "script", PLUGIN_REPORT_ENV: str(said)}
        code, newest = NO_COMMAND, not cad.command
        if cad.command:
            # Asked first, quietly: a cad with no such command, run for real, would put argparse's complaint on the
            # terminal before this command's own line.
            missing = here.run([cad.command, "plugin", "install", "--help"]).code == NO_COMMAND
            if not missing:
                code = here.show([cad.command, "plugin", "install"], environ)
            newest = missing or (code == NO_COMMAND and not said.exists())
            if newest:
                print(f"{f'cad {cad.release}' if cad.release else 'This cad'} has no `cad plugin install`: the newest "
                      "cad's runs instead (uv tool run cad@latest), which uv downloads once.", flush=True)
        else:
            print("Setting up the plugin with the newest cad all the same (uv tool run cad@latest), which uv downloads "
                  "once.", flush=True)
        if newest:
            uv = find_uv(here)
            code = here.show([uv, "tool", "run", "--no-config", *UV_TOOL_ARGS, "cad@latest", "plugin", "install"],
                             environ) if uv else 127
        found = read_json(said)
        apps = found.get("apps") if isinstance(found, dict) else None
        ran = isinstance(apps, dict)
        if code and code != BUSY and not ran:
            # No app was reached. The cad this computer has counts a failure of its own command; where the newest
            # could not be run, or the command could not be started, no cad does.
            how = (f"uv tool run exit status {code}; what it said is above" if newest and code != 127 else
                   "uv was not found" if newest else f"cad plugin install exit status {code}; what it said is above")
            print(f"The plugin was not set up in the agent apps ({how}): run this again.", flush=True)
            if newest or code == 127:
                reports.failed("plugin", code)
        return Plugin(code, {str(key): str(status) for key, status in apps.items()} if ran else {})
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def switch_on(here: Here, cad: Cad, failed: bool) -> None:
    """Step 5 (see the module): ``cad plugin update auto on`` by the cad this computer has, the tool's own command;
    ``failed``, the plugin's step did not end with every app it found gone well (it ended non-zero, or named an app
    ``failed``), which cad is told (``FAILED_ENV``: ``1``, else not there, never the caller's). That command keeps a
    setting and starts nothing, on every release that has it: it never runs this command, an install or ``cad
    update`` (0.11.13's ``_switch`` keeps the switch by the running server, else by itself, and that is all).
    Whatever it answers, the run ends as it would have: a failure is one line."""
    environ = {key: value for key, value in here.environ.items() if key != FAILED_ENV}
    if failed:
        environ[FAILED_ENV] = "1"
    ran = here.run([cad.command, "plugin", "update", "auto", "on"], timeout=120, environ=environ)
    if ran.ok:
        for line in ran.out.splitlines():
            if line.strip():
                print(line, flush=True)
    elif ran.code == NO_COMMAND:  # a usage error: a cad that has no such command
        print(f"{f'cad {cad.release}' if cad.release else 'This cad'} has no `cad plugin update auto`: the plugin will "
              "not follow cad's updates. Run this command again to update the plugin.", flush=True)
    else:
        print(f"The plugin's automatic updates were not turned on (cad said: {ran.last()}). Run this command again to "
              "update the plugin.", flush=True)


# --- one report of a failure ----------------------------------------------------------------------------

# How the environment spells an off and an on, as cad reads them (its ``analytics._environment``).
_OFF, _ON = ("0", "off", "false", "no"), ("1", "on", "true", "yes")
# What the receiver takes for a frame's function and an exception type's name.
_FUNCTION = re.compile(r"[A-Za-z_$<][A-Za-z0-9_$.<>]{0,79}")
_TYPE = re.compile(r"[A-Za-z_][A-Za-z0-9_.]{0,127}")
FRAMES = 10


def development(here: Here) -> bool:
    """Whether this is a checkout's run, which reports nothing: the shell ran a local ``install.py``
    (``CAD_INSTALL_PY``, the rehearsals' hook), or this file is a checkout's (``dev_install.py`` beside it; the hosted
    copy is alone in a scratch folder)."""
    return bool(here.environ.get("CAD_INSTALL_PY")) or Path(__file__).with_name("dev_install.py").exists()


# What cad's kept settings must reach to count as a person told, and as a yes to what is sent now: cad's own numbers
# (its ``analytics.NOTICE`` and ``analytics.DISCLOSURE``, which a test holds these to).
TOLD, AGREED = 1, 1


def kept(settings: Path) -> Optional[bool]:
    """What cad's settings file says of telemetry, as cad decides it (its ``analytics._decide``, by the
    ``telemetry`` section): False where the person said no (``choice`` is ``off``); True where they said yes to what
    is sent now (``choice`` is ``on``, its ``disclosure`` at ``AGREED``), or were told what is sent by default
    (``notifiedAt``, its ``notice`` at ``TOLD``); None where nothing is decided and nobody was told. A file that is
    there and cannot be read now is no yes: False."""
    try:
        text = settings.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except (OSError, ValueError):
        return False
    try:
        found = json.loads(text)
    except ValueError:
        return None
    section = found.get("telemetry") if isinstance(found, dict) else None
    if not isinstance(section, dict):
        return None
    if section.get("choice") == "off":
        return False
    disclosure, when, notice = section.get("disclosure"), section.get("notifiedAt"), section.get("notice")
    if section.get("choice") == "on" and isinstance(disclosure, int) and disclosure >= AGREED:
        return True
    return True if isinstance(when, (int, float)) and isinstance(notice, int) and notice >= TOLD else None


def reporting(here: Here) -> bool:
    """Whether this run may send its one report (see the module): never against the environment's no, in CI, from
    a checkout, or against a no cad keeps; and, where cad started the run, only where cad keeps that the person
    was told or said yes: this run's own line would be read by nobody."""
    def said(name: str) -> str:
        return str(here.environ.get(name) or "").strip().lower()

    if said("DO_NOT_TRACK") in _ON or said("CAD_TELEMETRY") in _OFF or said("CI") not in ("", *_OFF):
        return False
    if development(here):
        return False
    answers = [kept(folder / "settings.json") for folder in here.state_dirs()]
    return False not in answers and (True in answers or not by_cad(here))


def exit_status(code: int) -> int:
    """``code`` as an exit status, 0 to 255: one ended by a signal as a shell says it (128 and the signal)."""
    return code if 0 <= code <= 255 else min(128 - code, 255) if code < 0 else 255


class Reports:
    """The one report a run may send (see the module): ``failed`` for a stage that failed, ``crashed`` for an
    exception of this program's. Neither raises, prints, or sends a second."""

    def __init__(self, here: Here) -> None:
        self.here = here
        self.on = reporting(here)
        self.run = str(uuid.uuid4())  # this run's alone: kept nowhere
        self.sent = False

    def failed(self, stage: str, code: int) -> None:
        self._send({"stage": stage, "outcome": "failed", "code": exit_status(code)})

    def crashed(self, error: BaseException) -> None:
        """``error``, which this program raised: its type's name and its last frames in this file, a function and a
        line each. Python exits 1 for it."""
        try:
            mine = os.path.normcase(os.path.abspath(__file__))
            frames = [{"function": name if _FUNCTION.fullmatch(name) else "<?>", "line": line}
                      for name, line in ((frame.f_code.co_name, line)
                                         for frame, line in traceback.walk_tb(error.__traceback__)
                                         if os.path.normcase(os.path.abspath(frame.f_code.co_filename)) == mine)]
            name = type(error).__name__
            self._send({"stage": "script", "outcome": "crashed", "code": 1,
                        "type": name if _TYPE.fullmatch(name) else "<?>", "frames": frames[-FRAMES:]})
        except Exception:  # noqa: BLE001 - the exception being reported is the one Python shows
            pass

    def _uv(self) -> str:
        uv = find_uv(self.here)
        found = re.match(r"uv (\d+\.\d+\.\d+)\b", self.here.run([uv, "--version"], timeout=10).out) if uv else None
        return found.group(1) if found else "none"

    def _send(self, what: Dict[str, Any]) -> None:
        if not self.on or self.sent:
            return
        self.sent = True
        try:
            platform = self.here.platform
            body = {"schema": 1, "run": self.run, "at": int(time.time()), **what,
                    "platform": platform if platform in ("darwin", "win32") else
                    "linux" if platform.startswith("linux") else "other",
                    "arch": re.sub(r"[^A-Za-z0-9_.+:-]+", "-", _platform.machine().lower())[:16],
                    "by": "cad" if by_cad(self.here) else "person", "uv": self._uv()}
            for late in ("type", "frames"):  # a crash's own, last
                if late in body:
                    body[late] = body.pop(late)
            base = str(self.here.environ.get(API_ENV) or "").strip().rstrip("/")
            request = urllib.request.Request(
                (base if base.startswith(("https://", "http://")) else API) + "/install",
                data=json.dumps(body, separators=(",", ":")).encode("utf-8"), method="POST",
                headers={"Content-Type": "application/json"})

            def post() -> None:
                try:
                    with urllib.request.build_opener().open(request, timeout=REPORT_SECONDS):
                        pass
                except Exception:  # noqa: BLE001 - a report that could not go is not said
                    pass

            # On a thread, so a name that will not resolve cannot hold the run past REPORT_SECONDS.
            sender = threading.Thread(target=post, name="install-report", daemon=True)
            sender.start()
            sender.join(REPORT_SECONDS)
        except Exception:  # noqa: BLE001 - never a failure of the run
            pass


# --- the run ------------------------------------------------------------------------------------------

REPORT_SCHEMA = "text-to-cad install report/1"
# What the report adds to the apps where the plugin's step ended non-zero and named none of them as failed: no
# app's name, and the one word the releases that read the report (0.11.12, 0.11.13) take for a failure, in any value.
UNSAID = {"plugin": "failed"}


def reported(cad: Cad, plugin: Plugin) -> Dict[str, str]:
    """``apps`` of the report cad reads (see the module): what the plugin's step said of each app, and with it
    ``UNSAID`` where that step ended non-zero and named no app as failed, on a computer whose cad step ended 0 (a
    reader would take the run for one that ended well). As the step said them where it ended 0, where it named a
    failure itself, and where cad could not be installed (``setup`` says that)."""
    if cad.code or not plugin.code or "failed" in plugin.apps.values():
        return plugin.apps
    return {**plugin.apps, **UNSAID}


def write_report(here: Here, release: Optional[str], setup: int, apps: Dict[str, str]) -> None:
    """What the run did, written to the file ``CAD_INSTALL_REPORT`` names, where it names one (see the module).
    Never a failure of the run, and never said."""
    target = here.environ.get("CAD_INSTALL_REPORT")
    if not target:
        return
    temporary = None
    try:
        text = json.dumps({"schema": REPORT_SCHEMA, "release": release, "setup": setup, "apps": apps}, indent=1,
                          sort_keys=True) + "\n"
        folder = os.path.dirname(os.path.abspath(target))
        handle, temporary = tempfile.mkstemp(prefix=".install-report-", dir=folder)
        with os.fdopen(handle, "w", encoding="utf-8") as out:
            out.write(text)
        os.replace(temporary, target)
        temporary = None
    except Exception:  # noqa: BLE001 - the report is cad's to read; the run is the person's
        pass
    finally:
        if temporary is not None:
            try:
                os.remove(temporary)
            except OSError:
                pass


def utf8(stream: Any, system: str = os.name) -> bool:
    """Whether this installer writes ``stream`` in UTF-8: on Windows, one that is no console (a pipe, a file), where
    Python would write the ANSI code page. uv and cad, which it runs on the same streams, write such a stream in
    UTF-8, so the install command's lines are one encoding there. A console stays as it is, as does every stream on
    other systems."""
    try:
        return system == "nt" and not stream.isatty()
    except (AttributeError, OSError, ValueError):  # no stream, or a closed one
        return False


def started(environ: Dict[str, str]) -> bool:
    """The file the shell that ran this program named (``MARK_ENV``), left as it starts; whether it named one. The
    variable goes no further: nothing this program runs is this program."""
    mark = environ.pop(MARK_ENV, None)
    if mark:
        try:
            Path(mark).touch()
        except OSError:
            pass
    return bool(mark)


def main(argv: Optional[Sequence[str]] = None) -> int:
    here = Here()
    by_shell = started(here.environ)
    # On Windows, a pipe or a file in UTF-8, as uv's and cad's lines in it are (`utf8`). A character the output's
    # encoding has not (a stream left in a code page) is printed as `?`, never raised.
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(errors="replace", **({"encoding": "utf-8"} if utf8(stream) else {}))
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv:
        print("This installer takes no options: run it as it is to install or update text-to-cad in every agent app "
              "on this computer. To remove text-to-cad, run `uv tool uninstall cad`, and each app's own remove "
              "command.", file=sys.stderr)
        return 2
    reports = Reports(here)
    # Said to a person: the shell that ran this has said it already, and a run cad started has no reader.
    if reports.on and not by_shell and not by_cad(here):
        print(NOTICE, flush=True)
    try:
        return run(here, reports)
    except Exception as error:
        reports.crashed(error)
        raise


def run(here: Here, reports: Reports) -> int:
    """Steps 2-5, said as they go; then the report cad reads, last."""
    cad = install_cad(here)
    if cad.code:
        reports.failed("cad", cad.code)
    elif cad.there and not by_cad(here):
        update(here, cad)
    plugin = hand_over(here, cad, reports)
    if cad.command:
        switch_on(here, cad, bool(plugin.code) or "failed" in plugin.apps.values())
    if cad.code:
        print("cad itself was not installed (what went wrong is above), and the plugin's skills need it: run this "
              "again.", flush=True)
    write_report(here, cad.release, cad.code, reported(cad, plugin))
    return 1 if cad.code else BUSY if plugin.code == BUSY else 1 if plugin.code else 0


if __name__ == "__main__":
    sys.exit(main())
