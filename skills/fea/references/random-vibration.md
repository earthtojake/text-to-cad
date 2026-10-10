# Random vibration (`random_vibration`)

Answers "will it survive this transport or vibration spec": the part's
response to a random shake given as a power spectral density (PSD) in g²/Hz,
shaken where it is held. It reports the RMS (one standard deviation, 1σ)
stress and movement the shaking causes, and judges them at 1σ or 3σ.

## When to use it

- "It ships by truck; here is the ASTM D4169 / ISTA profile": a PSD table
  along the vertical axis with a stress check.
- "It must pass MIL-STD-810 method 514 (or a launch vehicle's random spec)":
  copy the spec's table as it is printed, one run per axis.
- "Does the sensor end move more than 0.5 mm?": a displacement check on that
  face.
- Use `harmonic` when the spec is a sine sweep (an amplitude in g against
  frequency), `shock` when it is a shock response spectrum, and `modal` first
  when the question is only where it rings.

## Study

On top of the common keys in [study-file.md](study-file.md#common-keys):

- `fixtures`: required, as in static (`fixed` faces). They are shaken
  together.
- `psd`: `{"direction": [0, 0, 1], "table": [[Hz, g²/Hz], ...]}`, required.
  - `direction`: the axis it is shaken along (any non-zero vector; it is
    normalised). A spec given per axis is one run per axis.
  - `table`: at least two rows, frequencies rising, every value above 0.
    Between rows the PSD is a straight line on log-log axes (the way every
    spec is drawn, so a "+3 dB/oct" segment is just its two end points);
    outside the table it is zero. Convert a spec given in dB/oct to its
    corner points first.
- `damping_ratio`: modal damping as a share of critical, default 0.02 (2 %).
  The RMS response grows as 1/√ζ, so say what you assumed.
- `sigma`: 1 or 3, default 3: the level the checks judge at. A Gaussian
  response stays under 1σ 68.3 % of the time and under 3σ 99.7 %; 3σ is the
  usual design level.
- `material` needs a density (every table material has one).
- Checks:
  - `stress` (the default when the view names none), labelled "Random
    vibration": sigma × the RMS von Mises at its peak against yield, judged
    with the study's `margin`.
  - `displacement` (`limit_mm`, optional `faces`): sigma × the RMS movement
    relative to the fixtures.
- View drives: `field` (`von_mises_rms`, `displacement_rms`), `sigma` (1σ or
  3σ, a multiplier on the RMS fields), `load_scale` (k times this shake's
  amplitude), `threshold`. With no view, the viewer opens on the field and
  the Sigma control, at the study's `sigma`. Nothing deforms: an RMS has no
  sign.

```json
{"analysis": "random_vibration", "material": "aluminum-6061-t6",
 "fixtures": [{"faces": ["#o1.f1"]}],
 "psd": {"direction": [0, 0, 1], "table": [[20, 0.01], [80, 0.04], [350, 0.04], [2000, 0.007]]},
 "damping_ratio": 0.02, "sigma": 3,
 "view": {"checks": [{"kind": "stress"}, {"kind": "displacement", "limit_mm": 0.5}]}}
```

That table is 6.06 g rms from 20 to 2000 Hz.

## What it writes

- `summary`: `psd` (direction, table, `band_Hz`), `grms_input` (the input's
  g rms: the area under the table, each log-log segment integrated exactly),
  `damping_ratio`, `sigma`, `max_von_mises_rms_MPa` and `max_von_mises_MPa`
  (at sigma, with `_at_mm`), `yield_MPa`, `safety_factor` (yield over the
  stress at sigma), `max_displacement_rms_mm` and `max_displacement_mm` (at
  sigma, with `_at_mm`), `zero_crossing_Hz` (ν0+, the rate the stress at its
  peak crosses zero upwards: the cycle rate fatigue counts at) and
  `displacement_zero_crossing_Hz`, `modes` (each mode's frequency, its
  effective mass fraction along X, Y, Z, its `participation_factor` along the
  shake in √kg, its `stress_share` of the RMS stress at the peak, and whether
  it was `used`), `modes_used`, `modes_up_to_Hz`, `effective_mass_fraction`
  and `effective_mass_axis`, `total_mass_kg`, `frequency_points`,
  `points_per_bandwidth`, `checks`.
- Curves in the sidecar: `input_psd_g2_Hz`, `stress_psd_MPa2_Hz` (von
  Mises's equivalent PSD at the stress peak) and `displacement_psd_mm2_Hz` (at
  the most-moving node), against frequency.
- The GLB: `_VON_MISES_RMS` and `_DISPLACEMENT_RMS`, both 1σ (the viewer
  calls them "Stress (1σ)" and "Displacement (1σ)"), no series.
- Findings, in plain words: a failing stress check is an error ("Shaken at
  random at 6.06 g rms along Z, the part reaches 312 MPa at 3σ, over its 276
  MPa yield"), a close one a warning; `random_response` (info) gives the RMS
  stress and movement, their 3σ values and the mode that carries the stress;
  `no_resonance_in_band` (info) when no natural frequency lies in the table;
  `modes_missing_mass` (warning) when the modes used move under 80 % of the
  mass along the shake.

## How it is computed

Modal superposition: the modes up to 1.5 × the table's top, each answering
the base acceleration through qᵢ = −Γᵢ Hᵢ(ω) a. The modal coordinates'
cross-spectral density (Γ⊙H)(Γ⊙H)ᴴ S_a(f) is integrated over a log frequency
grid with 40 points across every mode's half-power bandwidth (2ζf) into one
covariance matrix C. A displacement's variance is φᵀ C φ. Von Mises RMS is
Segalman's quadratic form: with A the matrix that makes σ_vm² = σᵀ A σ,
σ_vm,rms = sqrt(∫ tr(A S_σσ) df) = sqrt(Σᵢⱼ Cᵢⱼ ψᵢᵀ A ψⱼ), ψ each mode's stress
(D. J. Segalman, C. W. G. Fulcher, G. M. Reese and R. V. Field, "An efficient
method for calculating RMS von Mises stress in a random vibration
environment", Journal of Sound and Vibration 230(2), 393–410, 2000). Von
Mises itself is not Gaussian; its RMS is exact, and sigma × that RMS is the
usual design value.

## Hand check

Miles' equation, for one mode under a PSD that is flat (P g²/Hz) around its
natural frequency fn, with Q = 1/(2ζ):

- the mode's absolute acceleration is G_rms = sqrt(π/2 · fn · Q · P) g rms;
- its movement relative to the base is G_rms · 9806.65 / ωn² mm rms,
  ωn = 2π fn;
- for a cantilever's tip, multiply by the first mode's participation at the
  tip, 1.566: x_rms ≈ 1.566 · 9806.65 · sqrt(π/2 · f1 · Q · P) / ω1².

A 100 mm steel cantilever, 6 x 6 mm, under a flat 0.04 g²/Hz from 20 to 1000
Hz along Z with ζ = 0.02 (6.26 g rms in): f1 ≈ 490 Hz, G_rms ≈ 27.7 g, tip
≈ 0.045 mm rms (0.135 mm at 3σ). cadgen gives 0.0449 mm rms, and about 9.6 MPa
rms at the clamp. If a result is far from Miles with one mode clearly
dominant, check the damping, the direction and the fixtures.

The input's g rms is the square root of the table's area: a flat segment adds
P (f2 − f1); a log-log segment of slope s (s = ln(P2/P1) / ln(f2/f1)) adds
P1 f1 ((f2/f1)^(s+1) − 1) / (s + 1), or P1 f1 ln(f2/f1) when s = −1.

## Limits

- Gaussian, stationary and linear: the shake's statistics do not change over
  the test, the response is a linear filter of it, and 3σ is exceeded 0.3 % of
  the time. A real test with a non-Gaussian drive, or a part that rattles,
  bottoms out or yields, is outside this.
- One axis per run, with every fixture moving together. A spec on three axes
  is three runs; cross-axis coupling of the shaker is not modelled.
- Modal damping, one ratio for every mode; real damping varies with the mode
  and the joints, and the RMS response scales as 1/√ζ.
- Modes are included up to 1.5 × the table's top. Mass that moves only in
  higher modes is left out: `modes_missing_mass` says when this is more than
  20 %. Under a resonant response the effect is small.
- Fixed faces are perfectly rigid; a real bolted mount is softer and resonates
  lower. An assembly is bonded where it touches.
- Displacement is relative to the fixtures. Stress is projected onto the nodes
  from each mode's stress, which smooths sharp corners a little.

## Adapted to fit

A model too big for the machine still runs; each step is reported
("adapted: ..."):

- `reduce_modes` (tried first): keeps only the fewest modes holding 90 % of
  the mass moving along the shake, and says how many and the share: "Kept 1
  of the 2 modes up to 1500 Hz, the ones holding 61% of the mass moving along
  Z, to fit". The search for modes also stops once that share is reached.
- `adaptive_steps`: integrates on a coarser frequency grid, 10 points across
  each resonance instead of 40. Its accuracy note is measured on a single
  resonance at the study's damping ("a single resonance's RMS moves under
  0.1% on the coarser grid").
- `iterative`: the modes are found with LOBPCG and a multigrid
  preconditioner instead of factorising the stiffness. No accuracy cost.
- `local_refine`, `defeature`, `linear_elements`: the shared mesh rungs
  ([study-file.md](study-file.md#common-keys)). local_refine keeps the
  requested size where the RMS stress is highest and says how far it moved
  between its two passes. Linear elements read stresses low and frequencies
  high.
- `symmetry` is declared but not taken yet: a symmetric half needs the
  antisymmetric modes too.
