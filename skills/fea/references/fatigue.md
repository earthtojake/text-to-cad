# Fatigue life (`fatigue`)

It answers "how long will it last" and "how many cycles": the number of times a load can go on and
off before a crack starts, and the fatigue safety factor at the number of cycles the part needs. The
load comes from a static load case, repeated. Fatigue from a shaker dwell (`harmonic`) or a random
vibration spec (`random_vibration`) is coming; a study that names either is refused with that
sentence.

## When to use it

- A part loaded and unloaded many times: a lever, a clip, a bracket on a running machine, a handle,
  a spring arm. "Will it last a million cycles?"
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
- Check `fatigue`: `cycles` (the life needed; default the study's `fatigue.cycles`) and `margin`
  (default 1.5). Several checks at different cycles are fine ("a million cycles in service, a
  billion over its life").

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

## What comes out

- Fields: `life` (log10 cycles, the colour bar in powers of ten, at most N_e: past the material's
  data it says nothing more) and `fatigue_factor` (n at the study's cycles, at most 100), plus the
  static case's `displacement`.
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

## Limits

- Stress-life (high-cycle) only, from a linear static case: no plasticity at the notch, no crack
  growth. Under about 1000 cycles the line is extrapolated, and a `low_cycle_fatigue` warning says
  so; a part that yields on each cycle needs a strain-life method this cadgen does not have.
- The mean stress uses von Mises, which is never negative, so a compressive mean gets no credit
  (conservative).
- One load case scaled in time: the stress directions do not change through the cycle.
- The fatigue data are textbook room-temperature values on polished specimens; welds, threads, and
  printed parts' layers are far weaker. Use `factor` or the user's own S-N point when they matter.
- The peak at a sharp corner or a fixed face is exaggerated in the static case (its findings say so),
  and fatigue life is very sensitive to it: a 10 % higher stress can halve the life.

## When the model is big

Its ladder is its source's: the static case is the solve, so static's steps apply
([linear-static.md](linear-static.md#when-the-model-is-big-the-static-ladder)), and the fatigue
fields are worked out on the adapted mesh. Report every `adapted:` step with its accuracy note:
fatigue life moves far more than stress with an accuracy cost.
