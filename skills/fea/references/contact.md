# Contact (`contact`, lite)

It answers "what happens where parts press or slide on each other instead of being glued": how
hard two parts press together and where, whether a joint opens under the load, whether a part slides
or friction holds it, and parts resting on a rigid floor. The plain word is Contact.

**It is a lite solver. Its limits are written into every result** (`analysis.limits`, the
verdict's "Lite · " and its Details): small sliding, node-to-surface, static, linear elastic parts.
Say them whenever you quote a number from it.

## When to use it, and when bonded or free is enough

Every other analysis glues every touching pair of an assembly (`bonded`, the default) or leaves a
pair apart (`free`). Choose by what the joint does:

- `bonded` (any analysis): the parts are welded, glued, or clamped so hard they never move apart
  or slide. A bonded joint passes tension as readily as compression.
- `free` (any analysis): the parts do not touch under the load, or you want one left out.
- `contact` (this analysis): the parts only press. A contact passes compression, never tension, and
  slides unless friction holds it. Use it for: a pin or a shaft pressing on a plate or a bore, a
  block or a foot resting on another part, a part sitting on a floor or a bench (a rigid plane), a
  joint that may open on one side under a moment, a clamp that holds by friction, "how hard do these
  press" (bearing or Hertz contact pressure), or "does this lift off".
- Not for: impact or anything fast (`impact`), bolts with pretension (`bolt`, [bolt.md](bolt.md)), parts that slide far
  along each other (more than a fraction of an element), press fits (an overlap counts as touching,
  not as an interference to be pushed apart), rubber or metal past yield (`nonlinear`: its parts stay
  bonded).

## The study

On top of the common keys in [study-file.md](study-file.md#common-keys):

- `connections`: the pairs that press, `{"between": [A, B], "type": "contact", "friction": 0.2}`.
  `friction` is Coulomb's coefficient, 0 (frictionless, the default) to 2: about 0.1 for oiled
  steel, 0.2 for dry steel on steel, 0.3 to 0.5 for aluminium or plastics on metal. Every other
  touching pair stays bonded unless the study says `free`. Only this analysis accepts `contact`;
  every other refuses it with "not yet supported". The two parts need not touch to begin with: a
  pin a hair off its hole, or a sphere touching a plate at one point, closes the gap first. A
  contact pair joined through other bonded parts is refused (the glue would join it too).
- `rigid_planes`: rigid floors, `[{"point_mm": [0, 0, 0], "normal": [0, 0, 1], "parts": ["plate"],
  "friction": 0.3}]`. `normal` points from the plane to the parts (it is turned round when the parts
  are on the other side); `parts` defaults to every part; `friction` to 0. A rigid plane holds a
  part as a fixture would, but only against pressing.
- `fixtures` and `loads`: as `static` ([linear-static.md](linear-static.md)), body loads included.
  `loads` are required; `fixtures` are optional when a rigid plane holds the parts. A part need not
  be fixed itself: it may rest on a contact or a plane alone. A part held by nothing (no fixture,
  no rigid plane, no contact with a held part) is refused, naming it.
- `steps`: how many equal load steps to start with, 1 to 200, default 5. A step that does not
  converge is halved and tried again (up to six times).
- Checks, each judged at the last load solved:
  - `stress` (the default with no `view.checks`): the peak von Mises against the yield, as static.
  - `contact_pressure`: `limit_MPa` (for bearing, often 1.5 times the yield for a static load; for
    rolling or Hertz contact, the material's allowable), optional `faces`. Fails over the limit,
    close past 0.9 of it. Row line "Peak 380 MPa, limit 400 MPa".
  - `displacement`: `limit_mm`, optional `faces`, as static.
- No load control (`load_scale` is not a drive): contact opens, closes and slides, so the response
  is not proportional to the load. View drives: `frame` (the load-step scrubber), `field`,
  `deformation`, `threshold`. With no view: the load-step scrubber, the field and the deformation.

A pin pressed into a plate that rests on a bench, dry steel:

```json
{"analysis": "contact", "material": "steel",
 "connections": [{"between": ["pin", "plate"], "type": "contact", "friction": 0.2}],
 "rigid_planes": [{"point_mm": [0, 0, 0], "normal": [0, 0, 1], "parts": ["plate"]}],
 "loads": [{"faces": ["#o1.1.f3"], "type": "force", "vector_N": [0, 0, -2000]}],
 "steps": 5,
 "view": {"checks": [{"kind": "stress"}, {"kind": "contact_pressure", "limit_MPa": 400}]}}
```

## What comes out

- A series of load steps (`series.kind` "time", unit "%"), frames labelled "60 % load", at most
  24, opened on the last. Each frame has `von_mises` (MPa), `displacement` and `contact_pressure`
  (MPa, on the faces in contact, else 0). The viewer scrubs them (Load step) and plays them (Play).
  Study names each pair ("pin presses on plate, friction 0.2") with what it did under the load, and
  each rigid plane under "Rigid floor".
- Summary: `status` ("Carries the full load", or "Stops at about 70 % of the load" when Newton finds
  no equilibrium past it), `max_von_mises_MPa`, `max_displacement_mm`, `max_contact_pressure_MPa`
  and where each is, and `contacts`, one per pair and plane: `touching`, `force_N` (the force it
  passes), `area_mm2` (the area pressing), `peak_MPa` and `peak_at`, `friction_N` (the sideways
  force friction carries), `slipping_share` (the share of the contact that slips, with friction),
  `max_slide_mm`. Then the steps, Newton iterations and `contact_updates`. Curves: the largest
  displacement and the total contact force against the load in %.
- Findings, in plain words: `contact_presses` (info, each pair: "pin presses on plate: 2000 N over
  12 mm², peak contact pressure 380 MPa"), `peak_contact_pressure` (info, where it peaks),
  `contact_separates` (warning: "they separate under this load and no longer touch"),
  `contact_slides` or `contact_sticks` (info, with friction; or "slides freely" without),
  `comes_loose` (error: a part held only by contacts lifts off all of them) and `slides_away`
  (error: friction cannot hold a part held only by contacts; its displacement is then meaningless),
  `contact_stops` (error: no equilibrium past a load), `load_steps_cut` (info).

## Judging the answer (hand checks)

- Two flat blocks pressed together by F over a face of area A: the pressure is F/A everywhere. The
  solver lands within 1 % on a 3 mm mesh of 10 mm blocks.
- Pulled apart: no contact pressure, and the part underneath takes no load at all (a contact never
  pulls). A part held only by the contact comes loose, and says so.
- A sphere of radius R on a flat (Hertz), both elastic: the contact radius a = (3 F R / 4 E*)^(1/3)
  and the peak pressure p0 = 3 F / (2 π a²), with 1/E* = (1 − ν1²)/E1 + (1 − ν2²)/E2 (a rigid flat:
  1/E* = (1 − ν²)/E). Steel on steel, R = 10 mm, F = 20 kN: a = 1.11 mm, p0 = 7.8 GPa. The solver
  reads a within 2 % and p0 within 7 % with elements of about a/4 where they touch (0.3 mm here);
  the peak closes on Hertz as the elements shrink. Point and line contacts need that fine a mesh
  near the contact: set `mesh.size_mm` small or let the ladder's `local_refine` refine at the peak.
- Friction: a part pushed sideways by T while pressed by N sticks when T < μ N (friction carries
  all of T) and slides when T > μ N (friction carries μ N exactly). Near the edges of a part pressed
  on a stiffer one some micro-slip is normal: the surfaces slip where the sideways traction from the
  part's own bulge passes μ times the local pressure.
- Sanity: frictionless and bonded agree when the joint only presses and nothing slides; a contact
  pair's force equals the load it carries (the reaction at the fixtures).

## Limits

- Small sliding: each surface node is paired once, before loading, with the surface it faces.
  Parts may slide only a fraction of an element along each other; a part that slides further, or
  turns far, is beyond it.
- Node-to-surface: the pressure is resolved to the mesh. A flat contact needs a few elements across
  it; a point or line contact (a ball, a roller, a knife edge) needs elements of about a quarter of
  the contact width where it touches.
- Static: no impact, inertia or rate effects. Friction is Coulomb with one coefficient, the same at
  rest and sliding.
- The parts stay linear elastic; a pressure past yield is reported, not followed into plasticity.
  An initial overlap within the contact tolerance counts as just touching (no press fit).
- A part held only by contacts is kept from drifting where they do not hold it (sideways with no
  friction) by a very weak spring, a hundred-millionth of its own stiffness. If that spring ends up
  carrying the load (the part lifts off or slides away), the result says so and its displacement
  means nothing.

## When the model is big

It runs at any size. The ladder (as `nonlinear`'s) may take, each an `adapted:` line to report:

- `iterative`: Newton-Krylov, each Newton step solved by GMRES with a multigrid preconditioner
  instead of factorising the tangent. Exact (same tolerance).
- `adaptive_steps`: the load steps grow (up to 4 times the starting step) while the contacts settle
  in a few Newton iterations, and are still cut where they do not. Its note says friction's slip is
  followed in larger steps; the final contact is solved to the same tolerance.
- `local_refine`: a coarse pass, then a pass fine only where the coarse one peaked in contact
  pressure: the way to resolve a point contact on a big model.
- `defeature`: small fillets and holes far from the loads and fixtures left out of the mesh.
- `symmetry` (one part on a rigid plane only): one half or quarter solved and mirrored, when the
  part, fixtures, loads, checks and every rigid plane are symmetric.
