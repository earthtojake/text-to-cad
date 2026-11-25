"""An in-process build's restart as the engine has one: each model this process built is recorded as the daemon
records it (its ``.xbf`` and that file's version as written, ``models.Models.record``), and a fresh worker takes a
model from its ``.xbf`` while the file is that version and its key unchanged (``build._previous``). A test that builds
with ``daemon=False`` calls ``restart(state)`` where a worker would go, and builds through ``build(state, ...)``, the
engine's build (``take=True``) with ``state`` as its state folder: nothing of the developer's is used."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from unittest import mock


def record(state: Path | str) -> list[str]:
    """Every model this process holds, recorded in ``state`` as the daemon records a build: the ids recorded."""
    from cad.engine import build
    from cad.engine.ids import file_id
    from cad_server.engine.registry import Registry, file_version, relative

    held = Registry(state)
    recorded = []
    for key, written in list(build._WRITTEN.items()):
        script, _, name = key.rpartition("::")
        xbf = written.declared
        version = file_version(xbf) if xbf is not None else None
        if version is None:
            continue
        root = str(Path(script).parent)
        ident = file_id(xbf)
        held.put({"id": ident, "kind": "model", "root": root, "home": relative(script, root), "entry": name,
                  "namespace": root, "name": name, "revision": "r", "built": 0.0, "saved": relative(xbf, root),
                  "version": version})
        recorded.append(ident)
    return recorded


def restart(state: Path | str) -> None:
    """A worker gone and a fresh one in its place: what it built recorded in ``state`` first (``record``), then nothing
    held."""
    from cad.engine import build
    from cad.engine.kernel import memo

    record(state)
    memo.clear()
    build._WRITTEN.clear()
    build._PARTS.clear()
    build._BUILT.clear()


def build(state: Path | str, script: Path | str, functions: list[str] | None = None, **options: Any) -> list[dict]:
    """The engine's build of ``script`` in this process (``take=True``), its records those of ``state``, and no engine
    to reach: what a fresh worker takes, it takes from a model's ``.xbf``."""
    from cad.engine import build as engine_build

    with mock.patch.dict(os.environ, {"CAD_STATE_DIR": str(state), "CAD_ENGINE_DIR": str(Path(state) / "engine")}):
        return engine_build.build(Path(script), functions, take=True, **options)


def stamp(state: Path | str, xbf: Path | str) -> None:
    """``xbf``'s record in ``state`` names the file as it is now: what the engine records of an ``.xbf`` it wrote -- a
    release's own, of another format or another writer -- so a run takes it, or says why it does not, by its bytes."""
    from cad.engine.ids import file_id
    from cad_server.engine.registry import Registry, file_version

    held = Registry(state)
    held.update(file_id(xbf), lambda record: {**record, "version": file_version(xbf)} if record else None)
