"""``GET /api/v1/documents/scad/<id>/mesh``: an OpenSCAD program's mesh, rendered by OpenSCAD off the request and
kept by the program's bytes.

The program is the document's file, by its absolute path (``http_app`` resolves the id): a path that is not
absolute, or not a ``.scad``, is 400, a missing file 404. The answer is the binary STL OpenSCAD rendered of
the program (``model/stl``), made once per key (``cad_server._internal.scads``: the program's bytes, every
file OpenSCAD read beside it, OpenSCAD's version and the render code's) and kept on disk under the program's
document in the engine's document cache, so a saved edit to the program or to a library it includes is the
next answer's new key, and the same bytes are served again without OpenSCAD. The ``source`` route stays the
program's own text.

A mesh not rendered yet is rendered off the request, one render per key at a time (every request for that key
joins it): a request waits on it as long as ``hold_seconds``, then answers 202 ``{"state": "rendering",
"retryMs"}`` and is asked again; OpenSCAD never runs on a request's thread. Each 200 carries ``etag:
"<key>"``; a request naming it (``If-None-Match``) is answered 304. What is held in memory is held by key, at
most ``HELD`` answers, and a held mesh is served only while its file is there: one deleted (``cad delete``, a
cleared cache) is rendered again. A program OpenSCAD refuses is 400 saying why, in OpenSCAD's words (a 2D
program among them), held until the program changes: its own fault. OpenSCAD not running, or not finishing in
time, is 503 and held by no one: the next request asks again; a computer with no OpenSCAD is 503 with the
install hint, asked again too, so installing it is enough. A program's key is worked out again whenever the
stamp of the program or of a recorded include (``mtime_ns``, size, inode) differs; the stamps and the
includes are remembered per program, at most ``HELD`` programs, and forgotten after a render, whose includes
are the next lookup's.
"""

from __future__ import annotations

import os
import threading
from collections import OrderedDict
from pathlib import Path
from typing import Any, Callable

from .backend import absolute_path
from .scanner import node_basename

__all__ = ["HELD", "HOLD_SECONDS", "ScadAnswers", "resolve_scad_path"]

# How long a request waits on a render before it answers 202; the answers and the keys kept in memory.
HOLD_SECONDS = 8.0
HELD = 16
_STATE = "rendering"
_INSTALL = "install OpenSCAD, then open the program again"
_AGAIN = "ask for the mesh again; OpenSCAD did not finish this time"


def resolve_scad_path(file_ref) -> str | None:
    """The program's absolute path, or None for a file that is not there; a path that is not absolute, or not a
    ``.scad``, is refused by name."""
    text = str(file_ref or "")
    if not text or not Path(text).is_absolute():
        raise ValueError("a program's mesh is read by the absolute path of a .scad file")
    if not text.lower().endswith(".scad"):
        raise ValueError(f"a program's mesh is a .scad's; {node_basename(text)} is not one")
    candidate = absolute_path(text)
    return candidate if os.path.isfile(candidate) else None


class _Work:
    __slots__ = ("done", "status", "body", "key")

    def __init__(self, key: str) -> None:
        self.done = threading.Event()
        self.status = 500
        self.body: Any = {"error": "the program's render stopped before it finished"}
        self.key = key


class _Known:
    """A program's key as last worked out: OpenSCAD's version, the stamps of the program and its includes, the
    includes themselves (so a poll stats them without reading the record again), and the key."""

    __slots__ = ("version", "stamp", "includes", "key")

    def __init__(self, version: str, stamp: tuple, includes: list[str], key: str) -> None:
        self.version, self.stamp, self.includes, self.key = version, stamp, includes, key


def _stamps(files: list[str]) -> tuple:
    stats = []
    for file in files:
        try:
            info = os.stat(file)
            stats.append((file, info.st_ino, info.st_size, info.st_mtime_ns))
        except OSError:
            stats.append((file, 0, -1, 0))
    return tuple(stats)


class ScadAnswers:
    """The mesh route's work, off the request, and the answers it made (see the module)."""

    def __init__(self, *, hold_seconds: float = HOLD_SECONDS, retry_ms: int = 0, on_crash=None,
                 render: Callable[[Path], tuple[Path, str]] | None = None, version: Callable[[], str] | None = None) -> None:
        self.hold_seconds = hold_seconds
        self.retry_ms = retry_ms
        self._on_crash = on_crash
        # ``render`` stands in for OpenSCAD's in a test (the kept STL and its key); the engine's is
        # ``scads.rendered``. ``version`` the OpenSCAD found, asked once per key lookup.
        self._render = render
        self._version = version
        self._lock = threading.Lock()
        self._work: dict[str, _Work] = {}
        self._held: OrderedDict[str, _Work] = OrderedDict()
        self._keys: OrderedDict[str, _Known] = OrderedDict()

    def _openscad(self) -> str:
        """The OpenSCAD this computer has, its version checked (``_program.ready``), or ``OpenscadMissing``."""
        if self._version is not None:
            return self._version()
        from cad.openscad._program import ready

        return ready()[1]

    def key(self, path: str) -> str:
        """The program's key (``scads.key``), worked out again when its stamp or a recorded include's changes."""
        from cad_server._internal import scads

        version = self._openscad()
        with self._lock:
            known = self._keys.get(path)
        if known is not None and known.version == version and _stamps([path, *known.includes]) == known.stamp:
            with self._lock:
                self._keys.move_to_end(path)
            return known.key
        includes = [str(item) for item in scads.includes(path)]
        found = _Known(version, _stamps([path, *includes]), includes, scads.key(path, version))
        with self._lock:
            self._keys[path] = found
            self._keys.move_to_end(path)
            while len(self._keys) > HELD:
                self._keys.popitem(last=False)
        return found.key

    def _forget(self, path: str) -> None:
        """A render changed what the program's includes are: the next lookup reads the record anew."""
        with self._lock:
            self._keys.pop(path, None)

    def response(self, file_ref, *, if_none_match: str = "") -> tuple[int, Any, str]:
        """``(status, body, key)``: the kept STL's path at 200, 304 for the key the client named, 202 while it
        is rendered, or a JSON error dict (400 in OpenSCAD's words, 404, 503 with no OpenSCAD or none that ran)."""
        from cad.openscad._program import OpenscadMissing

        candidate = resolve_scad_path(file_ref)
        if candidate is None:
            return 404, {"error": "Not found"}, ""
        try:
            program_key = self.key(candidate)
        except OpenscadMissing as error:
            return 503, {"error": str(error), "hint": _INSTALL}, ""
        except OSError as error:
            return 400, {"error": f"{node_basename(candidate)} could not be read ({error}); "
                                  "check that it is a file this user may read"}, ""
        named = (if_none_match or "").strip()

        def current(*keys: str) -> bool:
            return bool(named) and any(named in (f'"{key}"', f'W/"{key}"') for key in keys)

        with self._lock:
            work = self._held.get(program_key)
            if work is not None and work.status == 200 and not Path(work.body).is_file():
                # The kept mesh is gone (cad delete, a cleared cache): rendered again, never a 404 for its key.
                for slot in [slot for slot, held in self._held.items() if held is work]:
                    del self._held[slot]
                work = None
            if work is not None:
                self._held.move_to_end(program_key)
                # The key the client holds is the render's (the etag it was answered), which the lookup's
                # equals once the render's includes are recorded; either names the mesh it has.
                if work.status == 200 and current(program_key, work.key):
                    return 304, b"", work.key
                return work.status, work.body, work.key
        if current(program_key):
            return 304, b"", program_key
        with self._lock:
            work = self._work.get(program_key)
            if work is None:
                work = self._work[program_key] = _Work(program_key)
                threading.Thread(target=self._make, args=(work, program_key, Path(candidate)), name="cad-scad-mesh",
                                 daemon=True).start()
        if work.done.wait(self.hold_seconds):
            return work.status, work.body, work.key
        return 202, {"state": _STATE, "retryMs": self.retry_ms}, program_key

    def _make(self, work: _Work, program_key: str, program: Path) -> None:
        from cad.openscad._program import OpenscadMissing
        from cad.openscad._render import ProgramRefused, RenderError

        keep = False
        try:
            if self._render is not None:
                mesh, actual = self._render(program)
            else:
                from cad_server._internal import scads

                mesh, actual = scads.rendered(program, self._openscad())
            work.status, work.body, work.key, keep = 200, Path(mesh), actual, True
            self._forget(str(program))  # the render's includes are the next lookup's
        except ProgramRefused as error:
            work.status, work.body, keep = 400, {"error": str(error)}, True  # the program's own fault: the same until it changes
        except FileNotFoundError as error:
            work.status, work.body = 404, {"error": str(error)}
        except RenderError as error:  # OpenSCAD did not run or finish: no fault of the program's, asked again
            work.status, work.body = 503, {"error": str(error), "hint": _AGAIN}
        except OpenscadMissing as error:
            work.status, work.body = 503, {"error": str(error), "hint": _INSTALL}
        except Exception as error:  # noqa: BLE001 - a crash is reported once; the request is answered, never hung
            work.status, work.body = 500, {"error": f"{type(error).__name__}: {error}"}
            if self._on_crash is not None:
                self._on_crash(error)
        finally:
            with self._lock:
                self._work.pop(program_key, None)
                if keep:
                    # Held under the key the render found too: the next lookup, its includes recorded, names it.
                    for slot in {program_key, work.key}:
                        self._held[slot] = work
                        self._held.move_to_end(slot)
                    while len(self._held) > HELD:
                        self._held.popitem(last=False)
            work.done.set()
