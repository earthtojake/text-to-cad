"""``turn_face``: face the front of the bar down to the part's front face (or a height), in axial steps.

Own keys: ``z_mm`` (the faced front, WCS; default the part's front face plus ``allowance_z_mm``), ``doc_mm`` (the
most taken off a pass, axially; default the material's roughing depth of cut), ``allowance_z_mm`` (left on the face
for a finish pass; default 0), ``x_end_mm`` (where each pass ends; default the nose radius past the centre, so no
pip is left), ``css_m_min``, ``feed_mm_rev``. Each pass starts outside the bar, feeds towards the axis, backs off
the face and returns outside the bar; the passes split the stock evenly.
"""

from __future__ import annotations

import math

from cadgen._internal.cam.job_errors import read_number
from cadgen._internal.cam.operations._turning import TURN_KEYS, TurnOperation, lathe, note

__all__ = ["TurnFaceOp"]


class TurnFaceOp(TurnOperation):
    name = "turn_face"
    plain = "Face"
    keys = ("z_mm", "doc_mm", "allowance_z_mm", "x_end_mm", *TURN_KEYS)
    common_keys = ("feed", "speed")
    tool_types = ("turn",)
    feeds_kind = "turn_face"

    def parse(self, spec, ctx):
        params = super().parse(spec, ctx)
        extra = spec.extra
        params.update(
            z_mm=read_number(extra, "z_mm", spec.where, minimum=-1e6),
            doc_mm=read_number(extra, "doc_mm", spec.where),
            allowance_z_mm=read_number(extra, "allowance_z_mm", spec.where, default=0.0, minimum=0.0),
            x_end_mm=read_number(extra, "x_end_mm", spec.where, minimum=-1e6),
        )
        return params

    def plan(self, ctx, params):
        from cadgen._internal.cam.feeds import turn_depth_of_cut

        lt = lathe(ctx)
        tool = ctx.tool
        r = tool.nose_radius_mm
        target = params["z_mm"] if params["z_mm"] is not None else lt.profile.z_front + params["allowance_z_mm"]
        x_end = params["x_end_mm"] if params["x_end_mm"] is not None else -r
        b = lt.builder()
        lt.begin(b)
        front = lt.front()
        ctx.meta["lathe"] = {"role": "od"}
        ctx.meta["what"] = f"to Z{target:g}"
        top = lt.top() or lt.bar_radius
        feeds = lt.feeds("turn_face", 2.0 * top, params)
        if front is None or front <= target + 1e-6:
            note(ctx, "the front is already at the faced height: nothing to face")
            lt.home(b)
            return b.build()
        if target < lt.profile.z_front - 1e-6:
            note(ctx, f"faces to Z{target:g}, into the part (its front face is at Z{lt.profile.z_front:g})")
        doc = params["doc_mm"] or turn_depth_of_cut(ctx.material)
        count = max(1, int(math.ceil((front - target) / doc - 1e-9)))
        x_start = top + lt.approach
        f = feeds.feed_mm_min
        for k in range(count):
            z = front - (front - target) * (k + 1) / count
            b.rapid(x=x_start)
            b.rapid(z=z)
            b.feed(x=x_end, f=f)
            b.rapid(z=z + lt.approach)
            b.rapid(x=x_start)
        ctx.meta.update({"passes": count, "face_z": round(target, 4)})
        lt.home(b)
        return b.build()
