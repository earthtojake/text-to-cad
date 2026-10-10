# Heat over time (`thermal_transient`)

It answers "how hot does it get during a warm-up or a duty cycle, and when is it hottest":
temperature against time from a starting temperature, with heat, held temperatures and air that can
switch on and off. The plain word is Heat over time.

## When to use it

- "How hot after ten minutes", "how long until it reaches 60 °C", "a 5-minute burst every hour",
  "it cools down between shots".
- A part that never settles in the time that matters (a short burst into a big block). For "once it
  has settled", the steady [`thermal`](thermal.md) is faster and exact.

## The study

On top of the common keys in [study-file.md](study-file.md#common-keys):

```json
{"analysis": "thermal_transient", "material": "aluminum-6061-t6",
 "initial_C": 25, "end_s": 600, "step_s": "auto",
 "heat": [{"faces": ["#o1.f7"], "W": 15, "history": [[0, 1], [300, 1], [301, 0]]}],
 "convection": [{"faces": ["#o1.f3"], "h_W_m2K": 10, "ambient_C": 25}],
 "view": {"checks": [{"kind": "temperature", "max_C": 85}]}}
```

- `temperatures`, `heat`, `convection`: as in [thermal.md](thermal.md#the-study).
- `history` on any of them: a schedule, `[[t_s, factor], ...]`, straight lines between its points,
  flat before the first and after the last. The factor multiplies the entry's `W`, `W_per_m2`, `C`
  or `ambient_C`. The example heats at 15 W for 300 s, then switches off within a second.
- `initial_C`: the whole part's temperature at t = 0 (default 20 °C).
- `end_s`: how long to follow it, in seconds (required).
- `step_s`: the time step, or `"auto"` (default): a two-hundredth of `end_s`. Smaller steps follow
  fast changes better; a step shorter than the fastest change you care about is enough.
- No anchor is required: an insulated part warming up has an answer over time. Something must
  change its temperature (a `heat`, `temperatures` or `convection` entry).
- The material needs a conductivity and a specific heat (`conductivity_W_mK`,
  `specific_heat_J_kgK`; every table material has both) and its density.
- Check `temperature`: `max_C`, optional `faces`, judged on the highest temperature over all time.
  Its `at` says when (`time_s`) and which frame; the viewer jumps there when the check is chosen.
  It is measured from the coolest temperature the study sets (held, ambient or `initial_C`).

## What comes out

- Fields `temperature` and `heat_flux`, per frame: up to 24 frames, evenly spaced from t = 0 to
  `end_s`, plus the hottest step. The viewer opens on the hottest frame with a Time scrubber, and
  Play runs the frames.
- Curve `max_temperature_C` against time (the sidecar's `curves`), at every step.
- Summary: `max_temperature_C` and `max_at_s` (the hottest moment), `max_at_mm`,
  `final_max_temperature_C`, `min_temperature_C`, `max_heat_flux_W_m2`, `initial_C`, `end_s`,
  `step_s`, `steps`, `adaptive`, the smallest and largest step, `frames`, `reference_C`, `checks`.
- CLI: "hottest 64 °C at 5 min, at [x, y, z] mm; 41 °C at the end" and "followed from 25 °C for
  10 min in 200 steps".
- Findings: the temperature check's (as `thermal`), and `still_heating` (info) when the hottest
  moment is the last: run longer, or solve it steady.

## Judging the answer (a hand check)

- A small, conductive part cools (or warms) as one lump when h × (volume / area) / k is under 0.1:
  T(t) = T_air + (T_0 - T_air) e^(-t/τ), τ = ρ c V / (h A). A 10 mm aluminium cube in h = 100 has
  τ = 2700 × 896 × (0.01 / 6) / 100 = 40 s; from 100 °C in 20 °C air it is at 31 °C after 80 s. The
  solver matches within 1.5 % at the automatic step.
- Heat into an insulated part raises its mean temperature by P t / (m c): 5 W into 2.7 g of
  aluminium for a minute is 124 °C. Every joule put in is stored.
- Settling takes about 3 to 5 τ; if `still_heating` appears, the steady `thermal` gives where it ends.

## Limits

- As [thermal.md](thermal.md#limits): conduction with constant properties, no radiation, `h` given.
- Backward Euler takes each step's heat at the step's end: a heater that switches off between two
  steps is missed for that step. Keep `step_s` below the shortest on-time in the schedule.
- Backward Euler damps fast changes a little: with the automatic step the lumped cube runs about
  1 % warm at 2 τ.

## When the model is big

It runs at any size and any length. The ladder may take an iterative (multigrid) solver, a mesh kept
fine where it is hottest, small far fillets left out, simpler elements, half a symmetric part, and
`adaptive_steps`: the time step grows while the temperatures change slowly and shrinks where they
change fast, each step checked against two half steps (step doubling, kept within 0.2 % of the
temperature range a step). Each is an `adapted:` line with its accuracy note; report every one.
