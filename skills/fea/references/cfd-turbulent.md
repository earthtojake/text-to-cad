# Turbulent flow (`cfd_turbulent`, lite)

It answers what [Flow](cfd.md) answers, "what pressure does the fluid lose through or around the
part, how fast does it go, how hard does it push on the part", when the flow is turbulent: water
in a pipe faster than a few cm/s, air in a duct, a stream past a body. It solves the steady
Reynolds-averaged flow with a turbulence model (k-omega SST) and wall functions, in-house (no
outside software). With `map_to_structure` the wall pressure is applied to a static solve of the
part, so its stress and displacement come too. The plain word is Turbulent flow.

**Limits, written into every result: "Steady RANS (k-omega SST), wall functions,
incompressible".** Quote them whenever you quote a turbulent flow number.

## When to use it

- A `cfd` result warned that its Reynolds number is past the laminar range ("Re 4200 is past the
  laminar range ..."): run the same study with `"analysis": "cfd_turbulent"` and report this one.
- Before running, work out Re = ρ V D / μ (D the inlet's hydraulic diameter, 4 × area / perimeter,
  for flow through the part; the part's largest extent for flow around it). Above **Re 2000
  internal** or **Re 1000 external**, start here.
- Below those numbers use `cfd`: the flow is likely laminar, and a turbulence model overstates the
  pressure drop. This analysis still runs there and warns (`reynolds_laminar_range`).
- Not for gas faster than about Mach 0.3 (about 100 m/s in air), where its density changes: use
  `cfd_compressible` ([cfd-compressible.md](cfd-compressible.md)). Not for heat transfer, free
  surfaces, or anything time-varying (vortex shedding shows only as its steady average).

## The study

Exactly `cfd`'s study ([cfd.md](cfd.md#the-study)): `flow` (`internal` with `inlets` and `outlets`
on sides of the part's bounding box, or `external` with a free stream), `fluid`, optional
`map_to_structure`, checks `pressure_drop` and `velocity` (plus `stress` and `displacement` when
mapped). One key is added:

- `turbulence_intensity`: the fluctuating share of the mean speed. Internal flow: per inlet
  (default `0.05`, 5 %). External flow: on `flow` (default `0.01`, a calm free stream).

```json
{"analysis": "cfd_turbulent",
 "mesh": {"size_mm": 1.0},
 "flow": {"kind": "internal", "fluid": "water",
          "inlets": [{"opening": "x_min", "velocity_m_s": 1.0}],
          "outlets": [{"opening": "x_max", "pressure_Pa": 0}]},
 "view": {"checks": [{"kind": "pressure_drop", "limit_Pa": 50},
                     {"kind": "velocity", "limit_m_s": 3}]}}
```

```json
{"analysis": "cfd_turbulent",
 "flow": {"kind": "external", "fluid": "air", "velocity_m_s": [20, 0, 0], "turbulence_intensity": 0.01}}
```

- An inlet's `profile`:
  - `"developed"` (default): the settled turbulent flow of a long straight duct of the opening's
    own shape (its speed, k and omega, solved on the opening by the same model), as if a long
    straight pipe fed it. The intensity is not read: the developed flow sets its own.
  - `"uniform"`: one speed everywhere, with k = 1.5 (I U)² from the intensity and a length scale
    of 0.07 D. It adds the entrance's extra loss (a 2-diameter pipe fed uniform reads about 25 %
    over the developed drop).
- `mesh.size_mm` is the element size at the walls and openings. Default: a tenth of the narrowest
  opening's hydraulic diameter (internal), L/8 (external, the free stream four times coarser).
  Turbulent flow needs a finer mesh than laminar: at a sixth of the diameter a pipe's drop reads
  about 10 % low.

## What comes out

- Fields on the part's surface: `pressure` (wall pressure, Pa gauge, signed) and `wall_shear` (Pa,
  the wall function's ρ u_τ²). A face the fluid does not wet reads 0. Mapped: `von_mises` and
  `displacement` too.
- Summary: everything `cfd` gives (`reynolds` with `turbulent` instead of `laminar`,
  `pressure_drop_Pa`, flow rates, `max_velocity_m_s`, wall pressure and shear ranges, `force_N`,
  `fluid_mesh`, the checks), plus `turbulence` (`model`, `wall_treatment`, the eddy-to-fluid
  viscosity ratio `viscosity_ratio_mean` / `viscosity_ratio_max`, and `wall_yplus` min / mean /
  max of the wall function's distance), `solve` (pseudo-time `steps`, `factorizations`, the last
  `residual`, `converged`) and, for a developed inlet, `developed_inlets` (each opening's friction
  factor from its own cross-section solve).
- CLI: the flow and its Re, the pressure drop, flow rate and fastest speed, the wall pressure,
  shear and force, the eddy viscosity and wall y+, the steps.
- Findings: `reynolds_laminar_range` (warning), `turbulent_unsettled` (warning: the march
  stopped short of its tolerance), the check findings, `flow_balance`, and the static findings
  when mapped.

## Judging the answer (a hand check)

A smooth straight pipe, fully developed: Δp = f (L / D) ρ U² / 2, with Darcy's friction factor f
from Colebrook's equation (the Moody chart, smooth wall):

1 / √f = −2 log₁₀(2.51 / (Re √f)), solved by repeating it from f = 0.02.

| Re | 10,000 | 20,000 | 50,000 | 100,000 |
| --- | --- | --- | --- | --- |
| f (smooth) | 0.0309 | 0.0259 | 0.0209 | 0.0180 |

Water at 1.0 m/s through a 10 mm bore 15 mm long: Re ≈ 10,000, f = 0.0309, Δp = 0.0309 × 1.5 ×
998 × 1² / 2 ≈ 23 Pa; the wall shear is f ρ U² / 8 ≈ 3.9 Pa. The solver's benchmark (that pipe,
fed developed, 1 mm elements) reads Δp within 2 % at Re 10,000 and 4 % at Re 50,000, and the
test holds it to 10 %.

- Turbulent drop grows nearly as the square of the speed (U^1.75 in a smooth pipe): double the
  speed, about 3.4 times the drop. A drop growing in proportion to the speed is laminar: use `cfd`.
- Bends, steps and splits add about K ρ U² / 2 each (K of order 0.2-1.5); the solver includes them.
- External: drag F = Cd × ½ ρ U² A; a bluff body (a cube, a plate face-on) has Cd of order 1.
- Mapped: a tube under internal pressure p has a hoop stress at the bore of p (Ro² + Ri²)/(Ro² − Ri²).

## Limits

- Steady RANS (k-omega SST), wall functions, incompressible. No heat, gravity, free surface or
  time variation; no wall roughness (smooth walls); no compressibility.
- Wall functions: the first element is kept in the log layer (its wall distance at least y+ 30),
  so the flow next to the wall is the law of the wall, not resolved. Separation and reattachment
  on a smooth curved wall are approximate.
- The mean flow is Taylor-Hood (quadratic velocity, linear pressure) with streamline diffusion
  where the mesh is coarse for the speed; k and omega are linear, stabilised by SUPG.
- One part only; openings are bounding-box sides (as `cfd`).
- The wall values are carried to the part's faces from the nearest fluid node on the same face.

## How it solves

Pseudo-transient continuation: from a Stokes-like start with a mixing-length eddy viscosity (or
the free stream's), each step solves the mean flow with the eddy viscosity frozen and a local
pseudo-time term, then k, then omega, each with the new velocity. The pseudo-time step grows while
the change per step shrinks and is halved when it stalls; the march stops when the velocity
changes by under 1e-5 of the reference speed in a step. A developed pipe settles in about 15 steps;
a body in a free stream takes 100 or more. A run that does not settle returns its last state with
a `turbulent_unsettled` warning, never a refusal.

## When the model is big

It runs at any size. The ladder may take, each an `adapted:` line to report:

- `fluid_coarsen`: the free stream and far field meshed coarser (2.5× each time), walls and
  openings kept at the size asked for: "Coarsened the flow mesh away from the walls to fit: walls
  and openings are still meshed at 1.25 mm, the free stream at 3.12 mm". Its note: the core of the
  flow is coarser; the pressure drop and wall shear are set at the walls. Skipped where every
  element is near a wall.
- `continuation`: the pseudo-time march in longer steps (CFL from 50, growing 4× a step): "Marched
  to the steady turbulent flow in longer pseudo-time steps ... so it settles in fewer solves". The
  same steady flow, to the same tolerance; the stall rule still halves the step where it must.
- `iterative`: Krylov solves (GMRES with a multigrid preconditioner on the velocity and the
  pressure mass matrix) instead of a direct factor, where that saves memory. Exact; a stalled
  Krylov solve is finished by the direct solver.
