# Bounded specialist task: six thumb CMC reaction liners

Build and validate the six fixed-length CMC reaction-liner paths for the downstream thumb joints. This is a numerical geometry task; do not edit the already accepted finger solvers or change joint ranges, pulley radii, phalanx lengths, or inlet/drive-pulley datums. Produce a pure analytic path-data factory under `lib/`, with proof scripts/reports under `validation/anthropomorphic_hand/`. Coordinate any structural-envelope conflict with the parent. A feasible optimizer result is not a collision certificate.

## Coordinates and mechanism

Use a local CMC frame with joint origin at zero, finger direction +Y, flex axis +X, yaw axis +Z. Child transform is Rz(yaw) Rx(flex). In the assembly this frame maps by columns `THUMB_CROSS_AXIS`, `THUMB_DIRECTION`, global Z, translated by `THUMB_CMC`, all in `lib/layout.py`. CMC yaw range −25..45 degrees; flex −15..65. The metacarpal is 36 mm long. The next MCP universal joint is at local Y36.

The scheme is antagonistic, 48 tendons / 48 actuators for 24 total joints. These are ideal zero-clearance, inextensible reaction liners: tendon radius .30, liner ID radius .30, OD radius .45. Their working centerline length must remain exactly fixed under both CMC axes, so the net upstream tendon-plus-liner generalized torque is zero. A bare curved tendon alone does not have that property. Minimum tendon centerline bend radius is 3.5 mm. Candidate optimizers use 3.65 for numerical margin. All data are canonical cubic paths `{kind:'bezier', points:[p0,p1,p2,p3]}`.

## Fixed datums

CMC flex drive drums: planes X±.9, pitch radius7, maximum outer radius7.5, width1.5. Continuous flex drive shaft envelope R1 along X. CMC yaw drums: positive center Z−11, negative Z−13.5, same pitch radius7 and width1.5. Carrier and metacarpal are actual bodies in `lib/universal_carrier.py` and `lib/thumb_metacarpal.py`. CMC carrier uses width19 / yaw_plane9.5, with central layout hub datums.

Own CMC-flexion tendons cross only yaw via `lib/thumb_yaw_transport.py::thumb_yaw_reaction_span(yaw, sign)`: fixed length24.5, parent anchor `(sign*.9,−23,sign*7)`, rotating-child anchor `(sign*.9,−3,sign*7)`; then a bare 3 mm tangent lead reaches the flex groove. Its free bank angle handles yaw45. Independent 102-sample local proof: min radius3.6463838, length error<9.4e−12. These two existing routes must be included as obstacles when solving the six distal liners. Hardware/body collision validation of those two routes remains pending.

The six distal liners begin at parent-fixed `(lane,−12.25,0)`:

| Target tendon | lane X | Proposed child-fixed outlet | Candidate fixed length |
|---|---:|---|---:|
| thumb_ip_negative | −5.4 | (−5.4,12.25,0) | 33 |
| thumb_ip_positive | +5.4 | (+5.4,12.25,0) | 33 |
| thumb_mcp_flexion_negative | −4.2 | (−.9,13,−5.5) | 35.5 |
| thumb_mcp_flexion_positive | +4.2 | (+.9,13,+5.5) | 35.5 |
| thumb_mcp_abduction_negative | −3 | (−3,12.25,0) | 33 |
| thumb_mcp_abduction_positive | +3 | (+3,12.25,0) | 33 |

Every inlet tangent is parent +Y; every outlet tangent is child +Y. The custom MCP-flexion outlets are necessary: the next MCP yaw-reaction liner starts at Y36−23=13 with X±.9,Z±5.5. A generic Z0 outlet at Y12.25 leaves only .75 mm to change transverse position, which cannot satisfy R3.5. These outlet points feed that next liner directly, with a fixed metacarpal anchor between them. The other four outlets can use fixed curved guides along the metacarpal to their next target/transport stage. Candidate lengths are not yet accepted; increase if geometry demands it, but do not alter fixed assembly datums or reduce the minimum radius.

The 10 upstream thumb splice positions supplied to the root wrist/palm planner are fixed by `lib/hand_inlets.py`: CMC yaw local Y−3, CMC flexion Y−24, and six distal tendons Y−13.25. The six distal inlets above receive one-millimetre bare straight runs from those Y−13.25 datums. These advanced splice points clear the wrist drive disks; all reaction-liner and pulley endpoints remain unchanged.

## Starting implementation and known failures

`validation/anthropomorphic_hand/thumb_cmc_candidate.py` is the latest runnable numerical probe (no CAD kernel). It uses two C1 cubics, eight parameters a,b,d,my,mz,theta,mx,psi; moving endpoints remain exact. It constrains fixed length, sampled curvature, both yaw-cylinder envelopes, both flex-cylinder envelopes, the continuous shaft, actual-size conservative cheek boxes, the own-yaw liners, and previously solved distal liners. It solves channels in order −5.4,+5.4,−4.2,+4.2,−3,+3 and requires sampled centerline separation≥1.04. Final independent proofs must use conservative interval bounds or exact geometry, not those optimizer samples.

Earlier 31/32.5 mm candidates solved all six neutral channels and all six at flex65/yaw0. With rotation-aware half-quaternion seeds, the outer pair also solved flex65/yaw45. The remaining extremes—especially flex0/yaw45 and the negative custom-outlet route—failed. Debugging at flex0/yaw45 produced near-feasible branches with R≈3.2 rather than3.65, suggesting additional working length or more shape freedom may be needed. Latest 33/35.5 mm probe is running and has not been accepted.

Do not use an infinite lateral corridor for the metacarpal: at large yaw the fixed parent inlet sits outside the child cheek plane but outside the solid in Y/Z, so such a constraint falsely excludes valid configurations. The latest probe uses finite conservative side-plate boxes in child coordinates (X ranges±[8.05,9.5], Y−3.55..39.55, Z±4.85). Actual curved windows provide more room, but any use of that space must be independently tested against the real body.

Useful existing validation helpers:
- `lib/path_analysis.py`: exact polynomial cubic minimum radius / axis distance; certified-spacing samples.
- `lib/bowden_universal.py`: fast vectorized curve length/curvature and quaternion helpers.
- `lib/bowden_mcp.py`: accepted four-channel finger implementation, including lazy continuation only after direct seeds fail and adaptive length refinement. Read as an example; do not edit it.
- `validation/anthropomorphic_hand/check_middle_hardware_paths.py`: exact wire-to-solid radius-envelope proof with cached bounds and revolved-pulley symmetry. A tube is contained in the radius-neighborhood of its centerline, so a larger exact distance proves continuous clearance between samples.

Expected handoff: a named six-route packet factory returning paths, fixed working lengths, input/output datums and neutralized CMC axes; local radius/length/mutual-clearance evidence throughout single-axis ranges and compound corners; actual carrier/metacarpal/pulley/shaft clearance evidence; candid unresolved cases. Do not declare a partial local solve to be the full thumb gate.
