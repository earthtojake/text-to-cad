# Piezo (`piezo`, lite)

It answers "how far does this actuator move at 100 V, and how hard can it push", "what voltage does
this sensor make when it is pressed", "what is its capacitance", "where are its resonance and
anti-resonance, and how strongly does it couple", and "how much does it move and how much current
does it draw across a band of frequencies" (a buzzer, an ultrasonic transducer, an energy harvester).
The plain word is Piezo. A study names one `solve`: `static` (the default), `resonance` or `harmonic`.

**It is a lite solver. Its limits are written into every result** (`analysis.limits`, the verdict's
"Linear · " and its Details): linear, small signal, room-temperature constants at low field; no
depolarisation, no hysteresis, no ageing and no self-heating. A field near the coercive field
(about 1.2 kV/mm for PZT-5A, 0.65 for PZT-5H, per TP-226), a large stress or a hot part departs from
it. Say this whenever you quote a number from it.

## When to use it

- `static`: a stack or plate actuator's stroke and blocked force, a bimorph or unimorph bender's
  deflection at a voltage, the stress the voltage makes in a bonded part, the voltage a sensor
  makes under a force (its output electrode `open`), and the capacitance between the electrodes.
- `resonance`: the natural frequencies with the electrodes shorted (resonance, fr) and open
  (anti-resonance, fa), and each mode's effective coupling k_eff² = (fa² − fr²)/fa²; the clamped
  (blocked) capacitance C0, which with them gives the equivalent circuit.
- `harmonic`: a buzzer, a transducer or a harvester driven across a band: the displacement, the
  current into the driven electrode and its admittance |Y| = I/V, and an open electrode's voltage,
  at each frequency, with a loss.
- Not for: a large-signal or switching drive (hysteresis, depoling), a temperature sweep, an
  electrostrictive (PMN) or magnetostrictive material, an acoustic load (solve the vibration here,
  then the sound with `acoustic` from a `harmonic` study of the same part).

## Materials

A piezo part's material carries a `piezo` block ([materials.md](materials.md#piezoelectric-ceramics)):
`pzt-4`, `pzt-5a` and `pzt-5h` are in the table (Morgan TP-226 constants), or give the supplier's
matrices. The poling direction is the block's `poling` (default +Z): a part poled the other way is
`{"name": "pzt-5a", "piezo": {"poling": [0, 0, -1]}}`. In an assembly each part takes its own:

- a part with a `piezo` block is piezoelectric;
- a metal (under 1 ohm·m, a brass shim, a steel substrate) is a conductor: one voltage throughout,
  held when an electrode is on it, floating otherwise;
- a plastic with a `relative_permittivity` is a dielectric (field, no coupling);
- anything else carries only stiffness and mass.

A `stress` check needs the ceramic's `yield_MPa` (it has none: brittle): use the dynamic tensile
strength, 24 MPa for PZT-4, 28 MPa for PZT-5A and PZT-5H (TP-226), for a driven part.

## The study

On top of the common keys in [study-file.md](study-file.md#common-keys):

- `solve`: `static` (default), `resonance` or `harmonic`.
- `electrodes`: required. Each `{"faces": [...], "V": 100, "name": "top"}` (held at a voltage;
  0 is ground; in a `harmonic` study an amplitude) or `{"faces": [...], "open": true, "name": "out"}`
  (it floats: one voltage over its faces, no net charge; a sensor's output). Static and harmonic
  studies hold at least one; a resonance study needs one at 0 V (ground) and the electrode it is
  driven or read through (any V, or open).
- `fixtures`: as static's (fixed or roller); required for `static` and `harmonic`, optional for
  `resonance` (a free part's six rigid-body modes are left out).
- `loads` (`static`, `harmonic`): forces and pressures on faces, as static's.
- `modes` (`resonance`, `harmonic`): how many modes to find, 1 to 30, default 6. A harmonic study
  finds them to place its frequencies around each resonance.
- `sweep_Hz` (`harmonic`, required): `[low, high]`; `points` (10 to 400, default 60) log-spaced
  frequencies, plus points around each mode in the band. `damping_ratio` (default 0.01): applied as
  a loss on the stiffness (η = 2ζ). A free PZT disc is about 1/(2 Qm): 0.001 for PZT-4, 0.007 for
  PZT-5A; a mounted part 0.01 to 0.05.
- Checks (`view.checks`): `static` and `harmonic` take `stress`, `displacement` and `voltage`;
  `resonance` takes `frequency`. `voltage` judges an open electrode's signal:
  `{"kind": "voltage", "min_V": 0.5, "electrode": "out"}` (the electrode defaults to the first open
  one; it fails under `min_V`, is close within 10 % above it). "Signal" by default; the row reads
  "0.82 V, needs at least 0.5 V". In a sweep, displacement and voltage are judged at their worst
  frequency.

Voltage sign: a voltage applied along the poling (the + electrode on the side the poling points
away from) makes the ceramic grow along it (d33 > 0). With poling +Z, put the voltage on the bottom
electrode and ground the top to make it grow.

## Examples

A plate actuator, free to grow (rollers that only stop it sliding away):

```json
{"analysis": "piezo", "material": "pzt-5a",
 "electrodes": [{"faces": ["#o1.f5"], "V": 100, "name": "drive"}, {"faces": ["#o1.f6"], "V": 0, "name": "ground"}],
 "fixtures": [{"faces": ["#o1.f5", "#o1.f1", "#o1.f3"], "type": "roller"}],
 "view": {"checks": [{"kind": "displacement", "limit_mm": 0.0001}]}}
```

A force sensor, its output open:

```json
{"analysis": "piezo", "material": "pzt-4",
 "electrodes": [{"faces": ["#o1.f6"], "open": true, "name": "out"}, {"faces": ["#o1.f5"], "V": 0, "name": "ground"}],
 "fixtures": [{"faces": ["#o1.f5"], "type": "roller"}, {"faces": ["#o1.f1", "#o1.f3"], "type": "roller"}],
 "loads": [{"faces": ["#o1.f6"], "type": "force", "vector_N": [0, 0, -10]}],
 "view": {"checks": [{"kind": "voltage", "min_V": 5, "electrode": "out"}]}}
```

A series bimorph bender (two layers poled opposite ways, glued; voltage across the outer faces):

```json
{"analysis": "piezo", "material": "pzt-5a",
 "parts": {"upper": {"material": {"name": "pzt-5a", "piezo": {"poling": [0, 0, 1]}}},
           "lower": {"material": {"name": "pzt-5a", "piezo": {"poling": [0, 0, -1]}}}},
 "electrodes": [{"faces": ["#o1.1.f6"], "V": 10, "name": "top"}, {"faces": ["#o1.2.f5"], "V": 0, "name": "bottom"}],
 "fixtures": [{"faces": ["#o1.1.f1", "#o1.2.f1"]}]}
```

A buzzer (a PZT disc on a brass shim, the shim the ground electrode) swept for its resonance:

```json
{"analysis": "piezo", "solve": "harmonic", "material": "brass",
 "parts": {"disc": {"material": "pzt-5h"}},
 "electrodes": [{"faces": ["#o1.1.f2"], "V": 5, "name": "drive"}, {"faces": ["#o1.2.f3"], "V": 0, "name": "shim"}],
 "fixtures": [{"faces": ["#o1.2.f1"]}],
 "sweep_Hz": [500, 10000], "damping_ratio": 0.02}
```

Its resonance and anti-resonance: the same with `"solve": "resonance"` (no sweep keys).

## What comes out

- Static: fields `von_mises`, `potential` (V, signed), `electric_field` (kV/mm) and `displacement`.
  Summary: each electrode's voltage (an open one's is its reading), charge (C) and mean
  displacement (an actuator's stroke: `electrodes[i].mean_displacement_mm`), `capacitance_F`
  between the highest and lowest held electrodes (with no load), the largest displacement, stress
  and field, and the fixtures' reactions (a blocked force).
- Resonance: a mode series (pick it in the viewer's Mode control), each frame its shape, stress and
  voltage with the shape scaled to 1 mm. Summary `modes`: each `resonance_Hz`, `antiresonance_Hz`,
  `k_eff` and `k_eff2`; `blocked_capacitance_F` (1 V on the first driven electrode, the part held still).
- Harmonic: a frequency series (the viewer's scrubber), each frame its displacement, stress (peak
  over the cycle) and voltage amplitude. Curves in the sidecar: `max_displacement_mm`,
  `current_mA` and `admittance_S` (the driven electrode: the one with the largest voltage), and
  `voltage_V:<name>` for each open electrode. Summary: the peak, `peak_admittance_S` and its
  frequency, `peak_current_mA`.
- Findings: the capacitance, an open electrode's reading, the first modes' fr, fa and k_eff, and a
  warning where the field passes 0.35 kV/mm (a third of soft PZT's coercive field).

## Hand checks

From the ceramic's own constants (s^E = (c^E)⁻¹, d = e s^E, ε^T = ε^S + d eᵀ, c33^D = c33^E + e33²/ε33^S):

- Free plate (thickness t, area A, free to grow every way): C = ε33^T A/t; stroke d33 V; held
  between two flat rollers (thickness blocked, sides free), it pushes with F = d33 V A/(s33^E t);
  pressed by F with its output open, V = g33 F t/A (g33 = d33/ε33^T). PZT-5A: d33 = 373 pC/N.
- Thickness mode of a wide plate (laterally clamped): fa = sqrt(c33^D/ρ)/(2t), fr from
  k_t² = (π/2)(fr/fa) tan((π/2)(fa − fr)/fa), k_t² = e33²/(c33^D ε33^S); blocked C0 = ε33^S A/t.
- Series bimorph cantilever (length L, total thickness t): the uniform-field closed form is
  δ = 3 d31 V L²/(2t²). The bending strain makes a field of its own inside each layer, which
  stiffens each layer's own bending (to its open-circuit biaxial compliance, (s11 + s12)(1 − kp²)):
  the solve reads about 11 % under that formula for PZT-5A, and matches
  δ × (2/3)/(1/2 + r/6), r = 1/(1 − kp²), within a few percent. With weak coupling the two agree.
- A low-frequency drive draws |Y| = 2π f C.

These are the benchmarks in the tests: the plate within 2 % (it is exact to rounding), the
thickness mode within 5 % (it reads within 0.01 %), the bimorph within 10 % of the closed form at weak
coupling and within 5 % of the coupled form at PZT-5A's.

## Big models

It is never refused for size. The ladder (`fit`): `iterative` (static: the coupled system by MINRES
with a block multigrid preconditioner instead of a factorisation), `local_refine` (coarse, then
fine where the stress peaked), `symmetry` (static and harmonic: one half or quarter about planes
along every poling direction, mirrored back; not for resonance, which would miss the antisymmetric
modes) and `reduce_modes` (resonance: fewer modes; harmonic: the sweep by modes with a static
correction, exact below the highest mode kept). Each step is said in the result.
