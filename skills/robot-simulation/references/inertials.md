# Inertials

Inertials are the most-freehanded and least-checked part of LLM-authored URDFs and SDFs. The rule is absolute: **never type inertia numbers from intuition.** Every `mass`, inertial `origin`, and `inertia` value is generated from the CAD model, copied from source data (vendor datasheet, measurement) or computed by a formula or script in the same task. A hand-written file records which, per link, in the design ledger ([urdf-ledger.md](urdf-ledger.md), [sdf-ledger.md](sdf-ledger.md)).

## Generated From the CAD Model

A description generated from a CAD model (`cad model export <id> robot.xml`, `.urdf`, `.sdf`, or `cad.mujoco.spec`) takes every link's inertial from the kernel: the exact solids at each part's material density, summed over the link's parts, the centre of mass in the link frame and the tensor about it in the link frame's axes, in kilograms and kg·m². It replaces everything below for that robot: no formula, no mesh integration, no ledger line. A number the kernel computed is regenerated, never edited.

- **Give every part a material** (`part.material = metals.aluminum()`, from `bd_materials`): its density is what weighs it. Check the result before exporting: `cad model inspect <id> <assembly label>` weighs the assembly and names the parts with no material.
- **A part with no material weighs nothing.** A link whose parts all lack one has no inertial, and each format reads that its own way: MuJoCo computes one from the link's geoms, visual and collision both, and says so as `inertia_from_visuals` ([mjcf-checks.md](mjcf-checks.md#model-health)); a URDF link without one is warned of by `cad urdf validate` when it moves; SDFormat assumes 1 kg and a unit tensor. Any of these on a moving link is wrong: set the materials and export again. A link that leaves out some of its parts says which in the export's warning.
- **A density that is not a positive number** is refused by name.
- **A part that is not what it is made of** (a hollow shell modelled solid, a motor modelled as its housing): give it the material with the density that gives the measured mass (`plastics.pla(density=...)`, kg/m³: measured mass over the part's volume), and say so to the person.

## When Inertials Are Required

- Simulation and dynamics consumers (Gazebo/Ignition, physics engines, torque control): every physical link needs a valid `inertial`. For dynamic SDF models inertial data is simulation-critical: very small, zero, negative, or guessed inertias are high risk, and the SDF validator warns about a dynamic physical link without one.
- Visualization-only or kinematics-only consumers (RViz, CAD Viewer, MoveIt kinematic planning): inertials are optional but still recommended so the model stays simulator-ready.
- Frame-only links (`base_footprint`, optical frames, TCP markers), and in SDF frame-like or static links: intentionally omit `inertial` and mark the link frame-only in the ledger.

Do not give movable physical links zero or missing mass for a simulation target; most engines misbehave. If mass is unknown, use a documented assumed density or assumed total mass distributed by volume, and say so in the ledger.

## Semantics

- `<inertial><origin>` is the center of mass expressed in the link frame. It is not the visual origin, the collision origin, or the joint origin.
- `<inertia>` is the rotational inertia tensor about the center of mass, expressed in the inertial frame (link frame rotated by the inertial origin `rpy`), in kg·m².
- If source data gives the tensor about another point, transfer it to the COM (parallel axis theorem, subtracting) before writing it down — or simpler, re-export CAD mass properties about the COM.

In SDF the same quantities are elements: `<inertial>` holds `<mass>`, an optional `<pose>` for the center of mass, and `<inertia>` with `<ixx>`, `<ixy>`, `<ixz>`, `<iyy>`, `<iyz>`, `<izz>` ([sdf-examples.md](sdf-examples.md)). Do not copy visual origins into inertial origins unless that is physically justified. A placeholder inertial, only where the user asked for a scaffold, is labelled as one ([guardrails.md](guardrails.md#placeholder-policy)).

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

- The mesh must be the same file, same frame, and same scale as the URDF or SDF reference; otherwise the COM and tensor land in the wrong frame.
- The mesh should be watertight for volume integration; if it is not, fix the export or fall back to a documented primitive approximation.
- Uniform density is an assumption — record the chosen density (or the total-mass target it was derived from) in the ledger.
- CAD-native mass properties (for example OCP/OpenCascade `BRepGProp` on the STEP solid) are better than mesh integration when the STEP source is available; same rules apply.

For complex or parametric models it is reasonable to keep this helper script on disk next to the model's other source files and reference it from the ledger. That is optional; the checked-in URDF or SDF values remain canonical.

## Sanity Gates

Before accepting any inertial block, check:

1. `mass > 0`, all values finite; diagonal `ixx, iyy, izz > 0`.
2. Triangle inequality: `ixx + iyy ≥ izz`, `ixx + izz ≥ iyy`, `iyy + izz ≥ ixx`. The bundled URDF validator reports a violation as the warning `inertia_triangle_inequality`, which `--strict` promotes to blocking; positive-semidefiniteness and positive diagonals are hard errors. The SDF validator also warns on a triangle-inequality violation and requires a positive-semidefinite tensor.
3. Magnitude plausibility: for a part with characteristic size `d` and mass `m`, diagonal terms should be within roughly an order of magnitude of `m·d²/10`. A 0.5 kg, 10 cm part with `ixx = 2.0` kg·m² is wrong by ~1000×.
4. COM plausibility: the inertial origin lies inside (or very near) the part's bounding volume.
5. Off-diagonal terms are small relative to diagonals unless the part is genuinely skewed in the link frame — large `ixy/ixz/iyz` values usually mean the tensor was expressed in the wrong frame.

A common unit bug to watch for: CAD systems report mass properties in mm-based units. Converting mm-based inertia to kg·m² requires a factor of `1e-6` on top of any density conversion (lengths enter the tensor squared, volumes cubed). If the magnitude gate fails by a clean power of ten, suspect this first.
