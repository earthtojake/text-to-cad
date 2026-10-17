from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

from cadgen._internal.glb_topology import STEP_EDGE_DEFAULT_RENDER_VISIBILITY_CLASSES
from cadgen._internal.step_names import ComponentNames

ColorRGBA = tuple[float, float, float, float]


@dataclass(frozen=True)
class SelectorOptions:
    """How a build extracts a tree's topology.

    Carries no mesh tolerance. A tree is tessellation-free -- each part is
    meshed once, at the one display tolerance, into its part record -- so the
    only option here with a consequence is which edge classes get built. A mesh
    tolerance belongs to the mesh EXPORT path (``MeshExportJob``), which never
    reads this.
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
    prototype_shapes: Mapping[int, Any]
    prototype_names: dict[int, str | None] = field(default_factory=dict)
    prototype_colors: dict[int, ColorRGBA] = field(default_factory=dict)
    prototype_face_colors: dict[int, dict[int, ColorRGBA]] = field(default_factory=dict)
    # Prototype key -> (codec, BREP object hash) of the stored component it was
    # decoded from, where the scene knows it: the facts a scene's edge policy
    # reads are then remembered by that BREP (store.bounds.cached_component_topology).
    prototype_components: dict[int, tuple[str, str]] = field(default_factory=dict)
    # Prototype key -> what its stored component is named by, where the scene was
    # read from a tree whose component carries it: the construction key and the
    # lineage (``component_package.read_lineage``), either None. A tree built from
    # the scene names the prototype the same (``store.build``).
    prototype_identity: dict[int, tuple[str | None, dict[str, Any] | None]] = field(default_factory=dict)
    # Prototype key -> what the file names it by, where it names it: its product's part key
    # and its faces' and edges' names, by the prototype's own ordinals (``step_names``).
    prototype_step_names: dict[int, ComponentNames] = field(default_factory=dict)
    load_elapsed: float = 0.0
    step_hash: str | None = None
    source_kind: str = "step"
    source_path: str | None = None
    # Typed-mates kinematics block from kinematics= (JSON-ready dict; axis
    # refs resolved to numbers during the tree build, then written into the
    # model's sidecar).
    kinematics: dict[str, Any] | None = None
    materials: dict[str, Any] | None = None
    animation: dict[str, str] | None = None
    # The model run that made a generated scene's shapes (kernel_memo.run): the
    # tree build asks it what names each component it prepares, and the publish
    # writes its features beside the record (STORE.md §3).
    kernel_run: Any | None = None
    source_hash: str | None = None
    source_closure_hash: str | None = None
    source_closure_files: tuple[str, ...] = ()
    source_closure_file_hashes: dict[str, str] = field(default_factory=dict)
    # Sliced helper files -> the names the build reached in them (record.closure.names)
    # and their whole-file hashes (record.closure.wholes).
    source_closure_names: dict[str, tuple[str, ...]] = field(default_factory=dict)
    source_closure_wholes: dict[str, str] = field(default_factory=dict)
    # Listed folders -> the entries their digests leave out, the model's own
    # outputs (record.closure.own).
    source_closure_own: dict[str, tuple[str, ...]] = field(default_factory=dict)
    # Literals imported from model files, tracked by value (record.constants).
    source_closure_constants: dict[str, dict[str, str]] = field(default_factory=dict)
    # `cadgen step build IN OUT` only: the INPUT document's content hash (the
    # closure a re-emitted document is fresh against) and a digest of the
    # annotation it was given (the kinematics declaration). Set on a scene
    # loaded from IN and re-pathed to OUT; their presence
    # is what tells the sidecar writer this is a re-emit rather than an import.
    reemit_source_hash: str | None = None
    reemit_annotation_hash: str | None = None
    doc: Any | None = None


@dataclass(frozen=True)
class AdaptiveMeshResolution:
    """What the scene's topology says about how to RENDER it.

    Not tessellation settings: cadgen's tessellator (``tessellate``) takes its
    own relative tolerances. This is the classification — ``profile`` plus the
    ``hints`` it was computed from — which ``step_scene_mesh.edge_visibility_classes``
    turns into the edge classes a tree renders.
    """

    profile: str
    hints: dict[str, Any]


@dataclass
class OccurrenceNode:
    # ``path`` is the node's position in the parsed product hierarchy (the reader's own
    # bookkeeping, never a name); ``id`` is its token in the document tree
    # (``cadgen._internal.tree_tokens``) where the scene came from one, else None.
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
    id: str | None = None


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

