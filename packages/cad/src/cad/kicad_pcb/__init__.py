"""``cad.kicad_pcb``: the KiCad PCB document type (``cad.registry``), a saved KiCad board.

A ``.kicad_pcb`` is an AUTHORED file, edited in KiCad or as text, never a document a model makes. Its
decorator, ``@kicad_pcb("board.kicad_pcb")``, declares a board script that edits that saved board through
KiCad's IPC API (the ``kicad`` integration's producer, ``cad.kicad._session``; a ``@step`` stacked on it
writes the saved board's STEP), never a model. Its functions take paths and our own board objects, so
they are the type's, not the ``kicad`` integration's (the signature rule):

* :func:`read` parses the file and the ``.kicad_pro`` beside it with the standard library
  (:mod:`cad.engine.formats.kicad`), so a check script run with ``cad run`` imports it without the
  CAD kernel and without KiCad; :func:`inside` is the even-odd test a check measures a pour or an
  outline with, in the same millimetres.
* :func:`inspect` is the board in one look as plain data -- its format, thickness, size, layers, parts
  and nets -- what ``cad kicad_pcb inspect`` prints; ``snapshot`` draws it flat, as ``cad kicad_pcb
  snapshot`` does.
* :func:`drc` (KiCad's design rule check) and :func:`export` (its fabrication, assembly and 3D outputs)
  run KiCad's own ``kicad-cli``, the ``kicad`` integration's (kicode, ``cad[kicad]``): they are the
  commands ``cad kicad_pcb drc`` and ``cad kicad_pcb export``, one to one. Where this environment lacks
  kicode, the command runs them in the environment of ``cad[kicad]`` the engine makes on first need; a
  function called here says to install the extra (or run the script with ``cad run``, which does).
"""

from __future__ import annotations

from pathlib import Path

from cad.engine.formats.kicad.board_index import read_board as read
from cad.engine.formats.kicad.geometry import inside
from cad.results import CheckResult, ExportResult

__all__ = ["drc", "export", "inside", "inspect", "read"]


def inspect(path: Path | str) -> dict:
    """What the board at ``path`` holds, as plain data: ``file``, ``format``, ``thickness``, ``size``,
    ``layers``, ``parts``, ``nets`` and ``counts`` (``cad kicad_pcb inspect``)."""
    from cad.engine.formats.kicad.summary import inspect_board

    return inspect_board(path)


def drc(board: Path) -> CheckResult:
    """Check the KiCad board BOARD with KiCad's design rule check.

    Runs ``kicad-cli pcb drc`` on the saved file with every severity reported
    and lists each violation and unconnected item with where it is (millimetres
    from the board's origin). The board fails when any error-severity violation
    or any unconnected item exists; warnings are reported and do not fail it.
    The result's ``measurements["drc"]`` is every finding as KiCad reported it,
    each item with its uuid and position.

    board: the .kicad_pcb to check (its .kicad_pro beside it carries the rules).
    """
    from cad.kicad._check import check

    return check(Path(board))


def export(board: Path | str, to: str, out: Path | str) -> ExportResult:
    """KiCad's ``to`` export of the saved ``board`` into the folder ``out`` (``cad kicad_pcb export BOARD
    --to KIND -o DIR``): ``to`` is one of ``gerbers``, ``drill``, ``pos``, ``bom``, ``step``, ``glb``,
    ``odb``, ``ipc2581``, ``pdf`` and ``dxf`` (``cad.kicad._export``'s table says what each writes). The
    result says the files written and any warning. ``RuntimeError`` in KiCad's words when it fails."""
    from cad.kicad._export import export as run

    said: list[str] = []
    source = Path(board).expanduser()
    written = run(source, str(to), Path(out).expanduser(), warn=said.append)
    return ExportResult(path=source.resolve(), to=str(to), written=tuple(written), warnings=tuple(said))


from cad._internal.document_type import bind as _bind  # noqa: E402

_bind(__name__)
