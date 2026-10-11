# Shock (`shock`)

Answers "will it survive this shock spec": the peak stress and movement of a
held part under a shock given as a shock response spectrum (SRS), the way
shock requirements are usually written (a pyrotechnic separation, a hammer
test, a transport or drop spec). Each vibration shape (mode) of the part takes
its peak from the spectrum at its own frequency, and the modes are combined
into one envelope of stress and one of movement.

## When to use it

- "The spec says 50 g above 100 Hz with Q = 10 (5 % damping): does the
  bracket yield?" Use a spectrum along the shock's axis with a stress check.
- "How far does the tip swing in this shock, and does it hit its neighbour?"
  Add a displacement check on that face.
- Use `modal` first when the question is only "where does it ring". Use
  `harmonic` for a sine sweep, `random_vibration` for a PSD in g²/Hz, and
  `transient` when the shock is given as a pulse against time (a half-sine,
  a measured record) rather than as a spectrum.

## Study

On top of the common keys in [study-file.md](study-file.md#common-keys):

- `fixtures`: required, as in static (`fixed` faces). The shock comes in
  through them, every fixture moving together along the spectrum's direction.
- `srs`, required:
  - `direction`: the axis of the shock, `[x, y, z]` (any non-zero vector; it
    is normalised). One axis per study: run one study per axis.
  - `table`: at least two `[frequency Hz, peak g]` rows, frequencies rising,
    every value above zero. Between rows the spectrum is read on log-log axes
    (a straight line on the usual SRS plot); below the first row and above the
    last it is held at that row's g.
  - `damping_ratio`: the damping the spectrum was computed at, default 0.05
    (Q = 10, the usual for shock specs; Q = 1 / (2 × damping_ratio)). The modes
    are damped the same, which is what CQC uses.
- `combination`: how the modes' peaks add up. `"srss"` (default): the square
  root of the sum of the squares, right when the modes are well apart.
  `"cqc"`: the complete quadratic combination, which also counts modes that
  peak together; use it when two modes that move along the shock are within
  about 10 % of each other (the `closely_spaced_modes` finding says so).
- `material` needs a density (every table material has one).
- Checks:
  - `stress` (the default when the view names none, labelled "Shock"): the
    peak von Mises against yield, judged with the study's `margin`.
  - `displacement` (`limit_mm`, optional `faces`): the peak movement
    relative to the fixtures.
- View drives: `field` (`von_mises`, `displacement`), `deformation`,
  `load_scale` (k times this shock), `threshold`. With no view, the viewer
  opens on the field and the deformation. There is no scrubber and no
  routine: a spectrum gives peaks, not a motion over time.

```json
{"analysis": "shock", "material": "aluminum-6061-t6",
 "fixtures": [{"faces": ["#o1.f1"]}],
 "srs": {"direction": [0, 0, 1],
         "table": [[10, 5], [100, 50], [2000, 50]],
         "damping_ratio": 0.05},
 "combination": "srss",
 "view": {"checks": [
   {"kind": "stress"},
   {"kind": "displacement", "limit_mm": 0.5, "faces": ["#o1.f7"], "label": "Clearance"}]}}
```

## How it is solved

1. The modes are found up to the spectrum's top frequency (the last row).
2. Each mode's participation along the shock, Γ = φᵀ M r (r the part moved
   rigidly by a unit step along the shock), and its peak modal coordinate
   q = Γ · S_a(f) / ω², with S_a the spectrum at the mode's frequency f
   (ω = 2πf).
3. Each displacement component (x, y, z at every node) and each stress
   component (the six of the stress tensor) is combined over the modes:
   - SRSS: R = √(Σ Rᵢ²);
   - CQC: R = √(Σᵢ Σⱼ ρᵢⱼ Rᵢ Rⱼ), with the correlation coefficients of
     A. Der Kiureghian, "A response spectrum method for random vibration
     analysis of MDF systems", Earthquake Engineering and Structural Dynamics
     9 (1981) 419–435: for equal damping ζ and r = ωⱼ/ωᵢ,
     ρᵢⱼ = 8ζ² (1 + r) r^{3/2} / ((1 − r²)² + 4ζ² r (1 + r)²), which is 1 for
     r = 1 and falls fast as the modes move apart (under 0.002 at r = 6).
4. Von Mises is taken from the combined stress components.

## What it writes

- `summary`: `srs` (as given), `spectrum` (the line people read: "50 g
  above 100 Hz along Z, 5% damping"), `combination`, `max_von_mises_MPa`
  (with `_at_mm`), `yield_MPa`, `safety_factor`, `max_displacement_mm` (with
  `_at_mm`), `modes` (each mode's frequency, `participation` in √kg,
  `effective_mass_kg`, its effective mass fraction along X, Y, Z, whether it
  was `used`, and for a used one the spectrum's `srs_g` at it and `peak_mm`,
  the most that mode alone moves the part), `modes_used`, `modes_up_to_Hz`,
  `effective_mass_fraction` (the share of the mass the modes used move along
  the shock, `effective_mass_axis`), `total_mass_kg`, `checks`.
- The GLB: two envelopes, `von_mises` and `displacement`, and no series.
  Combined components have no sign; the displacement drawn takes, per
  component, the sign of the mode that contributes most there, so the shape
  reads right while its size is the combined peak.
- Findings, in plain words: a failing stress check is an error ("In this
  shock the part reaches 310 MPa, over its 276 MPa yield (Shock)"), a close
  one a warning; `shock_response` (info) names the mode that carries most of
  the shock, the g the spectrum gives it and the peak movement;
  `modes_missing_mass` (warning) when the modes used move under 90 % of the
  mass along the shock; `modes_below_spectrum` (info) when a mode lies below
  the table's first frequency and took that row's g; `closely_spaced_modes`
  (warning, SRSS only) when two modes that move along the shock are within
  10 % of each other.

## Hand check

A cantilever of length L shocked along a bending direction, first mode
ω1 = 2π f1 (f1 from [modal.md](modal.md#hand-check)), the spectrum giving
S_a(f1) in g at f1 (× 9806.65 for mm/s²): the first mode carries nearly all
the tip's movement, and the tip moves relative to the clamp by about

    tip = 1.566 · S_a(f1) / ω1²

where 1.566 is the cantilever's first-mode participation at the tip. A
100 mm steel cantilever, 6 x 6 mm (f1 ≈ 490 Hz), under 50 g above 100 Hz
along Z: tip ≈ 1.566 × 50 × 9806.65 / (2π × 490)² ≈ 0.081 mm. cadgen gives
0.0811 mm. With the second bending mode (about 6.3 × f1) in the table, SRSS
and CQC agree within 0.1 %.

If a reported peak is far from this with one mode dominant, check the
spectrum's value at f1 (read it off the table, log-log) and the fixtures.

## Limits

- A response spectrum gives each mode's peak, not when it happens: the result
  is an envelope, not a time history. Every peak is assumed to happen at
  once, which is conservative for SRSS of well-separated modes and the
  standard engineering estimate. For the motion over time, or a shock given
  as a pulse, use `transient`.
- Signs are lost in the combination: every combined component is positive,
  so the stress cannot say tension from compression, and the drawn shape takes
  the dominant mode's sign. Von Mises from combined components is the usual
  practice, not an upper bound.
- SRSS assumes the modes peak independently, which holds only when they are
  well apart; CQC accounts for modes close together through their damping.
  Both assume every mode has the spectrum's damping ratio.
- Linear: no yielding, gaps, rattling or contact during the shock.
- Modes are included up to the spectrum's top frequency. Mass that moves only
  in higher modes (and the mass on a fixed face, which never moves) is left
  out, with no missing-mass correction: `modes_missing_mass` says when the
  modes used move under 90 % of the mass along the shock. That mass would
  answer near the spectrum's last g as a rigid body; its stress near the
  fixtures can be underestimated by up to the share left out. Extend the
  table higher to include more modes.
- Fixed faces are perfectly rigid; a real bolted mount is softer, resonates
  lower and sees a different g. An assembly is bonded where it touches.
- Stress is projected onto the nodes from each mode's stress, which smooths
  sharp corners a little more than the static solve does.

## Adapted to fit

A model too big for the machine still runs; each step is reported
("adapted: ..."):

- `reduce_modes` (tried first): keeps only the fewest modes holding 90 % of
  the mass moving along the shock (the search for modes also stops once that
  share is reached), and says how many, the share and the missing mass:
  "Kept 2 of the 4 modes up to 4000 Hz, the ones holding 80% of the mass
  moving along Z, to fit (the other 20% of the mass along Z, the missing mass,
  is left out, so the peak may read a little low)". Modes that do not move
  along the shock barely change the answer.
- `iterative`: the modes are found with LOBPCG and a multigrid preconditioner
  instead of factorising the stiffness. No accuracy cost.
- `local_refine`, `defeature`, `linear_elements`: the shared mesh rungs
  ([study-file.md](study-file.md#common-keys)). local_refine keeps the
  requested size where the shock stresses the part most and says how far the
  peak stress moved between its two passes. Linear elements read stresses low
  and frequencies high.
- `symmetry` is declared but not taken yet: a symmetric half needs the
  antisymmetric modes too.
