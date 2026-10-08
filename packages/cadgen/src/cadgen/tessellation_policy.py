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
- **The floors** (:data:`TESSELLATION_FLOORS`): the finest anything may ask to
  have meshed (``cadgen.metadata``), so an absurd request is refused where it
  enters rather than exhausting a mesher.
- **A snapshot's tessellation** (:func:`snapshot_tessellation`): an explicit
  ``quality.tessellation``, or the rung its display asks for -- Render's
  ``final`` lighting quality draws the finest rung, everything else the
  standard one. The job carries the answer; the page only reads it.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from cadgen.metadata import MESH_ANGULAR_TOLERANCE_MIN, MESH_TOLERANCE_MIN

__all__ = [
    "DEFAULT_LEVEL",
    "DEFAULT_TESSELLATION",
    "TESSELLATION_FLOORS",
    "TESSELLATION_LADDER",
    "ladder_payload",
    "snapshot_tessellation",
]

TESSELLATION_LADDER: tuple[dict[str, float], ...] = (
    {"chordTolerance": 2e-3, "angleTolerance": 1.4},
    {"chordTolerance": 1.5e-3, "angleTolerance": 0.35},
    {"chordTolerance": 5e-4, "angleTolerance": 0.35},
    {"chordTolerance": 1.5e-4, "angleTolerance": 0.35},
)
DEFAULT_LEVEL = 1
DEFAULT_TESSELLATION: dict[str, float] = dict(TESSELLATION_LADDER[DEFAULT_LEVEL])
TESSELLATION_FLOORS: dict[str, float] = {
    "chordTolerance": MESH_TOLERANCE_MIN,
    "angleTolerance": MESH_ANGULAR_TOLERANCE_MIN,
}
# The rung Render's `final` lighting quality draws a still at.
FINAL_RENDER_LEVEL = len(TESSELLATION_LADDER) - 1


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

    An explicit ``quality.tessellation`` (already checked against the floors)
    names its own; a tolerance it leaves out is the standard rung's.
    """
    quality = job.get("quality") if isinstance(job.get("quality"), Mapping) else {}
    explicit = quality.get("tessellation")
    if isinstance(explicit, Mapping):
        return {key: float(explicit.get(key, value)) for key, value in DEFAULT_TESSELLATION.items()}
    display = job.get("display") if isinstance(job.get("display"), Mapping) else {}
    level = FINAL_RENDER_LEVEL if _lighting_quality(display) == "final" else DEFAULT_LEVEL
    return dict(TESSELLATION_LADDER[level])
