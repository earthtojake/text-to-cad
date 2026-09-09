# Forearm guide-mouth supports

`lib/forearm_guide_mounts.py` exposes `make_forearm_guide_mount_bodies(host=None)`.
The result is108 independently named native solids in the assembled forearm
frame. Assign every returned body to the `forearm` articulated frame; do not
apply a finger fan or actuator placement. The optional `host` is the actual
forearm chassis. With no argument, the factory reproduces the same two rail
contact surfaces from the shared rail dimensions, avoiding an expensive
unrelated chassis rebuild.

`forearm_guide_rows()` derives96 actual +Y mouth datums from
`guide_end_registry()`:48 capstan-guide downstream outlets and48 wrist-guide
inlets. It excludes the capstan followers' moving upstream mouths and the2
wrist drive-side ends owned by the other mount builder.

Each side has five exit bridges atY−222/−181/−140/−99/−58 and one forward portal.
The forward portal supports the last four exits atY−17 and all24 wrist inlets
atY−12. The six face heights remain±43/41.8/40.6/39.4/38.2/37, with the exact
staggered bundle lanes unchanged. Each four-bore comb hasR0.47 guide bores,
0.55mm axial length and a0.08mm split between the jaws. The liners areR0.45.
The0.08 split admits the required0.04mm diametral closing travel.

Twelve lower structures carry the split combs and side arches. Twenty-four
separate upper comb jaws and48 separate recessed M0.6 socket screws close
the mouths. Twenty-four separate M1 socket screws attach the lower structures
to the existing chassis bores onX±38,Y−223/−182/−141/−100/−59/−36. Their working
shanks extend2.8mm inward from the foot topZ±7.5; each head is1.7mm diameter
and0.7mm high. All screw sockets are real recesses. Thread helices are not
represented in the B-rep.

The two native review files are `forearm_guide_banks_review.step` (108 bodies)
and `forearm_mount_system_review.step` (frame plus guides,110 bodies), under
`models/assemblies/STEP/anthropomorphic_hand/`. Strict
`inspect validate --every-placement` on the final guide export reports108
occurrences,96 prototypes and0 failures, including topology, closure, volume
and every-placement self-intersection checks. Verdict:
`tmp/anthropomorphic_hand/forearm_guide_banks_validate.json`.

The full48 neutral-route audit uses actual path-wire-to-body distances, guide
radius0.45 and bare tendon radius0.30. It also checks actual chassis contact and
all mutually nearby mount/fastener solids. The final report is
`tmp/anthropomorphic_hand/forearm_guide_banks_fit.json`; the reproducible script
is `check_forearm_guide_banks.py` in that directory. The final-export repeat reports `ok:true`:620 exact path-to-body distances,
0 route collisions,0 chassis volume overlaps and0 mutual volume overlaps.
Minimum route surface clearance is0.0097216948665mm.

The guide and contextual default-renderer1800×1400 snapshots were inspected:
`tmp/anthropomorphic_hand/forearm_guide_banks.png` and
`tmp/anthropomorphic_hand/forearm_mount_system.png`.
The current viewer serves `models/` at `http://127.0.0.1:3250/`; select the
corresponding `assemblies/STEP/anthropomorphic_hand/` file.

All moving-pose/wrist compensation tests and newly added housing/fastener
clearances remain part of the complete integration gate. No mount stiffness
or manufacturing qualification is asserted by these geometric checks.
