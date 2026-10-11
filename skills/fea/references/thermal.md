# Heat (`thermal`)

It answers "how hot does it get once it has settled": the steady temperature across the part from
faces held at a temperature, heat put in (a chip, a heater, a motor), heat carried away by air
or liquid (convection) and heat radiated (to the surroundings, and between faces that see each
other). The plain word is Heat.

## When to use it

- "How hot does the chip side get", "will the case stay under 60 °C", "is this heat sink enough".
- Steady running: the temperatures once nothing changes any more. For a warm-up, a duty cycle or
  "how long until it is too hot", use [`thermal_transient`](thermal-transient.md). For "does the heat
  stress or warp it", use [`thermal_stress`](thermal-stress.md), which runs this first.

## The study

On top of the common keys in [study-file.md](study-file.md#common-keys):

```json
{"analysis": "thermal", "material": "aluminum-6061-t6",
 "temperatures": [{"faces": ["#o1.f1"], "C": 25}],
 "heat": [{"faces": ["#o1.f7"], "W": 15}, {"faces": ["#o1.f8"], "W_per_m2": 2000}],
 "convection": [{"faces": ["#o1.f3", "#o1.f4"], "h_W_m2K": 10, "ambient_C": 25}],
 "view": {"checks": [{"kind": "temperature", "max_C": 85, "faces": ["#o1.f7"], "label": "Chip side"}]}}
```

- `temperatures`: faces held at a temperature, in °C (a cold plate, a wall the part is bolted to,
  water at a known temperature).
- `heat`: heat going in through faces. `W` is the total power, spread evenly over all its faces'
  area; `W_per_m2` is a heat flux. Exactly one of the two per entry. A negative value takes heat out.
- `convection`: air or liquid carrying heat away. `h_W_m2K` is how well it does (still air about
  5-10, a fan 25-100, water 500 or more), `ambient_C` its temperature. A face with nothing on it is
  insulated: no heat crosses it.
- `radiation` (optional): faces radiating heat, see [Radiation](#radiation) below.
- **At least one `temperatures`, `convection` or `radiation` entry is required.** A part only
  heated, with nowhere for the heat to go, has no steady temperature, and the study is refused with
  that sentence. Add the air around it, the face it sits on, or what it radiates to.
- The material needs a thermal conductivity (`conductivity_W_mK`; every table material has one). An
  assembly takes each part's own, and heat crosses bonded joints as if they were one piece (no
  contact resistance).
- No `fixtures`, `loads` or `margin`: nothing moves.
- Check `temperature`: `max_C`, the hottest it may get, and optional `faces` (else the whole part).
  It is measured from the coolest temperature the study sets (the lowest held temperature or
  ambient, the result's `reference_C`), so 84 °C against a 100 °C limit with 25 °C air has used
  59/75 = 0.79 of its room; past 0.9 it is close, past 1 it fails. A limit at or under that
  reference is refused. The row reads "Hottest 84 °C, limit 100 °C"; with no check, the verdict
  shows none.

## Radiation

```json
{"radiation": [{"faces": ["#o1.f3"], "emissivity": 0.9, "ambient_C": 25},
               {"faces": ["#o1.f8", "#o1.f9"], "emissivity": 0.8, "ambient_C": 25, "surface_to_surface": true}]}
```

- Each entry's faces radiate as a grey, diffuse surface: `emissivity` (0 to 1, required) and the
  surroundings' temperature `ambient_C`. Emissivity depends on the finish far more than on the
  alloy, so there is no table value: polished aluminium about 0.05, bare machined aluminium 0.1,
  anodised or painted 0.8-0.95, oxidised steel 0.8. Ask, or say which you assumed.
- Without `surface_to_surface`, a face sees its surroundings whole: it loses ε σ (T⁴ − T∞⁴) per area,
  as if nothing of the part stood in its way. Right for an outside face of a convex part.
- With `"surface_to_surface": true`, the entry's faces also exchange heat with every other such
  face (fins facing each other, the inside of a box, two plates). cadgen computes the view factors
  itself: the faces' surface triangles grouped into at most 300 patches (one per face only if more
  faces than that radiate), each pair's view factor by
  the contour integral from every triangle's centroid, obstruction by ray casting against every
  surface triangle of the part. Whatever a face does not see of the other radiating faces goes to
  its entry's `ambient_C`; a face nobody named counts as surroundings too (it blocks rays, but does
  not radiate back). The radiosity of the patches is solved exactly for grey surfaces.
- A face may be in one radiation entry only. Radiation is nonlinear (T⁴, in kelvin inside); the
  solve is Newton's method from the warmest temperature the study sets. A study without
  `radiation` solves exactly as before.
- The summary adds `radiation`: each entry's `net_W` out (negative where it takes heat in),
  `radiated_W`, and with surface-to-surface, the `view_factors` between the entries (row i: the
  share of entry i's radiation that reaches entry j), the `patches`, the method and the rays cast.
  The CLI adds "radiated 100 W from #o1.f6 (emissivity 0.9, to 25 °C)". `heat_out_W` counts it.

Hand checks for radiation:

- A plate radiating Q from area A to surroundings at T∞ (kelvin) settles at
  T = (Q / (ε σ A) + T∞⁴)^¼: 100 W from 0.01 m² at ε 0.9 into 25 °C is 398.8 °C. The solver
  matches the closed form to 0.001 % of the rise.
- Two black, directly opposed 50 mm squares 50 mm apart see each other by F = 0.1998 (the analytic
  formula); the solver's view factor is within 0.1 %, and the heat the cold one takes in,
  A F σ (T_h⁴ − T_c⁴), within 0.1 %.
- Radiation matters past about 100 °C, or for a dull part cooled only by still air: at 50 °C
  a black face loses about 6 W/m²K, comparable to still air's convection.

## What comes out

- Fields: `temperature` (°C; its colours run from its own coolest to its hottest) and `heat_flux`
  (the conducted heat flow's size, W/m², "Heat flow" in the viewer). Nothing deforms, and there is
  no load control.
- Summary: `max_temperature_C`, `min_temperature_C`, `max_at_mm`, `max_heat_flux_W_m2`,
  `heat_in_W`, `heat_out_W`, `heat_balance` (their mismatch as a share), `reference_C` and the
  `checks`. An assembly adds each part's `max_temperature_C` under `parts`.
- CLI: "hottest 84 °C at [x, y, z] mm, coolest 25 °C" and "heat in 15 W, out 15 W".
- What goes in comes out: a balance off by more than 1 % is a warning (and a `heat_balance`
  finding); it means the solve did not settle, so check it on a finer mesh before trusting it.
- Findings: `temperature_over_limit` (error) and `temperature_close_to_limit` (warning) per check,
  and `no_heat` (info) when nothing heats it.

## Judging the answer (a hand check)

- A slab held at two temperatures conducts Q = k A ΔT / L: a 10 × 10 mm aluminium bar 20 mm long,
  100 °C to 20 °C, passes 167 × 1e-4 × 80 / 0.02 = 66.8 W, and its temperature falls in a straight
  line. The solver matches this to well under 1 %.
- Heat out to air: Q = h A (T_surface - T_air). 15 W into a part with 0.01 m² of surface in still
  air (h = 10) needs 150 °C above the air: a hand check that tells you whether the answer is
  plausible, and that a heat sink or a fan is needed.
- A pin fin (a rod held hot at its base in air, its tip insulated): T_tip - T_air = (T_base -
  T_air) / cosh(mL), m = √(hP / (kA)). A 4 × 4 mm aluminium pin 50 mm long in h = 50 keeps 72 % of
  its base excess at the tip; the solver matches within 2 %.
- In series (a spreader bonded to a mount): the resistances L / (k A) add, and the joint sits where
  the drop across each matches its share.

## Limits

- Conduction with constant properties: no temperature-dependent conductivity or emissivity, no
  contact resistance at bonded joints.
- Radiation is grey and diffuse; a face that is not named radiates nothing and counts as the
  surroundings for those that see it; a transparent medium (no gas absorbs). View factors are
  between patches of up to a few hundred per study: a fine detail inside one patch is averaged.
- `h` is a number you give, not a flow calculation: a range (5-10 still air, 25-100 forced) is
  often the largest uncertainty. Say which you assumed.
- Steady state only: how long it takes to get there is `thermal_transient`.

## When the model is big

It runs at any size. The ladder may take: an iterative (multigrid) solver for the temperatures
(exact, said only when it matters), a mesh kept fine where it is hottest and coarse away from it,
small far fillets left out, simpler elements, half a symmetric part. Each step is an `adapted:` line
with its accuracy note; report every one.
