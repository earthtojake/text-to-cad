# The study file

One JSON object, passed as `--study study.json` (or inline: `--study '{...}'`).
For the `static` analysis (the default, and the only one that runs today),
every key other than `material`, `fixtures` and `loads` is optional.
The assembly keys (`parts`, `connections`, `contact_tolerance_mm`) are in
[Assemblies](#assemblies); a study without them on a one-part document is
unchanged.

```json
{
  "material": "aluminum-6061-t6",
  "fixtures": [
    {"faces": ["#o1.f17"], "type": "fixed"}
  ],
  "loads": [
    {"faces": ["#o1.f22"], "type": "force", "vector_N": [0, -500, 0]},
    {"faces": ["#o1.f3", "#o1.f4"], "type": "pressure", "pressure_MPa": 0.8},
    {"type": "gravity", "vector_g": [0, 0, -1]}
  ],
  "mesh": {"size_mm": 2.5},
  "output": {"deformation_scale": "auto"},
  "margin": 2,
  "view": {"controls": [{"drives": "load_scale", "label": "Rider weight", "min": 0.5, "max": 3}]}
}
```

## `analysis`

Which question the study answers. Optional; left out, it is `static`, and a
study without it behaves exactly as one with `"analysis": "static"`.

Only `static` runs in this cadgen. Every other name below is registered but
planned: a study that names one is refused with "'<name>' is planned but not
in this cadgen yet", and nothing else about it is checked. Do not write one;
the skill's "Choose the analysis" table says what to do instead.

| `analysis` | plain word | status | its keys |
| --- | --- | --- | --- |
| `static` | Strength | runs today | this page, and [linear-static.md](linear-static.md) |
| `modal` | Vibration | runs today | [modal.md](modal.md) |
| `buckling` | Buckling | runs today | [buckling.md](buckling.md) |
| `thermal` | Heat | runs today | [thermal.md](thermal.md) |
| `thermal_transient` | Heat over time | runs today | [thermal-transient.md](thermal-transient.md) |
| `thermal_stress` | Heat stress | runs today | [thermal-stress.md](thermal-stress.md) |
| `harmonic` | Shaking | runs today | [harmonic.md](harmonic.md) |
| `random_vibration` | Random vibration | runs today | [random-vibration.md](random-vibration.md) |
| `shock` | Shock | runs today | [shock.md](shock.md) |
| `transient` | Over time | runs today | [transient.md](transient.md) |
| `fatigue` | Fatigue life | runs today, from a static load case | [fatigue.md](fatigue.md) |
| `drop` | Drop (estimate) | runs today, as an estimate | [drop.md](drop.md) |
| `cfd` | Flow | coming, not in this cadgen yet | [cfd.md](cfd.md) |
| `impact` | Drop impact | coming, not in this cadgen yet | [impact.md](impact.md) |
| `nonlinear` | Permanent bend / Stretch | coming, not in this cadgen yet | [nonlinear.md](nonlinear.md) |
| `contact` | Contact | coming, not in this cadgen yet | [contact.md](contact.md) |

Turbulent and compressible flow, creep, composites, bolted joints and
electromagnetic analysis come after these: [planned-next.md](planned-next.md).

## Common keys

Every analysis reads these; each analysis adds its own keys, listed in its
reference.

| key | meaning |
| --- | --- |
| `analysis` | the analysis (above); default `static` |
| `material` | a table name or an object ([`material`](#material)); each analysis checks that the material has the properties it needs and names a missing one |
| `mesh` | element size ([`mesh`](#mesh)) |
| `output` | how the result is drawn ([`output`](#output)) |
| `parts`, `connections`, `contact_tolerance_mm` | an assembly ([Assemblies](#assemblies)) |
| `margin` | the safety factor to keep; the static family only ([`margin`](#margin)) |
| `fit` | memory and time targets, and which adaptations are allowed ([`fit`](#fit)) |
| `view` | what the Viewer's Study shows ([`view`](#view)) |

A key that neither the common keys nor the analysis claims is refused with a
sentence naming the analysis and the keys it takes.

## Units

Geometry in mm, force in N, stress, pressure and modulus in MPa, mass density
in t/mm³, as always. Accelerations, and the heat and flow inputs of the coming
analyses, are written in the units people use; cadgen converts them inside.

| quantity | unit in the study | example key |
| --- | --- | --- |
| length | mm | `size_mm`, `limit_mm` |
| force | N | `vector_N` |
| stress, pressure, modulus | MPa | `pressure_MPa`, `E_MPa` |
| mass density | t/mm³ (steel is 7.85e-9) | `density_t_per_mm3` |
| acceleration, gravity | g (9.81 m/s²) | `vector_g` |
| temperature | °C | `C`, `ambient_C` |
| conductivity | W/(m·K) | material `conductivity_W_mK` |
| heat transfer coefficient | W/(m²·K) | `h_W_m2K` |
| heat flux | W/m² | `W_per_m2` |
| power | W | `W` |
| specific heat | J/(kg·K) | material `specific_heat_J_kgK` |
| vibration PSD | g²/Hz | `psd.table` |
| fluid density, viscosity | kg/m³, Pa·s | `density_kg_m3`, `viscosity_Pa_s` |
| velocity | m/s | `velocity_m_s` |
| time | s (ms where the key says) | `end_s`, `impact_ms` |
| frequency | Hz | `range_Hz` |

Of these, only length, force, stress, density and `vector_g` are read by
`static`; the rest belong to analyses that are not in this cadgen yet.

## `material`

A name from [materials.md](materials.md), or an object:

```json
{"name": "custom", "E_MPa": 70000, "nu": 0.33, "yield_MPa": 240, "density_t_per_mm3": 2.7e-9}
```

An object may also name a table entry and override some of its fields:
`{"name": "steel", "yield_MPa": 355}`.

## `fixtures`

At least one. Each entry lists faces and a type; only `fixed` exists (every
displacement component clamped on those faces). A part with no fixture has no
answer, so the run refuses it.

## `loads`

At least one. Four types:

| type | fields | meaning |
| --- | --- | --- |
| `force` | `faces`, `vector_N: [Fx, Fy, Fz]` | the TOTAL force over the listed faces, spread as a uniform traction over their combined area |
| `pressure` | `faces`, `pressure_MPa` | a normal pressure on the listed faces, positive pushing into the part |
| `gravity` | `vector_g: [gx, gy, gz]`, no `faces` | the part's own weight: every bit of it is pulled along `vector_g`, in g (`[0, 0, -1]` is Earth's gravity down -Z) |
| `acceleration` | `vector_g: [ax, ay, az]`, no `faces` | the part is accelerated by `vector_g`, in g, so it feels an inertial load the opposite way (`[5, 0, 0]`: speeding up at 5 g in +X pushes the part toward -X) |

`gravity` and `acceleration` act on the whole volume (of every part, in an
assembly) and need a density greater than zero: every table material has one;
a material object must give `density_t_per_mm3`, or the study is refused with
a sentence saying so. Their total (mass times acceleration) joins the applied
force in the sidecar's `applied_force_N`, so the reactions still balance it.
More in [linear-static.md](linear-static.md#body-loads-gravity-and-acceleration).

Remote loads, bearing loads, moments and bolt preloads are not in this
version; approximate a moment with a pair of opposite forces on two faces.

## Faces

Face references are the Viewer's selectors: `#o1.f17` is face 17 of
occurrence 1. A reference the user selected arrives with its document prefix
(`part.step#o1.f17`); both forms are accepted, and the prefix must match the
document being solved. `cadgen fea faces part.step` prints every face with
its area, centre, surface type and a hint. In a one-part study every face must
belong to the same part occurrence (an assembly's may be on any part).

Selectors are positions in the saved document. When the model is edited and
the STEP re-written, a face's number can change; list the faces again before
re-running a study on a new revision.

## Assemblies

A document of several parts is solved as an assembly, bonded where parts touch.
Run `cadgen fea parts assembly.step` first to see the parts and the pairs.

```json
{
  "material": "aluminum-6061-t6",
  "parts": {
    "post": {"material": "steel"},
    "#o1.3": {"material": {"name": "custom", "E_MPa": 70000, "nu": 0.33, "yield_MPa": 240}}
  },
  "connections": [{"between": ["post", "base"], "type": "free"}],
  "contact_tolerance_mm": 0.1,
  "fixtures": [{"faces": ["#o1.1.f9"], "type": "fixed"}],
  "loads": [{"faces": ["#o1.2.f6"], "type": "force", "vector_N": [1000, 0, 0]}]
}
```

- `parts`: a material per part, keyed by occurrence ref (`#o1.2`) or by name;
  same forms as `material`. A part left out gets the default `material` and a
  `default_material` finding. A name that two parts share is refused: use a
  ref. A part named twice is refused.
- `connections`: optional overrides, `{"between": [A, B], "type": ...}` with
  `bonded` or `free`. Without it every pair that touches within the tolerance
  is bonded. `bonded` needs the pair to touch within the tolerance; `free`
  leaves them unjoined (their faces stay separate and may not pass load). A
  `free` pair that is still joined through other bonded parts is refused.
  `bolt` and `contact` are refused with "not yet".
- `contact_tolerance_mm`: default 0.1. Faces this close are touching; a gap
  within it is closed to bond the pair, and so is an overlap no thicker than
  it (an interference; a `gap_closed` finding says which). A thicker overlap
  is never bonded.
- Faces: `#o1.4.f23` is face 23 of occurrence `#o1.4`; faces may be on any
  part. A face that another part only partly covers (a plate's top with a post
  standing on it) holds or loads its exposed area; a face wholly covered by a
  bonded joint is refused before the solve. At least one
  part must be fixed, and every part must reach it through bonded neighbours
  (`not_connected` error otherwise).
- `--occurrence REF` on the command line solves that one part alone; `parts`
  and `connections` are then ignored, with a warning.

## `mesh`

`size_mm` is the target element size. Omitted, it is a fortieth of the part's
bounding diagonal. Halving it roughly multiplies the run time by eight; a
first run at the default, then one refinement to confirm the peak, is the
usual pattern. `--mesh-size` on the command line overrides the file for one
run. Elements are quadratic tetrahedra (`order` 2); a study cannot ask for
another order under `static`, though the run may switch to simpler elements
to fit a big model, and then says so ([`fit`](#fit)).

## `output`

`deformation_scale` multiplies the displacement baked into the GLB so that a
small deflection is visible. `"auto"` shows the largest displacement as 5 % of
the part's size; a number fixes it (`1` shows the true deformed shape). The
sidecar records the scale used.

## `margin`

The safety factor against yield the part should keep. Omitted, 2. Below 1 is
refused (a part that yields has no margin). A result under it, but above 1,
is a `low_margin` warning; below 1 is a `yields` error. Raise it for polymers,
fatigue or a part whose failure hurts someone.

## `fit`

Optional. A model too big for the machine's memory or for the time target is
never refused: the run adapts it, step by step, until it fits, and says what
it did. `fit` sets the targets and which steps are allowed.

```json
"fit": {"memory_GB": 8, "seconds": 600, "allow": ["iterative", "local_refine"]}
```

| key | meaning |
| --- | --- |
| `memory_GB` | the memory to stay under; default half of this machine's memory, at least 2 GB |
| `seconds` | the time to aim for; default 600 |
| `allow` | the steps the run may take, by name; default every step the analysis has |

The steps `static` can take, in the order it tries them:

| step | what it does | what it costs |
| --- | --- | --- |
| `iterative` | an iterative solver, or one that never stores the whole matrix | nothing; said only when it changes the run time |
| `local_refine` | a coarse first pass, then a second mesh fine only around the peak and on the named faces | the peak's change between the passes, stated |
| `defeature` | leaves out small fillets, chamfers and holes far from every named face and from the peak, for meshing only | none stated for far features; named faces are never touched |
| `linear_elements` | simpler (linear) elements | bending stress reads low, about 10 to 30 %, stated |
| `idealise` | a thin-walled part as a shell, or a slender one as a beam | the textbook error for its slenderness, stated; skipped where this cadgen has no shell or beam model yet |
| `symmetry` | solves a half or a quarter of a symmetric part and load, and mirrors it | none: exact for a symmetric part and load |

A step that does not apply (no thin wall, no symmetry) is skipped silently.
Every step taken prints one `adapted:` line on the CLI, joins the sidecar's
`fit` list and the GLB's `extras.fit` (each with `rung`, `words`, `accuracy`,
`accuracy_pct`, `faces`, `detail`), and is an `info` finding `fit_<step>`.

Use `allow` only when the user rules a simplification out: "keep every
fillet" is an `allow` without `defeature`. `fit` never makes a refusal
possible: with every step forbidden, or every step taken and the target still
missed, the run goes ahead and says how long and how much memory to expect.
Never ask the user to shrink a model before running it.

## `view`

What the Viewer's Study panel shows for the result, all picked from closed
vocabularies: the `checks` its verdict judges, the `sections` it shows, the
`controls` of What you see (each shown `when` it helps), named `presets` of
them, and what is drawn (`show`). Optional; without it the verdict is the
stress check and Study shows every section, with a field select over every
field, opening on stress, and a deformation slider. cadgen checks it with the
rest of the study and copies it into the GLB (`extras.view`) and the sidecar
(`view`).

```json
"view": {
  "checks": [
    {"kind": "stress"},
    {"kind": "displacement", "limit_mm": 0.5, "faces": ["#o1.f23"], "label": "Tip sag"}
  ],
  "sections": ["verdict", "setup", "controls", "details"],
  "controls": [
    {"drives": "load_scale", "type": "number", "label": "Rider weight", "min": 0.5, "max": 3, "default": 1, "unit": "×", "when": "failing"},
    {"drives": "field", "type": "enum", "label": "Show", "options": ["von_mises", "displacement"], "default": "von_mises"},
    {"drives": "deformation", "type": "number", "label": "Exaggerate"},
    {"drives": "threshold", "type": "number", "label": "Over half yield", "field": "von_mises", "min": 0, "max": 300, "default": 138, "unit": "MPa"}
  ],
  "presets": [{"label": "Cruise", "load_scale": 1}, {"label": "Landing (3×)", "load_scale": 3}],
  "show": {"loads": true, "fixtures": true}
}
```

### `checks`

What the result is judged by. cadgen evaluates every check on the written
solve and writes each result (`kind`, `label`, `value`, `limit`, `unit`,
`ratio` = value over limit, `close_at`, `status` of `fails`, `close` or
`passes`, and `where`, the face and point of the worst value) into the
summary (`summary.checks`), the GLB (`extras.checks`) and the CLI lines. The
verdict says how many fail and how much of the load the weakest takes, then
one row per check, worst first, all scaled by `load_scale` (stress and
displacement are linear in the load).

| `kind` | judges | keys |
| --- | --- | --- |
| `stress` | peak von Mises against each part's yield (an assembly's weakest part): fails under a safety factor of 1, close under the margin. Today's verdict | `margin` (default the study's `margin`; give it once, the same if both), `label` |
| `displacement` | the largest displacement over the whole model, or over `faces` (they may span parts), against `limit_mm`: fails past it, close within a tenth of it (the model's own accuracy) | `limit_mm` (required, > 0), `faces` (face refs, resolved like the fixtures'), `label` (the user's words, "Tip sag") |

At most one `stress` check; an empty list is refused (leave `checks` out for
the stress check alone). A failing displacement check is an error finding
("'Tip sag' moves 2.1 mm, more than the 0.5 mm allowed"); the stress check's
findings are the yields and margin findings already made.

### `sections`

The parts of Study, in order, from `verdict`, `setup` (Held at, Pushed, Made
of, each only where the study has it), `controls` (What you see) and
`details` (the mesh). Default all four, in that order. A section listed twice
or unknown is refused. Parts stays its own panel (`show.parts`).

### `controls`

`controls` are listed in the order the panel shows them, at most one per
`drives`. The agent picks the words (`label`, `unit`) and ranges; the Viewer
decides what dragging one does:

| `drives` | `type` | what it moves | keys |
| --- | --- | --- | --- |
| `field` | `enum` | which field the colours show | `options` (fields the result writes: `von_mises`, `displacement`; default both), `default` (default the first option) |
| `deformation` | `number` | how many times the displacement is drawn | none: leave `min`, `max` and `default` out and it runs from 0 to four times the result's own `deformation_scale`, opening there (the solve picks that scale, so a fixed range is often wrong); or `min` (default 0), `max` and `default` (left out, the result's own) |
| `load_scale` | `number` | the load as a multiple of the solved one: stress, displacement and deformation times it, safety factors divided by it | `min` (default 0.1; more than 0, since at no load there is nothing to show), `max` (required), `default` (1 where the range holds it, else `min`) |
| `threshold` | `number` | values of `field` under it are drawn grey, so only the regions over it carry colour | `field` (required), `min` (default 0), `max` (required), `default` (default `min`), in that field's units |

Every control may add `when`: `always` (default), `failing` (shown only
while a check fails or is close at the load shown) or `passing` (only while
every check passes). A hidden control keeps its value and acts at its
default meanwhile. A `load_scale` control's own `when` is judged at its
default load (as solved, unless its `default` says), so dragging it never
hides it: a load slider `when: failing` appears on a part that fails and
stays while the person drags it down to a load that passes.

`type` may be left out; given, it must be the one above. `min` is zero or
more and below `max`, and `default` lies between them. Every number is
finite. Leave `controls` out for the default field select and deformation
slider; an empty list is refused. The findings stay those of the solved load
whatever `load_scale` is set to.

- Use `load_scale` when the user asks how much the part can take, or what
  happens at a heavier load, labelled with the load in their words.
- Every control is more to read: declare only those the user's question
  needs, with Show (`field`) and Exaggerate (`deformation`), the default
  pair, among them.
- Use `presets` only for two or more load cases the user named: `{"label": ..., <drives>: value}`,
  each key the `drives` of a declared control, each value in its range (an
  option for `field`). With no `controls`, a preset may set `field` and
  `deformation` (zero or more), the two the Viewer shows by default. A
  preset is a full state: controls it does not name go back to their
  defaults.
- Use `threshold` only when the user asked where the stress is over a limit
  (half yield, an allowable stress, a deflection limit on `displacement`),
  with that limit as its `default` and in its label ("Over half yield"), so
  it shows what they asked when the result opens. One at its minimum greys
  nothing, so it does nothing until dragged.
- `show`: `loads` and `fixtures`, `true` or `false` (default both true): whether
  the arrows on the loaded faces and the cones on the fixed faces are drawn
  when the result opens. The person can still turn them on in Display.
  `parts`, `true` or `false`: whether an assembly's Parts panel is shown.
  Left out, it shows from six parts up; under that, a face picked on the
  model names its part, the part's material and its margin, and the
  findings name the joints. Set it `true` when the user asked about the
  parts or joints of a small assembly.

An unknown key, `kind`, `drives`, section or `when`, a field the result does
not write, a range out of order or a preset naming no control is refused with
a sentence naming the key, like every other study error.

## What comes out

`cadgen fea solve part.step` writes two files beside the part, or at the `OUT`
path you give (which must end in `.glb`) plus its `.json` twin:

- `part.fea.glb`: the boundary surface, deformed and coloured by von Mises
  (blue low, red high); the value itself rides along as the `_VON_MISES`
  vertex attribute, and the mesh `extras` carry the field, units, range and
  deformation scale.
- `part.fea.json`: the study as given, the material, the resolved faces,
  the summary (max von Mises nodal and Gauss-point, safety factor, max
  displacement and its location, applied and reaction forces; for an assembly
  also `parts`, one entry per part with its material, peak stress, safety
  factor and displacement, and the weakest part's name and peak; and
  `checks`, each check judged, also in the GLB's `extras.checks`), per-fixture
  reactions, mesh statistics, timings and warnings, the `findings` (also in
  the GLB's mesh `extras`) and `refined`: the first and the finer solve's
  element size and peak when the run solved twice, else `null`. When the run
  adapted to fit, `fit` lists each step ([`fit`](#fit)); it is left out when
  no step was taken.
- for an assembly the sidecar also records `connections` (each joint: parts,
  type, area, gap, `interference_mm` when the parts overlapped by no more than
  the tolerance and were bonded, interface faces), and the GLB carries `parts`,
  `connections` and a per-vertex `_PART` index beside `_FACE`.
- `part.fea.vtu` with `--vtu`: the volume mesh with displacement and von
  Mises point data, for ParaView.

For an assembly the summary mixes two scopes. `yield_MPa` and `safety_factor`
are the weakest part's (the part named by `weakest_part`, whose own peak is
`weakest_part_peak_MPa` at `weakest_part_peak_at_mm`). `max_von_mises_MPa`,
`max_von_mises_gauss_MPa`, `max_von_mises_at_mm` and `max_displacement_mm`
span the whole assembly: the highest stress can sit in a stronger part, so
`yield_MPa` over `max_von_mises_MPa` is not the safety factor. Each part's own
numbers are in `parts`.
