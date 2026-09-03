# Prompt: A workshop DRAWING rather than a cut layout (issue #246) -- a cabinetmaker's
# side panel drawn as a document: front elevation, plan view, section A-A, eleven
# dimension callouts, centre and shelf lines, and a title block.
#
# The retired ezdxf generator (git history: `models/drawings/dxf/cabinet_panel_drawing.dxf.py`)
# built this out of DXF DIMENSION entities, ISO 128 CENTER/HIDDEN linetypes, a
# non-plotting CONSTRUCTION layer and TEXT entities. `@dxf` emits none of those:
# the contract is build123d geometry in, entities out. So the drawing's INFORMATION
# is re-expressed in the mechanism the contract does have -- geometry on layers that
# carry intent:
#
#   CUT      the three views' closed profiles and the two dowel holes
#   ENGRAVE  everything annotative, as outlines and open lines: witness/leader
#            lines, the dimension VALUES as engraved text, centre and shelf lines,
#            the title block and its lettering
#
# Every measurement below is the same number the retired generator dimensioned.

from __future__ import annotations

from cadgen import build123d as bd
from cadgen import dxf

PANEL_WIDTH_MM = 600.0
PANEL_HEIGHT_MM = 400.0
PANEL_THICKNESS_MM = 18.0

SHELF_HEIGHT_MM = 220.0
DOWEL_DIAMETER_MM = 8.0
DOWEL_INSET_MM = 50.0

ELEVATION_ORIGIN = (0.0, 0.0)
PLAN_ORIGIN = (0.0, -160.0)
SECTION_ORIGIN = (700.0, 0.0)

TITLE_ORIGIN = (0.0, -260.0)
TITLE_WIDTH_MM = 420.0
TITLE_HEIGHT_MM = 70.0

DIM_TEXT_MM = 18.0
TITLE_TEXT_MM = 16.0
WITNESS_GAP_MM = 4.0  # the break between a feature and its witness line
WITNESS_OVER_MM = 6.0  # how far a witness line runs past the dimension line
TICK_MM = 5.0  # the 45 degree architectural tick that stands in for an arrowhead


def _rectangle(origin, width, height):
    """A closed rectangle as a sketch face, positioned by its lower-left corner."""
    x, y = origin
    with bd.BuildSketch() as sketch:
        with bd.Locations((x + width / 2.0, y + height / 2.0)):
            bd.Rectangle(width, height)
    return sketch.sketch


def _text(value, position, size, *, rotation=0.0, align=None):
    align = align or (bd.Align.MIN, bd.Align.MIN)
    with bd.BuildSketch() as sketch:
        with bd.Locations(position):
            bd.Text(value, font_size=size, align=align, rotation=rotation)
    return sketch.sketch


class _Annotation:
    """Collects annotation line work, dropping segments that repeat exactly.

    Adjacent dimensions legitimately share a witness line (the 220 and the 180
    both witness off y=220), and the drawing checks reject exact duplicate
    geometry as a double-cut risk, so the shared edge is emitted once.
    """

    def __init__(self):
        self._seen = set()
        self.edges = []

    def line(self, start, end):
        key = tuple(sorted((tuple(round(v, 6) for v in start), tuple(round(v, 6) for v in end))))
        if key in self._seen:
            return
        self._seen.add(key)
        self.edges.append(bd.Line(start, end))


def _horizontal_dim(ann, x1, x2, y_feature, y_dim, label):
    """A horizontal linear dimension: two witness lines, a dimension line, ticks, a value."""
    direction = -1.0 if y_dim < y_feature else 1.0
    for x in (x1, x2):
        ann.line(
            (x, y_feature + direction * WITNESS_GAP_MM),
            (x, y_dim + direction * WITNESS_OVER_MM),
        )
        ann.line((x - TICK_MM, y_dim - TICK_MM), (x + TICK_MM, y_dim + TICK_MM))
    ann.line((x1, y_dim), (x2, y_dim))
    return _text(
        label,
        ((x1 + x2) / 2.0, y_dim + WITNESS_GAP_MM),
        DIM_TEXT_MM,
        align=(bd.Align.CENTER, bd.Align.MIN),
    )


def _vertical_dim(ann, y1, y2, x_feature, x_dim, label):
    """A vertical linear dimension; the value reads from the right, as ISO wants."""
    direction = -1.0 if x_dim < x_feature else 1.0
    for y in (y1, y2):
        ann.line(
            (x_feature + direction * WITNESS_GAP_MM, y),
            (x_dim + direction * WITNESS_OVER_MM, y),
        )
        ann.line((x_dim - TICK_MM, y - TICK_MM), (x_dim + TICK_MM, y + TICK_MM))
    ann.line((x_dim, y1), (x_dim, y2))
    return _text(
        label,
        (x_dim - WITNESS_GAP_MM, (y1 + y2) / 2.0),
        DIM_TEXT_MM,
        rotation=90.0,
        align=(bd.Align.CENTER, bd.Align.MIN),
    )


def _diameter_callout(ann, centre, radius, label, side):
    """A 45 degree leader off the hole, a horizontal shoulder, and the value above it.

    ``side`` is -1 or +1, so a callout can lean away from the nearest panel edge.
    """
    cx, cy = centre
    offset = radius / (2.0**0.5)
    knee = (cx + side * 30.0, cy + 30.0)
    ann.line((cx + side * offset, cy + offset), knee)
    ann.line(knee, (knee[0] + side * 40.0, knee[1]))
    return _text(
        label,
        (knee[0] + side * 2.0, knee[1] + WITNESS_GAP_MM),
        DIM_TEXT_MM,
        align=(bd.Align.MIN if side > 0 else bd.Align.MAX, bd.Align.MIN),
    )


@dxf(out="../DXF/cabinet_panel_drawing.dxf")
def cabinet_panel_drawing():
    elevation_x, elevation_y = ELEVATION_ORIGIN
    section_x, section_y = SECTION_ORIGIN

    # --- the three views, as closed cut profiles ------------------------------------
    with bd.BuildSketch() as cut:
        bd.add(_rectangle(ELEVATION_ORIGIN, PANEL_WIDTH_MM, PANEL_HEIGHT_MM))
        bd.add(_rectangle(PLAN_ORIGIN, PANEL_WIDTH_MM, PANEL_THICKNESS_MM * 4))
        bd.add(_rectangle(SECTION_ORIGIN, PANEL_THICKNESS_MM, PANEL_HEIGHT_MM))
        dowel_xs = (DOWEL_INSET_MM, PANEL_WIDTH_MM - DOWEL_INSET_MM)
        with bd.Locations(*[(elevation_x + x, elevation_y + SHELF_HEIGHT_MM) for x in dowel_xs]):
            bd.Circle(DOWEL_DIAMETER_MM / 2.0, mode=bd.Mode.SUBTRACT)

    ann = _Annotation()
    labels = []

    # --- reference line work the retired generator carried as linetypes ---------------
    # HIDDEN: the shelf behind the face, which you cannot see from the front.
    ann.line((elevation_x, elevation_y + SHELF_HEIGHT_MM),
             (elevation_x + PANEL_WIDTH_MM, elevation_y + SHELF_HEIGHT_MM))
    # CENTER: the vertical axis, running past the outline as a centre line does.
    ann.line((elevation_x + PANEL_WIDTH_MM / 2.0, elevation_y - 25.0),
             (elevation_x + PANEL_WIDTH_MM / 2.0, elevation_y + PANEL_HEIGHT_MM + 25.0))
    # The shelf where the section cuts it.
    ann.line((section_x, section_y + SHELF_HEIGHT_MM),
             (section_x + PANEL_THICKNESS_MM, section_y + SHELF_HEIGHT_MM))

    # --- the eleven dimensions -------------------------------------------------------
    labels.append(_horizontal_dim(ann, 0.0, PANEL_WIDTH_MM, 0.0, -60.0, "600"))
    # The dowel ladder witnesses off the TOP edge, not the bottom. The retired generator
    # stacked it below at y=-95/-130, which drew the 500 straight across the plan view;
    # the values and spans are its values and spans, moved to where they can be read.
    top_edge = elevation_y + PANEL_HEIGHT_MM
    labels.append(_horizontal_dim(ann, 0.0, DOWEL_INSET_MM, top_edge, top_edge + 60.0, "50"))
    labels.append(
        _horizontal_dim(
            ann,
            PANEL_WIDTH_MM - DOWEL_INSET_MM,
            PANEL_WIDTH_MM,
            top_edge,
            top_edge + 60.0,
            "50",
        )
    )
    labels.append(
        _horizontal_dim(
            ann,
            DOWEL_INSET_MM,
            PANEL_WIDTH_MM - DOWEL_INSET_MM,
            top_edge,
            top_edge + 95.0,
            "500",
        )
    )

    labels.append(_vertical_dim(ann, 0.0, PANEL_HEIGHT_MM, 0.0, -70.0, "400"))
    labels.append(_vertical_dim(ann, 0.0, SHELF_HEIGHT_MM, 0.0, -115.0, "220"))
    labels.append(_vertical_dim(ann, SHELF_HEIGHT_MM, PANEL_HEIGHT_MM, 0.0, -115.0, "180"))

    labels.append(
        _horizontal_dim(
            ann, section_x, section_x + PANEL_THICKNESS_MM, section_y, section_y - 60.0, "18"
        )
    )
    labels.append(
        _vertical_dim(
            ann,
            section_y,
            section_y + SHELF_HEIGHT_MM,
            section_x + PANEL_THICKNESS_MM,
            section_x + 90.0,
            "220",
        )
    )

    for x, side in ((DOWEL_INSET_MM, 1.0), (PANEL_WIDTH_MM - DOWEL_INSET_MM, -1.0)):
        labels.append(
            _diameter_callout(
                ann,
                (elevation_x + x, elevation_y + SHELF_HEIGHT_MM),
                DOWEL_DIAMETER_MM / 2.0,
                f"{chr(0x00D8)}{DOWEL_DIAMETER_MM:.0f}",
                side,
            )
        )

    # --- title block ------------------------------------------------------------------
    title_x, title_y = TITLE_ORIGIN
    for corner_a, corner_b in (
        ((title_x, title_y), (title_x + TITLE_WIDTH_MM, title_y)),
        (
            (title_x + TITLE_WIDTH_MM, title_y),
            (title_x + TITLE_WIDTH_MM, title_y + TITLE_HEIGHT_MM),
        ),
        (
            (title_x + TITLE_WIDTH_MM, title_y + TITLE_HEIGHT_MM),
            (title_x, title_y + TITLE_HEIGHT_MM),
        ),
        ((title_x, title_y + TITLE_HEIGHT_MM), (title_x, title_y)),
        (
            (title_x, title_y + TITLE_HEIGHT_MM / 2.0),
            (title_x + TITLE_WIDTH_MM, title_y + TITLE_HEIGHT_MM / 2.0),
        ),
    ):
        ann.line(corner_a, corner_b)

    for value, position in (
        ("CABINET SIDE PANEL", (8.0, -222.0)),
        ("SCALE 1:5   MATERIAL 18mm BIRCH PLY", (8.0, -252.0)),
        ("SECTION A-A", (section_x - 10.0, section_y - 100.0)),
    ):
        labels.append(_text(value, position, TITLE_TEXT_MM))

    return {"CUT": cut.sketch, "ENGRAVE": [*labels, *ann.edges]}


if __name__ == "__main__":
    cabinet_panel_drawing()
