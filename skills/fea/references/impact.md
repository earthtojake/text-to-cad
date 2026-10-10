# Drop impact (`impact`)

**Not available in this cadgen yet.** `cadgen fea solve` refuses a study with `"analysis": "impact"` ("'impact' is planned but not in this cadgen yet"), so do not write one; tell the user it is coming, and see the skill's "When the question needs an analysis that is not here yet". This page is filled in, with its schema, an example, a hand check, its limits and its adapted steps, when it ships.

It will answer "what really happens when it hits the floor": a simulation through time of the part striking a rigid floor, with the peak g and peak stress, the deeper check after a `drop` estimate. It is a lite solver: rigid floor, simple (linear) elements, elastic unless plasticity is given.

On top of the common keys in [study-file.md](study-file.md#common-keys), it will take:

- `drop`: `{"height_mm": 1000, "direction": [0, 0, -1], "floor": "rigid", "friction": 0.0}`.
- `window_ms`: how long to simulate, or `"auto"`.
- `plasticity`: optional `{"tangent_MPa": 200}`.
- `mesh.order`: 1 is the only order allowed.
- Checks `stress`, `acceleration` (`limit_g`) and `plastic_strain` (`limit_percent`).
