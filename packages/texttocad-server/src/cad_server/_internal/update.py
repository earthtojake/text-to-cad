"""The update the engine runs when a person clicks its update button (``POST /__cad/update``).

One at a time, in the engine's own process, in the background: the request that asked for it is
answered at once, and the page or card that asked reads where it is (``GET /__cad/version``'s
``update``) until the engine goes and comes back with the new release. Nothing here starts on its
own: no fetch and no switch without that click, ``cad update`` or the install command.

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
engine stays as it was.
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from typing import Any

__all__ = ["UPDATE", "Update"]

# The stages of an update, in order, as its progress frames count them (``cad.engine.progress``).
STAGES = ("install", "build123d", "apps", "restart")


class Update:
    """The engine's update: its state, which the page and the card read, and its work."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.state: dict[str, Any] = {"state": "idle", "target": None, "progress": None, "error": None}
        self.started = 0.0
        self.thread: threading.Thread | None = None

    def snapshot(self) -> dict[str, Any]:
        """Where the update is: ``state`` (``idle``, ``working``, ``restarting``, ``failed``), the
        release it moves to (``target``), its last progress frame and, failed, why."""
        with self.lock:
            return dict(self.state)

    def _frame(self, stage: str, detail: str = "") -> None:
        from cad.engine.progress import event

        frame = event("update", stage, job=str(self.state.get("target") or ""), detail=detail,
                      done=STAGES.index(stage), total=len(STAGES),
                      elapsed_ms=int((time.monotonic() - self.started) * 1000))
        with self.lock:
            self.state["progress"] = frame

    def start(self, server: Any) -> dict[str, Any]:
        """The update started for the engine whose HTTP server is ``server`` (its port, and its drain:
        ``server.retire``), unless one runs or has handed over; its state. The feed is read with no lock
        held (``updates.newest``, a few seconds at most): the page's reads of the state never wait on it."""
        from cad_server import updates

        with self.lock:
            if self.state["state"] in ("working", "restarting"):
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

    def _run(self, target: str, server: Any) -> None:
        from cad_server._internal import base, installations, releases, switch

        try:
            self._frame("install", f"text-to-cad {target}")
            made = releases.make(target, told=lambda _line: None)
            self._frame("build123d")
            code, said = self._setup(made["cadgen"])
            if code != 0:
                self._failed(said or f"text-to-cad {target}'s setup failed (exit status {code})")
                return
            self._frame("restart")
            with self.lock:
                self.state = {**self.state, "state": "restarting"}
            previous = installations.current_version()
            port = getattr(server, "port", None)
            server.retire(lambda: switch.spawn(target, port=port, previous=previous))
        except base.Refused as refused:
            self._failed(str(refused))
        except Exception as error:  # noqa: BLE001 - an update that cannot go on leaves the engine as it was
            self._failed(f"{type(error).__name__}: {error}")

    def _setup(self, command: str) -> tuple[int, str]:
        """The release's own ``cad setup --engine-update``, its progress frames taken as they come:
        its exit status, and the last line it said when it failed."""
        errors: list[str] = []
        # The release runs its own cadgen: no import path of this engine's (a source tree's) goes with it.
        env = {key: value for key, value in os.environ.items() if key not in ("PYTHONPATH", "PYTHONHOME")}
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
