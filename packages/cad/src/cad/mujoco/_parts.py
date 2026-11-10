"""A spec's parts, remembered: ``collisions``, ``fit`` and ``decompose`` on a spec ``spec`` made.

A MuJoCo function chooses a part's collision by the part's label path, the path ``cad model inspect``
prints (``hinge/arm``): a last segment is enough where only one part ends in it (``arm``), and any
trailing run of segments names the parts it ends; one that names two is refused with their full paths,
and one that names none with the parts there. A part is never named by a generated geom name
(``arm_collision``): those follow writer rules a script should not depend on.

**What ``spec`` remembers.** An ``MjSpec`` takes no new attributes, so each spec ``spec`` returns is a key
of a weak dictionary (``SOURCES``) whose value is what the helpers need, and goes when the spec goes:

- From a document (a model call's handle, a build123d shape, a STEP or an ``.xbf``): each part by its
  occurrence path -- the body its geoms are in, its frame there (metres), its visual and collision geoms by
  name as the export wrote them (``mjcf.rendered``'s owners), its mesh (the description's, metres, the one
  ``decompose`` cuts) and its solid (the B-rep bytes, read again when a primitive is fitted).
- From an MJCF path: no solids. Each part is a mesh a colliding geom uses, named by the mesh's name (an
  export names a part's mesh for the part), its collision geoms those geoms; its triangles are read from
  the mesh's file by MuJoCo when a decomposition asks for them.

A spec made another way (``MjSpec.from_file``, a ``copy()``) has no remembered parts and is refused by
name. Each helper keeps the record up to date: the geoms it adds are the part's collisions after it.

**A body weighed by its collision.** A part with no density and no declared mass has no ``<inertial>``: MuJoCo
weighs its body from its geoms, so ``fit`` or ``decompose`` on it changes its mass and inertia. Each says so once
per body, as a Python warning (``UserWarning``) at the call, naming how to stop it (a material with a density, or
``mass()`` on the model).

**``fit``.** The kernel's fit of the exact solid (``describe.fit``: the oriented bounding box of the
B-rep; a cylinder about the axis the part is turned about). It replaces the part's collision geoms with one geom named as the export names a part's
collision (``<part>_collision`` where its visual holds ``<part>``), which keeps the first one's contact
settings (class, friction, contact types). A spec read from an MJCF has no solid and is refused, as a
part read from a mesh file is.

**``decompose``.** CoACD's convex hulls of the part's mesh (``cad.engine.hulls``: its cache, its child
process, its refusals where coacd cannot run), each a mesh ``<mesh>_hull<i>`` (a file
``<model>_<mesh>_hull<i>.stl`` in the engine's cache, ``places.cache_dir()/mjcf/hulls/<digest>``) and a
collision geom ``<part>_hull<i>`` where the part's collision was. It needs the
mesh, not the kernel, so it works on a spec read from an MJCF too.
"""

from __future__ import annotations

import weakref
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from cad.engine.hulls import MAX_HULLS

__all__ = ["SOURCES", "collisions", "decompose", "fit", "remember_document", "remember_mjcf"]

#: The primitives ``fit`` makes: a geom of each kind of MuJoCo's.
PRIMITIVES = ("box", "sphere", "cylinder", "capsule")
#: How many parts a refusal names before it says how many more.
SHOWN = 12
#: The contact settings a geom put in a part's collision's place takes from it.
CONTACT = ("contype", "conaffinity", "condim", "group", "priority", "friction", "solmix", "solref", "solimp",
           "margin", "gap")


@dataclass
class Part:
    """One part of a remembered spec (the module docstring)."""

    path: str  # its label path; an MJCF part's mesh name
    name: str  # its last segment: the stem its geoms are named by
    body: str  # the body its geoms are in ("" for an MJCF part, whose geoms may be in several)
    placement: np.ndarray  # its frame in its body (metres)
    collisions: list[str] = field(default_factory=list)  # its collision geoms, by name
    visuals: list[str] = field(default_factory=list)
    mesh: str = ""  # the stem its hull meshes are named by: its mesh's name
    triangles: tuple[np.ndarray, np.ndarray] | None = None  # its mesh (metres), a document's
    solid: bytes | None = None  # its B-rep, a document's


@dataclass
class Source:
    """What ``spec`` remembers of one spec: its model's name, whether it came from a document, its parts."""

    model: str
    document: bool
    parts: dict[str, Part]
    weighed: set[str] = field(default_factory=set)  # the bodies told their collision now sets their mass (``_weighed``)


#: Each spec ``spec`` made, and what it remembers of it.
SOURCES: "weakref.WeakKeyDictionary[Any, Source]" = weakref.WeakKeyDictionary()


def remember_document(made: Any, description: Any, owners: dict[str, dict[str, Any]],
                      solids: dict[str, bytes]) -> Any:
    """``made``, a spec written from ``description``, remembered with its parts (``owners``: what the writer wrote
    of each, ``mjcf.rendered``) and their solids by mesh key. Returns ``made``."""
    parts = {}
    for path, owned in owners.items():
        key = owned.get("key")
        mesh = description.meshes.get(key) if key is not None else None
        parts[path] = Part(path, path.rsplit("/", 1)[-1], owned["body"], np.asarray(owned["placement"], dtype=float),
                           list(owned["collisions"]), list(owned["visuals"]), mesh.name if mesh is not None else "",
                           (mesh.positions, mesh.triangles) if mesh is not None else None, solids.get(key))
    SOURCES[made] = Source(description.name, True, parts)
    return made


def remember_mjcf(mujoco: Any, made: Any) -> Any:
    """``made``, a spec read from an MJCF, remembered with its parts: each mesh a colliding geom uses. Returns
    ``made``."""
    parts: dict[str, Part] = {}
    for geom in made.geoms:
        if geom.type == mujoco.mjtGeom.mjGEOM_MESH and geom.meshname and _colliding(geom):
            part = parts.setdefault(geom.meshname, Part(geom.meshname, geom.meshname, "", np.eye(4),
                                                        mesh=geom.meshname))
            if geom.name:
                part.collisions.append(geom.name)
    SOURCES[made] = Source(made.modelname or "model", False, parts)
    return made


def _colliding(geom: Any) -> bool:
    return bool(int(geom.contype) or int(geom.conaffinity))


# --- finding a part -----------------------------------------------------------------------------------------------


def _source(spec: Any, said: str) -> Source:
    import mujoco

    if not isinstance(spec, mujoco.MjSpec):
        raise TypeError(f"{said} takes the mujoco.MjSpec cad.mujoco.spec made, not {type(spec).__name__}")
    found = SOURCES.get(spec)
    if found is None:
        raise ValueError(f"{said}: this MjSpec was not made by cad.mujoco.spec (MjSpec.from_file, a copy, a new "
                         "spec), so its parts are not known: make it with spec(model_or_file)")
    return found


def _part(source: Source, part: Any, said: str) -> Part:
    """The part ``part`` names (the module docstring's label path), refused by name where it names none or two."""
    if not isinstance(part, str) or not part.strip("/"):
        raise TypeError(f"{said}: a part's label path (as `cad model inspect` prints it), not {part!r}")
    wanted = part.strip("/")
    if wanted in source.parts:
        return source.parts[wanted]
    found = [path for path in source.parts if path.endswith("/" + wanted)]
    if len(found) == 1:
        return source.parts[found[0]]
    if found:
        raise ValueError(f"{said}: {part!r} names {len(found)} parts of {source.model}: {_listed(sorted(found))}; "
                         "name one by its path")
    there = sorted(source.parts)
    kind = "parts" if source.document else "parts (the meshes its colliding geoms use: it was read from an MJCF)"
    raise ValueError(f"{said}: {source.model} has no part {part!r}; its {kind}: "
                     + (_listed(there) if there else "none"))


def _listed(names: list[str]) -> str:
    shown = ", ".join(names[:SHOWN])
    return shown + (f" and {len(names) - SHOWN} more" if len(names) > SHOWN else "")


def _geoms(mujoco: Any, spec: Any, source: Source, part: Part) -> list[Any]:
    """The part's collision geoms as they are in ``spec`` now: those it remembers that are still there and, read from
    an MJCF, every colliding geom on its mesh (a geom there may have no name)."""
    found = [geom for geom in (spec.geom(name) for name in part.collisions) if geom is not None]
    if not source.document:
        held = {id(geom) for geom in found}
        found += [geom for geom in spec.geoms if geom.type == mujoco.mjtGeom.mjGEOM_MESH
                  and geom.meshname == part.mesh and _colliding(geom) and id(geom) not in held]
    return found


# --- the helpers ----------------------------------------------------------------------------------------------------


def collisions(spec: Any, part: str) -> list[Any]:
    """The collision geoms (``mujoco.MjsGeom``) of the part ``part`` names, a label path (the module docstring):
    a list, empty for a part that collides as nothing, never None."""
    import mujoco

    source = _source(spec, "collisions")
    return _geoms(mujoco, spec, source, _part(source, part, "collisions"))


def fit(spec: Any, part: str, kind: str) -> list[Any]:
    """Replace the collision of the part ``part`` names with the primitive ``kind`` (``box``, ``sphere``, ``cylinder``
    or ``capsule``) the kernel fits to its solid (the module's **fit**). Returns its collision geoms, the one."""
    import mujoco

    from cad.engine.description import DescriptionError

    source = _source(spec, "fit")
    if kind not in PRIMITIVES:
        raise ValueError(f"fit {kind!r}: a primitive is one of {', '.join(PRIMITIVES)}"
                         + ("; decompose(spec, part) cuts a part into convex hulls" if kind == "decomposed" else ""))
    found = _part(source, part, "fit")
    if not source.document:
        raise ValueError(f"fit {found.path!r}: this spec was read from an MJCF, which holds meshes and no solids, and "
                         f"a {kind} is fitted to a part's exact solid: make the spec from the model, its STEP or its "
                         ".xbf, or set the geom's type and size with MuJoCo's API")
    from cad.engine.describe import fit as fitted

    shape = None
    if found.solid is not None:
        from cad.engine.mesh import read_shape

        shape = read_shape(found.solid)
    try:
        frame, size = fitted(shape, found.name, kind)
    except DescriptionError as error:
        raise ValueError(f"fit: {error}") from None
    placed = found.placement @ frame
    geom = _replace(mujoco, spec, source, found, 1)[0]
    geom.type = getattr(mujoco.mjtGeom, f"mjGEOM_{kind.upper()}")
    geom.meshname = ""  # a primitive naming a mesh is fitted to that mesh by MuJoCo's compiler
    if kind == "box":
        geom.size = [value / 2 for value in size]
    elif kind == "sphere":
        geom.size = [size[0], 0.0, 0.0]
    else:
        geom.size = [size[0], size[1] / 2, 0.0]
    _place(geom, placed)
    _weighed(mujoco, spec, source, [geom])
    return [geom]


def decompose(spec: Any, part: str, *, max_hulls: int | None = MAX_HULLS, threshold: float | None = None) -> list[Any]:
    """Replace the collision of the part ``part`` names with the convex hulls CoACD cuts its mesh into (the module's
    **decompose**): ``max_hulls`` at most that many (16 by default, None for no limit), ``threshold`` CoACD's
    concavity threshold, 0.01 to 1, a smaller one cutting finer (CoACD's 0.05 where None). Returns its collision
    geoms, one per hull."""
    import mujoco

    from cad.engine import hulls as hulling

    source = _source(spec, "decompose")
    options = hulling.options(max_hulls, threshold)
    found = _part(source, part, "decompose")
    if source.document:
        if found.triangles is None:
            raise ValueError(f"decompose {found.path!r}: the part has no mesh to cut")
        meshes = [(found.triangles, found.placement, found.body)]
    else:
        meshes = _mjcf_meshes(mujoco, spec, source, found)
    if not meshes:
        raise ValueError(f"decompose {found.path!r}: no collision geom of the part is left to cut")
    try:
        made = hulling.hulls([(positions, triangles, options) for (positions, triangles), _frame, _body in meshes[:1]],
                             names=[found.path])[0]
    except hulling.Unavailable as error:
        raise RuntimeError(f"decompose {found.path!r}: CoACD makes the hulls: {error}") from None
    except hulling.Failed as error:
        raise RuntimeError(f"decompose {found.path!r}: CoACD could not decompose it: {error}") from None
    if not made:
        raise RuntimeError(f"decompose {found.path!r}: CoACD made no hulls of its mesh")
    names = _hull_meshes(mujoco, spec, source, found, made)
    template = _template(mujoco, spec, source, found)
    for geom in _geoms(mujoco, spec, source, found):
        spec.delete(geom)
    found.collisions = []
    taken = {geom.name for geom in spec.geoms if geom.name}
    added = []
    for _triangles, frame, body in meshes:
        holder = spec.worldbody if body in ("", "world") else spec.body(body)
        for at, mesh in enumerate(names):
            geom = _added(mujoco, spec, holder, template)
            geom.name = _unique(f"{found.name}_hull{at}", taken)
            geom.type = mujoco.mjtGeom.mjGEOM_MESH
            geom.meshname = mesh
            _place(geom, frame)
            found.collisions.append(geom.name)
            added.append(geom)
    _weighed(mujoco, spec, source, added)
    return added


# --- the pieces -----------------------------------------------------------------------------------------------------


def _mjcf_meshes(mujoco: Any, spec: Any, source: Source,
                 part: Part) -> list[tuple[tuple[np.ndarray, np.ndarray], Any, str]]:
    """An MJCF part's mesh as its file holds it (metres, the mesh's scale applied: MuJoCo reads it and the frame it
    moved it to is undone), and each of its collision geoms' frame in its body (a 4x4 matrix) and its body."""
    asset = spec.mesh(part.mesh)
    if asset is None:
        raise ValueError(f"decompose {part.path!r}: the spec has no mesh {part.mesh!r}")
    alone = mujoco.MjSpec()
    alone.add_mesh(name="m", file=asset.file, scale=list(asset.scale))
    model = alone.compile()
    start, count = int(model.mesh_vertadr[0]), int(model.mesh_vertnum[0])
    first, faces = int(model.mesh_faceadr[0]), int(model.mesh_facenum[0])
    turn = np.zeros(9)
    mujoco.mju_quat2Mat(turn, model.mesh_quat[0])
    positions = np.asarray(model.mesh_vert[start:start + count], dtype=float) @ turn.reshape(3, 3).T + model.mesh_pos[0]
    triangles = np.asarray(model.mesh_face[first:first + faces], dtype=np.uint32)
    held = (positions.astype(np.float32), triangles)
    return [(held, _frame(mujoco, spec, geom), geom.parent.name) for geom in _geoms(mujoco, spec, source, part)]


def _frame(mujoco: Any, spec: Any, geom: Any) -> np.ndarray:
    """A geom's frame in its body as a 4x4 matrix: its ``pos`` and its orientation, however it was given."""
    quat = np.asarray(geom.quat, dtype=float)
    if geom.alt.type != mujoco.mjtOrientation.mjORIENTATION_QUAT:
        quat = np.asarray(spec.resolve_orientation(bool(spec.compiler.degree), spec.compiler.eulerseq, geom.alt),
                          dtype=float)
    turn = np.zeros(9)
    mujoco.mju_quat2Mat(turn, quat / np.linalg.norm(quat))
    found = np.eye(4)
    found[:3, :3] = turn.reshape(3, 3)
    found[:3, 3] = np.asarray(geom.pos, dtype=float)
    return found


def _hull_meshes(mujoco: Any, spec: Any, source: Source, part: Part, made: list[tuple[np.ndarray, np.ndarray]]) -> list[str]:
    """The hulls as mesh assets of ``spec``, each a binary STL in the engine's cache named as the export names a
    mesh, and their names: those ``decompose`` made of the part before are removed first."""
    import hashlib

    from cad.engine.export.mjcf import _stem, _stl
    from cad.engine.places import cache_dir

    stem = part.mesh or part.name
    for at in range(len(spec.meshes) * 2):  # a hull mesh of the last decomposition: its names are these
        old = spec.mesh(f"{stem}_hull{at}")
        if old is None:
            break
        if not any(geom.meshname == old.name for geom in spec.geoms if geom.name not in part.collisions):
            spec.delete(old)
    taken = {mesh.name for mesh in spec.meshes if mesh.name}
    names = []
    for at, (positions, triangles) in enumerate(made):
        name = _unique(f"{stem}_hull{at}", taken)
        data = _stl(f"{source.model}/{name}", positions, triangles)
        folder = cache_dir() / "mjcf" / "hulls" / hashlib.sha256(data).hexdigest()[:32]
        file = folder / f"{_stem(source.model)}_{_stem(name)}.stl"
        if not file.is_file():
            from cad.engine.atomic_replace import put

            folder.mkdir(parents=True, exist_ok=True)
            put(file, lambda staged: Path(staged).write_bytes(data))
        spec.add_mesh(name=name, file=str(file.resolve()))
        names.append(name)
    return names


def _template(mujoco: Any, spec: Any, source: Source, part: Part) -> dict[str, Any]:
    """What a geom put in place of the part's collision takes: the first collision geom's class and contact settings,
    else the class named ``collision`` (an export's)."""
    geoms = _geoms(mujoco, spec, source, part)
    if geoms:
        first = geoms[0]
        return {"default": first.classname, **{key: _copied(getattr(first, key)) for key in CONTACT}}
    return {"default": spec.find_default("collision")}


def _copied(value: Any) -> Any:
    return value.copy() if hasattr(value, "copy") else value


def _added(mujoco: Any, spec: Any, body: Any, template: dict[str, Any]) -> Any:
    default = template.get("default")
    geom = body.add_geom(default) if default is not None else body.add_geom()
    for key in CONTACT:
        if key in template:
            setattr(geom, key, template[key])
    return geom


def _replace(mujoco: Any, spec: Any, source: Source, part: Part, count: int) -> list[Any]:
    """The part's collision geoms replaced by ``count`` new ones in its body, the first named as the export names a
    part's collision, each keeping the first old one's contact settings; the part's collisions after."""
    template = _template(mujoco, spec, source, part)
    for geom in _geoms(mujoco, spec, source, part):
        spec.delete(geom)
    taken = {geom.name for geom in spec.geoms if geom.name}
    holder = spec.worldbody if part.body in ("", "world") else spec.body(part.body)
    made = []
    for at in range(count):
        geom = _added(mujoco, spec, holder, template)
        wanted = part.name if part.name not in taken else f"{part.name}_collision"
        geom.name = _unique(wanted if not at else f"{wanted}_{at + 1}", taken)
        made.append(geom)
    part.collisions = [geom.name for geom in made]
    return made


def _place(geom: Any, frame: np.ndarray) -> None:
    """``geom`` at ``frame``, a 4x4 matrix in its body (metres)."""
    from cad.engine.export.mjcf import _quaternion

    geom.pos = [float(value) for value in frame[:3, 3]]
    geom.quat = [float(value) for value in _quaternion(frame)]


def _weighed(mujoco: Any, spec: Any, source: Source, geoms: list[Any]) -> None:
    """Warn, once per body, where a collision just chosen sets its body's mass and inertia: a body with no
    ``<inertial>`` (a part with no density and no declared mass) that MuJoCo weighs from its geoms, these carrying
    mass. Said as a Python warning, as the export's notes are outside a translation (``export.note``), so a
    MuJoCo function's author is told when the choice is made, whether or not the spec is saved."""
    import math
    import warnings

    if spec.compiler.inertiafromgeom == mujoco.mjtInertiaFromGeom.mjINERTIAFROMGEOM_FALSE:
        return
    low, high = (int(value) for value in spec.compiler.inertiagrouprange)
    for geom in geoms:
        body = geom.parent
        named = body.name or "world"
        if named in source.weighed or named == "world" or body.explicitinertial:
            continue
        mass = float(geom.mass)
        if not low <= int(geom.group) <= high or not (mass > 0 if not math.isnan(mass) else float(geom.density) > 0):
            continue
        source.weighed.add(named)
        warnings.warn(f"body {named!r} has no <inertial>, so MuJoCo weighs it from its geoms: the collision just "
                      f"chosen for it ({geom.name!r}) now sets its mass and inertia. Give its parts a material with a "
                      "density, or declare mass() on the model, and the body is weighed as the part is",
                      UserWarning, stacklevel=4)


def _unique(wanted: str, taken: set[str]) -> str:
    name, at = wanted, 1
    while name in taken:
        at += 1
        name = f"{wanted}_{at}"
    taken.add(name)
    return name
