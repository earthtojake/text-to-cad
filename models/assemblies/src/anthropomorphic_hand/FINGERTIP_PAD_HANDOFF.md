# Fingertip pad interface

`lib/fingertip_pad.py` provides `make_fingertip_pad(name, length, width)` in
the distal joint's native frame and `fingertip_pad_bodies()` in assembled,
already-fanned frames. The latter returns thirty `(shape, frame, system, kind)`
tuples: six bodies per finger. Add them after the assembly's generic fan pass.

Each set contains a matte ivory silicone pad, a dark conformal carrier, two
polished M0.8 hex socket screws, and two flanged captive inserts. The carrier
is machined to the actual distal frame and has a small silicone overhang at
the bond edge. Its bore stations are X=±(width/2−0.825), Y=0.71×length.

Index and thumb contact ellipsoids retain the solved native centers
(0, 0.71×length, 5.4) and radii (6.25, 6.5, 2) / (6.75, 7, 2).
The pad is trimmed only below Z=4.15. Solved native contact points lie at
Z=5.645762 and 5.618177, more than 1.46 mm above that trim.
Other radii are middle (6.25, 6.5, 2), ring (6, 6.5, 2), and little
(5.2, 5.5, 2), preserving the same family and anatomical proportions.

The original phalanx geometry is unchanged. The bridge seats on Z=3.325
bosses. Inserts have nominal Ø1.12 outer contact in the original bores and a
flange between Z=3.325 and 3.50. Screw heads seat at Z=3.60 and top out at
Z=4.05. Screw shanks/insert mating cylinders are nominal Ø0.8, from Z=1.95;
thread helices and press-fit interference are intentionally omitted from CAD.
This is a nominal mounting representation, not a manufactured-thread drawing.
The silicone is bonded to the carrier at Z=4.15; no adhesive thickness is
modeled. Fastener labels use `_M0p8_socket_screw` and `_M0p8_captive_insert`.

The skin silhouette and all joint, pulley, tendon, and phalanx parameters are
unchanged by this work. Nails should remain outside these palmar mounting
surfaces and their occupied bore band Z=1.95–3.325.

Review source: `fingertip_pad_review.py`.
Review STEP: `../../STEP/anthropomorphic_hand/fingertip_pad_review.step`.
Review packet: `fingertip_pad_render_job.json`.
Validation: `../../validation/anthropomorphic_hand/fingertip_pad_validate.json`,
`fingertip_pad_refs.json`, `fingertip_pad_contact_trim.json`, and
`fingertip_pad_report.json`. The last file records source hashes and the final
pass status; partial/in-progress output is not an acceptance certificate.

Run the exact mounting and motion audit from the repository root:

```bash
PYTHONPATH=models/assemblies/src/anthropomorphic_hand .venv/bin/python models/assemblies/validation/anthropomorphic_hand/check_fingertip_pads.py
```

It checks all thirty new bodies against each other and all fifteen native
production phalanx factories over the named poses and independent full-range
10-degree samples, and checks actual route-wire distances with .30/.45 mm
outer radius envelopes. This is not an exhaustive all-joint Cartesian-product
sweep, nor a check against future palm/nail/other geometry.

The independent native contact check (`fingertip_pad_native_contact.json`)
reports zero overlap volume and 7.1e−15 mm minimum distance at the solved pose.
OCCT treats the analytic 0.000098164 mm clearance as contact within its surface
tolerance. This is the intended index–thumb touch, not a promise of submicron
manufacturing clearance.

The little pad was reduced from radii (5.75, 6.1, 2) to (5.2, 5.5, 2) to clear
the MCP flexion liner in the full fist. `fingertip_pad_little_repair.json` proves
all six new little components are exact subsets of the earlier components,
remeasures all mounting contacts, and reports 0.384264 mm liner clearance.
Consequently the earlier225-pose body sweep and every passing route result
remain conservative certificates for the final geometry. The larger-reference
route report intentionally retains its one failed full-fist row as evidence;
the repair certificate supersedes that exact pair.

Final acceptance: `../../validation/anthropomorphic_hand/fingertip_pad_acceptance.json`
reports `pass:true`:225 body poses,203 route poses,35 strict every-placement
validations, all mounted contacts, four cup route samples, and continuous
terminal-circle clearance. Recreate the joined certificate with:

```bash
PYTHONPATH=models/assemblies/src/anthropomorphic_hand .venv/bin/python models/assemblies/validation/anthropomorphic_hand/accept_fingertip_pads.py
```

The review link was loaded and verified in CAD Viewer:
http://127.0.0.1:3250/?file=assemblies/STEP/anthropomorphic_hand/fingertip_pad_review.step
Palmar and opposite snapshots are in the validation directory as
`fingertip_pad_macro.png` and `fingertip_pad_underside.png`. The underside
contact-patch render artifact is documented in repository `BUGS.md`016.
