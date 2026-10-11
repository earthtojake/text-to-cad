# Permanent bend / Stretch (`nonlinear`, lite)

It answers "does it bend for good, and how much", "at what load does it give way" (a metal part
past yield), and "how far does this rubber part stretch or squash" (large deformation). The load is
applied in steps, from nothing to the full load, and the part is followed through them, so the
answer is not a straight line from a linear solve. The plain word is Permanent bend / Stretch.

**It is a lite solver. Its limits are written into every result** (`analysis.limits`, the
verdict's "Lite · " and its Details): small-strain J2 metal plasticity with isotropic hardening
only, no rate or temperature effects, Neo-Hookean rubber, loads that keep their direction. Say
them whenever you quote a number from it.

## When to use it

- A static study says the part yields (safety factor under 1) and the user wants to know whether
  it bends for good, by how much, or whether it still holds: a bracket overloaded once, a clip
  bent past its spring, a tab pushed flat.
- "At what load does it give way?": push it with more than it can take and it reports where it
  collapses ("Collapses at about 70 % of the load"), never a refusal.
- A rubber or elastomer part stretched or squashed by more than a few percent: a gasket, a grip,
  a bumper, a seal, a flexure in TPU.
- Not for: repeated or reversed loads (fatigue, cyclic plasticity), creep, impact or anything fast,
  heat softening, contact between parts (that is `contact`), or a metal past large strains (tens
  of percent: necking and tearing are not modelled).

## The study

On top of the common keys in [study-file.md](study-file.md#common-keys):

- `fixtures` and `loads`: as `static` ([linear-static.md](linear-static.md)), body loads
  included; required. The loads are the full load; the solver ramps them up.
- `steps`: how many equal load steps to start with, 1 to 200, default 10. A step that does not
  converge is halved and tried again (up to six times, down to 1/64 of a step), then the solve
  carries on at the step it got through with.
- `material` must say how it behaves past the linear range, one of:
  - Metal (J2 plasticity): `plasticity: {"tangent_MPa": 2000}` (or `tangent_MPa` at the top of
    the object) is the slope of the stress-strain curve past `yield_MPa`; `0` is perfectly
    plastic (the limit-load case). It must be under E. Steel's 2000 MPa is a common bilinear
    guess; use the grade's own curve (UTS minus yield over the strain to UTS) when the user has it.
  - Rubber (Neo-Hookean): `hyperelastic: {"model": "neo_hookean", "mu_MPa": 0.6, "bulk_MPa": 300}`,
    μ the shear modulus, the bulk modulus about 500 μ for a nearly incompressible rubber. A rubber
    needs no `E_MPa`, `nu` or `yield_MPa` (its small-strain E and ν come from μ and the bulk
    modulus, and it has no yield).
  - A material with neither is refused with a sentence saying which block to add.
- In an assembly, a part with neither block stays elastic (in a rubber study, an elastic part is a
  Neo-Hookean of its own E and ν; a metal part's plasticity is then left out, with a warning).
- Checks, each judged at the last load the part carried:
  - `plastic_strain`: `limit_percent`, the most permanent strain allowed (the equivalent plastic
    strain, in percent). Fails over the limit, close past 0.9 of it. Row line "0.4 % permanent,
    limit 0.2 %". With no `view.checks` the study is judged by `{"kind": "plastic_strain",
    "limit_percent": 0.2}`, the 0.2 % offset that defines yield. A rubber reads 0 ("Springs back").
  - `stress`: the peak von Mises against the yield (as static); refused for a rubber with no yield.
  - `displacement`: `limit_mm`, optional `faces` (as static).
  - A part that collapses fails every check, whatever its numbers at the last load carried.
- No load control (`load_scale` is not a drive): the response is not proportional to the load.
  View drives: `frame` (the load-step scrubber), `field`, `deformation`, `threshold`. With no view:
  the load-step scrubber, the field and the deformation.

Metal (perfectly plastic steel, pushed past its collapse load):

```json
{"analysis": "nonlinear",
 "material": {"name": "steel", "plasticity": {"tangent_MPa": 0}},
 "mesh": {"size_mm": 2},
 "fixtures": [{"faces": ["#o1.f1"]}],
 "loads": [{"faces": ["#o1.f2"], "type": "force", "vector_N": [0, 0, -127]}],
 "steps": 10,
 "view": {"checks": [{"kind": "plastic_strain", "limit_percent": 0.2},
                     {"kind": "displacement", "limit_mm": 2}]}}
```

Rubber (a pad stretched):

```json
{"analysis": "nonlinear",
 "material": {"name": "rubber 50A (estimate)",
              "hyperelastic": {"model": "neo_hookean", "mu_MPa": 0.82, "bulk_MPa": 409}},
 "fixtures": [{"faces": ["#o1.f5"]}],
 "loads": [{"faces": ["#o1.f6"], "type": "force", "vector_N": [0, 0, 30]}],
 "steps": 8,
 "view": {"checks": [{"kind": "displacement", "limit_mm": 5}]}}
```

### Rubber from its Shore A hardness: a first guess, labelled as an estimate

There is no rubber in the material table. When the user knows only a hardness, offer Gent's
relation as a first guess and say it is an estimate, in the study (put "estimate" in the material's
`name`) and in your reply: E ≈ 0.0981 (56 + 7.62336 S) / (0.137505 (254 − 2.54 S)) MPa, μ = E/3,
bulk = 500 μ.

| Shore A | μ_MPa | bulk_MPa |
| --- | --- | --- |
| 30 | 0.38 | 190 |
| 40 | 0.56 | 282 |
| 50 | 0.82 | 409 |
| 60 | 1.20 | 601 |
| 70 | 1.84 | 920 |
| 80 | 3.12 | 1559 |

A measured stress-strain curve beats it; hardness to modulus scatters by ±30 % between compounds.

## What comes out

- A series of load steps as pseudo-time (`series.kind` "time", unit "%"), frames labelled "60 %
  load", at most 24 (evenly spread, the last load carried always kept and opened on). Each frame
  has `von_mises` (MPa; for rubber the true stress), `displacement` and, for a metal,
  `plastic_strain` (the equivalent plastic strain, %). Nodal values never pass the integration
  points' own range. The viewer scrubs them (Load step) and plays them (Play).
- Summary: `status` ("Carries the full load" or "Collapses at about 70 % of the load"),
  `collapsed`, `load_percent` (the last load carried), `collapse_percent`, `material_model`,
  `max_von_mises_MPa` (and the Gauss-point value), `max_displacement_mm`,
  `max_plastic_strain_percent` (metal), each with where, `applied_force_N` (carried),
  `requested_force_N`, `reaction_force_N`, `steps_requested`, `steps` (converged), `step_cuts`,
  `smallest_step_percent`, `newton_iterations`, `adaptive`, `frames`, `checks`. Curves: the largest
  displacement (and plastic strain) against the load in %.
- Findings: `collapses` (error: "The part collapses at about 70 % of the load: it carries about
  88 N, not the full load"), `bends_for_good` (error, the plastic_strain check failing),
  `stays_elastic` (info: nothing yielded, a static study says the same), `load_steps_cut` (info).
- CLI: the status, peak stress, displacement and permanent strain; what was carried of what was
  asked; the steps and Newton iterations.

### What "collapses" means

The load is stepped up; at each step Newton's method looks for equilibrium. Where it finds none,
or where the part runs away (a step moves it more than 500 times as far as the unloaded part would
move for the same added load: a plastic hinge has formed, or a rubber part snaps through), the step
is halved, down to 1/64 of the starting step. When even that does not hold, the part has collapsed
at the last load it carried. That load is the result: report it as "collapses at about N % of the
load (X N)", not as a failure of the tool.

## Judging the answer (hand checks)

- A bar pulled past yield (bilinear): strain = σ/E + (σ − σy)/H, H = E·Et/(E − Et). Steel at
  350 MPa with Et = 2000 MPa: 0.00175 + 100/2020 = 5.1 %. The solver matches it to round-off.
- A cantilever's plastic collapse (rectangular b × h, length L, perfectly plastic): the fully
  plastic moment σy b h²/4 at the root, so P = σy b h² / (4 L), 1.5 times the load that first yields
  it. The solver lands within 5 % (a fixed face's constraint and the mesh make it read a little high:
  about 4.5 % at L/h = 13, 3 elements through the depth).
- Rubber in plain tension (nearly incompressible Neo-Hookean): nominal stress μ (λ − 1/λ²). μ =
  0.6 MPa stretched to twice its length carries 1.05 MPa. The solver matches within 0.2 %.
- Rubber in shear: the shear stress is μ γ, linear even at large strain.
- Sanity: below yield the result equals a static study's; past it the stress stays near the yield
  (perfectly plastic: never above it) and the displacement grows faster than the load.

## Limits

- Metal plasticity is small strain: rotations and strains must stay small (a few percent). Past
  that, the displacement is indicative only. Von Mises (J2) yield, bilinear curve, isotropic
  hardening only: no kinematic hardening (Bauschinger effect), so reversed and cyclic loading are
  not modelled. Mean dilatation (a constant pressure per element) keeps plastic flow from locking.
- No rate or temperature effects: no creep, no strain-rate hardening, no heat softening.
- Rubber is Neo-Hookean (one constant μ, plus the bulk modulus): fair to stretches of about 100 %
  in tension, stiffening beyond that is not captured; no Mullins softening on reloading, no
  viscoelasticity or damping.
- Loads keep their size and direction as the part deforms (dead loads); a pressure does not turn
  with the surface. Fixtures are rigid.
- The load is stepped up only; the path past a collapse (the falling branch) is not followed.

## When the model is big

It runs at any size. The ladder may take, each an `adapted:` line to report:

- `iterative`: Newton-Krylov: each Newton step solved by GMRES with a multigrid preconditioner (the
  hierarchy kept through a load step) instead of factorising the tangent. Exact (same tolerance);
  said when it saves memory or time.
- `adaptive_steps`: the load steps grow (up to 4 times the starting step) while Newton converges in
  four iterations or fewer, and are still cut where it does not. Fewer solves where the part answers
  smoothly. For a metal its note says the plastic strain is followed in larger steps; the collapse
  load is still found to within the smallest step. Exact for rubber.
- `local_refine`: a coarse pass, then a pass fine only where the coarse one peaked in stress.
- `defeature`: small fillets and holes far from the loads and fixtures left out of the mesh.
- `symmetry`: one half (or quarter) solved and mirrored, when the part, the fixtures, the loads
  and the checks are all symmetric.
