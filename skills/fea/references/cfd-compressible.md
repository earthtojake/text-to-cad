# Fast gas flow (`cfd_compressible`, lite)

It answers what [Flow](cfd.md) answers, "what does the gas lose through or around the part, how
fast does it go, how hard does it push on the part", when the gas is fast enough that its density
changes with its speed: past about **Mach 0.3** (about 100 m/s in air). A nozzle, a valve or an
orifice under a real pressure ratio, a high-speed air duct, a gas jet. It also says how close to
the speed of sound the gas gets, whether the passage chokes (the mass flow stops growing with the
pressure ratio), and where a shock stands. It solves the steady flow of an ideal gas in-house (no
outside software). With `map_to_structure` the wall pressure is applied to a static solve of the
part, so its stress and displacement come too. The plain word is Fast gas flow.

**Limits, written into every result: "Steady, ideal gas, adiabatic (one total temperature); an
inviscid core with frictionless walls past the laminar range, laminar walls in it; no turbulence
model; shocks are captured over a few elements."** Quote them whenever you quote a number.

## When to use it

- "How much air does this nozzle pass at 1.5 bar?", "does it choke?", "what Mach number does the
  throat reach?", "where does the shock stand?"
- "What pressure does this orifice / valve seat see at this pressure ratio?" (`map_to_structure`:
  "will it hold?")
- Any gas flow a `cfd` or `cfd_turbulent` result shows faster than about Mach 0.3 (the speed over
  343 m/s for air at 20 °C): their incompressible answer is off by a few percent at Mach 0.3 and
  badly past Mach 0.5.
- Not for liquids, slow gas (use [cfd](cfd.md) or [cfd_turbulent](cfd-turbulent.md): this one
  warns and gives the same answer), heat put in or taken out through the walls, combustion,
  anything time-varying, or a supersonic jet leaving the outlet (it warns; below).

## The study

On top of the common keys in [study-file.md](study-file.md#common-keys). Internal flow (through
the part), a reservoir at 1.5 bar absolute feeding a nozzle that blows into the room:

```json
{"analysis": "cfd_compressible",
 "mesh": {"size_mm": 1.5},
 "flow": {"kind": "internal", "gas": "air",
          "inlets": [{"opening": "x_min", "total_pressure_Pa": 150000, "total_temperature_C": 20}],
          "outlets": [{"opening": "x_max", "pressure_Pa": 101325}]},
 "view": {"checks": [{"kind": "mach", "limit": 0.8},
                     {"kind": "pressure_drop", "limit_Pa": 30000}]}}
```

A fixed mass flow instead: `"inlets": [{"opening": "x_min", "mass_flow_kg_s": 0.004,
"total_temperature_C": 20}]`. External flow (around the part): `{"kind": "external", "gas": "air",
"velocity_m_s": [150, 0, 0], "pressure_Pa": 101325, "temperature_C": 20}`.

- **Pressures are absolute** (1 atm is 101325 Pa), unlike `cfd`'s gauge pressures: the gas's
  density follows its absolute pressure.
- `flow.gas`: `"air"` (default: gamma 1.4, R 287 J/kg K, Sutherland viscosity), `"nitrogen"`,
  `"helium"`, `"co2"`, or `{"name", "gamma", "gas_constant_J_kgK", "viscosity_Pa_s"}` (the
  viscosity at 20 °C).
- Internal flow, openings as `cfd`'s (sides of the part's bounding box; run `cadgen fea faces`):
  - `inlets`: each `{"opening", "total_pressure_Pa" or "mass_flow_kg_s", "total_temperature_C"}`.
    The total pressure and temperature are the reservoir's (the gas at rest upstream). A total
    pressure must be above the outlet's. `"profile"` (`"uniform"` or `"developed"`) goes with a
    mass flow only.
  - `outlets`: each `{"opening", "pressure_Pa"}`, the static pressure the gas leaves into
    (default 101325).
- `flow.walls`: `"auto"` (default), `"slip"` or `"no_slip"`. Auto picks laminar no-slip walls in the
  laminar range (Re up to 2000 internal, 1000 external) and frictionless walls (an inviscid core)
  past it, where a laminar wall would be wrong and the core of a fast gas flow is nearly inviscid.
  With frictionless walls the pressure lost to wall friction is not counted; it says so.
- `mesh.size_mm`: the element size at the walls and openings (default as `cfd`: a quarter of the
  narrowest opening's hydraulic diameter). A shock is spread over about three elements: a finer
  mesh places it more sharply.
- `map_to_structure`: as `cfd`'s. The wall pressure applied is the pressure above the first
  outlet's (the room the part sits in).
- Checks: `mach` (`limit`, the fastest Mach number anywhere in the gas), `pressure_drop`
  (`limit_Pa`, inlet static to outlet static) and `velocity` (`limit_m_s`), each close past 0.9 of
  its limit; plus `stress` and `displacement` when mapped. The `mach` check's titles are "Too fast",
  "Close to the limit" and "Within the speed limit".

## What comes out

- Fields on the part's wetted surface: `pressure` (Pa above the outlet's, signed), `mach` (the gas's
  speed over its local speed of sound) and `temperature` (the gas's, °C: it cools as it speeds
  up, T = T0 / (1 + 0.2 M²) in air). Mapped: `von_mises` and `displacement`, and the part deforms.
- Summary: `mass_flow_kg_s` (in) and `outflow_kg_s`, `flow_balance`, `max_mach` and where,
  `max_velocity_m_s`, `outlet_mach`, `pressure_ratio` (the inlet's total pressure over the outlet's
  static), `inlet_total_pressure_Pa`, `inlet_pressure_Pa`, `outlet_pressure_Pa`,
  `pressure_drop_Pa`, `choked` (the gas reached Mach 1), `shock` (`at_mm`, its sharpness, the
  elements it spans; null without one), `mach` (`value`, `limit`, `regime`: subsonic, transonic or
  supersonic, `checked`), `walls`, `reynolds` (from the solved mass flow), the wall pressure, Mach
  and temperature ranges, `force_N`, `solve` (steps, residual, any continuation) and `fluid_mesh`.
- Findings: `mach_past_checked` (warning, below), `shock` (info: where it stands),
  `gas_flow_unsettled` (warning), `mach_over_limit` / `pressure_drop_over_limit` /
  `velocity_over_limit` (error) and their `_close_to_limit` (warning), `flow_balance`, and the
  static findings when mapped.
- A march that does not settle (a limit cycle at a shock or along a wall: its residual not halving
  in 40 steps stops it early, at its best state) is never a settled pass: every check reads
  `settled: false`, its label ends "(flow not settled)", a pass becomes `close`, and
  `gas_flow_unsettled` says so.

## The speed warning (never a refusal)

It solves whatever it is given. The fastest flow it is checked to is a normal shock standing in a
nozzle's diverging part with **Mach 1.8 just ahead of it as captured** (1.96 by the tables).
Past that, or when the gas leaves the outlet faster than sound, it still solves (or says how far
the solve got) and warns, in a sentence and as data (`summary.mach`, `extras.analysis.mach`):
"Mach 2.10 is past Mach 1.8, the fastest this solver is checked to: ...", or "... the gas leaves
the outlet faster than sound: the outlet's pressure is held there though a supersonic exit sets
its own ...". A supersonic exit (a nozzle blowing at its design pressure ratio or below) is not
modelled well: report the throat's numbers and the mass flow, which the exit does not change once
the throat chokes, and say the exit's are not to be trusted.

## Judging the answer (a hand check with the isentropic tables)

With p0 and T0 the reservoir's, M the Mach number and gamma 1.4 (air):

- T / T0 = 1 / (1 + 0.2 M²), p / p0 = (T / T0)^3.5, and A / A* = (1/M) [(1 + 0.2 M²) / 1.2]³.
  Mach 0.3: p / p0 = 0.939, Mach 0.5: 0.843, Mach 1: 0.528.
- Subsonic nozzle: from the outlet's p / p0 get the exit Mach number, from it A_exit / A*, then
  every section's Mach number from its own A / A*. The solver matches the isentropic Mach number
  within 1 % at every section of a gentle nozzle at p_out / p0 = 0.95 and 0.92, with 1.6 mm
  elements in a 4 mm throat.
- Choking: once the throat reaches Mach 1, the mass flow is
  ṁ = p0 A_throat sqrt(gamma / (R T0)) (2 / (gamma + 1))^3 = 0.0404 p0 A_throat / sqrt(T0) (SI)
  and no lower outlet pressure raises it. The solver matches it within 0.2 %.
- A normal shock: in a converging-diverging nozzle with p_out / p0 between the subsonic-choked
  value and the one for a shock at the exit, a shock stands in the diverging part where
  p_exit A_exit / (p0 A_throat) fixes the exit Mach number, the total pressure it lost fixes the
  shock's Mach number, and that Mach number's A / A* is where it stands. The benchmark (exit to
  throat area 1.69, p_out / p0 = 0.75): the tables put it 12.6 mm into a 25 mm diverging part with
  Mach 1.69 ahead of it; the solver puts it within 2 % of the diverging length, with the Mach
  number ahead smeared to about 1.5. At p_out / p0 = 0.6 (Mach 1.96 ahead) within 2 % too.
- Slow flow: under Mach 0.3 the answer is `cfd`'s; the solver matches cfd's laminar pipe
  pressure drop within 1 % there (and warns that cfd gives the same answer).

## Limits

- Steady, ideal gas (p = ρ R T), adiabatic with one total temperature (the inlets' mean): the
  temperature follows the speed. No heat through the walls, no combustion, no condensation.
- Walls are frictionless (an inviscid core) past the laminar range, laminar no-slip in it. There
  is no turbulence model: friction loss in a long fast gas line is not counted (frictionless) or a
  lower bound (laminar walls past the laminar range, which it warns about).
- Shocks are captured by an added bulk viscosity over about three elements: their place is good
  to about two elements, the Mach number just ahead of a strong shock reads low, and a shock
  touching the outlet or the inlet is unreliable.
- An outlet holds its static pressure: a supersonic outflow is not modelled (it warns).
- One part only; openings are bounding-box sides; the wall values are carried to the part's faces
  from the nearest fluid node on the same face.

## When the model is big or the flow is hard

It runs at any size. The ladder may take, each an `adapted:` line to report:

- `fluid_coarsen`: as `cfd`'s (external flow's free stream and far field coarser, the walls kept).
- `continuation`: when the pressure ratio could choke the passage (the drive expanded to the outlet
  passes Mach 0.5), the pressure difference is stepped up (50 %, then 100 %), each stage from the
  one before: "Reached the full pressure ratio in steps (50%, 100% of the drive) from a gentler
  flow, so the march starts the choked flow near its answer". Exact (the same steady flow).
  Without the rung, a march that does not settle falls back to it by itself.
- `iterative`: GMRES with a multigrid preconditioner instead of a direct factor; a Krylov solve
  that stalls is finished by the direct solver, and it says so.
