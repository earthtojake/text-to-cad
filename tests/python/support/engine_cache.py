"""An in-process build's restart as the engine has one: before the worker goes, the daemon's cache
keeps each document it holds (``cad_server.engine.cache``: its idle save, ``worker._save``'s bytes, at
``<cache>/<id>/document.xbf``), and a fresh worker takes a model from there when its key is
unchanged (``build._previous``). A test that builds with ``daemon=False`` passes the folder as
``cache=`` and calls ``keep`` where a worker would be saved: nothing of the developer's is used."""

from __future__ import annotations

from pathlib import Path


def keep(cache: Path | str) -> list[Path]:
    """Every document this process holds, written where the engine's cache keeps it, as its save
    writes it: the cache files written."""
    from cad.engine import build, worker
    from cad.engine.ids import model_id
    from cad.engine.model import _MODELS

    written = []
    for key in list(build._WRITTEN):
        script, _, name = key.rpartition("::")
        declared = _MODELS.get(key)
        ident = declared.id if declared is not None else model_id(Path(script), name)
        header, payload = worker._save({"ident": ident, "script": script, "name": name, "generation": "g"})
        if header.get("error"):
            continue
        path = Path(cache) / ident / "document.xbf"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        written.append(path)
    return written


def restart(cache: Path | str) -> None:
    """A worker gone and a fresh one in its place: what it held kept in ``cache`` first (``keep``),
    then nothing held."""
    from cad.engine import build
    from cad.engine.kernel import memo

    keep(cache)
    memo.clear()
    build._WRITTEN.clear()
    build._PARTS.clear()
    build._BUILT.clear()
