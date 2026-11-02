"""``cad.kicad_pcb``: the KiCad PCB document type (``cad.registry``), a saved KiCad board.

A ``.kicad_pcb`` is an AUTHORED file, edited in KiCad or as text, never a document a model makes, so
this type has no decorator (what would write a board from a model's code is open). Its functions take
paths and our own board objects, so they are the type's, not the ``kicad`` integration's (the signature
rule):

* :func:`read_board` parses the file and the ``.kicad_pro`` beside it with the standard library
  (:mod:`cad.engine.formats.kicad`), so a check script run with ``cad run`` imports it without the
  CAD kernel and without KiCad; :func:`inside` is the even-odd test a check measures a pour or an
  outline with, in the same millimetres.
* :func:`inspect` is the board in one look as plain data -- its format, thickness, size, layers, parts
  and nets -- what ``cad kicad_pcb inspect`` prints; ``snapshot`` draws it flat, as ``cad kicad_pcb
  snapshot`` does.
* ``check`` (KiCad's design rule check) and ``export`` (its fabrication outputs) run KiCad's own
  ``kicad-cli``, which the server finds and runs and a model's environment never does: they are the
  commands ``cad kicad_pcb check`` and ``cad kicad_pcb export``, and as functions they say so.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from cad.engine.formats.kicad.board_index import read_board
from cad.engine.formats.kicad.geometry import inside

__all__ = ["check", "export", "inside", "inspect", "read_board"]


def inspect(path: Path | str) -> dict:
    """What the board at ``path`` holds, as plain data: ``file``, ``format``, ``thickness``, ``size``,
    ``layers``, ``parts``, ``nets`` and ``counts`` (``cad kicad_pcb inspect``)."""
    from cad.engine.formats.kicad.summary import inspect_board

    return inspect_board(path)


def _runs_kicad(operation: str) -> RuntimeError:
    return RuntimeError(f"cad.kicad_pcb.{operation} runs KiCad's kicad-cli, which the CAD server runs, not a model's "
                        f"process: run the command, cad kicad_pcb {operation} BOARD (cad kicad_pcb {operation} --help)")


def check(path: Path | str, *args: Any, **options: Any) -> Any:
    """KiCad's design rule check: the server's command, ``cad kicad_pcb check BOARD``."""
    raise _runs_kicad("check")


def export(path: Path | str, *args: Any, **options: Any) -> Any:
    """KiCad's fabrication outputs: the server's command, ``cad kicad_pcb export BOARD --to KIND -o DIR``."""
    raise _runs_kicad("export")


from cad._internal.document_type import bind as _bind  # noqa: E402

_bind(__name__)
