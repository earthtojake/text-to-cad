# Implicit solids

Read this file when a part is easier to say as a field than as B-rep operations: blended
unions, a constant wall that follows the blends, lattice nodes, gyroids and other triply
periodic surfaces, organic shapes. These are the cases where OCCT's fillet and shell refuse.
Machined parts with exact faces, holes, threads and selectable cylinders stay B-rep.

## Contents

- [A field is a function of points](#a-field-is-a-function-of-points)
- [The cell](#the-cell)
- [What is refused](#what-is-refused)
- [Field recipes in numpy](#field-recipes-in-numpy)
- [Fields from other libraries](#fields-from-other-libraries)
- [Checking a field part](#checking-a-field-part)

## A field is a function of points

`cadgen.implicit.solid(field, bounds, cell)` turns a field into a solid inside the model's body.
`field(points)` takes an `(N, 3)` array of millimetres and returns `N` numbers, negative inside.
The result is an ordinary build123d solid made of planar triangles, so the body colours, labels,
places and returns it like any part, and an assembly composes it with B-rep parts:

```python
import build123d as bd
import numpy as np
from cadgen import model
from cadgen.implicit import solid


def node_field(p):
    tubes = [capsule(p, (0, 0, 0), tip, 6.0) for tip in ((30, 0, 0), (-30, 0, 0), (0, 30, 0),
                                                          (0, -30, 0), (0, 0, 30), (0, 0, -30))]
    field = tubes[0]
    for tube in tubes[1:]:
        field = blend(field, tube, 4.0)          # a 4 mm blend at every root
    wall = np.abs(field) - 1.0                   # a 2 mm wall that follows the blends
    return np.maximum(wall, np.linalg.norm(p, axis=1) - 28.0)   # cut open by a ball


@model
def node():
    body = solid(node_field, bounds=((-30, -30, -30), (30, 30, 30)), cell=1.0)
    body.label, body.color = "node", "#c8a46e"
    return body
```

Everything else is the usual workflow: run the script, show the page, `cadgen snapshot`,
`cadgen inspect`, `cadgen export` (STEP, STL, 3MF, GLB, xbf). A STEP of a field part is faceted:
one planar face per triangle, so no face is a cylinder and a radius reads as chords. Say so when
handing a STEP to a check that needs exact radii (`$dfm`, `$sendcutsend`).

The field runs in the model's worker, every time the body runs. A body whose edit leaves the
field's surface unchanged (a colour, another part) keeps the triangles and their face names.

## The cell

`cell` is the sampling step in millimetres and the resolution of the part: detail finer than it
is not in the result.

- Choose it from the thinnest wall or gap: at least two cells across it, four when its thickness
  matters. A 2 mm wall wants a 1 mm cell, 0.5 mm for a dimension to hold.
- Cost grows with the surface's area over the cell's square: halving the cell quadruples the
  triangles, the build time and every file. A 60 mm node at a 1.25 mm cell is about 49,000
  triangles, a 31 MB xbf, a 113 MB STEP and a 2.3 MB STL. Draft at a coarse cell and refine once
  the shape is right.
- `bounds` must hold the whole part with a cell to spare on every side.
- Sharp creases from a hard `np.minimum`/`np.maximum` come out slightly ragged at the cell's
  scale; blends come out smooth.

## What is refused

A build fails, naming where and what to change, rather than writing a wrong part:

| Message says | Change |
| --- | --- |
| `the bounds cut the part` | wider `bounds` |
| `nowhere inside the bounds` | the field's sign (negative inside), or `bounds` |
| `a wall or a feature thinner than the cell` | a smaller `cell`, or a thicker wall |
| `a gap or a hole thinner than the cell` | a smaller `cell`, or a wider gap |
| `the surface folds there` | a smaller `cell` |
| `past the ... the engine samples` | a larger `cell` or smaller `bounds` |
| `every value must be finite` | the field at the point named (a division, a `log`) |

## Field recipes in numpy

Distances in millimetres. Each takes `p`, the `(N, 3)` points.

```python
def sphere(p, centre, r):
    return np.linalg.norm(p - np.asarray(centre, float), axis=1) - r


def box(p, centre, half):                         # half-extents
    q = np.abs(p - np.asarray(centre, float)) - np.asarray(half, float)
    return np.linalg.norm(np.maximum(q, 0), axis=1) + np.minimum(q.max(axis=1), 0)


def capsule(p, a, b, r):                          # a rod from a to b
    a, b = np.asarray(a, float), np.asarray(b, float)
    t = np.clip(((p - a) @ (b - a)) / ((b - a) @ (b - a)), 0, 1)
    return np.linalg.norm(p - a - t[:, None] * (b - a), axis=1) - r


def blend(a, b, k):                               # union rounded by k mm
    h = np.clip(0.5 + 0.5 * (b - a) / k, 0, 1)
    return b * (1 - h) + a * h - k * h * (1 - h)


def gyroid(p, period, thickness):                 # a sheet; intersect it with a body
    x, y, z = (2 * np.pi / period * p).T
    return np.abs(np.sin(x) * np.cos(y) + np.sin(y) * np.cos(z) + np.sin(z) * np.cos(x)) - thickness
```

Union is `np.minimum(a, b)`, intersection `np.maximum(a, b)`, difference `np.maximum(a, -b)`, a
wall of thickness `t` around any surface `np.abs(f) - t / 2`, an offset `f - d`. A blend grows
the part near the seam by up to `k / 4`, so keep faces whose position matters more than `k` from a
blended seam. A gyroid's value is no distance: the sheet's thickness follows `thickness` and
`period` together, so measure it.

## Fields from other libraries

Any library that evaluates points works: return its answer, and cadgen reads it with
`numpy.asarray`. JAX (and a JAX field kernel such as cadjoint) runs on the CPU; the field is
called in chunks of a fixed size, so a `jax.jit` traces it a few times, not once a call. A library the
model imports is the project's dependency, declared in its `requirements.txt` or
`pyproject.toml`; cadgen does not install it.

## Checking a field part

- The field is plain Python: assert a dimension on the field itself in the body, where it is
  exact and cheap. For a true distance field the value at a point is its distance to the surface,
  so a wall's half-thickness is the field's depth at its middle: `node_field(np.array([[6.0, 0,
  15]]))` is `[-1.0]`, the middle of the z tube's 2 mm wall.
- The part's bounds, volume and mass are `cadgen inspect "$ID"`, measured on the triangles.
- A clipped snapshot shows a wall's section ([clipped views](snapshot-review.md#clipped-views)).
