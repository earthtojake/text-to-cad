# Torsional tendon load cartridges

The cartridge is one monolithic stainless spring body with three separate dark bonded gauge chips. The spring has a lower outer frame annulus, an upper inner motor flange, three long spline-profile scroll flexures and a scalloped inner riser. The scallops provide access to three captive motor nuts. This is CAD geometry for a reaction-torque sensor; stiffness, strain calibration, electrical terminations and strength are not certified.

## Factory and mounting contract

`lib/tension_cartridge.py`: `make_tension_cartridge(prefix)` returns four individually named solids, spring first then three chips. `tension_cartridge_mounts()` returns the three motor bores, three frame bores and three nut clearances. Positive bank geometry uses station-local world axes and Z0.40..3.95; place with `Pos(x,y,0)`. Rotate180° about Y before translating for the negative bank. Do not add the motor's Z4 offset to the cartridge.

- Outside radius8.20; actual tight kernel bounds16.40×16.40×3.55mm.
- Outer land radial6.90..8.20, Z0.40..1.75; Ø1.08 straight through bores on radius7.55 at60/180/300°. Frame clamp fasteners remain separately owned.
- Motor land radial4.60..6.80, Z3.05..3.95; Ø1.08 straight through bores on radius5.70 at0/120/240°.
- Captive-nut reserves are cylinders radius0.85, Z2.25..3.05 on the three motor-bore axes. Riser access scallops have radius1.15.
- Three scroll arms have0.58mm radial profile width and0.65mm axial thickness. Gauge chips are0.24×0.68×0.11mm, with rounded corners and three actual shallow foil-grid trenches. Chip undersides contact the planar arm top atZ1.75.

## Checks completed

- `tension_cartridge_review.step`:8 solids comprising an upright and inverted4-body cartridge.
- `tension_cartridge_bank_review.step`:48 cartridges,192 independently named solids at all24 paired contract stations. Strict `inspect validate --every-placement` passed:192 occurrences,2 prototypes,0 failures. This includes positive volume, closed shells, valid topology and self-intersection tests at every placement.
- `refs --facts --planes --positioning` ran on both STEP files; `frame` verified the bank's first station atX−27,Y−252. Cached spline bounds are conservative (BUG004); direct factory and reimported STEP tight bounds match the intended R8.20 envelope.
- Actual solid intersections at all48 spring placements found no collision with the transformed motor case and no collision with the full central-frame envelope X±40,Y−280..0,Z±0.35. Both minimum axial clearances are0.050mm. The frame test is against the specified envelope; the completed chassis's local features remain subject to the whole-assembly fit check.
- All three reserved captive-nut cylinders are clear of the spring. Each chip's complete underside is supported by its arm (computed area fraction1.000 within numerical precision), with no chip/spring volume overlap.
- Authored solid/material snapshots at2800×1800, tessellation0.001/0.18: macro, top and full48-cartridge bank inspected. Three scroll paths and both three-hole mounting patterns are visible. The bank has four columns and six paired rows.

Reports and reproducible audit code: `tmp/anthropomorphic_hand/tension_cartridge_fit.json`, `tension_cartridge_bank_validate.json`, `tension_cartridge_validate.json`, `check_tension_cartridge.py`, and corresponding refs/frame JSON files.

Viewer launched at `http://127.0.0.1:3249/`, serving this repository's `models/`. Review paths are `assemblies/STEP/anthropomorphic_hand/tension_cartridge_review.step` and `assemblies/STEP/anthropomorphic_hand/tension_cartridge_bank_review.step`.
