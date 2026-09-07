# Anthropomorphic right hand

Original, unbranded research-hardware sculpture with mechanically explicit tendon actuation. Beauty is primary, within continuous finite-radius tendon routing and collision constraints.

## Fixed architecture

- Millimeters. Forearm runs along Y from -280 to 0. Wrist near Y=0, palm to Y=105, middle fingertip near Y=195. Palm side is +Z; thumb is on the hand's radial side, -X in a palm-side view with fingers upward.
- Four fingers each have MCP abduction, MCP flexion, PIP flexion, DIP flexion: 16 DOF.
- Thumb has CMC abduction/flexion, MCP abduction/flexion, IP flexion: 5 DOF.
- User approved transverse palm cupping as DOF 22. Wrist flexion/abduction brings total to 24.
- Antagonistic pairs throughout: **48 tendons, 48 actuators**, one motor/gearbox/capstan per tendon. No spring-only return axis. Each actuator includes a tension take-up/sensing element, termination and mounting hardware.
- Hand approximately 200 mm, palm 105 mm, middle finger 90 mm, actuator pack 280 mm.
- Four distinct finishes: blasted aluminum structure; dark actuator chassis; polished steel hardware; off-white soft pads. Braided high-contrast tendons remain visually dominant.

## Gate order

1. Routing architecture, finite-radius paths, all-body neutral clearance.
2. Specialist builder per independently judged part/design, fresh render-only blind A/B critic per part, all judged in whole-hand context.
3. Strict solid validation, complete tendon and moment-arm tables, 10-degree single-axis sweeps plus fist/pinch/open collision tables.
4. Whole-hand gauntlet: palm, dorsal, three-quarter with forearm, joint macro. Presentation theme, solid display, JSON jobs, maximum macro size.
5. Only after whole-hand passes: author periodic five-stage pose choreography and staged explode. Validate pose every .02 and explode every .05. No GIF verification.
6. Checked live CAD Viewer link with both parameters and honest evidence ledger.

## Files

Source: this directory; shared factories/constants in `lib/`. STEP outputs: `models/assemblies/STEP/anthropomorphic_hand/`. Render media and transient evidence: repository `tmp/anthropomorphic_hand/`. Durable validation/design reports stay beside source. Root repository issues: `BUGS.md`.

## Current prerequisite

The continuous swept-body deformation capability is implemented and exercised on a real STEP fixture. The hand geometry and its full routing/collision gates remain in progress. The capability fixture is not the final hand choreography.
