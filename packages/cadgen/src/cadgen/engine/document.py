"""The document: a model's result as an XCAF document, the file it is saved as, and
the document read back.

A result becomes **prototypes** and **instances**. A prototype is a part -- one
``TShape`` in one orientation, with the face colours a model painted on it -- or an
assembly: its components, each a prototype placed at a location under a name, with
a colour where its instance's differs from its prototype's. Two nodes of the result
that hold the same geometry are one prototype placed twice -- the same TShape, as every
placement of a shape shares it, or once named the same geometry key named alike
(``merge``) -- so a part used ten times is one prototype with ten components above it. The result's tree (build123d's
compound children) gives names and colours; its geometry and placements are read
from the TopoDS compounds themselves, child by child, so a placed copy of an
assembly is placed as the kernel holds it. A part with a face that has no surface -- a
mesh's triangles alone, as build123d's ``import_stl`` makes -- is refused by its
occurrence's path before anything is made of it (``mesh_faces``): a document holds B-rep,
and the kernel's face modifier (``direct``) crashes the process on such a face.

The XCAF document: units millimetres; a name on every prototype and component; a
colour per part and per painted face; a material per part and per face given one
(``materials``), as an ``XCAFDoc_Material`` (name, description, density) and an
``XCAFDoc_VisMaterial`` (PBR: base colour, metallic, roughness, emissive, alpha), its
base colour the part's colour too so a reader of colours alone agrees; on each part's face and edge sub-shape labels
the element names the memo's history gave them (``kernel.trace``), so a face's name
survives into the file and into a STEP; and on each part the key of its geometry
(``KEY_GUID``), which a reader caches the part's tessellation by only once the part it
read makes that key again (``Loaded``). Saved with the
BinXCAF driver as ``.xbf``, atomically, and only when its bytes changed -- every
sub-shape's ``Checked`` flag written cleared (``unchecked``), so a cold build and a
warm one of the same sources write the same bytes.

An assembly whose parts carry build123d joints carries its mechanism too: links,
pairs, the ground, the as-built configuration and the named ones, as a subtree of
standard attributes beside the XCAF tools (``mechanism``).

A model's document is kept in memory between builds (``Kept``) and a warm build patches
it rather than converting every prototype again (``to_xcaf``): each shape label holds the
prototype at its place in the order, and a cold conversion makes the same labels at the
same tags, so a label whose prototype did not change is kept as it is and the rest are
made again where a cold conversion would make them. The patched document saves to the
cold one's bytes.

Read back (``Loaded``), a document is its prototypes, its instances with their world
placements, what each prototype's elements are named, and its mechanism; a STEP the
engine did not write reads the same way, with the XCAF reader.
"""

from __future__ import annotations

import functools
import hashlib
import re
import threading
from collections import OrderedDict
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator

from cadgen.engine.atomic_replace import put

__all__ = ["Assembly", "Component", "Kept", "Loaded", "Part", "Tree", "collect", "geometry_key", "load", "merge",
           "mesh_faces", "read_step_shape", "read_xbf_shape", "save", "to_xcaf", "unchecked"]

# The GUID of the attribute that holds a part's geometry key on its label.
KEY_GUID = "c8f2d4a6-1b3e-4f5a-9c7d-2e8b6a4f0d13"
# What wrote a document, on its main label: the engine's xbf format and cadgen's release.
WRITER_GUID = "c49e4620-5730-422f-808f-c1e84d7bd163"
WRITER = "cadgen.engine {format} (cadgen {release})"
# The model's build closure, on its main label beside the writer (``previous``): its engine,
# libraries, source, modules and inputs as pointers and digests, and the key over them.
CLOSURE_GUID = "2f6c9d1e-8a43-4b7e-b5d0-7e1a3c9f4b62"
# The build's animations, a build record on its main label after the closure (``animations.record``):
# the compiled tracks a GLB of the document bakes; every other reader ignores them.
ANIMATIONS_GUID = "196117b9-7763-467d-8c37-7f838602e8a5"
_XCAF_LOCK = threading.RLock()
# The last document ``to_xcaf`` made and its tree; per path, the tree last saved there.
_MADE: list = []
_SAVED: dict[Path, "Tree"] = {}


@dataclass
class Part:
    """A part prototype: its geometry at the identity (orientation kept), its name, the
    colour of its first instance, the face colours painted on it by ordinal, its
    material and its faces' by ordinal, and, once named, its element names
    (``faces``/``edges`` lists by ordinal). A part's colour is its base colour: its own
    colour, which always wins, else its own material's colour, else the material it
    inherits' colour, else the colour it inherits; a part with a material and no colour at all is drawn
    in ``DEFAULT_COLOR``. A face given a material is coloured as the material, or as
    the part where the material has no colour."""

    shape: Any
    name: str
    color: tuple | None
    face_colors: dict[int, tuple]
    key: str = ""
    names: dict[str, Any] | None = None
    origin: Any = None  # the result's object it was first seen as
    material: Any = None
    face_materials: dict[int, Any] = field(default_factory=dict)


# The base colour of a part with a material and no colour: the exports' default grey.
DEFAULT_COLOR = (0.8, 0.8, 0.8, 1.0)


@dataclass
class Component:
    prototype: "Part | Assembly"
    location: Any
    name: str
    color: tuple | None


@dataclass
class Assembly:
    name: str
    components: list[Component] = field(default_factory=list)


@dataclass
class Tree:
    """A result as prototypes: ``order`` lists every prototype once, each after the ones
    it places; ``root`` is what the document's one free shape is; ``mechanism`` what its
    joints make of it (``mechanism.harvest``), or None."""

    root: "Part | Assembly"
    order: list
    parts: list[Part]
    signature: tuple
    mechanism: Any = None
    # Its animations (``animations.harvest``), by name, or None: baked into its GLB, and kept on the
    # document's main label as a build record (``ANIMATIONS_GUID``).
    animations: Any = None
    # The model's build closure (``previous.manifest``, as text), written on the main label;
    # None for none.
    closure: str | None = None
    # What ``collect`` made of the result's joints, sequences and animations (``Harvest``), and
    # whether it was handed back rather than made (``collect``'s ``harvested``).
    harvest: "Harvest | None" = None
    reused: bool = False


@dataclass(frozen=True)
class Harvest:
    """A result's harvest: its mechanism (``mechanism.harvest``: the pairs, the states and the
    configuration sequences, a function's sampled), its animations (``animations.harvest``) and
    what of the tree's signature they are. Plain values, read and never changed by what writes
    the document or bakes the GLB, so one harvest serves every build of the same result."""

    mechanism: Any
    animations: Any
    signature: tuple


def _identity() -> Any:
    from OCP.TopLoc import TopLoc_Location

    return TopLoc_Location()


def _location_key(location: Any) -> tuple:
    if location.IsIdentity():
        return ()
    value = location.Transformation().Value
    return tuple(round(value(row, column), 12) for row in (1, 2, 3) for column in (1, 2, 3, 4))


def _rgba(color: Any) -> tuple | None:
    """A shape's colour as the document holds it, linear RGBA: build123d keeps ``shape.color``
    as a ``Color``, whose channels are sRGB, and ``colors.linear`` reads it linear, as it reads a
    hex string ``paint`` is given (the engine README's **Materials**)."""
    if color is None:
        return None
    from cadgen.engine.colors import linear

    return tuple(linear(color, "a shape's color"))


def _material(value: Any) -> Any:
    """A shape's ``material`` field as the document takes it: a ``Material``, or None for
    none (build123d's own default for a compound is the empty string)."""
    from cadgen.engine.materials import Material

    if value is None or isinstance(value, Material) or value == "":
        return value or None
    raise TypeError(f"a shape's material is a cadgen.engine.Material, not {value!r}")


def _children(topods: Any) -> list[Any]:
    from OCP.TopoDS import TopoDS_Iterator

    found = []
    iterator = TopoDS_Iterator(topods, False, False)
    while iterator.More():
        found.append(iterator.Value())
        iterator.Next()
    return found


# Per part's TShape, the ordinals of its faces with no surface (``mesh_faces``): each part walked
# once, as the parts a build keeps (``build._PARTS``) are named once.
_MESH_FACES: "OrderedDict[Any, tuple[int, ...]]" = OrderedDict()
_MESH_FACES_HELD = 1 << 16

# A document's assembly as the engine reads it: a sub-assembly shared by several components is
# walked once for each of them, so a few kilobytes can name an exponential tree, and a component
# that refers to its own assembly names an endless one. A read refuses either.
MAX_OCCURRENCES = 250_000
MAX_ASSEMBLY_DEPTH = 64


def mesh_faces(shape: Any) -> tuple[int, ...]:
    """The ordinals (``TopExp.MapShapes``) of ``shape``'s faces that have no surface: a mesh's
    triangles alone, what build123d's ``import_stl`` makes. No document holds one, and the
    kernel's face modifier (``direct``) crashes the process on one."""
    key = shape.TShape()
    found = _MESH_FACES.get(key)
    if found is not None:
        _MESH_FACES.move_to_end(key)
        return found
    from OCP.BRep import BRep_Tool
    from OCP.TopAbs import TopAbs_FACE
    from OCP.TopExp import TopExp
    from OCP.TopoDS import TopoDS
    from OCP.collections import IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher

    faces = IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher()
    TopExp.MapShapes_s(shape, TopAbs_FACE, faces)
    found = _MESH_FACES[key] = tuple(ordinal for ordinal in range(1, faces.Extent() + 1)
                                     if not BRep_Tool.IsGeometric_s(TopoDS.Face(faces.FindKey(ordinal))))
    while len(_MESH_FACES) > _MESH_FACES_HELD:
        _MESH_FACES.popitem(last=False)
    return found


def _mesh_refused(path: str, ordinals: tuple[int, ...]) -> str:
    """Why a part holding mesh faces is refused, by its occurrence's path, and what to do."""
    shown = ", ".join(str(ordinal) for ordinal in ordinals[:6]) + (
        f" and {len(ordinals) - 6} more" if len(ordinals) > 6 else "")
    faces = f"face {shown} is a triangulation" if len(ordinals) == 1 else f"faces {shown} are triangulations"
    return (f"{path} is a mesh, not B-rep: {faces} with no surface (as build123d's import_stl makes), and a "
            "document holds B-rep alone. Read the mesh as data with read_mesh(path) -- its vertices, triangles "
            "and bounding_box() -- and build B-rep from those")


def collect(result: Any, name: str, harvested: Callable[[tuple], "Harvest | None"] | None = None) -> Tree:
    """The prototypes and instances of a model's result (see the module docstring). A part
    holding a face with no surface -- a mesh's triangles -- is refused by its occurrence's path
    (``mesh_faces``), before anything is made of it. ``harvested``, given the tree's signature
    (its structure: every prototype's TShape, label, colour and placement), answers the harvest
    made of this very result before, or None, and the joints, sequences and animations are
    harvested again (``build``: kept beside the model body's run)."""
    from OCP.TopAbs import TopAbs_COMPOUND

    from cadgen.engine.kernel.memo import FACE_COLORS, FACE_MATERIALS

    prototypes: dict[tuple, Part | Assembly] = {}
    signatures: dict[int, tuple] = {}
    order: list = []
    parts: list[Part] = []

    def visit(obj: Any, topods: Any, inherited: tuple | None, inherited_material: Any,
              path: str) -> tuple[Part | Assembly, tuple, tuple | None]:
        state = obj.__dict__ if obj is not None else {}
        own_color = _rgba(state.get("_color"))
        color = own_color or inherited
        own_material = _material(state.get("material"))
        material = own_material or inherited_material
        children = state.get("_NodeMixin__children") or ()
        label = state.get("label") or ""
        held = _children(topods) if children and int(topods.ShapeType()) == int(TopAbs_COMPOUND) else []
        if children and len(held) == len(children):
            components = []
            parts_signature = []
            own = path.rpartition("/")[2]
            for at, (child, child_topods) in enumerate(zip(children, held), 1):
                child_label = child.__dict__.get("label") or ""
                prototype, signature, child_color = visit(child, child_topods.Located(_identity()), color, material,
                                                          path + "/" + (child_label or f"{own}.{at}"))
                components.append((prototype, child_topods.Location(), child_label, child_color))
                parts_signature.append((signature, _location_key(child_topods.Location()), child_label, child_color))
            # An assembly is its components: the compound holding them is no content of its
            # own, so one made again around the same parts is the same assembly.
            signature = ("assembly", int(topods.Orientation()), label, tuple(parts_signature))
            found = prototypes.get(signature)
            if found is None:
                found = Assembly(label or f"assembly{len(order) + 1}")
                for prototype, location, child_label, child_color in components:
                    found.components.append(Component(prototype, location, child_label or prototype.name, child_color))
                prototypes[signature] = found
                order.append(found)
            return found, signature, color
        # An explicit colour always wins; a material's look colours only a part with none of its own.
        if own_color is None and material is not None and material.color is not None:
            color = (own_material if own_material is not None and own_material.color is not None
                     else material).color
        if material is not None and color is None:
            color = DEFAULT_COLOR
        face_materials = {int(ordinal): given for ordinal, given in (state.get(FACE_MATERIALS) or {}).items()}
        face_colors = {int(ordinal): tuple(rgba) for ordinal, rgba in (state.get(FACE_COLORS) or {}).items()
                       if int(ordinal) not in face_materials}
        for ordinal, given in face_materials.items():
            face_color = given.color or color or DEFAULT_COLOR
            face_colors[ordinal] = face_color
        painted = tuple(sorted(face_colors.items()))
        signature = ("part", topods.TShape(), int(topods.Orientation()), painted, material,
                     tuple(sorted(face_materials.items(), key=lambda item: item[0])))
        found = prototypes.get(signature)
        if found is None:
            meshes = mesh_faces(topods)
            if meshes:
                raise ValueError(_mesh_refused(path, meshes))
            found = Part(topods, label or f"part{len(parts) + 1}", color, dict(painted), origin=obj,
                         material=material, face_materials=face_materials)
            prototypes[signature] = found
            order.append(found)
            parts.append(found)
        return found, signature, color

    from cadgen.engine import mechanism

    wrapped = result.wrapped
    root_name = result.__dict__.get("label") or name
    root, signature, color = visit(result, wrapped.Located(_identity()), None, None, root_name)
    location = wrapped.Location()
    held = not (isinstance(root, Assembly) and location.IsIdentity())
    if not held:
        root.name = root_name
    else:
        holder = Assembly(root_name, [Component(root, location, root.name, color)])
        order.append(holder)
        root = holder
    tree = Tree(root, order, parts, (signature, _location_key(location), root_name))
    found = harvested(tree.signature) if harvested is not None else None
    if found is None:
        # The result's joints, harvested: the result is the holder's one component where it has one.
        kinematics = mechanism.harvest(result, tree, (0,) if held else ())
        # And its animations, a GLB's: a change of one rewrites the GLB and the document's record, never its tree.
        from cadgen.engine.animations import harvest

        animated = harvest(result, tree, (0,) if held else (), kinematics)
        found = Harvest(kinematics, animated, (kinematics.signature() if kinematics else None,
                                               tuple(sorted(animated.items())) if animated else None))
    else:
        tree.reused = True
    tree.harvest, tree.mechanism, tree.animations = found, found.mechanism, found.animations
    tree.signature = (*tree.signature, *found.signature)
    return tree


def merge(tree: Tree) -> None:
    """Parts of one geometry made apart -- a helper building the same screw for each place
    it goes, each call its own kernel construction and so its own TShape -- made one
    prototype, placed wherever either was: parts of one geometry key (``geometry_key``,
    their bytes as the document writes them), whose elements are named alike and which
    hold the same colour, paints and materials. Parts named, coloured, painted or given
    materials apart stay apart. Once the parts are named and keyed (``build``); the first
    in the tree's order stands for the others, its name the prototype's, each placement's
    own name and colour on its component."""
    first: dict[tuple, Part] = {}
    replaced: dict[int, Part] = {}
    for part in tree.parts:
        names = part.names or {}
        signature = (part.key, *(tuple(names.get(kind) or ()) for kind in ("faces", "edges", "vertices")),
                     part.color, tuple(sorted(part.face_colors.items())), part.material,
                     tuple(sorted(part.face_materials.items(), key=lambda item: item[0])))
        found = first.setdefault(signature, part)
        if found is not part:
            replaced[id(part)] = found
    if not replaced:
        return
    for prototype in tree.order:
        if isinstance(prototype, Assembly):
            for component in prototype.components:
                component.prototype = replaced.get(id(component.prototype), component.prototype)
    tree.order = [prototype for prototype in tree.order if id(prototype) not in replaced]
    tree.parts = [part for part in tree.parts if id(part) not in replaced]


# --- geometry keys ----------------------------------------------------------------------


@contextmanager
def unchecked(shapes: Iterable[Any]) -> Iterator[None]:
    """Every sub-shape of ``shapes`` with its ``Checked`` flag cleared, and each of
    ``shapes`` free, set back after: what the document writes of a shape, with the
    model's shapes left as they were.

    ``Checked`` is bookkeeping, not geometry: the kernel's face makers leave it set on
    the faces they make, a modifier walking a shape clears it on the faces it visits
    (``direct``), and the memo, which rewinds and reapplies each sub-shape's flags
    with the operations that changed them, leaves a warm build's faces with whichever
    value its replay last set. The flag is written with the shape, so a cold build and
    a warm build of the same sources wrote different bytes -- and the first build after
    a restart rewrote every file for nothing. Written cleared, it is one value on
    every path. No other flag differs between the two. ``Free`` is bookkeeping too: a
    shape added to a compound is no longer free, so a part as its own model's result and
    the same part placed in an assembly -- a child model's document, written by a build
    of it and by its parent's -- wrote other bytes. Each part is written free."""
    from OCP.TopExp import TopExp
    from OCP.collections import IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher

    cleared = []
    held = []
    for shape in shapes:
        root = shape.TShape()
        if not root.Free():
            root.Free(True)
            held.append(root)
        mapped = IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher()
        TopExp.MapShapes_s(shape, mapped)
        find = mapped.FindKey
        for ordinal in range(1, mapped.Extent() + 1):
            tshape = find(ordinal).TShape()
            if tshape.Checked():
                tshape.Checked(False)
                cleared.append(tshape)
    try:
        yield
    finally:
        for tshape in cleared:
            tshape.Checked(True)
        for tshape in held:
            tshape.Free(False)


def direct(shape: Any) -> Any:
    """``shape`` as the document holds it: every face on a direct (right-handed)
    surface. A STEP writer makes faces direct before it writes them, and a face it
    remakes loses its sub-shape label's name; made direct here, the writer remakes
    none and every face keeps its name. Face and edge ordinals are unchanged: the
    kernel's modifier rebuilds the shape in the order it walks it. The modifier
    clears the ``Checked`` flag of the faces it visits; the model's shape keeps its
    own (``unchecked``)."""
    from OCP.ShapeCustom import ShapeCustom

    with unchecked([shape]):
        found = ShapeCustom.DirectFaces_s(shape)
    return shape if found is None or found.IsNull() else found


def geometry_key(shape: Any, *, read: bool = False) -> str:
    """A key of a part's geometry: a digest of the bytes it is meshed from
    (``mesh.shape_bytes``: its binary BRep written and read once, no triangulation). Two
    parts with the same key tessellate alike, in any process. A part a document read
    (``read``) makes the key its build gave it, so a reader checks the key a file names
    for each part against the part itself (``Loaded``)."""
    from cadgen.engine.mesh import shape_bytes

    return hashlib.blake2b(shape_bytes(shape, read=read), digest_size=16).hexdigest()


def _checked_keys(prototypes: list, claims: dict[int, str]) -> None:
    """Each prototype keyed by what its file names (``claims``, by index) only where the
    file's word holds: a key every part naming it makes again from its own geometry
    (``geometry_key``) is kept, and is shared with every document of that geometry. Where
    one part naming a key does not make it, the parts naming it are keyed apart, by the
    key and their own geometry's keys together: a file never lends its part the key of
    another document's, so the daemon's caches -- meshes, facts, shapes -- never answer
    one document's part with another's geometry. A part's look kept apart from another
    of its geometry is a copy of its topology (``_apart``), whose bytes are not the
    first's: the two keep one key all the same, the one made of both. A part the file
    names no key for keeps its own geometry's."""
    named: dict[str, list] = {}
    for prototype in prototypes:
        claim = claims.get(prototype.index)
        if claim:
            named.setdefault(claim, []).append(prototype)
    for claim, group in named.items():
        if any(prototype.key != claim for prototype in group):
            made = "\0".join(["named", claim, *sorted(prototype.key for prototype in group)])
            claim = hashlib.blake2b(made.encode(), digest_size=16).hexdigest()
        for prototype in group:
            prototype.key = claim


# --- the XCAF document --------------------------------------------------------------------


def _application() -> Any:
    from OCP.BinXCAFDrivers import BinXCAFDrivers
    from OCP.XCAFApp import XCAFApp_Application

    app = XCAFApp_Application.GetApplication_s()
    if not getattr(_application, "defined", False):
        BinXCAFDrivers.DefineFormat_s(app)
        _application.defined = True  # type: ignore[attr-defined]
    return app


def _new_document() -> Any:
    from OCP.TCollection import TCollection_ExtendedString
    from OCP.TDocStd import TDocStd_Document

    # The document is made here and never handed to the application: OCP cannot hand back
    # the document ``NewDocument`` makes (it assigns a handle the binding copied), so that
    # call made a second, empty document the application kept open for the process's life,
    # one per document made. Saving and retrieval need only the format's drivers.
    _application()
    return TDocStd_Document(TCollection_ExtendedString("BinXCAF"))


def _quantity(rgba: tuple) -> Any:
    from OCP.Quantity import Quantity_Color, Quantity_ColorRGBA, Quantity_TOC_RGB

    # Linear RGB, as build123d's Color holds it.
    return Quantity_ColorRGBA(Quantity_Color(rgba[0], rgba[1], rgba[2], Quantity_TOC_RGB), float(rgba[3]))


def _name(label: Any, text: str) -> None:
    from OCP.TCollection import TCollection_ExtendedString
    from OCP.TDataStd import TDataStd_Name

    TDataStd_Name.Set_s(label, TCollection_ExtendedString(text, True))


# A material's fields XCAF's own attributes have no place for, written on its
# ``XCAFDoc_Material`` label as one ``TDataStd_NamedData`` named as the schema names them: text,
# reals, ``isotropic`` an integer and ``transmission_color`` an array of reals; a field at its
# default is not written, so a material of a name and a density has no such attribute.
_EXTRA_TEXT = ("family", "standard", "source")
_EXTRA_REALS = ("young_modulus", "poisson_ratio", "yield_strength", "ultimate_strength", "thermal_expansion",
                "thermal_conductivity", "specific_heat", "anisotropy", "anisotropy_rotation", "transmission",
                "transmission_depth", "coat", "coat_roughness", "emissive_strength")
_EXTRA_DEFAULTS = {"anisotropy": 0.0, "anisotropy_rotation": 0.0, "transmission": 0.0, "coat": 0.0,
                   "coat_roughness": 0.0, "emissive_strength": 1.0}


def _write_extra(label: Any, material: Any) -> None:
    from OCP.TCollection import TCollection_ExtendedString
    from OCP.TDataStd import TDataStd_NamedData

    from cadgen.engine.mechanism import _reals

    text = lambda value: TCollection_ExtendedString(value, True)  # noqa: E731
    texts = [(key, getattr(material, key)) for key in _EXTRA_TEXT if getattr(material, key) is not None]
    reals = [(key, getattr(material, key)) for key in _EXTRA_REALS
             if getattr(material, key) is not None and getattr(material, key) != _EXTRA_DEFAULTS.get(key)]
    if not (texts or reals or not material.isotropic or material.transmission_color is not None):
        return
    data = TDataStd_NamedData.Set_s(label)
    for key, value in texts:
        data.SetString(text(key), text(value))
    for key, value in reals:
        data.SetReal(text(key), float(value))
    if not material.isotropic:
        data.SetInteger(text("isotropic"), 0)
    if material.transmission_color is not None:
        data.SetArrayOfReals(text("transmission_color"), _reals(material.transmission_color))


def _read_extra(label: Any) -> dict[str, Any]:
    """The fields ``_write_extra`` wrote on a material's label."""
    from OCP.TCollection import TCollection_ExtendedString
    from OCP.TDataStd import TDataStd_NamedData

    data = TDataStd_NamedData()
    if not _find(label, data, TDataStd_NamedData.GetID_s()):
        return {}
    text = lambda value: TCollection_ExtendedString(value, True)  # noqa: E731
    found: dict[str, Any] = {}
    for key in _EXTRA_TEXT:
        if data.HasString(text(key)):
            found[key] = data.GetString(text(key)).ToExtString()
    for key in _EXTRA_REALS:
        if data.HasReal(text(key)):
            found[key] = data.GetReal(text(key))
    if data.HasInteger(text("isotropic")):
        found["isotropic"] = bool(data.GetInteger(text("isotropic")))
    if data.HasArrayOfReals(text("transmission_color")):
        values = data.GetArrayOfReals(text("transmission_color"))
        from cadgen.engine.colors import Linear

        found["transmission_color"] = Linear(values.Value(at) for at in range(values.Lower(), values.Upper() + 1))
    return found


class _Materials:
    """A document's materials, each written once: an ``XCAFDoc_Material`` per material
    (name, description, density in g/cm^3 -- the kernel's unit, which its STEP writer writes
    with its unit -- and every other physical field and look field XCAF has no place for, as
    ``_write_extra``), an ``XCAFDoc_VisMaterial`` per material and base colour (PBR: base
    colour and alpha, metallic, roughness, emissive, IOR)."""

    def __init__(self, doc: Any) -> None:
        from OCP.XCAFDoc import XCAFDoc_DocumentTool

        self.physical = XCAFDoc_DocumentTool.MaterialTool_s(doc.Main())
        self.visual = XCAFDoc_DocumentTool.VisMaterialTool_s(doc.Main())
        self.physical_labels: dict[Any, Any] = {}
        self.visual_labels: dict[tuple, Any] = {}

    def set(self, label: Any, material: Any, rgba: tuple) -> None:
        self.physical.SetMaterial(label, self.physical_label(material))
        self.visual.SetShapeMaterial(label, self.visual_label((material, tuple(rgba))))

    def physical_label(self, material: Any) -> Any:
        """The label of ``material``'s ``XCAFDoc_Material``, made at its first use."""
        from OCP.TCollection import TCollection_HAsciiString

        found = self.physical_labels.get(material)
        if found is None:
            found = self.physical_labels[material] = self.physical.AddMaterial(
                TCollection_HAsciiString(material.name), TCollection_HAsciiString(material.description or ""),
                (material.density or 0.0) / 1000.0, TCollection_HAsciiString("density"),
                TCollection_HAsciiString("MASS_DENSITY_MEASURE"))
            _write_extra(found, material)
        return found

    def visual_label(self, look: tuple) -> Any:
        """The label of the ``XCAFDoc_VisMaterial`` of ``look``, a material and the base colour
        it is drawn in, made at its first use."""
        found = self.visual_labels.get(look)
        if found is None:
            from OCP.Quantity import Quantity_Color, Quantity_TOC_RGB
            from OCP.Graphic3d import Graphic3d_AlphaMode_Blend, Graphic3d_AlphaMode_Opaque
            from OCP.TCollection import TCollection_AsciiString
            from OCP.XCAFDoc import XCAFDoc_VisMaterial, XCAFDoc_VisMaterialCommon

            material, rgba = look
            # OCP 8 leaves PBR.EmissiveFactor unbound. OCCT's native conversion
            # copies common emission into that field; set the other PBR fields after.
            made = XCAFDoc_VisMaterial()
            common = XCAFDoc_VisMaterialCommon()
            common.EmissiveColor = Quantity_Color(*(material.emissive or (0.0, 0.0, 0.0)), Quantity_TOC_RGB)
            made.SetCommonMaterial(common)
            pbr = made.ConvertToPbrMaterial()
            pbr.BaseColor = _quantity(rgba)
            pbr.Metallic = material.metallic
            pbr.Roughness = material.roughness
            pbr.RefractionIndex = material.ior
            pbr.IsDefined = True
            made.SetPbrMaterial(pbr)
            made.UnsetCommonMaterial()
            made.SetAlphaMode(Graphic3d_AlphaMode_Blend if rgba[3] < 1.0 else Graphic3d_AlphaMode_Opaque, 0.5)
            found = self.visual_labels[look] = self.visual.AddMaterial(made, TCollection_AsciiString(material.name))
        return found


@dataclass
class _Record:
    """What one shape label of a kept document holds: the prototype at its place in the
    tree's order, as the label was converted from it. Two records are the same when the
    label a cold conversion makes of the one is the label already made of the other."""

    values: tuple  # compared with ==
    shape: Any = None  # a part's shape, compared with IsEqual (the same TShape, placement and orientation)
    names: Any = None  # a part's element names, by identity, else by value
    children: tuple = ()  # an assembly's components' prototypes, by their place in the order
    locations: tuple = ()  # and their placements, compared with IsEqual (the same datums)
    colours: tuple = ()  # the colours its labels are given, in the order a conversion gives them,
    physical: tuple = ()  # its physical materials,
    visual: tuple = ()  # and its looks: (material, base colour)

    def same(self, other: "_Record") -> bool:
        if self.values != other.values or self.children != other.children:
            return False
        if (self.shape is None) != (other.shape is None) or (self.shape is not None
                                                             and not self.shape.IsEqual(other.shape)):
            return False
        if self.names is not other.names and self.names != other.names:
            return False
        return len(self.locations) == len(other.locations) and all(
            mine.IsEqual(theirs) for mine, theirs in zip(self.locations, other.locations))


def _records(tree: Tree) -> list[_Record]:
    """Each prototype of the tree's order as its label holds it (``_Record``)."""
    index = {id(prototype): at for at, prototype in enumerate(tree.order)}
    labelled: set = set()  # the TShapes an earlier part's label holds
    found = []
    for prototype in tree.order:
        if isinstance(prototype, Part):
            tshape = prototype.shape.TShape()
            apart = tshape in labelled
            labelled.add(tshape)
            painted = tuple(sorted(prototype.face_colors.items()))
            given = tuple(sorted(prototype.face_materials.items(), key=lambda item: item[0]))
            base = prototype.color or DEFAULT_COLOR
            found.append(_Record(
                ("part", apart, prototype.name, prototype.color, prototype.material, painted, given, prototype.key),
                shape=prototype.shape, names=prototype.names,
                colours=((prototype.color,) if prototype.color is not None else ())
                + tuple(rgba for _, rgba in painted),
                physical=((prototype.material,) if prototype.material is not None else ())
                + tuple(material for _, material in given),
                visual=(((prototype.material, tuple(base)),) if prototype.material is not None else ())
                + tuple((material, tuple(prototype.face_colors.get(ordinal) or DEFAULT_COLOR))
                        for ordinal, material in given)))
        else:
            written = tuple(_component_color(component) for component in prototype.components)
            found.append(_Record(
                ("assembly", prototype.name, tuple((component.name, color) for component, color
                                                   in zip(prototype.components, written))),
                children=tuple(index[id(component.prototype)] for component in prototype.components),
                locations=tuple(component.location for component in prototype.components),
                colours=tuple(color for color in written if color is not None)))
    return found


def _component_color(component: Component) -> tuple | None:
    """The colour a component's label is given: its own where it differs from its part's."""
    held = component.prototype
    if component.color is None or (isinstance(held, Part) and held.color == component.color):
        return None
    return component.color


def _tables(records: list[_Record]) -> tuple[list, list, list]:
    """The colours, physical materials and looks a cold conversion of these records makes
    labels of, in the order it makes them: each at its first use."""
    colours: dict = {}
    physical: dict = {}
    visual: dict = {}
    for record in records:
        for table, values in ((colours, record.colours), (physical, record.physical), (visual, record.visual)):
            for value in values:
                table.setdefault(value, None)
    return list(colours), list(physical), list(visual)


class Kept:
    """A model's XCAF document kept in memory from one build to the next, with what each
    of its shape labels holds (``_Record``): a warm build patches it (``to_xcaf``)."""

    def __init__(self) -> None:
        self.doc: Any = None
        self.records: list[_Record] = []
        self.tables: tuple | None = None
        self.materials: "_Materials | None" = None
        self.mechanism: tuple | None = None
        # The tags of the main label's children a conversion gives attributes: what a reader
        # of the document adds beside them (the STEP writer its GD&T tool) is cleared.
        self.tools: set[int] = set()
        # The last conversion: how many prototypes it converted, and whether it patched.
        self.converted = 0
        self.patched = False
        # The build closure the document holds (``Tree.closure``), and its animations' record.
        self.closure: str | None = None
        self.animations: str | None = None


def to_xcaf(tree: Tree, kept: Kept | None = None) -> Any:
    """The XCAF document of a tree whose parts are named (``Part.names``) and keyed.

    With ``kept``, a document held from the model's last build, the document is that one,
    patched: a prototype whose label holds what a cold conversion would make of it keeps its
    label untouched; every other label at its place in the order is cleared and made again
    (its name, colours, materials, element names, components), each at the tag a cold
    conversion gives it, and the references a cold conversion orders by its labels'
    places (a colour's, a material's, a part's placements) put back in that order; the
    mechanism is written again when it or the occurrences it names changed. So the patched
    document is the cold one, label for label, and saves to its bytes. A change to which
    colours or materials the document holds, or their order, converts it whole; so does a
    patch the kernel does not take as planned."""
    with _XCAF_LOCK:
        from OCP.XCAFDoc import XCAFDoc_ShapeTool

        XCAFDoc_ShapeTool.SetAutoNaming_s(False)
        records = _records(tree)
        doc = None
        if kept is not None and kept.doc is not None:
            try:
                doc = _patch(kept, tree, records)
            except Exception:  # noqa: BLE001 - a patch that fails leaves a document only a whole conversion mends
                doc = None
            if doc is None:
                kept.doc = None
        if doc is None:
            kept = kept if kept is not None else Kept()
            doc = _convert(tree, records, kept)
        _MADE[:] = [doc, tree]
        return doc


class _Unplanned(Exception):
    """The kernel did not take a patch as planned (a label at another tag than a cold
    conversion's): the document is converted whole."""


class _Converter:
    """Labels made of prototypes, as a cold conversion makes them; ``patching``, at the tag
    a cold conversion gives each, checked."""

    def __init__(self, doc: Any, kept: Kept, patching: bool) -> None:
        from OCP.Standard import Standard_GUID
        from OCP.XCAFDoc import XCAFDoc_DocumentTool

        self.doc = doc
        self.shapes = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
        self.colors = XCAFDoc_DocumentTool.ColorTool_s(doc.Main())
        self.materials = kept.materials
        self.patching = patching
        self.key_guid = Standard_GUID(KEY_GUID)

    def label(self, at: int) -> Any:
        return self.shapes.Label().FindChild(at + 1, False)

    def _placed(self, label: Any, at: int) -> None:
        if self.patching and (label.Tag() != at + 1 or not label.Father().IsEqual(self.shapes.Label())):
            raise _Unplanned(f"prototype {at + 1} landed at {_entry(label)}")

    def part(self, at: int, prototype: Part, record: _Record) -> Any:
        from OCP.TCollection import TCollection_AsciiString
        from OCP.TDataStd import TDataStd_AsciiString
        from OCP.TDF import TDF_Label
        from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_VERTEX
        from OCP.TopExp import TopExp
        from OCP.collections import IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher
        from OCP.XCAFDoc import XCAFDoc_ColorSurf

        shapes, colors, materials = self.shapes, self.colors, self.materials
        # Parts of one geometry painted or given materials apart share a TShape, and the
        # shape tool hands a shape it holds its first label again: the second is added as its
        # own topology on the same geometry (``_apart``).
        shape = _apart(prototype.shape) if record.values[1] else prototype.shape
        label = shapes.AddShape(shape, False, False)
        self._placed(label, at)
        _name(label, prototype.name)
        if prototype.color is not None:
            colors.SetColor(label, _quantity(prototype.color), XCAFDoc_ColorSurf)
        if prototype.material is not None:
            materials.set(label, prototype.material, prototype.color or DEFAULT_COLOR)
        if prototype.key:
            TDataStd_AsciiString.Set_s(label, self.key_guid, TCollection_AsciiString(prototype.key))
        faces = IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher()
        TopExp.MapShapes_s(shape, TopAbs_FACE, faces)
        face_names = (prototype.names or {}).get("faces") or []
        painted = prototype.face_colors
        for ordinal in range(1, faces.Extent() + 1):
            text = face_names[ordinal - 1] if ordinal <= len(face_names) else None
            rgba = painted.get(ordinal)
            given = prototype.face_materials.get(ordinal)
            if text is None and rgba is None and given is None:
                continue
            sub = TDF_Label()
            if not shapes.AddSubShape(label, faces.FindKey(ordinal), sub) and sub.IsNull():
                continue
            if text is not None:
                _name(sub, text)
            if rgba is not None:
                colors.SetColor(sub, _quantity(rgba), XCAFDoc_ColorSurf)
            if given is not None:
                materials.set(sub, given, rgba or DEFAULT_COLOR)
        for kind, topabs in (("edges", TopAbs_EDGE), ("vertices", TopAbs_VERTEX)):  # vertices: naming
            edge_names = (prototype.names or {}).get(kind) or []
            if not any(text is not None for text in edge_names):
                continue
            edges = IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher()
            TopExp.MapShapes_s(shape, topabs, edges)
            for ordinal in range(1, min(edges.Extent(), len(edge_names)) + 1):
                text = edge_names[ordinal - 1]
                if text is None:
                    continue
                sub = TDF_Label()
                if shapes.AddSubShape(label, edges.FindKey(ordinal), sub) or not sub.IsNull():
                    _name(sub, text)
        return label

    def assembly(self, at: int, prototype: Assembly, record: _Record, labels: list) -> Any:
        from OCP.XCAFDoc import XCAFDoc_ColorSurf

        label = self.shapes.NewShape()
        self._placed(label, at)
        _name(label, prototype.name)
        for place, (component, child) in enumerate(zip(prototype.components, record.children), 1):
            placed = self.shapes.AddComponent(label, labels[child], component.location)
            if self.patching and placed.Tag() != place:
                raise _Unplanned(f"component {place} of prototype {at + 1} landed at {_entry(placed)}")
            _name(placed, component.name)
            color = _component_color(component)
            if color is not None:
                self.colors.SetColor(placed, _quantity(color), XCAFDoc_ColorSurf)
        return label

    def mechanism(self, tree: Tree, labels: list) -> tuple | None:
        """The mechanism's record: its signature and the entries of the occurrences it names."""
        if tree.mechanism is None:
            return None
        entries = tuple(tuple(_entry(label) for label in self.occurrence(tree, labels, path))
                        for link in tree.mechanism.links for path in link.members)
        return tree.mechanism.signature(), entries

    @staticmethod
    def occurrence(tree: Tree, labels: list, path: tuple[int, ...]) -> list:
        """An occurrence's labels: the root's, then each component's down to it."""
        order = {id(prototype): at for at, prototype in enumerate(tree.order)}
        found, node = [labels[order[id(tree.root)]]], tree.root
        for at in path:
            found.append(labels[order[id(node)]].FindChild(at + 1, False))
            node = node.components[at].prototype
        return found


def _convert(tree: Tree, records: list[_Record], kept: Kept) -> Any:
    """The document made whole, and kept (``Kept``)."""
    from OCP.Standard import Standard_GUID
    from OCP.TCollection import TCollection_AsciiString
    from OCP.TDataStd import TDataStd_AsciiString
    from OCP.UnitsMethods import UnitsMethods_LengthUnit_Millimeter
    from OCP.XCAFDoc import XCAFDoc_DocumentTool

    from cadgen.engine import mechanism

    doc = _new_document()
    XCAFDoc_DocumentTool.SetLengthUnit_s(doc, 1.0, UnitsMethods_LengthUnit_Millimeter)
    kept.materials = None
    converter = _Converter(doc, kept, patching=False)
    converter.materials = kept.materials = _Materials(doc)
    TDataStd_AsciiString.Set_s(doc.Main(), Standard_GUID(WRITER_GUID), TCollection_AsciiString(_writer()))
    if tree.closure is not None:
        TDataStd_AsciiString.Set_s(doc.Main(), Standard_GUID(CLOSURE_GUID), TCollection_AsciiString(tree.closure))
    kept.closure = tree.closure
    animated = _animations_record(tree)
    if animated is not None:
        TDataStd_AsciiString.Set_s(doc.Main(), Standard_GUID(ANIMATIONS_GUID), TCollection_AsciiString(animated))
    kept.animations = animated
    labels: list = []
    for at, (prototype, record) in enumerate(zip(tree.order, records)):
        if isinstance(prototype, Part):
            labels.append(converter.part(at, prototype, record))
        else:
            labels.append(converter.assembly(at, prototype, record, labels))
    converter.shapes.UpdateAssemblies()
    kept.mechanism = converter.mechanism(tree, labels)
    if tree.mechanism is not None:
        mechanism.write(doc, tree.mechanism, lambda path: converter.occurrence(tree, labels, path))
    kept.doc, kept.records, kept.tables = doc, records, _tables(records)
    kept.tools = {tag for tag in _held_children(doc.Main()) if tag != mechanism.TAG}
    kept.converted, kept.patched = len(records), False
    return doc


def _animations_record(tree: Tree) -> str | None:
    """The record of a tree's animations its document holds (``animations.record``), or None."""
    from cadgen.engine.animations import record

    return record(tree.animations)


def _patch(kept: Kept, tree: Tree, records: list[_Record]) -> Any:
    """The kept document patched to ``tree`` (see ``to_xcaf``), or None where only a whole
    conversion makes the cold document."""
    from OCP.TDF import TDF_Label, TDF_TagSource
    from OCP.XCAFDoc import XCAFDoc, XCAFDoc_ColorSurf

    from cadgen.engine import mechanism

    tables = _tables(records)
    old = kept.records
    dirty: list[int] = []
    marked: set[int] = set()
    for at, record in enumerate(records):
        # An assembly placing a prototype made again is made again: its components hold
        # their prototypes' shapes.
        if at >= len(old) or not record.same(old[at]) or any(child in marked for child in record.children):
            dirty.append(at)
            marked.add(at)
    gone = list(range(len(records), len(old)))
    doc = kept.doc
    for tag in _held_children(doc.Main()):
        if tag not in kept.tools and tag != mechanism.TAG:
            doc.Main().FindChild(tag, False).ForgetAllAttributes(True)
    converter = _Converter(doc, kept, patching=True)
    labels = [converter.label(at) for at in range(min(len(records), len(old)))] + [None] * (len(records) - len(old))
    kept.converted, kept.patched = len(dirty), True
    animated = _animations_record(tree)
    if (tree.closure is None) != (kept.closure is None) or (animated is None) != (kept.animations is None):
        return None  # the main label's attributes in a cold conversion's order: made whole
    if tree.closure != kept.closure or animated != kept.animations:
        from OCP.Standard import Standard_GUID
        from OCP.TCollection import TCollection_AsciiString
        from OCP.TDataStd import TDataStd_AsciiString

        if tree.closure != kept.closure:
            TDataStd_AsciiString.Set_s(doc.Main(), Standard_GUID(CLOSURE_GUID), TCollection_AsciiString(tree.closure))
            kept.closure = tree.closure
        if animated != kept.animations:
            TDataStd_AsciiString.Set_s(doc.Main(), Standard_GUID(ANIMATIONS_GUID), TCollection_AsciiString(animated))
            kept.animations = animated
    if not dirty and not gone and tables == kept.tables and converter.mechanism(tree, labels) == kept.mechanism:
        return doc
    # The references a label makes, ordered by their labels' places: each colour's,
    # material's and look's, and each part's placements.
    colours: set = set()
    physical: set = set()
    visual: set = set()
    placed: set[int] = set()
    for at in dirty + gone:
        for record in ([old[at]] if at < len(old) else []) + ([records[at]] if at < len(records) else []):
            colours.update(record.colours)
            physical.update(record.physical)
            visual.update(record.visual)
            placed.update(record.children)
        if at < len(old):  # a place past the old order's holds nothing
            converter.label(at).ForgetAllAttributes(True)
    if tables != kept.tables:
        _renumber(converter, kept, tables)
    tags = TDF_TagSource.Set_s(converter.shapes.Label())
    for at in dirty:
        # The tag before this prototype's: the shape tool makes its label at the next one.
        tags.Set(at)
        prototype = tree.order[at]
        if isinstance(prototype, Part):
            labels[at] = converter.part(at, prototype, records[at])
        else:
            labels[at] = converter.assembly(at, prototype, records[at], labels)
    tags.Set(len(records))
    converter.shapes.UpdateAssemblies()
    for rgba in colours:
        found = TDF_Label()
        if converter.colors.FindColor(_quantity(rgba), found):
            _reorder(found, XCAFDoc.ColorRefGUID_s(XCAFDoc_ColorSurf), descending=True)
    for material in physical:
        _reorder(kept.materials.physical_labels[material], XCAFDoc.MaterialRefGUID_s(), descending=False)
    for look in visual:
        _reorder(kept.materials.visual_labels[look], XCAFDoc.VisMaterialRefGUID_s(), descending=True)
    for at in placed:
        if at < len(records) and at not in marked:
            _reorder(labels[at], XCAFDoc.ShapeRefGUID_s(), descending=False)
    record = converter.mechanism(tree, labels)
    if record != kept.mechanism:
        doc.Main().FindChild(mechanism.TAG, True).ForgetAllAttributes(True)
        if tree.mechanism is not None:
            mechanism.write(doc, tree.mechanism, lambda path: converter.occurrence(tree, labels, path))
    kept.records, kept.mechanism, kept.tables = records, record, tables
    return doc


def _renumber(converter: _Converter, kept: Kept, tables: tuple[list, list, list]) -> None:
    """The colours, materials and looks the document holds made again as ``tables`` lists
    them, each label at the tag a cold conversion gives it, and every reference the
    document's kept labels make to one put back on it in a cold conversion's order."""
    from OCP.TDataStd import TDataStd_TreeNode
    from OCP.TDF import TDF_TagSource
    from OCP.XCAFDoc import XCAFDoc, XCAFDoc_ColorSurf

    materials = kept.materials
    kinds = (
        (converter.colors.Label(), XCAFDoc.ColorRefGUID_s(XCAFDoc_ColorSurf), True, None,
         lambda rgba: converter.colors.AddColor(_quantity(rgba))),
        (materials.physical.Label(), XCAFDoc.MaterialRefGUID_s(), False, materials.physical_labels,
         materials.physical_label),
        (materials.visual.Label(), XCAFDoc.VisMaterialRefGUID_s(), True, materials.visual_labels,
         materials.visual_label),
    )
    for (tool, guid, descending, held, make), old, new in zip(kinds, kept.tables, tables):
        if old == new:
            continue
        if len(_held_children(tool)) != len(old):
            raise _Unplanned("the document holds other colours or materials than its records")
        referrers: dict = {}
        for at, value in enumerate(old):
            label = tool.FindChild(at + 1, False)
            node = TDataStd_TreeNode()
            if _find(label, node, guid) and node.HasFirst():
                child = node.First()
                while True:
                    referrers.setdefault(value, []).append(child)
                    if not child.HasNext():
                        break
                    child = child.Next()
                for child in referrers[value]:
                    child.Remove()  # from its father while that lives: forgetting it leaves no link
            label.ForgetAllAttributes(True)
        if held is not None:
            held.clear()
        if new:
            TDF_TagSource.Set_s(tool).Set(0)
        else:
            tool.ForgetAttribute(TDF_TagSource.GetID_s())  # a cold conversion made no label here
        for at, value in enumerate(new):
            label = make(value)
            if label.Tag() != at + 1:
                raise _Unplanned(f"table entry {at + 1} landed at {_entry(label)}")
            children = referrers.get(value)
            if children:
                father = TDataStd_TreeNode.Set_s(label, guid)
                for child in sorted(children, key=lambda node: _place(node.Label()), reverse=descending):
                    child.Remove()
                    father.Append(child)


def _held_children(label: Any) -> list[int]:
    """The tags of ``label``'s children that hold an attribute, or have a child that does."""
    from OCP.TDF import TDF_ChildIterator

    found = []
    children = TDF_ChildIterator(label, False)
    while children.More():
        child = children.Value()
        if child.HasAttribute() or _held_children(child):
            found.append(child.Tag())
        children.Next()
    return found


def _place(label: Any) -> tuple[int, ...]:
    """A label's place in the document: its entry's tags."""
    return tuple(int(tag) for tag in _entry(label).split(":"))


def _reorder(label: Any, guid: Any, descending: bool) -> None:
    """The references of tree ``guid`` to ``label`` in the order a cold conversion leaves
    them: by their labels' places, ``descending`` where the kernel puts each new one first."""
    from OCP.TDataStd import TDataStd_TreeNode

    if not label.IsAttribute(guid):
        return
    # The label's own node: ``FindAttribute`` hands back a copy of it, which a child appended
    # to would take for its father.
    node = TDataStd_TreeNode.Set_s(label, guid)
    if not node.HasFirst():
        return
    children = []
    child = node.First()
    while True:
        children.append((_place(child.Label()), child))
        if not child.HasNext():
            break
        child = child.Next()
    wanted = sorted(children, key=lambda item: item[0], reverse=descending)
    if [place for place, _ in wanted] == [place for place, _ in children]:
        return
    for _, child in wanted:
        child.Remove()
    for _, child in wanted:
        node.Append(child)


def _apart(shape: Any) -> Any:
    """``shape``'s topology made again over the same geometry (``BRepBuilderAPI_Copy``
    with ``copyGeom`` off): a shape the shape tool holds no label of, its sub-shapes in
    the same order (the same ordinals, so the same names, paints and materials), every
    ``Checked`` flag cleared, as ``unchecked`` writes a part's: the copy is the
    document's alone."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Copy
    from OCP.TopExp import TopExp
    from OCP.collections import IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher

    made = BRepBuilderAPI_Copy(shape, False, False).Shape()
    mapped = IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher()
    TopExp.MapShapes_s(made, mapped)
    for ordinal in range(1, mapped.Extent() + 1):
        mapped.FindKey(ordinal).TShape().Checked(False)
    return made


def write_bytes(path: Path, data: bytes, tree: "Tree | None" = None) -> tuple[bool, int]:
    """A document's xbf bytes (``to_bytes``: the bytes ``save`` writes) at ``path``, landed whole
    and only where the file does not hold them already (``atomic_replace.put``). ``tree``, the tree
    the document was made from, is remembered as the one at ``path`` (``saved``). Returns whether
    the file was written, and its size."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if tree is not None:
        _SAVED[path.resolve()] = tree
    written, _size = put(path, lambda temporary: temporary.write_bytes(data))
    return written, len(data)


def save(doc: Any, path: Path, *, compare: bool, tree: "Tree | None" = None) -> tuple[bool, int]:
    """Save ``doc`` to ``path`` atomically: a temporary file beside it whose name ends in
    ``.xbf`` (BinXCAF appends the suffix to any other name), then replaced over the
    path. With ``compare``, an existing file with the same bytes is left as it is
    (``atomic_replace.put``). Returns whether the file was written, and its size. The
    tree ``doc`` was made from -- the one just made (``to_xcaf``), or ``tree``, a kept document's
    own, saved again -- is remembered as the one at ``path`` (``saved``): its parts are the shapes
    written, so a kept document saved again writes the bytes it wrote first."""
    from OCP.PCDM import PCDM_StoreStatus
    from OCP.TCollection import TCollection_ExtendedString

    if _MADE and _MADE[0] is doc:
        tree = _MADE[1]
        _MADE.clear()
    if tree is not None:
        _SAVED[Path(path).resolve()] = tree
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    shapes = [part.shape for part in tree.parts] if tree is not None else _free_shapes(doc)

    def write(temporary: Path) -> None:
        with _XCAF_LOCK, unchecked(shapes):
            status = _application().SaveAs(doc, TCollection_ExtendedString(str(temporary), True))
        if status != PCDM_StoreStatus.PCDM_SS_OK or not temporary.exists():
            raise OSError(f"could not save {path}: {status}")
        _fix_date(temporary)

    return put(path, write, compare=compare, staged=path.with_suffix(".xbf").name)


# The creation date the BinXCAF storage driver writes in the file's info section, the
# day of the save (``Storage_Schema::ICreationDate``, ``%m/%d/%Y``: always ten bytes,
# after its little-endian length), which no API sets. The file is a function of the code
# and the geometry alone, so the written date is this one, put over it in place.
WRITTEN_DATE = b"01/01/2000"
_HEADER_DATE = re.compile(rb"\x0a\x00\x00\x00(\d\d/\d\d/\d\d\d\d)")
_INFO_BYTES = 1024


def _fix_date(path: Path) -> None:
    """Put ``WRITTEN_DATE`` over the saved file's creation date, in place: the same
    length, so no other byte moves."""
    with open(path, "r+b") as handle:
        found = _HEADER_DATE.search(handle.read(_INFO_BYTES))
        if found is None:
            raise OSError(f"{path} has no BinXCAF creation date in its info section")
        if found.group(1) != WRITTEN_DATE:
            handle.seek(found.start(1))
            handle.write(WRITTEN_DATE)


# The BinOcaf file a document is saved as, as far as ``relabel`` reads it: its magic and the byte
# order mark after it, the header's integers (where its info and comment sections end), the one
# table of contents entry of a file that writes its shapes inline in their attributes (``:``, three
# placeholders), and the markers that end a label's attributes and the label.
_MAGIC = b"BINFILE"
_ORDER = 0x04030201
_TOC_END = b"\x04\x00\x00\x00:\x00\x00\x00" + bytes(24)
_END_ATTRIBUTES, _END_LABEL = -1, -2
_STRING_TYPE = "TDataStd_AsciiString"


def relabel(data: bytes, texts: dict[str, str]) -> bytes:
    """An xbf's bytes with each ASCII string of its main label named here by GUID holding the text
    given: those attributes' bytes made again where they are, the sizes of the two labels that
    hold them (the root's and the main label's) moved by what they grew, every other byte as it
    was. The document is never read and saved again for it, which would make each direction and
    placement anew (``previous``'s note): these are the bytes a save of the document holding
    these texts writes. ``ValueError``, and nothing made, for bytes of another layout than the
    documents this engine writes -- one whose table of contents names sections (its shapes in a
    section of their own), labels other than the root's main label first, sizes that do not span
    the file, or no such string of a GUID asked for."""
    import struct
    import uuid

    def integer(at: int) -> int:
        if at + 4 > len(data):
            raise ValueError("not a document this engine wrote: it ends inside its labels")
        return struct.unpack_from("<i", data, at)[0]

    def refused(why: str) -> ValueError:
        return ValueError(f"not a document this engine wrote: {why}")

    if data[:len(_MAGIC)] != _MAGIC or integer(len(_MAGIC)) != _ORDER:
        raise refused("no BinOcaf header")
    info, info_end, comments_end = integer(11), integer(15), integer(23)
    types = _attribute_types(data, info, info_end)
    if data[comments_end:comments_end + len(_TOC_END)] != _TOC_END:
        raise refused("its table of contents names sections")
    root = comments_end + len(_TOC_END)
    if integer(root) != 0:
        raise refused("no root label")

    def attributes(at: int) -> tuple[list[tuple[int, int, int]], int]:
        """The attributes of the label whose first one is at ``at``: (start, its type, its data's
        size) each, and where the label's attributes end."""
        found = []
        while integer(at) != _END_ATTRIBUTES:
            kind, size = integer(at), integer(at + 8)
            if kind not in types:
                raise refused(f"an attribute of type {kind}, which its info section does not list")
            if size < 0:
                raise refused("an attribute written as a stream on its root or main label")
            found.append((at, kind, size))
            at += 12 + size
        return found, at + 4

    _root_attributes, main = attributes(root + 12)
    if integer(main) != 1:
        raise refused("no main label after the root's attributes")
    spans = {root + 4: len(data), main + 4: len(data) - 4}  # each label's size, from where it is to its end
    if integer(len(data) - 4) != _END_LABEL or any(struct.unpack_from("<Q", data, at)[0] != end - at
                                                    for at, end in spans.items()):
        raise refused("its labels' sizes do not span the file")
    wanted = {uuid.UUID(guid).bytes_le: (guid, text) for guid, text in texts.items()}
    edits = []
    main_attributes, _end = attributes(main + 12)
    for at, kind, size in main_attributes:
        guid = data[at + 12 + size - 16:at + 12 + size]
        if types[kind] != _STRING_TYPE or guid not in wanted or size < 20:
            continue
        old = data[at + 12:at + 12 + size - 16]
        ends = old.find(b"\x00")
        if ends < 0 or old[ends:].strip(b"\x00") or len(old) % 4 or len(old) - ends > 4:
            raise refused(f"the string {wanted[guid][0]} is not written as an ASCII string")
        text = wanted.pop(guid)[1].encode("ascii")
        if b"\x00" in text:
            raise ValueError("a label's text holds no NUL")
        string = text + b"\x00" * (4 - len(text) % 4)  # its NUL, then to a whole word, as OCCT aligns it
        edits.append((at + 8, at + 12 + size, struct.pack("<i", len(string) + 16) + string + guid))
    if wanted:
        raise refused(f"its main label holds no string {', '.join(guid for guid, _text in wanted.values())}")
    grown = sum(len(made) - (end - start) for start, end, made in edits)
    out, last = bytearray(), 0
    for start, end, made in edits:  # in the file's order: the main label's attributes, as found
        out += data[last:start] + made
        last = end
    out += data[last:]
    for at in spans:  # both labels are before every edit: their sizes are where they were
        struct.pack_into("<Q", out, at, struct.unpack_from("<Q", data, at)[0] + grown)
    return bytes(out)


def _attribute_types(data: bytes, start: int, end: int) -> dict[int, str]:
    """The attribute types a BinOcaf file's info section lists, by the number its attributes name
    them with: from ``START_TYPES`` to ``END_TYPES``, each a counted string, the first number 1."""
    import struct

    marker = b"\x0b\x00\x00\x00START_TYPES"
    at = data.find(marker, start, end)
    if at < 0:
        raise ValueError("not a document this engine wrote: no attribute types in its info section")
    at += len(marker)
    found: dict[int, str] = {}
    while at + 4 <= end:
        size = struct.unpack_from("<i", data, at)[0]
        name = data[at + 4:at + 4 + size].decode("ascii", "replace")
        at += 4 + max(size, 0)
        if name == "END_TYPES":
            return found
        found[len(found) + 1] = name
    raise ValueError("not a document this engine wrote: its attribute types do not end")


def _free_shapes(doc: Any) -> list[Any]:
    from OCP.collections import Sequence_TDF_Label
    from OCP.XCAFDoc import XCAFDoc_DocumentTool, XCAFDoc_ShapeTool

    free = Sequence_TDF_Label()
    XCAFDoc_DocumentTool.ShapeTool_s(doc.Main()).GetFreeShapes(free)
    return [XCAFDoc_ShapeTool.GetShape_s(free.Value(at)) for at in range(1, free.Length() + 1)]


# --- reading ----------------------------------------------------------------------------


def read_step_shape(path: Any) -> Any:
    """A STEP file as a build123d compound tree, every node named as the file names that
    occurrence (its own name, else its product's), coloured and given its material:
    parsed in a reader process (``reader.read_step``), so the parse's working memory never
    stays in the worker."""
    from cadgen.engine.reader import read_step

    return read_step(path)


def read_xbf_shape(path: Any) -> Any:
    """An xbf as a build123d compound tree (``reader.read_xbf``)."""
    from cadgen.engine.reader import read_xbf

    return read_xbf(path)


@dataclass
class Prototype:
    """A part of a loaded document: its geometry at the identity, its name and colour,
    its key, and what its faces and edges are named and coloured, by ordinal."""

    index: int
    shape: Any
    name: str
    color: tuple | None
    key: str
    face_names: dict[int, str]
    edge_names: dict[int, str]
    face_colors: dict[int, tuple]
    entry: str
    material: Any = None
    face_materials: dict[int, Any] = field(default_factory=dict)
    vertex_names: dict[int, str] = field(default_factory=dict)


@dataclass
class Instance:
    prototype: int
    path: list[str]
    matrix: list[float]  # 4x4, column-major, as WebGL reads it
    color: tuple | None


class Loaded:
    """A document read into memory: an ``.xbf`` through the BinXCAF retrieval driver, a
    ``.step``/``.stp`` through the XCAF reader. Its prototypes are its simple-shape labels,
    each once; its instances are every placement of one, through the assembly tree."""

    def __init__(self, path: Path, doc: Any = None) -> None:
        self.path = Path(path).resolve()
        if doc is None:
            stat = self.path.stat()
            self.version = (stat.st_mtime_ns, stat.st_size)
            self.doc = _read(self.path)
        else:  # read already, from bytes (``read_bytes``): ``path`` names it, and no file is there
            self.version = (0, 0)
            self.doc = doc
        self.writer = _label_text(self.doc.Main(), WRITER_GUID)  # None for a file this engine did not write
        self.prototypes: list[Prototype] = []
        self.instances: list[Instance] = []
        self.name = self.path.stem
        self.tree: dict[str, Any] = {}
        # Each instance's occurrence as component indices from the root; each occurrence's
        # placement by those, and its label entries (``/``-joined) to them.
        self.instance_paths: list[tuple[int, ...]] = []
        self.worlds: dict[tuple[int, ...], Any] = {}
        # And each occurrence's placement in its assembly's frame: its component's, a part's own
        # placement after it.
        self.locals: dict[tuple[int, ...], Any] = {}
        self.occurrences: dict[str, tuple[int, ...]] = {}
        self.step = self.path.suffix.lower() in (".step", ".stp")
        self._walk()
        self.mechanism = None
        if self.path.suffix.lower() == ".xbf":
            from cadgen.engine import mechanism

            self.mechanism = mechanism.read(self.doc, self.occurrences)

    def _walk(self) -> None:
        from OCP.TDF import TDF_Label, TDF_Tool
        from OCP.collections import Sequence_TDF_Label
        from OCP.TCollection import TCollection_AsciiString
        from OCP.XCAFDoc import XCAFDoc_DocumentTool, XCAFDoc_ShapeTool

        shapes = XCAFDoc_DocumentTool.ShapeTool_s(self.doc.Main())
        by_entry: dict[str, int] = {}
        # A STEP's names as the file means them (``step_name``); an xbf's as the engine wrote them.
        named = (lambda label: step_name(_label_name(label))) if self.step else _label_name

        def entry_of(label: Any) -> str:
            text = TCollection_AsciiString()
            TDF_Tool.Entry_s(label, text)
            return text.ToCString()

        counted = 0
        claims: dict[int, str] = {}

        def visit(label: Any, location: Any, path: list[str], inherited: tuple | None, name: str,
                  occurrence: tuple[int, ...], entries: list[str], ancestors: frozenset = frozenset()) -> dict[str, Any]:
            nonlocal counted
            counted += 1
            if counted > MAX_OCCURRENCES:
                raise ValueError(f"cannot read {self.path.name}: its assembly names more than "
                                 f"{MAX_OCCURRENCES} occurrences")
            if len(occurrence) > MAX_ASSEMBLY_DEPTH:
                raise ValueError(f"cannot read {self.path.name}: its assembly is deeper than "
                                 f"{MAX_ASSEMBLY_DEPTH} levels")
            color = _label_color(label) or inherited
            self.worlds[occurrence] = location
            self.occurrences["/".join(entries)] = occurrence
            if XCAFDoc_ShapeTool.IsAssembly_s(label):
                own = entry_of(label)
                if own in ancestors:
                    raise ValueError(f"cannot read {self.path.name}: an assembly contains itself")
                inner = ancestors | {own}
                node: dict[str, Any] = {"name": name, "children": []}
                components = Sequence_TDF_Label()
                XCAFDoc_ShapeTool.GetComponents_s(label, components, False)
                for at in range(1, components.Length() + 1):
                    component = components.Value(at)
                    referred = TDF_Label()
                    XCAFDoc_ShapeTool.GetReferredShape_s(component, referred)
                    own = XCAFDoc_ShapeTool.GetLocation_s(component)
                    self.locals[occurrence + (at - 1,)] = own
                    placed = location.Multiplied(own)
                    child_name = named(component) or named(referred) or f"{name}.{at}"
                    child_color = _label_color(component) or color
                    node["children"].append(visit(referred, placed, path + [child_name], child_color, child_name,
                                                  occurrence + (at - 1,), entries + [entry_of(component)], inner))
                return node
            shape = XCAFDoc_ShapeTool.GetShape_s(label)
            entry = entry_of(label)
            index = by_entry.get(entry)
            if index is None:
                index = by_entry[entry] = len(self.prototypes)
                self.prototypes.append(_prototype(index, label, shape, entry, self))
                claim = _label_text(label, KEY_GUID)
                if claim is not None:
                    claims[index] = claim
            placed = location.Multiplied(shape.Location())
            if occurrence in self.locals:
                self.locals[occurrence] = self.locals[occurrence].Multiplied(shape.Location())
            prototype = self.prototypes[index]
            self.instances.append(Instance(index, path, _matrix(placed),
                                           color if color != prototype.color else None))
            self.instance_paths.append(occurrence)
            return {"name": name, "prototype": index, "instance": len(self.instances) - 1}

        free = Sequence_TDF_Label()
        shapes.GetFreeShapes(free)
        roots = []
        for at in range(1, free.Length() + 1):
            label = free.Value(at)
            name = named(label) or f"{self.path.stem}{'' if free.Length() == 1 else at}"
            roots.append(visit(label, _identity(), [name], None, name, () if free.Length() == 1 else (at - 1,),
                               [entry_of(label)]))
        if len(roots) == 1:
            self.tree = roots[0]
            self.name = roots[0]["name"]
        else:
            self.tree = {"name": self.path.stem, "children": roots}
        _checked_keys(self.prototypes, claims)

    @property
    def closure(self) -> dict[str, Any] | None:
        """The build closure an xbf this engine wrote holds (``previous``): its engine,
        libraries, source, modules, inputs and key; None for a document with none."""
        import json

        found = _label_text(self.doc.Main(), CLOSURE_GUID)
        return json.loads(found) if found else None

    @property
    def animations(self) -> Any:
        """The build's animations the document records (``animations.record``), by name, as the
        harvest made them: what a GLB of it bakes. None for a document with none."""
        from cadgen.engine.animations import from_record

        return from_record(_label_text(self.doc.Main(), ANIMATIONS_GUID))

    def structure(self) -> dict[str, Any]:
        """The document as the page reads it (``serve``): its prototypes, its instances
        and its tree, with every name and colour, and its mechanism (``kinematics``,
        where it has one); no geometry."""
        found = {
            "name": self.name,
            "path": str(self.path),
            "version": f"{self.version[0]}-{self.version[1]}",
            "units": "mm",
            "prototypes": [{
                "index": p.index, "key": p.key, "name": p.name, "color": p.color,
                "faceNames": {str(k): v for k, v in sorted(p.face_names.items())},
                "edgeNames": {str(k): v for k, v in sorted(p.edge_names.items())},
                "vertexNames": {str(k): v for k, v in sorted(p.vertex_names.items())},
                "faceColors": {str(k): v for k, v in sorted(p.face_colors.items())},
                "material": material_json(p.material),
                "faceMaterials": {str(k): material_json(v) for k, v in sorted(p.face_materials.items())},
            } for p in self.prototypes],
            "instances": [{"prototype": i.prototype, "path": "/".join(i.path), "matrix": i.matrix, "color": i.color}
                          for i in self.instances],
            "tree": self.tree,
        }
        if self.mechanism is not None:
            from cadgen.engine import mechanism

            found["kinematics"] = mechanism.block(self.mechanism, self.instance_paths,
                                                  lambda path: _matrix(self.worlds[path]))
        animated = _animations_listed(self.animations)
        if animated:
            found["animations"] = animated
        return found


def saved(path: Path) -> "Tree | None":
    """The tree this process last saved at ``path`` (``save``), or None."""
    return _SAVED.get(Path(path).resolve())


def tree_structure(tree: Tree, path: Path) -> dict[str, Any]:
    """The structure ``Loaded(path).structure()`` reads from the document ``tree`` was saved
    as -- the same prototypes in the same order, instances, names, colours as the file
    gives them back, and the file's version -- made from the tree in memory, without
    reading the file. It follows ``to_xcaf`` and ``Loaded._walk`` rule for rule: a part's
    own colour wins over the one its placement passes down, an assembly label has none, a
    colour reads back as the kernel stores it, and a name falls back to the referred
    prototype's, then to its parent's with the component's place."""
    from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_VERTEX
    from OCP.TopExp import TopExp
    from OCP.collections import IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher

    # A document no file holds yet (code built with no --xbf) has the version "0-0".
    path = Path(path).resolve() if path is not None else None
    try:
        stat = path.stat() if path is not None else None
    except OSError:
        stat = None
    version = f"{stat.st_mtime_ns}-{stat.st_size}" if stat is not None else "0-0"
    prototypes: list[dict[str, Any]] = []
    instances: list[dict[str, Any]] = []
    index_of: dict[int, int] = {}
    read_colors: dict[tuple, tuple] = {}

    def read(rgba: tuple | None) -> tuple | None:
        if rgba is None:
            return None
        found = read_colors.get(rgba)
        if found is None:
            quantity = _quantity(rgba)
            rgb = quantity.GetRGB()
            found = read_colors[rgba] = (round(rgb.Red(), 6), round(rgb.Green(), 6), round(rgb.Blue(), 6),
                                         round(quantity.Alpha(), 6))
        return found

    def entry(part: Part, index: int) -> dict[str, Any]:
        faces = IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher()
        TopExp.MapShapes_s(part.shape, TopAbs_FACE, faces)
        names = part.names or {}
        face_names = {ordinal: text for ordinal, text in enumerate(names.get("faces") or [], 1)
                      if text and ordinal <= faces.Extent()}
        edge_names: dict[int, str] = {}
        if any(names.get("edges") or []):
            edges = IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher()
            TopExp.MapShapes_s(part.shape, TopAbs_EDGE, edges)
            edge_names = {ordinal: text for ordinal, text in enumerate(names.get("edges") or [], 1)
                          if text and ordinal <= edges.Extent()}
        vertex_names: dict[int, str] = {}
        if any(names.get("vertices") or []):
            vertices = IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher()
            TopExp.MapShapes_s(part.shape, TopAbs_VERTEX, vertices)
            vertex_names = {ordinal: text for ordinal, text in enumerate(names.get("vertices") or [], 1)
                            if text and ordinal <= vertices.Extent()}
        face_colors = {ordinal: read(rgba) for ordinal, rgba in part.face_colors.items()
                       if 1 <= ordinal <= faces.Extent()}
        material = None if part.material is None else as_read(part.material, read(part.color or DEFAULT_COLOR))
        face_materials = {ordinal: as_read(given, read(part.face_colors.get(ordinal) or DEFAULT_COLOR))
                          for ordinal, given in part.face_materials.items() if 1 <= ordinal <= faces.Extent()}
        return {"index": index, "key": part.key, "name": part.name or f"part{index + 1}", "color": read(part.color),
                "faceNames": {str(k): v for k, v in sorted(face_names.items())},
                "edgeNames": {str(k): v for k, v in sorted(edge_names.items())},
                "vertexNames": {str(k): v for k, v in sorted(vertex_names.items())},
                "faceColors": {str(k): v for k, v in sorted(face_colors.items())},
                "material": material_json(material),
                "faceMaterials": {str(k): material_json(v) for k, v in sorted(face_materials.items())}}

    paths: list[tuple[int, ...]] = []

    def visit(prototype: Any, location: Any, names: list[str], inherited: tuple | None, name: str,
              occurrence: tuple[int, ...] = ()) -> dict:
        if isinstance(prototype, Assembly):
            node: dict[str, Any] = {"name": name, "children": []}
            for at, component in enumerate(prototype.components, 1):
                held = component.prototype
                child_name = component.name or held.name or f"{name}.{at}"
                # A component colour equal to its part's is not written, and a part's own colour
                # wins over the one it inherits: either way the outcome is the same.
                child_color = read(component.color) or inherited
                node["children"].append(visit(held, location.Multiplied(component.location), names + [child_name],
                                              child_color, child_name, occurrence + (at - 1,)))
            return node
        own = read(prototype.color)
        color = own or inherited
        index = index_of.get(id(prototype))
        if index is None:
            index = index_of[id(prototype)] = len(prototypes)
            prototypes.append(entry(prototype, index))
        instances.append({"prototype": index, "path": "/".join(names),
                          "matrix": _matrix(location.Multiplied(prototype.shape.Location())),
                          "color": color if color != own else None})
        paths.append(occurrence)
        return {"name": name, "prototype": index, "instance": len(instances) - 1}

    root = visit(tree.root, _identity(), [tree.root.name], None, tree.root.name)
    found = {"name": root["name"], "path": str(path) if path is not None else "", "version": version, "units": "mm",
             "prototypes": prototypes, "instances": instances, "tree": root}
    if tree.mechanism is not None:
        from cadgen.engine import mechanism

        found["kinematics"] = mechanism.block(tree.mechanism, paths,
                                              lambda at: _matrix(mechanism._occurrence(tree, at)[0]))
    animated = _animations_listed(tree.animations)
    if animated:
        found["animations"] = animated
    return found


def _animations_listed(resolved: Any) -> list[dict[str, Any]]:
    """A document's animations (``animations.harvest``, by name) as its structure lists them: each
    its name and duration, in the build's order; the tracks stay the GLB's."""
    return [{"name": item.name, "duration": item.duration} for item in (resolved or {}).values()]


def _read(path: Path) -> Any:
    from OCP.BinXCAFDrivers import BinXCAFDrivers_DocumentRetrievalDriver
    from OCP.Message import Message_ProgressRange
    from OCP.TCollection import TCollection_ExtendedString

    suffix = path.suffix.lower()
    with _XCAF_LOCK:
        doc = _new_document()
        if suffix == ".xbf":
            # The application's Open and GetDocument leave the Python-side document empty:
            # the retrieval driver reads into the one handed to it. A file it cannot read
            # whole (cut short, garbage) it says so of, or raises: either is an error here.
            from OCP.PCDM import PCDM_ReaderStatus

            driver = BinXCAFDrivers_DocumentRetrievalDriver()
            driver.Read(TCollection_ExtendedString(str(path), True), doc, _application(), None,
                        Message_ProgressRange())
            status = driver.GetStatus()
            del driver
            if status != PCDM_ReaderStatus.PCDM_RS_OK:
                raise ValueError(f"cannot read {path}: {status.name}")
        elif suffix in (".step", ".stp"):
            from OCP.IFSelect import IFSelect_RetDone
            from OCP.Interface import Interface_Static
            from OCP.STEPCAFControl import STEPCAFControl_Reader

            reader = STEPCAFControl_Reader()
            reader.SetNameMode(True)
            reader.SetColorMode(True)
            reader.SetMatMode(True)
            # The reader defines the translator's parameters: set them once it exists.
            Interface_Static.SetIVal_s("read.stepcaf.subshapes.name", 1)
            if reader.ReadFile(str(path)) != IFSelect_RetDone:
                raise ValueError(f"cannot read {path}")
            refuse_external_files(reader, path)
            if not reader.Transfer(doc):
                raise ValueError(f"cannot read {path}")
        else:
            raise ValueError(f"not a document the engine reads: {path.name}")
    return doc


def refuse_external_files(reader: Any, path: Any) -> None:
    """A STEP that names another file (an external document: ``DOCUMENT_FILE``) refused, after
    ``ReadFile`` and before ``Transfer``: the XCAF reader's transfer opens every file such a STEP
    names -- beside it, above it, or anywhere by an absolute path -- and adds what it reads to the
    document as the STEP's own parts. A STEP read is the file it is, so a reference to another is
    an error here, wherever the read is made (``_read``, ``reader._parse``). The model's entities
    are counted by kind in the kernel (``NbTyped``): fetched into Python one by one, each costs
    about 0.25 ms, four minutes for a 63 MB STEP of a million entities."""
    from OCP.StepBasic import StepBasic_DocumentFile

    model = reader.ChangeReader().Model()
    if model.Entities().NbTyped(StepBasic_DocumentFile.get_type_descriptor_s()):
        raise ValueError(f"cannot read {Path(path).name}: it names another file to read (an external "
                         f"reference); the engine reads a STEP's own geometry only")


def read_bytes(data: bytes) -> Any:
    """An xbf's bytes read into a document, in memory: the application's stream read, overwriting
    into a document made here (``PCDM_ReaderFilter.AppendMode_e.AppendMode_Overwrite``), since the document a
    plain stream read makes is one OCP cannot hand back (``_new_document``)."""
    import io

    from OCP.PCDM import PCDM_ReaderFilter, PCDM_ReaderStatus

    with _XCAF_LOCK:
        doc = _new_document()
        status = _application().Open(io.BytesIO(data), doc, PCDM_ReaderFilter(PCDM_ReaderFilter.AppendMode_e.AppendMode_Overwrite))
    if status != PCDM_ReaderStatus.PCDM_RS_OK:
        raise ValueError(f"cannot read the document's bytes: {status.name}")
    return doc


def to_bytes(doc: Any, shapes: Iterable[Any] | None = None) -> bytes:
    """A document as the bytes ``save`` writes of it, in memory: the application's stream write
    (which saves a document the application has opened: this one is, from now on), its parts'
    ``shapes`` written as ``save`` writes them (``unchecked``), with the written date ``WRITTEN_DATE``."""
    import io

    from OCP.PCDM import PCDM_StoreStatus

    stream = io.BytesIO()
    with _XCAF_LOCK, unchecked(list(shapes) if shapes is not None else _free_shapes(doc)):
        if not doc.IsOpened():
            doc.Open(_application())
        status = _application().SaveAs(doc, stream)
    if status != PCDM_StoreStatus.PCDM_SS_OK:
        raise OSError(f"could not write the document's bytes: {status}")
    data = stream.getvalue()
    found = _HEADER_DATE.search(data, 0, _INFO_BYTES)
    if found is None:
        raise OSError("the document's bytes have no BinXCAF creation date")
    return data[:found.start(1)] + WRITTEN_DATE + data[found.end(1):]


@functools.cache
def _writer() -> str:
    from cadgen.engine.previous import FORMAT, version

    return WRITER.format(format=FORMAT, release=version())


def written_format(writer: str | None) -> str | None:
    """The xbf format a document's writer names (``xbf/8``), or None for another program's."""
    import re

    found = re.match(r"cadgen\.engine (xbf/[0-9]+) \(cadgen ", writer or "")
    return found.group(1) if found else None


def _label_text(label: Any, guid: str) -> str | None:
    from OCP.Standard import Standard_GUID
    from OCP.TDataStd import TDataStd_AsciiString

    found = TDataStd_AsciiString()
    return found.Get().ToCString() if _find(label, found, Standard_GUID(guid)) else None


def _find(label: Any, attribute: Any, guid: Any) -> bool:
    # FindAttribute faults on a label without the attribute: ask IsAttribute first.
    return label.IsAttribute(guid) and label.FindAttribute(guid, attribute)


def _entry(label: Any) -> str:
    from OCP.TCollection import TCollection_AsciiString
    from OCP.TDF import TDF_Tool

    text = TCollection_AsciiString()
    TDF_Tool.Entry_s(label, text)
    return text.ToCString()


def _label_name(label: Any) -> str:
    from OCP.TDataStd import TDataStd_Name

    found = TDataStd_Name()
    if _find(label, found, TDataStd_Name.GetID_s()):
        return found.Get().ToExtString()
    return ""


# OCCT's name for an occurrence its file left unnamed: the label it got (`=>[0:1:1:2]`).
_PLACEHOLDER = re.compile(r"^=>\[[0-9:]*\]$")
# ISO 10303-21's string escapes as a name can still hold them: a file that escaped its
# backslashes once too often leaves them for the reader to undo (`\\X2\\51F8\\X0\\`).
_ESCAPE = re.compile(r"\\{1,2}X2\\{1,2}((?:[0-9A-Fa-f]{4})+)\\{1,2}X0\\{1,2}|\\{1,2}X4\\{1,2}((?:[0-9A-Fa-f]{8})+)"
                     r"\\{1,2}X0\\{1,2}|\\{1,2}X\\{1,2}([0-9A-Fa-f]{2})|\\{1,2}S\\{1,2}(.)")


def step_name(text: str) -> str:
    """A name as a STEP file means it: its ``\\X2\\``/``\\X4\\`` (UTF-16, UTF-32), ``\\X\\``
    (ISO 8859-1) and ``\\S\\`` escapes decoded, and OCCT's placeholder for an unnamed
    occurrence (``=>[0:1:1:2]``) no name at all, so the product's name stands."""
    if _PLACEHOLDER.match(text):
        return ""
    if "\\" not in text:
        return text

    def decode(match: Any) -> str:
        wide, widest, byte, shifted = match.groups()
        if wide:
            return bytes.fromhex(wide).decode("utf-16-be", errors="replace")
        if widest:
            return bytes.fromhex(widest).decode("utf-32-be", errors="replace")
        if byte:
            return bytes.fromhex(byte).decode("latin-1")
        return chr(ord(shifted) + 128)

    return _ESCAPE.sub(decode, text)


def _label_color(label: Any) -> tuple | None:
    from OCP.Quantity import Quantity_ColorRGBA
    from OCP.XCAFDoc import XCAFDoc_ColorGen, XCAFDoc_ColorSurf, XCAFDoc_ColorTool

    # Linear RGB and alpha, as build123d's Color holds a colour.
    rgba = Quantity_ColorRGBA()
    for kind in (XCAFDoc_ColorSurf, XCAFDoc_ColorGen):
        if XCAFDoc_ColorTool.GetColor_s(label, kind, rgba):
            rgb = rgba.GetRGB()
            return (round(rgb.Red(), 6), round(rgb.Green(), 6), round(rgb.Blue(), 6), round(rgba.Alpha(), 6))
    return None


def _f32(value: float) -> float:
    """A value as the document keeps it, a 32-bit float, rounded as colours read back."""
    import struct

    return round(struct.unpack("<f", struct.pack("<f", float(value)))[0], 6)


def as_read(material: Any, rgba: tuple) -> Any:
    """``material`` as a document read back gives it: drawn in ``rgba`` (the base colour
    as read), its PBR factors (metallic, roughness, emissive, IOR) as 32-bit floats, its density
    through the kernel's g/cm^3, no emissive where it is black, no description where it is
    empty; every other field as it is (``_write_extra`` keeps doubles)."""
    from cadgen.engine.colors import Linear

    emissive = Linear(_f32(value) for value in (material.emissive or (0.0, 0.0, 0.0)))
    return material.but(density=round(material.density / 1000.0 * 1000.0, 6) if material.density else None,
                        color=Linear(rgba), metallic=_f32(material.metallic), roughness=_f32(material.roughness),
                        ior=_f32(material.ior), emissive=emissive if any(emissive) else None,
                        description=material.description or None)


# A material's fields as the structure carries them, by the structure's (camelCase) names.
_JSON_FIELDS = (("name", "name"), ("family", "family"), ("standard", "standard"), ("description", "description"),
                ("source", "source"), ("density", "density"), ("young_modulus", "youngModulus"),
                ("poisson_ratio", "poissonRatio"), ("yield_strength", "yieldStrength"),
                ("ultimate_strength", "ultimateStrength"), ("thermal_expansion", "thermalExpansion"),
                ("thermal_conductivity", "thermalConductivity"), ("specific_heat", "specificHeat"),
                ("isotropic", "isotropic"), ("color", "color"), ("metallic", "metallic"), ("roughness", "roughness"),
                ("ior", "ior"), ("anisotropy", "anisotropy"), ("anisotropy_rotation", "anisotropyRotation"),
                ("transmission", "transmission"), ("transmission_color", "transmissionColor"),
                ("transmission_depth", "transmissionDepth"), ("coat", "coat"), ("coat_roughness", "coatRoughness"),
                ("emissive", "emissive"), ("emissive_strength", "emissiveStrength"))


def material_json(material: Any) -> dict[str, Any] | None:
    """A material as the structure carries it: every field, its colour the base colour it is
    drawn in, ``emissive`` black where it has none, tuples as lists."""
    if material is None:
        return None
    found: dict[str, Any] = {}
    for field, key in _JSON_FIELDS:
        value = getattr(material, field)
        if field == "color":
            value = value or DEFAULT_COLOR
        elif field == "emissive":
            value = value or (0.0, 0.0, 0.0)
        found[key] = list(value) if isinstance(value, tuple) else value
    return found


def material_from_json(value: dict[str, Any] | None) -> Any:
    """The ``Material`` of ``material_json``'s answer (a black ``emissive`` is none); None for None."""
    if not value:
        return None
    from cadgen.engine.colors import Linear
    from cadgen.engine.materials import Material

    fields = {field: value[key] for field, key in _JSON_FIELDS if value.get(key) is not None}
    for field in ("color", "transmission_color", "emissive"):
        if field in fields:
            fields[field] = Linear(fields[field])
    if not any(fields.get("emissive") or ()):
        fields.pop("emissive", None)
    return Material(**fields)


def _label_material(label: Any) -> Any:
    """The material a label was given, as ``as_read`` describes it, or None: its
    ``XCAFDoc_Material`` (name, description, density, and the rest ``_write_extra`` wrote
    beside it) and its ``XCAFDoc_VisMaterial`` (PBR), either alone too -- a STEP the engine did
    not write has no PBR, and is drawn in the label's colour."""
    from OCP.TDataStd import TDataStd_TreeNode
    from OCP.XCAFDoc import XCAFDoc, XCAFDoc_Material, XCAFDoc_VisMaterialTool

    from cadgen.engine.colors import Linear
    from cadgen.engine.materials import Material

    name = description = ""
    density = None
    extra: dict[str, Any] = {}
    node = TDataStd_TreeNode()
    if _find(label, node, XCAFDoc.MaterialRefGUID_s()) and node.HasFather():
        physical = XCAFDoc_Material()
        held = node.Father().Label()
        if _find(held, physical, XCAFDoc_Material.GetID_s()):
            name = physical.GetName().ToCString() if physical.GetName() is not None else ""
            description = physical.GetDescription().ToCString() if physical.GetDescription() is not None else ""
            density = round(physical.GetDensity() * 1000.0, 6) or None
            extra = _read_extra(held)
    visual = XCAFDoc_VisMaterialTool.GetShapeMaterial_s(label)
    pbr = visual.PbrMaterial() if visual is not None and visual.HasPbrMaterial() else None
    ior = 1.5
    if pbr is not None:
        if not name:
            raw = visual.RawName()
            name = raw.ToCString() if raw is not None else ""
        base = pbr.BaseColor
        rgb = base.GetRGB()
        rgba = (round(rgb.Red(), 6), round(rgb.Green(), 6), round(rgb.Blue(), 6), round(base.Alpha(), 6))
        glow = visual.ConvertToCommonMaterial().EmissiveColor
        emissive = (_f32(glow.Red()), _f32(glow.Green()), _f32(glow.Blue()))
        metallic, roughness, ior = _f32(pbr.Metallic), _f32(pbr.Roughness), _f32(pbr.RefractionIndex)
    elif name:
        rgba, emissive, metallic, roughness = _label_color(label), (0.0, 0.0, 0.0), 0.0, 0.5
    else:
        return None
    return Material(name or "material", density, color=None if rgba is None else Linear(rgba), metallic=metallic,
                    roughness=roughness, ior=ior, emissive=Linear(emissive) if any(emissive) else None,
                    description=description or None, **extra)


def _prototype(index: int, label: Any, shape: Any, entry: str, loaded: Loaded) -> Prototype:
    from OCP.collections import Sequence_TDF_Label
    from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_VERTEX
    from OCP.TopExp import TopExp
    from OCP.collections import IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher
    from OCP.XCAFDoc import XCAFDoc_ShapeTool

    local = shape.Located(_identity())
    found_key = geometry_key(local, read=True)  # the file's key is checked against it (``_checked_keys``)
    face_names: dict[int, str] = {}
    edge_names: dict[int, str] = {}
    vertex_names: dict[int, str] = {}
    vertices = None
    face_colors: dict[int, tuple] = {}
    face_materials: dict[int, Any] = {}
    part_color = _label_color(label)
    subs = Sequence_TDF_Label()
    XCAFDoc_ShapeTool.GetSubShapes_s(label, subs)
    if subs.Length():
        faces = IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher()
        TopExp.MapShapes_s(shape, TopAbs_FACE, faces)
        edges = IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher()
        TopExp.MapShapes_s(shape, TopAbs_EDGE, edges)
        holding: list[tuple[Any, tuple]] = []  # coloured sub-shapes that hold faces: solids, shells
        for at in range(1, subs.Length() + 1):
            sub = subs.Value(at)
            held = XCAFDoc_ShapeTool.GetShape_s(sub)
            if held.IsNull():
                continue
            kind = held.ShapeType()
            if kind not in (TopAbs_FACE, TopAbs_EDGE, TopAbs_VERTEX):
                rgba = _label_color(sub)
                if rgba is not None:
                    holding.append((held, rgba))
            elif kind == TopAbs_FACE:
                ordinal = faces.FindIndex(held)
                if ordinal:
                    name = _label_name(sub)
                    if name:
                        face_names[ordinal] = name
                    color = _label_color(sub)
                    if color is not None:
                        face_colors[ordinal] = color
                    given = _label_material(sub)
                    if given is not None:
                        face_materials[ordinal] = given
            elif kind == TopAbs_EDGE:
                ordinal = edges.FindIndex(held)
                name = _label_name(sub) if ordinal else ""
                if name:
                    edge_names[ordinal] = name
            elif kind == TopAbs_VERTEX:
                if vertices is None:
                    vertices = IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher()
                    TopExp.MapShapes_s(shape, TopAbs_VERTEX, vertices)
                ordinal = vertices.FindIndex(held)
                name = _label_name(sub) if ordinal else ""
                if name:
                    vertex_names[ordinal] = name
        if holding:
            part_color = _held_colors(faces, holding, part_color, face_colors)
    name = step_name(_label_name(label)) if loaded.step else _label_name(label)
    return Prototype(index, local, name or f"part{index + 1}", part_color, found_key,
                     face_names, edge_names, face_colors, entry, _label_material(label), face_materials,
                     vertex_names=vertex_names)


def _held_colors(faces: Any, holding: list[tuple[Any, tuple]], color: tuple | None,
                 face_colors: dict[int, tuple]) -> tuple | None:
    """A part's colour, and its faces' (into ``face_colors``), where its file colours the solids or
    shells that hold its faces: a STEP styles a representation item (``STYLED_ITEM``), and a part of
    several solids is one ``MANIFOLD_SOLID_BREP`` each, styled each, which the XCAF reader puts on
    sub-shape labels of the part and none on the part. Each face takes the colour of the innermost
    coloured shape holding it, under its own. One colour over every face is the part's colour;
    else each face so coloured, and not the part's colour, is a painted face."""
    from OCP.TopAbs import TopAbs_FACE
    from OCP.TopExp import TopExp
    from OCP.collections import IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher

    held = []
    for shape, rgba in holding:
        inner = IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher()
        TopExp.MapShapes_s(shape, TopAbs_FACE, inner)
        held.append((inner, int(shape.ShapeType()), rgba))
    given: dict[int, tuple] = {}
    # The outermost first, so an inner shape's colour is the one a face keeps (a shell inside its
    # solid holds as many faces: a shell comes after a solid in the kernel's order of kinds).
    for inner, _kind, rgba in sorted(held, key=lambda item: (-item[0].Extent(), item[1])):
        for at in range(1, inner.Extent() + 1):
            ordinal = faces.FindIndex(inner.FindKey(at))
            if ordinal:
                given[ordinal] = rgba
    if len(given) == faces.Extent() and len(set(given.values())) == 1:
        return next(iter(given.values()))
    for ordinal, rgba in given.items():
        if ordinal not in face_colors and rgba != color:
            face_colors[ordinal] = rgba
    return color


def _matrix(location: Any) -> list[float]:
    transform = location.Transformation()
    value = transform.Value
    rows = [[value(row, column) for column in (1, 2, 3, 4)] for row in (1, 2, 3)] + [[0.0, 0.0, 0.0, 1.0]]
    return [rows[row][column] for column in range(4) for row in range(4)]


_LOADED: dict[Path, Loaded] = {}


def load(path: Path) -> Loaded:
    """The document at ``path``, read once and held while its file stays as it was:
    a changed file (its modification time or size) is read again."""
    path = Path(path).resolve()
    stat = path.stat()
    found = _LOADED.get(path)
    if found is not None and found.version == (stat.st_mtime_ns, stat.st_size):
        return found
    found = _LOADED[path] = Loaded(path)
    return found
