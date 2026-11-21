skill: sendcutsend
fixtures: tab.py => tab.step

## Request

I'm about to order tab.step from SendCutSend: 5052 aluminium, 0.090 inch thick, laser cut with its one bend, no finishing, quantity 10. Can you preflight it and tell me whether it is ready to upload?

## Expect

SKU ALU-090 joined. Two failures found: the inside bend radius (2.0 mm against `bending_specs.effective_bend_radius` 0.032 in) and the short flange (7.0 mm outside against `min_flange_length_after_bend` 0.326 in). Rows cite the JSON field paths; no "ready" verdict.
