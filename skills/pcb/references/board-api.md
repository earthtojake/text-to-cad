# The board API: kicad-python for boards

`board` is `cadgen.kipy.board.Board`: kicad-python, the client of KiCad's own API, vendored
in cadgen as `cadgen.kipy`. Everything in this file is that library; cadgen adds nothing on
top of it, so kicad-python's own documentation (https://docs.kicad.org/kicad-python-main/)
is the full reference and this file is the part a board script uses. A script needs some of:

```python
from cadgen import pcb
from cadgen.kipy.board_types import ArcTrack, BoardLayer, BoardPolygon, BoardSegment, BoardText, Net, Track, Via, Zone
from cadgen.kipy.geometry import Angle, PolygonWithHoles, PolyLineNode, Vector2
from cadgen.kipy.util.units import from_mm, to_mm
from cadgen.kipy.board_rules import CustomRule, CustomRuleConstraint
from cadgen.kipy.board_jobs import PlotSettings, PositionExportSettings
from cadgen.kipy.project_types import NetClass, NetClassAssignment, NetClassAssignments
```

Enumerations live in the generated protocol modules under `cadgen.kipy.proto`:
`board.board_types_pb2` (`ZoneType`, `ZoneConnectionStyle`, `PadType`, `ViaType`),
`board.board_rules_pb2` (`CustomRuleConstraintType`, `CustomRuleDisallowType`,
`CustomRuleConstraintOption`), `board.board_commands_pb2` (`BoardOriginType`, `CustomRulesStatus`), `board.board_jobs_pb2` (`StatsOutputFormat`, `DrillFormat`,
`Board3DFormat`), `common.types.base_types_pb2` (`MinOptMax`, `RuleSeverity`, `DocumentType`),
`common.types.library_types_pb2` (`LibraryType`, `LibraryLoadStatus`) and
`common.types.project_settings_pb2` (the `NetClass` message a net class is made from).

## Units and frame

- Every length is an **integer in nanometres**: `from_mm(0.25)` → `250000`, `to_mm(n)` back,
  `from_mils`/`to_mils` for imperial footprints.
- Positions are `Vector2.from_xy_mm(x, y)` (`.x`, `.y` in nm); angles `Angle.from_degrees(r)`
  (`.degrees`). `PolyLineNode.from_xy(x, y)` takes **nanometres**, so wrap its arguments in
  `from_mm`.
- The frame is KiCad's: millimetres, **y down**, origin at the page's corner. Place the board
  wherever is convenient (centred on (0, 0) is simplest); rotations are KiCad's, in degrees.
  The drill/place origin that exports and KiCad's editor can measure from is set with
  `board.set_origin(BoardOriginType.BOT_DRILL, Vector2.from_xy_mm(-20, -15))` and read with
  `board.get_origin(BoardOriginType.BOT_DRILL)`.
- `Box2` is a bounding box (`.pos`, `.size`): `board.get_item_bounding_box(item)`.

## Layers

`BoardLayer` names every layer: copper `BL_F_Cu`, `BL_In1_Cu` … `BL_In30_Cu`, `BL_B_Cu`;
`BL_F_SilkS`/`BL_B_SilkS`, `BL_F_Mask`/`BL_B_Mask`, `BL_F_Paste`/`BL_B_Paste`,
`BL_F_Fab`/`BL_B_Fab`, `BL_F_CrtYd`/`BL_B_CrtYd`, `BL_Edge_Cuts`, `BL_Margin`,
`BL_Dwgs_User`, `BL_Cmts_User`, `BL_User_1` … `BoardLayer.Name(layer)` prints one. A new
board has two copper layers (`board.get_copper_layer_count()`, `board.get_enabled_layers()`);
`board.set_enabled_layers(...)` changes the set for a four-layer board.

## Geometry

| Class | Use |
| --- | --- |
| `Vector2` | a point or a size; `.length()`, `.rotate(angle, center)` |
| `Angle` | `from_degrees`, `.degrees`, `normalize()` |
| `PolyLineNode` | one vertex, `from_xy(x_nm, y_nm)` (or `from_point(Vector2)`); `.has_arc` for arc vertices |
| `PolyLine` | `.nodes`, `.closed`, `append(node)` |
| `PolygonWithHoles` | `.outline` (a `PolyLine`), `.holes`, `add_hole(polyline)`, `move(delta)`, `rotate(delta, center)`, `bounding_box()` |

A closed rectangle, the shape every outline and pour starts from:

```python
def rectangle(w, h, cx=0.0, cy=0.0):
    poly = PolygonWithHoles()
    for x, y in ((cx - w / 2, cy - h / 2), (cx + w / 2, cy - h / 2), (cx + w / 2, cy + h / 2), (cx - w / 2, cy + h / 2)):
        poly.outline.append(PolyLineNode.from_xy(from_mm(x), from_mm(y)))
    poly.outline.closed = True
    return poly
```

## The document

| Call | What it does |
| --- | --- |
| `board.create_items([items])` | adds items (tracks, vias, zones, shapes, text); returns them with their ids |
| `board.update_items([items])` | writes back items you changed after they were created or placed (a footprint's reference and pad nets) |
| `board.remove_items([items])` | deletes items |
| `board.get_footprints()`, `get_pads()`, `get_tracks()`, `get_vias()`, `get_zones()`, `get_shapes()`, `get_text()`, `get_nets()` | reads everything of a kind back |
| `board.get_items_by_net(Net(name="VBUS"))` | pads, tracks, vias and zones on a net |
| `board.get_connected_items([pad])` | everything copper joins to the given items: connectivity without DRC |
| `board.get_pad_shapes_as_polygons([pads])` | a pad's copper outline per layer, for geometry checks |
| `board.refill_zones()` | fills every zone (the decorator calls it before saving) |
| `board.save()` | writes `.kicad_pcb`, `.kicad_pro`, `.kicad_prl` (the decorator calls it last) |
| `board.get_as_string()` | the board's s-expression text as it would be saved |

Items are plain objects until `create_items` sends them; a change to an item after that
needs `update_items`. The decorator catches nothing: an `ApiError` (KiCad refused something,
its message says what) propagates and nothing is saved.

## Footprints and pads

```python
fp = board.place_footprint_from_library("Resistor_SMD:R_0603_1608Metric",
                                        Vector2.from_xy_mm(0, 5), Angle.from_degrees(-90))   # layer=BoardLayer.BL_B_Cu flips it to the bottom
fp.reference_field.text.value = "R1"                 # KiCad returns it as REF**
fp.value_field.text.value = "1k"                     # value_field, datasheet_field, description_field
fp.attributes.do_not_populate = True                 # also exclude_from_bill_of_materials, exclude_from_position_files
for pad in fp.definition.pads:                       # pads as placed: pad.number, pad.position (absolute, nm), pad.pad_type
    pad.net = Net(name={"1": "VBUS", "2": "LED"}[pad.number])
board.update_items([fp])                             # the reference and the nets reach the board here
```

`place_footprint_from_library` takes the id as `Nickname:Name`; the nickname must be a row of
the project's `fp-lib-table`, or KiCad answers `footprint 'Nickname:Name' not found`
([parts](parts.md)). The returned `FootprintInstance` has `.position`, `.orientation`,
`.layer`, `.definition` (the `Footprint`: `.pads`, `.shapes`, `.texts`, `.models`) and its
fields. Pad numbers follow the footprint, not the datasheet's pin names.

## Nets

A net is its name. `Net(name="VBUS")` on a pad, a track, a via or a zone puts the item on
that net; the first item makes the net exist. `board.get_nets()` lists them (the empty name is
"no net"). There is no netlist to keep in step: connectivity is what copper joins, and
`get_connected_items` reads it. The decorator counts, per net, the pads a copper path from
the first pad does not reach, and reports that as `unconnected`.

## Tracks, arcs, vias

```python
t = Track()
t.start, t.end = Vector2.from_xy_mm(0, 0), Vector2.from_xy_mm(5, 0)
t.width, t.layer, t.net = from_mm(0.25), BoardLayer.BL_F_Cu, Net(name="LED")

arc = ArcTrack()                                     # start, mid, end on the arc; width, layer, net
v = Via()
v.position, v.net = Vector2.from_xy_mm(7.2125, -8), Net(name="GND")
v.diameter, v.drill_diameter = from_mm(0.6), from_mm(0.3)
board.create_items([t, arc, v])
```

A track is one straight segment: a route with corners is several, end to start (the
`track()` helper in the skill does this). Tracks and vias carry their own width and size;
nothing fills them in from a net class.

## Zones: pours and keepouts

```python
pour = Zone()                                        # a copper zone by default (ZoneType.ZT_COPPER)
pour.outline = rectangle(39, 29)
pour.layers = [BoardLayer.BL_B_Cu]                   # several layers: one zone on each
pour.net, pour.name = Net(name="GND"), "GND"
pour.priority = 1                                    # higher wins where pours overlap
pour.clearance = from_mm(0.3)                        # this pour's own clearance
pour.connection.zone_connection = ZoneConnectionStyle.ZCS_FULL   # solid to pads; ZCS_THERMAL is KiCad's default
pour.connection.thermal_spokes.width = from_mm(0.5)

keepout = Zone()
keepout.type = ZoneType.ZT_RULE_AREA
keepout.outline, keepout.layers, keepout.name = rectangle(4, 4, 12, -8), [BoardLayer.BL_F_Cu, BoardLayer.BL_B_Cu], "under the antenna"
keepout.rule_area_settings.keepout_copper = True     # also keepout_tracks, keepout_vias, keepout_pads, keepout_footprints
board.create_items([pour, keepout])
```

A new `Zone` carries KiCad's defaults (0.25 mm minimum width, islands removed). After
`refill_zones()`, `zone.filled_polygons` is `{layer: [PolygonWithHoles]}`: the copper as
filled, for checks.

## Outline, graphics, text

```python
edge = BoardPolygon()                                # the outline: a closed polygon on Edge.Cuts
edge.polygons.append(rectangle(40, 30))
edge.layer = BoardLayer.BL_Edge_Cuts
edge.attributes.stroke.width = from_mm(0.1)

line = BoardSegment()                                # silkscreen line; BoardCircle, BoardArc, BoardRectangle, BoardBezier likewise
line.start, line.end = Vector2.from_xy_mm(-5, 3), Vector2.from_xy_mm(5, 3)
line.layer, line.attributes.stroke.width = BoardLayer.BL_F_SilkS, from_mm(0.15)

label = BoardText()
label.value, label.position, label.layer = "blinky v1", Vector2.from_xy_mm(0, -4), BoardLayer.BL_F_SilkS
label.attributes.size = Vector2.from_xy_mm(1, 1)     # 1 mm high; attributes.stroke_width, bold, mirrored, angle...
label.attributes.stroke_width = from_mm(0.15)
board.create_items([edge, line, label])
```

A cutout is a hole in the outline polygon (`polygon.add_hole(...)`) or a second closed shape
on `BL_Edge_Cuts`. A mounting hole is a footprint from KiCad's `MountingHole` library, so
it carries its pad, clearance and courtyard.

## Design rules

```python
rules = board.get_design_rules().rules               # BoardDesignRules
c = rules.constraints                                # MinimumConstraints, every value in nm
c.min_clearance = from_mm(0.15)
c.min_track_width = from_mm(0.15)
c.min_via_size, c.min_through_drill = from_mm(0.5), from_mm(0.3)
c.min_via_annular_width = from_mm(0.13)
c.copper_edge_clearance = from_mm(0.3)
c.hole_clearance, c.hole_to_hole_min = from_mm(0.25), from_mm(0.5)
c.silk_clearance = from_mm(0.15)
c.min_silk_text_height, c.min_silk_text_thickness = from_mm(1.0), from_mm(0.15)
board.set_design_rules(rules)                        # persists into the .kicad_pro; what cadgen pcb drc checks against
```

`rules` also carries `predefined_sizes` (the editor's track and via presets),
`solder_mask_paste` (mask expansion, minimum web) and `severities`. Set the numbers to the
fab's limits ([manufacturing](manufacturing.md)).

## Custom rules

KiCad's rule language, for what the board-wide numbers cannot scope: one net, one footprint's
pads, one layer. The file is `<board>.kicad_dru` beside the board, hand-written in KiCad's text
([checks](checks.md) holds the catalogue in that form). The API writes the same file from objects,
for a script that would rather declare them in Python, and replaces a hand-written one:

```python
def rule(name, condition, *constraints):
    r = CustomRule()
    r.name, r.condition, r.constraints = name, condition, list(constraints)
    return r                              # also r.single_layer = BoardLayer.BL_F_Cu, r.severity = RuleSeverity.RS_WARNING

def numeric(kind, **min_opt_max):         # nm; a count for CRCT_VIA_COUNT
    constraint = CustomRuleConstraint.from_type(kind)
    constraint.numeric = MinOptMax(**min_opt_max)
    return constraint

solid = CustomRuleConstraint.from_type(CustomRuleConstraintType.CRCT_ZONE_CONNECTION)
solid.zone_connection = ZoneConnectionStyle.ZCS_FULL
no_vias = CustomRuleConstraint.from_type(CustomRuleConstraintType.CRCT_DISALLOW)
no_vias.disallow.types = [CustomRuleDisallowType.CRDT_THROUGH_VIAS]
response = board.set_custom_design_rules([                       # replaces the set; writes <board>.kicad_dru
    rule("VBUS carries 2 A", "A.NetName == 'VBUS'", numeric(CustomRuleConstraintType.CRCT_TRACK_WIDTH, min=from_mm(0.78))),
    rule("J1 solid to pour", "A.memberOfFootprint('J1') && A.NetName == 'GND'", solid),
    rule("no via under R1", "A.intersectsCourtyard('R1')", no_vias),
])
assert response.status == CustomRulesStatus.CRS_VALID, response.error_text
```

Constraint types are `CRCT_` plus the rule keyword (`CRCT_TRACK_WIDTH`, `CRCT_VIA_COUNT`,
`CRCT_LENGTH`, `CRCT_SKEW` with `CRCO_SKEW_WITHIN_DIFF_PAIRS` appended to `.proto.options`,
`CRCT_DIFF_PAIR_GAP`, `CRCT_MAX_UNCOUPLED` for `diff_pair_uncoupled`, `CRCT_HOLE_TO_HOLE`,
`CRCT_EDGE_CLEARANCE`, `CRCT_SILK_CLEARANCE`, `CRCT_COURTYARD_CLEARANCE`, `CRCT_CREEPAGE`,
`CRCT_THERMAL_RELIEF_GAP`, `CRCT_THERMAL_SPOKE_WIDTH`, `CRCT_ASSERTION` with
`.assertion_expression`, ...). KiCad parses the text it is about to write: an invalid condition
or an unsupported type refuses the whole set, `response.status` is `CRS_INVALID` and
`error_text` says where. On today's nightly that refusal includes the API's own `track_angle`
(`90deg`) and `min_resolved_spokes` (`(min 2)`), and `return_path`, `stub_length` and
`net_chain_length` have no type: those rules go in a hand-written `<board>.kicad_dru`
([checks](checks.md#declaring-rules)), which a build keeps as long as the script sets no rules
through the API.

## Net classes

Net classes live in the project (`.kicad_pro`): a DRC input (clearance and minimum width per
class) and the editor's defaults. They set nothing on a track the script draws, so give every
`Track` and `Via` its size; use a class to make the DRC hold a whole net to it.

```python
from cadgen.kipy.proto.common.types.project_settings_pb2 import NetClass as NetClassProto

project = board.get_project()
power = NetClass(NetClassProto(name="Power"))
power.track_width, power.clearance = from_mm(0.5), from_mm(0.2)
project.set_net_classes([power])                     # merged into the project's classes (Default stays)

vbus = NetClassAssignment()
vbus.net, vbus.netclasses = "VBUS", ["Power"]
project.set_net_class_assignments(NetClassAssignments([vbus]))

board.get_netclass_for_nets([Net(name="VBUS")])      # {"VBUS": the effective class}
board.get_nets("Power")                              # the nets in a class
```

`NetClassPatternAssignment` (`.pattern`, `.netclass`) assigns by wildcard (`"V*"`). On
today's kicad-python, `via_diameter`/`via_drill` cannot be set on a class made this way (the
setter fails on an empty via stack): size vias directly, or hold them with a
`CRCT_VIA_DIAMETER` custom rule.

## Exports

Every export is one of KiCad's own jobs, run by the server on the **saved** board file: a
job on a board that was never saved fails with `Failed to load board`, so a function that exports
refills and saves first (the decorator refills and saves again afterwards, cheaply):

```python
board.refill_zones()
board.save()
out = "/work/boards/fab"                             # directories for the multi-file jobs
result = board.export_gerbers(out, create_gerber_job_file=True)   # every layer, Gerber X2, Protel extensions
assert result.succeeded, result.message
board.export_drill(out)                              # Excellon, PTH and NPTH combined: <name>.drl
settings = PositionExportSettings()
settings.use_drill_place_file_origin, settings.exclude_dnp = True, True
board.export_position("/work/boards/fab/blinky.pos.csv", settings)    # <name>.pos-top.csv and -bottom.csv (single_file=True for one)
board.export_stats("/work/boards/fab/blinky.stats.json", format=StatsOutputFormat.SOF_JSON)

plot = PlotSettings()                                # the picture jobs need the layers named
plot.layers = [BoardLayer.BL_F_Cu, BoardLayer.BL_B_Cu, BoardLayer.BL_F_SilkS, BoardLayer.BL_Edge_Cuts]
board.export_svg("/work/boards/fab/blinky.svg", plot, fit_page_to_board=True)
board.export_png("/work/boards/fab/blinky.png", plot, dpi=300)
```

Each job returns a `JobResult` (`.succeeded`, `.output_paths`, `.message`): read `.succeeded`,
a failed job raises nothing. The other jobs are `export_pdf`, `export_dxf`, `export_ps`,
`export_3d` (`Export3DSettings`: `Board3DFormat.B3D_STEP`, `B3D_GLB`, ...), `export_render`,
`export_gencad`, `export_ipc2581`, `export_ipc_d356`, `export_odb`. What a fab needs and how
to hand it over: [manufacturing](manufacturing.md).

## Browsing libraries

Outside the decorator, the same server answers what a library holds and what a footprint
looks like. A document must be open for the project's `fp-lib-table` to be read, so name a
board path in the folder that holds the table; nothing is written unless `save()` is called.

```python
import os, tempfile
from cadgen.kipy import KiCad
from cadgen.kipy.proto.common.types.base_types_pb2 import DocumentType
from cadgen.kipy.proto.common.types.library_types_pb2 import LibraryLoadStatus, LibraryType
from cadgen.kipy.util.units import to_mm
from cadgen.kicad.install import find_kicad_cli      # the kicad-cli a build uses

os.environ["KICAD_CONFIG_HOME"] = tempfile.mkdtemp() # an empty settings directory: no user library table
with KiCad(headless=True, kicad_cli_path=str(find_kicad_cli()), timeout_ms=120000) as kicad:
    doc = kicad.create_document("/work/boards/blinky.kicad_pcb", DocumentType.DOCTYPE_PCB)
    kicad.load_all_libraries([LibraryType.LT_FOOTPRINT])
    for status in kicad.wait_for_libraries([LibraryType.LT_FOOTPRINT], interval_ms=100, timeout_s=300):
        print(status.nickname, LibraryLoadStatus.Name(status.status), status.error_message)
    for lib_id in kicad.get_library_footprints(["Resistor_SMD"]):          # every footprint of a library
        print(f"{lib_id.library}:{lib_id.name}")
    footprint = kicad.get_library_footprint("Resistor_SMD:R_0603_1608Metric")
    for pad in footprint.pads:                                              # positions relative to the footprint's origin
        print(pad.number, to_mm(pad.position.x), to_mm(pad.position.y), pad.pad_type)
    kicad.close_document(doc)
```

A name no loaded library has raises `ApiError: none of the requested items were found`.
`kicad.get_version()` is the server's KiCad version. Starting a server costs about half a
second; loading a library about a third of a second each, so keep these scripts to the
libraries the board uses.
