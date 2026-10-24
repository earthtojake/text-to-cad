"""What a model imports: a STEP or an xbf made a build123d compound tree, the reader
process a STEP is parsed in, and a mesh file read as data (``read_mesh``).

An XCAF document -- a STEP read by OCCT's XCAF reader, or an xbf -- is described as data
(``describe``): its products, each once however often it is placed (a name, a colour, a
material; a part's shape, the names its file gives its elements, an xbf's painted faces and
face materials; an assembly's components), and its free shapes; each component a product
placed by a location under a name and a colour. The shapes and the locations travel apart,
as kernel objects. ``assemble`` builds the tree a model gets from them: an assembly a
``Compound`` of its components, a part a handle of its own on its product's geometry (a
move places that occurrence, never the product's other placements), every node named as
the file names that occurrence (its own name, else its product's), coloured, given its
material. A mechanism is never imported: a part is a part.

**A STEP is parsed in a reader process** (``Reader``), not in the worker: the XCAF reader's
working memory is many times the result's (2.3 GB for a 354 MB file) and an allocator gives
little of it back, so a worker that parsed a STEP would keep it for its life. One reader
serves a build: started on the build's first STEP read (``session``), reused for the rest,
gone when the build ends. It answers a read with the description as JSON and one
``BinTools`` dump of a compound holding every part's shape, then a marker per location
(``pack``); the worker reads the dump once and assembles the tree. So the worker holds the
result and nothing of the parse. A shape written and read once is what the kernel gives
back from a document saved and read (``mesh.shape_bytes``), and the same bytes read the
same: the tree is a function of the file. A read outside a build starts a reader of its
own for it.

An xbf is read in the worker (``read_xbf``): its reader is the document's own retrieval
driver, its working memory the document's.

**A mesh is data, never a shape** (``read_mesh``, an ``.stl``): its vertices, its triangles
and its name, as numbers (``Mesh``). A mesh has no B-rep -- no surface under a face, no curve
under an edge -- so no document holds one: a model measures it and builds B-rep from its
numbers. The memo keys the read by the file's bytes, as it keys ``read_step``'s, and hands a
later build's read of the same bytes this very object.

**A model never reads a file its own build writes** (``refuse_written``): its own xbf or
export, a child's, a sibling's. Read, the file would be an input the build rewrites -- its
key moving on every build, so the model would never be taken from its file -- or, keyed by
anything but its bytes, a model depending on its own past. A model takes what it makes from
the live shape instead: the shape a body returns, or the child model it calls.
"""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import threading
from contextlib import contextmanager
from typing import Any, Iterator

__all__ = ["MESH_SUFFIXES", "Mesh", "Reader", "assemble", "describe", "main", "read_mesh", "read_step", "read_xbf",
           "refuse_written", "session", "written_by_build"]

# What ``read_mesh`` reads.
MESH_SUFFIXES = (".stl",)


# --- a document described ---------------------------------------------------------------------


def _rgba(quantity: Any) -> list[float]:
    rgb = quantity.GetRGB()
    return [rgb.Red(), rgb.Green(), rgb.Blue(), quantity.Alpha()]


def describe(doc: Any, step: bool) -> tuple[dict[str, Any], list[Any], list[Any]]:
    """An XCAF document as data (see the module), the shapes its parts are, and the locations
    its components are placed at. ``step``: a STEP's names decoded as the file means them,
    and a part's colour, where its label has none, its shape's or its largest coloured
    face's (as build123d's importer takes it); an xbf's names as the engine wrote them, its
    colours its labels', its painted faces and face materials carried."""
    import unicodedata

    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib
    from OCP.Quantity import Quantity_ColorRGBA
    from OCP.TDF import TDF_Label, TDF_LabelSequence
    from OCP.TopAbs import TopAbs_FACE
    from OCP.TopExp import TopExp, TopExp_Explorer
    from OCP.TopTools import TopTools_IndexedMapOfShape
    from OCP.XCAFDoc import XCAFDoc_ColorCurv, XCAFDoc_ColorGen, XCAFDoc_ColorSurf, XCAFDoc_ColorTool
    from OCP.XCAFDoc import XCAFDoc_DocumentTool, XCAFDoc_ShapeTool

    from cadgen.engine.document import _entry, _label_material, _label_name, material_json, step_name
    from cadgen.engine.kernel import imported

    tool = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    colors = XCAFDoc_DocumentTool.ColorTool_s(doc.Main())
    kinds = (XCAFDoc_ColorCurv, XCAFDoc_ColorGen, XCAFDoc_ColorSurf) if step else (XCAFDoc_ColorSurf, XCAFDoc_ColorGen)

    def name_of(label: Any) -> str:
        if not step:
            return _label_name(label)
        text = step_name(_label_name(label))
        return "".join(ch for ch in text if unicodedata.category(ch)[0] != "C")  # as the file has it

    def label_color(label: Any) -> list[float] | None:
        rgba = Quantity_ColorRGBA()
        for kind in kinds:
            if XCAFDoc_ColorTool.GetColor_s(label, kind, rgba):
                return _rgba(rgba)
        return None

    shape_colors: dict[Any, Any] = {}

    def own_color(shape: Any) -> list[float] | None:
        key = shape.TShape()
        if key not in shape_colors:
            rgba = Quantity_ColorRGBA()
            shape_colors[key] = _rgba(rgba) if any(colors.GetColor(shape, kind, rgba) for kind in kinds) else None
        return shape_colors[key]

    def shape_color(shape: Any) -> list[float] | None:
        found = own_color(shape)
        if found is not None:
            return found
        best, extent = None, -1.0
        explorer = TopExp_Explorer(shape, TopAbs_FACE)
        while explorer.More():
            face = explorer.Current()
            color = own_color(face)
            if color is not None:
                box = Bnd_Box()
                BRepBndLib.Add_s(face, box)
                if box.SquareExtent() > extent:
                    best, extent = color, box.SquareExtent()
            explorer.Next()
        return best

    def faces_given(label: Any, shape: Any) -> tuple[dict[str, list[float]], dict[str, Any]]:
        """An xbf part's painted faces and face materials, by ordinal."""
        paints: dict[str, list[float]] = {}
        given: dict[str, Any] = {}
        subs = TDF_LabelSequence()
        XCAFDoc_ShapeTool.GetSubShapes_s(label, subs)
        faces = None
        for at in range(1, subs.Length() + 1):
            sub = subs.Value(at)
            held = XCAFDoc_ShapeTool.GetShape_s(sub)
            if held.IsNull() or held.ShapeType() != TopAbs_FACE:
                continue
            if faces is None:
                faces = TopTools_IndexedMapOfShape()
                TopExp.MapShapes_s(shape, TopAbs_FACE, faces)
            ordinal = faces.FindIndex(held)
            if not ordinal:
                continue
            material = _label_material(sub)
            if material is not None:
                given[str(ordinal)] = material_json(material)
                continue
            color = label_color(sub)
            if color is not None:
                paints[str(ordinal)] = color
        return paints, given

    products: list[dict[str, Any]] = []
    index: dict[str, int] = {}
    shapes: list[Any] = []
    locations: list[Any] = []
    held_names: dict = {}

    def product(label: Any) -> int:
        key = _entry(label)
        found = index.get(key)
        if found is not None:
            return found
        topods = XCAFDoc_ShapeTool.GetShape_s(label)
        assembly = XCAFDoc_ShapeTool.IsAssembly_s(label)
        color = label_color(label)
        if color is None and step and not assembly:
            color = shape_color(topods)
        record: dict[str, Any] = {"name": name_of(label), "color": color, "assembly": assembly}
        found = index[key] = len(products)
        products.append(record)
        if assembly:
            components = TDF_LabelSequence()
            XCAFDoc_ShapeTool.GetComponents_s(label, components, False)
            record["components"] = [component(components.Value(at)) for at in range(1, components.Length() + 1)]
        else:
            record["shape"] = len(shapes)
            shapes.append(topods)
            names = imported.names(label, topods, held_names)  # what the file names its elements
            record["names"] = {str(kind): {str(o): text for o, text in found_names.items()}
                               for kind, found_names in names.items()}
            record["material"] = material_json(_label_material(label))
            if not step:
                record["paints"], record["face_materials"] = faces_given(label, topods)
        return found

    def component(label: Any) -> dict[str, Any]:
        referred = label
        if XCAFDoc_ShapeTool.IsReference_s(label):
            referred = TDF_Label()
            XCAFDoc_ShapeTool.GetReferredShape_s(label, referred)
        own = referred is not label
        at = len(locations)
        locations.append(XCAFDoc_ShapeTool.GetLocation_s(label))
        return {"product": product(referred), "name": name_of(label) if own else "",
                "color": label_color(label) if own else None, "location": at}

    free = TDF_LabelSequence()
    tool.GetFreeShapes(free)
    roots = [component(free.Value(at)) for at in range(1, free.Length() + 1)]
    return {"products": products, "roots": roots}, shapes, locations


def _material(found: dict[str, Any] | None) -> Any:
    from cadgen.engine.document import material_from_json

    return material_from_json(found)


def assemble(header: dict[str, Any], shapes: list[Any], locations: list[Any]) -> Any:
    """The build123d tree a description makes (see the module): the free shape's node, or a
    ``Compound`` of the free shapes' nodes when the document has several."""
    from build123d import Compound, Location
    from build123d.importers import topods_lut
    from build123d.topology.shape_core import downcast

    from cadgen.engine.colors import color as as_color
    from cadgen.engine.kernel import imported
    from cadgen.engine.kernel.memo import FACE_COLORS, FACE_MATERIALS

    from cadgen.engine.document import MAX_ASSEMBLY_DEPTH, MAX_OCCURRENCES

    products = header["products"]
    counted = 0

    def build(entries: list[dict[str, Any]], ancestors: frozenset = frozenset()) -> list[Any]:
        # A shared product is built once per placement: bound the tree (as Loaded's walk does).
        nonlocal counted
        if len(ancestors) > MAX_ASSEMBLY_DEPTH:
            raise ValueError(f"the document's assembly is deeper than {MAX_ASSEMBLY_DEPTH} levels")
        made = []
        for entry in entries:
            counted += 1
            if counted > MAX_OCCURRENCES:
                raise ValueError(f"the document's assembly names more than {MAX_OCCURRENCES} occurrences")
            found = products[entry["product"]]
            if found["assembly"]:
                if entry["product"] in ancestors:
                    raise ValueError("the document's assembly contains itself")
                node = Compound()
                node.children = build(found["components"], ancestors | {entry["product"]})
            else:
                topods = downcast(shapes[found["shape"]])
                node = topods_lut[type(topods)](downcast(topods.Located(topods.Location())))
                names = {int(kind): {int(o): text for o, text in held.items()}
                         for kind, held in (found.get("names") or {}).items()}
                if names:
                    node.__dict__[imported.ELEMENT_NAMES] = names
                material = _material(found.get("material"))
                if material is not None:
                    node.material = material
                if found.get("paints"):
                    node.__dict__[FACE_COLORS] = {int(o): tuple(rgba) for o, rgba in found["paints"].items()}
                if found.get("face_materials"):
                    node.__dict__[FACE_MATERIALS] = {int(o): _material(given)
                                                     for o, given in found["face_materials"].items()}
            color = entry["color"] or found["color"]
            node.color = None if color is None else as_color(color)
            node.label = entry["name"] or found["name"]
            node.move(Location(locations[entry["location"]]))
            made.append(node)
        return made

    root = Compound()
    root.children = build(header["roots"])
    return root.children[0] if len(root.children) == 1 else root


# --- the wire: shapes and locations as one BinTools dump ----------------------------------------


def pack(shapes: list[Any], locations: list[Any]) -> bytes:
    """Every shape, then a marker (an empty compound) at each location, in one compound's
    ``BinTools`` dump."""
    from OCP.BinTools import BinTools, BinTools_FormatVersion_VERSION_4
    from OCP.BRep import BRep_Builder
    from OCP.TopoDS import TopoDS_Compound

    builder = BRep_Builder()
    holder = TopoDS_Compound()
    builder.MakeCompound(holder)
    for shape in shapes:
        builder.Add(holder, shape)
    for location in locations:
        marker = TopoDS_Compound()
        builder.MakeCompound(marker)
        builder.Add(holder, marker.Located(location))
    stream = io.BytesIO()
    BinTools.Write_s(holder, stream, False, False, BinTools_FormatVersion_VERSION_4)
    return stream.getvalue()


def unpack(data: bytes, shapes: int) -> tuple[list[Any], list[Any]]:
    """``pack``'s shapes and locations, read back."""
    from OCP.BinTools import BinTools
    from OCP.TopoDS import TopoDS_Iterator, TopoDS_Shape

    holder = TopoDS_Shape()
    BinTools.Read_s(holder, io.BytesIO(data))
    found = []
    iterator = TopoDS_Iterator(holder, True, True)
    while iterator.More():
        found.append(iterator.Value())
        iterator.Next()
    return found[:shapes], [marker.Location() for marker in found[shapes:]]


# --- the reader process -----------------------------------------------------------------------


def _parse(path: str) -> tuple[dict[str, Any], bytes]:
    """A STEP read into an XCAF document and described, in this process: the description and
    the packed shapes and locations."""
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.Interface import Interface_Static
    from OCP.STEPCAFControl import STEPCAFControl_Reader
    from OCP.TCollection import TCollection_ExtendedString
    from OCP.TDocStd import TDocStd_Document

    doc = TDocStd_Document(TCollection_ExtendedString("XCAF"))
    reader = STEPCAFControl_Reader()
    reader.SetNameMode(True)
    reader.SetColorMode(True)
    reader.SetLayerMode(True)
    reader.SetMatMode(True)
    Interface_Static.SetIVal_s("read.stepcaf.subshapes.name", 1)  # the names the file gives elements
    if reader.ReadFile(os.fspath(path)) != IFSelect_RetDone:
        raise ValueError(f"cannot read the STEP file {path}")
    from cadgen.engine.document import refuse_external_files

    refuse_external_files(reader, path)
    reader.Transfer(doc)
    header, shapes, locations = describe(doc, step=True)
    header["shapes"] = len(shapes)
    return header, pack(shapes, locations)


class Reader:
    """A reader process (see the module): started on its first read, one read at a time."""

    def __init__(self) -> None:
        self.process: subprocess.Popen | None = None
        self.lock = threading.Lock()
        self.reads = 0

    def _start(self) -> subprocess.Popen:
        from cadgen.engine.daemon import windowless

        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        env = dict(os.environ)
        path = env.get("PYTHONPATH", "")
        if root not in path.split(os.pathsep):
            env["PYTHONPATH"] = os.pathsep.join(item for item in (root, path) if item)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        return subprocess.Popen([sys.executable, "-P", "-m", "cadgen.engine.reader"], stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE, env=env, **windowless())

    def read(self, path: str) -> tuple[dict[str, Any], bytes]:
        """The description of the STEP at ``path`` and its packed shapes and locations."""
        with self.lock:
            if self.process is None or self.process.poll() is not None:
                self.process = self._start()
            process = self.process
            assert process.stdin is not None and process.stdout is not None
            try:
                process.stdin.write((json.dumps({"path": os.fspath(path)}) + "\n").encode())
                process.stdin.flush()
                line = process.stdout.readline()
            except (BrokenPipeError, OSError):
                line = b""
            if not line:
                self.process = None
                code = process.wait()
                raise ValueError(f"the STEP reader exited ({code}) reading {path}")
            answer = json.loads(line)
            if "error" in answer:
                raise ValueError(answer["error"])
            size = int(answer["bytes"])
            chunks, left = [], size
            while left:
                chunk = process.stdout.read(left)
                if not chunk:
                    self.process = None
                    raise ValueError(f"the STEP reader exited inside its answer for {path}")
                chunks.append(chunk)
                left -= len(chunk)
            self.reads += 1
            return answer["header"], b"".join(chunks)

    def close(self) -> None:
        with self.lock:
            process, self.process = self.process, None
        if process is None:
            return
        try:
            if process.stdin is not None:
                process.stdin.close()
            process.wait(timeout=30)
        except Exception:  # noqa: BLE001 - a reader that will not go is stopped
            process.kill()
            process.wait()
        if process.stdout is not None:
            process.stdout.close()


_SESSION: list[Reader] = []
_SESSION_LOCK = threading.Lock()


@contextmanager
def session() -> Iterator[Reader]:
    """One build's reader: every STEP the build reads is parsed by it, and it exits when the
    build ends (it starts only if the build reads one)."""
    reader = Reader()
    with _SESSION_LOCK:
        _SESSION.append(reader)
    try:
        yield reader
    finally:
        with _SESSION_LOCK:
            _SESSION.remove(reader)
        reader.close()


def written_by_build(path: Any) -> str | None:
    """The model of the build running on this thread that writes ``path`` -- its identity,
    ``script.py::model`` -- or None: outside a build, or for a file no model of the build
    declares. The build's models are its script's (the one running and its siblings) and the
    children it has called."""
    from pathlib import Path

    from cadgen.engine import model as engine_model

    context = getattr(engine_model._CONTEXT, "build", None)
    keys = [] if context is None else [*context.stack, *context.results]
    if not keys:
        return None
    by_file: dict[str, Any] = {}
    for module in list(sys.modules.values()):
        file = getattr(module, "__file__", None)
        if isinstance(file, str) and file.endswith(".py"):
            by_file.setdefault(os.path.normcase(os.path.abspath(file)), module)

    def module_of(script: str) -> Any:
        found = by_file.get(os.path.normcase(script))
        if found is None:  # a module imported through a link: by the file it is
            wanted = Path(script).resolve()
            found = next((module for file, module in by_file.items() if Path(file).resolve() == wanted), None)
            by_file[os.path.normcase(script)] = found
        return found

    root = keys[0].rpartition("::")[0]
    held = module_of(root)
    found = list(engine_model.models_in(vars(held), Path(root))) if held is not None else []
    for key in keys:
        script, _sep, name = key.rpartition("::")
        held = module_of(script) if name.isidentifier() else None
        candidate = getattr(held, name, None) if held is not None else None
        if isinstance(candidate, engine_model.Model) and candidate not in found:
            found.append(candidate)
    wanted = Path(os.fspath(path)).resolve()
    for candidate in found:
        if any(Path(out).resolve() == wanted for _kind, out in candidate.targets()):
            return candidate.identity
    return None


def refuse_written(path: Any, verb: str) -> None:
    """Refuse a read, by a model of the build running on this thread, of a file the build writes
    (``written_by_build``): see the module."""
    writer = written_by_build(path)
    if writer is not None:
        raise ValueError(f"{verb} {os.fspath(path)}: this build writes it ({writer}), and a model reads no file "
                         "its own build writes; take it from the live shape instead, or call the model that makes it")


def read_step(path: Any) -> Any:
    """A STEP file as a build123d compound tree (see the module), parsed by the build's
    reader process, or by one of its own outside a build."""
    refuse_written(path, "read_step")
    with _SESSION_LOCK:
        reader = _SESSION[-1] if _SESSION else None
    own = reader is None
    reader = Reader() if own else reader
    try:
        header, data = reader.read(os.path.abspath(os.fspath(path)))
    finally:
        if own:
            reader.close()
    shapes, locations = unpack(data, header["shapes"])
    del data
    return assemble(header, shapes, locations)


def read_xbf(path: Any) -> Any:
    """An engine document (``.xbf``) as a build123d compound tree (see the module), read in
    this process: names, colours, materials, painted faces and element names as the document
    holds them; its mechanism and configurations are not imported."""
    from pathlib import Path

    from cadgen.engine.document import _read

    path = Path(os.fspath(path))
    if path.suffix.lower() != ".xbf":
        raise ValueError(f"read_xbf reads an .xbf, not {path.name}: read a STEP with read_step")
    refuse_written(path, "read_xbf")
    if not path.is_file():
        raise FileNotFoundError(f"no document {path}")
    doc = _read(path)
    header, shapes, locations = describe(doc, step=False)
    return assemble(header, shapes, locations)


# --- a mesh read as data ------------------------------------------------------------------------


class Mesh:
    """A mesh file as data (see the module): ``vertices`` (N x 3, float64: the file's numbers as
    millimetres -- an STL says no unit), ``triangles`` (M x 3, int64: each a row of indices into
    ``vertices``, in the file's order) and ``name`` (an ASCII STL's solid's, else the file's
    stem). Corners at one point are one vertex, in the order the file first has them. Both arrays
    are read-only: a later build's read of the same bytes hands back this very object."""

    __slots__ = ("vertices", "triangles", "name")
    # A value the memo keeps as it is and hands back on a hit (``memo._snapshot``).
    __kernel_value__ = True

    def __init__(self, vertices: Any, triangles: Any, name: str) -> None:
        vertices.flags.writeable = False
        triangles.flags.writeable = False
        self.vertices, self.triangles, self.name = vertices, triangles, name

    def bounding_box(self) -> Any:
        """The box of its vertices as build123d's ``BoundBox`` (``.size``, ``.min``, ``.max``,
        ``.center()``): what a model sizes or places B-rep by."""
        from build123d import BoundBox
        from OCP.Bnd import Bnd_Box
        from OCP.gp import gp_Pnt

        if not len(self.vertices):
            raise ValueError(f"the mesh {self.name!r} has no triangles, so no box")
        low, high = self.vertices.min(axis=0), self.vertices.max(axis=0)
        return BoundBox(Bnd_Box(gp_Pnt(*(float(value) for value in low)), gp_Pnt(*(float(value) for value in high))))

    def __repr__(self) -> str:
        return f"Mesh({self.name!r}: {len(self.vertices)} vertices, {len(self.triangles)} triangles)"


def _stl(path: Any) -> tuple[Any, str]:
    """An STL's corners, (M, 3, 3) float64, read by the engine's one STL parser
    (``formats/stl.read_stl``: binary or ASCII told as three's ``STLLoader`` tells them), and its
    name: an ASCII STL's solid's, else the file's stem."""
    import re

    from cadgen.engine.formats.stl import read_stl

    corners = read_stl(path)
    with open(path, "rb") as handle:
        head = handle.read(4096)
    named = re.match(rb"[^s]{0,4}solid[ \t]*([^\r\n]*)", head)
    binary = len(head) >= 84 and 84 + 50 * int.from_bytes(head[80:84], "little") == path.stat().st_size
    name = named[1].strip().decode("utf-8", "replace") if named and not binary else ""
    return corners, name or path.stem


def _welded(corners: Any) -> tuple[Any, Any]:
    """Triangle corners as vertices -- each point once, in the order the corners first hold it
    -- and the triangles as rows of their indices."""
    import numpy as np

    points = corners.reshape(-1, 3)
    if not len(points):
        return np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int64)
    unique, first, inverse = np.unique(points, axis=0, return_index=True, return_inverse=True)
    order = np.argsort(first, kind="stable")
    rank = np.empty(len(order), dtype=np.int64)
    rank[order] = np.arange(len(order))
    return np.ascontiguousarray(unique[order]), rank[inverse.reshape(-1)].reshape(-1, 3)


def _read_mesh(path: str) -> Mesh:
    from pathlib import Path

    found = Path(path)
    if not found.is_file():
        raise FileNotFoundError(f"no mesh {found}")
    corners, name = _stl(found)
    vertices, triangles = _welded(corners)
    return Mesh(vertices, triangles, name)


_READ_MESH: Any = None


def read_mesh(path: Any) -> Mesh:
    """A mesh file (``MESH_SUFFIXES``: an ``.stl``) as data, never a shape (``Mesh``: its
    vertices, triangles and name, and ``bounding_box()``): what a model sizes or places B-rep
    by. In a build the read is the model's own, keyed by the file's bytes as ``read_step``'s is
    (one of the closure's ``inputs``): a later build's read of the same bytes is this object, and
    a changed file runs the body that reads it. A file a model of the build writes is refused."""
    global _READ_MESH
    from pathlib import Path

    suffix = Path(os.fspath(path)).suffix.lower()
    if suffix not in MESH_SUFFIXES:
        other = {".step": "a STEP with read_step", ".stp": "a STEP with read_step", ".xbf": "an xbf with read_xbf"}
        raise ValueError(f"read_mesh reads an .stl, not {Path(os.fspath(path)).name}"
                         + (f": read {other[suffix]}" if suffix in other else ""))
    refuse_written(path, "read_mesh")  # before the memo, as read_step's
    if _READ_MESH is None:
        from cadgen.engine.kernel.memo import wrap_function

        _READ_MESH = wrap_function("read_mesh", _read_mesh)
    return _READ_MESH(os.fspath(path))


def main() -> int:
    """The reader process: one ``{"path"}`` line per read on stdin, each answered on stdout by
    ``{"header", "bytes"}`` and the packed bytes, or ``{"error"}``; it exits when stdin closes."""
    sys.dont_write_bytecode = True
    out = os.fdopen(os.dup(1), "wb")
    os.dup2(2, 1)  # the kernel's prints go to stderr, never into an answer
    sys.stdout = sys.stderr
    for line in sys.stdin:
        if not line.strip():
            continue
        path = json.loads(line)["path"]
        try:
            header, data = _parse(path)
            out.write(json.dumps({"header": header, "bytes": len(data)}, separators=(",", ":")).encode() + b"\n")
            out.write(data)
        except Exception as error:  # noqa: BLE001 - a file it cannot read is the build's error, said
            out.write(json.dumps({"error": f"{type(error).__name__}: {error}"}).encode() + b"\n")
        out.flush()
        del line
    return 0


if __name__ == "__main__":
    sys.exit(main())
