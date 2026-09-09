# Tendon routing feasibility — preliminary engineering definition

Status: analytical architecture only. No geometry or motion clearance has been validated by this document. The path, moment-arm and collision gates remain open until applied to actual generated bodies at every required sample.

## Fixed count

The user's enumerated finger joints total 16 and the enumerated thumb joints total 5. The separately approved palm-cupping joint supplies the twenty-second hand DOF. Two wrist DOFs bring the assembly to 24 DOF.

The scheme is **independent antagonistic pairs**, two continuous tendons and two independently driven capstans per DOF: **48 tendons and 48 actuators**. Each actuator includes motor, gearbox, capstan, termination and tension measurement. No spring is credited as replacing a driven direction. A preload spring may be included in a tension measurement cartridge without adding a controlled DOF or reducing the tendon count.

## Sign and length convention

For a joint coordinate q increasing in flexion/abduction/cupping, call the tendon pulling in its positive direction `joint.p` and its antagonist `joint.m`. Let L be free tendon path length from the actuator datum to its distal termination. The generalized torque from tension T is

    tau_j = -T * dL/dq_j.

An ideal independent positive tendon therefore has dL/dq_target = -r and zero derivative at every other hand joint. Its negative antagonist has derivative +r. The positive tendon's signed moment arm is +r and the negative tendon's is -r. Merely drawing a path near a proximal joint center does not prove a zero derivative.

The derivative matrix must be assembled for the complete paths. For the 44 hand tendons, the hand-joint block must have exactly one nonzero entry per row, paired signs, and rank 22. Numerical derivatives are a useful audit of the implemented analytic routing, not a substitute for collision tests.

## Why a normal pulley at a crossed joint is insufficient

An arc wrapped around a proximal joint changes length by approximately r*q. A distal tendon taken over that pulley generates proximal torque T*r even if a second tendon exists elsewhere. Pulling it alone does not actuate only its target. Opposed pairs can cancel such effects under coordinated tension control; that is not the requested tendon-level independence. Active decoupling is explicitly allowed for the wrist, but is not assumed for the fingers or palm cup.

A polyline going exactly through a joint-axis point has zero nominal moment arm but an infinitely sharp bend. Rounding it away from the axis generally reintroduces a moment arm. A hidden Bowden sheath should also not be silently substituted: its attachment reactions, fixed working length and all-pose minimum curvature would have to be modeled.

## Exact finite-radius neutral crossover: coaxial transport

One mathematically exact option is a fixed quarter-circle inlet, a straight segment lying on the joint axis, and a quarter-circle outlet rigidly attached to the downstream link. The outlet rotates around the straight segment's own axis. The two arcs and the axial straight segment have invariant lengths, tangents are continuous, and both arcs can have radius R. Thus dL/dq = 0 exactly, excluding rope torsion and friction from the ideal model.

The fixed inlet and rotating outlet should occupy different axial slabs. Each independent cable requires its own disjoint axial station; multiple finite-thickness cables cannot share the same axis segment. An uncomplicated station requires roughly 2R plus straight-span and structural clearance along the joint axis. At a provisional R = 2.5 mm, six downstream cables at an MCP abduction axis already consume more than 30 mm before bearings. This architecture is analytically clean but risks violating the requested delicate proportions. It cannot be declared spatially feasible without a packed assembly.

## Preferred compact candidate: a three-crossing wrap compensator

A true passive length compensator is a candidate for each tendon crossing a non-target hand joint. It uses three separated coaxial grooved circular guide layers with working radii R, R and 2R. A continuous tendon alternates attachment frames:

    parent lead -> arc 1 -> child crossover -> arc 2
                -> parent crossover -> arc 3 -> child lead

The crossovers are real, finite-radius, rigid guide paths attached to the named frame. They are not virtual transfers between curves. Arc 1 winds counterclockwise from a parent-controlled tangent to a child-controlled tangent. Arc 2 winds clockwise from a child-controlled tangent to a parent-controlled tangent. Arc 3 winds clockwise from a parent-controlled tangent to a child-controlled tangent. With angular offsets chosen to give nominal half-wraps,

    L1(q) = R * (pi + q)
    L2(q) = R * (pi + q)
    L3(q) = 2R * (pi - q)
    Ltotal(q) = 4*pi*R + Lrigid_crossovers
    dLtotal/dq = R + R - 2R = 0.

The physical joint torque from a single ideal tension is consequently zero. This is a derived candidate, not a claim that a commercial mechanism or a validated reference design exists.

A joint interval of -20 to +100 degrees keeps all three wraps strictly between zero and one full turn. Actual wrap offsets must be recomputed for the declared range of each axis. Radial and axial layers must separate the cable envelopes. The guide train needs retaining flanges and rotating tangent fairleads; a decorative three-pulley stack without those frame-specific crossovers does not implement this equation.

The layer-1 to layer-2 reversal is a real U-turn. It must have bend radius at least R and occupy a reserved volume. It must not be replaced by a short diagonal connector. The third layer has twice the groove working radius; reducing it to the first two layers' radius destroys decoupling. All guide solids and fairlead sweeps must stay clear through the full angular interval. This packing problem is still unresolved and is the main local feasibility gate before detailed styling.

## Cascaded routing graph

Proximal-to-distal axes for each of index, middle, ring and little:

    MCP abduction -> MCP flexion -> PIP -> DIP

The two tendons of each joint pass through neutral compensators at every upstream hand axis, then wrap/terminate on opposite sides of their own joint. They do not cross any downstream joint. The visible DIP run therefore follows the finger to the distal phalanx; PIP runs end at the middle phalanx; MCP runs end proximally. A physical carrier and an explicit termination exist at every endpoint.

Thumb order:

    CMC abduction -> CMC flexion -> MCP abduction -> MCP flexion -> IP

The CMC opposition pulley stack includes the eight downstream tendons crossing CMC abduction and the six crossing CMC flexion, in addition to their own antagonists. It must not be presented as a single decorative pulley.

Palm cup carries the ring/little metacarpal branch. Its sixteen downstream tendons need neutral transport through cupping. Index, middle and thumb routing remains on the fixed palm branch. The two palm-cup tendons end at the cupping joint.

With an individual three-arc compensator per crossed tendon, the four fingers require 48 neutral transport packets (12 per finger); the thumb requires 20; the palm cup requires 16. This is **84 neutral packets / 252 circular guide layers**, before terminal joint drums, forearm capstans, wrist guides and fixed palm fan-out guides. This large part count is a real consequence of strict tendon-level independence. Shared axles and multi-groove turned parts may reduce body count, but cannot combine cable lanes, omit crossovers or alter radius ratios.

## Wrist: explicit compensation

Forty-four hand tendons pass through both wrist axes. Assuming abduction is the proximal wrist axis, the two wrist-flexion tendons also pass through wrist abduction. The two wrist-abduction tendons terminate at the proximal wrist joint. Each wrist guide path must be a finite-radius analytic curve determined by wrist angles and its actual guide solids.

For hand tendon i, let W_i(q_w) be its wrist path contribution, and H_i(q_i) its target-joint contribution. Its motor must command the geometric payout

    lambda_i(q) = W_i(q_w) + H_i(q_i) + constant.

The compensation is W_i(q_w) - W_i(0), including coupled two-axis wrist poses. Payout is not just target-joint travel. Capstan angle is the commanded payout change divided by the capstan working radius, with a declared rotation sign.

These paths exert wrist torques -sum_i T_i * grad(W_i). The wrist antagonists must supply the opposite generalized torque in addition to the desired wrist torque. This is an explicit wrist force/length compensation assumption; it does not make the individual hand tendon wrist-neutral. Tension sizing is outside scope, but the compensation matrix and required signs must still be reported. Whether sufficient positive pair tensions exist is an engineering question, not something a visual animation proves.

## Provisional geometric parameters, not verified material specifications

Use tendon nominal diameter 0.35 mm and a provisional minimum centerline bend radius of 2.5 mm. This is a declared design requirement, not a supplier-qualified minimum. Braiding relief must fit inside the clearance envelope; a 0.35 mm envelope cannot contain a 0.35 mm core plus protruding braid. Pulleys require working radii at or above 2.5 mm; compensator layers three use 5 mm. Drum radii must remain immutable once the routing geometry is frozen.

Every full path must be represented by tangent-continuous lines and circular arcs, or another curve with explicitly bounded curvature. A visual B-spline that passes near guide centers is not proof of tangent contact or minimum bend radius. A faceted chain of cylinders is not a swept tendon and has corner-radius violations.

## Required implementation checks

1. For each cable and every sample, verify exact endpoint continuity and tangent continuity, calculate analytic arc/spline minimum curvature radius, and construct the complete swept envelope from spool exit to actual termination. Check the envelope against every non-contact solid. Groove contact is allowed only at its intended tangent surface; interpenetration is not.
2. List target and all crossed upstream joints per tendon, plus actual path length, minimum radius and collision result. Never mark a row clear because only sampled centerline points miss solids: use swept-volume intersections or a certified clearance bound.
3. Form dL/dq from the implemented paths. Confirm the signed target moment arms, zero cross terms at other hand axes, full hand rank, and the explicit wrist terms. Pulling `.p` must correspond to decreasing positive-tendon path length. Record magnitudes, not only plus/minus labels.
4. Sweep each joint at 10-degree increments including exact range endpoints with other joints neutral, plus full fist, precision pinch and flat open. Use transformed exact solids/valid envelopes. Include tendon-to-tendon clearance because intersecting cables cannot both occupy the same space even if the literal requested table emphasizes solids.
5. At animation pose samples 0.00 through 1.00 in steps of 0.02, recompute all routes, payout and capstan angles and rerun the same checks. Rigidly rotating a neutral cable body with its phalanx cannot represent sliding through proximal guides. Length errors cannot be concealed using an animation-scale transform.
6. Explode sampling must evaluate every actual body at increments of 0.05 and use a separately declared allowed contact policy. Bearings, retainers and threaded fasteners may have intentional interfaces at zero; neither a blanket exemption for all mechanical hardware nor deletion of those bodies is acceptable.

## Open blockers before claiming a working hand

- Compact, collision-free packing of the passive hand-joint compensators is unproven, especially the thumb CMC and cupping branch. Build and sweep one complete MCP neutral packet before propagating it.
- The wrist guide geometry and its length/torque compensation are not yet defined by actual guides.
- A live renderer restricted to rigid-body transforms cannot continuously reshape a swept tendon as its wrap and free spans change. A supported deforming-geometry mechanism must exist, or a minimal critical runtime capability must be implemented, before the requested animation can be truthfully delivered. Many static cable chunks that appear/disappear between frames are not equivalent to a continuous physical tendon.
- None of the required full-path, full-range, solid-intersection or animation-sample tables have been run yet. This note is not a pass report.
