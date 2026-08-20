from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
from functools import lru_cache
from pathlib import Path
from typing import Any

from cadgen._internal.glb_topology import STEP_EDGE_DEFAULT_RENDER_VISIBILITY_CLASSES
from cadgen.metadata import DEFAULT_MESH_ANGULAR_TOLERANCE
from cadgen.metadata import DEFAULT_MESH_TOLERANCE
from cadgen.metadata import MeshSettings


ColorRGBA = tuple[float, float, float, float]
# v2: per-prototype geometry is cached as binary BREP (BinTools) instead of the
# slower/larger ASCII BRepTools format.
STEP_SCENE_CACHE_SCHEMA_VERSION = 2
# Pinned BinTools format version. Cached geometry is rebuildable, so a future
# OCCT upgrade that cannot read this version simply misses the cache.
_STEP_SCENE_CACHE_BINTOOLS_VERSION = 3


@dataclass(frozen=True)
class SelectorOptions:
    linear_deflection: float = DEFAULT_MESH_TOLERANCE
    angular_deflection: float = DEFAULT_MESH_ANGULAR_TOLERANCE
    relative: bool = True
    edge_deflection: float | None = None
    edge_deflection_ratio: float = 0.00075
    max_edge_points: int = 96
    digits: int | None = 6
    mesh_resolution: dict[str, Any] | None = None
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
    params_path: str | None = None
    source_hash: str | None = None
    source_closure_hash: str | None = None
    source_closure_files: tuple[str, ...] = ()
    mesh_signature: tuple[float, float, bool] | None = None
    glb_mesh_payloads: dict[tuple[object, ...], Any] = field(default_factory=dict)
    assembly_mates: list[dict[str, Any]] = field(default_factory=list)
    export_shape: Any | None = None
    doc: Any | None = None


@dataclass(frozen=True)
class AdaptiveMeshResolution:
    settings: MeshSettings
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


