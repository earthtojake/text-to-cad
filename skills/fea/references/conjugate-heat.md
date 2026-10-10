# Cooled by flow (`conjugate_heat`, lite)

It answers "how hot does the part run when a fluid flows through or past it, and how warm does the
fluid come out": the flow is solved first (the laminar [`cfd`](cfd.md) solver, or the k-omega SST
[`cfd_turbulent`](cfd-turbulent.md) one), then the fluid's temperature and the part's are solved
together, the heat crossing the wetted walls. In-house, no outside software. The plain word is
Cooled by flow.

**Limits, written into every result: "Steady; the flow carries the heat but is not changed by it
(no buoyancy, constant properties)."** Quote them whenever you quote its numbers. The flow's own
limits ([cfd.md](cfd.md), [cfd-turbulent.md](cfd-turbulent.md)) hold too.

## When to use it

- "How hot does the chip get on this liquid cold plate at 1 L/min", "is this cooling channel
  enough", "how warm does the water come out".
- "What heat transfer coefficient does this flow give": instead of guessing `h` for a `thermal`
  study's `convection`, compute it here. A common route: solve this once, read the mean
  `heat_transfer_coefficient`, then iterate the part's design with the cheaper `thermal`.
- A part warming the air that blows past it (`external`).
- Not for natural convection (a fluid moved by its own heat: a still room, a heat sink with no fan),
  boiling or condensing, a fluid whose density or viscosity changes much with temperature, or a
  flow that changes over time. Not for radiation as well as flow: add `radiation` in a `thermal`
  study with the `h` this one finds.

## The study

On top of the common keys in [study-file.md](study-file.md#common-keys):

```json
{"analysis": "conjugate_heat", "material": "aluminum-6061-t6",
 "mesh": {"size_mm": 0.75},
 "flow": {"kind": "internal", "fluid": "water", "regime": "auto",
          "inlets": [{"opening": "x_min", "velocity_m_s": 0.2, "temperature_C": 20}],
          "outlets": [{"opening": "x_max", "pressure_Pa": 0}]},
 "heat": [{"faces": ["#o1.f3"], "W": 40}],
 "convection": [{"faces": ["#o1.f5"], "h_W_m2K": 10, "ambient_C": 25}],
 "view": {"checks": [{"kind": "temperature", "max_C": 70, "faces": ["#o1.f3"], "label": "Chip side"},
                     {"kind": "pressure_drop", "limit_Pa": 5000}]}}
```

External (a part in a stream):

```json
{"analysis": "conjugate_heat", "material": "aluminum-6061-t6",
 "flow": {"kind": "external", "fluid": "air", "velocity_m_s": [2, 0, 0], "temperature_C": 25},
 "heat": [{"faces": ["#o1.f1"], "W": 5}]}
```

- `flow`: everything a [`cfd`](cfd.md#the-study) study's `flow` takes (`kind`, `fluid`, `inlets`
  with `opening`, `velocity_m_s` and `profile`, `outlets`, an external `velocity_m_s`), plus:
  - each inlet's `temperature_C` (required), or an external flow's `flow.temperature_C`;
  - `regime`: `"auto"` (default: laminar below Re 2000 inside the part, Re 1000 around it, turbulent
    above), `"laminar"` or `"turbulent"`. A turbulent flow takes `turbulence_intensity` as
    [cfd-turbulent.md](cfd-turbulent.md#the-study) says; a laminar one refuses it.
  - a fluid given by its numbers needs `conductivity_W_mK` and `specific_heat_J_kgK` beside its
    density and viscosity, like
    `{"name": "oil", "density_kg_m3": 870, "viscosity_Pa_s": 0.03, "conductivity_W_mK": 0.13, "specific_heat_J_kgK": 2000}`.
    `"water"` (0.606 W/(m K), 4181 J/(kg K)) and `"air"` (0.0263 W/(m K), 1007 J/(kg K)) know theirs
    (20-27 °C, Incropera's tables).
- The part: `material` (its `conductivity_W_mK`; every table material has one), and the thermal
  keys of [thermal.md](thermal.md#the-study) on its faces: `heat` (a chip, a heater), `temperatures`
  (a face held) and `convection` (air on the faces the flow does not wet). No anchor is needed: the
  fluid coming in at its temperature takes the heat away. No `radiation` here (see When to use it).
- `mesh.size_mm` is the element size of both the part and the flow's walls and openings. Left out,
  the part takes its default and the flow its own (a quarter of the narrowest opening's hydraulic
  diameter laminar, a tenth turbulent). A heat answer needs the flow's wall layer resolved: give
  about 6-8 elements across a channel for a laminar flow.
- One part, as a flow study (name it with `--occurrence` in an assembly).
- Checks: `temperature` (the part; `max_C`, optional `faces`, measured from the coolest
  temperature the study sets, here usually the inlet's), `pressure_drop` (`limit_Pa`) and `velocity`
  (`limit_m_s`). None by default.

## What comes out

- Fields on the part's surface:
  - `temperature`: the part's (°C, signed; the colour bar runs from its own coolest);
  - `fluid_temperature` ("Fluid temperature"): the speed-weighted mean temperature of the fluid
    within one passage width of each wetted point (the local bulk temperature; for an external flow,
    within two wall elements of it); a face the fluid does not wet reads the inlet's temperature;
  - `wall_heat_flux` ("Heat into the flow", W/m², signed: negative where the fluid heats the part);
  - `heat_transfer_coefficient` (W/(m² K)): that flux over the wall's temperature less the local
    fluid temperature (internal) or the free stream's (external); 0 where the two are the same;
  - `pressure` (the wall pressure, Pa), as `cfd`'s.
- Nothing deforms; there is no load control. The viewer opens on Temperature with the other fields in
  Field, and its takeaway leads with "Laminar · " or "Turbulent · ".
- Summary: `regime`, `reynolds`, `prandtl`, `peclet`; the part's `max_temperature_C`,
  `min_temperature_C`, `max_at_mm`; the fluid's `inlet_temperature_C`, `outlet_temperature_C` (all
  outlets mixed), `outlet_temperature_by_balance_C` (the inlet's plus m c_p ΔT's rise), each of the
  `outlets`, `max_fluid_temperature_C`; `heat_to_fluid_W` (what the walls put in), `heat_carried_W`
  (m c_p ΔT out), `fluid_balance` (their mismatch, a share), `mass_flow_kg_s`, `part_heat_in_W`,
  `part_balance`; `wetted_area_mm2`, `mean_wall_temperature_C`, the wall heat flux's range, the
  `mean_heat_transfer_coefficient_W_m2K` (on the log-mean temperature difference, wall to fluid,
  in to out, as for a heat exchanger) and its `nusselt` number on the inlet's hydraulic diameter;
  the flow's `pressure_drop_Pa`, `flow_balance`, `flow_rate_L_min`, `max_velocity_m_s`, wall
  pressure range; `fluid_mesh`; `checks`.
- CLI: "internal laminar flow of water: Re 40, Pr 6.9", "part hottest 24.1 °C ...", "fluid in at
  20 °C, out at 21.89 °C; walls put 1 W into it, it carries 1 W out", "mean heat transfer
  coefficient 1154 W/m²K (Nusselt 7.62) over 300 mm² wetted", "pressure drop ...".
- Findings: the temperature check's (as `thermal`), the pressure and speed checks', `fluid_warms`
  (info: the outlet temperature and the heat carried), and warnings: the Reynolds number outside the
  regime solved, a heat balance off by more than 1 % (`fluid_heat_balance`: the solve did not
  settle), the mixed outlet temperature and the balance's apart by more than 1 % of the rise
  (`outlet_temperature_spread`: a turbulent flow's wall function lets a little fluid slip through
  its walls, which a small rise in a large flow magnifies; trust the balance's), an unsettled flow.

## How it is solved

- The flow: exactly the `cfd` (laminar) or `cfd_turbulent` solve of the same `flow`, on the fluid's
  own mesh. It is not changed by the heat.
- The fluid's temperature: steady advection-diffusion, ρ c_p u · ∇T = ∇ · ((k + ρ c_p ν_t / 0.85) ∇T),
  on linear elements, stabilised by SUPG. Linear temperature is the flow's own pressure space, so
  the solved velocity carries heat with no loss: what the walls put in leaves as m c_p ΔT to the
  solver's tolerance. An inlet brings fluid in at its temperature by Danckwerts' condition (the
  enthalpy coming in is fixed; the inlet plane is not held, which would make it a false heat sink
  next to a hot wall).
- The part: the `thermal` conduction system on its own mesh.
- The tie: the meshes do not match at the wetted walls, so each of the fluid's wall points takes the
  part's temperature at the same place (the part's quadratic surface interpolated there) and gives
  its heat back through the same weights, so no heat is lost between them. Laminar: the two are one
  temperature at the wall. Turbulent: the wall function's layer lies between them, a film of the
  thermal law of the wall (h = ρ c_p u_τ / T⁺, Jayatilleke's T⁺ with Pr_t 0.85).
- The fluid and the part are solved as one system (direct, or GMRES with an incomplete LU).

## Judging the answer (hand checks)

- The fluid's energy balance: T_out = T_in + Q / (m c_p), with m = ρ V A at the inlet. 1 W into a
  4 mm bore of water at 0.01 m/s (m = 1.25e-4 kg/s) warms it 1.9 °C. The solver's books close to
  1e-6; the mixed outlet temperature matches the balance on the solved flow to 1e-6, and the solved
  flow is within 1 % of ρ V A.
- Laminar, fully developed flow in a round pipe: Nu = h D / k = 3.66 with the wall at one
  temperature, 4.36 with an even heat flux into it; past the inlet, within about 0.05 Re Pr D. On a
  32 mm pipe of 4 mm bore at Pe 40 (0.5 mm elements), the bulk temperature's decay gives Nu 3.74
  (+2.2 %); at 0.4 mm elements, 3.655 (−0.1 %).
- Turbulent flow in a pipe: Dittus-Boelter Nu = 0.023 Re^0.8 Pr^0.4 (developed, Re > 10 000; a
  rough guide from about 4000), Gnielinski's correlation from 3000. A short channel reads higher
  for its entry. The 24 mm cold plate at Re 4000 reads a mean Nu of 38 (Dittus-Boelter 37.8).
- The part: from the wall to the hottest point it is conduction, as `thermal`'s hand checks; the
  wall sits about Q / (h A) above the fluid.

## Limits

- Steady; the flow is solved first and the heat does not change it: no natural convection, no
  property that varies with temperature (give properties at the mean fluid temperature), no boiling.
- Laminar entry and developed flow are resolved by the mesh: too few elements across a channel read
  the heat transfer coefficient high. Turbulent walls use wall functions (y⁺ ≥ 30 by construction),
  so the heat transfer coefficient is the law of the wall's, good to the 10-25 % of correlations.
- A wetted face is one temperature with the fluid at the wall (laminar): no contact resistance, no
  coating. The flow's own limits: one part, openings on sides of the bounding box; a channel with
  sharp internal corners can fail the laminar flow solve ("factor is exactly singular"): round
  them, or use a round bore.

## When the model is big

It runs at any size. The ladder may take: iterative solvers for the flow and the heat, the flow's
core coarsened away from its walls (`fluid_coarsen`: the heat it takes from the walls may read a
little high; the walls keep their size and the energy balance stays exact), Reynolds continuation
or longer pseudo-time steps for the flow (`continuation`), and the part's mesh kept fine where it is
hottest and coarse away from it (`local_refine`, with how far the hottest temperature moved between
the passes). Each step is an `adapted:` line with its accuracy note; report every one.
