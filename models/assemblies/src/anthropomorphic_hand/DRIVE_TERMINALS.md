# Driven tendon terminals

Every one of the 48 antagonists retains its original 150-degree neutral wrap,
0.30 mm rope radius and R3.5 / R4.5 / R5.5 / R7 / R11 working circle. The last
0.8 mm enters a separately manufactured curved steel ferrule: OD 0.92 mm,
ID 0.62 mm, with a 0.10 mm blind cap exactly against the flat rope endpoint.
The sleeve follows the original arc; no straight sleeve cuts across a bend.
A separate dark resin solid fills the 0.01 mm radial bond line between rope
and sleeve. That bond transfers tensile load into the ferrule; its material
strength has not been qualified. The identical capstan bond allowance is also
resolved into 48 individually placed resin solids.

A sculpted aluminum ear extends the pulley only to pitch radius + 0.64 mm and
stays inside the existing 1.50 mm axial cheek envelope. Its 0.98 mm pocket
clears the ferrule by 0.03 mm radially. The 0.72 mm inlet is smaller than the
ferrule OD, providing a positive pullout shoulder. The blind cavity prevents
motion beyond the rope tip. A separately made flush cover closes the pocket.
A recessed nominal M0.4 socket screw holds the cover: 0.40 mm shank diameter,
0.68 mm head diameter, 0.28 mm AF socket, 0.45 mm shank length, and 0.22 mm
head height. Its real shoulder seats at native Z+0.25 mm and its threaded tail
ends at Z-0.20 mm in the lower rim. The screw center sits 0.74 mm radially
inside the working rope circle, clear of the ferrule. The port has straight
axial walls. Removal sequence is screw +Z, cover +Z, then ferrule +Z; each
step is sampled every 0.05 mm. These are nominal thread envelopes rather than
helices, with no permanent weld or swage trapping the parts.

Each pulley also has a real inclined cone-point socket grub screw, represented
by a nominal M0.5 thread envelope: 0.50 mm major diameter, 0.78 mm overall
length and a 0.26 mm AF hex socket. The 45-degree screw axis exits the open
hub face; positive/negative antagonists use opposite axial sides. Its cone
point touches the existing continuous D-shaft flat without intersecting it.
It clamps axial position by friction; it is not a dog point or a positive
axial stop. The D profile carries torque. The screw and threaded hole are
nominal envelopes, not modeled helices. The complete installed screw stays
inside the pulley axial envelope (maximum native |Z| 0.7284 mm).

First release the inclined screw along its axis, withdraw the joint shaft
using its hardware sequence, then separate the pulley outboard. Remove the
terminal cover screw, cover and ferrule in that order. The helper
`drive_terminal_release_directions()` supplies neutral-world vectors for all
288 driven occurrences; it deliberately leaves animation timing to the integrator.

`lib/drive_terminal.py::drive_terminal_bodies()` returns 288 already assembled
and fanned occurrences, six for each route: drive pulley, removable cover,
cover socket screw, curved blind ferrule, resin sleeve and inclined grub screw. Every occurrence attaches to its
target child joint. The original assembly pulley loop must be removed and
this registry appended after the finger fan operation. The existing
`lib/pulley.py` remains the unchanged five-radius plain-pulley factory.

Validation is recorded by
`models/assemblies/validation/anthropomorphic_hand/drive_terminal_check.py`:
strict per-placement solids, exact rope/ferrule/pulley contacts, ferrule
pullout in six directions, axial ferrule insertion with the cover removed,
neutral inter-part interference, and target-joint motion at ten-degree
increments plus limits against real shafts and bushings. Whole-hand
frame/guide collision validation remains the assembly integrator's gate.
The equivalent parallel motion runner is `drive_terminal_motion_check.py`,
which loads the frozen native STEP per worker. `drive_terminal_certificate.py`
combines the completed proofs only after asserting 336 strict occurrences,
48 driven and 48 capstan seating checks, 56,280 neutral pairs, 200 removal
steps, 30 capture directions and all 434 target-joint poses.


Before axial terminal disassembly, retract each driven rope tip by 0.85 mm
along its existing final arc (0.80 mm sleeve length plus 0.05 mm separation).
The final arc sweep changes by `sign * degrees(0.85 / drive_radius)`. Advance
the capstan-side rope start by 0.85 mm along the exact helix. Both motions go
away from the blind caps, so the 0.10 mm cap thickness adds no travel. The
numeric per-route contract is `tendon_end_release_contract()`.

`capstan_bond_bodies()` separately returns 48 already placed forearm resin
sleeves; the existing capstan, steel ferrule and rope geometry is unchanged.

For the exploded presentation, retain each capstan resin sleeve with its
bonded ferrule/capstan group. A separate +Z sleeve withdrawal was tested and
failed against the existing capstan; the candidate is retained in
`capstan_bond_release_check.json`. `capstan_bond_release_directions()` is an
uncertified initial-direction candidate, not a complete collision-free path.
The capstan geometry remains unchanged. Peeling bonded resin is not required.
