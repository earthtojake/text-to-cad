# Tom CAD models (rev4), on cadgen 0.8

A copy of `src/` from the tom-cad repository as committed on its `main` branch
(`git -C <tom-cad> archive main src`, commit 7f79c52), ported to cadgen 0.8.
`tom.py` builds the production arm, Tom rev4: shoulder yaw, shoulder pitch, elbow
pitch, elbow roll, wrist pitch, wrist yaw and the gripper jaw.

```text
src/
  tom.py            the model, `@model` (`cadgen export <id> STEP/tom.step` writes its STEP)
  rev3_parts.py     Tom rev3's eight parts the tom2 stage reads: a model each, and their xbf export
  stages/           rev4 derivation chain: tom2, tom2_side_mounted_elbow, tom2_symmetric_yokes
                    are @memo stages tom calls; the other stages are plain functions
  base/             common_base_plate (@memo part), legacy/base_clamp (rev3 clamp datums)
  camera/           camera_payload (@memo part): Innomaker U20CAM + M2 screws/nuts
  common/           gripper_frame (@memo part of the tom2 stage)
  end_effector/     gripper datums and the servo6 gripper/camera factories the stages use
  hardware/         screws, nuts, standoffs (read pinned STEP/imported/hardware)
  purchased/        readers for pinned vendor STEP (servo, Pi 5, HAT, camera)
  lib/              shared factories and the revision layers tom.py applies
  shoulder_yaw_*.py rev3 yoke/bracket datums the stages still read
```

## The vendor inputs (not committed)

The model reads 139 MB of vendor and recovered STEP and xbf from `STEP/imported/`, resolved
relative to this model's folder (`Path(__file__).resolve().parents[2] / "STEP" /
"imported"`, `VENDOR_DIR`). They are tom-cad's read-only data and are never committed
here (`models/tom/STEP/` is gitignored; tom-cad's copy is 536 MB). Before the first build, put a copy beside
`src/`, from `models/tom`:

```
mkdir -p STEP
cp -c -R /path/to/tom-cad/STEP/imported STEP/imported   # an APFS clone; plain cp -R elsewhere
```

(tom-cad keeps them in Git LFS: check it out with LFS so the files are the STEP data, not
pointers.) Then extract the parts of Tom rev3 the build uses into the copy
(`STEP/imported/parts/`, below; a copy, not a symlink to tom-cad's folder, which this would
write into), `python src/rev3_parts.py`, and make it read-only as in tom-cad: `chmod -R a-w
STEP/imported`.

### Tom rev3's parts

`stages/tom2.py` derives rev4 from Tom rev3's production arm,
`recovered/tom_rev3/tom.step` (354 MB). It does not read that file: the eight occurrences it
uses are extracted once, each to `STEP/imported/parts/<occurrence>.xbf`, and read with
`read_xbf` into one dict, `rev3`, so their elements are named `arm_with_inline_wrist.rev3.N`
and a servo's details stay one prototype across the parts that carry a servo. Each is a
model of its own in `rev3_parts.py`, a `@model` that reads `tom.step` (`read_step`) and
returns that occurrence at its own frame, by the labels `cadgen inspect` names
(`base_link/shoulder_yaw_servo`, `base_link/m8_thumbscrew`, `shoulder_yaw_assembly`,
`shoulder_pitch_assembly/shoulder_pitch_assembly_screws`, `upper_arm_assembly`,
`elbow_assembly`, `forearm_assembly`, `gripper/gripper_screws`); running the script exports
each to its xbf (`export(part, path)`): the conversion of a vendor STEP, made once, and this
corpus's example of an xbf handed to another model. The first read parses the STEP (about
40 s), and each part's export takes about a minute. Regenerated 2026-10-23, the eight files
match the ones the retired `cadgen export --part` wrote, part for part: the same tree,
labels, placements, face counts, bounding boxes and colours.

Every one of them stands at the arm's origin in `tom.step`, so each subtree at its own
frame leaves its parts where they were. What the stage never used is
never read: the Pi HAT stack, its carrier and hardware, the shoulder pitch yoke, the
gripper's frame, servo and claws, and the camera assembly. The stage still reads the arm's
kinematics sidecar, `recovered/tom_rev3/tom.step.json`.

## Build

From `models/tom`, with `src` on `PYTHONPATH` (the stages import `lib`, `purchased`, ...
as top-level packages):

```
python src/tom.py                                  # prints the arm's id: and view:
cadgen snapshot "$ID" tom.png
cadgen snapshot "$ID" rest.png --pose rest
cadgen export "$ID" GLB/tom.glb                    # the three clips
```

A run writes nothing. A cold build takes under two minutes (107 s on 2026-10-21) and its
worker holds about 1.9 GB after; a second build of the unchanged model replays from the
worker's memory (1 s).

## What the port changed

- `from cadgen import ...` -> `build123d`, `cadgen` (`model`, `memo`, `read_xbf`, `read_step`);
  `@step(out='…/STEP/x.step', kinematics=…, animation=…)` -> `@model` on `tom` alone
  (`cadgen export` writes the STEP from its document). The six functions `tom`
  reaches that were their own models -- the stages `tom2`, `tom2_side_mounted_elbow` and
  `tom2_symmetric_yokes`, and the parts `gripper_frame`, `camera_payload` and
  `common_base_plate` -- are `@memo`: one document, and an edit to the root (its layout
  layers in `lib/`) replays the whole stage chain; each of the six holds seconds of
  kernel work, which is what earns a `@memo` (1.3-3 s per edit; see "When to use
  `@memo`" in `models/README.md`). The stages `tom` does not call
  (`tom2_500mm`, `tom2_600mm_solid`, `diagonal_lightning_current`, `legacy/base_clamp`)
  are plain functions: their helpers are what the root reads. The `purchased/` and
  `hardware/` readers stay plain: each is one `read_step`, which the kernel memo already
  holds.
- Mates: the revision layers compute the arm's kinematics as typed mates, which the build
  also reads as data (`lib/joint_zero.py` poses the arm at joint zero by their axes;
  `lib/joint_limits.py` audits their ranges). `cadgen.revolute`/`fastened` are replaced by the
  same records in `lib/mates.py`, and `lib/joints.py` turns the final list into build123d
  joints on the built occurrences: a `RevoluteJoint` (with the audited range) on the parent and
  a `RigidJoint` on the child per revolute mate, a `RigidJoint` pair per fastened mate, each in
  its part's own frame, placed with `connect_to` at the as-built pose. build123d's `connect_to`
  composes local locations, so where parent and child sit in different compounds it would move
  the child: there the joints are authored and the child keeps its pose (the build log lists
  those mates as `unplaced`). Each joint is named after its mate (`shoulderYaw` ...
  `gripperJaw`) and reads from joint zero, the old mates' convention: posing one alone turns
  exactly the parts the old clips rotated, by a right-handed turn about the mate's axis.
- Poses: the mates' presets (`poses`, from joint zero) are configurations of `tom`: `zero`
  (every joint 0: the as-built pose, kept because the old dict named every joint), `rest` (the
  folded rest: shoulder pitch +90, elbow pitch -90), `reach` and `packed`.
- The stages' own `kinematics=` blocks were the mechanisms of their own STEP models. Those
  stages are `@memo` stages (`tom2`, `tom2_side_mounted_elbow`, `tom2_symmetric_yokes`) or
  plain functions (`tom2_500mm`, `tom2_600mm_solid`) now: their results are stock `tom`
  re-places, never a document, so there is no document for a mechanism of theirs to live in.
  Their kinematics functions stay as data, the chain each revision layer derives the next
  one's mates from (`lib/current_arm_parts.configuration`), and `tom`'s final mates are the
  joints. A stage's own poses and limits are read by nothing but that chain.
- Clips: the three clips are motions of `tom` with their old names and durations (they
  looped; a motion carries no loop, AP242 having none, and a player repeats a clip; each
  ends on the pose it starts from): `showcase` 23.4 s, `wrist` 15.2 s and `approach` 28.65 s. Their beat
  table, control/ik/showcase.py's validated performances, is committed data again
  (`lib/showcase_keys.json`, unchanged), and `lib/tom_showcase.py` plays it as the old page
  did: a function of time over the seven joints (the table's URDF names map to the mates'
  by `MATES`), smoothstep between keys or linear into a key marked so, the breathing drift on
  top, wrapped at the duration. It checks the table against the audited limits, keys plus
  breath, as the old module did. The old clips were keyed, but one motion has one ease and no
  drift, so a waypoint motion could not say the mixed eases and the breath; a function can.
  Its values match the old page's to 1e-12 deg over 2001 samples a clip, and the document's
  samples of it stay within 0.09 deg (the engine samples a function to about 1e-3 rad; the
  linear keys' kinks are where it is furthest). The clips' labels and descriptions stay in
  `CLIPS` (the engine has no clip label). The pinned occurrence ids the old clips addressed,
  and their check, stay.
- Materials: `lib/materials.py`'s finishes are `Material` values set on the parts at the end
  of the build (`apply_materials`), each the catalogue's entry in its finish's look (`.but`):
  the sheet is Aluminum 5052-H32, the standoffs Brass C360, the nuts Stainless 304 and the
  12.9 black-oxide screws Steel 4140, matched by the finish colours the parts already carry.
  The vendor boards (the camera's PCB, the bus-servo driver HAT's) take the board finish, FR4,
  by the labels their files give them; the other board finishes are defined but assigned to
  nothing, as before.
- `cadgen.color.srgb("#…")` -> the hex itself, which a shape takes as it is; `cadgen.flatten` -> a copy in `lib/flatten.py`
  (only `lib/flat_project.py` imports it).
