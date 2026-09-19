# URDF Inertials

Inertials are the most-freehanded and least-checked part of LLM-authored URDFs. The rule is absolute: **never type inertia numbers from intuition.** Every `mass`, inertial `origin`, and `inertia` value is either copied from source data (CAD mass properties, vendor datasheet, measurement) or computed by a formula or script in the same task. Record which, per link, in the design ledger.

## When Inertials Are Required

- Simulation and dynamics consumers (Gazebo/Ignition, physics engines, torque control): every physical link needs a valid `inertial`.
- Visualization-only or kinematics-only consumers (RViz, CAD Viewer, MoveIt kinematic planning): inertials are optional but still recommended so the model stays simulator-ready.
- Frame-only links (`base_footprint`, optical frames, TCP markers): intentionally omit `inertial` and mark the link frame-only in the ledger.

Do not give movable physical links zero or missing mass for a simulation target; most engines misbehave. If mass is unknown, use a documented assumed density or assumed total mass distributed by volume, and say so in the ledger.

## Semantics

- `<inertial><origin>` is the center of mass expressed in the link frame. It is not the visual origin, the collision origin, or the joint origin.
- `<inertia>` is the rotational inertia tensor about the center of mass, expressed in the inertial frame (link frame rotated by the inertial origin `rpy`), in kg·m².
- If source data gives the tensor about another point, transfer it to the COM (parallel axis theorem, subtracting) before writing it down — or simpler, re-export CAD mass properties about the COM.

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

- The mesh must be the same file, same frame, and same scale as the URDF reference; otherwise the COM and tensor land in the wrong frame.
- The mesh should be watertight for volume integration; if it is not, fix the export or fall back to a documented primitive approximation.
- Uniform density is an assumption — record the chosen density (or the total-mass target it was derived from) in the ledger.
- CAD-native mass properties (for example OCP/OpenCascade `BRepGProp` on the STEP solid) are better than mesh integration when the STEP source is available; same rules apply.

For complex or parametric models it is reasonable to keep this helper script on disk next to the model's other source files and reference it from the ledger. That is optional; the checked-in URDF values remain canonical.

## Sanity Gates

Before accepting any inertial block, check:

1. `mass > 0`, all values finite; diagonal `ixx, iyy, izz > 0`.
2. Triangle inequality: `ixx + iyy ≥ izz`, `ixx + izz ≥ iyy`, `iyy + izz ≥ ixx` (the bundled validator enforces this).
3. Magnitude plausibility: for a part with characteristic size `d` and mass `m`, diagonal terms should be within roughly an order of magnitude of `m·d²/10`. A 0.5 kg, 10 cm part with `ixx = 2.0` kg·m² is wrong by ~1000×.
4. COM plausibility: the inertial origin lies inside (or very near) the part's bounding volume.
5. Off-diagonal terms are small relative to diagonals unless the part is genuinely skewed in the link frame — large `ixy/ixz/iyz` values usually mean the tensor was expressed in the wrong frame.

A common unit bug to watch for: CAD systems report mass properties in mm-based units. Converting mm-based inertia to kg·m² requires a factor of `1e-6` on top of any density conversion (lengths enter the tensor squared, volumes cubed). If the magnitude gate fails by a clean power of ten, suspect this first.
