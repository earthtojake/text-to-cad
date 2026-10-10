# Flow (`cfd`, lite)

It answers "how does fluid flow through or around the part, what pressure does it lose, how fast
does it go, and how hard does it push on the part": steady, laminar, incompressible flow, solved
in-house (no outside software). With `map_to_structure`, the wall pressure is then applied to a
static solve of the part, so its stress and displacement come too. The plain word is Flow.

**Limits, written into every result: "Laminar, steady, incompressible; no turbulence model."**
Quote them whenever you quote a flow number.

## When to use it

- "What pressure drop does this manifold / channel / nozzle cause at 0.5 m/s of water?"
- "How fast does the air go through this duct?", "is the flow split evenly between the outlets?"
- "How hard does the water push on this part?" (`map_to_structure`: "will the pressure crack it?")
- Flow around a body (`external`): the force of a slow air or water stream on it.
- Not for fast or turbulent flow (most air ducts at fan speeds, most water pipes above a few cm/s
  in a 1 cm bore): it still runs and warns (below), but the numbers are a laminar lower bound; use
  `cfd_turbulent` ([cfd-turbulent.md](cfd-turbulent.md)) for those. Not for gas faster than about
  Mach 0.3 (about 100 m/s in air), where its density changes: use `cfd_compressible`
  ([cfd-compressible.md](cfd-compressible.md)). For the heat a flow carries into or out of the part
  (a coolant, a cold plate), use `conjugate_heat` ([conjugate-heat.md](conjugate-heat.md)), which
  solves this flow first. Not for free surfaces or anything time-varying.

## The study

On top of the common keys in [study-file.md](study-file.md#common-keys). Internal flow (through
the part):

```json
{"analysis": "cfd",
 "mesh": {"size_mm": 1.0},
 "flow": {"kind": "internal", "fluid": "water",
          "inlets": [{"opening": "x_min", "velocity_m_s": 0.5}],
          "outlets": [{"opening": "x_max", "pressure_Pa": 0}]},
 "map_to_structure": {"material": "aluminum-6061-t6", "fixtures": [{"faces": ["#o1.f1"]}]},
 "view": {"checks": [{"kind": "pressure_drop", "limit_Pa": 2000},
                     {"kind": "velocity", "limit_m_s": 3},
                     {"kind": "stress"}]}}
```

External flow (around the part):

```json
{"analysis": "cfd",
 "flow": {"kind": "external", "fluid": "air", "velocity_m_s": [5, 0, 0]}}
```

- `material` is not needed for flow. It is the structure's, given in `map_to_structure.material`
  (or the top-level `material`), and only a mapped flow needs one.
- `flow.fluid`: `"air"` (1.204 kg/m³, 1.81e-5 Pa·s, 20 °C), `"water"` (998.2 kg/m³,
  1.002e-3 Pa·s, 20 °C) or `{"density_kg_m3", "viscosity_Pa_s", "name"}` for anything else
  (oil, glycol, a syrup).
- Internal flow:
  - Openings name a side of the part's bounding box: `x_min`, `x_max`, `y_min`, `y_max`, `z_min`,
    `z_max`. A port must reach that side (its face lies on it, with the hole in it). Run `cadgen
    fea faces` to see which sides the ports are on.
  - `inlets`: each `{"opening", "velocity_m_s", "profile"}`. `velocity_m_s` is the mean speed in
    (the flow rate is speed × the opening's area). `profile` is `"developed"` (default: the settled
    laminar profile of the opening's own shape, as if a straight pipe fed it) or `"uniform"`.
  - `outlets`: each `{"opening", "pressure_Pa"}` (gauge, default 0), where the flow leaves freely.
  - At least one inlet and one outlet. Each side is one opening: an inlet and an outlet cannot
    share a side.
  - Every port of the passage must be named. A side the part has no opening on is refused, naming
    the sides it does open on; a passage that also opens on an unnamed side is refused, naming it.
- External flow: `velocity_m_s` is the free stream `[x, y, z]`. The domain is a box around the
  part reaching 2 L upstream, 5 L downstream and 2 L to the sides (L the part's largest extent).
  The box sides the stream enters through are inlets, those it leaves through are outlets at 0 Pa,
  the rest are slip walls.
- `mesh.size_mm` is the element size at the part's walls (and an internal flow's openings).
  Default: a quarter of the narrowest opening's hydraulic diameter (internal), L/8 (external,
  with the free stream four times coarser).
- `map_to_structure`: `{"material", "fixtures"}` (fixtures as in a static study). The wall pressure
  is applied, face by face, as a pressure load on the part (one-way coupling; the wall shear is not
  applied). The static fields and checks join the result. When the part bends enough to change the
  flow (a soft flap, a thin reed, a hose that swells), use `fsi` ([fsi.md](fsi.md)): two-way, the
  wall shear applied too.
- Checks: `pressure_drop` (`limit_Pa`, the drop from the inlets to the outlets) and `velocity`
  (`limit_m_s`, the fastest point anywhere in the fluid), each close past 0.9 of its limit; plus
  `stress` and `displacement` when mapped (refused without `map_to_structure`). No check is made by
  default.

## What comes out

- Fields on the part's surface (what the viewer shows): `pressure` (wall pressure, Pa gauge,
  signed) and `wall_shear` (Pa). A face the fluid does not wet (a pipe's outside) reads 0. Mapped:
  `von_mises` and `displacement` too, and the part deforms.
- Summary: `reynolds` (`value`, `limit`, `kind`, `length_mm`, `laminar`), `max_velocity_m_s` and
  where, `flow_rate_m3_s` and `flow_rate_L_min` (in), `outflow_rate_m3_s`, `flow_balance` (their
  mismatch), `pressure_drop_Pa`, `inlet_pressure_Pa`, `outlet_pressure_Pa` (area means),
  `min/max_wall_pressure_Pa`, `max_wall_shear_Pa`, `force_N` (the flow's push on the part,
  pressure and friction), `solve` (Picard and Newton steps, the residual, any continuation stages),
  `fluid_mesh` (elements, wall and free-stream sizes) and the `checks`. Mapped: `max_von_mises_MPa`,
  `max_displacement_mm`, `yield_MPa`, `safety_factor`.
- CLI: the flow and its Re, the pressure drop, flow rate and fastest speed, the wall pressure range,
  shear and force, the solver steps, and the mapped stress.
- Findings: `reynolds_past_laminar` (warning), `pressure_drop_over_limit` / `velocity_over_limit`
  (error), `..._close_to_limit` (warning), `flow_balance` (warning: in and out differ by over 1 %),
  `continuation` (info), and the static findings when mapped.

## The Reynolds warning (never a refusal)

Re = ρ V D / μ, with D the inlet's hydraulic diameter (4 × area / perimeter) for internal flow and
the part's largest extent for external flow. Above **Re 2000 internal** or **Re 1000 external**
the run still solves (reaching that Re by continuation when it must) and warns: "Re 4200 is past
the laminar range (laminar above Re 2000 is unreliable): real flow is likely turbulent, so this
pressure drop is a lower bound and the flow pattern may be wrong; run the same study as
cfd_turbulent for the turbulent answer". The number is also data:
`summary.reynolds` (and `extras.analysis.reynolds`), so the viewer's verdict reads "Laminar ·
unreliable above Re 2000". Tell the user the number and what it means; do not quote the pressure
drop as the answer, only as a lower bound. Then run the same study with `"analysis":
"cfd_turbulent"` ([cfd-turbulent.md](cfd-turbulent.md)): the same keys, a turbulence model (k-omega
SST with wall functions), and the pressure drop to report.

## Judging the answer (a hand check)

- Straight round pipe (Hagen-Poiseuille): Δp = 8 μ L Q / (π R⁴), the profile is the parabola
  u = 2 U (1 − r²/R²), and the wall shear is 4 μ U / R. Water at 0.01 m/s through a 4 mm bore
  16 mm long: Q = 1.26e-7 m³/s, Δp = 0.32 Pa, τ = 0.020 Pa. The solver matches the drop within
  about 1 % and the profile within 2 % with the default mesh.
- Any duct, laminar: Δp grows in proportion to the speed (double it, double the drop). Turbulent
  flow grows nearer the square: if the user's measured drop grows faster than the speed, the flow
  is not laminar.
- Losses at bends, steps and splits add roughly K ρ U² / 2 each (K of order 0.5-1.5); the solver
  includes them, laminar.
- External: drag F = Cd × ½ ρ U² A. At low Re, Cd ≈ 24/Re for a sphere (Stokes); a box near Re 30
  has Cd of order 2-3. The domain's sides are 2 L away, so a slow flow around a wide body reads a
  little high (blockage).
- Mapped: a tube under internal pressure p has a hoop stress at the bore of p (Ro² + Ri²)/(Ro² − Ri²).

## Limits

- Laminar, steady, incompressible; no turbulence model. No heat, no gravity, no free surface, no
  time variation (vortex shedding shows only as a steady average, if at all).
- Galerkin Taylor-Hood elements with streamline diffusion where the mesh is coarse for the flow
  speed (cell Péclet number over 1): it steadies a fast flow on a coarse mesh at the cost of some
  accuracy where the flow changes along a streamline. Fully developed pipe flow is untouched.
- One part only (pick one of an assembly with `--occurrence`). Openings are bounding-box sides.
- The developed inlet profile assumes a straight feed; `"uniform"` adds an entrance loss.
- The wall values are carried to the part's faces from the nearest fluid node on the same face.

## When the model is big

It runs at any size. The ladder may take, each an `adapted:` line to report:

- `iterative`: Krylov solvers (MINRES for the Stokes start, GMRES after) with a multigrid
  preconditioner on the velocity and the pressure mass matrix, instead of a direct factor. Exact;
  said when it saves time or memory. A Krylov solve that stalls is finished by the direct solver.
- `fluid_coarsen`: the free stream and far field meshed coarser (2.5× each time), the part's walls
  (and an internal flow's openings) kept at the size asked for: "Coarsened the flow mesh away from
  the walls to fit: the part is still meshed at 2 mm, the free stream at 16 mm". Its note: the
  core of the flow is coarser; the pressure drop and wall shear are set at the walls. Skipped where
  every element is near a wall (a narrow pipe).
- `continuation`: above Re 100, when it saves solves, the Reynolds number is stepped up (Re/8,
  Re/4, Re/2, Re), each stage from the one before. Exact (the same steady flow). Without the rung,
  the solve still falls back to continuation by itself when Newton does not converge from the
  Stokes start (a `continuation` info finding).
