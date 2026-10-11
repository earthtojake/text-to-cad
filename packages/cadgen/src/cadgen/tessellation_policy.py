"""What cadgen meshes a STEP model's components at for display: the one tessellation policy.

Every display mesh is cadgen's (OCCT on the exact BREP, ``cadgen.store.meshes``),
and so is the choice of tolerances it is made at:

- **The ladder** (:data:`TESSELLATION_LADDER`): the rungs a viewer may draw a
  component at, coarse to fine. Chord tolerance is RELATIVE to each component's
  bounding diagonal, angle tolerance is radians. Rung :data:`DEFAULT_LEVEL` is
  the standard mesh every model opens at; the coarser rung loosens both
  criteria (chord alone is not reliably cheaper for trimmed surfaces), and the
  finer ones are close inspection's. A viewer picks a rung from its camera,
  with hysteresis; which numbers a rung means is this module's, published to
  the page (:func:`ladder_payload`: the CAD Viewer's server info, the CAD app's
  launch), never written down in the page.
- **The bounds** (:data:`TESSELLATION_FLOORS`, :data:`TESSELLATION_CEILINGS`):
  the finest and the coarsest anything may ask to have meshed. One rule
  (:func:`tolerance_refusal`) holds them at every door a tolerance enters -- a
  decorator argument or a flag (``cadgen.metadata``), a snapshot's
  ``quality.tessellation`` (``cadgen.snapshot_core``), a store or daemon request
  (``cadgen.store.meshes``) -- so a request outside them is refused where it
  enters, in words naming the bound, and never meshed.
- **A snapshot's tessellation** (:func:`snapshot_tessellation`): an explicit
  ``quality.tessellation``, or the rung its display asks for -- Render's
  ``final`` lighting quality draws the finest rung, everything else the
  standard one. The job carries the answer; the page only reads it.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

__all__ = [
    "DEFAULT_LEVEL",
    "DEFAULT_TESSELLATION",
    "TESSELLATION_CEILINGS",
    "TESSELLATION_FLOORS",
    "TESSELLATION_LADDER",
    "ladder_payload",
    "snapshot_tessellation",
    "tolerance_refusal",
]

TESSELLATION_LADDER: tuple[dict[str, float], ...] = (
    {"chordTolerance": 2e-3, "angleTolerance": 1.4},
    {"chordTolerance": 1.5e-3, "angleTolerance": 0.35},
    {"chordTolerance": 5e-4, "angleTolerance": 0.35},
    {"chordTolerance": 1.5e-4, "angleTolerance": 0.35},
)
DEFAULT_LEVEL = 1
DEFAULT_TESSELLATION: dict[str, float] = dict(TESSELLATION_LADDER[DEFAULT_LEVEL])
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
# The rung Render's `final` lighting quality draws a still at.
FINAL_RENDER_LEVEL = len(TESSELLATION_LADDER) - 1
_UNITS = {"chordTolerance": "of each component's bounding diagonal", "angleTolerance": "radians"}


def tolerance_refusal(key: str, value: float, *, name: str) -> str | None:
    """Why ``value`` is no ``key`` (``chordTolerance`` or ``angleTolerance``) anything
    may be meshed at, in words that call it ``name`` -- what the door it came through
    calls it -- and name the bound it crosses; ``None`` when it is one.

    ``value`` is a finite positive number: each door refuses anything else first."""
    floor, ceiling, unit = TESSELLATION_FLOORS[key], TESSELLATION_CEILINGS[key], _UNITS[key]
    default = DEFAULT_TESSELLATION[key]
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


def ladder_payload() -> dict[str, Any]:
    """The ladder as the page receives it: ``{"levels": [...], "defaultLevel": n}``."""
    return {"levels": [dict(level) for level in TESSELLATION_LADDER], "defaultLevel": DEFAULT_LEVEL}


def _lighting_quality(display: Mapping[str, Any]) -> str | None:
    """The lighting quality a display asks for, or ``None`` when it is not lit."""
    lighting = display.get("lighting")
    if isinstance(lighting, Mapping):
        if lighting.get("enabled", True) is False:
            return None
        return str(lighting.get("quality") or "final")
    return "final" if display.get("mode") == "render" else None


def snapshot_tessellation(job: Mapping[str, Any]) -> dict[str, float]:
    """The tolerances a snapshot job's STEP meshes are drawn at, both named.

    An explicit ``quality.tessellation`` (already held to the bounds) names its
    own; a tolerance it leaves out is the standard rung's.
    """
    quality = job.get("quality") if isinstance(job.get("quality"), Mapping) else {}
    explicit = quality.get("tessellation")
    if isinstance(explicit, Mapping):
        return {key: float(explicit.get(key, value)) for key, value in DEFAULT_TESSELLATION.items()}
    display = job.get("display") if isinstance(job.get("display"), Mapping) else {}
    level = FINAL_RENDER_LEVEL if _lighting_quality(display) == "final" else DEFAULT_LEVEL
    return dict(TESSELLATION_LADDER[level])
