"""Fabrication, assembly and 3D exports of a saved board, by KiCad's own command line, headless, in private homes.

``export(board, to, out_dir)`` runs ``kicad-cli`` for one of a fixed list (``EXPORTS``) with the finder and
the private environment DRC uses (``_program.ready``, ``_program.private_run``), and returns the files it
wrote. The board is read, never rewritten. What each writes into ``out_dir``:

============  ===========================================================================================
``gerbers``   every plot layer the board's own plot settings choose, one file a layer and a job file
``drill``     Excellon drill files in millimetres
``pos``       ``<board>-pos.csv``: the placement of both sides, CSV, millimetres
``bom``       ``<board>-bom.csv``: from the schematic beside the board (``<board>.kicad_sch``), grouped
              by value and footprint, Do-Not-Populate parts left out; columns ``Reference`` (every
              designator, comma-separated, no ranges), ``Value``, ``Footprint``, ``Quantity``, then
              ``MPN`` and ``LCSC`` where any part carries one (``BOM_FIELDS``' spellings)
``step``      ``<board>.step``: the board and its parts, STEP models substituted for VRML ones
``glb``       ``<board>.glb``: the same, as binary glTF
``odb``       ``<board>-odb.zip``: ODB++, zipped, millimetres
``ipc2581``   ``<board>-ipc2581.xml``: IPC-2581 revision C, millimetres
``pdf``       ``<board>-front.pdf`` and ``<board>-back.pdf`` (mirrored, as seen from below): one page a side,
              ``PDF_LAYERS`` -- its copper, silkscreen and fabrication layers over the outline
``dxf``       ``<board>-outline.dxf``: Edge.Cuts and every drilled hole, millimetres, for an enclosure
============  ===========================================================================================

A STEP or GLB written without some of its parts' 3D models (a model file not found -- kicode carries none
of KiCad's libraries -- or, for a STEP, a model only in VRML) is written, with a warning naming them;
kicad-cli calls it an error. A BOM needs a schematic, and KiCad's schematic support (kicode-sch): without
either it is refused in one line.
"""

from __future__ import annotations

import csv
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

from ._program import KicadRunError, private_run, project_as_found, ready
from ._program import quiet as _quiet

__all__ = ["BOM_FIELDS", "EXPORTS", "FOLDERS", "PDF_LAYERS", "commands", "export", "missing_parts"]

#: What can be exported, in the order they are listed to a person.
EXPORTS = ("gerbers", "drill", "pos", "bom", "step", "glb", "odb", "ipc2581", "pdf", "dxf")
#: The exports that write a folder of files (the CAD Viewer zips them); every other writes one file (a PDF two).
FOLDERS = ("gerbers", "drill")
#: Each PDF page's layers, by side: the copper, silkscreen and fabrication drawing over the outline.
PDF_LAYERS = {"front": ("F.Cu", "F.Silkscreen", "F.Fab", "Edge.Cuts"),
              "back": ("B.Cu", "B.Silkscreen", "B.Fab", "Edge.Cuts")}
#: The BOM's part-number columns and the symbol fields each is read from, the first a part carries.
BOM_FIELDS = {"MPN": ("MPN", "Manufacturer_Part_Number", "Manufacturer Part Number", "MFR Part Number"),
              "LCSC": ("LCSC", "LCSC Part", "LCSC Part #", "LCSC_Part", "JLCPCB Part #")}
_BOM_COLUMNS = ("Reference", "Value", "Footprint", "Quantity")

_TIMEOUT_SECONDS = 600


def _unknown(to: str) -> ValueError:
    return ValueError(f"cannot export {to!r}: choose one of {', '.join(EXPORTS)}")


def schematic_of(board: Path) -> Path:
    """The schematic a board's BOM is read from: the project's root sheet beside it, ``<board>.kicad_sch``."""
    return board.with_suffix(".kicad_sch")


def commands(cli: Path, board: Path, to: str, out_dir: Path, scratch: Path | None = None) -> list[list[str]]:
    """The ``kicad-cli`` command line(s) that export ``board`` as ``to`` into ``out_dir`` (a BOM is written
    into ``scratch`` first, then rewritten into ``out_dir``: ``_bom``)."""
    if to not in EXPORTS:
        raise _unknown(to)
    pcb = [str(cli), "pcb", "export", to]
    # A directory output ends in a separator, as kicad-cli reads it: the folder, not a file's name.
    folder = os.path.join(out_dir, "")
    stem = board.stem
    if to == "gerbers":
        return [[*pcb, "--board-plot-params", "-o", folder, str(board)]]
    if to == "drill":
        return [[*pcb, "--format", "excellon", "--excellon-units", "mm", "-o", folder, str(board)]]
    if to == "pos":
        return [[*pcb, "--format", "csv", "--units", "mm", "--side", "both", "-o", str(out_dir / f"{stem}-pos.csv"),
                 str(board)]]
    if to == "bom":
        fields = [*("Reference", "Value", "Footprint", "${QUANTITY}"), *(name for names in BOM_FIELDS.values()
                                                                       for name in names)]
        return [[str(cli), "sch", "export", "bom", "--fields", ",".join(fields), "--labels", ",".join(fields),
                 "--group-by", "Value,Footprint", "--ref-range-delimiter", "", "--exclude-dnp",
                 "-o", str((scratch or out_dir) / f"{stem}-bom-kicad.csv"), str(schematic_of(board))]]
    if to in ("step", "glb"):
        return [[*pcb, "--subst-models", "--force", "-o", str(out_dir / f"{stem}.{to}"), str(board)]]
    if to == "odb":
        return [[*pcb, "--units", "mm", "--compression", "zip", "-o", str(out_dir / f"{stem}-odb.zip"), str(board)]]
    if to == "ipc2581":
        return [[*pcb, "--units", "mm", "--version", "C", "-o", str(out_dir / f"{stem}-ipc2581.xml"), str(board)]]
    if to == "pdf":
        return [[*pcb, "--mode-single", "--layers", ",".join(layers), *(["--mirror"] if side == "back" else []),
                 "-o", str(out_dir / f"{stem}-{side}.pdf"), str(board)] for side, layers in PDF_LAYERS.items()]
    return [[*pcb, "--mode-single", "--output-units", "mm", "--layers", "Edge.Cuts", "--drill-shape-opt", "2",
             "-o", str(out_dir / f"{stem}-outline.dxf"), str(board)]]


def _model_file(to: str, board: Path, out_dir: Path) -> Path | None:
    """The 3D file a ``step`` or ``glb`` export writes; None for the others."""
    return out_dir / f"{board.stem}.{to}" if to in ("step", "glb") else None


def _step_written(to: str, completed: subprocess.CompletedProcess, step: Path) -> bool:
    """Whether kicad-cli wrote the STEP (or GLB) although it exited 2, its catch-all status: KiCad's 3D
    exporter reports a model it cannot add as an error (one only in VRML, which a STEP cannot hold, always;
    a file not found on some boards), keeps going, writes the file, says ``STEP file '<path>' created.``
    (``Binary GLTF file ...``) and then exits 2 because an error was reported. A real failure (a write
    error, an OpenCASCADE exception, memory) returns before that line, which KiCad never translates."""
    said = f"{completed.stdout}\n{completed.stderr}"
    return (to in ("step", "glb") and completed.returncode == 2 and f"file '{step}' created." in said
            and step.is_file())


def missing_parts(said: str) -> list[str]:
    """The references of the parts kicad-cli said it could add no 3D model for (``Could not add 3D model for
    R1.``: the model file was not found), once each, in reference order (``C2`` before ``C10``)."""
    return sorted(set(re.findall(r"Could not add 3D model for (\S+?)\.$", said, re.MULTILINE)),
                  key=lambda ref: (re.sub(r"\d+", "", ref), int(re.sub(r"\D", "", ref) or 0)))


def _missing_models(to: str, completed: subprocess.CompletedProcess, step: Path) -> str | None:
    """The warning for the parts a written STEP or GLB holds no body of -- a model file not found, or a
    model only in VRML -- whatever kicad-cli's exit status (0 when every model was only not found); else
    None."""
    if to not in ("step", "glb") or not step.is_file():
        return None
    said = f"{completed.stdout}\n{completed.stderr}"
    parts = missing_parts(said)
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


def _bom_ready(board: Path, cli: Path) -> None:
    """A BOM's schematic is there and this kicad-cli reads schematics, else ``KicadRunError`` in one line."""
    from ._program import _is_packaged, _kicode

    schematic = schematic_of(board)
    if not schematic.is_file():
        raise KicadRunError(f"a BOM is read from the board's schematic, and there is no {schematic.name} beside "
                            f"{board.name}")
    kicode = _kicode()
    if kicode is not None and _is_packaged(cli) and not kicode.has_schematic():
        raise KicadRunError("a BOM reads the schematic, which needs KiCad's schematic support, kicode-sch: "
                            "install cad[kicad] again (it brings kicode-sch)")


def _bom(raw: Path, out: Path) -> Path:
    """kicad-cli's BOM (every field ``commands`` asked for) as ours: the fixed columns, then each of
    ``BOM_FIELDS`` that any row carries, read from the first of its spellings that is filled."""
    with raw.open(newline="", encoding="utf-8-sig") as file:
        rows = list(csv.reader(file))
    if not rows:
        raise KicadRunError("kicad-cli sch export bom wrote an empty BOM")
    header, body = rows[0], rows[1:]
    where = {name: index for index, name in enumerate(header)}
    numbers = {column: [next((row[where[name]] for name in names if name in where and row[where[name]].strip()), "")
                        for row in body] for column, names in BOM_FIELDS.items()}
    extra = [column for column, values in numbers.items() if any(values)]
    fixed = [where.get(name, -1) for name in ("Reference", "Value", "Footprint", "${QUANTITY}")]
    with out.open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow([*_BOM_COLUMNS, *extra])
        for index, row in enumerate(body):
            writer.writerow([row[column] if column >= 0 else "" for column in fixed]
                            + [numbers[column][index] for column in extra])
    return out


def export(board: Path, to: str, out_dir: Path, *, cli: Path | None = None, timeout: float = _TIMEOUT_SECONDS,
           warn: Callable[[str], None] | None = None) -> list[Path]:
    """Export the saved ``board`` as ``to`` (one of :data:`EXPORTS`) into ``out_dir``, made if missing,
    and return the files the run wrote or changed there, sorted. ``cli`` defaults to the ``kicad-cli``
    that :func:`~cad.kicad._program.ready` finds; what is said beside (a part without its 3D model) goes to
    ``warn``, else stderr. Raises :class:`KicadRunError` when ``kicad-cli`` cannot run or refuses the board,
    and :class:`KicadMissingError` when there is none."""
    if to not in EXPORTS:
        raise _unknown(to)
    board = Path(board).resolve()
    out_dir = Path(out_dir).resolve()
    say = warn or (lambda line: print(f"warning: {line}", file=sys.stderr))
    if board.suffix.lower() != ".kicad_pcb" or not board.is_file():
        raise KicadRunError(f"{board} is not a saved KiCad board (.kicad_pcb)")
    if cli is None:
        cli = ready()
    if to == "bom":
        _bom_ready(board, cli)
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise KicadRunError(f"cannot write the {to} into {out_dir}: {error.strerror or error}") from None
    what = "sch export bom" if to == "bom" else f"pcb export {to}"
    before = _listing(out_dir)
    with private_run("cad-export-", cli) as (scratch, env), project_as_found(board):
        for command in commands(cli, board, to, out_dir, scratch):
            try:
                completed = subprocess.run(command, env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                                           timeout=timeout, check=False)
            except subprocess.TimeoutExpired:
                raise KicadRunError(f"kicad-cli {what} did not finish in {timeout:g} s") from None
            except OSError as error:
                raise KicadRunError(f"kicad-cli could not be started ({error})") from None
            model = _model_file(to, board, out_dir)
            if completed.returncode != 0 and not (model and _step_written(to, completed, model)):
                said = _quiet(completed.stderr) or _quiet(completed.stdout) or f"exit status {completed.returncode}"
                raise KicadRunError(f"kicad-cli {what} failed on {board}: {said}")
            warning = _missing_models(to, completed, model) if model else None
            if warning is not None:
                say(warning)
        if to == "bom":
            raw = scratch / f"{board.stem}-bom-kicad.csv"
            if not raw.is_file():
                raise KicadRunError(f"kicad-cli sch export bom wrote no BOM for {schematic_of(board).name}")
            _bom(raw, out_dir / f"{board.stem}-bom.csv")
    after = _listing(out_dir)
    written = sorted(path for path, stamp in after.items() if before.get(path) != stamp)
    if not written:
        raise KicadRunError(f"kicad-cli {what} wrote no file for {board}")
    if to == "gerbers" and not any("edge_cuts" in path.stem.lower() or path.suffix.lower() == ".gm1" for path in written):
        # The board's own plot settings choose the layers (--board-plot-params); a fab needs the outline.
        say(f"the gerbers of {board.name} have no board outline (Edge.Cuts): the board's plot settings leave it out")
    return written
