"""Implicit solids: a part made of a field, negative inside (the engine's **Implicit solids**).

``solid(field, bounds, cell)`` samples ``field`` every ``cell`` millimetres over ``bounds`` and
hands back the solid inside its zero surface, a B-rep of planar triangles, which a model's body
returns, places, colours or composes with other parts like any shape::

    import numpy as np
    from cadgen import xbf
    from cadgen.implicit import solid

    @xbf("XBF/bead.xbf")
    def bead():
        return solid(lambda p: np.linalg.norm(p, axis=1) - 10, bounds=((-12,) * 3, (12,) * 3), cell=0.5)

A field is any function of an ``(N, 3)`` array of points answering ``N`` values: written in numpy,
or in whatever library the model's environment holds. cadgen depends on none.

Every name loads on first use: ``import cadgen.implicit`` imports no CAD kernel.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

__all__ = ["solid"]


def __getattr__(name: str) -> Any:
    if name == "solid":
        from cadgen.engine import implicit

        return implicit.solid
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    """Its public names (``__all__``) and the submodules imported so far: what ``dir()`` and
    completion offer, without loading any of them, nor the kernel."""
    return sorted({*__all__, *(name for name, value in globals().items() if name.startswith("__")
                               or getattr(value, "__name__", "").startswith(__name__ + "."))})


if TYPE_CHECKING:
    from cadgen.engine.implicit import solid
