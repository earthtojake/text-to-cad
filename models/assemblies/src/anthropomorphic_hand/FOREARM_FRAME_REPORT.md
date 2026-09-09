# Forearm reaction frame handoff

`lib/forearm_frame.py` exposes `make_forearm_frame_bodies()` and
`forearm_frame_mounts()`. Both bodies are native solids in their assembled
forearm coordinates: the monolithic open reaction chassis and removable rear
mounting rim. `forearm_frame_review.py` exports the individual review assembly.

The chassis has24 paired annular cartridge lands at the unchanged stations,
144 fully reamed Ø1.08 fastening bores, side rails atX±38 and deep rounded ribs
between actuator rows. The annular faces remainZ±0.35. Four Ø3.3 wrist holes
are atX±10,Y−33.1,Z±9, axisY; their front facesY−31.6 leave0.10mm to the fixed
wrist fork rear facesY−31.5. The narrow branches enter the outboard walls of
the wrist eyes, clear of the bore axis.

The separate rear rim occupiesY−280..−276, X±42,Z±47. Its8 closed Ø3.3 external
mounting bores are atX±40/Z±27 andX±23/Z±45, all axesY. Four Ø1.8 chassis-fixing
bores atX±39,Z±3.3 align withØ1.7 pilot bores in the rear chassis shoes.
The four fixture screws and eight external attachment screws remain integration
hardware, as do the four wrist screws and the cartridge fasteners.

Guide-bank feet fasten through the side beams onX±38, Y−223/−182/−141/−100/−59/−36,
axisZ, Ø1.08. Positive and negative bank screws use opposite ends of those bores.
`lib/forearm_guide_mounts.py` owns those screws and the96 forearm liner mouths.

Completed frame checks: `cadgen step inspect validate --every-placement`
reports2 occurrences,2 prototypes,0 failures. This includes strict topology,
closed shells, positive volume and self-intersection checks. The final verdict
is in `tmp/anthropomorphic_hand/forearm_frame_validate.json`. The baseline
`refs --facts --planes --positioning` packet is
`tmp/anthropomorphic_hand/forearm_frame_refs.json` (rerun after any later edit).
The exact48 cartridge and case assertions have passed. Every seat has the
specified0.05mm axial gap and positive contact area after a0.000001mm additional
approach; all144 sensor bores and4 wrist bores are clear. The reproducible
`check_forearm_frame.py` writes `forearm_frame_sensor_fit.json` and
`forearm_frame_fit.json` under the same temporary review directory.
The separate final `forearm_frame_route_clearance.json` reports all48 full
neutral routes clear. Conservative hulls separate every group except the
negative wrist-flexion guide; exact path-wire-to-body distance verifies its
surface clearance at14.2144872mm. The smallest certified route separation
lower bound in the complete frame packet is4.7498081mm.

Default-renderer1800×1400 snapshots succeed; the authored studio render job
reproduced the existingBUG006 driver-disconnection at finer settings. The
snapshot path is `tmp/anthropomorphic_hand/forearm_frame_final.png`.
The current CAD Viewer is `http://127.0.0.1:3250/`, serving `models/`.
Select `assemblies/STEP/anthropomorphic_hand/forearm_frame_review.step`.

No strength, torsional calibration or manufacturing certification is claimed.
The whole-hand moving-hardware and route audit remains the integration gate.

## Captive rear nuts added during hardware integration

The four existing rear pilot axes now have side-entry hex-nut pockets of
circumradius1.50 at Y−275.35..−273.85, with outboard insertion slots. Each
pocket preserves a0.65mm rear bearing ledge; a plain rear-open counterbore
would not resist the bolt's clamping load. The nominal frame envelope, mounting
axes, wrist eyes, cartridge lands and guide-bank bores are unchanged. Both
`forearm_frame_review.step` and `forearm_mount_system_review.step` were rebuilt.
Final hardware and nut-seat certificates are listed in
`ACTUATOR_FASTENERS_REPORT.md`.
