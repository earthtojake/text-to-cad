"""One part's features as plain data: quiddity's recognition document tied to the part's own faces, or why not.

**The tie.** quiddity numbers the faces of the STEP it reads from 0, in the file's order; a part's faces are
numbered from 1 by the kernel (``TopExp.MapShapes``, the ordinal of ``<owner>/face N``). The kernel's writer puts a
shape's faces into a STEP in that order, so quiddity's face ``i`` is ordinal ``i + 1``. That is how the two were
measured to agree, not a thing either promises, so it is checked on every call (``_mapped``, the gate) and a part
that fails any of it has no features at all (``unverified``), never some:

1. quiddity counts the faces the kernel counts, and accounts for each once, in a group this module knows;
2. every face a record names is one of the part's;
3. the point quiddity proves on each face (its ``anchors``) lies on the kernel's face of that ordinal, within
   ``ANCHOR_MM``: whose face is whose, settled by geometry for every face it proves a point on (the result's
   ``unanchored_faces`` are the others);
4. where a record's family says what its faces are, the kernel's own reading of those faces (``surface``) agrees:
   a hole's cylinders are concave, about its axis, at its diameter or a step's; its cones, a rounded floor's
   sphere or torus, a countersink's cone and a mouth chamfer's are about that axis; its planes square to it; a
   step level's faces are planes.

**The result** (``VERSION``) is JSON-safe and the same for the same part: no time, no digest of the bytes handed
over. Lengths are millimetres and points and directions are in the coordinates of the shape handed over (a
document's part: where it stands). A face is its ordinal everywhere this module writes one; ``parameters`` is
quiddity's own record, untouched, so a face index inside it is quiddity's (the ordinal less one).
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable, Sequence
from typing import Any

__all__ = ["ANCHOR_MM", "FACES", "GATE_MM", "GROUPS", "PARALLEL", "REASONS", "SCHEMA", "VERSION", "features_of",
           "unavailable"]

#: The result's own shape: raised when a key changes its meaning or goes.
VERSION = 1
#: The recognition document this mapping reads; another is ``unknown_schema``.
SCHEMA = "quiddity-rust/recognition/6"
#: Where quiddity's accounting puts a face: named by a feature's record; explained as the body's own (a stock
#: side); consulted by a boss as its cap; named by a refusal; or none of them.
GROUPS = ("feature", "body", "supporting", "refused", "unexplained")
#: Why a part has no features (``unavailable``), a closed set.
REASONS = (
    "no_wheel",        # quiddity publishes no wheel for this platform
    "not_installed",   # no environment holds quiddity, and none could be made, or made in time
    "no_faces",        # the part holds no face
    "too_many_faces",  # the part holds more faces than are handed to quiddity (``FACES``)
    "unwritten",       # the kernel could not write the part's STEP
    "refused",         # quiddity refused the STEP, in its words
    "failed",          # quiddity raised (a panic in its Rust among them)
    "stopped",         # quiddity's process ended while it had the part
    "timed_out",       # quiddity did not finish the part in time and was stopped
    "over_memory",     # quiddity's process held more memory than it may with the part and was stopped
    "unreadable",      # quiddity's process answered what this code does not read (another release's recogniser)
    "unknown_schema",  # quiddity answered a document this mapping was not written for
    "unverified",      # the gate: quiddity's faces could not be shown to be the part's
)
#: The most faces a part handed to quiddity holds: one of more is not asked about (``too_many_faces``), on any
#: computer, so whether a part is read is its own, not the speed of whatever reads it. quiddity's time grows
#: faster than a part's faces, and by what they are. Measured on four cores of a Linux machine, quiddity 0.5.5,
#: seconds and the process's peak memory: a filleted plate of drilled holes, 266 faces 2.0 s and 123 MiB, 410
#: faces 3.8 s, 586 faces 7.1 s, 910 faces 16 s, 1306 faces 40 s and 519 MiB; a bar of filleted pockets, the
#: slowest kind found, 186 faces 4.4 s, 276 faces 8.7 s, 366 faces 14 s, 546 faces 31 s; a finned shaft, the one
#: that held most, 244 faces 3.4 s and 222 MiB, 484 faces 4.4 s and 383 MiB. At this bound the slowest kind takes
#: about 10 s, a third of the time a part may take (``_process.TIMEOUT_S``), which a computer three times slower
#: still meets; free-form faces cost by what they are, not by their count (four swept grooves, 18 faces, 2.7 s),
#: and are what the time limit is still for.
FACES = 300
#: A point quiddity proves on a face lies on the kernel's face within this (mm): the two read the same numbers,
#: so they differ by rounding alone; a neighbouring face is a feature's size away.
ANCHOR_MM = 1e-4
#: A record's axis, point and diameter agree with the kernel's surface within this (mm): quiddity publishes a
#: diameter to five decimals and a countersink's point to four.
GATE_MM = 1e-3
#: Two directions are one where the sine of the angle between them is under this (about 0.006 degrees).
PARALLEL = 1e-4

_LETTERS = {"x": (1.0, 0.0, 0.0), "y": (0.0, 1.0, 0.0), "z": (0.0, 0.0, 1.0)}
Vector = tuple[float, float, float]


class _Unverified(Exception):
    """The gate's refusal, in one line."""


class _UnknownSchema(_Unverified):
    """A document this mapping was not written for."""


def unavailable(reason: str, detail: str, quiddity: str | None = None) -> dict[str, Any]:
    """The result of a part that has no features: ``reason`` (``REASONS``) and ``detail``, one line a person can
    read. Nothing was measured, which is not the same as nothing being there."""
    if reason not in REASONS:
        raise ValueError(f"{reason!r} is no reason a part has no features ({', '.join(REASONS)})")
    return {"available": False, "version": VERSION, "quiddity": quiddity, "reason": reason,
            "detail": " ".join(str(detail).split())}


def features_of(parts: Iterable[Any], timeout_s: float) -> list[dict[str, Any]]:
    """Each part's result, in order (``cad.quiddity.features_of``): its STEP written in memory, quiddity asked in
    one process for them all, each answer tied to the part's faces and put through the gate."""
    from cad.build123d import _dfm_brep as brep
    from cad.engine.export.step import shape_bytes
    from cad.quiddity._process import Recogniser

    results = []
    with Recogniser(timeout_s) as ask:
        for given in parts:
            part = given if isinstance(given, brep.Part) else brep.Part(name="", owner="", shape=_shape(given))
            try:
                faces = part.faces()
                if len(faces) > FACES:
                    results.append(unavailable("too_many_faces", f"the part holds {len(faces)} faces, over the "
                                                                 f"{FACES} of a part handed to quiddity"))
                    continue
                step = shape_bytes(part.shape) if faces else b""
            except Exception as error:  # noqa: BLE001 -- a shape the kernel does not write is this part's answer
                results.append(unavailable("unwritten", f"the kernel could not write the part's STEP: {error}"))
                continue
            if not faces:
                results.append(unavailable("no_faces", "the part holds no face"))
                continue
            answer = ask(step)
            version = answer.get("quiddity")
            if "reason" in answer or not ("document" in answer and "anchors" in answer):
                # (a reason this code does not know, or no answer it reads: another release's recogniser's)
                reason, detail = str(answer.get("reason")), str(answer.get("detail") or "")
                if reason not in REASONS:
                    reason, detail = "unreadable", (f"quiddity's process answered {reason!r}, which this does not "
                                                    f"read: {detail}" if "reason" in answer else
                                                    "quiddity's process answered neither a document nor a reason")
                results.append(unavailable(reason, detail, version))
                continue
            try:
                results.append(_mapped(answer["document"], answer["anchors"], str(version), faces, brep.surface))
            except _Unverified as error:
                reason = "unknown_schema" if isinstance(error, _UnknownSchema) else "unverified"
                results.append(unavailable(reason, str(error), version))
            except Exception as error:  # noqa: BLE001 -- an answer or a face that does not read verifies nothing
                results.append(unavailable("unverified", f"quiddity's answer could not be checked against the "
                                                         f"part: {type(error).__name__}: {error}", version))
    return results


def _shape(given: Any) -> Any:
    if not hasattr(given, "wrapped"):
        raise TypeError(f"a part is a build123d shape, not {type(given).__name__}")
    return given


# --- the gate and the mapping ------------------------------------------------------------------------------


def _mapped(document: Any, anchors: Any, version: str, faces: Sequence[Any],
            surface_of: Callable[[Any], Any]) -> dict[str, Any]:
    """quiddity's ``document`` as the result of the part whose faces are ``faces`` (in their ordinals' order;
    ``surface_of`` the kernel's reading of one), every check of the gate passed; ``_Unverified`` where one fails."""
    if not isinstance(document, dict) or document.get("schema_version") != SCHEMA:
        said = document.get("schema_version") if isinstance(document, dict) else type(document).__name__
        raise _UnknownSchema(f"quiddity {version} answered {said!r}, and this reads {SCHEMA!r}")
    if document.get("coordinate_space", "file") != "file":
        raise _UnknownSchema(f"quiddity {version} answered in {document.get('coordinate_space')!r} coordinates, and "
                             "this reads the file's")
    count = len(faces)
    if document.get("face_count") != count:
        raise _Unverified(f"quiddity read {document.get('face_count')} faces where the kernel holds {count}")
    accounting = _accounting(document.get("face_accounting"), count)
    unanchored = _anchored(anchors, faces)
    read: dict[int, Any] = {}

    def surface(ordinal: int) -> Any:
        if ordinal not in read:
            read[ordinal] = surface_of(faces[ordinal - 1])
        return read[ordinal]

    records = []
    holes = []
    for record in _list(document.get("records"), "records"):
        if not isinstance(record, dict) or not isinstance(record.get("parameters"), dict):
            raise _Unverified("a record of quiddity's that is no record")
        name = _text(record.get("id"), "a record's id")
        family = _text(record.get("family"), f"{name}'s family")
        status = record.get("evidence_status")
        if status not in ("verified", "unproved"):
            raise _Unverified(f"{name}: evidence_status {status!r} is neither verified nor unproved")
        own = _ordinals(record.get("faces"), count, name)
        parameters = record["parameters"]
        if family == "holes":
            holes.append(_hole(name, status, own, parameters, count, surface))
        elif family == "countersinks":
            _about(name, own, _axis(parameters.get("axis"), name), _point(parameters.get("location"), name), surface,
                   kinds=("cone",))
        elif family == "step_levels":
            for ordinal in own:
                if surface(ordinal).kind != "plane":
                    raise _Unverified(f"{name}: face {ordinal} is a step level to quiddity and a "
                                      f"{surface(ordinal).kind} to the kernel")
        records.append({"id": name, "family": family, "record_type": _text(record.get("record_type"), f"{name}'s type"),
                        "faces": list(own), "evidence_status": status, "parameters": parameters})
    bodies = document.get("bodies")
    if bodies is not None:
        if not isinstance(bodies, dict):
            raise _Unverified("quiddity's bodies are no object")
        bodies = {"solids": bodies.get("solids"), "void_shells": bodies.get("void_shells"),
                  "solid_faces": [_ordinals(solid, count, "a solid of bodies")
                                  for solid in _list(bodies.get("solid_faces") or [], "bodies' solid_faces")]}
    return {"available": True, "version": VERSION, "quiddity": version, "schema": SCHEMA, "face_count": count,
            "run_mode": document.get("run_mode"), "input_repairs": list(document.get("input_repairs") or ()),
            "bodies": bodies, "frame": document.get("frame"), "unanchored_faces": unanchored, "records": records,
            "holes": holes, "accounting": accounting}


def _accounting(given: Any, count: int) -> list[dict[str, Any]]:
    """quiddity's place for each face, by ordinal: its own entry (``group``, and ``record_ids``, ``reason`` or
    ``refusals`` as that group has them), with the face's ordinal."""
    entries = _list(given, "face_accounting")
    if len(entries) != count:
        raise _Unverified(f"quiddity accounts for {len(entries)} faces where the kernel holds {count}")
    found = []
    for ordinal, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict) or entry.get("group") not in GROUPS:
            group = entry.get("group") if isinstance(entry, dict) else entry
            raise _Unverified(f"face {ordinal} is accounted {group!r}, which is none of {', '.join(GROUPS)}")
        found.append({"face": ordinal, **entry})
    return found


def _anchored(anchors: Any, faces: Sequence[Any]) -> list[int]:
    """Each point quiddity proves on a face lies on the kernel's face of that ordinal (the module's **The tie**,
    3). The ordinals of the faces it proves no point on, which are not checked this way."""
    entries = _list(anchors, "anchors")
    if len(entries) != len(faces):
        raise _Unverified(f"quiddity anchors {len(entries)} faces where the kernel holds {len(faces)}")
    without = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict) or entry.get("face") != index:
            raise _Unverified(f"quiddity's anchor {index} is not its face {index}'s")
        if entry.get("point") is None:
            without.append(index + 1)
            continue
        away = float(faces[index].distance_to(_point(entry["point"], f"face {index + 1}'s anchor")))
        if not away <= ANCHOR_MM:
            raise _Unverified(f"the point quiddity proves on its face {index} lies {away:.3g} mm off the kernel's "
                              f"face {index + 1}: its faces are not the part's in this order")
    return without


def _hole(name: str, status: str, own: list[int], parameters: dict[str, Any], count: int,
          surface: Callable[[int], Any]) -> dict[str, Any]:
    """One hole in the words a check reads first (``cad.quiddity``'s docstring lists the keys), its faces checked
    against the kernel (the module's **The tie**, 4)."""
    axis = _axis(parameters.get("axis"), name)
    point = _point(parameters.get("location"), name)
    diameter = _length(parameters.get("diameter"), f"{name}'s diameter")
    steps = [_step(parameters.get(key), count, f"{name}'s {key}") for key in ("cbore", "spotface")]
    outer = [_step(step, count, f"{name}'s outer step") for step in parameters.get("outer_steps") or ()]
    radii = [diameter / 2.0, *(step["diameter_mm"] / 2.0 for step in (*steps, *outer) if step is not None)]
    _about(name, own, axis, point, surface, radii=radii)
    if not any(surface(ordinal).kind == "cylinder" and abs(surface(ordinal).radius - diameter / 2.0) <= GATE_MM
               for ordinal in own):
        raise _Unverified(f"{name}: none of its faces is a cylinder of its diameter, {diameter:g} mm, to the kernel")
    for step in (*steps, *outer):
        if step is not None:
            _about(name, step["faces"], axis, point, surface, radii=[step["diameter_mm"] / 2.0], kinds=("cylinder",))
    sunk = parameters.get("csink")
    countersink = None
    if sunk is not None:
        if not isinstance(sunk, dict):
            raise _Unverified(f"{name}'s csink is no object")
        countersink = {"diameter_mm": _length(sunk.get("major_diameter"), f"{name}'s countersink diameter"),
                       "angle_deg": _length(sunk.get("included_angle"), f"{name}'s countersink angle"),
                       "depth_mm": _length(sunk.get("depth"), f"{name}'s countersink depth"),
                       "faces": _ordinals(sunk.get("faces") or [], count, f"{name}'s csink")}
        _about(name, countersink["faces"], axis, point, surface, kinds=("cone",))
    breaks = []
    for given in parameters.get("mouth_chamfers") or ():
        if not isinstance(given, dict):
            raise _Unverified(f"{name}'s mouth chamfer is no object")
        what = f"{name}'s mouth chamfer"
        breaks.append({"diameter_mm": _length(given.get("diameter"), f"{what}'s diameter"),
                       "size_mm": _length(given.get("size"), f"{what}'s size"),
                       "depth_mm": _length(given.get("depth"), f"{what}'s depth"),
                       "angle_deg": _length(given.get("angle"), f"{what}'s angle"),
                       "faces": _ordinals(given.get("faces") or [], count, what)})
        _about(name, breaks[-1]["faces"], axis, point, surface, kinds=("cone",))
    bottom = _text(parameters.get("bottom"), f"{name}'s bottom")
    return {"id": name, "evidence_status": status, "diameter_mm": diameter,
            "depth_mm": _length(parameters.get("depth"), f"{name}'s depth"), "through": bottom == "through",
            "bottom": bottom, "point_mm": list(point), "axis": list(axis), "counterbore": steps[0],
            "spotface": steps[1], "outer_counterbores": [step for step in outer if step is not None],
            "countersink": countersink, "mouth_chamfers": breaks, "faces": own}


def _step(given: Any, count: int, what: str) -> dict[str, Any] | None:
    """A counterbore-class step (``cbore``, ``spotface``, an outer step): its diameter, its own depth and the
    cylinders quiddity located for it."""
    if given is None:
        return None
    if not isinstance(given, dict):
        raise _Unverified(f"{what} is no object")
    return {"diameter_mm": _length(given.get("diameter"), f"{what}'s diameter"),
            "depth_mm": _length(given.get("depth"), f"{what}'s depth"),
            "faces": _ordinals(given.get("faces") or [], count, what)}


def _about(name: str, ordinals: Iterable[int], axis: Vector, point: Vector, surface: Callable[[int], Any],
           radii: Sequence[float] = (), kinds: Sequence[str] = ()) -> None:
    """Each of ``ordinals`` is, to the kernel, a surface a feature about ``axis`` through ``point`` can have
    there: of ``kinds`` where any are named; a cylinder concave, about the axis and of one of ``radii`` (where any
    are given); a cone or a torus about the axis; a sphere centred on it; a plane square to it. A free-form face
    says nothing either way."""
    for ordinal in ordinals:
        found = surface(ordinal)
        kind = found.kind
        if kinds and kind not in kinds:
            raise _Unverified(f"{name}: face {ordinal} is a {kind} to the kernel, not a {' or a '.join(kinds)}")
        if kind == "plane":
            if _sine(found.normal, axis) > PARALLEL:
                raise _Unverified(f"{name}: face {ordinal} is a plane the kernel finds not square to its axis")
            continue
        if kind not in ("cylinder", "cone", "sphere", "torus"):
            continue
        if kind != "sphere" and _sine(found.axis, axis) > PARALLEL:
            raise _Unverified(f"{name}: face {ordinal} is a {kind} about another direction to the kernel")
        off = _norm(_cross(_minus(point, found.origin), axis))
        if off > GATE_MM:
            raise _Unverified(f"{name}: face {ordinal} is a {kind} {off:.3g} mm off its axis to the kernel")
        if kind == "cylinder":
            if found.concave is False:
                raise _Unverified(f"{name}: face {ordinal} is a cylinder with its material inside to the kernel")
            if radii and not any(abs(found.radius - radius) <= GATE_MM for radius in radii):
                raise _Unverified(f"{name}: face {ordinal} is a cylinder of diameter {2 * found.radius:g} mm to "
                                  "the kernel, none of its own")


# --- quiddity's values, read strictly ----------------------------------------------------------------------


def _list(given: Any, what: str) -> list[Any]:
    if not isinstance(given, list):
        raise _Unverified(f"quiddity's {what} is no list")
    return given


def _text(given: Any, what: str) -> str:
    if not isinstance(given, str) or not given:
        raise _Unverified(f"{what} is no text")
    return given


def _length(given: Any, what: str) -> float:
    if isinstance(given, bool) or not isinstance(given, (int, float)) or not math.isfinite(given):
        raise _Unverified(f"{what} is no number")
    return float(given)


def _ordinals(given: Any, count: int, what: str) -> list[int]:
    """quiddity's face indices (from 0) as the part's ordinals (from 1), each one of the part's faces."""
    found = []
    for index in _list(given, f"{what}'s faces"):
        if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < count:
            raise _Unverified(f"{what} names quiddity's face {index!r}, and it read faces 0 to {count - 1}")
        found.append(index + 1)
    return found


def _point(given: Any, what: str) -> Vector:
    if not isinstance(given, (list, tuple)) or len(given) != 3:
        raise _Unverified(f"{what} has no point")
    return (_length(given[0], what), _length(given[1], what), _length(given[2], what))


def _axis(given: Any, what: str) -> Vector:
    """An axis as a unit vector: quiddity writes one as a vector or as a file axis's letter."""
    if isinstance(given, str) and given in _LETTERS:
        return _LETTERS[given]
    vector = _point(given, f"{what}'s axis")
    size = _norm(vector)
    if not abs(size - 1.0) <= 1e-6:
        raise _Unverified(f"{what}'s axis is no unit vector")
    return (vector[0] / size, vector[1] / size, vector[2] / size)


def _minus(a: Sequence[float], b: Sequence[float]) -> Vector:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _cross(a: Sequence[float], b: Sequence[float]) -> Vector:
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _norm(a: Sequence[float]) -> float:
    return math.sqrt(a[0] * a[0] + a[1] * a[1] + a[2] * a[2])


def _sine(a: Sequence[float], b: Sequence[float]) -> float:
    """The sine of the angle between two unit directions, whichever way each points."""
    return _norm(_cross(a, b))
