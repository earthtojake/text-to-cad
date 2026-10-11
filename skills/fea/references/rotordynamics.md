# Spinning (`rotordynamics`, lite)

It answers "will this shaft run through a critical speed", "how far are the criticals from my
operating speeds", "how big does the orbit get with this unbalance", "is the whirl damped or does
it grow" and "what stress does the spin put in this disc or impeller". The part (a shaft with its
discs, or a bonded assembly of them) spins about an axis in its bearings. cadgen cuts the CAD into
a line of shaft sections along the axis, solves the whirl of that rotor line with its gyroscopic
terms across a speed range (the Campbell diagram), finds the critical speeds and the unbalance
response, and solves the spinning stress on the part's own mesh. The plain word is Spinning.

**It is a lite solver. Its limits are written into every result** (`analysis.limits`, the
verdict's "Lite · " and its Details): linear bearings (each a spring and a damper, which may change
with speed; no fluid-film nonlinearity), bending whirl only (no torsional or axial vibration, no
torsional-lateral coupling), a round rotor line (each section's stiffness is the mean of its two
directions), a rigid disc's shaft bends like the shaft beside it, and a linear spinning stress.
Say them whenever you quote a number from it.

## When to use it

- A spinning shaft, spindle, rotor, fan, impeller, flywheel or turbine disc: its critical speeds
  against its operating speeds (API 684 asks a separation of about 15 %), its run-up through a
  critical, its unbalance orbit, the damping its bearings give the whirl.
- "Spinning stress": the hoop stress in a disc or a flywheel rim at top speed (the
  `stress` check), and, with `spin.solid_modes`, how the spin stiffens a blade or a disc.
- Not for: torsional vibration of a drive train, a shaft whose bearings are oil films you need the
  nonlinear behaviour of (give their linearised coefficients instead), a rotor that is not round
  (a two-bladed propeller's anisotropic inertia), or a part that is not a line along its axis.
  For a fixed part's vibration use `modal`; for a shaker sweep `harmonic`.

## The study

On top of the common keys in [study-file.md](study-file.md#common-keys):

- `spin` (required): how it spins.
  - `axis`: `"X"`, `"Y"`, `"Z"` (default) or a direction `[x, y, z]`; the spin is positive about it.
  - `rpm`: the operating speeds, `[low, high]` (low may be 0), or the one speed it runs at.
  - `sweep_rpm`: the Campbell diagram's top speed; default 1.5 × the top speed, and never short
    of the separation a `critical_speed` check asks for.
  - `through_mm`: a point the axis passes through; default the parts' mass centre.
  - `solid_modes`: how many of the solid's own modes to find at rest and spinning (0 to 12,
    default 0); needs a bearing given by faces (they are held for it).
- `bearings` (required, one or more): where the rotor runs and how stiff.
  - Where: `faces` (its place along the axis is the faces' centre: a journal's cylinder, an end
    face) or `at_mm` (the position along the axis in the part's own coordinates: its Z for a Z
    axis), one of them.
  - How: `"rigid": true` (holds the shaft across; a stiff ball bearing in a stiff housing),
    `"clamped": true` (holds the tilt too; a long sleeve, or a pair of bearings close together),
    or springs and dampers: `k` (N/mm, both directions) or `kxx` and `kyy`, cross terms `kxy`,
    `kyx`; `c` (N s/mm) or `cxx`, `cyy`, `cxy`, `cyx`. `x` and `y` are the axes across the spin:
    (X, Y) for a Z axis, (Y, Z) for X, (Z, X) for Y. Each may be a table over speed,
    `[[rpm, value], ...]`, read linearly and held flat past its ends (a fluid film's linearised
    coefficients).
- `discs` (optional): discs the CAD leaves out, each `at_mm`, `mass_kg`, `polar_kg_mm2`,
  `diametral_kg_mm2` (default half the polar: a thin disc). Discs in the CAD are found by
  themselves: a run of sections stiff-wider than 1.5 × the shaft either side and shorter than
  its own diameter.
- `disc_model`: `"rigid"` (default: a disc found in the CAD is lumped at its mass centre with its
  exact mass, polar and diametral inertia, the shaft through it as stiff as the shaft beside it)
  or `"flexible"` (it stays as its own sections).
- `unbalance` (optional): each `g_mm` (grams × millimetres off the axis) at `faces` or `at_mm`,
  and `phase_deg` (its angle in the rotor, default 0). With none, cadgen uses balance grade G2.5
  (ISO 21940-11: turbines, compressors, spindles) at the heaviest disc, or the rotor's mass
  centre, at the top speed, and says so (`default_unbalance`).
- `modes`: whirl curves to track each way, forward and backward (1 to 12, default 4).
- `view.checks`:
  - `critical_speed` (default): every critical kept clear of the operating speeds by
    `margin_percent` (default 15). Inside the range fails ("Runs at a critical speed"), within the
    margin is close ("Close to a critical speed"), else "Clear of critical speeds"; its row says
    "Critical at 12,400 rpm, 14% above the 10,800 rpm top speed". `orders` (default `[1]`, once per
    revolution) judges other multiples of the spin too (`[1, 2]` for a misalignment's 2×);
    `"backward": true` judges backward-whirl criticals too (which only anisotropic bearings excite).
  - `stability` (default): the smallest log decrement of the whirl over the operating speeds
    against `min_log_dec` (default 0.1). Below 0 a whirl grows ("Unstable"); under the minimum it
    is "Barely damped". With no damper and no cross-coupled spring nothing takes energy out: it
    passes as undamped and a finding asks for the bearings' dampers.
  - `stress` (default): the spinning stress at the top speed against yield, with the study's
    `margin`. Its label is "Spin stress".

```json
{
  "analysis": "rotordynamics",
  "material": "steel",
  "spin": {"axis": "Z", "rpm": [0, 10800]},
  "bearings": [
    {"faces": ["#o1.f3"], "k": 50000, "c": 20},
    {"faces": ["#o1.f9"], "kxx": 50000, "kyy": 40000, "c": 20}
  ],
  "unbalance": [{"faces": ["#o1.f5"], "g_mm": 50}],
  "view": {"checks": [{"kind": "critical_speed", "margin_percent": 15}, {"kind": "stability"}, {"kind": "stress"}]}
}
```

## What comes out

- Fields: the spinning stress at the top speed (von Mises; it colours the part) and the whirl
  shape at each critical speed (an orbit, its largest motion 1 mm), a series of frames ("Critical
  · 12,400 rpm · forward"; with no critical in the sweep, the whirls at the top speed). The
  viewer's Whirl walks each section around its orbit. Study lists "Spins 0 to 10,800 rpm about Z",
  "Bearings at face 3 and face 9", the discs and unbalances the study adds, and the material.
- Summary: `spin`, `rotor` (`length_mm`, `mass_kg`, `elements`), `bearings` (each `at_mm` and its
  coefficients at the top speed), `discs` (each found or added: `at_mm`, `mass_kg`,
  `polar_kg_mm2`, `diametral_kg_mm2`, `source`, `lumped`), `critical_speeds` (each `rpm`,
  `order`, `whirl` forward or backward, `mode`, `frequency_Hz`, `log_decrement`, `frame`),
  `first_critical_rpm`, `lowest_log_decrement`, `unbalance`, `unbalance_peak_um` and its rpm,
  `unbalance_at_top_um`, `max_von_mises_MPa`, `safety_factor`, `solid_modes` when asked.
- Curves (sidecar): the Campbell diagram (`forward_1_Hz`, `backward_1_Hz`, ... against rpm, and
  each one's `_log_dec`), the order lines (`order_1x_Hz`), the unbalance response
  (`unbalance_amplitude_mm`, the largest orbit radius along the rotor, `unbalance_amplitude_at_unbalance_mm`,
  `unbalance_phase_deg`, the lag of the motion behind its force).
- Findings: `critical_speed_inside` (error), `critical_speed_close` (warning), `unstable_whirl`
  (error), `barely_damped_whirl` (warning), `undamped_whirl` (info), `spin_stress_over_yield`
  (error), `spin_stress_close` (warning), `critical_speeds` or `no_critical_speed`,
  `default_unbalance`, `unbalance_peak`, `solid_mode_spinning`, `rotor_held_still` (info).

## How it is solved

- The rotor line: stations at every vertex of the CAD along the axis (where its sections change)
  and at every bearing, unbalance and added disc, each segment cut into elements of at most 1/40
  of the rotor's length. Each element's section is sliced from the solid exactly (OpenCascade's
  Boolean common with a slab, and its volume integrals): its mass, bending stiffness about its
  own stiffness centre (each part's E), shear stiffness, and rotary and polar inertia about the
  axis. Timoshenko shaft elements with consistent mass, rotary inertia and gyroscopic matrices
  (Friswell et al., Dynamics of Rotating Machines, 2010).
- The whirl at each speed is the damped state-space eigenproblem of M q'' + (C + ΩG) q' + K q = 0;
  a whirl is forward when its orbit turns with the spin. The Campbell diagram has 61 speeds from
  rest to the sweep's top; each crossing of a whirl with an order line is refined by Brent's
  method to a part in 10^9. The unbalance response is the steady forced solution at 240 speeds
  plus points close around each critical.
- The spinning stress: the body load ρΩ²r on the part's mesh at the top speed, balanced against
  its own inertia (inertia relief) and pinned at six DOF so it cannot drift: the stress is the
  spin's alone, whatever holds it. With `solid_modes`, the solid's modes held at its bearing faces,
  at rest and spinning with stress stiffening and spin softening (K + Kσ − Ω²M across the axis),
  in the rotating frame (no Coriolis).

## Judging the answer (hand checks)

- Jeffcott rotor (a disc of mass m at the middle of a light shaft on rigid bearings): its critical
  speed is ωn = √(k / m), k = 48 EI / L³. cadgen's rotor line gives it to 1e-9.
- A uniform shaft on rigid bearings at its ends: its first critical is close to its first bending
  frequency, (π² / 2π) √(EI / ρAL⁴) Hz. A steel shaft 600 mm long and 20 mm across: 110.1 Hz,
  6,607 rpm; cadgen finds 6,603 rpm (gyroscopic stiffening, shear and rotary inertia are a fraction
  of a percent on a slender shaft).
- An overhung disc on a cantilever: the forward and backward whirl at a spin Ω are the roots of
  (k11 − mω²)(k22 − Id ω² + Ip Ω ω) − k12² = 0 (forward ω > 0, backward ω < 0), with k the
  stiffness at the disc. The forward whirl climbs with speed, the backward falls.
- Unbalance response away from a critical, a Jeffcott rotor on springs k and dampers c:
  r = (U / m) · (Ω/ωn)² / √((1 − (Ω/ωn)²)² + (2ζ Ω/ωn)²), ζ = c / (2√(km)); the orbit lags its force
  by atan2(2ζΩ/ωn, 1 − (Ω/ωn)²): small below the critical, 90° at it, near 180° above. Well above
  every critical the orbit settles at U / m (the rotor spins about its own mass centre).
- A cross-coupled spring q (an oil film, a seal) destabilises a Jeffcott rotor once q > c ωn.
- A spinning thin disc, inner radius a, outer b: the hoop stress at the bore is
  ρΩ²(3 + ν)/4 · (b² + (1 − ν)/(3 + ν) a²); at the bore von Mises is the hoop stress. A steel disc
  200 mm across with a 40 mm bore at 10,000 rpm: 71.6 MPa; cadgen reads 71.7. A solid disc's
  centre: ρΩ²(3 + ν)/8 · b².
- Units: rpm = 60 × Hz on the 1× line; 1 g·mm = 1e-6 t·mm, so U Ω² is in N.

## Limits

- Linear bearings: springs and dampers (with cross terms), constant or tabulated over speed; no
  fluid-film nonlinearity, no bearing clearance, no oil whip beyond what the linear coefficients
  say. Bearing pedestals and foundations are rigid unless their flexibility is folded into k.
- Bending whirl only: no torsional or axial vibration, no torsional-lateral coupling, no
  rotating (internal) damping, no blade or disc flexibility in the whirl (use `solid_modes`).
- A round rotor line: a section's bending stiffness and rotary inertia are the means of its two
  directions; a keyway or a flat is averaged. The rotor line is one connected line of material
  along the axis (an error says where it breaks).
- A rigid disc's shaft bends like the smaller of the shafts beside it; a disc shrunk on with a
  stiff hub is better kept `"flexible"`.
- The spinning stress is linear: the spin's load on the undeformed part (no spin softening in the
  stress; it is in `solid_modes`). It is the spin's stress alone: no bearing loads, torque or fits.
- Forward and backward curves are tracked by their order at each speed: two curves of one
  direction that cross swap names there (their criticals are still found).

## When the model is big

It runs at any size. The ladder may take, each an `adapted:` line to report:

- `reduce_modes`: the rotor line projected on its slowest bending shapes (at rest, its bearings at
  the middle speed), so the whirl, criticals and response cost almost nothing. Its accuracy is
  measured: the first whirl frequency at the top speed against the full rotor's.
- `iterative`: the spinning stress solved with an AMG-preconditioned iterative solver. Exact.
- `local_refine`: the spinning stress solved coarse away from its peak, then fine where it peaked;
  its accuracy is how far the peak moved between the passes.
