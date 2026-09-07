# Distal thumb CMC transport handoff

Status: published and passed the stated static thumb scope on 2026-09-06 at 07:19 UTC. Production uses the Y16 contract. The original certified 65-pose atlas is retained unchanged, with a separately checked exact final-pinch packet appended as entry66; see `thumb_cmc_mounts_handoff.md`.

The six tendons retain their names and constant working lengths: MCP flexion pair 40 mm each; IP and MCP abduction pairs 36 mm each. They use ideal snug inextensible reaction liners, so their net CMC flexion and abduction moment arms are zero. The ten complete thumb routes retain five antagonistic actuator pairs.

All six CMC parent anchors remain `(lane, -12.25, 0)`, where lanes are -4.2/+4.2 for MCP flexion, -5.4/+5.4 for IP, and -3/+3 for MCP abduction. The common inlet tangent is `(sin(35deg), cos(35deg), 0)`; each upstream splice is exactly one millimetre before that anchor along the tangent. Read these datums through `cmc_inlet_contract()` rather than duplicating constants.

The authorized revision advances only the two MCP-flexion child outlets to `(sign*.9, 16, sign*5.5)`. The other four child outlets remain `(lane, 12.25, 0)`. All child tangents are +Y. Downstream automatically uses the independently tested 20.5-mm MCP-yaw reaction liner with parent Y=-20 when this contract is published.

MCP-flexion and IP CMC liners use three C1 cubic spans (14 parameters); MCP-abduction CMC liners use four (20 parameters). Parameters are `[first_handle_length, last_handle_length, midpoint1_xyz, tangent_handle1_xyz, ...]`. Endpoints and their tangent directions are regenerated from exact CMC forward kinematics. At each displayed pose, correct parameter 0 using the nearest scalar root of adaptive path length minus the fixed working length. `curves_from_parameters()` and `correct_length()` implement this. Neither interpolating raw control points nor correcting length alone is a collision proof.

The important packing order is inner MCP-abduction pair first, then MCP-flexion pair, then outer IP pair. Freezing MCP-flexion or outer IP paths before the negative inner liner can trap the high-flex branch, although a feasible common bank exists. The public packet returns each route by tendon name, not by assumed index.

The frozen atlas is exported both as review JSON and as `lib/thumb_cmc_atlas.py::ATLAS`, which is imported by the transport module so CAD dependency tracking sees all parameter changes. Every row contains the exact pose, working length, parameter vector, and generated cubic controls.

Required integration checks still belong to the whole assembly: wrist and forearm routing, the full assembled hardware set including mounts, all required articulated hand poses, 0.02 animation samples, and the staged explode gate. The local thumb gate does not substitute for those.

## Evidence

`validation/anthropomorphic_hand/thumb_cmc_final_certificate.json` combines25 complete-thumb poses, including all23 required axes/corners/pinch poses, with4,427 actual body-distance checks and no conflicts. The390 CMC tendon instances across65 atlas poses have maximum fixed-length error1.983e-12mm, minimum radius3.546307mm, and minimum certified mutual surface gap0.029841mm. Complete-thumb minimum certified mutual gap is0.019852mm.

`thumb_cmc_candidate_review_validate.json` records12/12 strict neutral solid passes. `thumb_cmc_axis_interpolation_numeric.json` records21 one-degree scalar-corrected samples across45..65 at yaw0, with minimum radius3.513965mm; that interpolation probe does not claim actual-CAD or full animated-hand coverage.
