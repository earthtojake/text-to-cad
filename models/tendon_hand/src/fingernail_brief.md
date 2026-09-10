# Dorsal fingernail subsystem

Five shallow blasted-aluminum closed ovals, proportioned to the existing distal phalanges (8.14–9.62 mm wide, 8.64–11.34 mm long, 1.36 mm maximum thickness). The oval is a rational ellipsoid, with continuous dorsal curvature and a rolled edge. Its aluminum finish repeats the existing structural material; a slender dark conformal saddle visually separates the nail from the skeleton.

Each nail has its own structural saddle, two M0.8 socket screws, and two captive flanged inserts. The host's existing two Ø1.12 pad-bores are continued dorsally without changing their axis or diameter. The lower inserts terminate at local Z=1.65, below the existing palmar inserts beginning at Z=1.95. Nominal cylindrical threaded interfaces omit helical thread tessellation and interference. The saddle conforms to the actual host exterior and nail underside through exact Boolean subtraction.

Factories in `lib/fingernail.py` return positive native solids and do no CAD work during import. `fingernail_bodies()` returns thirty `(shape, frame, system, kind)` tuples in the same neutral assembly fan used by the accepted pad subsystem: six bodies each on index/middle/ring/little DIP and thumb IP. Integrators must not apply that fixed fan again.

The separate review native STEP includes all thirty nail bodies, all thirty pad bodies, and fourteen finger/thumb phalanges at their actual assembled proportions. The collision audit additionally includes the thumb metacarpal. Its 225 poses and all 48 routes per pose are taken from the immutable static packet manifest. Reports state the completed scope and must be consulted before acceptance.

The nail-to-saddle interface is a conformal structural bond, modeled at zero bond-line thickness, analogous to the palmar pad's bonded support. The two metal screws clamp the saddle to the distal rail through captive inserts; they do not clamp the oval's remote center. Adhesive chemistry, thread pitch, preload, fatigue and strength remain engineering selections rather than claims from this geometric model.
