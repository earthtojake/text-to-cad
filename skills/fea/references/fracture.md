# Cracks (`fracture`, lite)

It answers "will this crack grow", "how big a crack can it take at this load" and, with a growth
block, "how many load cycles until the crack grows to breaking". The study describes the crack;
cadgen cuts it into the part, meshes its front fine, solves the load case, and reads the stress
intensity factors along the front. The plain word is Cracks.

**It is a lite solver. Its limits are written into every result** (`analysis.limits`, the
verdict's "Lite · " and its Details): linear-elastic fracture mechanics (LEFM) only, small-scale
yielding (the material stays elastic around the crack), no ductile tearing and no plastic
collapse; K where the front meets a free surface is read as the plane-strain value; crack growth
keeps the crack's shape and grows it straight on in its own plane. Say them whenever you quote a
number from it.

## When to use it

- A crack, flaw or defect is known or assumed: one found in inspection, a weld toe flaw, a
  scratch or tool mark on a stressed face, damage tolerance ("assume a 1 mm crack is there").
- Brittle or high-strength materials, where a crack decides failure before yielding does: high
  strength aluminium (7075), titanium, hardened steels, cast parts. Check the `lefm_limit` finding:
  a tough mild steel in a thin part usually yields before a crack runs, and LEFM then overstates
  the danger and understates the crack's real instability at the same time.
- With `growth`, a cyclic load that grows a crack: how long a part with a crack lasts.
- Not for: a part with no crack (use `static` and `fatigue` for crack initiation), cracks that
  branch or curve, cracks in an assembly's joint, rubber or plastics without measured toughness,
  or a crack whose faces press shut (it warns: the faces would overlap).

## The study

On top of the common keys in [study-file.md](study-file.md#common-keys):

- `fixtures` and `loads`: as `static` ([linear-static.md](linear-static.md)), body loads included;
  required.
- `crack` (required): where the crack is and how big.
  - `kind`: `"edge"` (straight across the section from a face, like a saw cut: `size_mm` deep),
    `"through"` (through the thickness of a plate: `2 × size_mm` long), `"surface"` (a half-ellipse
    on a face: `size_mm` deep, `length_mm` long on the face, default `2 × size_mm`, a half circle)
    or `"embedded"` (an ellipse inside the part: semi-axis `size_mm`, `length_mm` across, default a
    circle).
  - `face`: the face the crack opens from (edge, surface) or crosses (through: its normal is the
    thickness direction); an embedded crack takes none. From `cadgen fea faces`.
  - `at_mm`: a point on the crack's mouth on that face (edge, surface; it is moved onto the face if
    within 5 % of the crack's size), or the crack's centre (through, embedded).
  - `normal` (`[x, y, z]`, the way its faces open, usually along the main stress) or `plane`
    (`"xy"`, `"yz"`, `"xz"`): the crack's plane, exactly one. The plane goes through `at_mm`.
  - `size_mm`: depth (edge, surface), half length (through) or semi-axis (embedded), mm.
  - `along` (optional, through and embedded): the direction of its length in the crack plane
    (through: default the plane's normal × the face's normal).
- `growth` (optional): grow the crack by Paris's law, da/dN = C (ΔK)^m.
  - `load_ratio`: R = lowest / highest load of each cycle, from −1 up to but not 1; default 0
    (on and off). ΔK = (1 − R) K_max; for R < 0 only the tension part counts (ΔK = K_max: a
    crack pressed shut does not grow).
  - `paris_C` (m per cycle, with ΔK in MPa√m) and `paris_m`, together: the alloy's crack-growth
    data. Without them the material's are used ([materials.md](materials.md#fracture): steel and
    304 stainless have Barsom's fits; the others have none and ask for them).
  - `final_mm` (optional): stop at this size (an inspection limit) instead of where K reaches K_IC.
- `material` needs `fracture_toughness_MPa_sqrt_m` (K_IC) for a `fracture` check or a growth
  block: 6061-T6 (29), 7075-T6 (20, its lowest orientation) and Ti-6Al-4V (75) carry one. Steel,
  304 and brass do not (tough metals have no valid plane-strain K_IC): ask the user for the grade's
  tested value, never make it up.
- One part: solve the cracked part alone (`--occurrence`) in an assembly.
- Checks:
  - `fracture`: the largest equivalent K along the front, √(K_I² + K_II² + K_III²/(1 − ν)), against
    K_IC, held to `margin` (default 1.5). Fails at K ≥ K_IC, close past K_IC / margin. Row line
    "K 18 MPa√m at the deepest point, toughness 29 MPa√m"; titles "Crack grows" / "Close to the
    limit" / "Crack is safe". It follows the viewer's load control (K is linear in the load):
    "OK up to 1.6× this load" is the load at which the crack would grow. With no `view.checks` the
    study is judged by `{"kind": "fracture", "margin": 1.5}`.
  - `crack_life` (needs `growth`): `cycles`, the cycles the part must last with its crack, and
    `margin` (default 2: the life must be twice that to pass). Fails under the cycles needed, close
    under margin × cycles. Row line "Grows to critical in 350 thousand cycles, needs 100 thousand";
    titles "Breaks too soon" / "Close to the limit" / "Lasts long enough". No load control.
  - `stress` and `displacement`, as static. A stress check is rarely useful here: the stress at a
    crack's front is singular, so its peak grows without limit as the mesh is refined.

A 7075-T6 plate with a 2 mm edge crack, pulled at 100 MPa, cycled from 10 % to full load:

```json
{"analysis": "fracture",
 "material": "aluminum-7075-t6",
 "fixtures": [{"type": "roller", "faces": ["#o1.f3"]}],
 "loads": [{"type": "pressure", "faces": ["#o1.f4"], "pressure_MPa": -100}],
 "crack": {"kind": "edge", "face": "#o1.f1", "at_mm": [0, 0, 5], "normal": [0, 1, 0], "size_mm": 2},
 "growth": {"load_ratio": 0.1, "paris_C": 1.6e-11, "paris_m": 3.6},
 "view": {"checks": [{"kind": "fracture"}, {"kind": "crack_life", "cycles": 100000}]}}
```

(The Paris constants above are illustrative: use the alloy's own.)

## What comes out

- Fields as static: von Mises stress (its colours stop at the 99th percentile: the field is
  singular at the front; the field's entry carries `capped` with the peak, and the colour bar says
  "≥") and displacement, which shows the crack opening (the faces are drawn on
  both sides). The viewer draws dots along the crack's front, and its Study panel has a "Crack" row
  ("2 mm edge crack on face 4", the largest K its hint).
- Summary: `crack` (as given, with `words`), `K_max_MPa_sqrt_m` (the equivalent K that is judged),
  `K_I_MPa_sqrt_m`, `K_II_MPa_sqrt_m`, `K_III_MPa_sqrt_m` and `K_at_mm`, `K_point` ("the deepest
  point", "the surface", "mid-front", "the crack's edge") there; `toughness_MPa_sqrt_m`,
  `fracture_factor` (K_IC / K); `front`: every station along the front(s) with `s_mm`, `at_mm`,
  `K_I`, `K_II`, `K_III` and `J_N_per_mm`; `front_size_mm`, `domain_radius_mm`,
  `domain_change_percent` (how far K moved between two J domains: the accuracy); `growth`
  (`cycles`, `from_mm`, `critical_mm`, `to_mm`, `start_rate_mm_per_cycle`, the Paris constants and
  R) or null; the static numbers (displacement, forces).
- Curves (sidecar): `K_I`, `K_II`, `K_III` against the position along the front (mm), `front` saying
  which front each station is on (a through crack has two).
- Findings: `crack_grows` (error), `low_fracture_margin` (warning), `crack_life_short` (error),
  `low_crack_life_margin` (warning), `lefm_limit` (warning: 2.5 (K / yield)² is more than the crack's
  size, ASTM E399's size for plane strain: the plastic zone is not small, so LEFM is stretched),
  `front_accuracy` (warning: K moved more than 5 % between the two J domains), `crack_closed`
  (warning: K_I negative, the faces would press together), `mixed_mode` (info: K_II or K_III over a
  tenth of K_I). Static's stress findings are left out: the peak stress at a crack says nothing.
- CLI: the crack and its mesh, K and where (with its three modes) against K_IC, the change between
  the J domains, the crack growth, the largest displacement.

## How it is solved

- The crack is cut into the part with OpenCascade along its whole plane: the crack's own face and
  the rest of the plane split the part into solids that share their faces, so the mesh is
  conforming across the plane and the front is an edge. Every face keeps its ordinal.
- The front is meshed fine: about six quadratic elements across the J domain, whose radius is 0.4
  of the crack's smaller size (its depth or half length), in a tube along the whole front. Ordinary
  quadratic tets, not quarter-point ones (netgen's tets around a front are not the collapsed bricks
  quarter-point elements need); the domain integral does not need the near-tip field resolved.
- The nodes of the crack's faces are duplicated (the front's stay shared), so the faces open.
- K_I, K_II and K_III come from the domain interaction integral with the Williams plane-strain
  near-tip fields, at stations along the front about half a domain radius apart; J from the domain
  J-integral beside them (for mode I, J = K_I² (1 − ν²) / E). The integral is read on two domains
  (the second 0.6 times as big); their difference is `domain_change_percent`.
- Paris's law is integrated numerically from `size_mm` to the critical size a_c = a (K_IC / K)²,
  where K grows as √a (the geometry factor held at the value solved).

## Judging the answer (hand checks)

- A centre crack 2a long in a wide plate in tension σ: K = σ √(πa), times √(sec(πa / W)) for a plate
  W wide (Feddersen; 1.006 at 2a / W = 0.1). A 10 mm crack at 100 MPa: 12.6 MPa√m. cadgen is within
  2 % of it on its default front mesh (the test holds it to 5 %).
- A single edge crack a deep: K = 1.12 σ √(πa) for a small crack (Tada: F = 1.12 − 0.231 (a/W) +
  10.55 (a/W)² − 21.72 (a/W)³ + 30.39 (a/W)⁴ for a plate W wide, ends free to rotate). 5 mm at
  100 MPa: 14.0 MPa√m (14.2 with Tada's F at a/W = 0.05).
- A semicircular surface crack in a thick plate: K ≈ 1.04 σ √(πa / 2.46) at its deepest point and
  about 10 % more near the surface (Newman-Raju); cadgen's deepest point reads within about 5 %.
- Units: K in MPa√m is σ (MPa) × √(πa) with a in metres; MPa√mm is √1000 = 31.6 times larger.
- The crack life at a constant geometry factor Y is the closed form
  N = (a_c^(1−m/2) − a_0^(1−m/2)) / (C Y^m π^(m/2) Δσ^m (1 − m/2)), a in metres (Norton's
  Machine Design, eq. 6.4b); cadgen matches it within 2 %.
- Sanity: doubling the load doubles K and shrinks a_c four times; K_II and K_III are near zero for a
  crack across a pure tension.

## Limits

- LEFM only: valid where the plastic zone is small next to the crack and the part
  (`lefm_limit` says when it is not). No ductile tearing (J-R curves), no plastic collapse of the
  remaining ligament: check the net section with `static` or `nonlinear` too.
- Small-scale yielding, isotropic linear-elastic material, small strain. One part.
- K at a point where the front meets a free surface is read as plane strain; the real field there
  is a corner field, and the end stations are the least accurate.
- Curvature terms of a curved front are left out of the integral (a few percent on an ellipse).
- Crack growth keeps the crack's shape and grows it straight on in its plane, at a geometry factor
  held at the solved value: as a crack nears another face its factor grows, so the life is
  unconservative for a crack that grows across most of the section. No threshold ΔK_th, no
  overload retardation, no crack closure.
- A crack pressed shut (K_I negative) lets its faces overlap; it warns.

## When the model is big

It runs at any size. The ladder may take, each an `adapted:` line to report:

- `iterative`: an AMG-preconditioned (or a matrix-free) iterative solver. Exact.
- `local_refine`: a coarse pass away from the crack, then a pass fine where the coarse one peaked;
  the crack's front keeps its own fine mesh throughout. Its accuracy is how far K moved between the
  passes. When even that misses the budget the front itself is meshed coarser, never under three
  elements across its J domain, and the step says so.
- `defeature`: small fillets and holes far from the loads, fixtures and the crack's face left out
  of the mesh; the crack is cut into the simplified part.
- `symmetry`: one half (or quarter) solved and mirrored, when the part, the fixtures, the loads,
  the checks and the crack are all symmetric about a plane that holds the crack's normal (never the
  crack's own plane: its faces are free and its ligament is not); the front's halves are joined.
