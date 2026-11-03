"""What the engine makes of a KiCad board with KiCad: its pours refilled, its DRC, its exports, each kept by
the board's bytes.

The engine holds no kicode of its own; KiCad runs in the environment of ``cad[kicad]``
(``integration_env``, made once, on first need, here in the engine: ``engine=False``), and every product
is kept by the board's key (``cad.engine.formats.kicad.poured.key``: its bytes, its project's and rules',
and the plotting code's), under ``<cache>/kicad/<key>/``, so a changed file is a new key and nothing stale
is ever read:

* ``refill``: KiCad's refill of a copy's zones (``cad.kicad._refill``), which ``poured.payload`` plots the
  pours from (``CAD_KICAD_REFILL=0`` turns it off: the pours as saved, and no kicode fetched to draw a board;
  the test runner's default, but for the KiCad suite); ``payload`` is that payload, the one the CAD Viewer's board page and ``cad kicad_pcb
  snapshot`` both draw (``prepare`` keeps it before a snapshot's render process reads it).
* ``drc``: ``cad.kicad_pcb.check`` of the saved board, the ``CheckResult`` ``cad kicad_pcb check --json``
  prints, as data (``drc.json``).
* ``exported``: an export's download kept by its kind (``exports/<kind>/``), for the kinds a function of
  the key alone (not ``step`` and ``glb``, whose 3D models are files of their own, outside it; nor a BOM,
  whose schematic sheets are too: ``KEPT``).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from cad._internal.atomic_replace import replace_atomic

__all__ = ["KEPT", "drc", "exported", "keep_export", "payload", "prepare", "refill", "refills"]

#: The exports kept by the board's key: what reads nothing but the board, its project and its rules.
KEPT = frozenset({"gerbers", "drill", "pos", "odb", "ipc2581", "pdf", "dxf"})
_REFILL_TIMEOUT = 900


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
    """KiCad's DRC of the saved board, as ``cad kicad_pcb check --json`` prints it: kept for ``board_key``."""
    from cad.engine.formats.kicad.poured import folder

    kept = folder(board_key) / "drc.json"
    try:
        return json.loads(kept.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    from cad_server._internal import integration_env

    found = integration_env.call(_python(), "kicad_pcb", "check", [str(board)], {})
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


def exported(board_key: str, kind: str, filename: str) -> Path | None:
    """The download an earlier export of these bytes as ``kind`` made, kept; None for none."""
    from cad.engine.formats.kicad.poured import folder

    if kind not in KEPT:
        return None
    path = folder(board_key) / "exports" / kind / filename
    return path if path.is_file() else None


def keep_export(board_key: str, kind: str, made: Path) -> None:
    """The download ``made`` kept for these bytes as ``kind``."""
    from cad.engine.formats.kicad.poured import folder

    if kind not in KEPT:
        return
    target = folder(board_key) / "exports" / kind / made.name
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        partial = target.with_name(f".{target.name}.part")
        shutil.copyfile(made, partial)
        replace_atomic(partial, target)
    except OSError:
        pass
