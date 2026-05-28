# build123d modeling patterns

Read this file when writing or repairing build123d Python source.

## Contents

- Modeling objective
- Topology stack
- Source envelope
- Parameters first
- Coordinate system
- Builder contexts
- Primitives
- Feature operations
- Selection practices
- Assemblies and positioning
- Labels and assemblies
- Common failure modes

## Modeling objective

Create a valid STEP-ready BREP model, not a visual mesh. Prefer closed solids, explicit labels, and stable parametric dimensions.

## Topology stack

Think in this order:

```text
Vertex → Edge → Wire → Face → Shell → Solid → Compound
```

For normal STEP output, return one of:

- a valid `Solid`
- a compound of valid solids
- a labeled assembly compound

Avoid returning loose wires, open faces, or construction surfaces unless the user explicitly requested them.

## Source envelope

Generated sources should define:

```python
def gen_step():
    ...
    return shape_or_compound
```

Do not hardcode output paths inside `gen_step()`. The CLI owns output paths.

## Parameters first

Put meaningful dimensions in named variables:

```python
width = 80.0
depth = 50.0
thickness = 6.0
hole_diameter = 4.5
hole_offset_x = 30.0
hole_offset_y = 17.5
```

Avoid burying important numbers inside geometry calls.

## Coordinate system

Declare or comment the convention:

```text
Origin: center of primary part or chosen mating datum
XY: main base/sketch plane
+Z: up/extrusion direction
```

Use `Location`, `Plane`, and `Axis` intentionally. For positioning-sensitive tasks and source-level assembly relationships, read `positioning.md`.

## Builder contexts

Use the context that matches the geometry:

```python
with BuildLine() as path:
    ...

with BuildSketch() as profile:
    ...

with BuildPart() as part:
    ...
```

Typical flow:

```text
curves/paths → sketches/profiles → solids/features → labels → STEP
```

## Primitives

Use canonical primitives when they fit the design intent:

- `Box` for rectangular blocks and plates
- `Cylinder` for bosses, rods, pins, and subtractive cylindrical cuts
- `Sphere` for knobs or spherical ends
- `Torus` for rings and circular sweeps
- `Cone` for tapered features
- `Wedge` for sloped solids

Use sketches plus `extrude`, `revolve`, `sweep`, or `loft` when the shape is profile-driven.

## Feature operations

Map design intent to operations:

```text
hole              → Hole or subtractive cylinder
counterbore       → CounterBoreHole
countersink       → CounterSinkHole
slot              → slot profile + subtractive extrude
boss/standoff     → cylinder addition + central hole
rib               → extruded rectangular/triangular profile
rounded edge      → fillet
beveled edge      → chamfer
hollow enclosure  → shell or subtractive inner volume
revolved part     → revolve profile
swept tube/rail   → sweep profile along path
```

## Selection practices

Avoid fragile topology order when possible. Select by:

- axis or normal
- location or bounding position
- plane grouping
- feature intent
- stable construction plane
- inspected `@cad[...]` reference for downstream validation

For source operations, prefer robust selectors such as top/bottom by axis or position rather than arbitrary list indexes.


## Assemblies and positioning

For assemblies, keep this file focused on BREP modeling patterns and labels. Use `positioning.md` as the single source of truth for:

- part-local coordinate conventions
- when to use `cadpy.assembly.AssemblyHelper`, build123d joints, or explicit `Location` transforms
- `connect_to()` behavior
- CLI `inspect mate` as read-only validation
- frame, measure, and positioning report expectations

## Labels and assemblies

Label every exported part and assembly child with native build123d labels. Prefer semantic labels through `cadpy.assembly` helpers:

```python
from cadpy.assembly import AssemblyHelper, label_shape

asm = AssemblyHelper("electronics_enclosure")
base = asm.add(make_base(), "base")
lid = asm.add(make_lid(), "lid")

boss = label_shape(Cylinder(radius=3.0, height=12.0), "feature", "m3_boss", "front_left")
```

Useful label prefixes are `assembly:`, `module:`, `component:`, `feature:`, `datum:`, `mate:`, and `hardware:`. Feature labels survive STEP export best when the feature remains a labeled child shape in a `Compound`; boolean-subtracted or fused feature history should be represented by source parameters, named datums, and validation refs instead of assumed persistent feature labels.

For repeated parts, keep transforms or joint connections explicit and inspect frames/positioning after generation.

## Common failure modes

- Fillet radius larger than local edge geometry.
- Subtractive tool does not pass fully through target material.
- Open sketch profile produces invalid or missing face.
- Face selector changes after a boolean or fillet.
- Source-level assembly composition is lost by re-importing generated STEP instead of using the Python assembly source.
- Part origin is arbitrary and later mating checks become ambiguous.
- Joint labels are duplicated within the same part.
- Source-level joints are treated as if they were persistent STEP constraints rather than one-time source placement operations.
- Joint labels are missing, duplicated, or attached to the wrong local datum.
- `.connect_to()` fixes the wrong side of the relationship, moving the part intended to remain fixed.

Use `repair-loop.md` when generation or validation fails.
