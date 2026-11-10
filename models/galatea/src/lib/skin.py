"""Galatea's exterior: how a skin is made, and the forms every skin is cut from.

A skin is two layers over one lofted form (rows of `geo.S` sections):

    the panel    pearl, PANEL_T thick, the outside. It is cut into panels by regions drawn
                 in a side or front view, with a shut line GAP wide between two panels.
    the liner    black, LINER_T thick, under all of it. Where no panel lies it is the
                 outside: the under-body that shows at the flanks, behind the calves and in
                 every shut line. It is what the frame's pads carry.

The mechanism stands inside the liner with AIR round it (`fit.py` measures that from the
rows, without the kernel; `checks/interference.py` has the last word).

FORMS lists each form with the links whose mechanism it has to hold, for `fit.py`.
"""

import build123d as bd

from . import geo

PANEL_T = 2.6
LINER_T = 1.8
AIR = 3.0
GAP = 1.6
WIDE = 500.0

# Labels (or their beginnings) of the parts that are skin, which no skin has to hold.
SKIN_LABELS = ("helmet", "face_shield", "head_liner", "face_fascia", "panel_", "liner_", "pad_", "status_light", "trim_", "wordmark")

FORMS = {}


def register(name, rows, covers, **more):
    """Enter a form in FORMS (what `fit.py` reads) and return its rows."""
    FORMS[name] = dict(rows=list(rows), covers=list(covers), **more)
    return list(rows)


class Form:
    """One lofted form at several insets, each lofted once: `form(2.6)` is the form with
    every section drawn in by 2.6. `top`/`bottom` close an end in a point."""

    def __init__(self, rows, top=None, bottom=None):
        self.rows, self.top, self.bottom, self.made = list(rows), top, bottom, {}

    def __call__(self, shrink=0.0):
        if shrink not in self.made:
            shift = lambda v, d: None if v is None else (v[0], v[1], v[2] + d)
            self.made[shrink] = geo.loft(self.rows, shrink=shrink, top=shift(self.top, -shrink), bottom=shift(self.bottom, shrink))
        return self.made[shrink]

    @property
    def panel(self):
        if "panel" not in self.made:
            self.made["panel"] = geo.cut(self(0.0), self(PANEL_T), "panel layer")
        return self.made["panel"]

    @property
    def liner(self):
        if "liner" not in self.made:
            self.made["liner"] = geo.cut(self(PANEL_T), self(PANEL_T + LINER_T), "liner layer")
        return self.made["liner"]

    @property
    def cavity(self):
        return self(PANEL_T + LINER_T)


def trim(layer, tools, what):
    """A layer less every tool: the tools are plain prisms and boxes, joined first, so that the
    lofted layer meets the kernel (and the guard's slow measure) once."""
    tool = tools[0]
    for more in tools[1:]:
        tool = tool + more
    return geo.cut(layer, tool, what)


def from_side(points, closing, x0=-WIDE, x1=WIDE):
    """The region bounded by a curve drawn in the side view (y, z) and closed through
    `closing`, as a prism across the robot from x0 to x1."""
    return geo.plate_yz(geo.behind_curve(points, closing), x0, x1)


def from_front(face, y0=-WIDE, y1=0.0):
    """An outline drawn in the front view (x, z), as a prism from y0 to y1 (the robot's front by default)."""
    return geo.plate_xz(face, y0, y1)


def from_top(face, z0, z1):
    """An outline drawn in plan (x, y), as a prism from z0 to z1."""
    return geo.plate_xy(face, z0, z1)


def solids(shape):
    """A boolean's result as one shape: its solid, or a compound of its solids."""
    found = list(shape) if isinstance(shape, (list, bd.ShapeList)) else shape.solids()
    if not found:
        raise geo.WrongBoolean("nothing is left of a skin")
    return found[0] if len(found) == 1 else bd.Compound(found)


FONT = "/usr/share/fonts/opentype/inter/Inter-Medium.otf"     # the wordmark's face, Inter, where this computer has it
CAP = 0.727                                                    # ... whose capitals are this part of its size


def lettering(text, height, plane, depth):
    """`text` as prisms `depth` long standing on `plane`, its capitals `height` tall and centred
    on the plane's origin. Set in Inter where the font file is there, in the kernel's default
    face elsewhere (the letters then differ; nothing else does)."""
    import os

    face = dict(font_path=FONT) if os.path.exists(FONT) else {}
    word = bd.Text(text, font_size=height / CAP, align=(bd.Align.CENTER, bd.Align.CENTER), **face)
    return bd.extrude(plane * word, amount=depth)
