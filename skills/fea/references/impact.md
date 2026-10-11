# Drop impact (`impact`, lite)

It answers "what really happens when it hits the floor": the part, dropped from a height, is
followed through time from the moment it touches a rigid floor, with the stress wave running
through it, the floor's push, the peak g and the peak stress, and any permanent strain when
plasticity is given. It is the deeper check after a [`drop`](drop.md) estimate. The plain word is
Drop impact.

**Limits, written into every result: "Rigid floor; linear tets; elastic unless plasticity is
given."** Quote them whenever you quote an impact number.

## When to use it, and when the drop estimate is enough

- Use `drop` first: it is quick, and it is enough when you can say how far the part stops (a
  rubber foot, a padded case) or how long the impact lasts. Its answer is an equivalent steady load
  you assumed.
- Use `impact` when nobody can say the stopping distance (a hard part onto a hard floor), when the
  stress wave matters (a long part landing on its end, a thin wall far from the landing point), or
  when you want the peak g, how long it stays on the floor or whether it is left bent for good.
- Not for: a soft or yielding floor (the floor is rigid), a part hitting another part, cracks or
  fracture, rubber (no hyperelastic material here), or how far it bounces after the first impact
  (the run follows a short window after landing).

## The study

On top of the common keys in [study-file.md](study-file.md#common-keys):

```json
{"analysis": "impact", "material": "abs",
 "drop": {"height_mm": 1000, "direction": [0, 0, -1], "floor": "rigid", "friction": 0.0},
 "window_ms": "auto", "plasticity": {"tangent_MPa": 200},
 "mesh": {"size_mm": 3, "order": 1},
 "view": {"checks": [{"kind": "stress"},
                     {"kind": "acceleration", "limit_g": 2000},
                     {"kind": "plastic_strain", "limit_percent": 1}]}}
```

- `drop.height_mm` (required): how far it falls. The impact speed is v = √(2 g h): 1 m is 4.43 m/s.
- `drop.direction`: the way it falls, as `[x, y, z]` in the part's axes; default `[0, 0, -1]`
  (straight down). To land it on another face or a corner, give the direction that points from the
  part toward the floor in the part's own axes: `[1, 0, 0]` lands it on its +X side, `[1, 1, -1]`
  on a corner.
- `drop.floor`: `"rigid"`, the only floor modelled (and the default).
- `drop.friction`: the Coulomb friction coefficient between the part and the floor, default 0.
- `window_ms`: how long after first contact to follow it, or `"auto"` (the default): three times
  the contact-time estimate below. The estimate is a guess (a corner landing on a soft part stays
  down several times longer), so an automatic window still pressing on the floor at its end goes on
  until the first impact is over, plus 20 %, up to four times itself (`extended_to_pulse_end` in the
  summary). A part still pressing on the floor at the end of the run says so (an info finding,
  `still_in_contact`); give a longer window.
- `plasticity`: optional, `{"tangent_MPa": 200}`. Bilinear J2: the material is E up to its yield,
  then the tangent slope (0 is perfectly plastic). Without it the part stays elastic and the stress
  can run past yield. The material's yield is required with it. `tangent_MPa` may be left out when
  the material object gives one.
- `mesh.order`: 1 is the only order (linear tetrahedra), and the default.
- No fixtures and no loads: the part flies free until it lands; nothing names faces. The faces
  that met the floor are found and written back (`extras.study.drop.onto`).
- Checks:
  - `stress` (the default): the peak von Mises over the run against yield, with the study's margin.
  - `acceleration` with `limit_g`: the peak rigid-body g, the floor's push over the part's mass.
    With `faces`, it is those faces' mean deceleration instead (a board or a battery mounted
    there). Its label is "Peak g".
  - `plastic_strain` with `limit_percent`: the permanent strain left at the end. It needs
    `plasticity`; without it the study is refused with a sentence saying so.

The contact-time estimate is the elastic one: a stress wave runs from the landing point to the far
end and back while the part is pressed on the floor, t_c = 2 L / c, with L the part's length along
the fall and c = √(E/ρ) (5.05 km/s for steel and aluminium, 1.45 km/s for ABS). The window is 3 t_c.

## What it writes

- A time series (`extras.series`, kind `time`): up to 24 frames from first contact, evenly
  spaced, plus the moment of the peak stress, which the viewer opens on. Each frame carries the von
  Mises stress and the displacement relative to the part's own travel (its centre of mass), so the
  deformation shown is the squash and ring, not the fall.
- Envelopes: `von_mises_peak` (the most each point reached) and `displacement_peak`; and with
  plasticity, `plastic_strain` (percent, at the end).
- Curves in the sidecar: `contact_force_N` (the floor's push against time) and `rigid_body_g`
  (that push over the mass, in g).
- Summary: `contact_ms` (when the first impact ended), `contact_time_estimate_ms`, `window_ms`,
  `end_ms`, `step_us`, `steps`, `peak_g` and `peak_g_at_ms`, `peak_force_N`, `max_von_mises_MPa`
  and when and where, `safety_factor`, `max_displacement_mm`, `rebound_speed_m_s` (the centre of
  mass's speed away from the floor at the end), `mass_added_percent`, `subcycle`, `filter_us`, the
  `unfiltered` peaks, and with plasticity `max_plastic_strain_percent`.
- The reported stress and push are filtered at the mesh's own resolution (a first-order filter of
  four element transits, `filter_us`), like a crash test's channel filter: the single-step bump of
  the first node to land, and the ringing a coarse mesh adds behind a wave front, are not the part's.
  The unfiltered peaks are in `summary.unfiltered`; quote the filtered ones.
- The viewer: Time scrubber, Field and Deformation, a Play routine, a "Dropped" row ("1 m drop onto
  a rigid floor"), the drop arrow and a see-through floor; its takeaway starts "Rigid floor · ".

## How to judge the answer (hand checks)

- **A bar dropped end-on** (the benchmark): it stays on the floor for 2 L / c, the stress behind the
  wave is ρ c v and the floor pushes with ρ c v A, so the peak is c v / L in g after dividing by
  9806.65 mm/s². A steel bar 100 mm long dropped 1 m: 39.6 µs, 175 MPa, about 22,800 g. cadgen's
  test gets these within 2 %, 3 % and 1 % (Poisson's ratio 0, so the 3D bar is the 1D bar of the
  theory; with steel's 0.3 the bar's lateral inertia makes it ring above ρ c v behind the wave front,
  about 15 % in the same run).
- **Any compact part**: the peak stress near the landing point is of order ρ c v (steel at 1 m:
  175 MPa; aluminium: 60 MPa; ABS: about 7 MPa), whatever its shape; corners and thin walls
  concentrate it. A stress far above that is a stress concentration or a too-coarse mesh.
- **Peak g**: of order c v / L. A short, stiff part takes thousands of g from a hard floor; that is
  why the drop estimate's assumed stopping distance matters so much.
- **Perfectly plastic metal**: the stress stops at yield and the floor pushes with yield × the
  landing area; the plastic strain sits at the landing end.

## Limits (say them)

- **Rigid floor**: a real floor gives a little (wood, a carpet, a padded case lengthen the impact
  and lower the g a lot). Use `drop` with a stopping distance for a soft landing.
- **Linear tets**: constant-strain elements read peak bending stress low and need a fine mesh near
  stress concentrations; a mesh several elements through the thinnest wall is a minimum.
- **Elastic unless plasticity is given**: without `plasticity`, a stress past yield is reported but
  the material never yields; with it, J2 bilinear only (no rate effects, no damage, no fracture).
- The floor is a penalty spring (10 E A / h at each surface node, damped at 20 % of critical so a
  landed node stays down), a little bulk viscosity damps the ringing behind a wave front, and
  gravity acts through the window. Air, sound and heat are not modelled.
- The run follows one short window from first contact, not a whole bounce sequence.

## Adapted to fit (ladder steps)

The run's cost is the element count times the number of steps, and the step is set by the smallest
element (dt = 0.9 · l_min / c, a few tenths of a microsecond for millimetre elements in metal), so a
small fillet or a sliver can make a run slow. It is never refused; in this order:

1. `iterative`: the force loop is already matrix-free (no stiffness matrix is stored); never said.
2. `window`: stop once the first impact is over (the floor stopped pushing and the part stopped or
   turned back), plus 20 % of it, instead of the whole window. Accuracy: the first impact and its
   peak are kept; a second bounce or later ringing is not followed.
3. `subcycling`: the elements with the smallest stable step, and their neighbours, are stepped
   several times per step of the rest. Accuracy: each region still steps within its own stability
   limit; where they meet the larger step's motion is interpolated. When mass scaling (or a remesh)
   evens out the steps afterwards, the step says it was not needed after all.
4. `mass_scaling`: mass is added to the smallest elements so their step grows, never more than 5 %
   of the part's mass, and always reported with the share added and its effect on peak g, measured
   by rerunning the first 10 % of the run unscaled when that costs no more than the run itself, else
   stated as up to the added share. Quote both numbers.
5. `local_refine`: coarse away from the peak, the requested size where it peaked.
6. `defeature`: small fillets and holes far from the landing are left out for meshing.

Report every step with its accuracy note ("Added 5.0% to the part's mass ... peak g moved 0.5%
against an unscaled rerun"). A result that took a step with an accuracy cost says "adapted".
