# Guide reaction mounts

All full paths are in `lib/neutral_routes.py` as48 named route dictionaries.
Their groups carry path, guide kind, frame, and neutralized joints. The hollow
liners are real swept bodies, radius0.45 outside and0.30 inside. Tendons are
radius0.30; their braid is a shader finish without displacement.

An inextensible reaction liner must be anchored to its parent and child
frames. A floating tube cannot cancel the upstream joint moment. Build real
end collars and structural attachments without moving accepted guide paths.
Adjacent liner ends at the same point/tangent may share one clamp. The clamp
bore must clear the0.45 guide envelope, and the structural branch must clear
all other tendon/guide envelopes. Clip mouths may remain open to expose braid.
Each clamp/strut/fastener is a named real body and has an articulated frame.

Use short collars, approximately0.8mm long, bore radius0.46 or larger, outer
radius around0.70. Exact size follows clearance; do not enlarge a collar into
a moving phalanx or drum. A support can be an elegant curved ribbon ending in
a machined eye, with a clear attachment to the existing frame. Tiny separate
contact faces and a clamp fastener are preferable to an unblended union.

Useful architecture: transverse comb supports at the MCP reaction outlets
(localY12.25,Z0,X±3/±4.2), attached to proximal side rails; analogous PIP outlet
supports on middle phalanges; shaped support fingers for the fixed guide ends
near each driven joint. Palm-side inlet combs follow the actual neutral fan.
Wrist inlet combs live at Y−12 with all48 actual lane/height coordinates. Root
wrist guide shapes are explicitly compensated and compliant; their forearm
and hand-side mounting datums stay fixed in their named frames.

The forearm capstan exit guide is compliant and follows the moving helix
exit. Its downstream mouth at (lane, actuatorY+30, height) attaches to the
forearm. Its upstream mouth is a cantilevered guide end; do not rigidly attach
it to the rotating capstan.

Every new mount must be checked against the existing full neutral route
clouds and actual skeleton. Reaction end clamps need the full local joint
sweeps too; preserve all accepted joint ranges, phalanx lengths and pulley
radii. The root will repeat the complete body/animation checks after adding
these parts. Final acceptance is not implied by this contract.
