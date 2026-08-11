"""Public STEP scene helpers for generator scripts.

The scene engine lives in :mod:`cadgen._internal.step_scene`; this module
re-exports the supported surface used by build123d generator sources that
import or compose existing STEP files. Anything not exported here is private
and may change between releases.
"""

from cadgen._internal.step_scene import (
    _located_shape as located_shape,
    import_step,
    load_step_scene,
    occurrence_selector_id,
    scene_occurrence_shape,
)

__all__ = [
    "import_step",
    "load_step_scene",
    "located_shape",
    "occurrence_selector_id",
    "scene_occurrence_shape",
]
