# Inertials

Inertials are the most-freehanded and least-checked part of LLM-authored URDFs and MJCFs. The rule is absolute: **never type inertia numbers from intuition.** Every `mass`, inertial `origin`, and `inertia` value is generated from the CAD model, copied from source data (vendor datasheet, measurement) or computed by a formula or script in the same task. A hand-written file records which, per link, in the design ledger ([urdf-ledger.md](urdf-ledger.md)), or in an MJCF's ledger comment.

## Generated From the CAD Model

A description generated from a CAD model (`cad model export <id> robot.xml` or `.urdf`, or `cad.mujoco.spec`) takes every link's inertial from the kernel: the exact solids at each part's material density, summed over the link's parts, the centre of mass in the link frame and the tensor about it in the link frame's axes, in kilograms and kg·m². It replaces everything below for that robot: no formula, no mesh integration, no ledger line. A number the kernel computed is regenerated, never edited.

- **Give every part a material** (`part.material = metals.aluminum()`, from `bd_materials`): its density is what weighs it. Check the result before exporting: `cad model inspect <id> <assembly label>` weighs the assembly and names the parts with no material.
- **A part with no material weighs nothing.** A link whose parts all lack one has no inertial, and each format reads that its own way: MuJoCo computes one from the link's geoms, visual and collision both, and says so as `inertia_from_visuals` ([mjcf-checks.md](mjcf-checks.md#model-health)); a URDF link without one is warned of by `cad urdf validate` when it moves. Either on a moving link is wrong: set the materials and export again. A link that leaves out some of its parts says which in the export's warning.
- **A density that is not a positive number** is refused by name.
- **A part that is not what it is made of** (a hollow shell modelled solid, a motor modelled as its housing): declare what it weighs, `mass(part, grams)` from `cad.build123d`, the measured or datasheet total; its solids are scaled alike to make it up, so the centre of mass and the inertia's shape stay the geometry's. On an assembly, `mass()` is all of it: its parts keep their densities' ratios (one density for all where none of them has a material; a part with no material among parts that have one carries none of the total, and the export says so), an inner `mass()` fixes its own subtree and the outer one scales the rest. Say so to the person.
- **A lump the CAD leaves out** (a motor or a battery inside a filled housing): `point_mass(part, grams, at, name="motor")`, at `at` in the part's own frame, with no inertia of its own unless `inertia=(ixx, iyy, izz)` (kg·m², in `at`'s axes) gives it. It goes into the link's inertial exactly. A `mass()` above it counts it, so declare the measured total and the lumps you know: the solids make up the rest, and a total the lumps reach is refused by name.

## A Link Drawn as One Plain Solid

A vendor's simplified STEP, or an industrial arm's shells, draws each link as one filled solid with
no motor inside, and the datasheet gives the whole arm's weight and nothing per link. Give every
solid one material and the arm its total, `mass(arm, total_g)`: the total is split by the links'
volumes, and the model's docstring says so. That split puts each link's mass where its envelope is,
but the hardware's mass sits mostly in its motors and gearboxes, at the joints: each link's centre of
mass comes out too far from its joints (towards the middle of its envelope), and its inertia too
large, by tens of percent on a long link. Where the actuators' masses are known (the vendor's
actuator line, a published motor) or can be estimated (an actuator of the joint's torque class from
another maker's datasheet), put each at its joint, on the link that holds its case, with
`point_mass()` in that part's own frame, and keep `mass(arm, total_g)`: the lumps count towards the
total and the solids make up the rest, so the total stays the datasheet's and the centres of mass
move towards the joints. Say in the docstring which masses are listed and which estimated.

```python
ARM_G = 9000.0                                     # the datasheet: the arm's weight
ACTUATOR_G = {"shoulder": 1200.0, "elbow": 900.0}  # each joint's actuator: listed, or estimated (say which)
for joint, grams in ACTUATOR_G.items():
    case = parts[HOLDS[joint]][0]                  # the link that holds the actuator's case
    point_mass(case, grams, case.location.inverse() * bd.Location(AXES[joint][0]), name=f"{joint}_actuator")
mass(arm, ARM_G)
```

## A Printed Part

A printed part is a shell around sparse infill, not the solid its CAD models, so its material's
density overweighs it. In order of preference, declare with `mass(part, grams)`:

1. **The part weighed on a scale**, or the maker's published weight for it.
2. **The slicer's filament weight** for that part, at the settings it is printed with.
3. **An estimate from the print settings**, computed in the model from the part's own B-rep:
   `grams = density x (shell + infill x (volume - shell))`, where `shell = area x walls x line width`
   (for example 2 walls x 0.4 mm). Densities in g/cm^3 (1e-3 g/mm^3): PLA 1.24, PETG 1.27, ABS 1.04,
   ASA 1.07. The estimate treats the top and bottom layers as walls, so expect it to be off by 10-20 %,
   and say so in a comment beside it.

```python
PLA_G_PER_MM3, SHELL_MM, INFILL = 1.24e-3, 2 * 0.4, 0.15   # PLA, 2 walls of a 0.4 mm nozzle, 15 %


def printed_grams(part):
    shell = min(part.volume, part.area * SHELL_MM)
    return PLA_G_PER_MM3 * (shell + INFILL * (part.volume - shell))


part.material = plastics.pla()
mass(part, printed_grams(part))   # an estimate from the print settings, not weighed
```

A real print carries more of its mass at the surface than the solid does, but `mass()` scales the
solid uniformly: the centre of mass is the solid's, and the inertia comes out a little low. That is
close enough for a simulation, and not worth modelling the shell for. A
servo, a motor or a battery is a bought part with a datasheet: `mass(case, grams)` on its
sub-assembly with the datasheet's weight, or `point_mass()` where the CAD leaves it out.

## When Inertials Are Required

- Simulation and dynamics consumers (MuJoCo and other physics engines, torque control): every physical link needs a valid `inertial`. Inertial data is simulation-critical: very small, zero, negative, or guessed inertias are high risk.
- Visualization-only or kinematics-only consumers (RViz, CAD Viewer, MoveIt kinematic planning): inertials are optional but still recommended so the model stays simulator-ready.
- Frame-only links (`base_footprint`, optical frames, TCP markers): intentionally omit `inertial` and mark the link frame-only in the ledger.

Do not give movable physical links zero or missing mass for a simulation target; most engines misbehave. If mass is unknown, use a documented assumed density or assumed total mass distributed by volume, and say so in the ledger: a split by volume puts each link's centre of mass too far from its joints where the hardware's mass is in its motors ([A Link Drawn as One Plain Solid](#a-link-drawn-as-one-plain-solid)).

## Semantics

- `<inertial><origin>` is the center of mass expressed in the link frame. It is not the visual origin, the collision origin, or the joint origin.
- `<inertia>` is the rotational inertia tensor about the center of mass, expressed in the inertial frame (link frame rotated by the inertial origin `rpy`), in kg·m².
- If source data gives the tensor about another point, transfer it to the COM (parallel axis theorem, subtracting) before writing it down — or simpler, re-export CAD mass properties about the COM.

In MJCF the same quantities are attributes of a body's `<inertial>`: `pos` for the center of mass, `mass`, and `fullinertia="ixx iyy izz ixy ixz iyz"` (or `diaginertia` with `quat` for the principal axes). Do not copy visual origins into inertial origins unless that is physically justified. A placeholder inertial, only where the user asked for a scaffold, is labelled as one ([guardrails.md](guardrails.md#placeholder-policy)).

## Closed-Form Formulas (solid, uniform density)

With mass `m` (kg) and dimensions in meters, about the COM, axis-aligned:

- Box `x × y × z`: `ixx = m(y² + z²)/12`, `iyy = m(x² + z²)/12`, `izz = m(x² + y²)/12`.
- Cylinder radius `r`, length `l`, axis +Z: `ixx = iyy = m(3r² + l²)/12`, `izz = m r²/2`.
- Sphere radius `r`: `ixx = iyy = izz = 2m r²/5`.
- Thin rod length `l`, axis +Z: `ixx = iyy = m l²/12`, `izz ≈ 0` (use a small positive value, not 0).

Off-diagonal terms are zero for these primitives when the axes align with the link frame. If the primitive is rotated relative to the link frame, express the rotation in the inertial origin `rpy` instead of hand-rotating the tensor.

## Mesh-Derived Inertials

For mesh geometry, write a throwaway helper script; do not approximate a complex part as a primitive without saying so in the ledger. The standard recipe with `trimesh`:

```python
import trimesh
mesh = trimesh.load("3MF/forearm_link.3mf", force="mesh")
mesh.apply_scale(0.001)          # mm -> m, match the URDF mesh scale
mesh.density = 1200.0            # documented assumed density, kg/m^3
print("mass", mesh.mass)
print("com", mesh.center_mass)   # -> inertial <origin xyz>
print(mesh.moment_inertia)       # about COM, link-frame axes -> ixx..izz
```

Requirements for the script route:

- The mesh must be the same file, same frame, and same scale as the URDF or MJCF reference; otherwise the COM and tensor land in the wrong frame.
- The mesh should be watertight for volume integration; if it is not, fix the export or fall back to a documented primitive approximation.
- Uniform density is an assumption — record the chosen density (or the total-mass target it was derived from) in the ledger.
- CAD-native mass properties (for example OCP/OpenCascade `BRepGProp` on the STEP solid) are better than mesh integration when the STEP source is available; same rules apply.
- A link that is a text-to-cad model of several parts in different materials is one call on its exact solids, each at its own density: in a script `cad run` runs, `cad.build123d.mass_properties([(solid, density), ...])` with the solids in the link's frame and densities in kg/mm³ returns the link's mass (kg), centre of mass (mm) and inertia about it (kg·mm²); multiply the centre by `1e-3` and the inertia by `1e-6` for the description. A bought part weighed at its maker's mass takes that mass over its solid's volume as its density. Each part's material density, without loading a solid, is `cad.model.inspect(handle, query="structure")["summary"]["materials"]`, in kg/m³: times `1e-9` for kg/mm³.

For complex or parametric models it is reasonable to keep this helper script on disk next to the model's other source files and reference it from the ledger. That is optional; the checked-in URDF or MJCF values remain canonical.

## Sanity Gates

Before accepting any inertial block, check:

1. `mass > 0`, all values finite; diagonal `ixx, iyy, izz > 0`.
2. Triangle inequality: `ixx + iyy ≥ izz`, `ixx + izz ≥ iyy`, `iyy + izz ≥ ixx`. The bundled URDF validator reports a violation as the warning `inertia_triangle_inequality`, which `--strict` promotes to blocking; positive-semidefiniteness and positive diagonals are hard errors.
3. Magnitude plausibility: for a part with characteristic size `d` and mass `m`, diagonal terms should be within roughly an order of magnitude of `m·d²/10`. A 0.5 kg, 10 cm part with `ixx = 2.0` kg·m² is wrong by ~1000×.
4. COM plausibility: the inertial origin lies inside (or very near) the part's bounding volume.
5. Off-diagonal terms are small relative to diagonals unless the part is genuinely skewed in the link frame — large `ixy/ixz/iyz` values usually mean the tensor was expressed in the wrong frame.

A common unit bug to watch for: CAD systems report mass properties in mm-based units. Converting mm-based inertia to kg·m² requires a factor of `1e-6` on top of any density conversion (lengths enter the tensor squared, volumes cubed). If the magnitude gate fails by a clean power of ten, suspect this first.
