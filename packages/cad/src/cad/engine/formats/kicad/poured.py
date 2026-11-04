"""A board's plot with its pours as KiCad fills them now: the one function the viewer and the snapshot share.

A ``.kicad_pcb`` saves its zones' fills, which go stale when an edit moves copper and nobody refills them.
So before a board is plotted, KiCad refills the zones of a temporary copy of it (``refill``: the kicad
integration's headless api-server and KiPy, ``cad.kicad._refill``, in the environment that holds kicode),
and the plot is drawn from the copy's bytes, under the board's own name and project
(``plot.build_plot(path, data)``). The person's file is never written. Without KiCad, or when the refill
fails, the board is plotted as saved and the payload says so: ``pours`` is ``{"refilled": false,
"warning": "..."}`` (``{"refilled": true}`` otherwise).

The payload is a function of what it is read from, so it is kept by that (``key``): a sha256 of the board's
bytes, its ``.kicad_pro``'s and its ``.kicad_dru``'s, and the source of the code that plots it (this
package's modules). A changed file is a new key, so nothing stale is ever read. It is kept on disk, gzipped,
in the engine's document cache beside the board's own document, under its document id (the board file's,
``ids.file_id``) and its key (``<cache>/documents/<id>/kicad/<key>/plot.json.gz``: ``folder``, ``cached``), so
deleting the document (``cad delete``, the home's Delete) deletes it too, and where the snapshot's render
process reads what the engine plotted; a plot as saved (no refill) is never kept there, so a later run with
KiCad refills it.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import tempfile
from collections.abc import Callable
from functools import cache
from pathlib import Path
from typing import Any

__all__ = ["Refill", "cached", "folder", "key", "payload", "plot", "warning_of"]

#: What refills a copy: ``refill(board, out_dir)`` writes KiCad's refill of ``board`` into ``out_dir`` and
#: answers the refilled file's path; it raises (any ``Exception``) when it cannot.
Refill = Callable[[Path, Path], Path]

_PLOT = "plot.json.gz"
# The files beside a board that what is made of it reads: its project (rules, net classes) and custom rules.
_BESIDE = (".kicad_pro", ".kicad_dru")


@cache
def _code() -> str:
    """The source of the code that plots a board, so an edit to it (a release, a checkout's change) is a new key."""
    digest = hashlib.sha256()
    for module in sorted(Path(__file__).resolve().parent.glob("*.py")):
        digest.update(module.name.encode())
        digest.update(module.read_bytes())
    return digest.hexdigest()


def key(path: Path | str, *, extra: bytes = b"") -> str:
    """The board's key: its bytes, its project's and custom rules', and the plotting code's source (with
    ``extra``, what else a caller's product reads)."""
    path = Path(path)
    digest = hashlib.sha256()
    digest.update(_code().encode())
    for file in (path, *(path.with_suffix(suffix) for suffix in _BESIDE)):
        digest.update(file.suffix.encode())
        digest.update(file.read_bytes() if file.is_file() else b"\0none")
    digest.update(extra)
    return digest.hexdigest()


def folder(path: Path | str, board_key: str) -> Path:
    """Where what is made of the board at ``path`` with ``board_key`` (``key``) is kept: under its document in
    the engine's document cache, ``<cache>/documents/<the file's document id>/kicad/<key>``, which deleting
    the document removes with it (``registry.Registry.delete``)."""
    from cad.engine.ids import file_id
    from cad.engine.places import cache_dir

    return cache_dir() / "documents" / file_id(path) / "kicad" / board_key


def cached(path: Path | str, board_key: str | None = None) -> bytes | None:
    """The refilled payload kept for the board at ``path`` (``board_key``: its key, worked out when not
    given), its JSON bytes, or None."""
    try:
        return gzip.decompress((folder(path, board_key or key(path)) / _PLOT).read_bytes())
    except (OSError, EOFError, gzip.BadGzipFile):
        return None


def _keep(path: Path, board_key: str, data: bytes) -> None:
    """``data`` kept for the board at ``path`` with ``board_key``, written whole or not at all
    (``atomic_replace.put``)."""
    from cad.engine.atomic_replace import put

    target = folder(path, board_key) / _PLOT
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        put(target, lambda staged: staged.write_bytes(gzip.compress(data, 1, mtime=0)), compare=False)
    except OSError:
        pass  # a cache that cannot be written is no cache: the payload is still answered


def _with_pours(payload: dict[str, Any], pours: dict[str, Any]) -> bytes:
    from cad.engine.formats.kicad.plot import payload_bytes

    return payload_bytes({**payload, "pours": pours})


def payload(path: Path | str, *, refill: Refill | None = None, board_key: str | None = None,
            why: str = "KiCad is not available here") -> tuple[bytes, bool]:
    """The plot payload's JSON bytes for the board at ``path`` and whether its pours are KiCad's refill:
    the one kept for its key; else, with ``refill``, KiCad's refill of a copy plotted (and kept); else the
    board as saved, its ``pours`` saying why (``why``, without a ``refill``). Raises ``PlotError`` for a
    file that is no readable board."""
    from cad.engine.formats.kicad.plot import _checked, build_plot

    path = _checked(Path(path))
    board_key = board_key or key(path)
    found = cached(path, board_key)
    if found is not None:
        return found, True
    why = f"{why}: the pours are drawn as the file saved them"
    if refill is not None:
        with tempfile.TemporaryDirectory(prefix="cad-refill-", ignore_cleanup_errors=True) as scratch:
            try:
                refilled = refill(path, Path(scratch))
                data = Path(refilled).read_bytes()
            except Exception as error:  # noqa: BLE001 - KiCad's or the environment's: said in the payload
                why = f"KiCad could not refill the pours ({str(error).strip() or type(error).__name__}): they are " \
                      f"drawn as the file saved them"
            else:
                body = _with_pours(build_plot(path, data), {"refilled": True})
                _keep(path, board_key, body)
                return body, True
    return _with_pours(build_plot(path), {"refilled": False, "warning": why}), False


def warning_of(body: bytes) -> str | None:
    """What a payload says of its pours when they are not KiCad's refill; None when they are."""
    try:
        pours = json.loads(body).get("pours") or {}
    except ValueError:
        return None
    return None if pours.get("refilled") else str(pours.get("warning") or "the pours are drawn as saved")


def plot(path: Path | str) -> dict[str, Any]:
    """The plot payload of the board at ``path`` as data, for a process that runs no KiCad (the snapshot's
    render process): the refilled one the engine kept for its key, else the board as saved (``pours`` says so)."""
    body, _refilled = payload(path)
    return json.loads(body)
