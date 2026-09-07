# Open forearm housing brief

Two dark anodized side frames, each 1.8 mm thick, frame the 48-actuator pack
without covering its broad faces. Their envelope is X±42.5..44.3,
Y−270.5..−36.5 and Z±47 mm. Two removable split clamps per side seat on the
existing rounded chassis rails at Y−264/−69. Eight nominal M1.6 socket screws
close these clamps; no existing frame hole or actuator coordinate is changed.

Four double-lip silicone grommets resolve Ø2.6 cable exits at the rear edges.
Eight separate tie anchors with sixteen nominal M1.2 socket screws provide
open cable-tie passages. Cable harnesses and ties are not yet installed.
The assembly is 42 separately labeled closed solids. All new parts attach to
the forearm frame in assembled coordinates via `forearm_housing_bodies()`.
The distal inner clamp caps have a straight inward-open relief around the
existing Y−67.5 transverse brace. The grommet shoulders are reamed after
rounding to keep their entire Ø4.4 panel seat clear of the panel material.

Remove the clamp screws and inner caps inward, then separate the side frames
outward. The elastic grommets remain with their panels for exploded viewing.
Tie anchors and their screws withdraw outward. Thread forms are nominal
envelopes. Validation must cover strict solids, mating contacts, local mutual
intersections, the existing 110 frame/guide and 824 fastener bodies, all 48
neutral tendon paths and capstan motion ±5π, plus full wrist motion.

The final every-placement native gate passes all 42 bodies. The independent
Bernstein control-bound proof covers every capstan angle in ±5π, with at least
2.220373 mm surface clearance to every housing body. Screw/rail bearing seats
are checked by a 0.001 mm approach; the 28 seats and 240 initial removal
samples pass. The corrected caps additionally pass 42 samples against the
actual rounded transverse brace. `forearm_housing_certificate.py` issues the
combined certificate only after the complete fit, actuator, wrist and render
proofs finish successfully. All proof files reside under
`models/assemblies/validation/anthropomorphic_hand`.

`forearm_housing_context.step` includes the actual 48 motor/gearbox/cartridge
stacks and the accepted 110 frame/guide and 824 fastener bodies. Its final
render certificate records the completed STEP SHA256 before and after the
render, the PNG SHA256, the render-job SHA256 and the housing source SHA256.
