# Repo defects found while building the radial

Each entry: symptom, minimal trigger, workaround applied in this model. Only
defects of the repo's tooling (cadgen / skills), not of the model itself.

1. **STEP export can turn a valid solid into an invalid or garbage one.**
   - `heads:seat_1I`: correct and valid in Python, but read back from the saved
     STEP as a 2.85-litre "spike" (bbox 988 mm) — found by the kinematic gate.
     Trigger: a seat ring made by a boolean with the chamber sphere, then cut by
     the section cutter. Workaround: rebuilt the ring without the sphere boolean;
     the heads build now round-trips every cut leaf through STEP and aborts on
     growth.
   - `heads:head_2`: passes BRepCheck at every build stage in memory; written to
     STEP and read back, one small planar face at y = 109 in the intake-port
     throat fails with `BadOrientationOfSubshape`. Trigger: a swept port bore
     (circle along a spline, R24) meeting a straight cylindrical flange bore of
     the same R24 → near-coincident surfaces leave a sliver face. Workaround: a
     deliberate 0.4 mm step (R24.4 from y 104).
   - `propshaft:thrust_inner`: balls fused into the inner race failed BRepCheck
     only after the STEP round trip. Workaround: balls/cage as a separate body.
   Expected: the canonical STEP writer should either preserve validity or fail
   the build; today it silently writes an invalid/garbage solid.
2. **`gate --static`-style exact distance on big finned castings is extremely
   slow** (BRepExtrema: seconds to >10 min per pair on heads/crankcase); the
   model's gate uses mesh screens + OCC booleans instead.
