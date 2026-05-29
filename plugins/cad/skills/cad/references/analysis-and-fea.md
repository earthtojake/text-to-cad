# Analysis and modal FEA

Read this file when the user asks for mass properties, an inertia tensor,
interference/overlap, clearance/wall-thickness, cross-section area, or a modal /
natural-frequency / resonance estimate from STEP geometry.

Two launchers live in the CAD skill directory:

```bash
python scripts/analyze {props|interference|clearance|section} ...
python scripts/fea {modal|materials} ...
```

`analyze` uses only build123d/OCP (already required by the skill). `fea` is
**opt-in**: it imports `ngsolve` + `netgen` lazily and only when you run
`fea modal`. `analyze --help`, `fea --help`, and `fea materials` work without
the solver stack.

## When to use which

- Use `analyze` to turn a STEP into physical facts: volume, surface area,
  center of mass, the inertia tensor, whether two parts overlap and by how much,
  the gap or wall thickness between two parts, and the load-bearing cross-section
  along an axis. This is the deterministic-geometry counterpart to the visual
  `scripts/snapshot` and the reference-level `scripts/inspect`.
- Use `fea modal` for a first-pass linear-elastic natural-frequency estimate of
  a single fixtured part — resonance, mode shapes, isotropy checks for flexures
  and brackets. It is a design-iteration estimate, **not** certified FEA.

## analyze props — mass properties and inertia

```bash
python scripts/analyze props part.step
```

Returns `volume`, `area`, `centerOfMass`, `inertiaAboutCom` (Ixx..Iyz for a
unit-density solid, taken about the COM), `topology`, and `bbox`. Inertia is
reported about the center of mass so symmetry is visible directly: a part with
N>=3-fold rotational symmetry about Z shows `Ixx == Iyy` and zero products of
inertia (`Ixy = Ixz = Iyz = 0`). This is the fastest programmatic confirmation
that a symmetric design is actually symmetric.

## analyze interference / clearance — fit checks

```bash
python scripts/analyze interference a.step b.step
python scripts/analyze clearance plate.step pin.step
```

`interference` reports the boolean-overlap volume and its bounds (zero volume =
no interference). `clearance` reports the minimum surface-to-surface distance
plus a `status` that disambiguates what a single distance can mean:

- `apart` — surfaces don't touch; `clearance` is the gap.
- `touching` — surfaces meet; `clearance ~ 0`, no overlap volume.
- `containing` — one solid is fully inside the other; `clearance` is the
  smallest wall thickness from the inner surface to the outer hull (use this to
  verify a pocket fits inside a plate).
- `interpenetrating` — partial overlap; both solids have volume outside the
  other (the wall-piercing case).

`intersectionVolume`, `aOutsideB`, and `bOutsideA` quantify overlap so you don't
need a second call.

## analyze section — cross-section area along an axis

```bash
python scripts/analyze section arm.step --axis z --slices 20
```

Samples the section area at evenly spaced stations and returns per-station areas
plus `minArea`/`maxArea`. Use it to find the minimum load-bearing section of a
flexure arm or neck, or to confirm a part is continuous along an axis.

## fea modal — natural frequencies and mode shapes

```bash
python scripts/fea modal spring.step --material pla --fixed outer --modes 6
python scripts/fea materials   # list the built-in material table
```

Output is one row per mode with `frequencyHz` and a `dominant`/`description`
classification (x/y/z-translation, z-rotation/torsion, rocking). Modes are
classified by projecting each eigenvector onto rigid-body motions of the moving
body, so the labels survive the arbitrary basis a solver picks within a
degenerate pair — never assume mode order equals Tx/Ty/Tz.

Key flags:

- `--material` — name from `fea materials` (steel, aluminum, titanium, pla,
  fr4, ...). Add custom values by editing `cadpy_fea/materials.py`.
- `--fixed` — which face(s) to clamp:
  - `bottom` / `top` — largest planar face in the global min/max Z plane.
  - `outer` — the outer wall face spanning the full XYZ extent (e.g. the rim of
    a disk-shaped flexure). It must span full Z, which is what distinguishes the
    wall from the flat top/bottom faces.
  - `largest` — single largest-area face (fallback).
  - `auto` — bottom if present, else largest.
- `--units` — STEP length units (default `mm`; geometry is scaled to metres for
  the SI solve).
- `--maxh` — max mesh element size in model units (`0` = auto, ~18 elements
  across the largest dimension). Refine for converged frequencies; the auto mesh
  is coarse and biases frequencies a few percent high.
- `--modes`, `--order` — number of modes and FE polynomial order.

Install the solver stack with `pip install ngsolve netgen-occt`.

### Flexure / isotropic-resonance notes

These come from tuning orthoplanar springs (flexure translational stages) and
generalize to most planar flexures:

- **N>=3-fold rotational symmetry makes the in-plane stiffness tensor
  isotropic**, so the two in-plane translational modes are automatically
  degenerate (Tx == Ty). Confirm with `analyze props` (Ixx == Iyy, zero
  products of inertia).
- **Balancing the out-of-plane mode (Tz) against the in-plane pair is a tuning
  problem.** Out-of-plane bending stiffness scales as `w*t^3`; in-plane as
  `t*w^3` plus arm axial stretch. Tune the arm cross-section ratio `t/w` and the
  hub size: a larger hub shrinks the radial corridor, makes arms more
  tangential, and moves the isotropy point to wider, more manufacturable arms.
- **A thicker sheet wants wider arms** for the same balance — `t` and `w` track
  together. More spiral wraps (sweep > 360 deg) does not help isotropy and
  invites self-collision.
- **The geometric isotropy ratio is material-independent** to first order;
  frequencies scale as `sqrt(E/rho)`. So tune geometry once, then read the
  frequency for any material with `fea modal --material ...`.

### Gotcha: face selection

netgen's `faces.Nearest(point)` compares to face *centres*, and a cylindrical
face reports its **axis centre** — so all concentric cylinders tie and the wrong
face can be clamped, producing absurdly stiff (high) frequencies. `fea modal`
selects faces by bounding box / area / plane membership instead (see
`select_fixed_faces`). If a clamp looks wrong, check the `fixed.areaMm2` field in
the JSON output and try a different `--fixed` strategy.

## Validation reporting

Report only what actually ran. For `analyze`, cite the returned numbers
(volume, clearance status, min section area). For `fea modal`, state the
material, fixed-face strategy, mesh element count, and that the result is a
first-pass linear-elastic estimate — note that auto-mesh frequencies run a few
percent high until refined with `--maxh`.
