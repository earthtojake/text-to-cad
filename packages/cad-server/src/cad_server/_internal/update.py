"""The updater: the default channel moved to a newer release, by the update button (``POST /api/v1/local/update``),
by ``cad update`` (``cad_server.cli.update``), by itself when automatic updates are on (``automatic``,
``cad_server/auto_updates.py``), and by a pinned command newer than the default channel's version
(``cad_server._internal.pins.update_default``).

Only the default channel has an updater, and only where the install command has run here (its receipt,
``install-receipt.json``): a named channel's copy is updated by whoever delivers it. Only the default channel's
version's server reads the version feed and offers the update (``cad_server._internal.channel.told``).

**The contract, from this release on.** An updater does one thing to a newer release V: it installs it and runs
its setup. Nothing else passes between the two releases, so no later release depends on how this one behaves:

1. **Install** (``install``): V's own ``cad setup --add --quiet``, run by uvx (``uvx --no-config --managed-python
   --python 3.14 --from cad-server==V cad setup --add --quiet``), the same command the ``cad`` command and the CAD
   app's launcher run for a version they lack. V makes itself present in its own folder; exit 0 means it is.
2. **Its setup** (``run_setup``): the ``cad`` its code marker names (``versions/V/code/cad-version.json``'s
   ``cad``, the line the ``cad`` command reads too), run as ``cad setup --engine-update`` and nothing else:
   standard input closed; its progress on standard output, a JSON line a frame (``{"progress": frame}``, kind
   ``update``, stage one of ``STAGES``), which the updater may stop reading at any moment; its words on standard
   error; its exit status the result, 0 when it moved the default channel to itself. V's setup does the rest: the
   default channel moved (``versions.move``: the first-start import, the pointer, the mirror for 0.11.10 and
   earlier, every version no pointer names removed, the pages' port handed to V's server), then the apps step
   (our own plugin copies given V's text; a store's copy is left alone). The move may stop the server that runs
   the updater -- that is the update -- so a setup outlives the process that started it, and writes its frames
   as long as someone reads them.

That is what any release's setup is handed: one argument, and no variable, file or port.

**The sequence V's setup runs** (``cad_server.cli.setup``), each step safe to repeat, and what a failure leaves:

1. V present (``versions.make_present``). Fails: nothing changed; the old version serves as before.
2. The default channel moved to V (``versions.move``): V's data imported from the old version, V proven to run,
   then the pointer written -- the one write that is the update -- and the mirror. Fails before the pointer:
   nothing changed but V's own folder. After it: V is the default, the old version is removed when nothing is
   connected to it (else by the next sweep), and V's server takes the old one's port where the old one stopped.
3. The apps step. Fails for an app -- a command of it fails, or its command is not on the PATH the setup runs with
   while it keeps an older copy of ours --: that app keeps its copy of the text before, said on stderr, and is
   recorded behind in the receipt (``cli.setup.BEHIND``), which ``cad doctor`` names. An updater's run
   (``--engine-update``) still exits 0, since the default channel moved; a person's run (the install command, ``cad
   update`` run from a terminal) exits 1 for a command that failed (a command missing from its PATH is said in its
   plan, and recorded, but fails nothing). ``cad update`` or the install command run again does the step again
   (``move`` finds V already the default), and so does the default version's server by itself once a day while idle
   (``Update.catch_up``).

Nothing running is switched under a command: the old version's server is stopped only when nothing is in flight
there (``versions.connected``), and otherwise retires by itself once it is idle.

The server's own updater (``Update``): one at a time, in the background of the default version's server, the
request that asked for it answered at once, and the page that asked reads where it is (``GET
/api/v1/server``'s ``update``) until one of two endings: the server goes and V's comes back on the same port, with the
same token (nothing was in flight here, and no other channel is on this version); or this server stays -- work in
flight here, or another channel still on its version -- and the update ends as ``moved``, naming the address of V's
server, started on the next free port, which the page goes to (``Update.snapshot``, ``_moved``).
An update installs V, which no sweep removes while it waits, installed and never used (``versions.fate``); an
updater that prepares a newer release removes its own earlier target, which it made and never moved to
(``_discard``). An automatic update installs V at once (step 1 of the contract, in the background) and runs its
setup once the
server has handled nothing for ``auto_updates.IDLE_SECONDS``: no build, draw, export, request that serves or
agent's tool call in flight (``Daemon.working``, asked every ``IDLE_POLL_SECONDS``) and none ended since
(``Daemon.worked``: where "the last command" is read), no drain, no ``cad setup`` holding the install lock. A
click meanwhile makes it the click's, done at once. One that fails says nothing to any page, unless a click had
made it its own, and is not tried again by itself for a day (``auto_updates.attempt``).

Where an update is goes as progress frames of kind ``update`` (``cad.engine.progress``): ``install`` while V is
installed, ``build123d`` once it is (its kernel environment is made with it), ``restart`` as V's setup moves the
default channel, ``apps`` while it gives the apps its text; the page sees as many as the old server lives for.
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from typing import Any, Callable

__all__ = ["STAGES", "UPDATE", "Update", "environment", "install", "install_command", "installed_here", "run_setup"]

# The stages of an update, in order, as its progress frames count them (``cad.engine.progress``).
STAGES = ("install", "build123d", "restart", "apps")
# How often an automatic update that is ready looks whether the server is idle.
IDLE_POLL_SECONDS = 1.0
# How long an install of a release may take (uv's cache first; the network for what it lacks, the kernel's first
# download among it).
INSTALL_SECONDS = 1800.0
# The apps behind (``catch_up``): how often the default version's server runs its setup again for them at most, how
# long that run may take, and the record of its last one, in the version's data folder.
CATCH_UP_SECONDS = 24 * 60 * 60.0
CATCH_UP_BOUND = 1800.0
CAUGHT_UP = "apps-caught-up.json"


# --- the contract: install it, run its setup --------------------------------------------------------------------


def installed_here() -> bool:
    """Whether the install command has run on this device (its receipt): the one place the default channel has an
    updater."""
    from cad.engine.places import state_dir
    from cad_server._internal.pointers import RECEIPT

    try:
        return (state_dir() / RECEIPT).is_file()
    except OSError:
        return False


def install_command(version: str) -> list[str]:
    """Step 1 of the contract for ``version``: its own ``cad setup --add --quiet`` through uvx, as the ``cad``
    command runs it for a version it lacks; a folder of wheels a test names read beside the index
    (``base.FIND_LINKS_ENV``)."""
    from cad_server._internal import base
    from cad_server._internal.launch import COMMAND, PYTHON, SERVER

    links = os.environ.get(base.FIND_LINKS_ENV, "").strip()
    return [base.find_uv(), "tool", "run", "--no-config", "--managed-python", "--python", PYTHON,
            *(["--find-links", links] if links else []), "--from", f"{SERVER}=={version}", COMMAND, "setup", "--add",
            "--quiet"]


def environment() -> dict[str, str]:
    """The environment another release runs in: this one's, but none of this process's import path, its version's
    name or its channel (a release knows its own)."""
    from cad.engine.places import INSTALLATION_ENV, RUN_WITH

    return {key: value for key, value in os.environ.items()
            if key not in ("PYTHONPATH", "PYTHONHOME", INSTALLATION_ENV, RUN_WITH, "CAD_UPDATE_PREPARE")}


def install(version: str) -> dict[str, Any]:
    """Release ``version`` installed by its own release (step 1 of the contract): its code marker
    (``places.version_record``). ``base.Refused`` in one line when it could not be."""
    from cad.engine import places
    from cad_server._internal import base

    found = places.version_record(version)
    if found is not None and places.alive(found):
        return found
    try:
        done = subprocess.run(install_command(version), env=environment(), stdin=subprocess.DEVNULL,
                              capture_output=True, text=True, encoding="utf-8", errors="replace",
                              timeout=INSTALL_SECONDS, **places.windowless())
    except FileNotFoundError as error:
        raise base.Refused(f"text-to-cad {version} could not be installed: {error}", "uv") from None
    except (OSError, subprocess.SubprocessError) as error:
        raise base.Refused(f"text-to-cad {version} could not be installed: {type(error).__name__}: {error}") from None
    places._versioned.cache_clear()
    found = places.version_record(version)
    if done.returncode == 0 and found is not None and places.alive(found):
        return found
    lines = [line.strip() for line in (done.stderr or done.stdout or "").splitlines() if line.strip()]
    raise base.Refused(lines[-1] if lines else f"text-to-cad {version}'s install exited {done.returncode}")


def run_setup(record: dict[str, Any], *, frame: Callable[[str, str], None] | None = None,
              args: tuple[str, ...] = ("--engine-update",), environ: dict[str, str] | None = None,
              seconds: float | None = None) -> tuple[int, str]:
    """Step 2 of the contract: the setup of the release whose code marker is ``record``, ``cad setup
    --engine-update``, each progress frame it writes handed to ``frame`` (stage, detail) as it comes: its exit
    status, and the last line it said on standard error when it failed. Started in a session of its own, so it
    outlives this process should its move stop this process's server. ``environ``: variables over this process's
    environment (``catch_up``'s PATH); ``seconds``: a bound, past which it is killed."""
    from cad.engine import places

    errors: list[str] = []
    with subprocess.Popen([record["cad"], "setup", *args], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace",
                          env={**environment(), "PYTHONUNBUFFERED": "1", **(environ or {})},
                          **places.detached()) as process:
        bound = threading.Timer(seconds, process.kill) if seconds else None
        if bound is not None:
            bound.daemon = True
            bound.start()
        reading = threading.Thread(target=lambda: errors.extend(process.stderr or ()), daemon=True)
        reading.start()
        try:
            for line in process.stdout or ():
                try:
                    said = json.loads(line)
                except ValueError:
                    continue
                found = said.get("progress") if isinstance(said, dict) else None
                if frame is not None and isinstance(found, dict) and found.get("kind") == "update" \
                        and found.get("stage") in STAGES:
                    frame(found["stage"], str(found.get("detail") or ""))
            code = process.wait()
        finally:
            if bound is not None:
                bound.cancel()
        reading.join(5)
    lines = [line.strip() for line in errors if line.strip()]
    return code, lines[-1] if lines else ""


# --- the server's own updater ------------------------------------------------------------------------------------


class Update:
    """The server's update: its state, which the page and the card read, and its work."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.state: dict[str, Any] = {"state": "idle", "target": None, "progress": None, "error": None}
        self.started = 0.0
        self.thread: threading.Thread | None = None
        # An automatic update getting ready (``automatic``): ``{"state": "preparing" | "waiting", "release",
        # "progress"}``, never in ``state`` until its setup runs; None when there is none.
        self.auto: dict[str, Any] | None = None
        # A click, while an automatic update gets ready: it goes on at once, as the click's.
        self.urgent = threading.Event()
        # When the update last failed (monotonic).
        self.failed_at = float("-inf")
        # The setup run again for the apps behind (``catch_up``), while it runs.
        self.catching: threading.Thread | None = None

    def snapshot(self) -> dict[str, Any]:
        """Where the update is: ``state`` (``idle``, ``working``, ``restarting``, ``moved``, ``failed``), the release
        it moves to (``target``), its last progress frame and, failed, why. ``moved``: the default channel moved to
        ``target`` and this server stays (another channel is still on its version, or work is in flight here), so a
        page that asked goes to the new default's server, at ``address`` (None where it could not be reached), with a
        link signed with its token (``moved_token``)."""
        with self.lock:
            return {key: value for key, value in self.state.items() if key != "token"}

    def moved_token(self) -> str | None:
        """The page token of the server an update moved the default channel to (``snapshot``'s ``address``), which the
        page's application signs a link with for a page going there (``viewer.http_app``): None where there is none.
        Never in the update's state."""
        with self.lock:
            token = self.state.get("token") if self.state.get("state") == "moved" else None
        return token if isinstance(token, str) and token else None

    def status(self) -> dict[str, Any]:
        """What the server's ``status`` says of its update (``cad status``): its state, its release, and an
        automatic update getting ready (``automatic``), or None."""
        with self.lock:
            auto = self.auto
            return {"state": self.state["state"], "target": self.state["target"],
                    "automatic": None if auto is None else {"state": auto["state"], "release": auto["release"]}}

    def _frame(self, stage: str, detail: str = "") -> None:
        """A progress frame: the update's, which the page reads while it is ``working``, and an automatic
        update's, kept with it until its setup runs (or a click makes it the click's)."""
        from cad.engine.progress import event

        with self.lock:
            auto = self.auto
            target = self.state.get("target") or (auto["release"] if auto else "")
        frame = event("update", stage, job=str(target or ""), detail=detail,
                      done=STAGES.index(stage), total=len(STAGES),
                      elapsed_ms=int((time.monotonic() - self.started) * 1000))
        with self.lock:
            if self.auto is not None:
                self.auto["progress"] = frame
            if self.state["state"] in ("working", "restarting"):
                self.state["progress"] = frame
                if stage in ("restart", "apps"):
                    self.state["state"] = "restarting"

    def start(self, server: Any = None) -> dict[str, Any]:
        """The update started, unless one runs; its state. ``server`` (the HTTP server the click came through) is
        not needed: the release's setup takes the port from this server's own status. The feed is read with no
        lock held (``updates.newest``, a few seconds at most): the page's reads of the state never wait on it."""
        from cad_server import updates

        with self.lock:
            if self.state["state"] in ("working", "restarting"):
                return dict(self.state)
            if self.auto is not None:
                # An automatic update getting ready: the click's now, and done at once (``_wait``).
                self.urgent.set()
                self.state = {"state": "working", "target": self.auto["release"], "progress": self.auto.get("progress"),
                              "error": None}
                return dict(self.state)
            self.state = {"state": "working", "target": None, "progress": None, "error": None}
            self.started = time.monotonic()
        from cad_server import auto_updates

        previous = (auto_updates.attempted() or {}).get("release")
        if not installed_here():
            from cad_server.updates import command

            self._failed(f"there is no install of text-to-cad here to update: the install command installs one, "
                         f"{command()}")
            return self.snapshot()
        target = updates.newest()
        with self.lock:
            if target is None:
                self.state = {"state": "idle", "target": None, "progress": None, "error": None}
                return dict(self.state)
            self.state = {**self.state, "target": target}
            self.thread = threading.Thread(target=self._run, args=(target, previous), name="cad-update",
                                           daemon=True)
            self.thread.start()
            return dict(self.state)

    def _failed(self, error: str) -> None:
        with self.lock:
            self.state = {**self.state, "state": "failed", "error": error}
            self.failed_at = time.monotonic()

    def _run(self, target: str, previous: str | None = None) -> None:
        from cad_server._internal import base

        try:
            self._frame("install", f"text-to-cad {target}")
            record = install(target)
            _discard(previous, target)
            self._frame("build123d")
            self._setup(target, record)
        except base.Refused as refused:
            self._failed(str(refused))
        except Exception as error:  # noqa: BLE001 - an update that cannot go on leaves the server as it was
            self._failed(f"{type(error).__name__}: {error}")

    def _setup(self, target: str, record: dict[str, Any]) -> None:
        """Step 2: the release's own setup, which moves the default channel to it and may stop this server as it
        does. Should it return with this server still here, the update held (this server, no channel's now,
        retires once idle) or failed, said in its one line."""
        code, said = run_setup(record, frame=self._frame)
        if code != 0:
            self._failed(said or f"text-to-cad {target}'s setup failed (exit status {code})")
            return
        moved = _moved(target)
        with self.lock:
            if moved is None:  # this server goes: the new default's takes its port, and the page reloads into it
                self.state = {**self.state, "state": "restarting"}
            else:  # this server stays: the update is done here, and a page goes to the new default's server
                self.state = {**self.state, "state": "moved", "progress": None, "address": moved.get("url"),
                              "token": moved.get("token")}

    # --- the automatic update ------------------------------------------------------------------------------------

    def automatic(self, engine: Any) -> str | None:
        """The server's own update, asked for as it tends itself (``Daemon.tend``): when automatic updates are on
        (``auto_updates.enabled``), the install command has run here (``installed_here``), this server's version
        is the default channel's (the feed is read and told for it alone, ``updates.notice``), and a newer release
        that breaks nothing is known (``auto_updates.takes``) -- the feed as last read, read again in the
        background when an hour has passed -- and nothing stands in its way: no update running or getting ready,
        none failed in the last ``RETRY_SECONDS`` by itself, no drain, no ``cad setup`` holding the install lock
        (``auto_updates.installing``), and that release not tried by itself in the last day
        (``auto_updates.due``). Then it gets ready in the background (``_automatic``): the release it moves to, or
        None. Never raises; never waits on the network."""
        from cad_server import auto_updates, updates

        try:
            if not auto_updates.enabled() or not installed_here():
                return None
            updates.refresh()  # due: read in the background, for the next tend; this one goes by what it knows
            found = updates.notice()
            if found is None:
                return None
            target = found["latest"]
            if not auto_updates.takes(found["version"], target):  # a breaking release waits for a click
                return None
            with self.lock:
                if self.auto is not None or self.state["state"] in ("working", "restarting"):
                    return None
            if getattr(engine, "draining", False) or engine.stopping.is_set() or auto_updates.installing():
                return None
            if not auto_updates.due(target, auto_updates.attempted(), time.time()):
                return None
            with self.lock:
                if self.auto is not None or self.state["state"] in ("working", "restarting"):
                    return None
                self.auto = {"state": "preparing", "release": target, "progress": None}
                self.urgent.clear()
                self.started = time.monotonic()
                previous = (auto_updates.attempted() or {}).get("release")
                self.thread = threading.Thread(target=self._automatic, args=(target, engine, previous),
                                               name="cad-update-automatic", daemon=True)
            auto_updates.attempt(target)
            self.thread.start()
            return target
        except Exception:  # noqa: BLE001 - the server's tending never fails for an update
            return None

    def _automatic(self, target: str, engine: Any, previous: str | None = None) -> None:
        """An automatic update: its release installed now (an earlier target it made and never moved to, ``previous``,
        removed: ``_discard``); its setup once the server is idle (``_wait``), or at once should a click make it its
        own."""
        from cad_server import auto_updates
        from cad_server._internal import base

        try:
            self._frame("install", f"text-to-cad {target}")
            record = install(target)
            _discard(previous, target)
            self._frame("build123d")
            with self.lock:
                if self.auto is not None:
                    self.auto["state"] = "waiting"
            if not self._wait(engine):
                with self.lock:
                    self.auto = None
                return
            with self.lock:
                self.auto = None
            self._setup(target, record)
            with self.lock:
                failed = self.state["state"] == "failed" and self.state.get("error")
            if failed:
                auto_updates.attempt(target, error=str(failed))
        except Exception as error:  # noqa: BLE001 - an update that cannot go on leaves the server as it was
            said = str(error) if isinstance(error, (base.Refused, RuntimeError)) else f"{type(error).__name__}: {error}"
            auto_updates.attempt(target, error=said)
            with self.lock:
                self.auto = None
                shown = self.urgent.is_set() or self.state["state"] == "working"
            if shown:
                self._failed(said)  # a click made it its own: its page says it
            else:
                with self.lock:
                    self.failed_at = time.monotonic()

    # --- the apps behind -----------------------------------------------------------------------------------------

    def catch_up(self, engine: Any) -> list[str] | None:
        """The apps step run again, by the default version's server as it tends itself (``Daemon.tend``), for the apps
        the receipt says are behind this version (``behind``: a step of its setup could not give them its text --
        their command line missing from the PATH of the process that ran it, most often): this version's own ``cad
        setup --engine-update``, as an update runs it (``run_setup``), which finds the default channel on it already
        and does the apps step again, recording what it did in the receipt. Only where this server has an updater
        (``channel.told``), once it has handled no command for ``auto_updates.IDLE_SECONDS`` and nothing is in flight
        (as an automatic update waits), with no update running or getting ready and no ``cad setup`` holding the
        install lock; at most once every ``CATCH_UP_SECONDS`` (``CAUGHT_UP``); in the background, bounded by
        ``CATCH_UP_BOUND``, with the PATH of the last shell a build came from (``Daemon.shell_path``), where those
        command lines are. The apps it runs it for, or None. Never raises; never waits on the network."""
        from cad_server import auto_updates

        try:
            from cad.engine import places
            from cad_server._internal.channel import told

            name = places.versioned()
            if name is None or not told():
                return None
            lagging = sorted(app for app, row in behind().items() if row.get("release") == name)
            if not lagging:
                return None
            with self.lock:
                if self.auto is not None or self.state["state"] in ("working", "restarting") \
                        or (self.catching is not None and self.catching.is_alive()):
                    return None
            if getattr(engine, "draining", False) or engine.stopping.is_set() or engine.working():
                return None
            if not auto_updates.quiet(float(getattr(engine, "worked", 0.0) or 0.0), time.monotonic()):
                return None
            if auto_updates.installing():
                return None
            now = time.time()
            last = _caught_up()
            if last is not None and 0 <= now - last < CATCH_UP_SECONDS:
                return None
            record = places.version_record(name)
            if record is None or not places.alive(record):
                return None
            _caught_up(now, lagging)
            shell = getattr(engine, "shell_path", None)
            with self.lock:
                self.catching = threading.Thread(target=self._catch_up, args=(record, shell), name="cad-apps",
                                                 daemon=True)
                self.catching.start()
            return lagging
        except Exception:  # noqa: BLE001 - the server's tending never fails for the apps
            return None

    @staticmethod
    def _catch_up(record: dict[str, Any], shell: str | None) -> None:
        from cad_server._internal.providers import lasting

        try:
            run_setup(record, environ={"PATH": lasting(shell)} if shell else None, seconds=CATCH_UP_BOUND)
        except Exception:  # noqa: BLE001 - said by the receipt it leaves, and tried again tomorrow
            pass

    def _wait(self, engine: Any) -> bool:
        """Until the server is idle -- nothing in flight (``working``) and none ended (``worked``) for
        ``auto_updates.IDLE_SECONDS``, no drain, no ``cad setup`` holding the install lock -- or a click makes the
        update its own: then the update is ``working``, and True. False when it is no longer wanted: the server
        stops or drains, or the person turned automatic updates off (its attempt forgotten, so turning them on
        again goes on with it)."""
        from cad_server import auto_updates

        quiet_since = time.monotonic()
        while True:
            if self.urgent.wait(IDLE_POLL_SECONDS):
                return True  # ``start`` made it ``working``
            if engine.stopping.is_set() or getattr(engine, "draining", False):
                return False
            if not auto_updates.enabled():
                auto_updates.forget()
                return False
            now = time.monotonic()
            if engine.working():
                quiet_since = now
            quiet_since = max(quiet_since, float(getattr(engine, "worked", 0.0) or 0.0))
            if not auto_updates.quiet(quiet_since, now):
                continue
            if auto_updates.installing():
                quiet_since = now
                continue
            with self.lock:
                if self.urgent.is_set():
                    return True
                auto = self.auto or {}
                self.state = {"state": "working", "target": auto.get("release"), "progress": auto.get("progress"),
                              "error": None}
                return True


_RECEIPT_READ: list[Any] = [None, {}]  # the receipt as ``behind`` last read it: its identity, and what it said


def behind() -> dict[str, dict[str, Any]]:
    """The apps the receipt records behind (``cli.setup.BEHIND``): each app's ``{release, why, at}``. Read again only
    when the receipt changed since (one ``stat``): the server asks it as it tends itself. Nothing for a device with
    no receipt, or one that cannot be read."""
    from cad.engine.places import state_dir
    from cad_server._internal.pointers import RECEIPT

    path = state_dir() / RECEIPT
    try:
        found = os.stat(path)
    except OSError:
        return {}
    seen = (str(path), found.st_mtime_ns, found.st_size)
    if _RECEIPT_READ[0] == seen:
        return _RECEIPT_READ[1]
    try:
        kept = json.loads(path.read_text(encoding="utf-8")).get("behind")
        rows = {app: row for app, row in kept.items()
                if isinstance(app, str) and isinstance(row, dict) and isinstance(row.get("release"), str)}
    except (OSError, ValueError, AttributeError):
        rows = {}
    _RECEIPT_READ[0], _RECEIPT_READ[1] = seen, rows
    return rows


def _caught_up(now: float | None = None, apps: list[str] | None = None) -> float | None:
    """When the default version's server last ran the apps step again (``catch_up``), from its record in this
    version's data folder (``CAUGHT_UP``); with ``now``, that run kept as it begins. Never raises."""
    from cad.engine.places import data_dir

    path = data_dir() / CAUGHT_UP
    if now is None:
        try:
            at = json.loads(path.read_text(encoding="utf-8")).get("at")
        except (OSError, ValueError, AttributeError):
            return None
        return float(at) if isinstance(at, (int, float)) else None
    from cad._internal.atomic_replace import write_bytes_atomic

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        write_bytes_atomic(path, (json.dumps({"at": now, "apps": apps or []}) + "\n").encode("utf-8"))
    except OSError:
        pass
    return now


def _moved(target: str) -> dict[str, Any] | None:
    """After a setup that moved the default channel to ``target`` returned 0 with this server still running: where
    the new default's server serves pages (``{"url", "token"}``), started for it where it does not run yet -- it
    takes the next free port, this one still holding its own --; ``{}`` where it could not be started or asked (the
    update is done all the same). None where this server is on its way out after all, or the update is no move of
    its own: a process with no version, its own version still the default's, or its door closed (the move's drain:
    the new default's server takes this one's port, and a page reloads into it there). Never raises."""
    try:
        from cad.engine.places import versioned
        from cad_server._internal import pointers, versions

        name = versioned()
        if name is None or name == target or pointers.read(None) != target or not versions.serves(name):
            return None
        if not versions.start_server(target):
            return {}
        answer = versions.ask(target, {"op": "http"}, seconds=versions.START_SECONDS)
        if not isinstance(answer, dict) or "failed" in answer or not isinstance(answer.get("url"), str):
            return {}
        return {"url": answer["url"], "token": answer.get("token") if isinstance(answer.get("token"), str) else None}
    except Exception:  # noqa: BLE001 - the update is done: a page that cannot be sent on is told so
        return {}


def _discard(previous: str | None, target: str) -> None:
    """The release this updater last went for (``previous``, ``auto_updates.attempted``), older than the one it has
    just installed and never moved to, removed: installed and never used, no sweep would ever take it
    (``versions.remove_unused``, which keeps one a pointer names or that has been used). Never raises."""
    from cad_server._internal import versions

    if not previous or previous == target or not versions.older(previous, target):
        return
    try:
        versions.remove_unused(previous)
    except Exception:  # noqa: BLE001 - a folder left is cad doctor --prune's: never a failed update
        pass


UPDATE = Update()
