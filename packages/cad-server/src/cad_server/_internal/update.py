"""The update the engine runs when a person clicks its update button (``POST /__cad/update``), and
the one it runs by itself when automatic updates are on (``automatic``, ``cad_server/auto_updates.py``).

One at a time, in the engine's own process, in the background: the request that asked for it is
answered at once, and the page or card that asked reads where it is (``GET /__cad/version``'s
``update``) until the engine goes and comes back with the new release.

An automatic update takes the same steps, in two halves. The daemon asks for it as it tends itself
(``automatic``, every ``daemon.TEND_SECONDS``): with the setting on, and the feed as last read (read
again in the background once an hour) or an agent app's newer server naming a release newer than this
one, its folder is made and its own ``cad setup --engine-update`` run with ``PREPARE_ENV`` set, which
registers it and makes its base and stops there: nothing of the apps or the engine changes. That
release is then kept ready until the engine has run nothing for ``auto_updates.IDLE_SECONDS`` -- no
build, draw, export, request that serves or agent's MCP call in flight (``Daemon.working``, and when
the last ended, ``Daemon.worked``), no drain, no ``cad setup`` holding the install lock -- and only
then is its setup run whole (the apps' plugins) and the engine switched, as a click does: the state
is ``working``, then ``restarting``, so a page or card open follows it to the new release as it
follows a click. Until then the state stays ``idle``: no page shows it. A click meanwhile makes it the
click's, done at once (``start``). One that fails in the engine is kept as failed
(``auto_updates.attempt``) and says nothing to any page, unless a click had made it its own; a switch
that fails comes back as any switch does (``recall``). Neither is tried again by itself for a day.

1. **The release**: the newest the version feed names, read now (``cad_server/updates.py``), or a newer
   one an agent app's CAD server runs (``updates.seen``, which needs no network).
2. **Its folder**: ``<state>/releases/<release>`` made with uv (``cad_server._internal.releases``).
3. **Its setup**: that release's own ``cad setup``, run from its folder, which registers it, makes
   its base -- so the first build after the restart is warm -- and updates each agent app's plugin
   exactly as ``cad setup`` does, but switches nothing (``--engine-update``); it says where it is
   on stdout, a progress frame a line.
4. **The switch**: the engine drains (``cad_server.engine.daemon.Daemon.drain``: nothing in flight, open
   pages and held sessions not counted) and, as it exits, starts the helper, ``cad update --switch``
   (``cad_server._internal.switch``), which starts the new release's engine on the same port, with the same
   token, and goes back to this one should it fail.

Where it is goes as progress frames of kind ``update`` (``cad.engine.progress``): ``install`` while
the release's folder is made, ``build123d`` while its base is, ``apps`` while the apps' plugins are
updated, ``restart`` once the engine drains. A step that fails ends it, said in one line, and the
engine stays as it was. A switch that fails brings the release before back, whose engine, starting to
serve, says the update failed (``Update.recall``) to the page that followed it through the restart.
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from typing import Any, Callable

__all__ = ["UPDATE", "Update"]

# The stages of an update, in order, as its progress frames count them (``cad.engine.progress``).
STAGES = ("install", "build123d", "apps", "restart")
# How recent a failed switch is that an engine starting to serve says as its own update's failure
# (``Update.recall``): the release before's engine, which the failed switch starts again, serves within a
# minute or two of it; an older one is no news to an engine started later.
RECALL_SECONDS = 600.0
# Set in the environment of a release's ``cad setup --engine-update`` that an automatic update runs
# before the engine is idle: it registers the release and makes its base, and stops before the apps.
# A release that does not know it does the whole setup, and the second run finds nothing to do.
PREPARE_ENV = "CAD_UPDATE_PREPARE"  # ``cad_server.cli.setup.PREPARE_ENV``
# How often an automatic update that is ready looks whether the engine is idle.
IDLE_POLL_SECONDS = 1.0


class Update:
    """The engine's update: its state, which the page and the card read, and its work."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.state: dict[str, Any] = {"state": "idle", "target": None, "progress": None, "error": None}
        self.started = 0.0
        self.thread: threading.Thread | None = None
        # An automatic update getting ready (``automatic``): ``{"state": "preparing" | "waiting",
        # "release", "progress"}``, never in ``state`` until it switches; None when there is none.
        self.auto: dict[str, Any] | None = None
        # A click, while an automatic update gets ready: it goes on at once, as the click's.
        self.urgent = threading.Event()
        # When the update last failed, here or in a switch the engine recalls (monotonic).
        self.failed_at = float("-inf")

    def snapshot(self) -> dict[str, Any]:
        """Where the update is: ``state`` (``idle``, ``working``, ``restarting``, ``failed``), the
        release it moves to (``target``), its last progress frame and, failed, why."""
        with self.lock:
            return dict(self.state)

    def status(self) -> dict[str, Any]:
        """What the engine's ``status`` says of its update (``cad status``): its state, its release, and
        an automatic update getting ready (``automatic``), or None."""
        with self.lock:
            auto = self.auto
            return {"state": self.state["state"], "target": self.state["target"],
                    "automatic": None if auto is None else {"state": auto["state"], "release": auto["release"]}}

    def _frame(self, stage: str, detail: str = "") -> None:
        """A progress frame: the update's, which the page reads while it is ``working``, and an automatic
        update's, kept with it until it switches (or a click makes it the click's)."""
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

    def start(self, server: Any) -> dict[str, Any]:
        """The update started for the engine whose HTTP server is ``server`` (its port, and its drain:
        ``server.retire``), unless one runs or has handed over; its state. The feed is read with no lock
        held (``updates.newest``, a few seconds at most): the page's reads of the state never wait on it."""
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
        target = updates.newest()
        with self.lock:
            if target is None:
                self.state = {"state": "idle", "target": None, "progress": None, "error": None}
                return dict(self.state)
            self.state = {**self.state, "target": target}
            self.thread = threading.Thread(target=self._run, args=(target, server), name="cadgen-update", daemon=True)
            self.thread.start()
            return dict(self.state)

    def _failed(self, error: str) -> None:
        with self.lock:
            self.state = {**self.state, "state": "failed", "error": error}
            self.failed_at = time.monotonic()

    def recall(self) -> None:
        """As the engine starts serving: a switch that failed moments ago (``switch.failed_lately``) is this
        engine's update, failed -- the release before's engine, started again by that switch, is this one --
        so a page that followed the update through the restart reads ``failed``, its target and why, until
        the next click, as it would for a failure in the engine's own process."""
        from cad_server._internal import switch

        found = switch.failed_lately(RECALL_SECONDS)
        if found is None:
            return
        with self.lock:
            if self.state["state"] == "idle":
                self.state = {"state": "failed", "target": found.get("to"), "progress": None,
                              "error": str(found["error"])}
                self.failed_at = time.monotonic()
        try:
            from cad_server import auto_updates

            last = auto_updates.attempted()
            if last is not None and last["release"] == found.get("to") and not last.get("error"):
                auto_updates.attempt(last["release"], error=str(found["error"]))  # an automatic one's switch
        except Exception:  # noqa: BLE001 - a note for `cad status`, never a reason the engine does not serve
            pass

    def _run(self, target: str, server: Any) -> None:
        from cad_server._internal import base, releases

        try:
            self._frame("install", f"text-to-cad {target}")
            made = releases.make(target, told=lambda _line: None)
            self._frame("build123d")
            self._switch_to(target, made["cadgen"], port=getattr(server, "port", None), retire=server.retire)
        except base.Refused as refused:
            self._failed(str(refused))
        except Exception as error:  # noqa: BLE001 - an update that cannot go on leaves the engine as it was
            self._failed(f"{type(error).__name__}: {error}")

    def _switch_to(self, target: str, command: str, *, port: int | None, retire: Callable[..., None]) -> None:
        """The second half of an update, its release's folder made: that release's setup, whole (its
        base, the apps' plugins), then the engine's drain (``retire``), the switch's helper started as
        it exits. A setup that fails ends it, said in its one line, the engine as it was."""
        from cad_server._internal import installations, switch

        code, said = self._setup(command)
        if code != 0:
            self._failed(said or f"text-to-cad {target}'s setup failed (exit status {code})")
            return
        self._frame("restart")
        with self.lock:
            self.state = {**self.state, "state": "restarting"}
        previous = installations.current_version()
        retire(lambda: switch.spawn(target, port=port, previous=previous))

    # --- the automatic update ------------------------------------------------------------------------

    def automatic(self, engine: Any) -> str | None:
        """The engine's own update, asked for as it tends itself (``Daemon.tend``): when automatic
        updates are on (``auto_updates.enabled``) and a release newer than this one is known --
        the feed as last read, read again in the background when an hour has passed, or an agent
        app's newer server (``updates.notice``) -- and nothing stands in its way: no update running
        or getting ready, none failed in the last ``RECALL_SECONDS``, no drain, no ``cad setup``
        holding the install lock, and that release not tried by itself in the last day
        (``auto_updates.due``). Then it gets ready in the background (``_automatic``): the release
        it moves to, or None. ``engine`` is the daemon (``working``, ``worked``, ``draining``,
        ``stopping``, ``drain`` and its ``server``'s port). Never raises; never waits on the network."""
        from cad_server import auto_updates, updates

        try:
            if not auto_updates.enabled():
                return None
            updates.refresh()  # due: read in the background, for the next tend; this one goes by what it knows
            found = updates.notice()
            if found is None:
                return None
            target = found["latest"]
            with self.lock:
                if self.auto is not None or self.state["state"] in ("working", "restarting"):
                    return None
                if self.state["state"] == "failed" and time.monotonic() - self.failed_at < RECALL_SECONDS:
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
                self.thread = threading.Thread(target=self._automatic, args=(target, engine),
                                               name="cadgen-update-automatic", daemon=True)
            auto_updates.attempt(target)
            self.thread.start()
            return target
        except Exception:  # noqa: BLE001 - the engine's tending never fails for an update
            return None

    def _automatic(self, target: str, engine: Any) -> None:
        """An automatic update: its release's folder made and its base, now (its setup with
        ``PREPARE_ENV``); the rest -- the apps, the switch -- once the engine is idle (``_wait``), or at
        once should a click make it its own."""
        from cad_server import auto_updates
        from cad_server._internal import base, releases

        try:
            self._frame("install", f"text-to-cad {target}")
            made = releases.make(target, told=lambda _line: None)
            self._frame("build123d")
            code, said = self._setup(made["cadgen"], prepare=True)
            if code != 0:
                raise RuntimeError(said or f"text-to-cad {target}'s setup failed (exit status {code})")
            with self.lock:
                if self.auto is not None:
                    self.auto["state"] = "waiting"
            if not self._wait(engine):
                with self.lock:
                    self.auto = None
                return
            with self.lock:
                self.auto = None
            server = getattr(engine, "server", None)
            self._switch_to(target, made["cadgen"], port=getattr(server, "port", None), retire=engine.drain)
            with self.lock:
                failed = self.state["state"] == "failed" and self.state.get("error")
            if failed:
                auto_updates.attempt(target, error=str(failed))
        except Exception as error:  # noqa: BLE001 - an update that cannot go on leaves the engine as it was
            said = str(error) if isinstance(error, (base.Refused, RuntimeError)) else f"{type(error).__name__}: {error}"
            auto_updates.attempt(target, error=said)
            with self.lock:
                self.auto = None
                shown = self.urgent.is_set() or self.state["state"] == "working"
            if shown:
                self._failed(said)  # a click made it its own, or it had begun to switch: its pages say it
            else:
                with self.lock:
                    self.failed_at = time.monotonic()

    def _wait(self, engine: Any) -> bool:
        """Until the engine is idle -- nothing in flight (``working``) and none ended (``worked``) for
        ``auto_updates.IDLE_SECONDS``, no drain, no ``cad setup`` holding the install lock -- or a click
        makes the update its own: then the update is ``working``, and True. False when it is no longer
        wanted: the engine stops or drains (another update's switch among them), or the person turned
        automatic updates off (its attempt forgotten, so turning them on again goes on with it)."""
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

    def _setup(self, command: str, *, prepare: bool = False) -> tuple[int, str]:
        """The release's own ``cad setup --engine-update``, its progress frames taken as they come:
        its exit status, and the last line it said when it failed. ``prepare``: its first half alone
        (``PREPARE_ENV``), for an automatic update before the engine is idle."""
        errors: list[str] = []
        # The release runs its own cadgen: no import path of this engine's (a source tree's) goes with it.
        env = {key: value for key, value in os.environ.items()
               if key not in ("PYTHONPATH", "PYTHONHOME", PREPARE_ENV)}
        if prepare:
            env[PREPARE_ENV] = "1"
        with subprocess.Popen([command, "setup", "--engine-update"], stdin=subprocess.DEVNULL,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8",
                              errors="replace", env={**env, "PYTHONUNBUFFERED": "1"}) as process:
            reading = threading.Thread(target=lambda: errors.extend(process.stderr or ()), daemon=True)
            reading.start()
            for line in process.stdout or ():
                try:
                    said = json.loads(line)
                except ValueError:
                    continue
                frame = said.get("progress") if isinstance(said, dict) else None
                if isinstance(frame, dict) and frame.get("kind") == "update" and frame.get("stage") in STAGES:
                    self._frame(frame["stage"], str(frame.get("detail") or ""))
            code = process.wait()
            reading.join(5)
        lines = [line.strip() for line in errors if line.strip()]
        return code, lines[-1] if lines else ""


UPDATE = Update()
