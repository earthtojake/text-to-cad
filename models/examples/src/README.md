# examples

Every script of `models/examples/src`, on cadgen 0.8: a `@model` each, writing nothing, but
the two print parts below, which declare their files, and the import's `__main__`, which
exports the two STEPs it reads.

| Script | Files | What it is |
| --- | --- | --- |
| `l_bracket.py` | — | L-bracket with gussets and a filleted transition (`lib/part_common.safe_fillet`) |
| `electronics_enclosure_base.py` | — | Open-top enclosure with rounded corners and standoffs |
| `basic_shape_mating_test_fixture.py` | — | Seven parts and a sub-assembly seated on a base plate by build123d joints |
| `electronics_enclosure_base_import.py` | `STEP/electronics_enclosure_base.step`, `STEP/basic_shape_mating_test_fixture.step` (its `__main__` exports them) | The enclosure's and the fixture's STEP read back with `read_step` |
| `electronics_enclosure_base_drawing.py` | `PDF/electronics_enclosure_base_drawing.pdf` | **Engineering drawing** (`@eng_drawing`) of the enclosure, calling its model: three views with hidden lines and centre marks, measured dimensions, hole callouts, title block. Build the enclosure first. |
| `cam_follower_roller.py` | — | Cam follower roller with central bearing bore and rounded outer profile (Steel 4140) |
| `centrifugal_impeller.py` | — | Single solid centrifugal impeller (Aluminum 6061-T6) |
| `circular_flange.py` | — | Circular flange with a six-hole bolt circle (Steel 1018) |
| `clevis_bracket_lightening_cutouts.py` | — | Clevis bracket with lightening cutouts (Aluminum 7075-T6) |
| `cylindrical_cap.py` | — | Cylindrical cap with hollow interior, top boss, and rounded external edges (Aluminum 6061-T6) |
| `cylindrical_spacer_sleeve.py` | — | Cylindrical spacer sleeve with a central through-bore and rounded rim edges (Aluminum 6061-T6) |
| `flywheel_disk.py` | — | Flywheel disk with central bore, annular rim, and lightening holes (Steel 1018) |
| `gusset_plate.py` | — | Gusset plate with a triangular web, base holes, and softened perimeter edges (Steel A36) |
| `keyed_shaft_hub.py` | — | Keyed shaft hub with central bore, keyway slot, and bolt-hole pattern (Steel 1018) |
| `mounting_plate.py` | `STL/`, `3MF/`, `GLB/mounting_plate.*` | Mounting plate with central cutout, side slot, four corner holes, rounded edges (Aluminum 6061-T6) |
| `open_top_electronics_enclosure.py` | — | Open-top electronics enclosure with corner bosses (ABS) |
| `print_in_place_hinge.py` | — | Print-in-place barrel hinge for FDM printing: two leaves, one revolute joint (PLA) |
| `print_in_place_multi_pivot_phone_holder.py` | — | Print-in-place multi-pivot phone/tablet holder: four links, three revolute joints (PLA) |
| `pulley_wheel.py` | — | Pulley wheel with a central hub, outer groove, and circular through-bore (Aluminum 6061-T6) |
| `radial_engine_cylinder.py` | — | Radial-engine-style cylinder with cooling fins (Aluminum 6061-T6) |
| `rectangular_calibration_block.py` | — | Rectangular calibration block with four holes and a chamfered top (Steel 1018) |
| `rectangular_clamp_block.py` | — | Rectangular clamp block with a split slot and two transverse screw holes (Aluminum 6061-T6) |
| `retainer_plate.py` | — | Retainer plate with elongated slot, two circular holes, and chamfered perimeter (Steel 1018) |
| `shaft_collar.py` | — | Shaft collar with a central bore, radial set-screw hole, and chamfered faces (Steel 1018) |
| `small_enclosure_cover.py` | — | Small enclosure cover with raised rim, corner screw holes, and recessed center (ABS) |
| `spur_gear_blank.py` | `STL/`, `3MF/`, `GLB/spur_gear_blank.*` | Spur gear blank with central bore, raised hub, and simplified perimeter teeth (Brass C360) |
| `square_mounting_block.py` | — | Square mounting block with a vertical through-hole and two side clearance holes (Aluminum 6061-T6) |
| `stepped_shaft_keyway.py` | — | Stepped shaft with keyway (Steel 4140) |
| `t_slot_slider_block.py` | — | T-slot slider block with central channel, side relief cuts, and mounting holes (Aluminum 6061-T6) |

The 24 parts after the first five are the old project's, ported as they were: `@step`
became `@model`, `build123d` is imported directly, and the two that also declared STL,
3MF and GLB keep those decorators, alone: this corpus's example of declared files, a print
part whose STL, 3MF and GLB every run writes (`../STL/`, `../3MF/`, `../GLB/`, gitignored). Their shared builders are `lib/simple_model_library.py` (the
`make_*` parts) and `lib/part_common.py`, plain modules; a colour is the sRGB hex itself,
which a shape takes as it is. Each takes a catalogue material, in brackets above: a part that
authors its own colour has it restored after native material assignment; one that
does not takes the material’s explicit colour.
The two print-in-place assemblies' `AssemblyHelper` frames are build123d joints: a
`RevoluteJoint` on the bored link and a `RigidJoint` on the pinned one, on the same pin
axis, paired by their label where the links stand as printed (open flat, 0 degrees).

Materials: the L-bracket is Steel 1018 and the enclosure ABS, each drawn in the
catalogue's colour (neither authored one); the fixture takes one material on its
assembly, which every part below it takes: bead-blasted Aluminum 6061-T6,
anodised in each part's own colour (restored after native material assignment).
The imports read the STEP inputs as they are, without materials.

A run writes nothing, but the mounting plate's and the gear blank's declared files. The
import script's `__main__` exports the enclosure and the fixture to `../STEP/` (gitignored,
like every export: Git holds no CAD files) and reads them back; run it before opening either
import model, which reads those files.
Build from this folder, in any order: each script builds the models its `__main__` calls, for example

```
python l_bracket.py
python electronics_enclosure_base.py
python basic_shape_mating_test_fixture.py
python electronics_enclosure_base_import.py
python electronics_enclosure_base_drawing.py   # builds the enclosure too
```

The fixture's `AssemblyHelper` frames are build123d joints: a `RigidJoint` on
each part in its own frame and `connect_to` moving the part onto the base
(`offset=` as a second fixed joint, `<frame>:offset`, as the old helper made).

`electronics_enclosure_base_drawing.py` is cadgen's `@eng_drawing`, outside the
engine: a document over a part, run in the script's own process, never a model.
It read the STEP the enclosure wrote; it calls the enclosure's model now, which the
engine builds (a replay when current) and hands back as a shape, and takes every
dimension's constants from the model module. Its PDF (`../PDF/`, gitignored) carries no
date: an unchanged drawing writes the same bytes.

`electronics_enclosure_base_import.py` keeps the drawing's old read: `read_step` of
the enclosure's STEP, plus a read of the fixture's STEP to exercise an imported
assembly's names and colours.
