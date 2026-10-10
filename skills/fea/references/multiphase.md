# Two fluids (`multiphase`, lite)

It answers "what does the liquid inside this part do over time": a tank sloshing when it is shaken or
braked, how high the liquid climbs the walls, how hard it presses on them and how hard the slosh pushes
the tank, a cavity filling or draining, a bubble rising. Two immiscible fluids (water and air by default),
solved in-house over time (no outside software). With `map_to_structure`, the wall pressure at the moment
of the largest slosh is applied to a static solve of the part, so its stress and displacement come too.
The plain word is Two fluids.

**Limits, written into every result: "Laminar (no turbulence model), incompressible; the interface is
smeared over a few elements and the walls slide freely; no evaporation, boiling, mixing or foam."** Quote
them whenever you quote a number from it.

## When to use it

- "Will the water spill out of this tank when the truck brakes at 0.3 g?" (`fill_level` check)
- "How hard does the slosh push on the tank, and when?", "what pressure do the walls see?"
- "At what frequency does the liquid slosh?" (the summary gives linear theory's first mode; a short shake
  shows the real one in the force curve)
- Filling or draining a cavity through an opening; a bubble rising through a liquid.
- Not for a single fluid filling the whole part with no free surface: use `cfd` ([cfd.md](cfd.md)).
  Not for fast, splashing or turbulent flow (breaking waves, jets): it still runs, but the fine structure
  of the splash is beyond a few elements across the interface. Not for boiling, evaporation, foam or two
  liquids that mix.

## The study

On top of the common keys in [study-file.md](study-file.md#common-keys):

```json
{"analysis": "multiphase",
 "mesh": {"size_mm": 5},
 "fluids": {"liquid": "water", "gas": "air"},
 "fill": {"fraction": 0.5},
 "acceleration": {"direction": [1, 0, 0], "amplitude_g": 0.3,
                  "history": {"shape": "half_sine", "duration_s": 0.2}},
 "end_s": 1.5,
 "probes": [{"label": "front wall", "at_mm": [3, 5, 0]}],
 "view": {"checks": [{"kind": "fill_level"},
                     {"kind": "wall_pressure", "limit_Pa": 2000}]}}
```

- The part is the container. The liquid fills its inside: the space it encloses, closed or open on sides
  of its bounding box (an open-top tank opens on `z_max`). An open side nobody names is open to the air
  at 0 Pa (liquid that reaches it spills out). A part with no inside is a study error.
- `material` is not needed. It is the structure's, given in `map_to_structure.material` (or the top-level
  `material`), and only a mapped study needs one.
- `fluids` (optional): `liquid` is `"water"` (998.2 kg/m³, 1.002e-3 Pa·s, 20 °C), `"oil"` (870, 0.1),
  `"glycerine"` (1261, 1.41) or `{"density_kg_m3", "viscosity_Pa_s", "name"}`; `gas` is `"air"` (1.204,
  1.81e-5) or an object. The liquid must be the denser. `surface_tension_N_m` (default 0: none) is a
  number or `"auto"` (water against air, 0.0728 N/m); it matters for small parts (millimetres) and
  bubbles, not for a tank.
- `fill` (optional, default half full): exactly one of
  - `{"level_mm": 25}`: the liquid's surface this far above the inside's floor (along gravity);
  - `{"fraction": 0.5}`: this share of the inside's volume, level;
  - `{"box_mm": [[x0, y0, z0], [x1, y1, z1]]}`: liquid inside this box only (a dam about to break);
  - `{"bubble": {"center_mm": [x, y, z], "radius_mm": r}}`: a full part with a bubble of gas.
- `gravity_m_s2` (optional): `[0, 0, -9.80665]` by default.
- `acceleration` (optional): the part's own acceleration, the way it is shaken, braked or turned:
  `direction` (`[x, y, z]`), `amplitude_g`, and `history` as in [transient.md](transient.md) (a table
  `[[t_s, factor], ...]`, `{"shape": "step"}` held (the default), `"ramp"` or `"half_sine"` with
  `duration_s`) or `{"shape": "sine", "frequency_Hz": f}` (shaken back and forth).
- `inlets` / `outlets` (optional, filling and draining): each names an open side of the part, as in
  [cfd.md](cfd.md): an inlet `{"opening": "z_max", "velocity_m_s": 0.2, "fluid": "liquid"}` (or `"gas"`),
  an outlet `{"opening": "z_min", "pressure_Pa": 0}`.
- `end_s` (optional): how long to follow it, s. Default: three periods of the first sloshing mode.
- `step_s` (optional, default `"auto"`): the largest time step, s. Auto is a fortieth of the first
  sloshing period; steps also shrink so the fastest fluid crosses at most half an element a step.
- `walls` (optional): `"slip"` (default: the fluid slides along the walls, so the waterline moves) or
  `"no_slip"`.
- `probes` (optional): vertical lines, each `{"label", "at_mm": [x, y, z]}` (any point on the line); the
  liquid's height along each is followed over time. With none, two are placed at the walls along the shake.
- `map_to_structure` (optional): `{"material", "fixtures"}`, as in [cfd.md](cfd.md).
- `view.checks`:
  - `{"kind": "fill_level"}`: the highest the liquid rises above the inside's floor, anywhere (or at
    `"probes": ["front wall"]`), against `limit_mm` (default: the brim, the inside's height). Titles:
    "Spills over" / "Close to the brim" / "Stays in". Close at 90 %.
  - `{"kind": "wall_pressure", "limit_Pa": 2000}`: the hardest the fluids press on the walls at any time.
  - `stress` and `displacement` when mapped.

## What comes out

- A series of time frames (up to 24: evenly spaced, plus the moments the liquid rises highest, presses
  hardest and pushes hardest). The viewer's Time scrubber opens on the highest rise; Play runs them.
- On the part's wetted walls, per frame: `water_fraction` (1 where the liquid touches the wall, 0 where
  the gas does; outer faces read 0) and the wall `pressure` (Pa, gauge: 0 at an open side, or at the top
  of a sealed part).
- Curves over time (sidecar `curves`): `fill_level_mm` (the highest point of the surface), `height_<probe>_mm`,
  `sloshing_force_{x,y,z}_N` (the fluids' push on the part, less its push at rest, which is their weight),
  `moment_{x,y,z}_N_m` (about the inside's floor, below its middle), `max_wall_pressure_Pa`,
  `volume_change_percent`.
- Summary: `peak_fill_level_mm` and when, `brim_mm`, `probes` (peak, when, final), `max_wall_pressure_Pa`,
  `force_N` (`at_rest`, `sloshing_peak`, `sloshing_peak_N` and when), `moment_N_m`, `first_sloshing_Hz`
  (linear theory, below), `volume` (start, end, change, `net_inflow_L` through the openings, `error_percent`
  against what came in and went out, the largest per-step drift before it was put
  back), `max_speed_m_s`, `interface_mm` (how thick the smeared surface is), `fill.words` ("Half full of
  water"), the mesh and the march.
- The interface's 0.5 iso-surface is not drawn in the GLB (the GLB is the part); the water fraction on
  the walls and the probe heights show where the surface is.

## How it is solved

Taylor-Hood elements (quadratic velocity, linear pressure) on netgen's tetrahedra of the inside, density
and viscosity from a level set (the signed distance to the surface, smoothed over about 0.35 element
each side), surface tension as a continuum force, BDF2 in time with one linear solve a step. The
hydrostatic pressure is split off analytically from the level set, so a still tank stays still to
round-off on any mesh. That split is exact only while the level set is a distance, so it is
re-distanced from its zero level whenever the flow has stretched or squeezed it anywhere along the
surface, and an inlet lets its fluid in upwind at its own speed rather than pinning the inlet to it.
The liquid's volume is put back every step (it is conserved to round-off, less what leaves through an
open side, plus what an inlet brings).

## Judging the answer (hand checks)

- Still liquid: the floor pressure is ρ g h (water, 25 mm deep: 245 Pa); the push on the floor is the
  liquid's weight.
- The first sloshing mode of a rectangular tank, linear theory: ω² = g k tanh(k h), k = π / L, with L the
  length along the shake and h the depth (60 mm long, 25 mm deep: 3.35 Hz). Small sloshes follow it; the
  engine reads its period within 5 % (2-4 % at about 12 elements along L). Shaken near that frequency
  the slosh grows; well below it the surface just tilts by about the angle atan(a / g).
- A steady acceleration a tilts the surface to slope a / g: the rise at the wall is about (L / 2)(a / g).
- Filling through an inlet into a part with air in it: the inlet starts at once, and the air, a
  thousand times lighter, is what gets pushed out first, so the air's speed reads several times the
  inlet's (a half-full 10 mm duct fed at 0.05 m/s: about 0.35 m/s in the air at the top wall, mostly
  in the first step, easing after). Liquid spilling out of an open side falls at about free fall:
  nothing should outrun the inlet's speed plus sqrt(2 g H) over the part's height H. A
  `max_speed_m_s` well past that is a fault, not physics.
- Benchmarks the engine is tested against: the still column (floor pressure within 1 %, no spurious
  motion), the sloshing period (within 5 %), Hysing et al.'s rising bubble (Int. J. Numer. Meth. Fluids
  60 (2009) 1259, test case 1: rise velocity within 15 % on a coarse mesh, 5 % measured) and volume within
  1 % over a run.

## Limits

- Laminar and incompressible: no turbulence model, no compressible gas (a sealed air pocket does not
  compress).
- The interface is a few elements thick: features smaller than about two elements (droplets, thin
  films, spray) are smeared out, and a slosh smaller than an element is approximate. Mesh finer for
  small sloshes.
- Walls slide by default (no boundary-layer drag); the contact angle is not modelled.
- No phase change (evaporation, boiling, condensation), no mixing or foam, no heat.
- Air near the surface is carried along within the smeared band, so air speeds read high near it; the
  liquid's motion is not affected. `max_speed_m_s` is the fastest of either fluid, so it is usually the
  air's.

## When the model is big

Never refused. The ladder (`fit` in [study-file.md](study-file.md#fit)), in order:

- `adaptive_steps`: lets the step grow to a twentieth of the sloshing period, the fluid crossing at most
  one element a step (BDF2 then reads the period about 3 % long, against 0.8 % at the default 40 steps).
- `iterative`: GMRES with multigrid on the momentum and a pressure-Laplacian Schur complement, in place of
  the direct solver, when memory is what misses.
- `local_refine`: fine only in the band the surface sweeps (its level plus or minus how far the shake can
  move it), 2.5 times coarser above and below.
- `fluid_coarsen`: the whole fluid mesh 1.6 times coarser; it says how much the surface is smeared.

Each step is said in the result, with its accuracy cost where it has one.
