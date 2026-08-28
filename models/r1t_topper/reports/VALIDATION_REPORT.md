# Validation report — Phase 2 conceptual envelope

Status: **PASS for conceptual envelope review only**

## Checks run

- Python compilation passed for all current CAD sources.
- `cad/checkpoint1_checks.py` verifies:
  - the manufacturer-reference bed envelope is `1377 mm` long, `1299 mm`
    wide, and `465 mm` deep;
  - the closed pickup tailgate extends from `Z=-510` to the bed-rail plane at
    `Z=0`;
  - the concept footprint begins at the forward bed plane (`X=0`); this does
    not establish a production cab contact or seal;
  - all four crossbar references share one horizontal mounting elevation;
  - each crossbar envelope is `70 × 1750 × 28 mm` and is more than twenty times
    longer in Y than X.
- `cad/phase2_checks.py` verifies:
  - five ordered silhouette sections taper monotonically in height and base
    width from front to rear and remain tagged `ESTIMATED`;
  - roof height and width remain nearly constant through the 78% station, with
    the visible narrowing and drop concentrated in the final rear-corner
    segment;
  - the master envelope spans `X=0..1462 mm`, sharing the tailgate outer back
    plane and covering the bed-plus-tailgate top-plane length;
  - all five base sections are `1730 mm` wide, so the conceptual footprint
    reaches both provisional bed edges for its full length;
  - its provisional maximum envelope is `1462 × 1730 × 760 mm`;
  - the rail, cab, anchor, control, and crossbar mounting inputs remain tagged
    `PLACEHOLDER REQUIRING SCAN`.
- STEP generation passed for `R1T_TOPPER_ASSEMBLY.step`.
- CAD inspection reported a labeled assembly with 21 leaf occurrences / shapes,
  128 faces, 258 edges, no warnings, and overall bounds:
  - minimum `[-685, -875, -510] mm`
  - maximum `[1462, 875, 813] mm`
- The topper bottom face spans `X=0..1462 mm`, `Y=-865..865 mm` and has area
  `2,529,260 mm²`, exactly the `1462 × 1730 mm` conceptual footprint.
- The topper rear face and tailgate outer face are parallel at `X=1462 mm`;
  the measured flush-alignment translation is `0 mm`.
- Stable occurrence references were confirmed for the bed, cab, tailgate,
  anchors, four crossbars, and coordinate artifact.
- Six regenerated snapshots were visually reviewed. The master envelope is one
  coherent blue concept volume with rounded crown/shoulders, an R1S-like level
  roof continuation, and a localized rear-corner taper; the cyan rail/crossbar
  references remain visibly distinct placeholders.

## Intent review

| Requirement | Result |
| --- | --- |
| Reference occupies the pickup bed, not an SUV conversion | PASS |
| Original pickup tailgate remains at/below bed-rail plane | PASS |
| Concept footprint starts at forward bed plane | PASS |
| Crossbar reference elevations are consistent | PASS |
| All crossbars are transverse, left-to-right along Y | PASS |
| Concept volume occupies the intended bed-plus-tailgate envelope | PASS |
| Rear face shares the tailgate outer back plane | PASS |
| Base footprint reaches both bed edges for its full length | PASS |
| Estimated silhouette is symmetric and visually R1S-like | PASS |
| Concept volume remains visibly distinct from scan-required references | PASS |
| Production cab-roof continuation and curvature | NOT TESTED — scan required |

## Known limitations

No vehicle value has yet been physically measured. The bed length, exposed
cargo width, and maximum bed height are manufacturer references; their precise
values come from Rivian's September 2025 R1T Upfitting Guide and require
confirmation on the target 2022 Gen 1 vehicle. The cab and bed rails remain
intentionally crude block envelopes. The master topper is a solid design-volume
proxy, not a shell, mold surface, mounting system, or clearance proof. This
visual match is based on perspective screenshots, not measured sections. This
report does not claim fitment, structural capacity, legal compliance,
aerodynamic performance, electronics compatibility, manufacturability, or
production readiness.
