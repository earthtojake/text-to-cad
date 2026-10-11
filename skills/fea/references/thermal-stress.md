# Heat stress (`thermal_stress`)

It answers "it gets hot: does that stress it or warp it": the stress and movement that come from
the part's temperature, with any mechanical loads on top. The steady [`thermal`](thermal.md) solve
runs first, on the same mesh, and its temperatures drive the static solve. The plain word is Heat
stress.

## When to use it

- "It's bolted down at both ends and gets to 120 °C: does it buckle the brackets or crack",
  "how much does it grow", "will the hot side bow".
- A part held where it would like to grow (clamped, bolted to a cooler or a different metal), or
  heated unevenly (one hot side). A part free to grow and evenly heated grows without stress.

## The study

On top of the common keys in [study-file.md](study-file.md#common-keys):

```json
{"analysis": "thermal_stress", "material": "steel",
 "fixtures": [{"faces": ["#o1.f1"]}, {"faces": ["#o1.f2"]}],
 "temperatures": [{"faces": ["#o1.f2"], "C": 120}],
 "convection": [{"faces": ["#o1.f3", "#o1.f4"], "h_W_m2K": 10, "ambient_C": 25}],
 "reference_C": 20,
 "view": {"checks": [{"kind": "stress"}, {"kind": "displacement", "limit_mm": 0.1}]}}
```

- The heat: `temperatures`, `heat`, `convection` and `radiation`, exactly as a steady
  [`thermal`](thermal.md#the-study) study (at least one held temperature, convection or radiation;
  radiation as in [thermal.md](thermal.md#radiation): a part that only radiates settles where it
  radiates what it takes in, and that temperature drives the stress).
- `fixtures` (required) and `loads` (optional): as [static](linear-static.md), gravity and
  acceleration included.
- `reference_C`: the temperature at which the part is stress-free, as made or assembled (default
  20 °C). The stress comes from the change from it, α (T - reference).
- The material needs a conductivity and a thermal expansion (`conductivity_W_mK`,
  `expansion_per_K`; every table material has both). An assembly takes each part's own, so two
  metals bonded together bow as they would.
- Checks `stress` and `displacement`, as static ([linear-static.md](linear-static.md)).

## What comes out

- Everything static writes (peak von Mises, safety factor, displacement, reactions, the static
  findings), plus the `temperature` field, `max_temperature_C`, `min_temperature_C` and
  `reference_C` in the summary, and the thermal solve's own summary under the sidecar's `upstream`.
- An `info` finding `heated` says the temperature range against the stress-free one.
- Where the peak stress stands more than 1.1× above the field's 99th percentile (a clamped edge
  that cannot grow is singular in heat stress), the von Mises colours stop at that percentile so the
  rest of the part still reads; the field's entry carries `capped` (`quantile`, `peak`) and the
  colour bar says "≥". The stress check and the summary still judge the true peak, with static's
  notes on peaks at a fixture and peaks that rise on a finer mesh.
- The load control scales the temperature change and the mechanical loads together ("OK up to 1.6×
  this heat"): exact, because both act linearly. 2× means twice the rise above `reference_C`.
- CLI: the stress and displacement lines, then "temperatures 25 to 120 °C, stress-free at 20 °C".

## Judging the answer (a hand check)

- Free to grow (held at one end only): it grows ΔL = α L ΔT and carries no stress away from the
  fixed face. A 100 mm steel bar heated 100 °C grows 11e-6 × 100 × 100 = 0.11 mm; the solver
  matches within 1 %.
- Clamped at both ends: it cannot grow, so it is pressed by σ = -E α ΔT. Steel heated 100 °C:
  200 000 × 11e-6 × 100 = 220 MPa, near steel's yield, from heat alone. The solver matches within
  2 % in the middle, and the walls each push back with σ × area.
- Radiating: a part taking in Q and radiating it from area A settles at
  T = (Q / (ε σ A) + T∞⁴)^¼ (kelvin), and clamped it carries E α (T − reference). A 100 × 5 × 5 mm
  steel bar taking 1 W, radiating from every face at ε 0.9 into 20 °C, settles near 88 °C, so
  clamped at both ends it is pressed by about 150 MPa.
- A plate hot on one side and cool on the other bows toward the hot side; held flat, it carries
  about E α ΔT / (2 (1 - ν)) at its faces.
- A full `fixed` face also stops the part growing sideways, which stresses it near that face more
  than a bolted joint would: read the stress a little away from a fixture before redesigning.

## Limits

- One-way: the heat drives the stress; the movement does not change the heat.
- Linear and elastic, constant properties: E and α at room temperature, no softening when hot, no
  creep. A safety factor under 1 means it yields; how far is not modelled.
- Steady temperatures only; a stress at the hottest moment of a warm-up is not computed yet.

## When the model is big

Its ladder is static's ([linear-static.md](linear-static.md#when-the-model-is-big-the-static-ladder)),
with the thermal solve's own (an iterative solver for the temperatures) before it. Report every
`adapted:` step with its accuracy note.
