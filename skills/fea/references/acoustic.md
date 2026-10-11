# Sound (`acoustic`, lite)

It answers "at what frequencies does the air in or around this part ring, how loud does it get,
and how loud is the sound a vibrating part sends out": linear acoustics, the Helmholtz equation
for sound in air or another fluid, solved in-house (no outside software). The plain word is Sound.

**Limits, written into every result:**

- "Linear acoustics: small sound pressures in still air or fluid, no flow and no heat or viscous
  loss at the walls."
- "Absorption is lumped: each absorbing face is a normal-incidence impedance, and the air's loss
  one factor."
- Around the part (`"domain": "outside"`) also: "Open air ends at a first-order absorbing
  (Sommerfeld) boundary: exact for sound spreading from the part's centre, an approximation for
  any other."

Quote them whenever you quote a level or a frequency.

## When to use it

- "What frequencies does this enclosure, duct, cavity or room boom at?" (cavity modes)
- "How loud is it inside this box with a speaker in it?", "how much does lining this face help?",
  "what does the microphone at the end of this tube hear across 100 to 2000 Hz?" (frequency
  response, from a vibrating face or a point source)
- "How much sound does this vibrating panel or bracket send out, or into the box it closes?"
  (vibro-acoustics: a `harmonic` shake of the part drives the air)
- Not for: flow noise or anything with the air moving (fans, jets, whistles), loud sound (over
  about 150 dB, where it is no longer linear), sound through the walls of a part (the walls are
  rigid or absorbing, never flexible, except as a one-way vibrating source), thin viscous or
  thermal layers (micro-acoustics), or impulses over time (it solves steady tones, one frequency
  at a time).

## Where the air is (`domain`)

| `domain` | the air is | use it for |
| --- | --- | --- |
| `part` (default) | the part's own solid: model the air volume itself as the part | a duct, a room, a cavity you drew as its air |
| `inside` | the air the part closes inside it (box minus part, the pockets touching no side of it) | a closed enclosure, a speaker box, a housing |
| `outside` | the air around the part, out to a box `air_mm` past it on every side; each box side absorbs | sound sent out into open air |

A part with no air closed inside it is refused for `inside`, in a sentence. Open air
(`outside`) has no natural frequencies, so it takes sources (or `from`) and a sweep.

## The study

On top of the common keys in [study-file.md](study-file.md#common-keys). Cavity modes (no
sources):

```json
{"analysis": "acoustic", "domain": "inside", "modes": 6,
 "view": {"checks": [{"kind": "frequency", "min_Hz": 300, "label": "Box boom"}]}}
```

Frequency response, a speaker face and a microphone:

```json
{"analysis": "acoustic", "domain": "part", "fluid": "air",
 "sources": [{"faces": ["#o1.f1"], "velocity_mm_s": 1}],
 "absorbers": [{"faces": ["#o1.f2"], "absorption": 0.3}],
 "sweep_Hz": [100, 2000], "points": 40, "loss_factor": 0.01,
 "probes": [{"label": "ear", "at_mm": [490, 20, 20]}],
 "view": {"checks": [{"kind": "sound_level", "limit_dB": 85, "probes": ["ear"]}]}}
```

Vibro-acoustics, a harmonic shake of the part driving the air around it:

```json
{"analysis": "acoustic", "from": "harmonic", "domain": "outside", "material": "aluminum-6061-t6",
 "fixtures": [{"faces": ["#o1.f1"]}], "excitation": {"type": "base", "direction": [0, 0, 1], "amplitude_g": 1},
 "sweep_Hz": [100, 1500], "damping_ratio": 0.02, "air_mm": 60,
 "probes": [{"label": "1 m", "at_mm": [40, 20, 1000]}],
 "view": {"checks": [{"kind": "sound_level", "limit_dB": 70, "probes": ["1 m"]}]}}
```

- `fluid`: `"air"` (1.204 kg/m³, 343.2 m/s, levels re 20 µPa), `"water"` (998.2 kg/m³,
  1482 m/s, levels re 1 µPa) or `{"density_kg_m3", "speed_m_s", "name", "reference_Pa"}`.
- `material`: not needed for sound alone. Only `from: "harmonic"` needs one (the vibrating part's).
- No `sources` and no `from`: **cavity modes**. `modes` (1 to 30, default 6): how many to find.
  The walls are rigid; `open` faces are held at zero pressure. A closed cavity's uniform mode
  (0 Hz) is left out and said. `absorbers`, `sweep_Hz` and `loss_factor` are refused here.
- `sources` (or `from`): **frequency response**, at `sweep_Hz` (`[low, high]`, log-spaced
  `points`, default 40, plus five points around each mode of a closed air inside the sweep, so no
  peak falls between two) or at a list `frequencies_Hz`.
  - A vibrating face: `{"faces", "velocity_mm_s"}`, the normal velocity amplitude into the air,
    the same at every frequency (a speaker cone moving 1 mm/s).
  - A point source: `{"point_mm": [x, y, z], "volume_velocity_m3_s"}`, the volume it breathes in
    and out (amplitude). It must be in the air.
- `absorbers`: `{"faces", "absorption"}` (the share of sound striking it head-on that it soaks up,
  0 to 1: painted wall 0.05, carpet 0.3, foam 0.7) or `{"faces", "impedance_rayl"}` (its specific
  acoustic impedance, Pa·s/m; air's own is 413).
- `open`: `[{"faces": [...]}]`, held at zero sound pressure (an open pipe end, unflanged, the end
  correction left out).
- `loss_factor`: the air's damping, 0 to under 1 (default 0.01 in a response; k² becomes
  k²(1 − iη)). A rigid closed cavity with none rings without limit at its modes.
- `probes`: `[{"label", "at_mm"}]`, microphones. In open air a probe past the box is read just
  inside it and carried out by spherical spreading (1/r, with the phase), and said so.
- `air_mm` (`outside` only): how far the air reaches past the part. Default: the larger of half
  the part's size and half a wavelength at the sweep's top.
- `from: "harmonic"`: the study is also a `harmonic` study ([harmonic.md](harmonic.md)): its
  `fixtures`, `excitation`, `sweep_Hz`, `damping_ratio` and `loads`. The harmonic is solved first on
  the part; at each of its frames (its response peaks and log-spaced frequencies over the sweep,
  at most 24) the surface's velocity (relative motion plus a base shake's own) is carried onto
  the air's walls and drives it. One way: the air does not push back on the part. `domain` is
  `outside` by default, or `inside`; `sources`, `frequencies_Hz` and `points` are refused.
- `mesh.size_mm`: the air's element size where the study gives one; it is never coarser than
  six quadratic elements per wavelength at the top frequency (the sweep's top, or, for modes,
  where the modes asked for end), nor than an eighth of the part's diagonal. Open air grows to the
  wavelength's size away from the part.
- Checks:
  - `sound_level`: `limit_dB`, and `faces` (the loudest over them) or `probes` (labels), else the
    loudest anywhere in the air, over every frequency solved. Fails over the limit, close within
    3 dB of it. Default label "Sound"; titles "Too loud" / "Close to the limit" / "Quiet enough";
    its line "Peak 84 dB at 500 Hz, limit 80 dB". Choosing it jumps the scrubber to that frequency.
  - `frequency` on the cavity modes (as in [modal.md](modal.md): `min_Hz` with `mode`, or a band
    `avoid_Hz`), default label "Resonance". Modes only.
  - No check is made by default.

## What comes out

- Fields on the part's surface (the GLB is the part, as for every analysis):
  - modes: `sound_pressure`, each mode's pressure shape, signed, scaled to a largest of 1, one
    frame per mode ("Mode 2 · 903 Hz");
  - response: `sound_level` (dB, RMS re 20 µPa in air) and `sound_pressure` (amplitude, Pa), one
    frame per frequency kept (the peaks, each check's peak, and log-spaced ones; at most 24); the
    viewer opens on the loudest.
  - With the air `inside` or `outside`, the values are on the faces the air touches; a dry face
    reads 0. With the part as the air, every face shows its own.
- Summary: `solve`, `domain`, `fluid`, `air_mesh` (`elements`, `size_mm`, `top_Hz`,
  `elements_per_wavelength`, the open-air `box_mm`), and
  - modes: `modes` (each `frequency_Hz`), `first_frequency_Hz`, `uniform_mode_left_out`;
  - response: `frequencies`, `sweep_Hz`, `loss_factor`, `peak_level_dB`, `peak_Hz`,
    `peak_pressure_Pa`, `peak_at_mm`, `probes` (each `peak_level_dB`, `peak_Hz`,
    `peak_pressure_Pa`, `extrapolated`), `method` (`direct` or `modal`), `from`.
  - Sidecar `curves`: `max_level_dB` (the loudest anywhere against frequency) and
    `level_dB <label>` per probe.
- Findings: `too_loud` (error), `sound_close_to_limit` (warning), `acoustic_resonance` /
  `acoustic_resonance_close`, `wave_resolution` (warning: fewer than six elements per wavelength,
  with how far it may be off), `first_acoustic_mode`, `uniform_mode`, `loudest`,
  `probe_extrapolated` and `open_air_boundary` (info).

## Judging the answer (hand checks)

- Rigid rectangular box Lx × Ly × Lz: f = c/2 √((l/Lx)² + (m/Ly)² + (n/Lz)²). A 300 × 190 ×
  110 mm box of air: 572, 903, 1069, 1144, 1458, 1560 Hz. The solver matches within 0.1 % at the
  default resolution (the benchmark asks 1 %).
- A duct closed at both ends: f_n = n c / 2L (a 0.5 m duct rings at 343, 686, 1030 Hz). Open at both ends: the same; closed at one: f_n = (2n − 1) c / 4L.
- A piston at one end of a closed duct moving V: the pressure at the closed end is
  ρ c V / |sin kL| (0.41 Pa, 83 dB, for 1 mm/s at 500 Hz in a 0.5 m duct). Matched within 0.1 dB.
- A pulsating sphere of radius a, surface velocity V: |p(r)| = ρ c k a² V / (r √(1 + (ka)²)), falling
  6 dB per doubling of distance. A 20 mm sphere at 1 mm/s, 1000 Hz: 0.057 Pa (66 dB) at 50 mm.
  Matched within about 2 % through the absorbing box, also for a probe carried out past it.
- Levels: +6 dB is twice the pressure; doubling the source's velocity adds 6 dB; 10 identical
  incoherent sources add 10 dB. Adding absorption lowers the peaks at the resonances most and
  barely moves the levels between them.

## Limits to say

- Linear: small pressures, still air. No flow noise, no nonlinear (very loud) sound.
- The walls are rigid unless named as absorbers, open faces or sources. Absorption is lumped:
  a face's impedance at normal incidence, the same at every frequency and angle; the air's loss
  is one factor. No viscous or thermal boundary layers (they matter in narrow slits and tubes
  under a millimetre or so).
- Vibro-acoustics is one way: the structure's vibration (from `harmonic`) drives the air; the
  sound does not load the structure back (fine in air, poor for a thin panel in water).
- Open air ends at a first-order absorbing boundary, the Sommerfeld condition with its spherical
  spreading term about the part's centre: exact for sound spreading from there, reflecting a
  little of anything else, more as the box comes within a wavelength of the part. Probes past the
  box are carried out by 1/r.
- One part only (pick one of an assembly with `--occurrence`).

## Ladder steps

It runs at any size. The ladder may take, each an `adapted:` line to report with its note:

- `iterative`: LOBPCG with multigrid for the modes; GMRES with a multigrid preconditioner (on the
  positive-shifted Laplacian) at each frequency, instead of factorising. Exact; a frequency whose
  iterative solve stalls is finished directly, and said.
- `far_field` (open air): the absorbing box brought in toward the part, never under a quarter of
  its size or an eighth of a wavelength: "Brought the open air's absorbing box in to 121 mm past
  the part (from 172 mm) to fit". Its note gives k·r at the lowest frequency (under 1 reflects
  strongly).
- `local_refine`: the air meshed coarser than six elements per wavelength, never under 2.5:
  "Meshed the air at 114 mm to fit: 2.5 elements per wavelength at 1200 Hz, under the 6 it should
  have". Its note says how far the frequencies and levels near the top may be off (the mesh's own
  wave-speed error, measured on the same quadratic elements). Lower frequencies are resolved better.
- `reduce_modes`: modes: the first half of the modes asked for (never fewer than a check names).
  A response in closed air: built from the air's modes up to twice the sweep's top instead of a
  full solve at every frequency; the absorbers act through the modes kept.
- `symmetry`: a response in the part's own air, every source, absorber, open and checked face
  its own mirror image and no probe or point source: one half (or quarter) solved, the rest
  mirrored. Not for modes (a half misses the modes that are odd about the plane).

Never ask the user to shrink the model first; run it and report each step with its note.
