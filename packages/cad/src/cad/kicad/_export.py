"""Manufacturing and 3D exports of a saved board, by KiCad's own command line, headless, in private homes.

``export(board, to, out_dir)`` runs ``kicad-cli pcb export <to>`` for one of a fixed list --
``gerbers``, ``drill`` (Excellon, mm), ``pos`` (placement as CSV, mm) and ``step`` (3D models
substituted) -- with the finder and the private environment DRC uses (``_program.find_kicad_cli``,
``_program.private_run``), and returns the files it wrote. The board is read, never rewritten.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from ._program import KicadRunError, check_version, find_kicad_cli, kicad_version, private_run
from ._program import quiet as _quiet

__all__ = ["EXPORTS", "commands", "export"]

#: What can be exported, in the order they are listed to a person.
EXPORTS = ("gerbers", "drill", "pos", "step")

_TIMEOUT_SECONDS = 600


def commands(cli: Path, board: Path, to: str, out_dir: Path) -> list[list[str]]:
    """The ``kicad-cli`` command line(s) that export ``board`` as ``to`` into ``out_dir``.

    - ``gerbers``: every plot layer of the board, into ``out_dir`` (one file a layer and a job file).
    - ``drill``: Excellon drill files in millimetres, into ``out_dir``.
    - ``pos``: the placement of both sides as CSV in millimetres, ``out_dir/<board>-pos.csv``.
    - ``step``: the board and its components as ``out_dir/<board>.step``, STEP models substituted for
      VRML ones (``--subst-models``).
    """
    if to not in EXPORTS:
        raise ValueError(f"cannot export {to!r}: choose one of {', '.join(EXPORTS)}")
    head = [str(cli), "pcb", "export", to]
    # A directory output ends in a separator, as kicad-cli reads it: the folder, not a file's name.
    folder = os.path.join(out_dir, "")
    if to == "gerbers":
        return [[*head, "--board-plot-params", "-o", folder, str(board)]]
    if to == "drill":
        return [[*head, "--format", "excellon", "--excellon-units", "mm", "-o", folder, str(board)]]
    if to == "pos":
        return [[*head, "--format", "csv", "--units", "mm", "--side", "both",
                 "-o", str(out_dir / f"{board.stem}-pos.csv"), str(board)]]
    return [[*head, "--subst-models", "--force", "-o", str(out_dir / f"{board.stem}.step"), str(board)]]


def _listing(out_dir: Path) -> dict[Path, tuple[int, int]]:
    stamps = {}
    for path in out_dir.rglob("*"):
        if path.is_file():
            info = path.stat()
            stamps[path] = (info.st_mtime_ns, info.st_size)
    return stamps


def export(board: Path, to: str, out_dir: Path, *, cli: Path | None = None,
           timeout: float = _TIMEOUT_SECONDS) -> list[Path]:
    """Export the saved ``board`` as ``to`` (one of :data:`EXPORTS`) into ``out_dir``, made if missing,
    and return the files the run wrote or changed there, sorted. ``cli`` defaults to the ``kicad-cli``
    that :func:`~cad.kicad._program.find_kicad_cli` finds. Raises :class:`KicadRunError` when
    ``kicad-cli`` cannot run or refuses the board, and :class:`KicadMissingError` when there is none."""
    if to not in EXPORTS:
        raise ValueError(f"cannot export {to!r}: choose one of {', '.join(EXPORTS)}")
    board = Path(board).resolve()
    out_dir = Path(out_dir).resolve()
    if board.suffix.lower() != ".kicad_pcb" or not board.is_file():
        raise KicadRunError(f"{board} is not a saved KiCad board (.kicad_pcb)")
    if cli is None:
        cli = find_kicad_cli()
        check_version(cli, kicad_version(cli))
    out_dir.mkdir(parents=True, exist_ok=True)
    before = _listing(out_dir)
    with private_run("cad-export-") as (_scratch, env):
        for command in commands(cli, board, to, out_dir):
            try:
                completed = subprocess.run(command, env=env, capture_output=True, text=True, timeout=timeout,
                                           check=False)
            except subprocess.TimeoutExpired:
                raise KicadRunError(f"kicad-cli pcb export {to} did not finish in {timeout:g} s") from None
            except OSError as error:
                raise KicadRunError(f"kicad-cli could not be started ({error})") from None
            if completed.returncode != 0:
                said = _quiet(completed.stderr) or _quiet(completed.stdout) or f"exit status {completed.returncode}"
                raise KicadRunError(f"kicad-cli pcb export {to} failed on {board}: {said}")
    after = _listing(out_dir)
    written = sorted(path for path, stamp in after.items() if before.get(path) != stamp)
    if not written:
        raise KicadRunError(f"kicad-cli pcb export {to} wrote no file for {board}")
    return written
