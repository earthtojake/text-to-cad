"""The check kinds every analysis shares: how each is written in ``view.checks``, parsed and checked.

One :class:`~cadgen._internal.fea.analyses.base.CheckSpec` per kind (spec
section 6). Parsing only: the analysis that offers a kind judges it. The study
primitives (a number, a list of faces, a short label) live here too, so the
study, the analyses and the kinds all say an error the same way. Plus
:func:`field_max_over`, the largest value of a nodal field over some faces (or
the whole model), which a displacement, temperature, acceleration or contact
check reads. Stdlib only at import.
"""

from __future__ import annotations

import json
import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from cadgen._internal.fea.analyses.base import CheckSpec

if TYPE_CHECKING:
    import numpy as np

__all__ = [
    "ACCELERATION", "BUCKLING", "CHECK_SPECS", "CONTACT_PRESSURE", "DISPLACEMENT", "FATIGUE", "FREQUENCY", "FieldMax",
    "PLASTIC_STRAIN", "PRESSURE_DROP", "STRESS", "TEMPERATURE", "VELOCITY", "faces", "field_max_over", "json_text",
    "number", "parse_check", "text",
]


def json_text(value: Any) -> str:
    """A value as the JSON an agent wrote it: true, null, "text", not Python's True, None, 'text'."""
    try:
        return json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        return repr(value)


def number(value: Any, *, where: str, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{where}: expected a number, got {json_text(value)}")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{where}: expected a finite number, got {result}")
    if positive and not result > 0:
        raise ValueError(f"{where}: must be > 0, got {result}")
    return result


def faces(entry: dict, *, where: str) -> tuple[str, ...]:
    refs = entry.get("faces")
    if isinstance(refs, str):
        refs = [refs]
    if not isinstance(refs, list) or not refs or not all(isinstance(f, str) and f.strip() for f in refs):
        raise ValueError(f"{where}: 'faces' must be a non-empty list of face references like \"#o1.f17\"")
    return tuple(f.strip() for f in refs)


def text(entry: dict, key: str, *, where: str) -> dict:
    if key not in entry:
        return {}
    if not isinstance(entry[key], str) or not entry[key].strip():
        raise ValueError(f"{where}.{key}: expected a short piece of text")
    return {key: entry[key].strip()}


def _known(entry: dict, keys: frozenset[str], kind: str, where: str) -> None:
    unknown = set(entry) - keys
    if unknown:
        raise ValueError(f"{where}: unknown keys {sorted(unknown)}; a {kind} check takes {sorted(keys)}")


def _margin(entry: dict, where: str, *, low: float = 1.0, words: str) -> float:
    margin = number(entry["margin"], where=f"{where}.margin", positive=True)
    if margin < low:
        raise ValueError(f"{where}.margin: {words}; must be {low:g} or more, got {margin:g}")
    return margin


def _limit(entry: dict, key: str, where: str, words: str) -> float:
    if key not in entry:
        raise ValueError(f"{where}.{key}: {words}")
    return number(entry[key], where=f"{where}.{key}", positive=True)


def _with_faces(entry: dict, check: dict, where: str) -> dict:
    if "faces" in entry:
        check["faces"] = list(faces(entry, where=where))
    return check


def _spec(kind: str, keys: tuple[str, ...], label: str, scaling: str, body: Callable[[dict, str], dict],
          *, unique: bool = False) -> CheckSpec:
    accepted = frozenset({"kind", "label", *keys})

    def parse(entry: dict, where: str) -> dict:
        _known(entry, accepted, kind, where)
        return {"kind": kind, **body(entry, where), **text(entry, "label", where=where)}

    return CheckSpec(kind, accepted, parse, label, scaling, unique)  # type: ignore[arg-type]


def _stress(entry: dict, where: str) -> dict:
    if "margin" in entry:
        return {"margin": _margin(entry, where, words="a safety factor below 1 means the part yields")}
    return {}


def _displacement(entry: dict, where: str) -> dict:
    check = {"limit_mm": _limit(entry, "limit_mm", where, "a displacement check needs the most it may move, in mm")}
    return _with_faces(entry, check, where)


def _frequency(entry: dict, where: str) -> dict:
    given = [key for key in ("min_Hz", "avoid_Hz") if key in entry]
    if len(given) != 1:
        raise ValueError(f"{where}: a frequency check takes min_Hz (the lowest the mode may be) or avoid_Hz "
                         "([low, high], a band to keep clear of), exactly one")
    if given == ["min_Hz"]:
        check: dict = {"min_Hz": number(entry["min_Hz"], where=f"{where}.min_Hz", positive=True)}
        if "mode" in entry:
            mode = entry["mode"]
            if isinstance(mode, bool) or not isinstance(mode, int) or mode < 1:
                raise ValueError(f"{where}.mode: the mode number, 1 for the first, got {json_text(mode)}")
            check["mode"] = mode
        return check
    if "mode" in entry:
        raise ValueError(f"{where}.mode: a band check looks at every mode; mode goes with min_Hz only")
    band = entry["avoid_Hz"]
    if not isinstance(band, list) or len(band) != 2:
        raise ValueError(f"{where}.avoid_Hz: the band as [low, high] in Hz, like [110, 130]")
    low, high = (number(value, where=f"{where}.avoid_Hz", positive=True) for value in band)
    if not low < high:
        raise ValueError(f"{where}.avoid_Hz: low ({low:g}) must be below high ({high:g})")
    return {"avoid_Hz": [low, high]}


def _buckling(entry: dict, where: str) -> dict:
    if "margin" in entry:
        return {"margin": _margin(entry, where, words="a buckling margin below 1 means it buckles at this load")}
    return {"margin": 3.0}


def _temperature(entry: dict, where: str) -> dict:
    if "max_C" not in entry:
        raise ValueError(f"{where}.max_C: a temperature check needs the hottest it may get, in °C")
    return _with_faces(entry, {"max_C": number(entry["max_C"], where=f"{where}.max_C")}, where)


def _acceleration(entry: dict, where: str) -> dict:
    check = {"limit_g": _limit(entry, "limit_g", where, "an acceleration check needs the most it may take, in g")}
    return _with_faces(entry, check, where)


def _fatigue(entry: dict, where: str) -> dict:
    check: dict = {}
    if "cycles" in entry:
        check["cycles"] = number(entry["cycles"], where=f"{where}.cycles", positive=True)
    check["margin"] = (
        _margin(entry, where, words="a fatigue margin below 1 means it wears out before the cycles it needs")
        if "margin" in entry else 1.5
    )
    return check


def _pressure_drop(entry: dict, where: str) -> dict:
    return {"limit_Pa": _limit(entry, "limit_Pa", where, "a pressure_drop check needs the most it may lose, in Pa")}


def _velocity(entry: dict, where: str) -> dict:
    return {"limit_m_s": _limit(entry, "limit_m_s", where, "a velocity check needs the fastest it may flow, in m/s")}


def _plastic_strain(entry: dict, where: str) -> dict:
    return {"limit_percent": _limit(entry, "limit_percent", where,
                                    "a plastic_strain check needs the most permanent strain allowed, in percent")}


def _contact_pressure(entry: dict, where: str) -> dict:
    check = {"limit_MPa": _limit(entry, "limit_MPa", where, "a contact_pressure check needs the most it may press, in MPa")}
    return _with_faces(entry, check, where)


STRESS = _spec("stress", ("margin",), "Strength", "linear", _stress, unique=True)
DISPLACEMENT = _spec("displacement", ("limit_mm", "faces"), "Displacement", "linear", _displacement)
FREQUENCY = _spec("frequency", ("min_Hz", "avoid_Hz", "mode"), "Vibration", "none", _frequency)
BUCKLING = _spec("buckling", ("margin",), "Buckling", "inverse", _buckling, unique=True)
TEMPERATURE = _spec("temperature", ("max_C", "faces"), "Heat", "none", _temperature)
ACCELERATION = _spec("acceleration", ("limit_g", "faces"), "Shaking", "linear", _acceleration)
FATIGUE = _spec("fatigue", ("cycles", "margin"), "Fatigue life", "none", _fatigue)
PRESSURE_DROP = _spec("pressure_drop", ("limit_Pa",), "Flow resistance", "none", _pressure_drop)
VELOCITY = _spec("velocity", ("limit_m_s",), "Flow speed", "none", _velocity)
PLASTIC_STRAIN = _spec("plastic_strain", ("limit_percent",), "Permanent bend", "none", _plastic_strain)
CONTACT_PRESSURE = _spec("contact_pressure", ("limit_MPa", "faces"), "Contact", "none", _contact_pressure)

#: Every kind, by name, in the order of spec section 6.
CHECK_SPECS: dict[str, CheckSpec] = {spec.kind: spec for spec in (
    STRESS, DISPLACEMENT, FREQUENCY, BUCKLING, TEMPERATURE, ACCELERATION, FATIGUE, PRESSURE_DROP, VELOCITY,
    PLASTIC_STRAIN, CONTACT_PRESSURE,
)}


def parse_check(entry: Any, specs: tuple[CheckSpec, ...], *, where: str) -> dict:
    """One ``view.checks`` entry against the kinds an analysis offers (``specs``)."""
    if not isinstance(entry, dict):
        raise ValueError(f"{where}: expected an object like {{\"kind\": \"displacement\", \"limit_mm\": 0.5}}")
    kinds = {spec.kind: spec for spec in specs}
    kind = entry.get("kind")
    if kind not in kinds:
        raise ValueError(f"{where}.kind: {json_text(kind)} is not a check this cadgen makes; use one of {list(kinds)}")
    return kinds[kind].parse(entry, where)


@dataclass(frozen=True)
class FieldMax:
    """Where a nodal field is largest over some faces: the node, its value and place, and the face it is on."""

    node: int
    value: float
    at: tuple[float, float, float]
    #: The face the node is on (one of the asked faces), or ``None`` when it is on none of them.
    ref: str | None
    #: The asked faces, as the scene names them (bare ``#o1.fN``).
    faces: tuple[str, ...]


def field_max_over(
    values: "np.ndarray",
    refs: tuple[str, ...],
    *,
    boundary: "np.ndarray",
    boundary_ordinal: "np.ndarray",
    locations: "np.ndarray",
    face_ref: dict,
    ordinal_of: dict[str, int],
    where: str,
) -> FieldMax:
    """The largest of nodal ``values`` over the nodes of the surface triangles of faces ``refs``, else over every node.

    ``boundary`` is the boundary triangles in node ids, ``boundary_ordinal`` the
    face of each, ``face_ref`` the scene's ref of each face ordinal. A face
    wholly covered by a bonded joint has no surface: that is a ValueError at
    ``where``, in words the person can act on.
    """
    import numpy as np

    ordinals = sorted({ordinal_of[ref] for ref in refs})
    rows = np.isin(boundary_ordinal, ordinals) if refs else np.ones(len(boundary_ordinal), bool)
    nodes = np.unique(boundary[rows]) if refs else np.arange(len(values))
    if len(nodes) == 0:
        raise ValueError(
            f"{where}: {', '.join(refs)} {'is' if len(refs) == 1 else 'are'} wholly covered by a bonded joint, "
            "so there is no surface of it to judge; choose a face, or part of one, that is not covered by another part"
        )
    node = int(nodes[values[nodes].argmax()])
    on = rows & (boundary == node).any(axis=1)
    ordinal = int(boundary_ordinal[on][0]) if on.any() else 0
    return FieldMax(
        node=node,
        value=float(values[node]),
        at=tuple(float(c) for c in locations[node]),
        ref=face_ref[ordinal].ref if ordinal in face_ref else None,
        faces=tuple(face_ref[o].ref for o in ordinals),
    )
