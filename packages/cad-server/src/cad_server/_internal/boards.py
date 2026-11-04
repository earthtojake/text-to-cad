"""What the engine makes of a KiCad board with KiCad: its pours refilled, its DRC, its exports, each kept by
the board's bytes.

The engine holds no kicode of its own; KiCad runs in the environment of ``cad[kicad]``
(``integration_env``, made once, on first need, here in the engine: ``engine=False``), and every product
is kept by the board's key (``cad.engine.formats.kicad.poured.key``: its bytes, its project's and rules',
and the plotting code's), beside the board's document in the engine's document cache,
``<cache>/documents/<the board's document id>/kicad/<key>/`` (``poured.folder``), so a changed file is a new
key and nothing stale is ever read, and deleting the document (``cad delete``, the home's Delete) deletes
them with it:

* ``refill``: KiCad's refill of a copy's zones (``cad.kicad._refill``), which ``poured.payload`` plots the
  pours from (``CAD_KICAD_REFILL=0`` turns it off: the pours as saved, and no kicode fetched to draw a board;
  the test runner's default, but for the KiCad suite); ``payload`` is that payload, the one the CAD Viewer's board page and ``cad kicad_pcb
  snapshot`` both draw (``prepare`` keeps it before a snapshot's render process reads it).
* ``drc``: ``cad.kicad_pcb.drc`` of the saved board, the ``CheckResult`` ``cad kicad_pcb drc --json``
  prints, as data (``drc.json``).
* ``exported``: an export's download kept by its kind (``exports/<kind>/``), for the kinds a function of
  the key alone (not ``step`` and ``glb``, whose 3D models are files of their own, outside it; nor a BOM,
  whose schematic sheets are too: ``KEPT``).
* ``model``: the board in 3D for the CAD Viewer's 3D view (``cad.kicad._model``: KiCad's GLB of the body, the
  copper, silkscreen and mask, and the parts' models), gzipped, with what it holds (``model.json``: the parts
  it has a body of, and those whose model file was not found). Made in a process of its own at a low
  priority (``nice`` 10, Windows' below-normal class), which ``cancel`` kills with what it started; kept
  only while the board still has the key it was made of. Its parts' model files are read as they are when
  it is made: a model file changed alone is seen at the board's next revision.
"""

from __future__ import annotations

import gzip
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from cad._internal.atomic_replace import replace_atomic

__all__ = ["KEPT", "MODEL", "Cancelled", "drc", "exported", "keep_export", "model", "model_bytes", "model_kept",
           "payload", "prepare", "refill", "refills"]

#: The exports kept by the board's key: what reads nothing but the board, its project and its rules.
KEPT = frozenset({"gerbers", "drill", "pos", "odb", "ipc2581", "pdf", "dxf"})
_REFILL_TIMEOUT = 900
#: The 3D model's file and what it holds, beside the board's other products (``poured.folder``).
MODEL = "model.glb.gz"
_MODEL_META = "model.json"
# What the kept model was made by: a change to what it draws (``cad.kicad._model.FLAGS``) makes it again.
_MODEL_VERSION = 1
_MODEL_TIMEOUT = 900


class Cancelled(Exception):
    """A make let go of: the board changed under it, or what asked for it no longer wants it."""


def _python() -> str:
    from cad_server._internal import integration_env

    return integration_env.environment("kicad", lambda _line: None, engine=False)


def refill(board: Path, out_dir: Path) -> Path:
    """KiCad's refill of ``board``'s zones, as a copy in ``out_dir`` (``cad.kicad._refill``, run where kicode
    is): the copy's path. ``RuntimeError`` in KiCad's words when it cannot."""
    try:
        done = subprocess.run([_python(), "-P", "-m", "cad.kicad._refill", str(board), str(out_dir)],
                              stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=_REFILL_TIMEOUT,
                              check=False)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"the refill did not finish in {_REFILL_TIMEOUT} s") from None
    if done.returncode != 0:
        said = [line for line in done.stderr.splitlines() if line.strip()]
        raise RuntimeError(said[-1] if said else f"exit status {done.returncode}")
    return Path(done.stdout.strip().splitlines()[-1])


def refills() -> bool:
    """Whether a board's pours are refilled by KiCad before it is plotted: unless ``CAD_KICAD_REFILL=0``."""
    return os.environ.get("CAD_KICAD_REFILL", "").strip() != "0"


def payload(board: Path, board_key: str | None = None) -> tuple[bytes, bool]:
    """The board's plot payload (``poured.payload``) with KiCad's refill, and whether its pours are it."""
    from cad.engine.formats.kicad.poured import payload as poured

    if not refills():
        return poured(board, board_key=board_key, why="KiCad's refill is off here (CAD_KICAD_REFILL=0)")
    return poured(board, refill=refill, board_key=board_key)


def prepare(board: Path) -> None:
    """The board's refilled payload kept, for a snapshot's render process to draw (``poured.plot``)."""
    try:
        payload(Path(board))
    except (OSError, ValueError):
        pass  # the render process says what is wrong with the board, as it draws it


def drc(board: Path, board_key: str) -> dict[str, Any]:
    """KiCad's DRC of the saved board, as ``cad kicad_pcb drc --json`` prints it: kept for ``board_key``."""
    from cad.engine.formats.kicad.poured import folder

    kept = folder(board, board_key) / "drc.json"
    try:
        return json.loads(kept.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    from cad_server._internal import integration_env

    found = integration_env.call(_python(), "kicad_pcb", "drc", [str(board)], {})
    if not any(finding.get("code") in ("kicad_missing", "kicad_failed") for finding in found.get("findings") or ()):
        _write(kept, json.dumps(found, separators=(",", ":")).encode("utf-8"))
    return found


def _write(target: Path, data: bytes) -> None:
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=target.parent, prefix=".kept-", delete=False) as file:
            file.write(data)
        replace_atomic(file.name, target)
    except OSError:
        pass


def exported(board: Path, board_key: str, kind: str, filename: str) -> Path | None:
    """The download an earlier export of these bytes as ``kind`` made, kept; None for none."""
    from cad.engine.formats.kicad.poured import folder

    if kind not in KEPT:
        return None
    path = folder(board, board_key) / "exports" / kind / filename
    return path if path.is_file() else None


def keep_export(board: Path, board_key: str, kind: str, made: Path) -> None:
    """The download ``made`` kept for these bytes as ``kind``."""
    from cad.engine.formats.kicad.poured import folder

    if kind not in KEPT:
        return
    target = folder(board, board_key) / "exports" / kind / made.name
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        partial = target.with_name(f".{target.name}.part")
        shutil.copyfile(made, partial)
        replace_atomic(partial, target)
    except OSError:
        pass


def model_kept(board: Path, board_key: str) -> dict[str, Any] | None:
    """What the kept 3D model of these bytes holds (``{"modelled", "missing"}``), or None for none."""
    from cad.engine.formats.kicad.poured import folder

    kept = folder(board, board_key)
    try:
        meta = json.loads((kept / _MODEL_META).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(meta, dict) or meta.get("version") != _MODEL_VERSION or not (kept / MODEL).is_file():
        return None
    return {"modelled": list(meta.get("modelled") or ()), "missing": list(meta.get("missing") or ())}


def model_bytes(board: Path, board_key: str) -> bytes | None:
    """The kept 3D model's gzipped bytes, or None."""
    from cad.engine.formats.kicad.poured import folder

    try:
        return (folder(board, board_key) / MODEL).read_bytes()
    except OSError:
        return None


def _model_argv(python: str, board: Path, out_dir: Path) -> list[str]:
    """The command that draws ``board`` in 3D into ``out_dir``, in KiCad's environment (``cad.kicad._model``)."""
    return [python, "-P", "-m", "cad.kicad._model", str(board), str(out_dir)]


def _lowered(process: subprocess.Popen) -> None:
    """``process`` run at a low priority, and what it starts after it: the 3D view never takes the machine."""
    if sys.platform != "win32":
        try:
            os.setpriority(os.PRIO_PROCESS, process.pid, 10)
        except (AttributeError, OSError):
            pass


def _stop(process: subprocess.Popen) -> None:
    """``process`` and what it started (kicad-cli) stopped."""
    try:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(process.pid)], capture_output=True, check=False)
        else:
            os.killpg(process.pid, 9)
    except OSError:
        pass
    try:
        process.kill()
    except OSError:
        pass
    process.communicate()  # its pipes drained and closed


def model(board: Path, board_key: str, *, cancel: threading.Event | None = None,
          stage: Callable[[str], None] = lambda _stage: None) -> dict[str, Any]:
    """The board's 3D model kept for ``board_key`` (the module's ``model``), made first when it is not:
    ``{"modelled", "missing"}``. ``stage`` is told ``kicad`` while KiCad's environment is found (made, on first
    need) and ``export`` while KiCad draws it; ``cancel`` set stops the make (``Cancelled``). ``RuntimeError``
    in KiCad's words when it cannot."""
    from cad.engine.atomic_replace import put
    from cad.engine.formats.kicad.poured import folder, key, prune

    found = model_kept(board, board_key)
    if found is not None:
        return found
    cancel = cancel or threading.Event()
    stage("kicad")
    python = _python()
    if cancel.is_set():
        raise Cancelled()
    stage("export")
    flags = 0x00004000 | 0x00000200 if sys.platform == "win32" else 0  # BELOW_NORMAL_PRIORITY_CLASS, NEW_PROCESS_GROUP
    with tempfile.TemporaryDirectory(prefix="cad-model-", ignore_cleanup_errors=True) as scratch:
        process = subprocess.Popen(_model_argv(python, board, Path(scratch)),
                                   stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                   start_new_session=sys.platform != "win32", creationflags=flags)
        _lowered(process)
        deadline = time.monotonic() + _MODEL_TIMEOUT
        while True:
            try:
                out, err = process.communicate(timeout=0.25)
                break
            except subprocess.TimeoutExpired:
                if cancel.is_set() or time.monotonic() > deadline:
                    _stop(process)
                    if cancel.is_set():
                        raise Cancelled() from None
                    raise RuntimeError(f"KiCad did not draw the board in 3D in {_MODEL_TIMEOUT} s") from None
        if process.returncode != 0:
            said = [line for line in (err or "").splitlines() if line.strip()]
            raise RuntimeError(said[-1] if said else f"exit status {process.returncode}")
        made = json.loads(out.strip().splitlines()[-1])
        data = Path(made["glb"]).read_bytes()
    # A model of bytes the board no longer has is nobody's: never kept (it would prune the new key's folder).
    if cancel.is_set() or key(board) != board_key:
        raise Cancelled()
    found = {"modelled": list(made.get("modelled") or ()), "missing": list(made.get("missing") or ())}
    kept = folder(board, board_key)
    try:
        kept.mkdir(parents=True, exist_ok=True)
        put(kept / MODEL, lambda staged: staged.write_bytes(gzip.compress(data, 1, mtime=0)), compare=False)
        _write(kept / _MODEL_META, json.dumps({"version": _MODEL_VERSION, **found}).encode("utf-8"))
    except OSError:
        return found  # a cache that cannot be written: made again next time
    prune(kept)
    return found
