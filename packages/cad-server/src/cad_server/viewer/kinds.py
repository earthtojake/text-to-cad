"""The engine's HTTP API, ``/api/v1``: the kinds of documents it names, and the formats each exports.

Every document the pages read is one of ``KINDS``, a lower-case word: a model's document is
``model``, a file's is named by its extension (``FILE_KINDS``: a ``.stp`` is a ``step``). A kind is a
typed collection inside ``documents``: ``/api/v1/documents/<kind>/<id>/...`` is what a page reads of
a document of that kind, and the same id under another kind is a 404 that names the right one
(``http_app``). What each kind's collection answers:

* ``model``, ``xbf``, ``step``: the engine's document -- ``structure``, ``parts/<key>`` (and each
  part's ``faces``/``edges``/``vertices/<ordinal>``, ``groups``, ``volume``), ``measure``,
  ``kinematics``, ``POST pose``, ``POST mesh``; a file's also its ``source``.
* ``dxf``: ``drawing`` (the 2D payload), ``source``.
* ``kicad_pcb``: ``plot`` (the board's geometry per layer, and its index), ``drc`` (KiCad's design rule
  check of it), ``source``.
* ``kicad_sch``: ``plot`` (every sheet of the schematic a page of layers, and its index), ``source``.
* ``urdf``, ``srdf``, ``sdf``: ``structure`` (the robot resolved for the page), ``parts/<digest>``
  (a primitive's mesh), ``source``.
* ``stl``, ``glb``, ``3mf``: ``source``, which the page parses itself.
* ``implicit``: ``source`` too -- the GLB the engine holds of a model built from a field (the mesh sampled from
  it, ``cad.engine.implicit_document``), read as a ``glb``'s is; a document with no file of the author's.
"""
from __future__ import annotations

import os

from cad.registry import DOCUMENT_TYPES

API = "/api/v1"

# A file's kind is its document type as the API spells it (``cad.registry``'s ``wire``: the id, but
# ``3mf`` for ``threemf``, the spelling released pages read).
FILE_KINDS = {extension: entry.wire for entry in DOCUMENT_TYPES.values() for extension in entry.extensions}
# ``model`` is a document type of its own, the one with no file (``cad.registry``): a model's document.
KINDS = tuple(entry.wire for entry in DOCUMENT_TYPES.values())
# The documents the engine itself serves: their structure, parts and version are its reads.
ENGINE_KINDS = frozenset(entry.wire for entry in DOCUMENT_TYPES.values() if entry.view == "document")
# The kinds whose source the page parses itself: a mesh file's, and an implicit document's GLB.
MESH_KINDS = frozenset(entry.wire for entry in DOCUMENT_TYPES.values() if entry.view == "mesh")
ROBOT_KINDS = frozenset(entry.wire for entry in DOCUMENT_TYPES.values() if entry.view == "robot")

# What each kind's Export offers (``packages/ui``'s ``export/formats.ts``), by its format name
# (``exports.FORMATS``); ``dxf`` only where the view draws the document flat. A KiCad board's are KiCad's
# (``cad kicad_pcb export --to``, ``exports.BOARD``).
_SOLID = ["step", "stl", "threemf", "glb", "dxf"]
EXPORTS = {"model": [*_SOLID, "xbf"], "step": [*_SOLID, "xbf"], "xbf": [*_SOLID, "original"],
           "glb": ["stl", "threemf"], "stl": ["threemf", "glb"], "3mf": ["stl", "glb"], "implicit": ["stl", "threemf", "glb"],
           "dxf": [], "urdf": [], "srdf": [], "sdf": [],
           "kicad_pcb": ["gerbers", "drill", "pos", "bom", "step", "glb", "odb", "ipc2581", "pdf", "dxf"]}
# A KiCad schematic's are KiCad's too (``cad kicad_sch export --to``, ``exports.SCHEMATIC``).
EXPORTS["kicad_sch"] = ["pdf", "svg", "netlist", "bom"]


def file_kind(path) -> str | None:
    """The kind of the file at ``path``, by its extension; None for a file no page reads."""
    return FILE_KINDS.get(os.path.splitext(str(path or ""))[1].lower())


def document_api(kind: str, ident: str) -> str:
    """Where a page reads the document ``ident`` of ``kind``."""
    return f"{API}/documents/{kind}/{ident}"
