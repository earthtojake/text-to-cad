# Implicit against B-rep

A manual benchmark of the same three parts built three ways, each in a fresh
process with a fresh cadgen store:

- **brep**: a build123d script through `@step` and `@glb` (the store, a STEP,
  a tessellated GLB).
- **sdf**: the same part as an implicit field (`cadgen.implicit`), contoured to
  a GLB.
- **hybrid**: the implicit part with its STEP exported beside the mesh.

The parts are a rounded housing with a bore, boss and holes; an open-bottom
enclosure with screw bosses and a cable notch; and a revolved, shelled knob with
eight grip cuts (the shell OpenCascade refuses, so the B-rep script falls back
to a solid body and the implicit STEP is not written: read the notes column).

```sh
./.venv/bin/python scripts/bench/implicit-vs-brep/run.py
BENCH_RUNS=5 ./.venv/bin/python scripts/bench/implicit-vs-brep/run.py
```

It prints one line per part and method (median cold and warm seconds, file
sizes, notes), then the housing's SDF build at five resolutions, and writes
`tmp/bench-implicit/results.json`. Everything it produces is under the ignored
`tmp/`; nothing here runs in CI. Record the checkout and hardware beside any
numbers you keep.

Reference results (26 Sep 2026, M-series MacBook, medians of three):

| Part | brep | sdf | hybrid |
| --- | --- | --- | --- |
| housing | 5.69 s | 0.27 s | 1.89 s |
| enclosure | 5.80 s | 0.99 s | 2.74 s |
| knob | 6.39 s (shell failed, built solid) | 3.48 s | 9.02 s (no STEP) |

The kernel import alone was 2.2 s. The STEP-first default of `@im.part` (no
mesh) measured 2.7 s for the housing and 2.9 s for the enclosure the next day.
