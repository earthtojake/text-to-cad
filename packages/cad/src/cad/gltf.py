"""What glTF says that the document does not: a GLB's own animations.

``animation(assembly, name, duration=)`` names a GLB's choreography (the engine's
**Animations**): baked into each GLB the model declares, and kept in its xbf as a build record that
only a GLB of the document reads::

    from cad.gltf import animation

glTF is the format that defines animations; GLB is the container ``@glb`` writes.

Every name loads on first use: ``import cad.gltf`` imports no CAD kernel.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

__all__ = ["animation"]


def __getattr__(name: str) -> Any:
    if name == "animation":
        from cad.engine import model

        return model.animation
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    """Its public names (``__all__``) and the submodules imported so far: what ``dir()`` and
    completion offer, without loading any of them, nor the kernel."""
    return sorted({*__all__, *(name for name, value in globals().items() if name.startswith("__")
                               or getattr(value, "__name__", "").startswith(__name__ + "."))})


if TYPE_CHECKING:
    from cad.engine.model import animation
