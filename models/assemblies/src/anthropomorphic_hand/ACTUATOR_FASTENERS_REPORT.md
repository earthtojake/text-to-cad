# Actuator and reaction-frame fasteners

`lib/actuator_fasteners.py` exposes `actuator_fasteners()`, returning individually
named `(shape, 'forearm', 'forearm', kind)` occurrences in assembled coordinates.
It builds14 polished-steel prototypes once and places824 separate bodies.

Each of48 unchanged motor stations receives16 pieces: three M1 long socket tie
screws, three captive hex nuts, three0.05mm motor-seat shims, three M0.8 cartridge
clamp screws, three flanged frame inserts, and one M1 capstan retainer screw.
The inserts use the six staggered frame bores: each face takes alternate holes.
Their0.05mm flanges bridge the cartridge/frame gap without touching the opposite
cartridge. Captive motor nuts fill the specified Z2.25..3.05 scallop reserve;
shims fill Z3.95..4.00. Tie-screw head seats are Z29.50 and top faces Z30.05.
The capstan retainer seats at Z37.25; its tip is Z35.75,0.10mm above the blind
spindle-bore bottom. Negative-bank occurrences are proper180° Y rotations.

Four wrist mounts use short M3 socket screws, rear washers and hollow captive
thread inserts. The0.10mm insert flange bridges Y−31.60..−31.50; the thin-wall
insert occupies the existing Ø3.3 fork bore and ends at Y−28.60. Screw tips stop
at Y−28.70. This avoids the actual curved fork ribs, which interfere with a
conventional forward nut and protruding bolt. No fork or pulley geometry was
changed. These are nominal thread envelopes: helical threads, thread strength,
and manufacturing fits require engineering definition.

The eight rear external mounts have seated M3 screws, front/rear washers and
hex nuts. Four short M1.6 screws, rear washers and captive hex nuts connect the removable
rear rim to the existing chassis shoes. The nuts enter through small outboard
slots into Y−275.35..−273.85 pockets. A0.65mm rear bearing ledge carries the
clamp load; each nut seats at Y−275.35 and ends at Y−273.95. Total non-actuator
hardware:56 bodies.

One necessary motor correction extends the three existing Ø1.08 mounting bores
through the full case on their unchanged radius5.7 axes. The earlier forward-only
bores left the rear web and a narrow part of the rotor-cavity wall in the tie
screws' paths. This is a model correction, not a repository bug.

Validation artifacts live in `models/assemblies/validation/anthropomorphic_hand`:
`actuator_fasteners_validate.json`, `motor_fastener_revision_validate.json`,
`actuator_fasteners_final_fit.json`, `check_rear_captive_nuts.json`, and
`check_actuator_fastener_drives.json`. The final combined report distinguishes
the full baseline audit from the corrected rear-nut proof. The baseline
`check_actuator_fasteners.json` intentionally records the eight old rear-hardware
collisions which motivated that correction; none remain in the final result.
The exact scripts record source hashes, every station's inverse-placement
congruence, own-hardware Boolean intersections, complete drive checks on both
rigid bank orientations, and structural common-volume checks. No routes,
phalanx lengths, pulley radii or actuator station positions were changed.

`actuator_fasteners_macro.png` is the inspected2800×1800 authored solid studio
render of one actual stack. Its macro STEP and render-job JSON are beside the
other validation files; the STEP export is in the assembly STEP directory.

Final gate:824 occurrences,14 prototypes, strict every-placement validation,
zero failures. Updated motor6/3 and frame2/2 also pass. The final combined fit
report has `ok: true` and an empty remaining-collisions list. All four rear
nuts have zero clearance to their bearing ledges, positive contact area proven
by a0.001mm approach, and24 collision-free side-entry samples in total.
The two complete-drive bank representatives have zero exact intersections;
all48 rigid-congruence tests pass for all768 actuator-hardware occurrences.
