# Vibration (`modal`)

Answers "will it rattle or resonate, and at what frequencies does it ring":
the part's natural frequencies and the shape it vibrates in at each, so you can
check that the first one stays above a limit, or that no mode sits in a motor's,
a fan's or a road's frequency band.

## When to use it

- "Will it resonate with the motor at 7200 rpm (120 Hz)?" Use a band check
  around the forcing frequency.
- "Is it stiff enough not to buzz?" Use a minimum on the first mode; a common
  rule is to keep it above twice the highest forcing frequency.
- It does not say how far the part moves or how much it is stressed when
  shaken: a mode shape has no size of its own. For that, a shaker or a sweep
  needs `harmonic`, a g²/Hz spec `random_vibration`.

## Study

On top of the common keys in [study-file.md](study-file.md#common-keys):

- `fixtures`: optional, as in static (`fixed` faces). With none, the part is
  free in space (hanging on soft springs or bungees, flying): its six
  rigid-body motions come out at 0 Hz, are dropped, and are counted in
  `rigid_body_modes`. An assembly part that nothing holds adds six of its own.
- `modes`: how many to find, 1 to 30, default 6. A check that names a higher
  mode is always found.
- `range_Hz`: an optional `[low, high]` window. The search starts at `low` and
  stops past `high`; with a window above 0 Hz, mode 1 is the lowest mode in it.
- `loads` are not taken: a natural frequency does not depend on a load.
- `material` needs a density (every table material has one).
- Check `frequency`, exactly one of:
  - `min_Hz` (with optional `mode`, default 1): that mode must stay above it.
    It fails under the minimum and is close within 10 % above it. Row line:
    "First mode 85 Hz, must stay above 60 Hz".
  - `avoid_Hz: [low, high]`: no mode may sit in the band. A mode inside fails;
    a mode within 10 % of an edge is close. The check names the mode nearest
    the band. Row line: "Mode 2 at 118 Hz, inside 110–130 Hz". The search
    always reaches 10 % past the band's top, so a mode inside it is not missed.
- With no `view.checks` there is no check: the result lists the modes.
- View drives: `mode` (the mode picker), `deformation`, `field`, `threshold`.
  With no view, the viewer opens on the mode picker and the deformation.

```json
{"analysis": "modal", "material": "aluminum-6061-t6",
 "fixtures": [{"faces": ["#o1.f1"], "type": "fixed"}],
 "modes": 6,
 "view": {"checks": [
   {"kind": "frequency", "min_Hz": 60, "label": "First mode"},
   {"kind": "frequency", "avoid_Hz": [110, 130], "label": "Motor speed"}]}}
```

## What it writes

- `summary.modes`: `[{mode, frequency_Hz, effective_mass_fraction: [x, y, z]}]`.
  The fraction is the share of the part's mass each mode moves along X, Y and
  Z: a mode with a large share is the one a shake along that axis excites. The
  shares of all modes add up toward 1; a free part's elastic modes carry none.
- `summary.first_frequency_Hz`, `total_mass_kg`, `rigid_body_modes`,
  `modes_requested`, `range_Hz`, `checks`.
- The GLB: one series frame per mode, labelled "Mode 2 · 118 Hz", each shape
  scaled so its largest motion is 1 mm (so the colours compare across modes;
  the size itself means nothing). Mode 1 is also the displacement any viewer
  deforms by. The Viewer's routine is Vibrate.
- Two modes at the same frequency (a square or round section bends alike both
  ways) are turned to line up with X, Y and Z, so each bends along one axis.
- Findings: a failing check is an error, a close one a warning, in plain words
  ("The part's first mode is 52 Hz, under the 60 Hz it must stay above");
  `first_mode` (info) says the first frequency and the axis it moves along;
  `rigid_body_modes` (info) says the part is free in space.
- A close check re-solves once on a finer mesh, and says how far the first
  mode moved.

## Hand check

A cantilever of length L (mm), second moment I (mm⁴), area A (mm²), E in MPa
and ρ in t/mm³:

- first bending mode f1 = (1.875² / 2π) · sqrt(E I / (ρ A L⁴)) Hz;
- second bending mode about 6.27 × f1;
- free at both ends: f1 = (4.730² / 2π) · sqrt(E I / (ρ A L⁴)), plus six
  rigid-body modes at 0 Hz.

A 100 mm steel cantilever, 6 x 6 mm: f1 ≈ 490 Hz, f2 ≈ 3070 Hz. The solid
reads a percent or two under beam theory for a stubby beam (shear and rotary
inertia, which beam theory leaves out). A plate's or a bracket's first mode is
usually its softest bending direction; check that the reported first mode
moves the way the part is softest.

## Limits

- Linear and undamped: the frequencies of small vibrations about the unloaded
  shape. A preload (a tight bolt, a spinning part) that stiffens the part is
  not included.
- Fixed faces are perfectly rigid, which raises the frequencies: a real bolted
  mount is softer. If a frequency is close to a limit, say the real part may
  ring lower.
- An assembly is bonded where it touches, which also stiffens it.
- The mesh must resolve the bending: two or more elements through the
  thinnest wall. Halve `mesh.size_mm` and compare when it matters.

## Adapted to fit

A model too big for the machine still runs; each step is reported ("adapted: ..."):

- `iterative`: the modes are found with LOBPCG and a multigrid preconditioner
  instead of factorising the stiffness. No accuracy cost; taken when the
  factorisation would not fit in memory (it grows as n^1.5).
- `local_refine`, `defeature`, `linear_elements`: the shared mesh rungs
  ([study-file.md](study-file.md#common-keys)). local_refine keeps the
  requested size where mode 1 bends the part most and says how far the first
  frequency moved between its two passes. Linear elements read frequencies
  high (they are stiff in bending).
- `reduce_modes`: finds half the modes asked for (never fewer than a check
  names), "Found the first 3 of the 6 modes asked for, to fit". The modes it
  finds are exact.
- `idealise` and `symmetry` are declared but not taken for a vibration study
  yet: shells and beams have no mass model here, and a symmetric half needs
  the antisymmetric modes solved too.
