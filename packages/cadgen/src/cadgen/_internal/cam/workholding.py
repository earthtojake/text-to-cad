"""A setup's vise or plate, compiled to the keep-out boxes the ``fixture`` check and the GLB read.

The job names a fixture by its ``type`` (``job.FIXTURE_KEYS``; parsed into a :class:`~cadgen._internal.cam.job.Holding`)
and the plan builds its boxes here, where the stock and the setup's frame are known (``run.plan_setups``). They are
built around the stock's bounding box in the frame the fixture stands in, then written in part coordinates, so they
are :class:`~cadgen._internal.cam.job.Fixture` boxes like the job's own:

- the frame: the setup's WCS axes (Z up the tool), except on a mill4/mill5 in a rotary position, where the fixture is
  bolted to the table and turns with the part: there it stands in the part's own axes (the table at rotary zero). A
  box is square to the part's axes, so a fixture in a frame turned at an angle to them (a setup turned onto a sloping
  face) is refused, with the boxes to write instead.
- ``vise``: two jaws on the stock's sides along ``jaws_along`` (``x``: on its -X and +X sides, closing along X; by
  default across the stock's narrower side, ``y`` on a tie), ``jaw_width_mm`` wide about the stock's centre and
  ``jaw_thickness_mm`` thick, standing on the vise's floor (a slab ``floor_thickness_mm`` thick under both jaws). The
  stock sits on two parallels ``parallels_mm`` tall (0: on the floor), each ``parallel_width_mm`` wide (at most a
  quarter of the stock) under its edge along a jaw. ``grip_mm``, how far the jaws reach up the stock, is
  ``jaw_height_mm - parallels_mm``: any two give the third (``job`` checks three agree). With fewer than two stated
  the grip is :data:`VISE_GRIP_MM` (at most half the stock's height) and the jaws :data:`VISE_DEFAULTS`'s height.
- ``plate``: a plate ``thickness_mm`` thick under the stock, ``border_mm`` wider than it all round.

Every size the job did not state is a default, listed by key in what :func:`holding_boxes` returns, for the
``fixture`` check's ``assumed_fixture`` note. Stdlib at import; numpy inside.
"""

from __future__ import annotations

from cadgen._internal.cam.job import Fixture
from cadgen._internal.cam.job_errors import CamJobError

__all__ = ["PLATE_DEFAULTS", "VISE_DEFAULTS", "VISE_GRIP_MM", "holding_boxes"]

#: A vise's sizes when the job does not state them, mm.
VISE_DEFAULTS = {"jaw_height_mm": 40.0, "jaw_width_mm": 150.0, "jaw_thickness_mm": 20.0, "parallel_width_mm": 6.0,
                 "floor_thickness_mm": 10.0}
#: How far a vise's jaws reach up the stock when the job states fewer than two of jaw height, grip and parallels, mm
#: (at most half the stock's height).
VISE_GRIP_MM = 10.0
#: A plate's sizes when the job does not state them, mm.
PLATE_DEFAULTS = {"thickness_mm": 12.0, "border_mm": 25.0}


def holding_boxes(setup, wcs, stock_points) -> tuple[tuple[Fixture, ...], list[dict]]:
    """The boxes (part coordinates) of every vise and plate ``setup.holding`` names, around the stock (``stock_points``
    (N, 3), part mm) in the setup's frame (``wcs``); and per fixture with a default, ``{"fixture", "type",
    "assumed": {key: value}}``."""
    import numpy as np

    if not setup.holding:
        return (), []
    frame = np.eye(3) if wcs.rotary_deg else np.asarray(wcs.rotation, dtype=float)
    boxes: list[Fixture] = []
    assumed: list[dict] = []
    for holding in setup.holding:
        if not np.allclose(np.abs(frame), np.round(np.abs(frame)), atol=1e-9):
            raise CamJobError(f"{holding.where}: setup {setup.id} turns the part onto {setup.orientation}, at an "
                              f"angle to the part's axes, and a {holding.type}'s boxes stay square to them (a fixture "
                              "box is in part coordinates); give it as boxes {\"min_mm\", \"max_mm\"} in part "
                              "coordinates instead")
        turned = np.asarray(stock_points, dtype=float) @ frame.T
        low, high = turned.min(axis=0), turned.max(axis=0)
        build = _vise if holding.type == "vise" else _plate
        pieces, defaults = build(holding.stated, low, high)
        label = holding.name or holding.type
        for name, (lo, hi) in pieces:
            corners = np.array([[x, y, z] for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])])
            part = corners @ frame
            boxes.append(Fixture(tuple(round(float(v), 9) + 0.0 for v in part.min(axis=0)),
                                 tuple(round(float(v), 9) + 0.0 for v in part.max(axis=0)), f"{label} {name}".strip()))
        if defaults:
            assumed.append({"fixture": label, "type": holding.type, "assumed": defaults})
    return tuple(boxes), assumed


def _vise(stated: dict, low, high) -> tuple[list, dict]:
    height = float(high[2] - low[2])
    defaults: dict = {}
    along = stated.get("jaws_along")
    if along is None:
        along = "x" if high[0] - low[0] < high[1] - low[1] - 1e-9 else "y"
        defaults["jaws_along"] = along
    jaws, grip, parallels = (stated.get(k) for k in ("jaw_height_mm", "grip_mm", "parallels_mm"))
    given = sum(v is not None for v in (jaws, grip, parallels))
    if given < 2:
        if grip is None:
            grip = min(VISE_GRIP_MM, height / 2.0)
            if jaws is not None:
                grip = min(grip, jaws)
        if jaws is None:
            jaws = grip + parallels if parallels is not None else max(VISE_DEFAULTS["jaw_height_mm"], grip)
        if parallels is None:
            parallels = jaws - grip
        defaults.update({k: round(v, 4) for k, v in (("jaw_height_mm", jaws), ("grip_mm", grip),
                                                      ("parallels_mm", parallels)) if k not in stated})
    elif jaws is None:
        jaws = grip + parallels
    elif grip is None:
        grip = jaws - parallels
    elif parallels is None:
        parallels = jaws - grip
    sizes = {}
    for key in ("jaw_width_mm", "jaw_thickness_mm", "floor_thickness_mm") + (("parallel_width_mm",) if parallels > 0
                                                                              else ()):
        sizes[key] = stated.get(key, VISE_DEFAULTS[key])
        if key not in stated:
            defaults[key] = sizes[key]
    c = 0 if along == "x" else 1
    o = 1 - c
    word = "XY"[c]
    floor = float(low[2]) - parallels
    top = floor + jaws
    middle = (low[o] + high[o]) / 2.0
    half, thick = sizes["jaw_width_mm"] / 2.0, sizes["jaw_thickness_mm"]

    def box(c_range, o_range, z_range):
        lo, hi = [0.0] * 3, [0.0] * 3
        lo[c], hi[c] = c_range
        lo[o], hi[o] = o_range
        lo[2], hi[2] = z_range
        return lo, hi

    across = (middle - half, middle + half)
    pieces = [(f"-{word} jaw", box((low[c] - thick, low[c]), across, (floor, top))),
              (f"+{word} jaw", box((high[c], high[c] + thick), across, (floor, top))),
              ("floor", box((low[c] - thick, high[c] + thick), across, (floor - sizes["floor_thickness_mm"], floor)))]
    if parallels > 0:
        width = min(sizes["parallel_width_mm"], (high[c] - low[c]) / 4.0)
        under = (float(low[o]), float(high[o]))
        pieces += [(f"-{word} parallel", box((low[c], low[c] + width), under, (floor, low[2]))),
                   (f"+{word} parallel", box((high[c] - width, high[c]), under, (floor, low[2])))]
    return pieces, defaults


def _plate(stated: dict, low, high) -> tuple[list, dict]:
    sizes = {key: stated.get(key, value) for key, value in PLATE_DEFAULTS.items()}
    defaults = {key: value for key, value in sizes.items() if key not in stated}
    border, thickness = sizes["border_mm"], sizes["thickness_mm"]
    lo = [low[0] - border, low[1] - border, low[2] - thickness]
    hi = [high[0] + border, high[1] + border, low[2]]
    return [("", (lo, hi))], defaults
