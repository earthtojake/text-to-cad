"""The public ``harness`` namespace: the ``@harness`` decorator and the harness API.

``@harness`` DECLARES a wiring harness model; ``harness.Harness`` is what its
function builds and returns, with ``Connector``, ``Cable``, ``Wire`` and
``Pin`` its parts and ``HarnessError`` its refusals. They are the same object
-- this module is callable (see :mod:`cadgen._internal.format_namespace`) --
so ``from cadgen import harness`` gives a model script all of them.

A harness is written as one WireViz document, ``<name>.harness.yml``, after
its checks pass: a wire whose ends are on boards joins pins carrying the same
net, a pin takes one wire, every colour, gauge and length is one WireViz
reads. WireViz itself -- a separate program cadgen runs and never imports --
draws the document for the CAD Viewer and ``harness.snapshot`` (``cadgen
harness snapshot``) and lists its bill of materials (``@harness(bom=True)``,
or ``harness.bom``: ``cadgen harness bom``).

Import discipline: nothing here pulls in OCP or runs WireViz at module scope.
"""

from __future__ import annotations

from pathlib import Path

from cadgen._internal.format_namespace import callable_namespace
from cadgen._internal.snapshot_door import plot_snapshot_verb
from cadgen.results import FabExportResult

__all__ = ["Cable", "Connector", "Harness", "HarnessError", "Pin", "Wire", "bom", "snapshot"]

_DESIGN = frozenset({"Cable", "Connector", "Harness", "HarnessError", "Pin", "Wire"})

#: ``cadgen harness snapshot``'s verb: a harness document drawn as WireViz draws it, as the viewer draws it.
snapshot = plot_snapshot_verb("harness")


def bom(document: Path, out: Path | None = None, *, verbose: bool = False) -> FabExportResult:
    """Write the bill of materials (CSV) of the wiring harness DOCUMENT.

    WireViz's list of its connectors, terminals, cables and wires, grouped, with the
    part numbers the harness gives: what @harness(bom=True) writes. Needs WireViz.

    document: the .harness.yml to list.
    out: destination file. Omitted, writes the sibling <name>.bom.csv beside DOCUMENT.
    verbose: narrate the target on stderr.
    """
    from cadgen._internal.fab_door import harness_bom

    return harness_bom(document, out, verbose=verbose)


def __getattr__(name: str):
    if name in _DESIGN:
        from cadgen.wireviz import design

        return getattr(design, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


callable_namespace(__name__, "harness")
