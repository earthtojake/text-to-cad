"""A harness's bill of materials: WireViz's own, as CSV.

WireViz lists a harness document's parts (``wireviz --format t``): each
connector housing by type, subtype and pin count; every additional component
(a crimp terminal per populated pin, a seal, a sleeve); each jacketed cable by
wire count, gauge and length; and, for loose wires (``category: bundle``), each
wire by gauge and colour with its length -- grouped, with designators and the
part numbers the document gives. This module stages the document's bytes, asks
WireViz for that list and writes it as CSV, so ``@harness(bom=True)`` and
``cadgen harness bom`` on a saved ``.harness.yml`` cannot write different bytes.
It needs WireViz, not Graphviz: a list is not a drawing.
"""

from __future__ import annotations

import csv
import io

__all__ = ["harness_bom"]


def harness_bom(document: bytes, *, label: str = "the harness", install=None) -> bytes:
    """The BOM of a harness document's bytes, as CSV (UTF-8, one row per line)."""
    from cadgen.wireviz.cli import WirevizRunError, run_wireviz
    from cadgen.wireviz.install import find_wireviz

    install = install or find_wireviz(dot=False)
    try:
        written = run_wireviz(install, document, formats="t", name="harness")
    except WirevizRunError as error:
        raise RuntimeError(f"WireViz could not list the parts of {label}: {error}") from None
    table = written.get("harness.bom.tsv")
    if table is None:
        raise RuntimeError(f"WireViz wrote no bill of materials for {label}")
    rows = [line.split("\t") for line in table.decode("utf-8").splitlines() if line.strip()]
    buffer = io.StringIO()
    csv.writer(buffer, lineterminator="\n").writerows([cell.strip() for cell in row] for row in rows)
    return buffer.getvalue().encode("utf-8")
