"""The document types and the integrations: one table, the single source of every layer.

A **document type** is what is in a file. Each has one lowercase underscore id, the same in Python
(``cad.<id>``), the ``cad`` command (``cad <id> <operation>``), the server, the viewer and the
JavaScript generated from this table (``python -m cad.registry --js``). The table maps extensions to
ids (``.step`` and ``.stp`` are both ``step``); 3MF's id is ``threemf`` because an id is a Python name.

An **integration** is our support for one third-party tool, named for the tool's own project: one
extra (``cad[<name>]``) grouping what our code for it needs, our code for it (helpers that take its
objects, producers and operations), and a process kind. A **producer** is code that makes a document
type from some input; many integrations may produce one type, each stating which parts of the type's
content it provides. The **operations** are a fixed set: ``export``, ``snapshot``, ``inspect`` and
``check``.

Kernel-free, the standard library alone: the server imports this module, and so does every page's
build through the generated JavaScript. A producer's matcher reads a value's type names and modules,
never importing the library the value comes from.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

__all__ = ["DOCUMENT_TYPES", "INTEGRATIONS", "OPERATIONS", "PROCESS_KINDS", "VIEWS", "DocumentTypeEntry",
           "Integration", "Operation", "Probe", "Producer", "by_extension", "declarer_for", "help_text", "producer_for", "producers_for",
           "type_of"]

#: The operations, a fixed set shared by every type; each type implements those that make sense for it.
OPERATIONS = ("export", "snapshot", "inspect", "check")
#: How a type is viewed: an engine document (a B-rep scene the engine serves), a triangle mesh, a 2D
#: drawing, a robot description, a plot.
VIEWS = ("document", "mesh", "drawing", "robot", "plot")
#: Where an integration's code runs: inside the Python process that calls it, as a separate program, or both.
PROCESS_KINDS = ("in-process", "separate", "both")


@dataclass(frozen=True)
class Operation:
    """One operation a type implements: what it does, and the integration it needs (None: our own code alone)."""

    name: str
    summary: str
    integration: str | None = None


@dataclass(frozen=True)
class Probe:
    """How an external program an integration runs is found: the program, the oldest version our code
    supports, what to say when it is missing, and the variable that names it outright."""

    program: str
    minimum: str
    install_hint: str
    override: str


@dataclass(frozen=True)
class Integration:
    """Our support for one third-party tool: its extra, its process kind and, for an external program,
    its probe."""

    name: str
    summary: str
    extra: str | None
    process: str
    probe: Probe | None = None


@dataclass(frozen=True)
class Producer:
    """Code that makes ``document_type`` from a value ``matcher`` accepts: the integration it belongs to,
    the values it takes (``accepts``, in words), the code that writes the file (``writer``), and the parts
    of the type's content it provides.

    A producer that also DECLARES says what the type's decorator does with what it is stacked on
    (``declare``: the dotted name of ``(type, out, name) -> apply``), for the targets ``decorates`` takes
    (None: every target of a type that has no other declarer). Without one, a decorator is the engine's
    (``cad.engine.model``): the function is a model, and its result is checked against the matchers when
    it is built."""

    document_type: str
    integration: str
    accepts: str
    matcher: Callable[[Any], bool] = field(compare=False, repr=False)
    writer: str
    provides: tuple[str, ...]
    declare: str = ""
    decorates: Callable[[Any], bool] | None = field(default=None, compare=False, repr=False)


@dataclass(frozen=True)
class DocumentTypeEntry:
    """One document type: its id, its name as people write it, its extensions (the first the one a
    written file takes), its MIME type, how it is viewed, the content it carries, its operations, and
    whether it has a decorator (``@<id>("out.<ext>")``) and a reader (``<id>.read``).

    ``wire`` is the spelling the frozen protocols carry for it -- the HTTP API's document kinds
    (``/api/v1/documents/<kind>/...``) and the analytics schemas -- which is the id but for
    ``threemf``, whose protocols say ``3mf``: a released page and a released receiver read them."""

    id: str
    title: str
    summary: str
    extensions: tuple[str, ...]
    mime: str
    view: str
    content: tuple[str, ...]
    operations: tuple[Operation, ...]
    decorator: bool = False
    reader: bool = False
    wire: str = ""

    def __post_init__(self) -> None:
        if not self.id.isidentifier() or self.id != self.id.lower():
            raise ValueError(f"a document type's id is a lowercase Python name, not {self.id!r}")
        if self.view not in VIEWS:
            raise ValueError(f"{self.id}: view {self.view!r} is not one of {', '.join(VIEWS)}")
        for operation in self.operations:
            if operation.name not in OPERATIONS:
                raise ValueError(f"{self.id}: {operation.name!r} is not an operation ({', '.join(OPERATIONS)})")
        if not self.wire:
            object.__setattr__(self, "wire", self.id)

    @property
    def suffix(self) -> str:
        """The extension a file of this type is written with."""
        return self.extensions[0]

    def operation(self, name: str) -> Operation | None:
        return next((operation for operation in self.operations if operation.name == name), None)

    @property
    def operation_names(self) -> tuple[str, ...]:
        """Its operations, in the fixed order of ``OPERATIONS``."""
        mine = {operation.name for operation in self.operations}
        return tuple(name for name in OPERATIONS if name in mine)


_KERNEL = "build123d"

_EXPORT_DOCUMENT = Operation("export", "write the document to other files, each kind by its suffix "
                                       "(.step, .glb, .stl, .3mf, .dxf, .xbf)", _KERNEL)
_EXPORT_MESH = Operation("export", "write the mesh to the other mesh kinds (.glb, .stl, .3mf)")
_SNAPSHOT = Operation("snapshot", "draw it as the CAD Viewer does, into a PNG", _KERNEL)
_INSPECT_DOCUMENT = Operation("inspect", "what the document holds, then its build closure; with a ref, what one "
                                         "element or part is and what made it", _KERNEL)
_INSPECT_GLB = Operation("inspect", "its nodes, meshes and animations", _KERNEL)

_DOCUMENT_CONTENT = ("geometry", "assembly", "names", "colours", "materials", "element names", "mechanism",
                     "configuration sequences")

_TYPES = (
    DocumentTypeEntry(
        "xbf", "XBF", "the engine's own document: an XCAF document saved as BinXCAF, with its build closure",
        (".xbf",), "application/octet-stream", "document",
        (*_DOCUMENT_CONTENT, "animations", "build closure"),
        (_EXPORT_DOCUMENT, _SNAPSHOT, _INSPECT_DOCUMENT), decorator=True, reader=True),
    DocumentTypeEntry(
        "step", "STEP", "an ISO 10303 (AP242) exchange file of exact geometry", (".step", ".stp"),
        "application/step", "document", _DOCUMENT_CONTENT,
        (_EXPORT_DOCUMENT, _SNAPSHOT, _INSPECT_DOCUMENT), decorator=True, reader=True),
    DocumentTypeEntry(
        "stl", "STL", "a binary STL of one triangle mesh", (".stl",), "model/stl", "mesh", ("triangles",),
        (_EXPORT_MESH, _SNAPSHOT), decorator=True, reader=True),
    DocumentTypeEntry(
        "glb", "GLB", "a binary glTF scene of triangle meshes", (".glb",), "model/gltf-binary", "mesh",
        ("triangles", "assembly", "names", "colours", "materials", "animations"),
        (_EXPORT_MESH, _SNAPSHOT, _INSPECT_GLB), decorator=True),
    DocumentTypeEntry(
        "threemf", "3MF", "a 3D Manufacturing Format package of triangle meshes", (".3mf",), "model/3mf", "mesh",
        ("triangles", "assembly", "names", "colours", "materials"),
        (_EXPORT_MESH, _SNAPSHOT), decorator=True, wire="3mf"),
    DocumentTypeEntry(
        "dxf", "DXF", "a 2D drawing of a planar document", (".dxf",), "application/dxf", "drawing",
        ("2D geometry", "layers"), (_SNAPSHOT,), decorator=True),
    DocumentTypeEntry(
        "urdf", "URDF", "a robot description (ROS's Unified Robot Description Format)", (".urdf",),
        "application/xml; charset=utf-8", "robot", ("links", "joints", "inertials", "mesh references"),
        (Operation("check", "check it for conformance: structure, joints, inertials, mesh references"), _SNAPSHOT)),
    DocumentTypeEntry(
        "srdf", "SRDF", "a MoveIt semantic robot description, read against its URDF", (".srdf",),
        "application/xml; charset=utf-8", "robot",
        ("planning groups", "end effectors", "group states", "disabled collision pairs", "virtual joints"),
        (Operation("check", "check it against its URDF: every name, chain, state and disabled pair"), _SNAPSHOT)),
    DocumentTypeEntry(
        "sdf", "SDF", "an SDFormat world or model (Gazebo's Simulation Description Format)", (".sdf",),
        "application/xml; charset=utf-8", "robot", ("worlds", "models", "links", "joints", "mesh references"),
        (Operation("check", "check it for conformance, and with gz sdf --check where it is installed"), _SNAPSHOT)),
    DocumentTypeEntry(
        "kicad_pcb", "KiCad PCB", "a KiCad printed circuit board, read with the .kicad_pro beside it", (".kicad_pcb",),
        "text/plain; charset=utf-8", "plot",
        ("board outline", "layers", "footprints", "pads", "nets", "tracks", "vias", "zones", "design rules"),
        (Operation("export", "write its fabrication outputs with KiCad: gerbers, drill, pos or step, into a folder",
                   "kicad"),
         Operation("snapshot", "draw it flat, as the CAD Viewer's board view does, into a PNG"),
         Operation("inspect", "what the board holds: its format, thickness, size, layers, parts and nets"),
         Operation("check", "KiCad's design rule check: errors and unconnected items fail it, warnings are said",
                   "kicad")), decorator=True),
)

#: Every document type, by id, in the table's order.
DOCUMENT_TYPES: Mapping[str, DocumentTypeEntry] = MappingProxyType({entry.id: entry for entry in _TYPES})

#: Every integration, by name.
INTEGRATIONS: Mapping[str, Integration] = MappingProxyType({
    "build123d": Integration(
        "build123d", "build123d and the OCCT kernel under it (OCP): model code builds with it, and the engine "
                     "makes, reads, writes and draws documents with it", extra="build123d", process="in-process"),
    "kicad": Integration(
        "kicad", "KiCad's command line, kicad-cli: the server runs it, headless, for a board's design rule check "
                 "and its fabrication exports, and its IPC API, which a board script edits through", extra="kicad",
        process="separate",
        probe=Probe("kicad-cli", "9.0", "install KiCad 9 or newer from https://www.kicad.org/download/, or set "
                                        "CAD_KICAD_CLI to its kicad-cli", "CAD_KICAD_CLI")),
})

_BY_EXTENSION = MappingProxyType({extension: entry for entry in _TYPES for extension in entry.extensions})


def by_extension(extension: str) -> DocumentTypeEntry | None:
    """The type a file extension names (``".stp"`` -> ``step``), case-insensitively; None for none."""
    extension = str(extension or "").lower()
    return _BY_EXTENSION.get(extension if extension.startswith(".") else "." + extension)


def type_of(path: Any) -> DocumentTypeEntry | None:
    """The type of the file at ``path``, by its extension; None for a file of no type."""
    import os

    name = os.path.basename(os.fspath(path)) if path is not None else ""
    dot = name.rfind(".")
    return by_extension(name[dot:]) if dot > 0 else None


def _producers() -> tuple[Producer, ...]:
    # Each integration registers the producers it has; this is the one place they are gathered.
    from cad.build123d._producers import PRODUCERS as build123d
    from cad.kicad._producers import PRODUCERS as kicad

    return (*build123d, *kicad)


def producers_for(document_type: str) -> tuple[Producer, ...]:
    """The producers of one type, every integration's."""
    return tuple(producer for producer in _producers() if producer.document_type == document_type)


def producer_for(document_type: str, value: Any, *, where: str = "a model") -> Producer:
    """The one producer that makes ``document_type`` of ``value``; a ``TypeError`` naming what the type
    takes, and the integration that would take more, for a value none takes. Two producers taking one
    value is the registry's error, said as one."""
    found = [producer for producer in producers_for(document_type) if producer.matcher(value)]
    if len(found) == 1:
        return found[0]
    if len(found) > 1:
        raise RuntimeError(f"{document_type}: {len(found)} producers take {type(value).__name__} "
                           f"({', '.join(producer.integration for producer in found)}): exactly one may")
    accepted = sorted({producer.accepts for producer in producers_for(document_type)})
    origin = str(type(value).__module__).split(".")[0]
    if origin in INTEGRATIONS:
        more = f"the {origin} integration has no producer of {document_type} from {type(value).__name__}"
    elif origin in ("builtins", "", "__main__", "cad"):
        more = f"integrations: {', '.join(INTEGRATIONS)}"
    else:
        more = f"there is no {origin} integration: one would add a producer of it"
    takes = " or ".join(accepted) if accepted else "nothing: no producer is registered"
    raise TypeError(f"{where} returned {type(value).__name__}; a {document_type} document is made of {takes} "
                    f"({more})")


def declarer_for(document_type: str, target: Any) -> Producer | None:
    """The producer that declares what ``@<type>`` does with ``target`` (``Producer.declare``), or None when
    the decorator is the engine's. Two that take one target is the registry's error."""
    found = [producer for producer in producers_for(document_type) if producer.declare
             and (producer.decorates is None or producer.decorates(target))]
    if len(found) > 1:
        raise RuntimeError(f"@{document_type}: {len(found)} producers declare {type(target).__name__}: exactly one may")
    return found[0] if found else None


def help_text(document_type: str) -> str:
    """A type's help, worked out from this table: what it is, the content it carries, its operations and
    what writes it."""
    entry = DOCUMENT_TYPES[document_type]
    lines = [f"{entry.id}: {entry.summary} ({', '.join(entry.extensions)})",
             f"carries: {', '.join(entry.content)}"]
    lines.append("operations:")
    width = max((len(operation.name) for operation in entry.operations), default=0)
    for name in entry.operation_names:
        operation = entry.operation(name)
        assert operation is not None
        needs = f" [{operation.integration}]" if operation.integration else ""
        lines.append(f"  {name.ljust(width)}  {operation.summary}{needs}")
    producers = producers_for(entry.id)
    if producers:
        lines.append("written by:")
        for producer in producers:
            lines.append(f"  @{entry.id}(\"out{entry.suffix}\") of {producer.accepts} "
                         f"({producer.integration}: {', '.join(producer.provides)})")
    else:
        lines.append("written by: no producer; a file of it is authored")
    return "\n".join(lines)


def as_data() -> dict[str, Any]:
    """The table as data, for the JavaScript side (``--js``) and its parity test."""
    return {
        "operations": list(OPERATIONS),
        "views": list(VIEWS),
        "documentTypes": [
            {"id": entry.id, "title": entry.title, "wire": entry.wire, "extensions": list(entry.extensions),
             "mime": entry.mime, "view": entry.view, "operations": list(entry.operation_names),
             "decorator": entry.decorator}
            for entry in _TYPES
        ],
    }


_JS_HEAD = ("// GENERATED from the library's document type registry (cad.registry): do not edit.\n"
            "// Regenerate with `python -m cad.registry --js > packages/core/src/lib/documentTypes.generated.js`;\n"
            "// tests/python/packages/cad/test_registry.py fails when this file and the registry differ.\n")


def as_js() -> str:
    """The table as the ES module ``@cad/core``'s ``lib/documentTypes.generated.js`` is."""
    body = json.dumps(as_data(), indent=2, ensure_ascii=False)
    return f"{_JS_HEAD}export const DOCUMENT_TYPE_REGISTRY = Object.freeze({body});\n"


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv == ["--js"]:
        sys.stdout.write(as_js())
        return 0
    if argv == ["--json"]:
        sys.stdout.write(json.dumps(as_data(), indent=2) + "\n")
        return 0
    if len(argv) == 1 and argv[0] in DOCUMENT_TYPES:
        sys.stdout.write(help_text(argv[0]) + "\n")
        return 0
    sys.stderr.write(f"usage: python -m cad.registry --js | --json | {{{','.join(DOCUMENT_TYPES)}}}\n")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
