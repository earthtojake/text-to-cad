# Magnetic / electric (`electromagnetic`, lite)

It answers "will this gap arc over", "what is its capacitance", "what is the resistance of this
part and how hot does the current make it", "how strong is a coil's magnetic field, what is its
inductance and how hard does it pull", and at a frequency "how much eddy current and loss does this
AC field make in that part, how hot does it get, what is this busbar's AC resistance, what is this
coil's impedance". The plain word is Magnetic / electric. A study names one `mode`:
`electrostatic`, `current`, `magnetostatic` or `ac_magnetic`.

**It is a lite solver. Its limits are written into every result** (`analysis.limits`, the verdict's
"Static · " or "AC · " and its Details). The static modes: static and DC only (no eddy currents,
no AC, no high frequency, no skin effect), linear materials (no saturation, no hysteresis, no
permanent magnets). `ac_magnetic`: one frequency, a sine steady state (no switching transients or
harmonics), linear materials, stranded coils, no displacement current (not antennas or waves).
Say them whenever you quote a number from it.

## When to use it

- `electrostatic`: high voltage across a gap, an insulator or a printed housing ("will it arc",
  "how much field at this edge"), a capacitor or a sensor electrode's capacitance.
- `current`: a busbar, a trace, a heater element or a contact carrying a DC current: its
  resistance, where the current crowds, and (with `electro_thermal`) how hot the Joule heat makes it.
- `magnetostatic`: a coil or solenoid's field, its inductance, the force between two coils or
  on a magnetic part near a coil (a plunger, an armature), and that force as a load on the part.
- `ac_magnetic`: the same fields at a frequency, with the eddy currents they drive in metal:
  induction heating, the loss in a shield, bracket or plate near a transformer or coil, skin effect
  and AC resistance of a busbar or conductor, a coil's impedance (R and L) with metal near it. See
  [AC magnetic fields](#ac-magnetic-fields-ac_magnetic).
- Not for: switching transients or a waveform with harmonics (solve each harmonic as its own
  frequency), antennas and waves, permanent magnets, saturated iron, plasma or corona after breakdown.

## Materials

Each part's material gives the electrical numbers ([materials.md](materials.md#electrical-and-magnetic)):

- A material under 1 ohm·m (every metal in the table) is a **conductor**. In an electrostatic
  study it is one voltage throughout: held when any of its faces is in `voltages`, floating
  (no net charge) otherwise. A conductor held at two voltages is an error.
- Every other part is a **dielectric** with its `relative_permittivity`; one without it is asked for it.
- In a current study a material over 1000 ohm·m carries no current.
- Magnetostatics needs every part's `relative_permeability`. Structural `steel` has none in the
  table (it is ferromagnetic and saturates): give the grade's value from its B-H curve at the field
  you expect, and say it is a linear stand-in.

## The study

On top of the common keys in [study-file.md](study-file.md#common-keys):

- `mode`: `electrostatic`, `current` or `magnetostatic`; required.
- `voltages` (electrostatic, current): `[{"faces": [...], "V": 1000, "name": "top"}]`, faces held
  at a voltage. `name` is optional (default `"1000 V"`).
- `currents` (current): `[{"faces": [...], "A": 2, "name": "in"}]`, a current in amperes put in
  through the faces, spread evenly over them; it leaves through the held faces. A current study
  needs at least one voltage (0 V for ground).
- `capacitance` (electrostatic, optional): `{"between": ["top", "bottom"]}`. The capacitance is
  measured as a bridge does: the charge on the first electrode over the voltage between the two,
  every other electrode at its own voltage. With exactly two electrodes it is between them. A guard
  electrode at the first's voltage keeps the fringe field off it.
- `resistance` (current, optional): `{"between": ["in", "out"]}`; with exactly two electrodes it
  is between them. A current entry's voltage is the mean over its faces.
- `air` (electrostatic; always on in magnetostatics): `true` or `{"around_mm": 20}`, a box of air
  around the parts reaching that far past them (default: 1 x the parts' size for electrostatics,
  1.5 x for magnetostatics). The air is meshed with the parts, at the parts' element size next to
  them and coarser out in the box; the box's walls carry no field across them. Without air an
  electrostatic study solves only inside its parts (a dielectric between painted electrodes).
- `coils` (magnetostatic): `[{"part": "coil", "turns": 100, "A": 2, "axis": {"direction": [0, 0, 1],
  "point_mm": [0, 0, 0]}, "name": "coil 1"}]`. The part is the winding's solid, a ring around the
  axis (a full turn; one that reaches its own axis is an error). Its turns x amps flow evenly over
  its cross-section, around the axis right-handed about `direction`. `point_mm` defaults to the
  part's centre; `part` may be left out for a one-part study.
- `electro_thermal` (current, optional): `temperatures`, `heat` and `convection` as a thermal study
  writes them ([thermal.md](thermal.md)). The Joule heat goes into a steady thermal solve on the same
  mesh, one way (the resistivity does not change with the temperature). It needs each material's
  `conductivity_W_mK`.
- `map_to_structure` (magnetostatic, optional): `{"part": "armature", "fixtures": [{"faces": [...]}]}`.
  The magnetic force on that part (default: the part feeling the most) is spread evenly through it
  as a static load, one way; its stress and displacement join the result and the static checks apply.
- `probes` (optional, every mode): `[{"at_mm": [0, 0, 0], "label": "centre"}]`, points to read the
  field at (in the air too). The mesh keeps the parts' size around each probe.

Fields on the parts' surface: `potential` (Voltage, signed) and `electric_field` (kV/mm) for
electrostatics; `potential` and `current_density` (A/mm²) for current, plus `temperature` with
`electro_thermal`; `magnetic_field` (|B|, mT) for magnetostatics, plus `von_mises` and
`displacement` when mapped. On a conductor's surface the electric field shown is the field just
outside it.

Checks:

- `electric_field` (electrostatic): `limit_kV_mm`, optional `faces`. The strongest field anywhere in
  the dielectrics and the air (or on those faces) against the limit; fails over it, close past 0.9.
  Titles "Arcs over" / "Close to arcing" / "Holds the voltage", default label "Arcing", row line
  "Peak 2.8 kV/mm, limit 3 kV/mm". Dry air breaks down at about 3 kV/mm (less over long gaps and at
  sharp points); a plastic's dielectric strength is on its datasheet.
- `temperature` (current with `electro_thermal`): as [thermal.md](thermal.md).
- `stress`, `displacement` (magnetostatic with `map_to_structure`): as static.
- No load control: a field grows with the voltage, a force and a Joule heat with the current squared.

Numbers in the summary: `capacitance_pF`, `energy_J`, each electrode's `charge_nC`,
`max_field_kV_mm` and where; `resistance_ohm`, `current_A`, each electrode's current,
`joule_heat_W` (= I² R), `max_current_density_A_mm2`, the temperatures; `inductance_uH` (one coil,
2 W / I²), `energy_J`, `max_field_mT`, each coil's cross-section and current density, `forces`
(J x B on a coil, the Maxwell stress on a magnetic part), and each probe's reading.

## Examples

A 1 kV gap between two plates in air, with a capacitance and an arcing check:

```json
{"analysis": "electromagnetic", "mode": "electrostatic", "material": "aluminum-6061-t6",
 "air": {"around_mm": 10}, "mesh": {"size_mm": 1},
 "voltages": [{"faces": ["#o1.1.f3"], "V": 1000, "name": "hot"}, {"faces": ["#o1.2.f2"], "V": 0, "name": "ground"}],
 "view": {"checks": [{"kind": "electric_field", "limit_kV_mm": 3}]}}
```

A busbar carrying 50 A, cooled by still air:

```json
{"analysis": "electromagnetic", "mode": "current", "material": "aluminum-6061-t6",
 "currents": [{"faces": ["#o1.f1"], "A": 50, "name": "in"}], "voltages": [{"faces": ["#o1.f2"], "V": 0, "name": "out"}],
 "electro_thermal": {"convection": [{"faces": ["#o1.f3", "#o1.f4", "#o1.f5", "#o1.f6"], "h_W_m2K": 10, "ambient_C": 25}]},
 "view": {"checks": [{"kind": "temperature", "max_C": 90}]}}
```

A 100-turn coil at 2 A, its field at the centre:

```json
{"analysis": "electromagnetic", "mode": "magnetostatic", "material": "aluminum-6061-t6", "mesh": {"size_mm": 1},
 "coils": [{"turns": 100, "A": 2, "axis": {"direction": [0, 0, 1], "point_mm": [0, 0, 0]}}],
 "probes": [{"at_mm": [0, 0, 0], "label": "centre"}]}
```

## AC magnetic fields (`ac_magnetic`)

A time-harmonic solve at one frequency: every source is a sine at `frequency_Hz` and every number
is its amplitude (a loss is time-averaged). Each conducting part (resistivity under 1 ohm·m, not a
coil) carries the eddy currents the changing field drives, so it shields, heats and crowds its
current toward its skin. It solves the complex vector potential on lowest-order Nédélec elements
and the conductors' voltage on P2 elements (the A-phi formulation), in a box of air around the
parts (always on, as for magnetostatics).

**The skin is meshed for you.** A conductor's faces are meshed at half its skin depth (never over
the study's `mesh.size_mm`), the rest at the study's size. The summary's `skin` says, per conducting
part, the depth, the surface size it got and `resolved`. When the ladder had to mesh the surface
coarser, the result says so in plain words (the step, a warning in `analysis.warnings` and a CLI
line): the loss and AC resistance then read high, by about 6 % at one element per skin depth on a
round wire and more when coarser. Quote that note with the number.

Keys (on top of the common keys):

- `frequency_Hz` (required): the frequency, Hz.
- At least one source:
  - `coils`: as magnetostatics (`turns`, `A` now the current's amplitude, `axis`). A coil is a
    stranded winding: its current is spread evenly over its section and it carries no eddy current
    of its own. Its part's material does not matter.
  - `currents` with `voltages`: a conductor fed an AC current, `[{"faces": [...], "A": 100,
    "name": "in"}]` (the amplitude), its return held at 0 V, `[{"faces": [...], "V": 0}]`. The
    faces it goes in and out through must be flat, square to x, y or z and at the ends of the parts
    (where the leads go): the air stops there, and those faces are where the circuit closes. The
    input face is one voltage (a terminal), so the current is free to crowd to its skin.
  - `applied_field`: `{"mT": 10, "direction": [1, 0, 0]}`, a uniform AC field the air box's walls
    carry (as from a large coil far away): a plate or a shield in a known field.
- `air`, `probes`: as magnetostatics.
- `electro_thermal` (optional): `temperatures`, `heat`, `convection` as a thermal study writes
  them. The time-averaged loss in each part goes into a steady thermal solve on the part mesh, one
  way (induction heating; the resistivity does not change with the temperature). Every watt of loss
  goes in (`heat_in_W` = `loss_W`). Needs each material's `conductivity_W_mK`.
- Checks: `temperature` with `electro_thermal` (as [thermal.md](thermal.md)).
- Fields: `eddy_current` (Eddy current, A/mm², the amplitude of the current density in the
  conductors: induced, or a fed conductor's current crowding to its skin), `magnetic_field` (|B|
  amplitude, mT), and `temperature` with `electro_thermal`.

Numbers in the summary: `loss_W` and `losses` (per part, W, time-averaged),
`max_eddy_current_A_mm2` and `max_at_mm`, `max_field_mT`, `energy_J` (time-averaged magnetic
energy), `skin` (per conducting part), and, with exactly one coil or one fed conductor and no applied
field, `impedance`: `R_ohm` = 2 P / I² and `L_uH` = 4 W / I² at the frequency, `X_ohm` = 2 pi f L.
A fed conductor's R is its AC resistance; a coil's R is the loss its field causes in the metal
around it (the winding's own wire resistance is not in it: add it from the wire's gauge and length).

A busbar fed 100 A at 50 Hz, its AC resistance and how hot it runs:

```json
{"analysis": "electromagnetic", "mode": "ac_magnetic", "material": "aluminum-6061-t6", "frequency_Hz": 50,
 "mesh": {"size_mm": 2}, "air": {"around_mm": 30},
 "currents": [{"faces": ["#o1.f1"], "A": 100, "name": "in"}], "voltages": [{"faces": ["#o1.f2"], "V": 0, "name": "out"}],
 "electro_thermal": {"convection": [{"faces": ["#o1.f3", "#o1.f4", "#o1.f5", "#o1.f6"], "h_W_m2K": 10, "ambient_C": 25}]},
 "view": {"checks": [{"kind": "temperature", "max_C": 90}]}}
```

A 10-turn coil at 2 A and 50 kHz heating an aluminium part (the coil `"part": "coil"`, the
workpiece cooled by air):

```json
{"analysis": "electromagnetic", "mode": "ac_magnetic", "material": "aluminum-6061-t6", "frequency_Hz": 50000,
 "mesh": {"size_mm": 1},
 "coils": [{"part": "coil", "turns": 10, "A": 2, "axis": {"direction": [0, 0, 1]}}],
 "electro_thermal": {"convection": [{"faces": ["#o1.2.f1", "#o1.2.f2", "#o1.2.f3"], "h_W_m2K": 10, "ambient_C": 25}]},
 "view": {"checks": [{"kind": "temperature", "max_C": 200}]}}
```

A plate in a 10 mT, 500 Hz field along it:

```json
{"analysis": "electromagnetic", "mode": "ac_magnetic", "material": "aluminum-6061-t6", "frequency_Hz": 500,
 "mesh": {"size_mm": 1}, "applied_field": {"mT": 10, "direction": [1, 0, 0]}}
```

Hand checks for AC:

- Skin depth: delta = sqrt(rho / (pi f mu0 mu_r)). Aluminium 6061 (rho 3.99e-8 ohm·m): 14 mm at
  50 Hz, 0.8 mm at 15.8 kHz, 0.28 mm at 125 kHz; copper (1.7e-8) is about 0.65 x that. Under about a third of
  the part's thickness the current lives in its skin; over the part's size it barely notices.
- A round wire of radius a: R_ac / R_dc = Re[(ka / 2) J0(ka) / J1(ka)], k = (1 - j) / delta; past
  a few skin depths about a / (2 delta) + 1/4.
- A thin plate (t well under delta) in a field B along it: P = pi² B² f² t² sigma V / 6, a little
  less at its edges, where the currents turn.
- The field at a wire's surface is mu0 I / (2 pi a), at any frequency.
- At low frequency it is magnetostatics: the field and inductance match a `magnetostatic` study.
- Benchmarks this mode is tested against: the round wire's R_ac / R_dc at a / delta = 2.5 against
  Bessel's form (5 %; measured 1.3 % high); the same wire at 1 Hz against rho L / A (1 %; measured
  0.55 %); a 10 x 10 x 0.5 mm plate's eddy loss against the lamination formula (10 %; measured
  2.1 % low, the edge return); its temperature through the thermal handoff against P / (h A)
  (2 %; measured 0.02 %); a coil at 1 Hz against magnetostatics (2 %; identical); on a tiny budget
  the wire with its skin under-resolved (10 %; measured 5.7 % high).

AC limits to say: one frequency, a sine steady state; linear materials (no saturation, no
hysteresis loss, no permanent magnets: iron's loss is its eddy loss at the `relative_permeability`
you give, not its hysteresis); coils stranded (no proximity loss in their own wire); no
displacement current (fine below a few MHz on parts this size, not antennas or waves); the
conductors' resistivity does not change with their temperature (one way to thermal).

## Judging the answer (hand checks)

- Parallel plates: C = eps0 eps_r A / d (eps0 = 8.854 pF/m); the field between them V / d. Plates in
  air hold more than that by their fringe field (a few percent for a gap a tenth of their width).
- A straight bar: R = rho L / A; its Joule heat I² R; J = I / A.
- A thin loop: B = mu0 N I / (2 R) at its centre; inside a long solenoid B = mu0 N I / L.
- Two coaxial coils carrying current the same way pull together; their forces are equal and opposite.
- Benchmarks this solver is tested against (each to its tolerance): a PETG slab's C = eps A / d
  (0.1 %); a guard-ring capacitor in air against eps0 pi (r + g/2)² / d (3 %; measured 0.03 %); a bar's
  R = rho L / A (1 %; exact); Joule heat = I² R (exact); a thick ring coil's centre field against
  the closed form for a uniform current density (5 %; measured 1.9 % low at 1 mm elements); two
  coaxial coils' force against a Biot-Savart sum (5 %; measured 2.4 %).

## Limits to say

- The static modes are static and DC only, linear materials: a changing field in metal is
  `ac_magnetic`'s (its own limits are in [AC magnetic fields](#ac-magnetic-fields-ac_magnetic)).
- Sharp edges and corners concentrate an electric field without bound: the peak at a sharp edge
  depends on the mesh there. Round the edge (or read the field a little way off it) before
  trusting a breakdown verdict; the summary says where the peak is.
- The magnetic field uses lowest-order Nédélec elements: |B| is constant in each element, so the
  peak and a probe read within a few percent of the converged value at a few elements across the
  winding. The force on a magnetic part (Maxwell stress) is the most mesh-sensitive number: compare
  it with the equal and opposite force on the coil (J x B), and refine the mesh until they agree.
- The air box's walls stop the field (no flux crosses them): keep them well away (the default is
  1.5 x the parts' size for a magnetic field).
- A coil's current flows evenly over its section (a wound coil, not a single solid turn).

## Ladder steps

`iterative` (multigrid CG, no accuracy cost), `local_refine`, `defeature` and `symmetry` (a
potential solved on one part with no air: the half or quarter mirrored back, exact), and for a
study with air `fluid_coarsen`: "Coarsened the air away from the parts to fit: the parts are still
meshed at 1.5 mm, the air out at 10.6 mm", the field near the parts unchanged. Report each step with
its note, as for every analysis.

`ac_magnetic` takes, in order: `iterative` (multigrid GMRES on the complex system, falling back to
the direct solve when it does not converge), `fluid_coarsen` (as above), then `local_refine`, which
here keeps the conductors' surfaces as fine as the budget allows for their skin: "Meshed the
conductors' surfaces at 1 mm to fit, coarser than the 0.4 mm their 0.8 mm skin depth at 15.8 kHz
asks for; the rest of the parts at 1 mm", with the note that the loss and AC resistance then read
high. It never refuses for size.
