# Over time (`transient`)

Answers "what happens under a load that changes over time": a hammer blow, a
load switched on suddenly, a pulse, a push that ramps up, or the fixtures
jolted. It follows the movement and the stress through time from rest and
reports their peaks, when they happen, and how far the peak is above the
same load held steady.

## When to use it

- "A 50 N blow lasting 2 ms hits this tab: does it hold?" A force with a
  half-sine history.
- "The actuator slams on with 200 N: how far does the arm overshoot?" A
  force with a step history: an undamped part overshoots to twice its steady
  deflection.
- "The mount gets a 30 g, 6 ms jolt": a base `excitation` with a half-sine
  history.
- Use `static` when the load changes slowly compared with the part's first
  natural frequency (a ramp much longer than one period is static). Use
  `harmonic` for a steady sine, `shock` for a shock response spectrum, and
  `drop` (an estimate, with `"dynamic": true` for this analysis's check) or
  `impact` for a drop.

## Study

On top of the common keys in [study-file.md](study-file.md#common-keys):

- `fixtures`: required, as in static (`fixed` faces). A base shake moves them.
- `loads`: `force` and `pressure` on faces, as in static, each with a
  `history`: the factor on it against time, starting from rest at t = 0.
  - `{"shape": "step"}`: on at once and held.
  - `{"shape": "ramp", "duration_s": 0.002}`: rising from 0 to full over
    `duration_s`, then held.
  - `{"shape": "half_sine", "duration_s": 0.002}`: a pulse, sin(π t / τ) for
    `duration_s`, then 0.
  - `[[t_s, factor], ...]`: a table, times rising from 0, straight lines
    between the points, the first and last factors held before and after.
  - Body loads (`gravity`, `acceleration`) are not taken; shake the fixtures
    with `excitation` instead.
- `excitation` (optional, with or instead of `loads`):
  `{"type": "base", "direction": [0, 0, 1], "amplitude_g": 10, "history": {...}}`:
  every fixture moves together along `direction` with an acceleration of
  `amplitude_g` times the history. The displacement is then relative to the
  fixtures.
- `end_s`: how long to follow it, in seconds, required. Cover the load and at
  least one period of the first mode after it (the first mode's frequency is
  in [modal.md](modal.md#hand-check)).
- `step_s`: the time step in seconds, or `"auto"` (the default): a 400th of
  the run, at most a 20th of the quickest load's change, and at least 40 steps
  per period of mode 1.
- `damping_ratio`: a share of critical damping, default 0.02 (2 %); 0 is
  undamped. Bolted metal structures sit around 0.01–0.05.
- `method`:
  - `"modal"` (default): the modes up to 3 × the highest frequency in the
    loads (1 / a ramp's rise, 1 / a pulse's length, 1 / a table's quickest
    change; a step counts as 1 / 20 steps), each integrated exactly, plus the
    steady share of every mode left out (the static correction).
  - `"direct"`: the whole model stepped through time with Newmark's average
    acceleration (no numerical damping), with Rayleigh damping fitted to
    `damping_ratio` at modes 1 and 2.
- `material` needs a density (every table material has one).
- Checks:
  - `stress` (the default when the view names none): the peak von Mises over
    all time against yield, judged with the study's `margin`.
  - `displacement` (`limit_mm`, optional `faces`): the largest motion over all
    time.
  - Each says when it peaks (`at.time_s`); choosing it in the viewer jumps the
    Time scrubber there.
- View drives: `frame` (the Time scrubber, in seconds), `field` (`von_mises`,
  `displacement`, `von_mises_peak`, `displacement_peak`), `deformation`,
  `load_scale` (k times this load), `threshold`. With no view, the viewer
  opens on the Time scrubber (at the peak), the field and the deformation;
  its routine, Play, runs the frames over three seconds.

```json
{"analysis": "transient", "material": "steel",
 "fixtures": [{"faces": ["#o1.f1"]}],
 "loads": [{"faces": ["#o1.f2"], "type": "force", "vector_N": [0, 0, -50],
            "history": {"shape": "half_sine", "duration_s": 0.002}}],
 "end_s": 0.02, "step_s": "auto", "damping_ratio": 0.02, "method": "modal",
 "view": {"checks": [{"kind": "stress"}, {"kind": "displacement", "limit_mm": 1}]}}
```

A jolt at the mount:

```json
{"analysis": "transient", "material": "aluminum-6061-t6",
 "fixtures": [{"faces": ["#o1.f1"]}],
 "excitation": {"type": "base", "direction": [0, 0, 1], "amplitude_g": 30,
                "history": {"shape": "half_sine", "duration_s": 0.006}},
 "end_s": 0.03}
```

## What it writes

- `summary`: `method`, `loads` (each with its `history` and `words`, like
  "50 N half-sine, 2 ms"), `excitation`, `end_s`, `step_s`, `steps`,
  `adaptive`, `damping_ratio`, `peak_s` (the frame the viewer opens on),
  `max_von_mises_MPa` (with its `_at_s` and `_at_mm`), `yield_MPa`,
  `safety_factor`, `max_displacement_mm` (with `_at_s`, `_at_mm`),
  `static_displacement_mm` and `static_von_mises_MPa` (the same loads held
  steady at their peak), `dynamic_amplification` (the peak displacement over
  the steady one), `frames`, `checks`. Modal adds `modes` (each with `used`),
  `modes_used`, `modes_up_to_Hz`, `load_content_Hz`; direct adds
  `first_modes_Hz`, `rayleigh` (`alpha_per_s`, `beta_s`) and `rejected_steps`.
- Curve in the sidecar: `max_displacement_mm` against time.
- The GLB: a series of time frames, at most 24, evenly spaced from 0 to
  `end_s` plus the moments of the peak stress and the peak displacement,
  labelled "1.02 ms". Each frame carries von Mises and the displacement; the
  envelopes over all time are `von_mises_peak` and `displacement_peak`.
- Findings: a failing stress check is an error ("At 1.02 ms, the part reaches
  ... MPa, over its ... MPa yield"), a close one a warning; `transient_peak`
  (info) says when it moves most and how many times its steady response that
  is; `still_moving` (info) when the motion was still growing at the end (run
  longer).

## Hand check

A load F applied all at once to an undamped spring-mass swings it to 2 F / k:
twice its steady deflection. A part does the same mode by mode, so for a step
load with little damping:

- peak displacement ≈ 2 × the static answer (`dynamic_amplification` ≈ 2);
  a 100 mm steel cantilever, 6 x 6 mm, 10 N stepped onto its tip: static
  F L³ / (3 E I) = 0.154 mm, peak 0.307 mm, first at half a period of mode 1
  (490 Hz: 1.02 ms);
- damping ζ lowers the first overshoot to about 1 + e^(−πζ/√(1−ζ²)) (1.94 at
  2 %);
- a ramp much longer than one period of mode 1 gives about 1× (static);
- a half-sine pulse of length τ: about 1.77× at most, near f1 τ ≈ 0.8; a
  pulse much shorter than a period gives much less than its peak held steady
  (the part only feels the speed change).

If a step reads far from 2× with little damping, check `end_s` covers half a
period of mode 1 and that the fixtures hold.

## Limits

- Linear and small displacement: the material stays below yield and the shape
  does not change the stiffness. A safety factor under 1 means it yields; how
  badly is not modelled.
- Modal damping (modal) or Rayleigh damping (direct): one ratio, exact at the
  modes it is fitted to. Real damping varies with the mode and the joints.
- Modal: modes far above the loads' frequencies answer only by their steady
  share, so the displacement at t = 0 under a step carries that share at once
  (well under 1 % of the peak). Direct: stress is recovered at the frames only,
  so its peak stress is the frames' (the peak displacement's moment among
  them).
- Fixed faces are perfectly rigid. An assembly is bonded where it touches.
- No contact, impact or wave in the floor: for a drop, see `drop` and
  `impact`.

## Adapted to fit

A model too big for the machine still runs; each step is reported
("adapted: ..."):

- `reduce_modes` (tried first): a `direct` run switches to `modal` and says
  so ("Solved by modal superposition ... instead of stepping the whole model
  through time (direct), to fit"); a `modal` run keeps the fewest modes holding
  90 % of the response, the rest by their steady share ("Kept 3 of the 8
  modes up to 3000 Hz, the ones holding 95% of the response to the loads ...").
- `iterative`: the modes found with LOBPCG and multigrid, or each Newmark step
  solved with multigrid CG instead of a factor. No accuracy cost.
- `local_refine`, `defeature`, `linear_elements`: the shared mesh rungs
  ([study-file.md](study-file.md#common-keys)); local_refine keeps the
  requested size where the peak stress over time is.
- `adaptive_steps` (direct only): the step grows while Newmark's local error
  estimate, on the lowest modes' motion, stays under 0.1 % of the largest
  motion, and shrinks where it does not.
- `symmetry` is declared but not taken yet.
