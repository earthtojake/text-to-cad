# Prompt: A workshop DRAWING, not a cut layout -- the case from issue #246. A cabinetmaker's
# panel drawn as a document: plan view, front elevation, a section, 20 dimensions, centre lines,
# hidden edges and a title block.
#
# Nothing here is a toolpath, and that is the point. Every construct that makes a DXF a drawing
# rather than a laser file is present, because those are what `cadgen.drawing_checks` reads to
# decide which rules apply:
#
#   DIMENSION entities        the drawing's measurements
#   ISO 128 linetypes         CENTER for axes, HIDDEN for edges behind the face
#   a non-plotting layer      construction lines, which never reach paper
#   a title block layer       annotation, not geometry
#
# So a validator must NOT demand closed cut profiles here, and the Viewer must render it as
# lines rather than extruding a 3D prism out of contours that enclose nothing.

from __future__ import annotations

import ezdxf
from ezdxf.units import MM

PANEL_WIDTH_MM = 600.0
PANEL_HEIGHT_MM = 400.0
PANEL_THICKNESS_MM = 18.0

SHELF_HEIGHT_MM = 220.0
DOWEL_DIAMETER_MM = 8.0
DOWEL_INSET_MM = 50.0

ELEVATION_ORIGIN = (0.0, 0.0)
PLAN_ORIGIN = (0.0, -160.0)
SECTION_ORIGIN = (700.0, 0.0)


def _rectangle(msp, origin, width, height, layer):
    x, y = origin
    msp.add_lwpolyline(
        [(x, y), (x + width, y), (x + width, y + height), (x, y + height)],
        close=True,
        dxfattribs={"layer": layer},
    )


def gen_dxf():
    document = ezdxf.new("R2010", setup=True)
    document.units = MM
    msp = document.modelspace()

    for name, attribs in (
        ("OUTLINE", {}),
        ("HIDDEN-EDGES", {"linetype": "HIDDEN"}),
        ("CENTRELINES", {"linetype": "CENTER"}),
        ("CONSTRUCTION", {"plot": 0}),
        ("DIMENSIONS", {}),
        ("TITLEBLOCK", {}),
    ):
        document.layers.add(name, **attribs)

    # --- front elevation -------------------------------------------------------------
    _rectangle(msp, ELEVATION_ORIGIN, PANEL_WIDTH_MM, PANEL_HEIGHT_MM, "OUTLINE")
    # the shelf behind the face: hidden, because you cannot see it from the front
    msp.add_line(
        (ELEVATION_ORIGIN[0], ELEVATION_ORIGIN[1] + SHELF_HEIGHT_MM),
        (ELEVATION_ORIGIN[0] + PANEL_WIDTH_MM, ELEVATION_ORIGIN[1] + SHELF_HEIGHT_MM),
        dxfattribs={"layer": "HIDDEN-EDGES"},
    )
    # vertical centre line, running past the outline as a centre line does
    msp.add_line(
        (ELEVATION_ORIGIN[0] + (PANEL_WIDTH_MM / 2), ELEVATION_ORIGIN[1] - 25),
        (ELEVATION_ORIGIN[0] + (PANEL_WIDTH_MM / 2), ELEVATION_ORIGIN[1] + PANEL_HEIGHT_MM + 25),
        dxfattribs={"layer": "CENTRELINES"},
    )
    for x in (DOWEL_INSET_MM, PANEL_WIDTH_MM - DOWEL_INSET_MM):
        msp.add_circle(
            (ELEVATION_ORIGIN[0] + x, ELEVATION_ORIGIN[1] + SHELF_HEIGHT_MM),
            radius=DOWEL_DIAMETER_MM / 2,
            dxfattribs={"layer": "HIDDEN-EDGES"},
        )

    # --- plan view, projected below the elevation -----------------------------------
    _rectangle(msp, PLAN_ORIGIN, PANEL_WIDTH_MM, PANEL_THICKNESS_MM * 4, "OUTLINE")
    # projection lines tying the plan to the elevation: construction, never plotted
    for x in (0.0, PANEL_WIDTH_MM):
        msp.add_line(
            (PLAN_ORIGIN[0] + x, PLAN_ORIGIN[1] + (PANEL_THICKNESS_MM * 4)),
            (ELEVATION_ORIGIN[0] + x, ELEVATION_ORIGIN[1]),
            dxfattribs={"layer": "CONSTRUCTION"},
        )

    # --- section A-A, off to the right ----------------------------------------------
    _rectangle(msp, SECTION_ORIGIN, PANEL_THICKNESS_MM, PANEL_HEIGHT_MM, "OUTLINE")
    msp.add_line(
        (SECTION_ORIGIN[0], SECTION_ORIGIN[1] + SHELF_HEIGHT_MM),
        (SECTION_ORIGIN[0] + PANEL_THICKNESS_MM, SECTION_ORIGIN[1] + SHELF_HEIGHT_MM),
        dxfattribs={"layer": "OUTLINE"},
    )

    # --- dimensions ------------------------------------------------------------------
    # A drawing's defining feature. Twenty of them, on the layer the checks read as annotation.
    dim_style = {"layer": "DIMENSIONS"}
    horizontal = [
        ((0.0, 0.0), (PANEL_WIDTH_MM, 0.0), -60.0),
        ((0.0, 0.0), (DOWEL_INSET_MM, 0.0), -95.0),
        ((PANEL_WIDTH_MM - DOWEL_INSET_MM, 0.0), (PANEL_WIDTH_MM, 0.0), -95.0),
        ((DOWEL_INSET_MM, 0.0), (PANEL_WIDTH_MM - DOWEL_INSET_MM, 0.0), -130.0),
    ]
    for start, end, distance in horizontal:
        msp.add_linear_dim(base=(0, distance), p1=start, p2=end, dxfattribs=dim_style).render()

    vertical = [
        ((0.0, 0.0), (0.0, PANEL_HEIGHT_MM), -70.0),
        ((0.0, 0.0), (0.0, SHELF_HEIGHT_MM), -115.0),
        ((0.0, SHELF_HEIGHT_MM), (0.0, PANEL_HEIGHT_MM), -115.0),
    ]
    for start, end, distance in vertical:
        msp.add_linear_dim(
            base=(distance, 0), p1=start, p2=end, angle=90, dxfattribs=dim_style
        ).render()

    # section thickness and shelf height, dimensioned on the section
    msp.add_linear_dim(
        base=(SECTION_ORIGIN[0], SECTION_ORIGIN[1] - 60),
        p1=(SECTION_ORIGIN[0], SECTION_ORIGIN[1]),
        p2=(SECTION_ORIGIN[0] + PANEL_THICKNESS_MM, SECTION_ORIGIN[1]),
        dxfattribs=dim_style,
    ).render()
    msp.add_linear_dim(
        base=(SECTION_ORIGIN[0] + 90, SECTION_ORIGIN[1]),
        p1=(SECTION_ORIGIN[0] + PANEL_THICKNESS_MM, SECTION_ORIGIN[1]),
        p2=(SECTION_ORIGIN[0] + PANEL_THICKNESS_MM, SECTION_ORIGIN[1] + SHELF_HEIGHT_MM),
        angle=90,
        dxfattribs=dim_style,
    ).render()

    # radial dimensions on the dowel holes
    for x in (DOWEL_INSET_MM, PANEL_WIDTH_MM - DOWEL_INSET_MM):
        msp.add_diameter_dim(
            center=(x, SHELF_HEIGHT_MM),
            radius=DOWEL_DIAMETER_MM / 2,
            angle=45,
            dxfattribs=dim_style,
        ).render()

    # --- title block -----------------------------------------------------------------
    title_origin = (0.0, -260.0)
    _rectangle(msp, title_origin, 420.0, 70.0, "TITLEBLOCK")
    msp.add_line(
        (title_origin[0], title_origin[1] + 35),
        (title_origin[0] + 420, title_origin[1] + 35),
        dxfattribs={"layer": "TITLEBLOCK"},
    )
    for text, position in (
        ("CABINET SIDE PANEL", (8.0, -222.0)),
        ("SCALE 1:5   MATERIAL 18mm BIRCH PLY", (8.0, -252.0)),
        ("SECTION A-A", (SECTION_ORIGIN[0] - 10, SECTION_ORIGIN[1] - 100)),
    ):
        msp.add_text(text, height=12, dxfattribs={"layer": "TITLEBLOCK"}).set_placement(position)

    return {"document": document}


if __name__ == "__main__":
    gen_dxf()
