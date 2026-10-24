"""What glTF says that the document does not: a GLB's own animations.

``animation(assembly, name, duration=)`` names a GLB's choreography (the engine's
**Animations**): baked into each GLB the model declares, and kept in its xbf as a build record that
only a GLB of the document reads::

    from cadgen.gltf import animation

glTF is the format that defines animations; GLB is the container ``@glb`` writes.

Every name loads on first use: ``import cadgen.gltf`` imports no CAD kernel.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

__all__ = ["animation"]


def __getattr__(name: str) -> Any:
    if name == "animation":
        from cadgen.engine import model

        return model.animation
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


if TYPE_CHECKING:
    from cadgen.engine.model import animation
