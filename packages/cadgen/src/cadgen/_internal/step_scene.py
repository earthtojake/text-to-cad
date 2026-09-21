"""The STEP-scene names other modules reach for, gathered in one place.

The scene implementation is split by concern across ``step_scene_loader``,
``step_scene_geometry``, ``step_scene_mesh``, ``step_scene_package`` and
``step_scene_types``. This module is the read side of that split and nothing
else: it defines no behaviour, and every name below is a re-export that some
other module or test imports FROM HERE. Import a name from its own module
instead when you are working inside the scene code.
"""

from __future__ import annotations

from cadgen.selector_types import SelectorBundle
from cadgen._internal.step_hash import step_file_hash
from cadgen._internal.step_scene_geometry import _bbox_from_shape
from cadgen._internal.step_scene_loader import (
    _located_shape,
    _shape_hash,
    load_step_scene,
    load_step_scene_from_xcaf_doc,
)
from cadgen._internal.step_scene_mesh import (
    adaptive_mesh_resolution_for_scene,
    import_step,
    occurrence_selector_id,
    scene_leaf_occurrences,
    scene_occurrence_shape,
)
from cadgen._internal.step_scene_package import load_step_scene_cached
from cadgen._internal.step_scene_types import (
    LoadedStepScene,
    OccurrenceNode,
    SelectorOptions,
    _enum_name,
)

__all__ = [
    "LoadedStepScene",
    "OccurrenceNode",
    "SelectorBundle",
    "SelectorOptions",
    "_bbox_from_shape",
    "_enum_name",
    "_located_shape",
    "_shape_hash",
    "adaptive_mesh_resolution_for_scene",
    "import_step",
    "load_step_scene",
    "load_step_scene_cached",
    "load_step_scene_from_xcaf_doc",
    "occurrence_selector_id",
    "scene_leaf_occurrences",
    "scene_occurrence_shape",
    "step_file_hash",
]
