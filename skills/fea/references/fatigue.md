# Fatigue life (`fatigue`)

It answers "how long will it last" and "how many cycles": the number of times a load can go on and
off before a crack starts, and the fatigue safety factor at the number of cycles the part needs. The
load comes from a static load case, repeated, from a shaker dwell at the sweep's peak (`harmonic`),
or from a random vibration spec over a time (`random_vibration`).

## When to use it

- A part loaded and unloaded many times: a lever, a clip, a bracket on a running machine, a handle,
  a spring arm. "Will it last a million cycles?"
- A part shaken: "will it survive an hour's dwell at resonance on the shaker" (`harmonic`), "will it
  survive 8 hours of this random vibration spec" (`random_vibration`).
- Not for: a load applied once (that is `static`), cracks that already exist (fracture mechanics),
  or failure in under about a thousand cycles (low-cycle fatigue, below).

## The study

On top of the common keys in [study-file.md](study-file.md#common-keys), the static case's own
`fixtures` and `loads` (exactly as in a static study) and:

```json
{"analysis": "fatigue", "material": "aluminum-6061-t6",
 "fixtures": [{"faces": ["#o1.f1"]}],
 "loads": [{"faces": ["#o1.f2"], "type": "force", "vector_N": [0, 0, -150]}],
 "fatigue": {"from": "static", "loading": "fully_reversed", "cycles": 1e6, "surface": "machined"},
 "view": {"checks": [{"kind": "fatigue", "cycles": 1e6, "margin": 1.5}]}}
```

- `fatigue.from`: `"static"` (the default): the load case above is the peak of each cycle.
- `fatigue.loading`, how the load cycles:
  - `"fully_reversed"` (default): from the load to its opposite and back (a rotating shaft, a part
    bent one way then the other). R = -1.
  - `"zero_based"`: from nothing to the load and back (a lever pressed and released). R = 0.
  - `{"ratio": R}`: from R × the load to the load, with -1 ≤ R < 1 (a preloaded spring cycling
    between 10 % and 100 %: `{"ratio": 0.1}`).
- `fatigue.cycles`: the cycles the part must last (default 1e6). The `life` and `fatigue_factor`
  fields and the summary are at this number.
- `fatigue.surface`: `"polished"`, `"ground"`, `"machined"` (default), `"cold_drawn"`,
  `"hot_rolled"` or `"as_forged"`. A rougher surface lowers the fatigue strength (below).
- `fatigue.factor` (optional, 0 to 1, default 1): the other Marin factors multiplied (size, load
  type, temperature, reliability), when the user knows them. 0.814 is 99 % reliability.
- The material needs an ultimate strength and a fatigue strength at a number of cycles. Every metal
  in the table has them ([materials.md](materials.md)). **Polymers carry none**, so a fatigue study on
  `abs`, `pla`, `petg` or `nylon-pa12` is refused and asks for the grade's S-N point:
  `{"name": "abs", "fatigue_strength_MPa": 12, "fatigue_cycles": 1e6}`. Ask the user for the number
  from the datasheet; do not invent one.
- Check `fatigue`: `cycles` (the life needed; default the study's `fatigue.cycles`, or the cycles a
  vibration source counts, below) and `margin` (default 1.5). Several checks at different cycles are
  fine ("a million cycles in service, a billion over its life").

### From a shaker dwell (`"from": "harmonic"`)

The harmonic study's own keys sit at the top level (`fixtures`, `excitation`, `sweep_Hz`,
`damping_ratio`, and `loads` for a force shake; [harmonic.md](harmonic.md)), plus:

```json
{"analysis": "fatigue", "material": "steel",
 "fixtures": [{"faces": ["#o1.f1"]}],
 "excitation": {"type": "base", "direction": [0, 0, 1], "amplitude_g": 5}, "sweep_Hz": [10, 2000],
 "fatigue": {"from": "harmonic", "dwell_s": 3600, "surface": "machined"}}
```

- `fatigue.dwell_s` (required): how long it dwells at the sweep's peak, the frequency f where the
  von Mises stress is highest (its resonance). The cycles are f × `dwell_s`; there is no
  `fatigue.cycles`.
- The stress swings about zero, so it is fully reversed (R = -1); `loading` is not taken. Goodman
  is on the peak frame's stress amplitude.

### From a random vibration spec (`"from": "random_vibration"`)

The random vibration study's own keys sit at the top level (`fixtures`, `psd`, `damping_ratio`,
`sigma`; [random-vibration.md](random-vibration.md)), plus:

```json
{"analysis": "fatigue", "material": "aluminum-6061-t6",
 "fixtures": [{"faces": ["#o1.f1"]}],
 "psd": {"direction": [0, 0, 1], "table": [[20, 0.01], [80, 0.04], [350, 0.04], [2000, 0.007]]},
 "fatigue": {"from": "random_vibration", "duration_s": 28800}}
```

- `fatigue.duration_s` (required): how long it is shaken. Each node counts its cycles at its own
  zero-crossing rate ν0+ (random_vibration's `zero_crossing_Hz` at the peak, written per node), so
  the cycles are ν0+ × `duration_s`; there is no `fatigue.cycles`. A check that names `cycles`
  counts that many at every node instead.
- Fully reversed, as for a harmonic dwell.

## The method

Per node, on the static case's von Mises stress σ (Shigley's Mechanical Engineering Design,
chapter 6):

1. Amplitude and mean: σa = σ (1 − R) / 2, σm = σ (1 + R) / 2.
2. The endurance strength: Se = ka × factor × Se', with Se' the material's fatigue strength at its
   cycles N_e, and ka the Marin surface factor ka = a × Sut^b, at most 1, from Shigley table 6-2
   (Sut in MPa):

   | surface | a | b |
   | --- | --- | --- |
   | ground | 1.58 | −0.085 |
   | machined or cold-drawn | 4.51 | −0.265 |
   | hot-rolled | 57.7 | −0.718 |
   | as-forged | 272 | −0.995 |
   | polished | ka = 1 | |

3. The S-N line (Basquin, S = A × N^b) from 0.9 Sut at 1000 cycles to Se at N_e. Past N_e the
   strength stays Se: steel and titanium have an endurance limit, so a stress under Se never fails.
   Aluminium and copper alloys have none; their data ends at 5e8 (aluminium) or 1e8 (brass) cycles,
   and a life asked for past that is judged at the strength there, with a warning that it may
   overstate it.
4. The modified Goodman line for the mean stress: σa / Sf(N) + σm / Sut = 1 / n, so n is the fatigue
   safety factor at N cycles. The life is where n = 1: the equivalent fully reversed stress
   σa / (1 − σm / Sut) on the S-N line.

A harmonic dwell is steps 2 to 4 on the peak frame's stress, with σm = 0 and N = f × `dwell_s`.

A random vibration uses Steinberg's three-band method with Miner's rule on the RMS (1σ) von Mises
stress σ: a Gaussian response spends 68.3 % of its cycles at 1σ, 27.1 % at 2σ and 4.33 % at 3σ, so
the damage per cycle is D(σ) = 0.683 / N(σ) + 0.271 / N(2σ) + 0.0433 / N(3σ), with N from the S-N
line (at least 1 cycle). A stress at or under the endurance limit does no damage (steel, titanium);
a material with no endurance limit (aluminium, brass) keeps weakening along the Basquin line past
its last data point. The life is 1 / D(σ) cycles. The fatigue factor n is how many times the
stress may grow before the damage over the shake, ν0+ × `duration_s` × D(n σ), reaches 1; on the
line alone that is n = (cycles × D(σ))^b.

## What comes out

- Fields: `life` (log10 cycles, the colour bar in powers of ten, at most N_e: past the material's
  data it says nothing more) and `fatigue_factor` (n at the study's cycles, at most 100), plus the
  static case's `displacement` (a harmonic dwell's: the peak frame at its widest swing; a random
  vibration writes none).
- A vibration source's summary says `method` (`goodman` or `steinberg_miner`), `cycles` (the count
  it made), and `dwell_s` and `peak_Hz` with the stress amplitude (harmonic), or `duration_s`,
  `zero_crossing_Hz`, the peak RMS stress and the `bands` (random_vibration).
- The summary: `min_fatigue_factor` and where, `min_life_cycles` (or `null` with
  `life_beyond_cycles` when the whole part outlasts the data), the peak von Mises and its amplitude
  and mean, and `sn`: the S-N line used (UTS, fatigue strength, cycles, surface factor, factor,
  corrected endurance, Basquin A and b). Also the static numbers (applied force, reactions).
- Each check: `value` is n at its cycles, `limit` its margin, `ratio` 1/n, `close_at` 1/margin,
  `need` the cycles needed and `life` the shortest life (left out when it is past the material's
  data). It fails under n = 1 and is close under its margin. The viewer reads "Lasts 39 million
  cycles, needs 1 million", or "Factor 2.4 at 1 million cycles, needs 1.5" past the data.
- Findings in plain words: `wears_out` (error), `low_fatigue_margin`, `past_fatigue_data`,
  `low_cycle_fatigue`, and the static case's own (it yields, a peak at a fixed face, the mesh).

## Judging the answer (a hand check)

Take the peak von Mises from the summary and work it longhand. A 7075-T6 cantilever loaded from zero
to a peak of 266 MPa: Sut 572, Se' 159 MPa at 5e8; machined ka = 4.51 × 572^−0.265 = 0.838, so
Se = 133.3 MPa. The line: b = log10(133.3 / 514.8) / log10(5e8 / 1e3) = −0.1030, A = 514.8 / 1000^b.
σa = σm = 133 MPa; at 1e6 cycles Sf = A × 1e6^b = 252.8 MPa, n = 1 / (133 / 252.8 + 133 / 572) = 1.32
(close under a 1.5 margin); σar = 133 / (1 − 133 / 572) = 173.3 MPa, life ≈ 3.9e7 cycles. The run
agrees within 0.1 %.

For a quick sanity check on the stress itself, a cantilever's root bending stress is
6 F L / (b h²).

A random vibration longhand: take `max_von_mises_rms_MPa` σ and `zero_crossing_Hz` ν0+ from the
summary, N(kσ) = (kσ / A)^(1/b) for k = 1, 2, 3, D = 0.683 / N(σ) + 0.271 / N(2σ) + 0.0433 / N(3σ);
the life is 1 / D cycles, and over `duration_s` T the factor is (ν0+ T D)^b where every band is on
the line. A harmonic dwell longhand is the static one with σm = 0 and N = `peak_Hz` × `dwell_s`.

## Limits

- Stress-life (high-cycle) only, from a linear static case: no plasticity at the notch, no crack
  growth. Under about 1000 cycles the line is extrapolated, and a `low_cycle_fatigue` warning says
  so; a part that yields on each cycle needs a strain-life method this cadgen does not have.
- The mean stress uses von Mises, which is never negative, so a compressive mean gets no credit
  (conservative).
- One load case scaled in time: the stress directions do not change through the cycle.
- A harmonic dwell sits at one frequency, the peak; a sweep's passes through the resonance are not
  counted. A random vibration assumes a narrow-band Gaussian response (Steinberg), which suits one
  dominant mode and is conservative for a broad-band one.
- The fatigue data are textbook room-temperature values on polished specimens; welds, threads, and
  printed parts' layers are far weaker. Use `factor` or the user's own S-N point when they matter.
- The peak at a sharp corner or a fixed face is exaggerated in the static case (its findings say so),
  and fatigue life is very sensitive to it: a 10 % higher stress can halve the life.

## When the model is big

Its ladder is its source's: the source is the solve, so static's steps apply for a static case
([linear-static.md](linear-static.md#when-the-model-is-big-the-static-ladder)), harmonic's or
random_vibration's for a shake (fewer modes, a coarser frequency grid), and the fatigue fields are
worked out on the adapted mesh. Report every `adapted:` step with its accuracy note:
fatigue life moves far more than stress with an accuracy cost.
