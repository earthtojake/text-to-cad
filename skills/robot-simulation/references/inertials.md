# Inertials

Read this before writing or accepting a mass, a centre of mass or an inertia tensor in a URDF or an
MJCF. Never type one from intuition: every `mass`, inertial `origin` and `inertia` value is generated
from the CAD model, copied from a source (a datasheet, a measurement) or computed by a formula or a
script in the same task. A hand-written file's ledger says which, per link
([urdf-authoring.md](urdf-authoring.md#the-ledger)).

## Generated From the CAD Model

A description generated from a CAD model (`cad model export <id> robot.xml` or `.urdf`, or
`cad.mujoco.spec`) takes every link's inertial from the kernel: its parts' exact solids at their
materials' densities, with the masses the model declares ([from CAD](from-cad.md#mass)), as the
centre of mass in the link frame and the tensor about it, in kilograms and kg·m². A number in it is
changed in the model and exported again, never edited: the next two sections are cases of that, and
the formulas, scripts and ledger lines after them are for a hand-written file.

- **Weigh it before exporting.** `cad model inspect <id>` gives the total, each material's share,
  each declared mass and the parts with no material; with an assembly's label after the id, that
  assembly alone.
- **A part with no material weighs nothing.** The export warns of a link whose inertial leaves a part
  out, and of one with no inertial at all
  ([what each format makes of that](interoperability.md#one-description-two-writers)). On a moving
  link, set the materials and export again.

## A Link Drawn as One Plain Solid

A vendor's simplified STEP, or an industrial arm's shells, draws each link as one filled solid with
no motor inside, and the datasheet gives the whole arm's weight and nothing per link. One material on
every solid and `mass(arm, total_g)` split that total by the links' volumes, which puts each link's
mass where its envelope is. The hardware's mass sits mostly in its motors and gearboxes, at the
joints, so each link's centre of mass comes out too far from its joints, and its inertia off by tens
of percent on a long link. Where the actuators' masses are known (the vendor's actuator line, a
published motor) or can be estimated (an actuator of the joint's torque class from another maker's
datasheet), add each at its joint with `point_mass()`, on the part that holds its case, and keep the
total: the lumps count towards it and the solids make up the rest. Say in the model's docstring that
the total is split by volume, and which masses are listed and which estimated.

```python
ARM_G = 9000.0                                     # the datasheet: the arm's weight
ACTUATOR_G = {"shoulder": 1200.0, "elbow": 900.0}  # each joint's actuator: listed, or estimated (say which)
for joint, grams in ACTUATOR_G.items():
    case = parts[HOLDS[joint]][0]                  # the part that holds the actuator's case
    at = case.location.inverse() * bd.Location(AXES[joint][0])   # the joint's point, in the part's own frame
    point_mass(case, grams, at, name=f"{joint}_actuator")
mass(arm, ARM_G)
```

## A Printed Part

A printed part is a shell around sparse infill, not the solid its CAD models, so its material's
density overweighs it. Declare what it weighs with `mass(part, grams)`, from the first of these you
have:

1. **The part weighed on a scale**, or the maker's published weight for it.
2. **The slicer's filament weight** for that part, at the settings it is printed with.
3. **An estimate from the print settings**, computed in the model from the part's own B-rep: solid
   walls under its whole surface, and the infill's share of the rest. It treats the top and bottom
   layers as walls, so expect it to be off by 10 to 20 %, and say so in a comment beside it.

```python
PLA_G_PER_MM3, SHELL_MM, INFILL = 1.24e-3, 2 * 0.4, 0.15   # PLA, 2 walls of a 0.4 mm nozzle, 15 %


def printed_grams(part):
    shell = min(part.volume, part.area * SHELL_MM)
    return PLA_G_PER_MM3 * (shell + INFILL * (part.volume - shell))


part.material = plastics.pla()
mass(part, printed_grams(part))   # an estimate from the print settings, not weighed
```

`bd_materials`' densities, in g/cm^3: PLA 1.24, PETG 1.27, ABS 1.05, ASA 1.07. `mass()` scales the
solid uniformly, where a print carries more of its mass at its surface: the centre of mass is the
solid's and the inertia comes out a little low, which is close enough for a simulation.

## When Inertials Are Required

- **A simulation or torque control** (MuJoCo, any physics engine): every moving link needs a valid
  inertial, and MuJoCo refuses a moving body with no mass. Where a mass is unknown, use an assumed
  density, or an assumed total split by volume, and say so in the ledger
  ([what that split gets wrong](#a-link-drawn-as-one-plain-solid)).
- **Display or kinematics alone** (RViz, the viewer, MoveIt's kinematic planning): optional,
  though a simulator will want them later.
- **Frame-only links** (`base_footprint`, an optical frame, a tool point): none, and the ledger marks
  the link frame-only.

## Semantics

- **URDF**: `<inertial><origin>` is the centre of mass in the link frame, not the visual's, the
  collision's or the joint's origin. `<inertia>` is the tensor about that point, in the inertial
  frame (the link frame turned by the origin's `rpy`), in kg·m².
- **MJCF**: a body's `<inertial>` takes `pos` for the centre of mass, `mass`, and
  `fullinertia="ixx iyy izz ixy ixz iyz"`, or `diaginertia` with `quat` for the principal axes.
- A tensor a source gives about another point is moved to the centre of mass first (the
  parallel-axis theorem), or its mass properties are exported again about the centre of mass.
- A placeholder inertial, only where the person asked for a scaffold, is labelled as one
  ([guardrails.md](guardrails.md#placeholder-policy)).

## Closed-Form Formulas (solid, uniform density)

Mass `m` in kg and dimensions in metres give the tensor about the centre of mass, in the shape's own
axes:

- Box `x × y × z`: `ixx = m(y² + z²)/12`, `iyy = m(x² + z²)/12`, `izz = m(x² + y²)/12`.
- Cylinder radius `r`, length `l`, axis +Z: `ixx = iyy = m(3r² + l²)/12`, `izz = m r²/2`.
- Sphere radius `r`: `ixx = iyy = izz = 2m r²/5`.
- Thin rod length `l`, axis +Z: `ixx = iyy = m l²/12`, and a small positive `izz`, never 0.

Where the shape is turned in the link frame, put the turn in the inertial origin's `rpy` rather than
rotating the tensor by hand.

## Mesh-Derived Inertials

A link that is no primitive gets its numbers from a throwaway script, and the ledger says what the
script assumed (a primitive standing in for a complex part is an assumption too).

**From the exact solids**, where the link has them (a text-to-cad model, a STEP): in a script
`cad run` runs, `cad.build123d.mass_properties([(solid, density), ...])`, with the solids in the
link's frame and each density in kg/mm³, returns the link's `.mass` (kg), `.center_of_mass` (mm) and
`.inertia` about it (kg·mm²): multiply the centre by `1e-3` and the inertia by `1e-6` for the
description. Parts in different materials each take their own density, and a bought part weighed at
its maker's mass takes that mass over its solid's volume. A model's densities, without loading a
solid, are `cad.model.inspect(handle, query="structure")["summary"]["materials"]`, in kg/m³: times
`1e-9` for kg/mm³.

**From the mesh**, where that is all there is, with `trimesh`:

```python
# /// script
# dependencies = ["lxml"]        # trimesh reads a 3MF with it; an STL needs none
# ///
import trimesh

mesh = trimesh.load("3MF/forearm_link.3mf", force="mesh")
mesh.apply_scale(0.001)          # mm -> m: the scale the description gives the mesh
mesh.density = 1200.0            # an assumed density, kg/m^3
print("mass", mesh.mass)
print("com", mesh.center_mass)   # -> inertial <origin xyz>
print(mesh.moment_inertia)       # about the centre of mass, in the mesh's axes -> ixx..izz
```

The mesh must be the file the description references, in the same frame and at the same scale, or
the centre of mass and the tensor land in another frame. It must be watertight
(`mesh.is_watertight`), or its volume means nothing: fix the export, or fall back to a primitive and
say so. The uniform density is an assumption: record it, or the total mass it was derived from, in
the ledger.

## Sanity Gates

Before accepting an inertial block, check:

1. `mass > 0`, every value finite, and the diagonal `ixx`, `iyy`, `izz > 0`.
2. The triangle inequality: `ixx + iyy ≥ izz`, `ixx + izz ≥ iyy`, `iyy + izz ≥ ixx`.
3. Magnitude: for a part of characteristic size `d` and mass `m`, the diagonal terms lie within
   roughly an order of magnitude of `m·d²/10`. A 0.5 kg, 10 cm part with `ixx = 2.0` kg·m² is wrong
   by about 1000x.
4. The centre of mass lies inside the part's bounding volume, or very near it.
5. The off-diagonal terms are small beside the diagonal unless the part is skewed in the link frame:
   large `ixy`, `ixz` or `iyz` usually mean a tensor expressed in the wrong frame.

Of these, `cad urdf validate` runs the first two, and the third only for a link whose geometry is one
primitive ([urdf-checks.md](urdf-checks.md)). `cad mujoco check` fails, in MuJoCo's words, a moving
body with no mass and a tensor that breaks the triangle inequality, and checks no magnitude: its
`mass_summary` line gives the moving mass to read. The rest are yours.

A gate that fails by a clean power of ten is usually a unit. CAD mass properties come in millimetre
units, and an inertia in kg·mm² takes a factor of `1e-6` to become kg·m², on top of any density
conversion (lengths enter the tensor squared).
