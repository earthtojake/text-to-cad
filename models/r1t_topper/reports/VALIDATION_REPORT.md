# Validation report — Checkpoint 1

Status: **PASS for provisional reference-envelope use only**

## Checks run

- Python compilation passed for all Checkpoint 1 CAD sources.
- `cad/checkpoint1_checks.py` verifies:
  - the closed pickup tailgate extends from `Z=-510` to the bed-rail plane at
    `Z=0`;
  - the future cab/topper non-contact zone is positive and spans `X=0..20`;
  - all four crossbar references share one horizontal mounting elevation;
  - each crossbar envelope is `70 × 1750 × 28 mm` and is more than twenty times
    longer in Y than X.
- STEP generation passed for `R1T_TOPPER_ASSEMBLY.step`.
- CAD inspection reported a labeled assembly with 21 leaf occurrences / shapes,
  126 faces, 252 edges, and overall bounds:
  - minimum `[-685, -875, -510] mm`
  - maximum `[1202.6, 875, 813] mm`
- Stable occurrence references were confirmed for the bed, cab, tailgate,
  cab/topper keep-out, anchors, four crossbars, and coordinate artifact.
- Six saved snapshots were visually reviewed. The initial custom-camera packet
  made crossbar orientation visually ambiguous; it was replaced with exact CAD
  orthographic presets and regenerated.

## Phase 1 intent review

| Requirement | Result |
| --- | --- |
| Reference occupies the pickup bed, not an SUV conversion | PASS |
| Original pickup tailgate remains at/below bed-rail plane | PASS |
| Positive cab/topper non-contact zone exists | PASS |
| Crossbar reference elevations are consistent | PASS |
| All crossbars are transverse, left-to-right along Y | PASS |
| Detailed topper roof visually continues cab roof | NOT TESTED — Phase 2 |

## Known limitations

No vehicle value has yet been measured or approved as a manufacturer reference.
The cab and bed are intentionally crude block envelopes. This report does not
claim fitment, structural capacity, legal compliance, aerodynamic performance,
electronics compatibility, manufacturability, or production readiness.
