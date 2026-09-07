# Wrist frame interface

All three frame factories in `lib/wrist.py` return one valid solid in assembled neutral coordinates. The wrist has yaw about world Z through (0,−9,0), and flexion about X through (0,0,0). The yaw carrier follows yaw; the palm cradle follows yaw then flexion. The fixed fork stays with the forearm.

- Yaw driven pulleys: R 11, centers (0,−9,±5.5), D bore R 3.03 with flat toward world +X at 2.25.
- Flexion driven pulleys: R 11, centers (±14,0,0), D bore R 3.03 with flat toward world +Y at 2.25.
- Parent yaw bearing eyes: Z±9, thickness 3, bore R 5.03.
- Parent flexion bearing eyes: X±17, thickness 3, bore R 5.03.
- Moving flexion keyed eyes: X±20, thickness 2.4, D bore R 3.03/flat 2.25.
- Four forearm mounting holes: X±10,Y−30,Z±9, bore R 1.65 along Y. The mounting eye faces are Y−31.5 andY−28.5.
- Palm cradle mounting shoes: X±24,Y 14,Z−13.4, thickness 2.4, bore R 1.65 along Z. The top face Z−12.2 sits 0.60 mm below the palm boss bottom face Z−11.6. Insert actual 0.60 mm spacers under the palm bosses.

`make_wrist_bushings()` supplies all four separate flanged steel bearing bodies as `(frame, body)` pairs, where frame is `fixed` or `yaw`. Their radius 5 sleeves have bore 3.03; flanges radius 5.45 and thickness 0.28 face outward. The flexion flange outer faces at X±18.78 leave 0.02 mm axial clearance to the moving keyed eyes.

The local internal sweep includes actual frames, four actual driven pulleys, all four bushings, and continuous radius 3 D-shaft envelopes. Shaft retaining heads/rings, palm spacers, tendon paths, and the final palm-context gate are integration responsibilities. No claim is made that the local wrist gate certifies the complete hand.

Validation: `wrist_validate.json`, `wrist_factory_check.json`, and `wrist_internal_clearance.json` under the hand validation directory. Rerun `wrist_clearance.py` without `--wrist-only` once the final palm factory is stable. The script keeps the complete wrist range and simultaneous extrema, and caches only exact rigid-relative pair invariants.
