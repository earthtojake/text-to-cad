"""A 3MF read with the standard library: its model part (``3D/3dmodel.model``, or the part its
package relationships name), the objects, the components and the build items that place them,
each triangle's colour, and the model's ``unit``.

- **Objects**: a mesh object is a part (its vertices and triangles); a components object places
  other objects (a component's ``transform``, and its production-extension ``path`` to another
  model part of the package); a build item places an object in the scene. Every placement is the
  product down the build (3MF's 3x4 row-vector transforms), so an object placed twice is one part
  placed twice. A part is named by its object's ``name``, else by its place in the build.
- **Colours**: a triangle's ``pid``/``p1`` (else its object's ``pid``/``pindex``) name a property:
  a base material's ``displaycolor``, or a colour group's ``color`` (sRGB ``#RRGGBB[AA]``); a base
  material's display properties (``pbmetallic``) give its finish: metallic and roughness. A base
  material a slicer generated (named ``default``, in ``#fafafb`` or ``#b6c4ce``) is no colour at
  all, as the viewer has it: the part takes the look's fill. A texture coordinate group, a
  composite and a multi-property name no colour either.
- **Units**: ``unit`` (micron, millimeter, centimeter, inch, foot, meter; millimeter when absent,
  any other refused, as the viewer refuses it) gives the millimetres a number is (``Model.unit``);
  the numbers themselves are kept, for a robot's link mesh, whose
  description's mesh scale says what they are.

The XML is read in two parts, for speed (a robot's link meshes can be a hundred megabytes of it):
each ``<mesh>`` is cut out of the model part first and its vertices and triangles read with
patterns into numpy, an attribute at a time; the rest -- resources, objects, components, the
build -- is parsed as XML. A triangle that names its own property (``pid``, ``p1``) is read
element by element.
"""

from __future__ import annotations

import posixpath
import re
import zipfile
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import xml.etree.ElementTree as ET

import numpy as np

__all__ = ["Model", "ThreeMfError", "read_3mf"]

UNITS = {"micron": 0.001, "millimeter": 1.0, "centimeter": 10.0, "inch": 25.4, "foot": 304.8, "meter": 1000.0}
GENERATED = ({"default"}, {"#fafafb", "#b6c4ce"})
# A package is a zip: what a read takes out of it is bounded, so a small file cannot unpack into
# more than the reader can hold. At most this many entries; at most this many bytes of model parts
# in all; and a part past ``RATIO_FROM`` bytes at most ``MAX_RATIO`` times the bytes it is stored
# in (a mesh's XML packs some ten to one; padding packs a thousand to one).
MAX_ENTRIES = 10_000
MAX_UNPACKED = 1 << 30
MAX_RATIO = 100
RATIO_FROM = 1 << 20


# A triangle element whole; an attribute; an attribute's name; an attribute's value.
_TRIANGLE = re.compile(rb"<(?:[\w.-]+:)?triangle\b([^>]*)>")
_ATTRIBUTE = re.compile(rb"([\w:.-]+)\s*=\s*(?:\"([^\"]*)\"|'([^']*)')")


_NAMES = re.compile(rb"\s([\w:.-]+)\s*=")
_QUOTED = re.compile(rb"=\s*[\"']([^\"']*)[\"']")


def _values(body: bytes, element: bytes, attribute: bytes) -> list[bytes]:
    """Every ``attribute`` of every ``element`` in ``body``, in order (each element has one)."""
    return re.findall(rb"<(?:[\w.-]+:)?" + element + rb"\b[^>]*?\s" + attribute + rb"\s*=\s*[\"']([^\"']*)[\"']", body)


def _table(body: bytes, element: bytes, attributes: tuple[bytes, ...], dtype: Any) -> np.ndarray:
    """The ``attributes`` of every ``element`` in ``body`` as a table, a row an element: read in one
    pass where the elements name exactly those attributes, in the order the first and the last
    element name them (as writers write them), else an attribute at a time. Raises
    ``ValueError`` when an element lacks one."""
    tag = b"<" + element
    count = body.count(tag + b" ") + body.count(tag + b"\t") + body.count(tag + b"\n")
    if not count:
        count = len(re.findall(rb"<(?:[\w.-]+:)?" + element + rb"\b", body))
    head = body.find(tag)
    tail = body.rfind(tag)
    first = _NAMES.findall(body[head:body.find(b">", head)]) if head >= 0 else []
    last = _NAMES.findall(body[tail:body.find(b">", tail)]) if tail >= 0 else []
    values = _QUOTED.findall(body) if sorted(first) == sorted(attributes) and first == last else []
    if values and len(values) == count * len(attributes):
        table = np.array(values, dtype=dtype).reshape(count, len(attributes))
        return table[:, [first.index(name) for name in attributes]]
    columns = [_values(body, element, attribute) for attribute in attributes]
    if any(len(column) != count for column in columns):
        raise ValueError(f"a {element.decode()} lacks one of {b', '.join(attributes).decode()}")
    return np.array(columns, dtype=dtype).T.reshape(count, len(attributes))


def _cut(data: bytes) -> tuple[bytes, list[bytes]]:
    """The model part with each ``<mesh>``'s body cut out (``<mesh cadgen-block="N"/>`` in its
    place), and the bodies: what the XML parser need not walk."""
    pieces, bodies, at = [], [], 0
    while True:
        start = data.find(b"<mesh", at)
        if start < 0 or data[start + 5:start + 6] not in (b">", b" ", b"/", b"\t", b"\n", b"\r"):
            if start < 0:
                break
            pieces.append(data[at:start + 5])
            at = start + 5
            continue
        close = data.find(b">", start)
        if close < 0:
            raise ValueError("a <mesh> tag never closes")
        if data[close - 1:close] == b"/":
            body, end = b"", close + 1
        else:
            stop = data.find(b"</mesh", close)
            if stop < 0:
                raise ValueError("a <mesh> never ends")
            body, end = data[close + 1:stop], data.find(b">", stop) + 1
        pieces.append(data[at:start])
        pieces.append(b'<mesh cadgen-block="%d"/>' % len(bodies))
        bodies.append(body)
        at = end
    pieces.append(data[at:])
    return b"".join(pieces), bodies


class ThreeMfError(ValueError):
    """A file that does not read as a 3MF, said by name."""


@dataclass
class Part:
    """A mesh object: its points (as the file's numbers), its triangles, each triangle's paint
    (an index into ``Model.paints``, -1 for none)."""

    name: str
    points: np.ndarray
    triangles: np.ndarray
    paints: np.ndarray


@dataclass
class Model:
    unit: float  # millimetres per number
    parts: list[Part] = field(default_factory=list)
    # Each placement: (part index, 4x4 row-major in the file's numbers, the place in the build, 1-based).
    placed: list[tuple[int, np.ndarray, tuple[int, ...]]] = field(default_factory=list)
    # Each paint: (linear rgba, a material {metallic, roughness} or None).
    paints: list[tuple[tuple[float, float, float, float], dict[str, float] | None]] = field(default_factory=list)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _attribute(element: ET.Element, name: str) -> str:
    """An attribute by its local name, whatever namespace it is in (``p:path``)."""
    found = element.get(name)
    if found is not None:
        return found
    for key, value in element.attrib.items():
        if _local(key) == name:
            return value
    return ""


def _children(element: ET.Element | None, name: str) -> list[ET.Element]:
    return [child for child in (element if element is not None else []) if _local(child.tag) == name]


def _transform(text: str) -> np.ndarray:
    """3MF's ``m00 m01 m02 m10 ... m32`` (row vectors times the matrix) as a 4x4 acting on columns."""
    matrix = np.eye(4)
    values = [float(value) for value in text.split()] if text.strip() else []
    if len(values) == 12:
        matrix[:3, :3] = np.array(values[:9]).reshape(3, 3).T
        matrix[:3, 3] = values[9:]
    return matrix


def _linear(text: str) -> tuple[float, float, float, float] | None:
    value = text.strip().lstrip("#")
    if len(value) not in (6, 8):
        return None
    try:
        channels = [int(value[at:at + 2], 16) / 255 for at in range(0, len(value), 2)]
    except ValueError:
        return None
    rgb = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels[:3]]
    return (round(rgb[0], 6), round(rgb[1], 6), round(rgb[2], 6), round(channels[3] if len(channels) > 3 else 1.0, 6))


class _Unpacked:
    """The bytes a read has taken out of its package, refused past the bounds above."""

    def __init__(self, path: Path) -> None:
        self.path, self.total = path, 0

    def read(self, package: zipfile.ZipFile, name: str) -> bytes:
        info = package.getinfo(name)  # KeyError: no such part
        allowed = MAX_UNPACKED - self.total
        if info.file_size > RATIO_FROM:
            allowed = min(allowed, max(info.compress_size, 1) * MAX_RATIO)
        if info.file_size > allowed:
            raise ThreeMfError(self.refusal(name))
        try:
            with package.open(info) as stream:  # the declared size is the file's word: read no more than allowed
                data = stream.read(allowed + 1)
        except (zipfile.BadZipFile, zlib.error, NotImplementedError, EOFError, OSError) as error:
            raise ThreeMfError(f"{self.path.name}: {name} does not unpack ({error})") from None
        if len(data) > allowed:
            raise ThreeMfError(self.refusal(name))
        self.total += len(data)
        return data

    def refusal(self, name: str) -> str:
        return (f"{self.path.name}: {name} unpacks to more than a 3MF reader holds "
                f"({MAX_UNPACKED >> 20} MB in all, {MAX_RATIO} times its packed size)")


def _start(package: zipfile.ZipFile, unpacked: _Unpacked) -> str:
    """The model part the package's relationships name (``3D/3dmodel.model`` when none do)."""
    try:
        root = ET.fromstring(unpacked.read(package, "_rels/.rels"))
    except (KeyError, ET.ParseError):
        return "3D/3dmodel.model"
    for relationship in root:
        if str(relationship.get("Type") or "").endswith("/3dmodel"):
            return str(relationship.get("Target") or "").lstrip("/")
    return "3D/3dmodel.model"


def read_3mf(path: Path) -> Model:
    """The 3MF at ``path`` (see the module docstring)."""
    path = Path(path)
    try:
        package = zipfile.ZipFile(path)
    except (OSError, zipfile.BadZipFile) as error:
        raise ThreeMfError(f"{path.name} is not a 3MF package: {error}") from None
    with package:
        if len(package.infolist()) > MAX_ENTRIES:
            raise ThreeMfError(f"{path.name} lists more than {MAX_ENTRIES} entries: more than a 3MF reader opens")
        names = set(package.namelist())
        unpacked = _Unpacked(path)
        documents: dict[str, ET.Element] = {}
        blocks: dict[str, list[bytes]] = {}  # each part's mesh bodies, by the index its mesh element names

        def document(name: str) -> ET.Element:
            name = name.lstrip("/")
            if name not in documents:
                if name not in names:
                    raise ThreeMfError(f"{path.name} names a model part {name!r} it does not hold")
                data = unpacked.read(package, name)
                try:
                    stripped, found = _cut(data)
                    documents[name] = ET.fromstring(stripped)
                except (ET.ParseError, ValueError) as error:
                    raise ThreeMfError(f"{path.name}: {name} is not XML ({error})") from None
                blocks[name] = found
            return documents[name]

        start = _start(package, unpacked)
        root = document(start)
        declared = str(root.get("unit") or "millimeter")
        if declared.strip().lower() not in UNITS:
            # As the viewer refuses it (``sceneUnits.js``): a number of no known length is no millimetre.
            raise ThreeMfError(f'{path.name}: its model unit "{declared}" is not one the 3MF specification '
                               f'defines ({", ".join(UNITS)})')
        model = Model(UNITS[declared.strip().lower()])
        paint_of: dict[tuple, int] = {}
        properties: dict[tuple[str, str], list[int]] = {}  # (part, group id): paint per index
        objects: dict[tuple[str, str], ET.Element] = {}
        made: dict[tuple[str, str], int] = {}

        def paint(rgba: tuple | None, finish: dict[str, float] | None) -> int:
            if rgba is None:
                return -1
            key = (rgba, tuple(sorted((finish or {}).items())))
            if key not in paint_of:
                paint_of[key] = len(model.paints)
                model.paints.append((rgba, finish))
            return paint_of[key]

        loaded: set[str] = set()

        def resources(name: str) -> None:
            """The part's property groups and objects, once."""
            if name in loaded:
                return
            loaded.add(name)
            found = _children(document(name), "resources")
            holder = found[0] if found else None
            finishes: dict[str, list[dict[str, float]]] = {}
            for group in _children(holder, "pbmetallicdisplayproperties"):
                finishes[str(group.get("id"))] = [
                    {"metallic": float(_attribute(item, "metallicness") or 0), "roughness": float(_attribute(item, "roughness") or 1)}
                    for item in _children(group, "pbmetallic")]
            for group in _children(holder, "basematerials"):
                display = finishes.get(_attribute(group, "displaypropertiesid"), [])
                row = []
                for index, base in enumerate(_children(group, "base")):
                    colour = str(base.get("displaycolor") or "")
                    generated = (str(base.get("name") or "").strip().lower() in GENERATED[0]
                                 and colour.lower()[:7] in GENERATED[1])
                    row.append(-1 if generated else paint(_linear(colour), display[index] if index < len(display) else None))
                properties[(name, str(group.get("id")))] = row
            for group in _children(holder, "colorgroup"):
                properties[(name, str(group.get("id")))] = [paint(_linear(str(_attribute(item, "color") or "")), None)
                                                            for item in _children(group, "color")]
            for item in _children(holder, "object"):
                objects[(name, str(item.get("id")))] = item

        def mesh_part(name: str, element: ET.Element, label: str) -> int:
            key = (name, str(element.get("id")))
            if key in made:
                return made[key]
            body = blocks[name][int(_children(element, "mesh")[0].get("cadgen-block"))]
            start, end = body.find(b"<triangles"), body.rfind(b"</triangles")
            vertices_body, triangles_body = (body[:start], body[start:end]) if start >= 0 else (body, b"")
            try:
                points = _table(vertices_body, b"vertex", (b"x", b"y", b"z"), np.float64)
                if b"p1" in triangles_body or b"pid" in triangles_body:  # optional attributes: one at a time
                    triangles = np.array([_values(triangles_body, b"triangle", corner) for corner in (b"v1", b"v2", b"v3")],
                                         dtype=np.int64).T.reshape(-1, 3)
                else:
                    triangles = _table(triangles_body, b"triangle", (b"v1", b"v2", b"v3"), np.int64)
            except ValueError as error:
                raise ThreeMfError(f"{path.name}: object {element.get('id')}'s mesh does not read ({error})") from None
            default_group, default_index = str(element.get("pid") or ""), str(element.get("pindex") or "")
            row = properties.get((name, default_group))
            default = row[int(default_index)] if row is not None and default_index.isdigit() and int(default_index) < len(row) else -1
            paints = np.full(len(triangles), default, np.int64)
            if b"p1" in triangles_body or b"pid" in triangles_body:  # triangles that name their own property
                for at, match in enumerate(_TRIANGLE.finditer(triangles_body)):
                    attributes = {found.decode(): (one or two).decode() for found, one, two in _ATTRIBUTE.findall(match.group(1))}
                    if "pid" not in attributes and "p1" not in attributes:
                        continue
                    group = attributes.get("pid") or default_group
                    index = attributes.get("p1") or (default_index if group == default_group else "")
                    row = properties.get((name, group))
                    paints[at] = row[int(index)] if row is not None and index.isdigit() and int(index) < len(row) else -1
            if len(points) and len(triangles) and (triangles.min() < 0 or triangles.max() >= len(points)):
                raise ThreeMfError(f"{path.name}: object {element.get('id')} has a triangle naming a vertex it lacks")
            made[key] = len(model.parts)
            model.parts.append(Part(str(element.get("name") or "").strip() or label, points, triangles, paints))
            return made[key]

        # An object listed by several components is placed once for each, so a small file can name
        # an exponential build: bounded as a document's assembly is.
        from cadgen.engine.document import MAX_ASSEMBLY_DEPTH, MAX_OCCURRENCES

        visited = 0

        def place(name: str, ident: str, matrix: np.ndarray, at: tuple[int, ...], trail: tuple) -> None:
            nonlocal visited
            visited += 1
            if visited > MAX_OCCURRENCES:
                raise ThreeMfError(f"{path.name}: its build names more than {MAX_OCCURRENCES} occurrences")
            if len(trail) >= MAX_ASSEMBLY_DEPTH:
                raise ThreeMfError(f"{path.name}: its components nest deeper than {MAX_ASSEMBLY_DEPTH} levels")
            resources(name)
            element = objects.get((name, ident))
            if element is None:
                raise ThreeMfError(f"{path.name}: the build names object {ident}, which {name} does not hold")
            if (name, ident) in trail:
                raise ThreeMfError(f"{path.name}: object {ident} holds itself")
            if _children(element, "mesh"):
                model.placed.append((mesh_part(name, element, f"Object {'.'.join(map(str, at))}"), matrix, at))
            for index, component in enumerate(_children(_children(element, "components")[0], "component")
                                              if _children(element, "components") else [], 1):
                target = _attribute(component, "path")
                part = posixpath.normpath(posixpath.join(posixpath.dirname("/" + name), target)).lstrip("/") \
                    if target else name
                place(part, str(component.get("objectid")), matrix @ _transform(str(component.get("transform") or "")),
                      (*at, index), (*trail, (name, ident)))

        resources(start)
        build = _children(root, "build")
        for index, item in enumerate(_children(build[0], "item") if build else [], 1):
            target = _attribute(item, "path")
            place(target.lstrip("/") if target else start, str(item.get("objectid")),
                  _transform(str(item.get("transform") or "")), (index,), ())
        if not model.placed:
            raise ThreeMfError(f"{path.name} builds nothing: its <build> places no object")
        return model
