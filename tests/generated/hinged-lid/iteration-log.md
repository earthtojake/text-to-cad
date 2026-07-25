# Iteration Log: hinged-lid

## Iteration 1 (fail — 3 failures)

- Generator v1: `LID_T = 0.5` (intentionally thin lid to exercise the
  fix-retry loop). URDF v1: hinge axis `+X`.
- Results:
  - PASS `test_structural_sanity[base_mesh]`, `[lid_mesh]` — both meshes
    watertight, winding-consistent, single body, positive volume.
  - FAIL `test_lid_plate_thickness` — measured 0.5 mm < 1.0 mm floor.
    Expected: deliberate thin-wall trigger. Fix belongs in the CAD source.
  - FAIL `test_base_dimensions` — bounding-box assertion ignored the hinge
    lugs, which legitimately protrude (+4 mm in Y and Z). Test bug, not a
    part defect; the design intent is the 60 x 40 mm box footprint.
    Correction: measure the footprint from a mid-height cross-section
    instead of the global bounding box.
  - FAIL `test_hinge_settles_closed_within_limits` — lid released at
    1.0 rad settled at ~1.3 rad hanging down behind the box. Genuine sim
    finding: with axis `+X`, positive rotation swings the lid *downward
    behind* the base; the design intent is the lid opening *upward*.
    Fix belongs in the URDF source: hinge axis `-X`.

## Iteration 2 (fail — 2 failures)

- Changes: `LID_T` 0.5 → 2.0 in `hinged_lid.py` (design-note nominal);
  URDF hinge axis `+X` → `-X`; `test_base_dimensions` switched to a
  cross-section footprint measurement (stated reason above).
- Results:
  - PASS `test_lid_plate_thickness` — 2.0 mm plate, floor satisfied.
  - PASS hinge axis direction — the lid now swings the intended way.
  - FAIL `test_base_dimensions` — `Path2D` has no `bounding_box` in
    trimesh 4.x; API misuse in the test, fixed to `planar.extents`.
  - FAIL `test_hinge_settles_closed_within_limits` — lid crept from 1.0 to
    ~0.98 rad in 5 s. Two compounding causes found: (a) STL convex-hull
    collision geometry bridged the open top and the lid knuckle hull
    overlapped the base lug hull at the hinge, jamming rotation — replaced
    mesh collisions with primitive boxes (plate and box), which is the
    geometry the lid actually rests on; (b) joint damping 0.3 N·m·s/rad was
    ~150x oversized against the lid's ~0.002 N·m gravity torque — reduced
    to 0.001.

## Iteration 3 (pass — 6/6)

- Changes: damping 0.3 → 0.001 in `hinged_lid.urdf`.
- Results: all 6 tests pass in 0.58 s.
  - Geometry: watertight/single-body both meshes, footprint 60 x 40 mm,
    lid plate 2.0 mm.
  - Sim: hinge released at 1.0 rad settles closed (|angle| <= 0.05 rad)
    within limits (0..1.92 rad, never < -0.02), resting in contact with
    the base rim.
- Iteration budget: 3 of 3 attempts used; no further retries needed.

## Review outcome

- Design-note requirements all covered by at least one assertion; no
  requirement left untested.
- Threshold bases stated: 1.0 mm plate floor (FDM handling wall,
  reference range), +/- 0.2 mm dimensional tolerance (typical FDM
  accuracy), settle/limit bands from the URDF joint limits.
- Superficial-test check: structural sanity tests mirror trimesh defaults
  but gate real failure modes (non-watertight exports, duplicate shells);
  thickness and settle tests assert design intent, not measured values.
- Known simplification: collision geometry is primitive boxes, not the
  full STL; hinge lug/knuckle contact is not simulated. Acceptable for
  the settle/limit scenario; flagged here per the sim-test reference.
- Engine note: MuJoCo used per the environment note in design-note.md.
