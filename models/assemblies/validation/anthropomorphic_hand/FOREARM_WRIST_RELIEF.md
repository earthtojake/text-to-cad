# Forearm wrist saddle revision

The fixed wrist fork's curved side ribs clipped the two forward chassis eyes by1.992385mm³. The revised chassis retains the original mounting bores and subtracts aR0.96 swept saddle along each actualR0.90 fork rib. New saddle edges have0.025mm blends.

`forearm_wrist_relief_certificate.json` confirms native intersection0mm³, minimum separation0.0599993mm, and zero new material outside the previously validated chassis. The prior tendon/sensor/fastener clearance certificates remain valid by exact material-subset proof. Removed volume is39.2292169mm³.

`forearm_wrist_fit_strict.json` checks both unique native solids: valid topology, closed shells, positive volumes, zero self-intersection failures. The report uses first-placement mode; each of the two prototypes has exactly one placement, so both placements were checked.

Source changed: `models/assemblies/src/anthropomorphic_hand/lib/forearm_frame.py`. This is a model fit correction, not a repository defect.
