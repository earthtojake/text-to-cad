from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
from functools import lru_cache
from pathlib import Path
from typing import Any

from cadgen._internal.glb_topology import STEP_EDGE_DEFAULT_RENDER_VISIBILITY_CLASSES

ColorRGBA = tuple[float, float, float, float]


@dataclass(frozen=True)
class SelectorOptions:
    """How a build extracts a package's topology.

    Carries no mesh tolerance. A render package is tessellation-free — it
    stores surfaces (``.surf``) and the client meshes them — so the only
    option here with a consequence is which edge classes get built.
    ``--mesh-tolerance`` belongs to the mesh EXPORT path (``MeshExportJob``),
    which never reads this.
    """

    edge_deflection: float | None = None
    edge_deflection_ratio: float = 0.00075
    max_edge_points: int = 96
    digits: int | None = 6
    edge_visibility_classes: tuple[str, ...] = STEP_EDGE_DEFAULT_RENDER_VISIBILITY_CLASSES


@dataclass
class LoadedStepScene:
    step_path: Path
    roots: list["OccurrenceNode"]
    prototype_shapes: dict[int, Any]
    prototype_names: dict[int, str | None] = field(default_factory=dict)
    prototype_colors: dict[int, ColorRGBA] = field(default_factory=dict)
    prototype_face_colors: dict[int, dict[int, ColorRGBA]] = field(default_factory=dict)
    load_elapsed: float = 0.0
    step_hash: str | None = None
    source_kind: str = "step"
    source_path: str | None = None
    # Typed-mates kinematics block from kinematics= (JSON-ready dict; axis
    # refs resolved to numbers during the package build, then written into the
    # model's sidecar), the resolved {dof: value} bake pose the artifact is
    # written at, and the .anim.js choreography TEXT (copied at build; no path
    # survives into generated files).
    kinematics: dict[str, Any] | None = None
    bake_pose: dict[str, float] | None = None
    animation_source: str | None = None
    source_hash: str | None = None
    source_closure_hash: str | None = None
    source_closure_files: tuple[str, ...] = ()
    # Literals imported from model files, tracked by value (record.constants).
    source_closure_constants: dict[str, dict[str, str]] = field(default_factory=dict)
    # `cadgen step build IN OUT` only: the INPUT document's content hash (the
    # closure a re-emitted document is fresh against) and a digest of the
    # annotation it was given (kinematics declaration + bake point + animation
    # text). Set on a scene loaded from IN and re-pathed to OUT; their presence
    # is what tells the sidecar writer this is a re-emit rather than an import.
    reemit_source_hash: str | None = None
    reemit_annotation_hash: str | None = None
    # compound_from_instances carries its assembly hierarchy as an explicit
    # occurrence-metadata tree (cadgen.instances). The XCAF doc built for an
    # in-memory scene flattens such a compound to ONE leaf (it has no
    # build123d children), so scene consumers that need placed leaf
    # occurrences (interference) walk this tree instead when present.
    instance_occurrence_tree: dict[str, Any] | None = None
    doc: Any | None = None


@dataclass(frozen=True)
class AdaptiveMeshResolution:
    """What the scene's topology says about how to RENDER it.

    Not tessellation settings: there is one tessellator, it is JS, and it takes
    its own relative tolerances. What survives here is the classification —
    ``profile`` plus the ``hints`` it was computed from — because
    ``_edge_visibility_classes_for_resolution`` turns the pair into the edge
    classes a package actually renders. The absolute deflection numbers this
    once carried reached no mesher and are gone.
    """

    profile: str
    hints: dict[str, Any]


@dataclass
class OccurrenceNode:
    path: tuple[int, ...]
    name: str | None
    source_name: str | None
    transform: tuple[float, ...]
    prototype_key: int | None
    local_transform: tuple[float, ...] = field(default_factory=lambda: _identity_transform_matrix())
    color: ColorRGBA | None = None
    location: object | None = None
    children: list["OccurrenceNode"] = field(default_factory=list)
    row_index: int = -1


@lru_cache(maxsize=512)
def _enum_name_from_text(text: str, prefix: str) -> str:
    name = text.split(".")[-1]
    if name.startswith(prefix):
        return name[len(prefix) :].lower()
    return name.lower()


@lru_cache(maxsize=512)
def _enum_name_cached(enum_type: type, value: Any, prefix: str) -> str:
    return _enum_name_from_text(str(value), prefix)


def _enum_name(value: Any, prefix: str) -> str:
    # The OCCT enum domain (GeomAbs_*) is tiny and fixed, but this is called per face/edge
    # during topology extraction (~74k times for tom). Memoizing avoids re-running the slow
    # ``str(value)`` enum repr on every call; the cached ``_enum_name_from_text`` only helped
    # once the string already existed.
    #
    # The memo key MUST include the enum's type. OCP's pybind11 enums compare and hash by
    # their underlying int, and the GeomAbs_* families overlap numerically:
    # GeomAbs_Line/GeomAbs_Plane/GeomAbs_C0 are all 0, and
    # GeomAbs_Circle/GeomAbs_Cylinder/GeomAbs_G1 are all 1. Keyed on the value alone,
    # whichever family reached a given int first answered for every other family for the
    # rest of the process — faces are extracted before edges, so every curve came back
    # named after a surface ("circle" -> "cylinder", "line" -> "plane"). That corrupted
    # the exported ``curveType``, the continuity names, and the ``!= "line"`` /
    # ``!= "plane"`` guards that count curved edges and faces.
    return _enum_name_cached(type(value), value, prefix)


def _identity_transform_matrix() -> tuple[float, ...]:
    return (
        1.0,
        0.0,
        0.0,
        0.0,
        0.0,
        1.0,
        0.0,
        0.0,
        0.0,
        0.0,
        1.0,
        0.0,
        0.0,
        0.0,
        0.0,
        1.0,
    )


