"""What cadgen meshes a STEP model's components at for display: the one tessellation policy.

Every display mesh is cadgen's (OCCT on the exact BREP, ``cadgen.store.meshes``),
and so is the choice of tolerances it is made at:

- **The display tolerance** (:data:`DISPLAY_TESSELLATION`): the one pair every
  display mesh is made at -- the CAD Viewer's, the CAD app's, a snapshot's, a
  robot primitive's -- and the pair a mesh export that names none is written at,
  so that export is served from the very mesh the viewer draws. Chord tolerance
  is RELATIVE to each component's bounding diagonal, angle tolerance is radians.
  It is this module's alone, configurable nowhere, and no page knows it: a page
  reads each part's one display mesh by the part's key (``cadgen.store.parts``),
  which names no tolerance.
- **The bounds** (:data:`TESSELLATION_FLOORS`, :data:`TESSELLATION_CEILINGS`):
  the finest and the coarsest a mesh export may ask to have meshed. One rule
  (:func:`tolerance_refusal`) holds them at every door a tolerance enters -- a
  mesh decorator's argument or a mesh door's flag (``cadgen.metadata``), the mesh
  export they reach (``cadgen._internal.mesh_export``) -- so a request outside
  them is refused where it enters, in words naming the bound, and never meshed.
"""

from __future__ import annotations

import math

__all__ = [
    "DISPLAY_TESSELLATION",
    "TESSELLATION_CEILINGS",
    "TESSELLATION_FLOORS",
    "tolerance_refusal",
]

# The one pair every display mesh is made at: a part 1,000 px across strays half a
# pixel from its exact surface, and a round edge turns at most 0.35 rad (20 degrees)
# between facets -- OCCT draws a full circle with 36 facets at it, 10 degrees each.
DISPLAY_TESSELLATION: dict[str, float] = {"chordTolerance": 5e-4, "angleTolerance": 0.35}

# The finest tolerances anything may ask to have meshed: past any display or print
# need (a sphere 2,000 px across strays a third of a pixel at either), and the
# finest at which one face still meshes in seconds. OCCT's mesher spends more per
# triangle the more triangles one face has, and a face curved all the way round
# both ways -- a torus, a sphere, a closed freeform loft -- has the most. Measured
# on such faces (OCCT 7.9, one core): at 0.05 rad a torus is 127k triangles in
# 3.5 s of CPU and a sphere 32k in 0.3 s; at a chord of 5e-5 a closed loft is 86k
# triangles in 3 s, a sphere 58k and a torus 62k in under 1 s. Finer, the cost
# runs away: a torus at 0.03 rad is 351k triangles in 45 s, a sphere at 0.01 rad
# had not finished after 4 minutes, and at 0.005 rad a model of four primitives
# meshed for over 47 minutes.
TESSELLATION_FLOORS: dict[str, float] = {"chordTolerance": 5e-5, "angleTolerance": 0.05}
# The coarsest: past a twentieth of the bounding diagonal, or a quarter turn
# between neighbouring facets (a circle as a square), a mesh no longer follows the
# part. A chord tolerance above it is, in practice, an absolute millimetre
# deflection carried over from a mesher that took one.
TESSELLATION_CEILINGS: dict[str, float] = {"chordTolerance": 0.05, "angleTolerance": math.pi / 2}
_UNITS = {"chordTolerance": "of each component's bounding diagonal", "angleTolerance": "radians"}


def tolerance_refusal(key: str, value: float, *, name: str) -> str | None:
    """Why ``value`` is no ``key`` (``chordTolerance`` or ``angleTolerance``) anything
    may be meshed at, in words that call it ``name`` -- what the door it came through
    calls it -- and name the bound it crosses; ``None`` when it is one.

    ``value`` is a finite positive number: each door refuses anything else first."""
    floor, ceiling, unit = TESSELLATION_FLOORS[key], TESSELLATION_CEILINGS[key], _UNITS[key]
    default = DISPLAY_TESSELLATION[key]
    if value < floor:
        return (f"{name} {value:g} is finer than cadgen meshes: it must be at least {floor:g} {unit} "
                f"(default {default:g})")
    if value <= ceiling:
        return None
    if key == "chordTolerance":
        return (f"{name} {value:g} is too large: the value is RELATIVE to each component's bounding "
                f"diagonal, not millimetres, so it must be at most {ceiling:g} (default {default:g}). For an "
                f"absolute chord deviation of X mm on a part whose bounding diagonal is D mm, pass X/D -- "
                f"{value:g} mm on a 200 mm part is {value / 200.0:g}")
    return (f"{name} {value:g} is too large: it must be at most {ceiling:g} {unit}, a quarter turn between "
            f"neighbouring facets (default {default:g})")

