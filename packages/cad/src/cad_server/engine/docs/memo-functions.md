# Memo functions

A page of [the engine's documentation](../README.md). A name in bold in parentheses, such as (**Kinematics**), is another page or a named paragraph of one: the index says which.

`@memo`, bare, marks a function the engine may replay instead of executing (`model.py`,
`Memo`). A call of one inside a build is a body (**Body retention**), named by the
function and a digest of its arguments (`parts.py::wheel(3f2a…)`, the report's `bodies`):
its code is keyed as a model body's is, its kernel calls are logged, and a later build
with the same key replays it -- the same live objects, its features recorded again, so
names and provenance are what a run leaves. A second call with the same arguments in one
build is a new placement of the first's result, as a child model's is. It declares and
writes no file. Outside a build it is its function. Its contract:

- **Arguments by value**, snapshotted at the call (`memo.call_key`): None, bools,
  numbers, strings and bytes, tuples, lists and dicts of them (in order, at most
  `memo.ARGUMENT_VALUES` values), enums and paths; build123d's value types (`Location`,
  `Vector`, `Axis`, `Plane`, `Color`, `Rotation`) and a `Material`; a shape this process's
  operations made, by its memo key, and a replay needs that very TShape again. A call
  given anything else -- a callable, an arbitrary object, a shape made past the engine,
  too many values -- runs every time, as a plain call of its caller.
- **Geometry back**: a shape, or a tuple, list or dict whose leaves are shapes. A call
  returning anything else runs every time it is called (its log stays, for the bodies
  that called it).
- **OCCT's own makers**: a shape the call made past the engine -- an OCCT maker no key
  names, a hand-built B-spline surface made a face -- is keyed by the call itself
  (`memo.adopt`): when every shape it returns is such a shape, the result is one operation
  of the caller's, keyed by the call's name (its function and arguments) and by which run of
  it made them, and registered, so what the caller makes of them is keyed and kept. A replay
  hands back those very shapes, and the operation is a hit; a run of the call makes others,
  and a miss. Inside the call, a build123d operation on such a shape is unkeyed and keeps
  the call running: it returns them as made.
- **No methods**: `@memo` on a function whose first parameter is `self` or `cls` raises
  at decoration.
- **Pure**, the author's part: it reads only what its key holds -- its arguments, the
  code and values it reaches, the files it opens -- and writes nothing outside itself. A
  module global it sets for another function to read, a cache it fills on a shared
  object, an argument it mutates: none of it is seen, and a replay leaves it undone.

Each call that runs every time is named in the report's `retention.fallbacks` with why.
The restart key (**Build closure**) folds a `@memo` function's code in as it folds a
child model's.

**When to mark a function.** `@memo` saves only the Python cost of the kernel-memo hits a
replayed function avoids, 0.1–0.4 ms per hit, so mark a function only when it holds seconds of
kernel work an edit elsewhere leaves untouched: roughly a thousand kernel calls or more. Never
per part, never on a helper called many times; whole sub-assembly stages are the usual
candidates (tom's six stages, movement's three layers: 1.3–3 s each, and twice as fast on an
edit), while per-part markers measured under 0.1 s. Nested `@xbf` is never needed for caching:
the operation-level memo handles every kernel call in any model, markers or not. The one other
case is a builder several models call with the same arguments (nine posed copies of one
assembly): an operation's entry is keyed by the body that ran it, so two models never share one,
and unmarked the builder runs whole in each; marked, it runs once and the rest replay it.

A verifying build (`Model.build(verify=True)`) runs every
body the memo would replay -- a model's and every `@memo` call's -- and compares each fresh
result with the logged one: per shape its class, label, colour, paints, material and
placement, and each leaf's geometry: the same TShape, else the same binary BRep digest, else the
same geometry in another order of the BRep's entries (each face's area and centre, each edge's
length and centre, each vertex, sorted: what an order-only difference leaves alone, see **Known
and accepted**), which is `same`. The report's `verify` gives each body checked
as `same`, `differs: <where>`, or `follows <function>` for one whose result holds a body
that differs. A function whose result differs is marked to run on every call for the
worker's life (`memo.always()`), the bodies that call it with it, and a model that calls it
is not taken by its key. A verifying build does not ask the previous document.
