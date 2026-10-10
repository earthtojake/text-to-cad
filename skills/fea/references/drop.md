# Drop (estimate) (`drop`)

**An estimate, never an impact simulation.** It answers "what if I drop it" quickly: the drop
becomes one equivalent steady load, G g on the whole part, with the faces that hit the floor held
fixed, and that is solved as a static study. Say "estimate" every time you quote it, and say the
stopping distance or time you assumed: it sets the answer. For a deeper check, `impact` simulates
the impact itself (coming).

## When to use it

- "Will it survive a 1 m drop onto concrete", "what if it falls off the desk".
- A quick ranking of designs or drop orientations (which face to land on hurts most).
- Not for: how far it bounces, a crack growing, a thin shell denting, a part hitting another, or
  anything that depends on the stress wave. Those need `impact`.

## The study

On top of the common keys in [study-file.md](study-file.md#common-keys):

```json
{"analysis": "drop", "material": "abs",
 "drop": {"height_mm": 1000, "onto": ["#o1.f5"], "stop_mm": 2},
 "view": {"checks": [{"kind": "stress", "label": "Drop"}]}}
```

- `drop.height_mm`: how far it falls, in mm (1000 for 1 m).
- `drop.onto`: the faces that hit the floor. They are held fixed. No `fixtures` or `loads` keys: the
  drop makes both.
- How it stops, exactly one of:
  - `stop_mm`: the distance it takes to stop (constant deceleration). G = height / stop, so 1000 mm
    stopping in 2 mm is 500 g.
  - `impact_ms`: how long the impact lasts, as a half-sine pulse. The peak deceleration is
    π v / (2 τ), with the impact speed v = √(2 g h): 1 m stopping in 1.5 ms peaks at 473 g.
- `drop.direction` (optional): the way it falls, `[x, y, z]`, like `[0, 0, -1]` for straight down.
  Left out, it falls along the landing faces' mean outward normal (the bottom face's -Z for a part
  dropped flat). Give it when the landing faces face different ways (an edge or a corner landing).
- `drop.dynamic`: `true` also runs a `transient` check ([transient.md](transient.md)) on the same
  mesh: the landing faces held and shaken by a half-sine pulse with the estimate's peak G g and the
  impact's speed change (τ = π v / (2 G g), which is `impact_ms` when given), followed until the first
  mode has rung once after the pulse, 2 % damping. The larger response is reported: when the pulse's
  peak stress passes the same peak load held steady, the static solve is repeated at that many times G
  (an equivalent steady load), so every number, field and check carries the larger answer. The
  summary's `dynamic` block gives `pulse_ms`, the transient's `max_von_mises_MPa`, `factor` (its peak
  over the steady one), `first_mode_Hz`, `governs` and `G_reported`; a CLI line and an info finding
  `drop_dynamic` say it in words. A part that rings much faster than the pulse answers it as the
  steady load (factor about 1, the estimate governs); one whose first mode is near 1 / (1.3 τ) can
  reach about 1.7×. Leave it out (or `false`) for the estimate alone.
- The material needs a density (every table material has one).
- Checks: `stress` (labelled "Drop" unless you give a label) and `displacement`, as for static.

### Choosing the stopping distance

Nothing in the part tells the solver how it stops: the floor and whatever crushes do. Pick a
number, say it, and offer a range when the answer is close:

- Hard plastic or metal on concrete or tile: 0.5 to 2 mm, or 0.5 to 2 ms.
- Onto wood, a carpet, or with a rubber foot or bumper: 2 to 10 mm.
- Inside packaging foam: the foam's crush, often 10 to 50 mm.

Halving the stopping distance doubles the load and every stress, so a part that passes at 2 mm with
a safety factor under 2 fails at 1 mm.

## What comes out

- The summary carries `estimate: true`, `estimate_line`, and `drop`: the height, the stop, the
  impact speed (m/s), `G`, the travel `direction` and the `acceleration_g` the static solve used.
  Every static number is there too: peak von Mises, safety factor, displacement, applied force
  (mass × G g) and the reactions that balance it.
- The CLI's first line is the estimate line, word for word:
  "Estimate: 1 m drop stopping in 2 mm, 500 g equivalent static load; not an impact simulation
  (analysis impact simulates the impact)".
- The GLB's `extras.analysis` has `estimate: true`, `tier: 2` and the limits; the viewer's verdict
  reads "Estimate · OK up to 1.6× this drop". `extras.study.drop` echoes the drop, and the
  equivalent load is echoed in `loads` as an `acceleration`.
- An `info` finding `drop_estimate` says it is an estimate and names the stopping distance assumed.
- The load control scales the drop: 2× is the same drop stopping in half the distance.

## Judging the answer (a hand check)

- The applied force is mass × G × 9.81 N: a 6 cm³ ABS block (6.24 g) at 500 g is 30.6 N.
- A part landing flat on its base, loaded by its own inertia: the stress grows with its height above
  the base, σ ≈ ρ · G · g · h. A 10 mm tall ABS block at 500 g: 1.04e-9 × 500 × 9806.65 × 10 ≈
  0.05 MPa, small. Stress concentrates where mass hangs off a thin section: a boss on a thin wall,
  a cantilevered tab, a heavy part on a thin stand.
- An overhanging arm of length L, landing on its base, is a cantilever under its own weight times G:
  root stress ≈ G × (its weight per length) × L² / 2 / its section modulus.

The result is exactly the static study with `onto` fixed and an `acceleration` of G g pointing away
from the floor: the run equals that study to the last digit.

## Limits

- One equivalent steady load: no stress wave, no rebound, no vibration after the hit, no floor
  stiffness, no contact beyond the faces held, no damage or permanent bending. Real peaks at the
  impact point and in fast-ringing thin features can be higher.
- The landing faces are held perfectly rigid, which stiffens the part near them.
- Linear material below yield: a safety factor under 1 means it yields or cracks; how badly is not
  modelled.
- Report it as an estimate of an equivalent steady load, with the stopping distance assumed.

## When the model is big

Its ladder is static's: an iterative solver, a mesh kept fine at the peak and coarse away from it,
small far fillets left out, simpler elements, half a symmetric part
([linear-static.md](linear-static.md#when-the-model-is-big-the-static-ladder)). Report every
`adapted:` step with its accuracy note.
