"""Manufacturing and 3D exports of a saved board, by KiCad's own command line, headless, in private homes.

``export(board, to, out_dir)`` runs ``kicad-cli pcb export <to>`` for one of a fixed list --
``gerbers``, ``drill`` (Excellon, mm), ``pos`` (placement as CSV, mm) and ``step`` (3D models
substituted) -- with the finder and the private environment DRC uses (``_program.find_kicad_cli``,
``_program.private_run``), and returns the files it wrote. The board is read, never rewritten. A STEP
written without some of its parts' 3D models (missing, or VRML only) is a STEP, with a warning naming
them; kicad-cli calls it an error.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

from ._program import KicadRunError, check_version, find_kicad_cli, kicad_version, private_run, project_as_found
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


def _step_written(to: str, completed: subprocess.CompletedProcess, step: Path) -> bool:
    """Whether kicad-cli wrote the STEP although it exited 2, its catch-all status: KiCad's STEP exporter
    reports a model it cannot add as an error (one only in VRML, which a STEP cannot hold, always; a file
    not found on some boards), keeps going, writes the file, says ``STEP file '<path>' created.`` and then
    exits 2 because an error was reported. A real failure (a write error, an OpenCASCADE exception,
    memory) returns before that line, which is the one KiCad never translates."""
    said = f"{completed.stdout}\n{completed.stderr}"
    return (to == "step" and completed.returncode == 2 and f"STEP file '{step}' created." in said
            and step.is_file())


def _missing_models(to: str, completed: subprocess.CompletedProcess, step: Path) -> str | None:
    """The warning for the parts a written STEP holds no body of -- a model file not found, or a model
    only in VRML -- whatever kicad-cli's exit status (0 when every model was only not found); else None."""
    if to != "step" or not step.is_file():
        return None
    said = f"{completed.stdout}\n{completed.stderr}"
    parts = sorted(set(re.findall(r"Could not add 3D model for (\S+?)\.$", said, re.MULTILINE)),
                   key=lambda ref: (re.sub(r"\d+", "", ref), int(re.sub(r"\D", "", ref) or 0)))
    vrml = said.count("Cannot use VRML models when exporting to non-mesh formats.")
    if not parts and not vrml:
        return None
    missing = (f"{len(parts)} part{'s' if len(parts) != 1 else ''} without a 3D model ({', '.join(parts[:12])}"
               f"{', ...' if len(parts) > 12 else ''}): the model file was not found") if parts else ""
    only_vrml = f"{vrml} model{'s' if vrml != 1 else ''} only in VRML, which a STEP cannot hold" if vrml else ""
    return f"{step.name} is written, " + "; ".join(filter(None, (missing, only_vrml)))


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
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise KicadRunError(f"cannot write the {to} into {out_dir}: {error.strerror or error}") from None
    before = _listing(out_dir)
    with private_run("cad-export-") as (_scratch, env), project_as_found(board):
        for command in commands(cli, board, to, out_dir):
            try:
                completed = subprocess.run(command, env=env, capture_output=True, text=True, timeout=timeout,
                                           check=False)
            except subprocess.TimeoutExpired:
                raise KicadRunError(f"kicad-cli pcb export {to} did not finish in {timeout:g} s") from None
            except OSError as error:
                raise KicadRunError(f"kicad-cli could not be started ({error})") from None
            step = out_dir / f"{board.stem}.step"
            if completed.returncode != 0 and not _step_written(to, completed, step):
                said = _quiet(completed.stderr) or _quiet(completed.stdout) or f"exit status {completed.returncode}"
                raise KicadRunError(f"kicad-cli pcb export {to} failed on {board}: {said}")
            warning = _missing_models(to, completed, step)
            if warning is not None:
                print(f"warning: {warning}", file=sys.stderr)
    after = _listing(out_dir)
    written = sorted(path for path, stamp in after.items() if before.get(path) != stamp)
    if not written:
        raise KicadRunError(f"kicad-cli pcb export {to} wrote no file for {board}")
    if to == "gerbers" and not any("edge_cuts" in path.stem.lower() or path.suffix.lower() == ".gm1" for path in written):
        # The board's own plot settings choose the layers (--board-plot-params); a fab needs the outline.
        print(f"warning: the gerbers of {board.name} have no board outline (Edge.Cuts): the board's plot settings "
              f"leave it out", file=sys.stderr)
    return written
