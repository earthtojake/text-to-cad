# Bolted joint (`bolt`, lite)

It answers "will this bolted joint hold": how hard each bolt pulls once it is tightened and the
load is on (its preload plus its share of the load), whether the clamped faces open (separation),
whether they slide over each other (slip: friction against the sideways force), and how hard the
head, the nut and the clamped faces press. The plain word is Bolted joint.

**It is a lite solver. Its limits are written into every result** (`analysis.limits`, the
verdict's "Lite · " and its Details): each bolt is a pretensioned spring, not a meshed bolt; it is
linear elastic with no thread; no fatigue of the bolt yet; and contact's own limits for the clamped
faces. Say them whenever you quote a number from it.

## When to use it

- Bolts or screws with a preload (a tightening torque) clamping two parts: "is an M8 enough", "does
  the flange open under this pressure", "does the bracket slip under this side load", "what preload
  does 25 N·m give", "how much of the load does the bolt see".
- Not for: parts glued or welded (`bonded`, any analysis), parts that only press with no bolt
  (`contact`), a bolt's fatigue life (not yet: say so), a bolt loaded in shear through its shank
  (a fitted bolt; here the shank never bears on the hole), thread stripping, a gasket.

## The study

A `contact` study ([contact.md](contact.md)) whose `connections` name bolts. On top of the common
keys in [study-file.md](study-file.md#common-keys):

- `connections`: one entry per bolt,
  `{"between": ["plate", "bracket"], "type": "bolt", "size": "M6", "preload_N": 5000, "holes": [...]}`:
  - `between`: the part under the head, then the part under the nut (or the tapped part). By
    occurrence ref or name. The two must touch where the bolt clamps them.
  - `size`: `"M3"` to `"M30"` (ISO coarse thread: its stress area, clearance hole and head bearing
    diameter come from the size), or `{"diameter_mm": 7}` for another diameter (scaled from the
    nearest size).
  - `preload_N`, the clamp force the bolt is tightened to; or `torque_Nm`, the tightening torque,
    with `nut_factor` K (0.2 by default: dry steel; about 0.15 oiled, 0.12 with an anti-seize).
    Exactly one of the two.
  - `grade`: the property class, `"8.8"` by default (`"4.6"` to `"12.9"`, stainless `"A2-70"`,
    `"A4-80"` ...). Its proof load (proof stress times stress area) is the bolt check's limit.
  - `friction`: Coulomb's coefficient between the clamped faces, 0.2 by default (dry steel); about
    0.1 oiled, 0.3 to 0.5 for blasted or painted faces.
  - `holes`: the faces of the hole the bolt passes through (the cylindrical hole walls, on either or
    both parts: the bolt's axis and the hole are fitted to them, and the head and nut bear on an
    annulus from the hole out to the head's bearing diameter on the outermost flat faces), or the
    flat faces the head and nut sit on (a spot face or a washer face: all of it bears), one on each
    part. Find them with `cadgen fea faces`.
  - Several bolts may clamp the same two parts (one entry each); they share the friction.
  - The pair a bolt clamps is in frictional contact on its own: do not add a `contact` connection
    for it. Other pairs may be `contact`, `free` or bonded (the default) as in a contact study.
- `fixtures` (or `rigid_planes`) and `loads`: as `contact`. `loads` may be left out: the joint is
  then solved at its preload alone. A part need not be fixed itself: the bolt and the contact hold
  it.
- `steps`: how many equal load steps the load is applied in after the preload, 1 to 200, default 5.
  A step (of the preload or the load) whose contact forces do not settle is cut, and at the
  smallest step kept and marked as `contact` does ([contact.md](contact.md)): "Contact did not
  settle at 80% of the preload: ... not reliable", every check failing.
- Checks, each judged at the last load solved (the default is the first three):
  - `bolt_load`: each bolt's force after loading against `limit_N`, else its proof load. Fails past
    it, close past 0.9 of it. "Bolt overloaded" / "Close to the limit" / "Bolt holds", row line
    "Bolt 6.1 kN, limit 12 kN".
  - `joint_separation`: the clamp the preload gave the clamped faces, lost. Fails when all of it is
    (the faces open), or the clamp falls under `min_clamp_N` (optional, the clamp a seal or a joint
    needs to keep). Close past 0.9 of it. "Joint opens" / "Close to opening" / "Joint stays shut",
    row line "Lost 1.9 kN, of 5 kN clamp".
  - `joint_slip`: the sideways force the clamped faces carry against what friction holds there
    (friction times the clamp). Fails past it, close past 0.9. "Joint slips" / "Close to slipping" /
    "Joint holds by friction", row line "Sideways 950 N, friction holds 1 kN".
  - `stress`, `displacement`, `contact_pressure`: as `contact` (a stress check needs every
    material's yield).
- No load control: a preloaded joint does not answer in proportion to the load. View drives: `frame`
  (the load-step scrubber, from "Preload"), `field`, `deformation`, `threshold`.

A plate bolted to a bracket with one M6, tightened to 9 N·m, pulled off by 3 kN:

```json
{"analysis": "bolt", "material": "steel",
 "connections": [{"between": ["plate", "bracket"], "type": "bolt", "size": "M6", "torque_Nm": 9,
                  "grade": "8.8", "friction": 0.2, "holes": ["#o1.1.f7", "#o1.2.f7"]}],
 "fixtures": [{"faces": ["#o1.2.f1"]}],
 "loads": [{"faces": ["#o1.1.f2"], "type": "force", "vector_N": [0, 0, 3000]}],
 "view": {"checks": [{"kind": "bolt_load"}, {"kind": "joint_separation"}, {"kind": "joint_slip"},
                     {"kind": "stress"}]}}
```

## How it is solved

1. The clamped parts are meshed apart and pressed together by augmented-Lagrange contact
   ([contact.md](contact.md)). Each bolt is a spring along its axis from the head's bearing area to
   the nut's, each end spread evenly over its area (a uniform bearing pressure; it stiffens nothing).
2. Step 1, the preload: head and nut are pulled together by the preload while the clamped faces
   settle (sliding freely: they do as the nut turns). The bolt is then locked there: its length is
   set so it carries exactly the preload ("Preload", the series' first frame).
3. Step 2, the loads, in `steps` steps: each bolt is now a spring of its stiffness, from VDI 2230 for
   a plain shank through the clamp, the head and the nut, and the clamped faces stick until the
   sideways force passes friction.

## What comes out

- A series that opens on the preload ("Preload", 0 %) and then the load steps ("60 % load"), each
  with `von_mises`, `displacement` and `contact_pressure` (between the clamped faces, and under each
  head and nut). Study names each bolt in plain words ("M6 bolt, 5 kN preload, clamps plate and
  bracket"), its force after loading the row's hint.
- Summary: `status` ("Joint holds", "Joint opens", "Joint slips"), `bolts` (per bolt: `preload_N`,
  `force_N` after loading, `increase_N`, `proof_N`, `stiffness_N_mm`, `clamp_length_mm`,
  `shortened_mm` (how much the shank was shortened to hit the preload), the head and nut bearing
  area and pressure, and `hand`: VDI 2230's bolt and joint stiffness and load factor Φ for this
  geometry), and `joints` (per pair of clamped parts: `preload_clamp_N`, `clamp_N` after loading,
  `open`, `opens_at_percent` (the share of this load the faces open at, from the clamp's fall),
  `shear_N`, `friction_holds_N`, `slips`, `slips_at_percent`). Then the contacts, as `contact`.
  Curves: `bolt_force_N` and `clamp_force_N` against the load in %.
- Findings: `bolt_load` (info, per bolt: preload and after loading) or `bolt_overloaded` (error,
  past its proof load), `bolt_preload` (info, a torque turned into a preload), `bolt_slack`
  (warning), `joint_clamped` (info: the clamp left, and the load it would open at) or `joint_opens`
  (error), `joint_slips` (error), and contact's findings for the clamped faces.

## Judging the answer (hand checks)

- **Torque to preload:** F = T / (K d). M6, 9 N·m, K = 0.2: F = 9000 / (0.2 × 6) = 7.5 kN.
  K scatters by ±25 % in practice: a torque-tightened preload is a range, not a number.
- **Proof load:** proof stress × stress area. M6 8.8: 580 MPa × 20.1 mm² = 11.7 kN; a common target
  preload is 70 to 75 % of it.
- **Load factor (VDI 2230):** of a separating load F_A brought in under the head and nut, the bolt
  takes Φ F_A and the clamp loses (1 − Φ) F_A, with Φ = k_b / (k_b + k_c). k_b is the bolt's
  stiffness (1 / [(0.5 d + l_K + 0.4 d)/(E A_N) + 0.5 d/(E A_d3)], A_N = π d²/4, A_d3 at the minor
  diameter); k_c the clamped parts' (a sleeve E π (D_A² − d_h²)/(4 l_K) when they are no wider than
  the head; a wider part's cone, VDI 2230 section 5.1.2.2, is stiffer). The summary's `hand` gives
  both. Benchmark: two round steel plates as wide as an M6 head (6 + 6 mm), 5 kN preload: hand
  Φ = 0.356, solved 0.352; with a load brought in away from the bolt Φ is smaller (VDI's n < 1).
- **Separation:** the faces open at F_A = F_V / (1 − Φ). Benchmark: hand 7.76 kN, solved 7.72 kN;
  past it the bolt carries the whole load.
- **Slip:** a joint holds sideways up to μ × clamp × the number of slip faces. Benchmark: two 24 mm
  steel plates, μ = 0.2, 5 kN preload, one slip face: slips at 1.00 kN (hand 1.00 kN). Note an
  axial load lowers the clamp and so the slip load.
- **Bearing pressure** under the head: F / (π/4 (d_w² − d_h²)); M6 at 5 kN: 180 MPa; check it against the
  clamped material's limiting surface pressure (VDI 2230 lists it per material).
- Sanity: at the preload with no load, the clamped faces carry exactly the preload (to well within
  1 %), and the reactions are zero.

## Limits

- Each bolt is a pretensioned spring along its axis, not a meshed bolt: it carries axial force only,
  spread evenly under its head and nut. The shank never bears on the hole wall: once a joint slips,
  what happens next (the bolt in shear) is not modelled. It takes no bending.
- The bolt is linear elastic, no thread: its stiffness is VDI 2230's for a plain shank; a fully
  threaded bolt is about 10 to 20 % softer. Past its proof load it is reported, not yielded.
- No fatigue of the bolt yet, and no tightening torsion: the preload is the axial force alone.
- Step 1 lets the clamped faces settle sliding freely; friction holds from the tightened state on.
- Contact's limits apply to the clamped faces: small sliding, node-to-surface, static, the parts
  linear elastic ([contact.md](contact.md#limits)).
- A part held by bolts and contacts alone is kept from drifting where they do not hold it by a very
  weak spring; a joint that slips is reported as slipping, and its displacement then means little.

## When the model is big

It runs at any size, with contact's ladder ([contact.md](contact.md#when-the-model-is-big)):
`iterative` (Newton-Krylov), `adaptive_steps` (the load steps grow while Newton settles quickly;
each an `adapted:` line to report), `local_refine` (finer where the contact pressure peaks: under the
heads and around the holes) and `defeature` (small features far from the bolts; the hole faces a
bolt names are never removed). `symmetry` is not taken: a bolt would be cut in two.
