# Routing architecture and current evidence

The assembly manifest contains 24 independent joints and 48 antagonistic tendons, each with its own actuator. The hand has four 4-DOF fingers, a 5-DOF thumb, one palm-cupping joint, and a 2-DOF wrist. Palm cupping carries the little metacarpal. All tendon paths are explicit line, circular-arc, or cubic-Bezier data and produce real circular swept solids.

The selected transport mechanism is an ideal snug, inextensible Bowden reaction liner across every finger joint upstream of the tendon’s intended drive joint. Most longitudinal runs remain bare. The inner tendon radius and liner inner radius are both 0.30 mm; the liner outer radius is 0.45 mm. The liner is transparent in presentation geometry. This zero-clearance idealization is essential: a real finite-clearance cable can adopt a different length from its liner’s centerline. Manufacturing tolerance, liner stiffness, friction, compression, and fatigue are not validated here.

A liner is fixed to the two structures it crosses. Its constrained centerline length is independent of the intervening joint angles. It transmits a compressive reaction that balances the cable tension at those anchors. Thus the net upstream generalized force of tendon plus reaction liner is zero. The cable alone need not have zero raw moment about an upstream axis. The moment-arm report must identify this reaction explicitly; it must not claim that a curved bare cable is intrinsically decoupled.

For each target joint, a bare tangent lead reaches a turned drive pulley and follows a circular arc to a termination rigidly attached to the driven child. For sign s=±1, radius R, angle q in radians, the wrap angle is −s·150°+q. Over the declared motion range, its length derivative is −sR, giving generalized torque +sTR for cable tension T. The opposing cable gives −sTR. The driven pulley/shaft interface transmits torque into the child phalanx.

## Current middle-finger implementation

- MCP flexion tendons cross only the yaw axis through two 24.5 mm reaction liners. Their anchors are Y−23 and Y−3 in their respective rigid frames; each is followed by a 3 mm bare tangent lead to its drive groove.
- PIP and DIP tendons cross the coincident MCP yaw and flex axes together through four 30 mm reaction liners, with anchors at Y±12.25 and lateral lanes X±3.0 (PIP) and X±4.2 (DIP).
- DIP tendons cross PIP through two 30 mm reaction liners at X±4.2. The parent-authored PIP solver clears a continuous radius-1 driven shaft.
- MCP yaw drive pulley planes are Z−9.5 (positive) and Z−12 (negative). Both have pitch radius 5.5. MCP flexion pulley planes are X±0.9 with pitch radius 5.5. PIP and DIP pitch radii are 4.5 and 3.5.
- Fixed curved connections have corresponding swept guide bodies. Each stops 3 mm before the intended drive-groove tangent point, preventing its outer wall from entering the pulley flange.
- Every path group identifies its attachment frame, geometry, guide role, and upstream joints neutralized. Every complete route records its termination, target joint, and antagonist sign.

`lib/finger_routing.py`, `lib/bowden_mcp.py`, `lib/yaw_transport.py`, and `lib/pip_transport.py` are the current executable sources. The MCP solver constrains the full radius-1 shaft, conservative drive-pulley envelopes, neighboring MCP liners, and both MCP-flexion yaw-only routes. Its geometry solver is not itself a collision certificate: the independent assembly gates can reject the result.

## Evidence completed so far

1. All eight complete middle-finger routes pass position/tangent continuity and minimum-radius checks at neutral.
2. The 41-pose path gate passed all declared single-axis 10-degree samples (including final endpoints), flat open, full fist, precision pinch, and a combined 90-degree MCP flexion / 15-degree yaw pose. It conservatively compares every entire path as a radius-0.45 tube, with a sampling-derived clearance lower bound. Minimum full-path bend radius is 3.5 mm, set by the DIP drive circle.
3. Independent adaptive quadrature gives unintended upstream length derivatives below 6.6e-9 mm/rad. Intended derivatives have magnitudes 5.5, 4.5, and 3.5 mm/rad and the correct antagonist signs. See `validation/anthropomorphic_hand/middle_moment_arms_report.json`.
4. The neutral middle-routing prototype builds successfully as 31 bodies. With the previous carrier added, all 32 solids were valid and every tendon/liner/phalange/pulley Boolean intersection was zero. The two remaining collisions in that historical report involved the previous symmetric carrier, which has since been replaced by the coordinated dorsal-stack carrier. Current-carrier checks are ongoing.
5. A new exact OCCT wire-to-solid gate checks each swept path against actual phalanges, carrier, drive pulleys, and conservative full-shaft bodies. A minimum centerline distance greater than the tube radius proves its entire swept body clears that solid, including points between path samples.

These checks do not constitute acceptance of the entire hand. The current carrier audit, complete moving solid checks, thumb/palm/wrist integration, dense animation sampling, full-hand aesthetic gauntlet, and exploded-motion gates remain necessary. An optimizer can switch among feasible branches; smoothness of the eventual animation must be verified separately at and between its declared samples.

## Rejected concepts

The exact axis-coaxial crossover is mathematically decoupled, but its R3.5 quarter-circle channels require approximately 5.8 mm station pitch to avoid mutual collision. Six channels occupy roughly 38 mm of joint-axis width, which violates the intended delicate hand proportions. The compact 2.2 mm pitch was explicitly found to collide and was rejected.

The first symmetric Z±8 yaw-pulley arrangement blocked the palmar region needed by distal transport during MCP flexion. Long 34–36.5 mm guide detours were tested and rejected after mutual-route failures. The coordinated dorsal yaw stack removes that obstruction without changing pulley radii, phalanx lengths, tendon count, or joint ranges.

Historical analytical notes and failed solver geometry remain under `validation/anthropomorphic_hand/`; they are not current acceptance evidence.
