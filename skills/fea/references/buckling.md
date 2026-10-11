# Buckling (`buckling`)

Answers "will this column, strut or thin wall buckle, and at how many times
this load": the load factor λ at which the part's shape gives way sideways, and
the shape it buckles into. At λ times the study's load it buckles.

## When to use it

- A slender part pushed along its length: a column, a strut, a long pin, a
  thin rib or wall in compression, a tube under axial load.
- A static study says the stress is fine but the part is long and thin: a
  compressed slender part can buckle far below its yield.
- A part only pulled, bent or twisted gently does not buckle; the result then
  says "does not buckle under this load".

## Study

On top of the common keys in [study-file.md](study-file.md#common-keys):

- `fixtures` and `loads`: as `static` ([linear-static.md](linear-static.md)),
  body loads included. They are required.
- `modes`: how many buckling shapes to find, 1 to 30, default 3.
- Check `buckling`: `margin` (1 or more, default 3), the load factor it must
  keep. Below 1 it fails (the load as given buckles it); below the margin it is
  close. Row line: "Buckles at 13× this load, needs 3×". With no `view.checks`
  the study is judged by `{"kind": "buckling", "margin": 3}`.
- View drives: `mode`, `deformation`, `load_scale` (the factor moves as λ/k at
  k times the load), `field`, `threshold`. With no view: the mode picker and the
  deformation.

```json
{"analysis": "buckling", "material": "steel",
 "fixtures": [{"faces": ["#o1.f1"]}],
 "loads": [{"faces": ["#o1.f2"], "type": "force", "vector_N": [0, 0, -100]}],
 "modes": 3,
 "view": {"checks": [{"kind": "buckling", "margin": 3}]}}
```

## What it writes

- `summary.load_factors` (smallest first), `critical_load_N` (the first
  factor times the applied resultant), `modes`, `modes_requested`, and the
  prestress: `applied_force_N`, `reaction_force_N`, `max_von_mises_MPa`,
  `yield_MPa`, `yield_factor` (how many times this load before it yields).
- The GLB: one series frame per shape, labelled "Mode 1 · 13.3×", each scaled so
  its largest motion is 1 mm (the size itself means nothing), mode 1's also as
  the displacement; plus the prestress von Mises, the same in every frame. The
  Viewer's routine is Buckle.
- Findings: `buckles` (error) or `close_to_buckling` (warning) for the check;
  `first_buckling_mode` (info) with the critical load; `yields_before_buckling`
  (warning) when the part yields at a lower multiple than it buckles: then the
  material gives way first and the buckling factor is optimistic; `no_buckling`
  (info) for a load that does not compress it.
- A close check re-solves once on a finer mesh, and says how far the factor moved.

## Hand check

Euler's column, E in MPa, I the smaller second moment (mm⁴), L in mm:
P = π² E I / (K L)², with K = 2 fixed-free (a flagpole), 1 pinned-pinned,
0.7 fixed-pinned, 0.5 fixed-fixed. λ = P / applied load.

A 200 mm steel column, 6 x 6 mm, fixed at one end and pushed at the other:
P = π² · 200000 · 108 / (4 · 200²) ≈ 1332 N, so 100 N buckles it at 13.3×.
The solid reads within a percent of that. A thin wall or plate buckles in
ripples; its factor is far below a column hand check's, never above it.

## Limits

- Linear (eigenvalue) buckling of the perfect shape. A real part is never
  perfectly straight or loaded dead centre and buckles earlier, often by 20 %
  or more for thin shells: that is what the margin is for. Say so when you
  report.
- It says where buckling starts, not what happens after (no post-buckling).
- Elastic: if `yield_factor` is under the first load factor, the part yields
  first, and the yield factor is the real limit.
- Loads do not follow the deformation; fixed faces are perfectly rigid, which
  raises the factor (a real mount is softer).

## Adapted to fit

A model too big for the machine still runs; each step is reported ("adapted: ..."):

- `iterative`: the shapes are found with LOBPCG and a multigrid preconditioner
  instead of factorising the stiffness. No accuracy cost.
- `local_refine`, `defeature`, `linear_elements`: the shared mesh rungs.
  local_refine keeps the requested size where shape 1 bends the part most and
  says how far the first load factor moved between its passes. Linear
  elements read load factors high.
- `reduce_modes`: finds the first shape only, the one the check reads.
- `idealise` and `symmetry` are declared but not taken for buckling yet: shells
  and beams have no geometric stiffness here, and a symmetric half needs the
  antisymmetric shapes too (a column usually buckles antisymmetrically).
