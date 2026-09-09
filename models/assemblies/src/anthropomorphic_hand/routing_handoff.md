# Routing builder handoff

All dimensions are millimetres. Architecture remains 24 DOF, 48 antagonistic
tendons, and 48 actuators. Tendon radius is 0.30; reaction-liner outer radius is
0.45; minimum permitted bend radius is 3.5. Upstream independence relies on
the net tendon plus compressive reaction of an ideal snug, inextensible liner.
The raw tendon force alone is not torque-neutral. Wrist spans use explicit
length compensation and are not claimed to be inextensible.

## Accepted local gates

Reports are in `models/assemblies/validation/anthropomorphic_hand/`.

- `middle_combined_report.json`, `index_combined_report.json`,
  `ring_combined_report.json`, `little_combined_report.json`: respective
  41/42/41/44 local poses pass the full routed-finger body and mutual gates.
  Separate index/middle/ring adducted-fist reports pass the neutral-fan poses.
- `cup_transport_report.json`: all eight cup reaction liners pass at cup
  0/10/20/25 degrees against the imported main palm and final little
  metacarpal. Minimum radius 3.6457043274; maximum length error 7.11e-15.
  Those four accepted packets are imported from `lib/cup_atlas.py::ATLAS`;
  the JSON mirror is not a production input. Neutral geometry is unchanged.
- `hand_route_pairs_neutral.json`: all 48 hand-side paths pass continuity,
  bend radius, and mutual clearance; 232 nearby group-pair checks, minimum
  certified surface gap 0.05494187.
- `thumb_full_report.json` preserves the original neutral pass and historical
  yaw45 failure. The current repaired yaw45 packet passes independently in
  `thumb_full_yaw45_report.json` (143 exact body distances, minimum mutual
  gap 0.01993102). Do not describe the historical combined report as passing.
- `thumb_downstream_report.json`: original downstream six-route mechanism
  passes 26 poses.
- `thumb_downstream_short_candidate_report.json`: shortened downstream
  mechanism also passes all 26 poses, including MCP yaw +/-15, flexion70,
  IP85 and compounds. `thumb_mcp_yaw_short_candidate.json` additionally
  checks 62 one-degree cases, minimum radius 3.64723861 and maximum length
  error 4.974e-13.

## Thumb candidate switch

The CMC specialist owns the six-liner CMC atlas and full-range continuation.
The accepted public neutral atlas is frozen until their deliberate switch.
The new CMC MCP-flexion outlets at child Y16 replace Y13. Their downstream
reaction inlets move from local Y-23 to Y-20. The candidate factory in
`lib/thumb_mcp_yaw_transport.py` has fixed working length20.5, retains
X+/-0.9, Z+/-5.5 and outletY-3, and preserves the full MCP yaw range.

`thumb_downstream_routes(pose, short_mcp_yaw=True)` selects this candidate.
`thumb_routes()` selects it automatically only when the authoritative
`cmc_inlet_contract()` reports MCP-flexion outletY16. Therefore the specialist
can switch contract and atlas together; no duplicated downstream datum edit
is required. The new full CMC-plus-downstream packet still needs its combined
gate after that coordinated switch.

## Complete paths and remaining neutral failures

`lib/hand_routing.py` exposes:

- `hand_side_routes(pose=None, cup=None, thumb_cmc=None)`: all48 world-space
  hand-side paths, including little-finger cup reactions and six wrist/cup
  terminal routes.
- `full_tendon_routes(wrist_packet, pose=None, capstan_rotations=None)`:
  all48 continuous spool-to-termination paths. Wrist packet rows are keyed
  by tendon name. Capstan rotations are radians. This function checks splice
  positions; it does not silently solve payout or wrist compensation.

`full_route_pairs_neutral.json` has continuous complete paths but fails five
cross-interface pairs in the earlier root wrist packet: index MCP-yaw+
against thumb CMC-flex+ and IP+ guides; ring PIP+/DIP+ against cup+ approach;
ring PIP- against cup- approach. Exact groups and closest points are in that
report. Root is replanning wrist guides with all foreign hand paths as
obstacles. Rerun after replacing the wrist packet:

```bash
PYTHONPATH=models/assemblies/src/anthropomorphic_hand ./.venv/bin/python -u models/assemblies/validation/anthropomorphic_hand/check_hand_route_pairs.py --full
```

## Full actual-body audit ready, not yet run

`check_full_route_bodies.py` constructs the current authoritative integration
registry, including real shafts, bushings, rings, wrist frames, and actuator
bodies, and checks exact continuous path-wire distances using each group's
0.30 or0.45 physical radius. It imports the stable palm bodies from
`palm_frame_review.step` and `palm_little_review.step` to avoid expensive
rebuilding. It records those files' and the wrist packet's hashes.

```bash
PYTHONPATH=models/assemblies/src/anthropomorphic_hand ./.venv/bin/python -u models/assemblies/validation/anthropomorphic_hand/check_full_route_bodies.py
```

Optional arguments: `--pose '{}'`, `--wrist-file PATH`, `--out PATH`.
Default output is `full_route_bodies_neutral.json`. The script compiles but
has not been run: root requested the slot be freed before starting the long
full-hand hardware audit. Later-added pads, covers, sensors and guides must
be checked after entering the integration registry.

## Animation and acceptance limits

Every inextensible guide packet retains its target working length and scalar
length-correction recipe. Interpolating raw control points is insufficient:
regenerate endpoints/tangents from exact FK, then correct length. Root owns
the JS evaluation and all51 pose samples. The cup's four accepted static
packets do not substitute for the animation gate or continuous branch checks.
Root also owns final full-hand moments, full-hand collision sweeps, the blind
visual gauntlets, complete hardware generation/inspection, and explode checks.
No whole-hand or animation acceptance is claimed by this handoff.

The tendon braid is an optical finish within radius0.30, not displaced
geometry. No new repository bug was encountered during this final handoff;
BUGS.md remains root-owned.
