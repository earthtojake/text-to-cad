# Reusing parameterized CAD computations

`@memo` is an optional decorator for an expensive, pure geometry factory.
It can skip the factory's Python and CAD work when its inputs are unchanged.
It declares no output, model record, job or CLI command; a parameterless
`@step` model still owns the build and all declared exports.

```python
# geometry.py
from cadgen import memo, build123d as bd

@memo
def drilled_plate(width, holes):
    with bd.BuildPart() as plate:
        bd.Box(width, 20, 6)
        for i in range(holes):
            with bd.Locations((-width / 2 + 5 + i * 8, 0, 0)):
                bd.Cylinder(2, 10, mode=bd.Mode.SUBTRACT)
    return plate.part
```

Call it with ordinary arguments inside a model, for example
`drilled_plate(40.0, 4)`. Keep independently reusable factories in a helper
module when the parent model's dimensions or placement change frequently.
The cache includes each factory/helper's captured source file digest: editing
another function in that same file conservatively invalidates its entries too.
It does not infer independent feature histories from arbitrary monolithic Python.

## Author contract

Adding `@memo` declares that the factory computes geometry only from its
arguments and captured immutable Python globals, defaults, closure values and
deterministic helpers, under an unmodified CAD/math dependency runtime. It must
have no externally observable side effects. Do not use it for file reads or
writes, logging/progress reporting, random/time/environment inputs, child model
builds, dependency monkeypatches, process hooks, callbacks or object-identity
tests. It is not a Python sandbox or an automatic proof of purity.

The first implementation accepts a bounded vocabulary of ordinary CAD/math
operations, exact immutable scalar values and tuples, and ordinary helpers.
Nonfinite floats, mutable/protocol-bearing inputs, nested code, unknown calls
and an enclosing builder/location/workplane context decline reuse and execute
the original function. Unsupported shape classes or attribute recipes also
execute without storing their result. Use ordinary `Solid` or a builder's
`.part` for reusable geometry; a primitive's specialized `Box` wrapper is not
necessarily reconstructible by the canonical shape codec.

Prefer this decorator for costly repeated booleans or builders. Validation,
key construction and private BREP reconstruction have a cost; decorating a
cheap primitive can make it slower. Ordinary undecorated factories remain valid.

## Execution and recovery

A fresh daemon worker establishes its runtime witness before loading authored
modules. Transient workers do the same in their internal startup path. This
is an ordering guarantee within cadgen, not verification of arbitrary Python
startup hooks or a modified third-party installation. Runtime checks defend
against covered namespace, descriptor and context changes; they do not make
dependency mutation part of the supported contract.

Generic embedded/in-process execution cannot prove that initialization order,
so it executes the body. An existing untrusted witness cannot be upgraded.
Eligible calls still use the canonical return codec consistently: cache miss,
hit and `CADGEN_MEMO_CACHE=0` return equivalent private reconstructions. The
decorator can therefore change wrapper/native identity compared with an
undecorated call. Do not depend on the identity of an intermediate handle.
Arguments and returned native geometry are never retained for sharing across
independent calls.

The existing operation index contains the input key and the immutable result
object address. The key includes bound argument values, loaded code and helper
identity, captured source digests, globals/defaults/closures, scheme and runtime
versions. The result contains canonical BREP and its attribute recipe, with no
source path in the object. Hits verify the required disk object and reconstruct
private geometry; missing/corrupt data runs the factory and repairs the entry.
There is no native RAM cache or second storage framework. Process eviction and
store deletion remain recoverable. Source dependencies remain in the owning
model's closure even when a memoized body is skipped.

`CADGEN_MEMO_CACHE=0` disables result reuse for diagnosis. It does not force
a current model to rebuild; use the model's normal `--force` flag as needed.
No agent imports cache keys, sessions, persistence or invalidation utilities.
The full object/index and publication rules are in [STORE.md](STORE.md).
