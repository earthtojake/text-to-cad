# examples models

The repo's demo-model corpus as one `$cad-project`: every part, assembly and
2D drawing is a runnable model script directly under `src/`, and every artifact
lands in a format folder at the project root (`STEP/`, `STL/`, `3MF/`, `GLB/`,
`DXF/`). Nothing here is committed except this `src/` tree, `imported/` and
`DXF/imported/` — build what you need.

```bash
python models/examples/src/mounting_plate.py     # one model
ls models/examples/src/*.py | xargs -n1 -P4 python   # the whole corpus
```

Unchanged models are no-ops, so "build if missing" and "rebuild" are the same
command. Shared helper modules live in `src/lib/` (`part_common`,
`simple_model_library`, `mx_switch_socket`, `clamp_plate_profile`,
`research_humanoid_lib`) — plain
modules, never models. Because the scripts sit directly in `src/`,
`from lib import ...` and `import <sibling_model>` both resolve with no path
setup.

Two models carry kinematics and choreography: `planetary_gear_assembly`
(mates + a `drive` coupling + `quarter_cycle`/`half_cycle` poses) and
`mars_rover_concept` (27 mates, 7 couplings, 4 poses). Their `.anim.js` clips
sit beside the scripts and are copied into the artifact sidecar at build.

A handful of models declare mesh exports so the STL/3MF/GLB doors have real
fixtures to work against; `miniature_spiral_staircase` declares a `_highres`
variant at `mesh_tolerance=4e-4` to exercise the tolerance path.

`imported/import-smoke.step` is a committed SOURCE file (the viewer launch
test's fixture), not an output. `DXF/imported/` is the same idea for drawings:
permissively licensed `.dxf` files no script here regenerates.

### Parts

| Script | Artifact | Description |
|--------|----------|-------------|
| `basic_shape_mating_test_fixture.py` | `STEP/basic_shape_mating_test_fixture.step + 3MF/basic_shape_mating_test_fixture.3mf` | Primitive-shape mating fixture (box/cone/sphere/cylinder on a base plate) |
| `cam_follower_roller.py` | `STEP/cam_follower_roller.step` | Cam follower roller with central bearing bore and rounded outer profile |
| `centrifugal_impeller.py` | `STEP/centrifugal_impeller.step` | Single solid centrifugal impeller |
| `circular_flange.py` | `STEP/circular_flange.step` | Circular flange model |
| `clevis_bracket_lightening_cutouts.py` | `STEP/clevis_bracket_lightening_cutouts.step` | Clevis bracket model |
| `cylindrical_cap.py` | `STEP/cylindrical_cap.step` | Cylindrical cap with hollow interior, top boss, and rounded external edges |
| `cylindrical_spacer_sleeve.py` | `STEP/cylindrical_spacer_sleeve.step` | Cylindrical spacer sleeve with a central through-bore and rounded rim edges |
| `electronics_enclosure_base.py` | `STEP/electronics_enclosure_base.step` | Single solid open-top electronics enclosure base |
| `flywheel_disk.py` | `STEP/flywheel_disk.step` | Flywheel disk with central bore, annular rim, and lightening holes |
| `gusset_plate.py` | `STEP/gusset_plate.step` | Gusset plate with a triangular web, base holes, and softened perimeter edges |
| `keyed_shaft_hub.py` | `STEP/keyed_shaft_hub.step` | Keyed shaft hub with central bore, keyway slot, and bolt-hole pattern |
| `l_bracket.py` | `STEP/l_bracket.step` | L-bracket model |
| `motorcycle_helmet_fidget.py` | `STEP/motorcycle_helmet_fidget.step` | Motorcycle helmet fidget with a Cherry MX switch socket |
| `motorcycle_seat_fidget.py` | `STEP/motorcycle_seat_fidget.step` | Motorcycle pillion (backseat) fidget with a Cherry MX switch socket |
| `motorcycle_shock_fidget.py` | `STEP/motorcycle_shock_fidget.step` | Motorcycle shock absorber fidget with a Cherry MX switch socket |
| `motorcycle_wheel_fidget.py` | `STEP/motorcycle_wheel_fidget.step` | Motorcycle wheel fidget with a Cherry MX switch socket |
| `mounting_plate.py` | `STEP/mounting_plate.step + STL/mounting_plate.stl, 3MF/mounting_plate.3mf, GLB/mounting_plate.glb` | Mounting plate with central circular cutout, elongated side slot, four corner holes, and rounded edges |
| `open_top_electronics_enclosure.py` | `STEP/open_top_electronics_enclosure.step` | Open-top electronics enclosure model |
| `print_in_place_hinge.py` | `STEP/print_in_place_hinge.step` | Print-in-place barrel hinge for FDM printing |
| `print_in_place_multi_pivot_phone_holder.py` | `STEP/print_in_place_multi_pivot_phone_holder.step` | Print-in-place multi-pivot holder with a phone/tablet cradle for FDM printing |
| `pulley_wheel.py` | `STEP/pulley_wheel.step` | Pulley wheel with a central hub, outer groove, and circular through-bore |
| `radial_engine_cylinder.py` | `STEP/radial_engine_cylinder.step` | Radial-engine-style cylinder model |
| `rectangular_calibration_block.py` | `STEP/rectangular_calibration_block.step` | Rectangular calibration block model |
| `rectangular_clamp_block.py` | `STEP/rectangular_clamp_block.step` | Rectangular clamp block with a split slot and two transverse screw holes |
| `research_humanoid.py` | `STEP/research_humanoid.step` | Production-realistic, adult-scale humanoid research platform; links the two hand models below |
| `research_humanoid_hand_left.py` | `STEP/research_humanoid_hand_left.step` | Its left 15-axis dexterous hand, a sub-assembly model (`lib/research_humanoid_lib.build_hand`) |
| `research_humanoid_hand_right.py` | `STEP/research_humanoid_hand_right.step` | The right hand — a mirror image, so its own model from the same factory |
| `retainer_plate.py` | `STEP/retainer_plate.step` | Retainer plate with elongated slot, two circular holes, and chamfered perimeter |
| `shaft_collar.py` | `STEP/shaft_collar.step` | Shaft collar with a central bore, radial set-screw hole, and chamfered faces |
| `small_enclosure_cover.py` | `STEP/small_enclosure_cover.step` | Small enclosure cover with raised rim, corner screw holes, and shallow recessed center |
| `spur_gear_blank.py` | `STEP/spur_gear_blank.step + STL/spur_gear_blank.stl, 3MF/spur_gear_blank.3mf, GLB/spur_gear_blank.glb` | Spur gear blank with central bore, raised hub, and simplified perimeter teeth |
| `square_mounting_block.py` | `STEP/square_mounting_block.step` | Square mounting block with a vertical through-hole and two side clearance holes |
| `stepped_shaft_keyway.py` | `STEP/stepped_shaft_keyway.step` | Stepped shaft with keyway model |
| `t_slot_slider_block.py` | `STEP/t_slot_slider_block.step` | T-slot slider block with central channel, side relief cuts, and mounting holes |

### Assemblies

| Script | Artifact | Description |
|--------|----------|-------------|
| `compact_humanoid.py` | `STEP/compact_humanoid.step` | Original 28-DOF compact humanoid research platform concept |
| `cutaway_turbofan_engine.py` | `STEP/cutaway_turbofan_engine.step` | Labeled multi-body cutaway turbofan display model |
| `flying_car.py` | `STEP/flying_car.step` | Four-rotor flying car concept |
| `lunar_rover_corner_assembly.py` | `STEP/lunar_rover_corner_assembly.step` | Lunar rover corner module: wheel, hub motor, suspension |
| `mars_rover_concept.py` | `STEP/mars_rover_concept.step` | Mars rover concept on terrain, mated + animated |
| `mechanical_iris_aperture.py` | `STEP/mechanical_iris_aperture.step` | Labeled mechanical iris aperture assembly |
| `miniature_spiral_staircase.py` | `STEP/miniature_spiral_staircase.step + STL/miniature_spiral_staircase_highres.stl, 3MF/miniature_spiral_staircase_highres.3mf, GLB/miniature_spiral_staircase_highres.glb` | Labeled miniature spiral staircase STEP compound |
| `motorcycle_shock_absorber.py` | `STEP/motorcycle_shock_absorber.step` | Motorcycle rear shock absorber (coilover damper) assembly |
| `pelican_riding_bicycle.py` | `STEP/pelican_riding_bicycle.step` | Pelican riding a bicycle (organic + mechanical mix) |
| `photo_coffee_cup.py` | `STEP/photo_coffee_cup.step` | Photo-inspired takeaway coffee cup model |
| `planetary_gear_assembly.py` | `STEP/planetary_gear_assembly.step + STL/planetary_gear_assembly.stl, 3MF/planetary_gear_assembly.3mf, GLB/planetary_gear_assembly.glb` | Labeled simplified planetary gear assembly |
| `planetary_gear_stage.py` | `STEP/planetary_gear_stage.step` | Simplified planetary gear assembly |
| `robotic_hand_end_effector.py` | `STEP/robotic_hand_end_effector.step` | Labeled cybernetic robotic hand end-effector STEP assembly |
| `sculpted_humanoid.py` | `STEP/sculpted_humanoid.step` | Sculpted full-scale humanoid research platform |
| `six_axis_industrial_robot_arm.py` | `STEP/six_axis_industrial_robot_arm.step` | Labeled six-axis industrial robot arm display assembly |
| `six_blade_open_propeller.py` | `STEP/six_blade_open_propeller.step` | Six-blade open propeller |
| `spiral_staircase.py` | `STEP/spiral_staircase.step` | Miniature spiral staircase model |

### Drawings

Small 2D `@dxf` fixtures for exercising the `dxf` skill tooling. Everything
here is intentionally simple so failures point at the tooling, not the fixture.
Written DXF bytes are a pure function of the returned geometry, so a rebuild
that changes them is a real change to report, not noise.

| Script | Artifact | Description |
|--------|----------|-------------|
| `angled_tab.py` | `DXF/angled_tab.dxf` | Plate with a corner gusset tab on a **45° bend line** |
| `cabinet_panel_drawing.py` | `DXF/cabinet_panel_drawing.dxf` | Workshop **drawing**: three views, engraved dimension callouts, title block |
| `clamp_plate.py` | `DXF/clamp_plate.dxf` | Cut profile projected from 3D topology (`lib/clamp_plate_profile.py`) |
| `gasket_plate.py` | `DXF/gasket_plate.dxf` | Rounded gasket, bolt holes, centre cutout, engraved crosshair |
| `l_bracket_flat.py` | `DXF/l_bracket_flat.dxf` | Sheet-metal flat pattern with a single bend line |
| `label_plate.py` | `DXF/label_plate.dxf` | Laser-cut label: engraved text outlines + an open score line |
| `multi_bend_test_panel.py` | `DXF/multi_bend_test_panel.dxf` | **Four bends in three orientations** on one blank |
| `u_channel_bracket.py` | `DXF/u_channel_bracket.dxf` | U-channel flat pattern with **two parallel** bend lines |

Together these cover the skill's standalone-drafting and topology-projection
workflows. `lib/clamp_plate_profile.py` is the clamp plate as a build123d
solid — a plain helper, not a `@step` model: the profile is projected from live
geometry rather than read back from a STEP artifact this project wrote (which
the `$dxf` skill forbids — the freshness gate could never say "current").

Build: `python src/<script>` per row; unchanged models are no-ops.
Imported sources: `imported/import-smoke.step` and `DXF/imported/*.dxf`
(committed, no script).

## Why the cabinet panel drawing exists

`cabinet_panel_drawing.py` is the only model here that is a **drawing document**
rather than a cut layout: three views (front elevation, plan, section A-A), the
eleven measurements a cabinetmaker needs, and a title block. It was a committed
baked file until its information was re-expressed in what `@dxf` actually emits —
geometry on layers that carry intent. The views and dowel holes are `CUT`;
everything annotative is `ENGRAVE`, so the dimension VALUES are `bd.Text`
outlines and the witness, leader, centre and shelf lines are open geometry, which
an engrave-intent layer allows. The DXF constructs the retired ezdxf generator
used — `DIMENSION` entities, ISO 128 `CENTER`/`HIDDEN` linetypes, a non-plotting
layer, `TEXT` entities — have no `@dxf` equivalent and are not reproduced; the
numbers they carried are. That generator is in git history at
`models/drawings/dxf/cabinet_panel_drawing.dxf.py`.

## Why each bend fixture exists

- `l_bracket_flat.py` — the ordinary case: one bend, edge to edge.
- `u_channel_bracket.py` — **two parallel** bends, so the web stays flat and
  both flanges fold the same way. Covers bend ordering and a segment bounded by
  a bend on both sides, which the single-bend L-bracket cannot exercise.
- `angled_tab.py` — arbitrary bend-line ORIENTATION. Every other bend fixture's
  lines are vertical, so a fold that only handles constant-X axes renders this
  one wrong.
- `multi_bend_test_panel.py` — the fold model itself: five faces, four hinges, a
  tree. Two parallel verticals, a horizontal tab fold whose line is a *chord*
  (it spans only the tab, and the same infinite line continues along the
  panel's bottom edge where no bend runs), and a 45° corner fold. This is the
  one that fails when a fold cuts by its infinite line instead of its own
  segment.

## `DXF/imported/` — committed inputs

Raw DXF files no script regenerates, committed via Git LFS and never rebuilt.
They cover R12 (AC1009) and R2013+ (AC1027) flavors and a spread of entity
types.

**Every file here encloses at least one closed area.** That is the selection
rule, and it exists because the viewer renders a DXF by extruding its closed cut
contours into a 3D flat pattern — a drawing with no area has nothing to extrude
and nothing to show.

Several of these deliberately mix closed cut profiles with open annotation
(dimension extension lines, stray arcs), because real drawings do — layer
intent is what separates the two, not the entity type.

From [skymakerolof/dxf](https://github.com/skymakerolof/dxf) (`test/resources`,
MIT):

- `alu_extrusion_profile.dxf` — an aluminium extrusion cross-section: nine
  nested closed LWPOLYLINE chambers, two HATCH regions, and seven DIMENSION
  annotations across several layers and colors. The most realistic engineering
  part in the set. Upstream name: `alu-profile.dxf`.
- `plate_four_holes.dxf` — an OpenSCAD 2D export: a plate outline with four
  circular holes, written as 452 individual LINE segments that chain into
  closed loops with no dangling ends. Exercises the contour walk hard, since
  not one entity is closed on its own. Upstream name: `openscad_export.dxf`.
- `square_and_circle.dxf` — a square outline with an inscribed circle on
  separate colored layers; the circle is tangent to the square, a useful
  near-degenerate case for contour resolution. Upstream name:
  `squareandcircle.dxf`.
- `block_square_in_circle.dxf` — a circle plus an INSERT whose block holds a
  closed square, and a second standalone circle. Small, and the simplest file
  here that requires block expansion. Upstream name: `accumulatortest.dxf`.
- `circles_ellipses_arcs.dxf` — two closed ELLIPSE entities and a CIRCLE
  alongside two open ARCs. Closed-area ellipse coverage with open geometry
  mixed in. Upstream name: `circlesellipsesarcs.dxf`.

From [gdsestimating/dxf-parser](https://github.com/gdsestimating/dxf-parser)
(`test/data`, MIT):

- `laser_text_outlines.dxf` — the word "LaserWeb" as twelve legacy POLYLINE
  letter outlines, including the counters inside `a`, `e` and `b`. Closed by
  coincident first/last vertices rather than the closed flag, so it also covers
  that distinction. A genuine laser-cut profile. Upstream name: `polylines.dxf`.
- `overlapping_ellipses.dxf` — two full closed ELLIPSE entities that overlap.
  Minimal ellipse coverage. Upstream name: `ellipse.dxf`.

From [mozman/ezdxf](https://github.com/mozman/ezdxf) (`examples_dxf`, MIT):

- `nested_hole_shapes.dxf` — eight shapes with nested holes: rectangles inside
  rectangles, notched profiles, and pentagons, as sixteen closed LWPOLYLINE
  boundaries with ten HATCH fills. The best coverage of holes and nesting
  depth. Upstream name: `hatches_1.dxf`.

Authored in-repo (committed because no script here can rebuild them):

- `bracket_inches.dxf` — a small bracket profile authored with `$INSUNITS = 1`
  (inches). The units fixture: the parser scales every coordinate to
  millimetres, and a drawing baked before that support existed came out 25.4×
  too small. Its LWPOLYLINEs omit the `AcDbPolyline` subclass marker, so
  ezdxf's strict reader refuses it while cadgen's own parser accepts it — which
  is itself the point of keeping it.

`DIMENSION`-entity coverage lives in `alu_extrusion_profile.dxf`. DXF `TEXT` and
`MTEXT` entities are covered by unit fixtures in
`packages/cadgen-js/src/lib/dxf/parseDxf.test.js`, not by a file here — the
cabinet panel drawing that used to hold that coverage is now generated, as
`src/cabinet_panel_drawing.py`.

Validate any file here post-hoc with the drawing checks (there is no
`--validate` flag; a clean drawing reports no findings):

```python
from cadgen.drawing_checks import validate_dxf_file

print([finding.render() for finding in validate_dxf_file("DXF/gasket_plate.dxf")])
```
