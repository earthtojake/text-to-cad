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
* ``urdf``, ``srdf``, ``sdf``: ``structure`` (the robot resolved for the page), ``parts/<digest>``
  (a primitive's mesh), ``source``.
* ``stl``, ``glb``, ``3mf``: ``source``, which the page parses itself.
"""
from __future__ import annotations

import os

API = "/api/v1"

FILE_KINDS = {".xbf": "xbf", ".step": "step", ".stp": "step", ".stl": "stl", ".glb": "glb", ".3mf": "3mf",
              ".dxf": "dxf", ".urdf": "urdf", ".srdf": "srdf", ".sdf": "sdf"}
KINDS = ("model", "xbf", "step", "stl", "glb", "3mf", "dxf", "urdf", "srdf", "sdf")
# The documents the engine itself serves: their structure, parts and version are its reads.
ENGINE_KINDS = frozenset({"model", "xbf", "step"})
ROBOT_KINDS = frozenset({"urdf", "srdf", "sdf"})

# What each kind's Export offers (``packages/ui``'s ``export/formats.ts``), by its format name
# (``exports.FORMATS``); ``dxf`` only where the view draws the document flat.
_SOLID = ["step", "stl", "threemf", "glb", "dxf"]
EXPORTS = {"model": [*_SOLID, "xbf"], "step": [*_SOLID, "xbf"], "xbf": [*_SOLID, "original"],
           "glb": ["stl", "threemf"], "stl": ["threemf", "glb"], "3mf": ["stl", "glb"],
           "dxf": [], "urdf": [], "srdf": [], "sdf": []}


def file_kind(path) -> str | None:
    """The kind of the file at ``path``, by its extension; None for a file no page reads."""
    return FILE_KINDS.get(os.path.splitext(str(path or ""))[1].lower())


def document_api(kind: str, ident: str) -> str:
    """Where a page reads the document ``ident`` of ``kind``."""
    return f"{API}/documents/{kind}/{ident}"
