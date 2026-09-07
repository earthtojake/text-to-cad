# Actuator mounting and tension sensing datums

This is a design contract for the remaining builders, not a completion claim.

The48actuators use24paired stations: four X columns−27,−9,+9,+27 and six Y
rows−252,−211,−170,−129,−88,−47. Motor native Z0 sits at world Z+4 on the
palmar bank. The dorsal bank is the same assembly rotated180° about Y, with
its native origin at world Z−4. Cases end native17.25, reducer shells26,
capstan centers29, capstan upper hub33.25. Output spindle ends33.20.

Each motor receives a real torsional spring/load-sensing mounting cartridge
between the central chassis and its case. The positive cartridge occupies
world Z+0.40..+3.95 (negative mirrored); the central frame occupies±0.35 at
the cartridge seats. Proposed cartridge outside radius8.20, outer mounting
annulus6.9..8.2, inner motor land4.6..6.8. Three sculpted compliant arms join
the lands. Three gauge chips bonded to arm surfaces make the torque sensor
explicit. Tendon tension follows measured reaction torque divided by the
7mm capstan working radius; sizing/calibration is outside this commission.

Motor mounting holes remain radius5.7 at angles0,120,240, Ø1.08clearance.
The cartridge must provide corresponding landing/thread bores under the motor.
Outer cartridge mounts are radius7.55 at60,180,300, Ø1.08. Mirroring the
dorsal cartridge about Y naturally staggers its three mounts between the
palmar ones. Frame seats contact the cartridge underside at±0.40 with a
0.05mm seat allowance; all fastener geometry is checked explicitly.

The chassis is a dark, open truss:24annular seats connected to longitudinal
rails and rear/front crossmembers, with real blended junctions. Overall
forearm envelope Y−280..0; distal chassis mounting extends to the wrist
fork's four bores at X±10,Y−30,Z±9, axesY (see WRIST_FOREARM_MOUNTS).
The outer housing should remain at |X|≥38 where the tendon bundle passes;
bundle lanes occupy−34.5..34.5, at |Z|37..43. Preserve every exit path in
lib/forearm_routing.py. The housing can be two sculpted dark side bodies,
with large windows, a rear flange and discrete cable exits.

Fastener contracts: three long M1 motor/reducer screws per actuator have
native head seat Z25.50, head top≤26.05 (the capstan begins26.10), headR≤.80,
shankR.50 and a length ending in the cartridge's motor land. One M1 capstan
retainer per actuator seats at native Z33.25, headR1.50, shank length1.50
(tip31.75; blind spindle bore starts31.65). These are independently resolved
solid bodies, with consistent socket heads and radiused visible edges.
