"""The engine's HTTP API, ``/api/v1``: the kinds of documents it names, and the formats each exports.

Every document the pages read is one of ``KINDS``, a lower-case word: a model's document is
``xbf``, whether the engine holds it built from code or it is its ``.xbf`` opened from disk; any other
file's is named by its extension (``FILE_KINDS``: a ``.stp`` is a ``step``). A kind is a typed collection
inside ``documents``: ``/api/v1/documents/<kind>/<id>/...`` is what a page reads of a document of that kind,
and the same id under another kind is a 404 that names the right one (``http_app``). ``model``, the kind a model
the engine holds had when it was a type of its own (0.11's pages read ``documents/model/<id>``), still answers as
``xbf``'s (``ALIASES``): its collection, its routes and its exports, for the programs that say it. What each
kind's collection answers:

* ``xbf``, ``step``: the engine's document -- ``structure``, ``parts/<key>`` (and each
  part's ``faces``/``edges``/``vertices/<ordinal>``, ``elements``, ``groups``, ``volume``), ``measure``,
  ``kinematics``, ``POST pose``, ``POST mesh``; a model built from code also ``POST parameters`` (its
  parameters set in its script, ``http_app.CadApp._parameters``) and ``POST preview``; a file (a STEP, a
  model's ``.xbf``) also its ``source``.
* ``dxf``: ``drawing`` (the 2D payload), ``source``.
* ``kicad_pcb``: ``plot`` (the board's geometry per layer, and its index), ``drc`` (KiCad's design rule
  check of it), ``source``.
* ``kicad_sch``: ``plot`` (every sheet of the schematic a page of layers, and its index), ``source``.
* ``urdf``, ``srdf``: ``structure`` (the robot resolved for the page), ``parts/<digest>``
  (a primitive's mesh), ``source``.
* ``stl``, ``glb``, ``3mf``: ``source``, which the page parses itself.
"""
from __future__ import annotations

import os

from cad.registry import ALIASES, DOCUMENT_TYPES

API = "/api/v1"

# A file's kind is its document type as the API spells it (``cad.registry``'s ``wire``: the id, but
# ``3mf`` for ``threemf``, the spelling released pages read).
FILE_KINDS = {extension: entry.wire for entry in DOCUMENT_TYPES.values() for extension in entry.extensions}
# A kind the API said once and answers still, as the kind it names now: ``model``, a model the engine holds, is ``xbf``.
KIND_ALIASES = {alias: DOCUMENT_TYPES[alias].wire for alias in ALIASES}
# Every kind a page reads (``GET /api/v1/server``'s ``reads``): each type's, an alias still answered after the kind
# it names.
KINDS = tuple(named for entry in DOCUMENT_TYPES.values()
              for named in (entry.wire, *(alias for alias, wire in KIND_ALIASES.items() if wire == entry.wire)))
# A file's format, as Open in names a file it offers (``export:<format>``) and the apps it takes: a file's kind.
FORMATS = FILE_KINDS
# The documents the engine itself serves: their structure, parts and version are its reads.
ENGINE_KINDS = frozenset(entry.wire for entry in DOCUMENT_TYPES.values() if entry.view == "document")
# A model's document: built from code and held, or its .xbf opened from disk.
XBF = DOCUMENT_TYPES["xbf"].wire
ROBOT_KINDS = frozenset(entry.wire for entry in DOCUMENT_TYPES.values() if entry.view == "robot")

# What each kind's Export offers (``packages/ui``'s ``export/formats.ts``), by its format name
# (``exports.FORMATS``); ``dxf`` only where the view draws the document flat. A KiCad board's are KiCad's
# (``cad export --to``, ``exports.BOARD``). An ``xbf`` is either a model the engine holds, which exports
# what ``EXPORTS["model"]`` lists (the key 0.11 read for it), or its ``.xbf`` opened from disk, which exports what
# ``EXPORTS["xbf"]`` lists, its own bytes as the ``original`` (``exports_of`` tells them apart).
_SOLID = ["step", "stl", "threemf", "glb", "dxf"]
EXPORTS = {"model": [*_SOLID, "xbf"], "step": [*_SOLID, "xbf"], "xbf": [*_SOLID, "original"],
           "glb": ["stl", "threemf"], "stl": ["threemf", "glb"], "3mf": ["stl", "glb"],
           "dxf": [], "urdf": [], "srdf": [],
           "kicad_pcb": ["gerbers", "drill", "pos", "bom", "step", "glb", "odb", "ipc2581", "pdf", "dxf"]}
# A KiCad schematic's are KiCad's too (``cad export --to``, ``exports.SCHEMATIC``).
EXPORTS["kicad_sch"] = ["pdf", "svg", "netlist", "bom"]


def kind(named: str) -> str:
    """A kind as it is now: an alias (``KIND_ALIASES``) the kind it names, any other as given."""
    return KIND_ALIASES.get(named, named)


def exports_of(kind: str, file: bool) -> list[str]:
    """What Export offers of a document of ``kind``: an ``.xbf`` opened from disk (``file``), what that file
    exports; any other, its kind's."""
    kind = KIND_ALIASES.get(kind, kind)
    return list(EXPORTS["model" if kind == XBF and not file else kind])


def file_kind(path) -> str | None:
    """The kind of the file at ``path``, by its extension; None for a file no page reads."""
    return FILE_KINDS.get(os.path.splitext(str(path or ""))[1].lower())


def file_format(path) -> str | None:
    """The format of the file at ``path`` (``FORMATS``), by its extension; None for a file no page reads."""
    return FORMATS.get(os.path.splitext(str(path or ""))[1].lower())


def document_api(kind: str, ident: str) -> str:
    """Where a page reads the document ``ident`` of ``kind``."""
    return f"{API}/documents/{kind}/{ident}"
