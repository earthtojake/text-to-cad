# thang010146 mechanism demos

Mechanism assemblies inspired by the YouTube channel
[thang010146](https://www.youtube.com/@thang010146/videos). Original mechanism
design, animation, and downloadable source files are credited to
`thang010146`.

A standard cad-project (`$cad-project`): authored code in `src/`, raw outputs
in `STEP/`, vendor documents in `STEP/imported/`.

```
thang010146/
  src/                    # authored: one @step wrapper per mechanism
    README.md             #   the model catalog
    gear_rack_gripper.py
  STEP/
    gear_rack_gripper.step        # generated (gitignored) + its .step.json sidecar
    gear_rack_gripper.step.js     # the render module beside it: the clip (authored, committed)
    imported/
      gear_rack_gripper.step      # the VENDOR document (committed; no code makes it)
  tmp/                    # snapshots and other review renders (gitignored)
```

The shape is never ours — every model script is a `cadgen.read_step` of the
vendor document re-exported under `out=`, so the geometry survives the trip
unchanged and the artifact is regenerable from a code-only checkout plus the
imported sources. What the script adds is the ANNOTATION, kept as authored code
so an edit is one `python src/<name>.py`.

Every mechanism kept here is a CLOSED-LOOP linkage. cadgen's mates evaluate
pure forward kinematics over a tree, so each model splits its motion the same
way:

- **Kinematics** (the script's `kinematics=` dict) declares the real joints, any
  exactly-linear gearing as a `couplings` entry, and named `poses` — each pose
  is the loop SOLVED at one configuration, so every preset is geometrically
  consistent even though no solver runs at view time.
- **Animation** (`src/<name>.anim.js`, whose text is copied into the sidecar)
  carries the reference loop: the branch switching, rolling contacts and
  slider-crank arithmetic a mate tree cannot express.

Zero is the artifact as written — every model's rest state is its imported
placement.

## Sources

| Mechanism | Imported document | Source |
|---|---|---|
| 180° flip mechanism | `STEP/imported/180_degree_flip_mechanism.step` | [Video](https://www.youtube.com/watch?v=IGexfslM_5Y), [STEP archive](https://www.mediafire.com/file/pcjk004x96r6ibu/180FlipMechanismSTEP.zip/file) |
| Adjustable height table 2 | `STEP/imported/adjustable_height_table_2.step` | [Video](https://www.youtube.com/watch?v=c30g2UszMws), [STEP archive](https://www.mediafire.com/file/ulf0n6zbbp1veo4/TableAdjustHeight2STEP.zip/file) |
| Robot gripper, gear-rack drive | `STEP/imported/gear_rack_gripper.step` | [Video](https://www.youtube.com/watch?v=CP5q6YxyeQ8), user upload `RobotGripperGearRackSTEP.zip` |

See `src/README.md` for what each script builds and which DOFs, poses, and clip
it declares. Extracted source archives, Inventor files, SDF working files,
videos, and intermediate generation scripts are intentionally omitted from this
fixture bundle.

## Building and reviewing

```bash
for f in src/*.py; do python "$f"; done          # unchanged models are no-ops
cadgen step inspect refs STEP/gear_rack_gripper.step --facts
cadgen step snapshot STEP/gear_rack_gripper.step tmp/open.png --kinematics open
```

Motion review is interactive: open the CAD Viewer on `models/` and pick the
mechanism, then scrub its clip or drag the pose sliders.

Editing kinematics or the clip and rebuilding refreshes the sidecar; the STEP
itself is re-emitted from the same imported bytes, so the geometry is stable
across annotation edits. The gripper's vendor document carries no root
assembly name of its own, so its tree root renders as the XCAF placeholder
`=>[0:1:1:1]` — inherited from the source file, not introduced here.
