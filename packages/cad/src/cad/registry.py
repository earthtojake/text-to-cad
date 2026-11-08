"""The document types and the integrations: one table, the single source of every layer.

A **document type** is what is in a file. Each has one lowercase underscore id, the same in Python
(``cad.<id>``), the ``cad`` command (``cad <id> <operation>``), the server, the viewer and the
JavaScript generated from this table (``python -m cad.registry --js``). The table maps extensions to
ids (``.step`` and ``.stp`` are both ``step``); 3MF's id is ``threemf`` because an id is a Python name.

An **integration** is our support for one third-party tool, named for the tool's own project: one
extra (``cad[<name>]``) grouping what our code for it needs, our code for it (helpers that take its
objects, producers and operations), and a process kind. A **producer** is code that makes a document
type from some input; many integrations may produce one type, each stating which parts of the type's
content it provides. The **operations** are a closed set (``OPERATIONS``): ``export`` and ``snapshot``,
shared by every type that has them, ``inspect`` where a type has it, and the rest named for what they do --
``dfm`` a 3D type's manufacturing check, ``drc`` a board's design rule check, ``erc`` a schematic's electrical
rules check, ``validate`` a robot description's conformance check.

``model`` is the one type with no file: a model built from code and held in the engine's memory,
addressed by its document id or the handle its call returns (``@model`` declares one); ``xbf`` is the
``.xbf`` file the engine writes of one.

Kernel-free, the standard library alone: the server imports this module, and so does every page's
build through the generated JavaScript. A producer's matcher reads a value's type names and modules,
never importing the library the value comes from.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable, Mapping
from functools import cache
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

__all__ = ["DOCUMENT_TYPES", "INTEGRATIONS", "OPERATIONS", "PROCESS_KINDS", "VIEWS", "DocumentTypeEntry",
           "Edit", "Integration", "Operation", "Probe", "Producer", "by_extension", "help_text", "integrations_of",
           "producer_for", "producers_for",
           "type_of"]

#: The operations, a closed set: ``export`` and ``snapshot`` shared by every type that has them, ``inspect``
#: where a type has it, and the others named for what they do -- each a type implements where it makes sense.
OPERATIONS = ("export", "snapshot", "inspect", "dfm", "drc", "erc", "validate")
#: How a type is viewed: an engine document (a B-rep scene the engine serves), a triangle mesh, a 2D
#: drawing, a robot description, a plot.
VIEWS = ("document", "mesh", "drawing", "robot", "plot")
#: Where an integration's code runs: inside the Python process that calls it, as a separate program, or both.
PROCESS_KINDS = ("in-process", "separate", "both")


@dataclass(frozen=True)
class Operation:
    """One operation a type implements: what it does, the integration it needs (None: our own code alone), and
    whether the engine runs it (``engine``: ``cad.engine.api``'s, in the daemon, whose base holds that
    integration), so a program that calls it needs none of its own; else it runs in the calling process."""

    name: str
    summary: str
    integration: str | None = None
    engine: bool = False


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
    """Our support for one third-party tool: its extra, its process kind, the top-level modules a script
    imports it by (``modules``: a script that imports one uses the integration), the distributions its
    extra installs (``distributions``) and, for an external program, its probe."""

    name: str
    summary: str
    extra: str | None
    process: str
    probe: Probe | None = None
    modules: tuple[str, ...] = ()
    distributions: tuple[str, ...] = ()
    #: The distributions that ARE it (its own and the other builds of its modules), of which one a resolution
    #: pulls in through another package means the program uses it; and the package indexes and wheel folders
    #: its packages come from beside the default index (none today: a hook for packaged binaries).
    identity: tuple[str, ...] = ()
    indexes: tuple[str, ...] = ()
    find_links: tuple[str, ...] = ()
    #: The commands its extra puts in an environment (``kicad-cli``), each the tool's own command line:
    #: ``cad run <command>`` makes the integration's environment for one and runs it there, through the
    #: integration's ``_command`` module (``cad.<name>._command``), headless in private homes.
    commands: tuple[str, ...] = ()
    #: What its extra brings, in the words said as its environment is made, and about how many megabytes of
    #: wheels it downloads: PyPI's wheels for what the extra adds to the library (whose own numpy uv's cache has from
    #: the server's install), macOS arm64, Linux x86-64 and Windows x86-64, rounded to what holds on all three. A
    #: download's size, never the installed environment's, which is two to three times that.
    holds: str = ""
    download_mb: int = 0


@dataclass(frozen=True)
class Producer:
    """Code that makes ``document_type`` from a value ``matcher`` accepts: the integration it belongs to,
    the values it takes (``accepts``, in words), the code that writes the file (``writer``), and the parts
    of the type's content it provides. A producer regenerates its file from code: the type's decorator is
    the engine's (``cad.engine.model``), the function a model, and its result is checked against the matchers
    when it is built."""

    document_type: str
    integration: str
    accepts: str
    matcher: Callable[[Any], bool] = field(compare=False, repr=False)
    writer: str
    provides: tuple[str, ...]


@dataclass(frozen=True)
class Edit:
    """How a file of a type is changed in place, in the caller's process, rather than made by a producer: the
    function that opens it for a ``with`` block (``<type>.edit``), the integration it runs, the word for what it
    opens, what the block is handed, in words, and the parts of the type's content it can change."""

    integration: str
    noun: str
    hands: str
    changes: tuple[str, ...]


@dataclass(frozen=True)
class DocumentTypeEntry:
    """One document type: its id, its name as people write it, its extensions (the first the one a
    written file takes; none for ``model``, which has no file), its MIME type, how it is viewed, the
    content it carries, its operations, and whether it has a decorator (``@<id>("out.<ext>")``) and a
    reader (``<id>.read``).

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
    #: The integration its reader needs in the process that calls it (None: our own code alone): a STEP's,
    #: an xbf's and an STL's read hands a model build123d's objects, through the kernel memo.
    reader_integration: str | None = None
    wire: str = ""
    #: How a file of it is changed in place (``<id>.edit``, a ``with`` block), where it can be: a KiCad board's
    #: and schematic's, through KiCad's IPC API. None for a type whose files are made or authored alone.
    edit: Edit | None = None

    def __post_init__(self) -> None:
        if not self.id.isidentifier() or self.id != self.id.lower():
            raise ValueError(f"a document type's id is a lowercase Python name, not {self.id!r}")
        if self.view not in VIEWS:
            raise ValueError(f"{self.id}: view {self.view!r} is not one of {', '.join(VIEWS)}")
        for operation in self.operations:
            if operation.name not in OPERATIONS:
                raise ValueError(f"{self.id}: {operation.name!r} is not an operation ({', '.join(OPERATIONS)})")
        if self.reader_integration is not None and not self.reader:
            raise ValueError(f"{self.id}: a reader_integration with no reader")
        if not self.wire:
            object.__setattr__(self, "wire", self.id)

    @property
    def suffix(self) -> str:
        """The extension a file of this type is written with ("" for a type with no file: ``model``)."""
        return self.extensions[0] if self.extensions else ""

    @property
    def has_file(self) -> bool:
        """Whether a document of this type is a file (every type's but ``model``'s, held in memory)."""
        return bool(self.extensions)

    def operation(self, name: str) -> Operation | None:
        return next((operation for operation in self.operations if operation.name == name), None)

    @property
    def operation_names(self) -> tuple[str, ...]:
        """Its operations, in the fixed order of ``OPERATIONS``."""
        mine = {operation.name for operation in self.operations}
        return tuple(name for name in OPERATIONS if name in mine)


_KERNEL = "build123d"

_EXPORT_DOCUMENT = Operation("export", "write the document to other files, each kind by its suffix "
                                       "(.step, .glb, .stl, .3mf, .dxf, .xbf); --tolerance meshes an .stl or a "
                                       ".3mf finer", _KERNEL, engine=True)
_EXPORT_MESH = Operation("export", "write the mesh to the other mesh kinds (.glb, .stl, .3mf)", engine=True)
_SNAPSHOT = Operation("snapshot", "draw it as the CAD Viewer does, into a PNG", _KERNEL, engine=True)
_INSPECT_DOCUMENT = Operation("inspect", "what the document holds, then its build closure; with a ref, what one "
                                         "element or part is and what made it", _KERNEL, engine=True)
_INSPECT_GLB = Operation("inspect", "its nodes, meshes and animations", _KERNEL, engine=True)
# The manufacturing check every 3D type shares (``cad._internal.manufacturing``), measured with trimesh.
_DFM = Operation("dfm", "measure it for manufacturing: injection molding (--process molding: draft, undercuts, "
                        "projected area) or 3D printing (--process printing: walls, overhangs, support); "
                        "--candidates ranks the pulls or orientations", "trimesh")

_DOCUMENT_CONTENT = ("geometry", "assembly", "names", "colours", "materials", "element names", "mechanism",
                     "configuration sequences")

_TYPES = (
    DocumentTypeEntry(
        "model", "model", "a model built from code and held in the engine's memory, with no file behind it: "
                          "addressed by its document id (cad run SCRIPT.py prints it) or the handle its call returns",
        (), "", "document", (*_DOCUMENT_CONTENT, "animations", "build closure"),
        (_EXPORT_DOCUMENT, _SNAPSHOT, _INSPECT_DOCUMENT, _DFM), decorator=True),
    DocumentTypeEntry(
        "xbf", "XBF", "the engine's own document saved as a file: an XCAF document as BinXCAF, with its build "
                      "closure", (".xbf",), "application/octet-stream", "document",
        (*_DOCUMENT_CONTENT, "animations", "build closure"),
        (_EXPORT_DOCUMENT, _SNAPSHOT, _INSPECT_DOCUMENT, _DFM), decorator=True, reader=True,
        reader_integration=_KERNEL),
    DocumentTypeEntry(
        "step", "STEP", "an ISO 10303 (AP242) exchange file of exact geometry", (".step", ".stp"),
        "application/step", "document", _DOCUMENT_CONTENT,
        (_EXPORT_DOCUMENT, _SNAPSHOT, _INSPECT_DOCUMENT, _DFM), decorator=True, reader=True,
        reader_integration=_KERNEL),
    DocumentTypeEntry(
        "stl", "STL", "a binary STL of one triangle mesh", (".stl",), "model/stl", "mesh", ("triangles",),
        (_EXPORT_MESH, _SNAPSHOT, _DFM), decorator=True, reader=True, reader_integration=_KERNEL),
    DocumentTypeEntry(
        "glb", "GLB", "a binary glTF scene of triangle meshes", (".glb",), "model/gltf-binary", "mesh",
        ("triangles", "assembly", "names", "colours", "materials", "animations"),
        (_EXPORT_MESH, _SNAPSHOT, _INSPECT_GLB, _DFM), decorator=True),
    DocumentTypeEntry(
        "threemf", "3MF", "a 3D Manufacturing Format package of triangle meshes", (".3mf",), "model/3mf", "mesh",
        ("triangles", "assembly", "names", "colours", "materials"),
        (_EXPORT_MESH, _SNAPSHOT, _DFM), decorator=True, wire="3mf"),
    DocumentTypeEntry(
        "dxf", "DXF", "a 2D drawing of a planar document", (".dxf",), "application/dxf", "drawing",
        ("2D geometry", "layers"), (_SNAPSHOT,), decorator=True),
    DocumentTypeEntry(
        "urdf", "URDF", "a robot description (ROS's Unified Robot Description Format)", (".urdf",),
        "application/xml; charset=utf-8", "robot", ("links", "joints", "inertials", "mesh references"),
        (Operation("validate", "check it for conformance: structure, joints, inertials, mesh references"), _SNAPSHOT)),
    DocumentTypeEntry(
        "srdf", "SRDF", "a MoveIt semantic robot description, read against its URDF", (".srdf",),
        "application/xml; charset=utf-8", "robot",
        ("planning groups", "end effectors", "group states", "disabled collision pairs", "virtual joints"),
        (Operation("validate", "check it against its URDF: every name, chain, state and disabled pair"), _SNAPSHOT)),
    DocumentTypeEntry(
        "sdf", "SDF", "an SDFormat world or model (Gazebo's Simulation Description Format)", (".sdf",),
        "application/xml; charset=utf-8", "robot", ("worlds", "models", "links", "joints", "mesh references"),
        (Operation("validate", "check it for conformance, and with gz sdf --check where it is installed"), _SNAPSHOT)),
    DocumentTypeEntry(
        "mjcf", "MJCF", "a MuJoCo model (MJCF XML): its bodies, joints and geoms, read as a robot with its "
                        "mesh assets", (".xml", ".mjcf"), "application/xml; charset=utf-8", "robot",
        ("bodies", "joints", "geoms", "mesh references", "keyframes"),
        (Operation("validate", "check it for conformance: structure, defaults, bodies, joints, geoms and mesh "
                               "references, and compile it with MuJoCo where cad[mujoco] is installed (--compile "
                               "required makes that environment)", "mujoco"), _SNAPSHOT)),
    DocumentTypeEntry(
        "kicad_pcb", "KiCad PCB", "a KiCad printed circuit board, read with the .kicad_pro beside it", (".kicad_pcb",),
        "text/plain; charset=utf-8", "plot",
        ("board outline", "layers", "footprints", "pads", "nets", "tracks", "vias", "zones", "design rules"),
        (Operation("export", "write its fabrication and 3D outputs with KiCad into a folder: gerbers, drill, pos, bom, "
                             "step, glb, odb, ipc2581, pdf or dxf", "kicad"),
         Operation("snapshot", "draw it flat, as the CAD Viewer's board view does, into a PNG"),
         Operation("inspect", "what the board holds: its format, thickness, size, layers, parts and nets"),
         Operation("drc", "KiCad's design rule check: errors and unconnected items fail it, warnings are said",
                   "kicad")), reader=True,
        edit=Edit("kicad", "board", "the open board, through KiCad's IPC API (kicode's KiPy)",
                  ("board outline", "layers", "footprints", "pads", "nets", "tracks", "vias", "zones", "design rules"))),
    DocumentTypeEntry(
        "kicad_sch", "KiCad schematic", "a KiCad schematic, read with every sheet of its project's hierarchy",
        (".kicad_sch",), "text/plain; charset=utf-8", "plot",
        ("sheets", "symbols", "pins", "fields", "wires", "buses", "labels", "junctions", "no-connects", "nets"),
        (Operation("export", "write it with KiCad: a pdf, an svg per sheet, the netlist or a BOM, into a folder", "kicad"),
         Operation("snapshot", "draw one sheet flat, as KiCad's schematic editor shows it, into a PNG"),
         Operation("inspect", "what the schematic holds: its sheets, parts and nets; with a ref, what that names"),
         Operation("erc", "KiCad's electrical rules check: errors fail it, warnings are said", "kicad")),
        reader=True,
        edit=Edit("kicad", "schematic", "the open schematic, its project's symbol libraries loaded, through KiCad's IPC API "
                           "(kicode's KiPy)",
                  ("sheets", "symbols", "pins", "fields", "wires", "buses", "labels", "junctions", "no-connects", "nets"))),
)

#: Every document type, by id, in the table's order.
DOCUMENT_TYPES: Mapping[str, DocumentTypeEntry] = MappingProxyType({entry.id: entry for entry in _TYPES})

#: Every integration, by name.
INTEGRATIONS: Mapping[str, Integration] = MappingProxyType({
    "build123d": Integration(
        "build123d", "build123d and the OCCT kernel under it (OCP): model code builds with it, and the engine "
                     "makes, reads, writes and draws documents with it", extra="build123d", process="in-process",
        modules=("build123d", "OCP"),
        distributions=("build123d", "cadquery-ocp-novtk", "bd_materials", "threejs-materials", "matplotlib", "shapely",
                       "ezdxf", "pillow"),
        identity=("build123d", "cadquery-ocp", "cadquery-ocp-novtk", "cadquery-ocp-proxy"),
        holds="the CAD kernel", download_mb=240),
    "kicad": Integration(
        "kicad", "KiCad's command line, kicad-cli, and its IPC API, both kicode's: a board's design rule check and "
                 "its fabrication exports run kicad-cli, headless, and an edit of a board or a schematic goes "
                 "through the API",
        extra="kicad", process="separate",
        # kicad-cli is kicode's (the extra's), or the one CAD_KICAD_CLI names: a check or an export runs 9 or
        # newer, an edit (kicad_pcb.edit, kicad_sch.edit) needs its headless api-server (kicode's has it; another's
        # is asked, cad.kicad._program.check_api_server, before it starts). A person's own KiCad is never run.
        probe=Probe("kicad-cli", "9.0", "kicad-cli comes with cad's kicad integration, cad[kicad] (kicode), which the "
                                        "cad command installs on first need (a script run with cad run: name "
                                        "cad[kicad] in its header); or set CAD_KICAD_CLI to a kicad-cli of "
                                        "KiCad 9 or newer (a nightly's, 10.99, for kicad_pcb.edit and kicad_sch.edit)",
                    "CAD_KICAD_CLI"),
        modules=("kicode",), distributions=("kicode",),
        identity=("kicode", "kicode-pcb", "kicode-sch"), commands=("kicad-cli",),
        holds="KiCad's kicad-cli", download_mb=100),
    "trimesh": Integration(
        "trimesh", "trimesh, the triangle-mesh library: a 3D document's manufacturing check measures its mesh with "
                   "it -- injection molding's draft, undercuts and projected area, 3D printing's walls, overhangs "
                   "and support", extra="trimesh", process="in-process",
        modules=("trimesh",), distributions=("trimesh", "rtree", "scipy", "networkx"), identity=("trimesh",),
        holds="trimesh", download_mb=40),
    "mujoco": Integration(
        "mujoco", "MuJoCo, the physics engine, as its headless core (mujoco-core: the compiler and the bindings, no "
                  "renderer): an MJCF's validate compiles the model with it, so what MuJoCo refuses is a finding "
                  "with MuJoCo's own words", extra="mujoco", process="in-process",
        modules=("mujoco",), distributions=("mujoco-core",), identity=("mujoco", "mujoco-core"),
        holds="MuJoCo's headless core", download_mb=10),
})

_BY_EXTENSION = MappingProxyType({extension: entry for entry in _TYPES for extension in entry.extensions})


def integrations_of(modules: Any) -> tuple[str, ...]:
    """The integrations a script uses, by the top-level modules it imports (``Integration.modules``)."""
    roots = {str(module).split(".")[0] for module in modules}
    return tuple(name for name, integration in INTEGRATIONS.items() if roots & set(integration.modules))


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


@cache
def _producers() -> tuple[Producer, ...]:
    # Each integration registers the producers it has; this is the one place they are gathered.
    from cad.build123d._producers import PRODUCERS as build123d

    return build123d


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


def help_text(document_type: str) -> str:
    """A type's help, worked out from this table: what it is, the content it carries, its operations and
    what writes it."""
    entry = DOCUMENT_TYPES[document_type]
    lines = [f"{entry.id}: {entry.summary}" + (f" ({', '.join(entry.extensions)})" if entry.has_file else ""),
             f"carries: {', '.join(entry.content)}"]
    lines.append("operations:")
    width = max((len(operation.name) for operation in entry.operations), default=0)
    for name in entry.operation_names:
        operation = entry.operation(name)
        assert operation is not None
        needs = f" [{operation.integration}]" if operation.integration else ""
        lines.append(f"  {name.ljust(width)}  {operation.summary}{needs}")
    producers = producers_for(entry.id)
    if entry.edit is not None:
        lines.append("written by:")
        lines.append(f"  with {entry.id}.edit(\"{entry.edit.noun}{entry.suffix}\") as {entry.edit.noun}: {entry.edit.hands}, "
                     f"changed in place, saved at the block's end when changed ({entry.edit.integration}: "
                     f"{', '.join(entry.edit.changes)})")
    elif producers and not entry.has_file:
        lines.append("made by:")
        for producer in producers:
            lines.append(f"  @{entry.id} on a function returning {producer.accepts.removesuffix(' a model returns')} "
                         f"({producer.integration}: {', '.join(producer.provides)})")
    elif producers:
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
