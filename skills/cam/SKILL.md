---
name: cam
description: Turn a saved STEP or xbf part into 3-axis CNC toolpaths and G-code with cadgen, planned and posted by the user's own FreeCAD (1.1 or newer, headless), then checked against the part for reach, gouges and rapids into the stock. Facing, profiling, pocketing, adaptive clearing and drilling on a CNC mill or router, posted for GRBL, LinuxCNC, Mach3/Mach4, Fanuc, Centroid, UCCNC or Smoothieware. Use when the user asks to mill, drill or rout a part, for CAM, toolpaths, feeds and speeds, or G-code for a CNC mill or router. Never sends G-code to a machine.
license: MIT
---

# CAM: toolpaths and G-code from a saved part

Provenance: maintained in [earthtojake/text-to-cad](https://github.com/earthtojake/text-to-cad).
Use the installed local skill files as the runtime source of truth; the repository link is only for
provenance and release review.

You write a small job file (machine, material, stock, tools, setups and their operations). `cadgen
cam plan` has the user's FreeCAD plan each setup's toolpaths and post them for the named
controller, checks every move against the part, and writes `<part>.cam.glb` (the part, the stock
and the toolpaths, with the verdict) and, when nothing is an error, the G-code beside the part.

Modelling the part is `$cad`; this skill reads a saved `.step`, `.stp` or `.xbf`. Reviewing whether
a design can be machined well is `$dfm`. 3D printing is `$gcode`.

## What it does not do

3-axis milling and drilling only, the tool always coming straight down Z, from the top (`+Z`) or
with the part turned over (`-Z`). There is no turning (lathe), laser, plasma, waterjet, wire EDM,
4th-axis, 3+2 indexed or 5-axis work, no 3D surface finishing (parallel, waterline, scallop), no
chamfering, engraving, thread milling or tapping, no tabs, no fixture or clamp checks, and no DXF
input. When the user asks for one of these, say "That is not in this version." Do not stand an
operation below in for it without saying what it leaves uncut.

## Setup

Run cadgen through the `cadgen` command its installation writes, so this skill's commands
share one installation, and its engine server, with the CAD app's:

- `cadgen` below means `cadgen +0.8.3` (`~/.local/bin/cadgen +0.8.3` where `~/.local/bin` is not on your PATH)
- `python` below means `cadgen +0.8.3 run`

If `cadgen` is not on your PATH, or it says 0.8.3 is not installed, run
`uvx --no-config --managed-python --python 3.13 --from cadgen==0.8.3 cadgen doctor` once,
outside any sandbox or with its permission: it installs cadgen, registers it, writes the
`cadgen` command and starts the engine. With the CAD app's server running, nothing else
needs the sandbox's permission: it starts the engine and holds it. Without it, a sandboxed
shell cannot start the engine; when a command says no engine is running, run `cadgen server`
outside the sandbox once.

`cadgen cam` reads its part from the file itself and needs no engine of its own.

### Install FreeCAD

`cadgen cam plan` needs FreeCAD 1.1 or newer, installed by the person; `cadgen cam features` does
not. cadgen downloads nothing and plans with nothing else. Get it from
https://www.freecad.org/downloads.php:

- macOS: drag the `.dmg`'s FreeCAD into Applications (or `~/Applications`). cadgen finds
  `FreeCAD.app/Contents/Resources/bin/freecadcmd` there.
- Windows: run the installer. cadgen finds `bin\freecadcmd.exe` in the newest `FreeCAD *` folder
  under Program Files, or under `%LOCALAPPDATA%\Programs` for a one-user install.
- Linux: a distribution or snap package (`/usr/bin/freecadcmd`, `/usr/local/bin/freecadcmd`,
  `/snap/bin/freecad.cmd`), or the AppImage unpacked with `--appimage-extract` and
  `CADGEN_FREECAD` set to its `squashfs-root/usr/bin/freecadcmd`.

Anywhere else, set `CADGEN_FREECAD` to the `freecadcmd` program
(`CADGEN_FREECAD=/opt/freecad/bin/freecadcmd`). cadgen tries `CADGEN_FREECAD`, then `freecadcmd`
or `FreeCADCmd` on PATH, then the places above. A missing or older FreeCAD stops the plan with an
error that says how to install it, and nothing is written: ask the user to install it, or install
it yourself with their permission, then plan again. Every result names the FreeCAD version that
planned it. FreeCAD runs in a temporary folder of its own, so a plan leaves nothing in the user's
FreeCAD settings.

Units are fixed: mm for lengths, mm/min for feeds, rev/min for spindle speed, degrees for angles.
Restate the user's numbers before you write them down (a 1/4" end mill is 6.35 mm, 30 ipm is 762
mm/min).

## Workflow

1. **Read the part.** Every job names faces by their refs.

   ```bash
   cadgen cam features part.step
   ```

   It prints the part's size, one line per face and one per hole:

   ```text
   block/face 15  flat floor at Z 17, facing +Z (a pocket floor 8 mm down, 1 island), 1469.7 mm²
   block/face 21  flat floor at Z 11, facing +Z (a pocket floor 6 mm down), 480 mm²
   hole block/face 7: Ø5 x 25 through along +Z at (-33, -23, 25)
   ```

   For an assembly pass the part, `--occurrence kit/arm` (`pin.2` for the second `pin`), here and to `plan`. A job takes a ref
   as `block/face 15`, as `face 15` on a one-part document, or as the Viewer copies it
   (`/work/part.step#block/face 15`). A model's part is its `@xbf` or `@step` output, or the file
   `cadgen export <id> part.step` writes.

2. **Ask what you cannot see.** Once, in one message, for what the user has not said:
   - **The controller.** `machine.post` is required and has no default: a dialect read by the
     wrong controller moves the machine wrongly. Ask which controller runs the machine (GRBL,
     LinuxCNC, Mach3/4, Fanuc, Centroid, UCCNC, Smoothieware); never guess it from the make.
   - **The spindle's top speed.** `machine.max_rpm` is required: a small cutter's table speed is
     past most spindles', and every operation's speed is held to it. Ask; never assume a router's.
   - The machine's travel, slowest spindle speed and feed limit (`travel_mm`, `min_rpm`,
     `max_feed_mm_min`): a 2,000 mm/min feed. Without them the plan posts the feeds table's
     travel and feeds unchecked.
   - **The tools.** Nothing about a tool is assumed: each one's T number (`number`), diameter,
     flute length and stickout, an end mill's flutes and shank diameter, a bull nose's corner
     radius and a drill's point angle are required. The program loads the tool by its number,
     every cut is held to its flutes, its feed is worked out from their count, FreeCAD models it
     from its stickout and shank, and a drill's point sets how far past a through hole's bottom
     it drills. Ask for the tools they own, as their tool table has them; with none, propose the
     fewest that fit and ask before planning with them. Never fill one of these in yourself.
   - The material (6061, not "aluminium"), how the part is held, and which features are
     critical.

3. **Write the job** as `part.cam.json` beside the part. Every key is in
   [job-file.md](references/job-file.md).

   ```json
   {
     "machine": {"post": "grbl", "travel_mm": [300, 300, 80], "max_rpm": 24000,
                 "max_feed_mm_min": 2500},
     "material": "aluminum-6061",
     "stock": {"margin_mm": [3, 3, 1]},
     "tools": [
       {"id": "T1", "type": "flat", "number": 1, "diameter_mm": 6, "flutes": 3, "flute_length_mm": 20,
        "stickout_mm": 30, "shank_diameter_mm": 6},
       {"id": "T2", "type": "drill", "number": 2, "diameter_mm": 5, "flute_length_mm": 40, "stickout_mm": 55,
        "point_angle": 118},
       {"id": "T3", "type": "flat", "number": 3, "diameter_mm": 10, "flutes": 3, "flute_length_mm": 32,
        "stickout_mm": 45, "shank_diameter_mm": 10}
     ],
     "setups": [
       {"id": "top", "orientation": "+Z", "origin": "stock-top-center", "operations": [
         {"op": "face", "tool": "T1"},
         {"op": "pocket", "tool": "T1", "faces": ["face 15"]},
         {"op": "pocket", "tool": "T1", "faces": ["face 21"]},
         {"op": "drill", "tool": "T2", "faces": ["face 7", "face 8", "face 9", "face 14"], "peck_mm": 2},
         {"op": "profile", "tool": "T3", "side": "outside", "through_mm": 0.5}
       ]}
     ]
   }
   ```

   The stock is the part's bounding box grown by `margin_mm` (x and y on each side, z over the
   top); its bottom is the part's bottom, on the table. Plan like a machinist: one setup per way
   the part is held; face, rough (`adaptive` with `leave_mm`), finish, then drill, and cut the
   outline free last; group each tool's operations together; use the shortest tool that reaches
   and the largest that fits.

4. **Plan.**

   ```bash
   cadgen cam plan part.step --job part.cam.json
   ```

   It prints the headline (`Ready to cut · 42 min · 3 tools` or `2 to fix · ...`), one line per
   operation (tool, rpm, feed, time), the files written, one `assumed:` line per value the job
   left out, then the findings, errors first. `--json` gives the same as one JSON object;
   `--out-dir DIR` writes elsewhere; `--verbose` times each stage. A job that cannot run at all
   (an unknown key, a missing face, no FreeCAD) is `not planned:` with one error that says what
   to change, exits 1 and writes nothing. A plan with errors exits 0: read the verdict, not the
   exit code.

5. **Read the verdict and fix the job.** "Ready to cut" means no check found an error. "N to fix"
   writes the GLB, to show where, and no G-code (`G-code not written: fix N errors first`); any
   G-code an earlier plan of the part posted is removed, so no stale program stands beside it.
   Fix each error in the job ([The checks](#the-checks)), never by changing the part unless the
   user asks, and plan again until it is ready. Then read the warnings.

6. **Show it** with `$cad` (its Show the model step): `part.cam.glb` shows the part, the stock
   and every setup's feeds and rapids.

7. **Hand over the G-code** ([Report](#report)).

## The operations

| `op` | Cuts | `faces` | Tools | Its own keys (default) |
| --- | --- | --- | --- | --- |
| `face` | The stock's top down to the part's top | Optional: flat faces facing the tool; left out, the part's top faces. Cuts down to the highest one named | `flat`, `ball`, `bull` | `stepdown_mm`, `stepover` (0.4) |
| `profile` | Around the part's outline, or along the faces named: with `side: "inside"` and a through bore's or a slot's walls named, it cuts them out. Down to the lowest face named (a blind feature's floor), or `through_mm` past the part's bottom where the faces reach it (always, for the outline) | Optional: the walls to run along; `outside` also takes a flat face, for its outline. `inside` takes a pocket's walls or its floor (walled all round, nothing opening in it), which stands for those walls and the plan names them; any other flat face is refused (`not_facing`), naming its walls | `flat`, `ball`, `bull` | `side` (`outside`, `inside`), `through_mm` (0), `stepdown_mm`, `leave_mm` (0) |
| `pocket` | A flat-floored pocket, around its islands | Required: floors at one height, facing the tool | `flat`, `ball`, `bull` | `stepdown_mm`, `stepover` (0.4), `leave_mm` (0) |
| `adaptive` | The same area as `pocket`, at a constant tool load: for roughing | Required: floors at one height | `flat`, `ball`, `bull` | `stepdown_mm`, `stepover` (0.15), `leave_mm` (0) |
| `drill` | Holes, to their depth (a through hole `through_mm` past its exit plus the drill's point) | Required: any face of each hole (its wall, its counterbore's wall or shoulder, its floor), as `cam features` lists them | `drill` only | `peck_mm` (none: one plunge), `through_mm` (1) |

Every operation also takes `tool` (required), `feed`, `speed`, `plunge_mm_min`, `coolant` and
`name` ([job-file.md](references/job-file.md#operations)). `leave_mm` is the wall stock a rough
pass leaves for a finish pass after; `face` and `drill` refuse it. `stepover` is a fraction
of the tool's diameter; `stepdown_mm` defaults to a fraction of the diameter set by the material
(half in aluminium, a quarter in steel), never past the flutes. Profiling is climb milled.

- **One depth per operation.** A `pocket` or `adaptive` naming floors at different heights is
  refused, and so is a `drill` naming holes of different depths or a `profile` naming faces that
  end at different heights: give each its own operation, as the example does. A `face` cuts down
  to the highest face it names.
- **Every face named is cut.** FreeCAD leaves out what the tool does not fit (a floor, slot or
  hole narrower than it) and says nothing, so a face or hole no cutting move reaches at the
  operation's depth is an `uncut` error, and so is a floor it cut only part of what the tool fits,
  or a face a `face` operation left part of. A floor is cut where the tool comes within 0.05 mm of
  it: a ball end mill's passes leave a ridge between them (its scallop), so a ball clears a flat
  floor only at a small stepover; a flat end mill is the tool for one.
- **A profile that cuts the part free** needs `through_mm` past the bottom, into a spoilboard,
  and flutes longer than the part, the top margin and `through_mm` together. There are no tabs:
  say how the part stays put (double-sided tape, screws through waste, a vacuum table).
- **Holes** are drilled from the side they open toward in the setup, with a drill the hole's Ø
  from the `cam features` line (`drill_size` below). A counterbore is part of its hole there; the
  drill does not cut it, and nothing cuts a countersink. A blind hole is drilled to its drawn
  bottom, so a drill whose point is longer than the drawn one (a flat floor's is none) leaves the
  bottom a cone (`drill_point` below).
- **A bore or slot too wide to drill** is a `profile` with `side: "inside"` naming its walls, with
  a tool narrower than it.
- **A material that is not in the feeds table** needs `drill_mm_per_rev` for a job that drills;
  without it the job is refused.

## The checks

FreeCAD plans what it is asked to and checks nothing against the part, so cadgen checks every
plan, before FreeCAD runs and after. An operation with a reach error is not given to FreeCAD.

| Finding | Severity | Means | Fix it in the job |
| --- | --- | --- | --- |
| `unreachable` | error | A named face lies under part of the part, seen from the tool's side, or a hole does not open toward the tool in this setup | Machine it from a setup that sees it (`orientation: "-Z"`), or name only faces the tool can reach |
| `not_facing` | error | A `face`, `pocket` or `adaptive` face is not flat and facing the tool, a `drill` face is not a face of a hole, or an inside `profile` names a flat face that is not one pocket's floor (the part's top, a floor with holes or islands in it) | Name the floor itself, or a face of the hole, as `cam features` lists them; for an inside profile, the walls the finding lists, or one pocket's floor |
| `drill_size` | error or warning | A drill is larger than its hole (an error: it cuts into the part) or smaller (a warning: it leaves the hole under size) | A drill the hole's size; for a smaller one, open the hole out after (a `pocket`, or a drill its size) |
| `drill_point` | warning | A blind hole's drill has a longer point than the drawn one (a flat floor's is none): its bottom is left a cone, short of the diameter | Say so to the user; mill the floor after with an end mill that fits, or drill with the drawn point angle |
| `too_deep` | error | The cut goes further below the stock top than the tool's flutes | A tool with longer flutes (state its `flute_length_mm`), or cut less deep from this side |
| `gouge` | error | A move brings the tool (its real flat, ball, bull nose or drill point shape) into the part | Name only faces the tool can reach, use a smaller tool, or split the floors by depth |
| `rapid_into_stock` | error | A rapid runs through stock that no move before it has cut | Raise the setup's `retract_mm` (and `clearance_mm`), or cut that material in an earlier operation |
| `empty_operation` | error | FreeCAD planned no cut for an operation | Check its faces, that the tool fits them, and for `face` that the stock has a top margin |
| `uncut` | error | No cutting move reaches a face or hole the operation names at its depth, a floor's moves cover only part of what the tool fits on it (its sharp inside corners are the tool's to leave; a ball's ridges between passes, its scallop, are not), or a `face` leaves part of the face: FreeCAD left it out | Cut it in its own operation with a tool that fits it, or leave it out; for a ridge, a smaller `stepover` or a flat end mill |
| `travel` | error | The setup's moves span more than `machine.travel_mm` | The part does not fit this machine in this setup |
| `overridden` | error | FreeCAD, recomputed, holds a spindle speed, feed, step down, peck or final depth other than the one cadgen set, so its paths and G-code follow FreeCAD's | A cadgen bug with this FreeCAD: report it, with the job; nothing is posted |
| `posted` | error | The posted program says a spindle speed (S), feed (F) or peck (Q) cadgen set for none of its operations, or moves in a work offset other than the job's: every program is read back | A cadgen bug with this FreeCAD and post: report it, with the job; nothing is posted |
| `clamped` | warning | A tool's spindle speed or feed was held to `max_rpm`, raised to `min_rpm`, or held to `max_feed_mm_min`: one warning a tool | Fine as a starting point; say so. A drill the machine would turn far too fast is refused: pocket the hole with an end mill, or give the operation's `speed` |

`job`, `freecad` and `internal_error` are the one finding of a plan that did not run: the job was
refused, FreeCAD is missing or failed, or cadgen hit a bug (report it with the part).

The gouge check sees the part from above, so it is exact for a part cut from one side and
conservative under an overhang. It knows the part, the stock box and the tools, nothing else: a
vise, clamps or a tool longer than the job says can still be hit.

## The posts and the files

`machine.post` names FreeCAD's post processor and the posted file:

| `post` | Controller | File |
| --- | --- | --- |
| `grbl` | GRBL | `part.top.nc`, or one per tool |
| `linuxcnc` | LinuxCNC | `part.top.ngc` |
| `mach3` | Mach3 and Mach4 | `part.top.tap` |
| `fanuc` | Fanuc | `part.top.nc` |
| `centroid` | Centroid | `part.top.nc` |
| `uccnc` | UCCNC | `part.top.nc` |
| `smoothie` | Smoothieware | `part.top.gcode`, or one per tool |

The file is `<part>.<setup id><ext>`, one per setup. GRBL and Smoothieware do not change tools, so
a setup with several tools posts one file per run of one tool, `part.top.1-T1.nc`,
`part.top.2-T2.nc` ...: the operator runs them in order, changing the tool and setting Z zero
before each. Each tool posts as its T number (its `number`), and two tools with one T number are
refused; the
work offset is `machine.work_offset` (`G54`). Every posted file opens with two comment lines
cadgen adds: what it is (the part, the setup, the FreeCAD version and the post) and that it is not
proven on a machine and must be air-cut or run single block first.

## Report

Hand the program over in this order, in the user's words:

- The verdict, the cycle time and the tool list, then each setup and its operations.
- The post and the controller it is for, the files in the order they run, and how the part is
  turned over and re-held between setups.
- The work zero and how to set it: `stock-top-center` on `G54` means X0 Y0 at the stock's centre
  and Z0 on its top; touch off there. The stock is the part's box plus `margin_mm`: the blank must
  be that size, its bottom on the table.
- Each tool by its T number: diameter, rpm and feed.
- Every warning, and every `assumed:` line as a question the user can answer: the rapid rate
  the cycle time is worked out at. Add anything else you assumed (the material, the tools).
- That feeds and speeds are starting points from a table, not tuned for their machine, and the
  cycle time is a lower bound (no spindle spin-up, tool changes or corner slow-downs).
- **Always:** the G-code has not been run on a machine. Say this line word for word: "Prove this
  program on the machine: single block, feed override low, in air first." Then the steps: check
  the post matches the controller; set the work offset and every tool's length (on GRBL and
  Smoothieware, zero Z with each tool's file); play the toolpaths in the Viewer and look at every rapid near the part
  and the clamps; dry-run 25-50 mm above the part; cut the first part single block with the
  overrides at 25 % and a hand on feed hold; measure it before running more. The same warning
  opens every posted file.

Never send G-code to a machine from this skill. When the user wants another controller, plan again
with another `machine.post` rather than editing the file by hand.
