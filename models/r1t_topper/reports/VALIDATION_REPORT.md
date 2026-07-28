# Validation report — Phase 2 conceptual envelope

Status: **PASS for conceptual envelope review only**

## Checks run

- Python compilation passed for all current CAD sources.
- `cad/checkpoint1_checks.py` verifies:
  - the manufacturer-reference bed envelope is `1377 mm` long, `1299 mm`
    wide, and `465 mm` deep;
  - the closed pickup tailgate extends from `Z=-510` to the bed-rail plane at
    `Z=0`;
  - the future cab/topper non-contact zone is positive and spans `X=0..20`;
  - all four crossbar references share one horizontal mounting elevation;
  - each crossbar envelope is `70 × 1750 × 28 mm` and is more than twenty times
    longer in Y than X.
- `cad/phase2_checks.py` verifies:
  - five ordered silhouette sections taper monotonically in height and base
    width from front to rear and remain tagged `ESTIMATED`;
  - the master envelope spans `X=20..1357 mm`, leaving the intentional
    conceptual `20 mm` front and rear clearances within the `1377 mm`
    manufacturer-reference bed length;
  - its provisional maximum envelope is `1337 × 1730 × 760 mm`;
  - the rail, cab, anchor, control, and crossbar mounting inputs remain tagged
    `PLACEHOLDER REQUIRING SCAN`.
- STEP generation passed for `R1T_TOPPER_ASSEMBLY.step`.
- CAD inspection reported a labeled assembly with 22 leaf occurrences / shapes,
  134 faces, 270 edges, no warnings, and overall bounds:
  - minimum `[-685, -875, -510] mm`
  - maximum `[1462, 875, 813] mm`
- Stable occurrence references were confirmed for the bed, cab, tailgate,
  cab/topper keep-out, anchors, four crossbars, and coordinate artifact.
- Six regenerated snapshots were visually reviewed. The master envelope is one
  coherent blue concept volume with rounded crown/shoulders and a modest
  rearward width/height taper; the cyan rail/crossbar references remain visibly
  distinct placeholders.

## Intent review

| Requirement | Result |
| --- | --- |
| Reference occupies the pickup bed, not an SUV conversion | PASS |
| Original pickup tailgate remains at/below bed-rail plane | PASS |
| Positive cab/topper non-contact zone exists | PASS |
| Crossbar reference elevations are consistent | PASS |
| All crossbars are transverse, left-to-right along Y | PASS |
| Concept volume occupies the intended bed-length envelope | PASS |
| Estimated silhouette is symmetric and visually tapered | PASS |
| Concept volume remains visibly distinct from scan-required references | PASS |
| Production cab-roof continuation and curvature | NOT TESTED — scan required |

## Known limitations

No vehicle value has yet been physically measured. The bed length, exposed
cargo width, and maximum bed height are manufacturer references; their precise
values come from Rivian's September 2025 R1T Upfitting Guide and require
confirmation on the target 2022 Gen 1 vehicle. The cab and bed rails remain
intentionally crude block envelopes. The master topper is a solid design-volume
proxy, not a shell, mold surface, mounting system, or clearance proof. This
report does not claim fitment, structural capacity, legal compliance,
aerodynamic performance, electronics compatibility, manufacturability, or
production readiness.
