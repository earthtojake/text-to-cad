# Contact (`contact`)

**Not available in this cadgen yet.** `cadgen fea solve` refuses a study with `"analysis": "contact"` ("'contact' is planned but not in this cadgen yet"), so do not write one; tell the user it is coming, and see the skill's "When the question needs an analysis that is not here yet". This page is filled in, with its schema, an example, a hand check, its limits and its adapted steps, when it ships.

It will answer "what happens where parts press or slide on each other": an assembly whose chosen pairs touch without being glued, with or without friction, and parts resting on a rigid plane, giving the stress and the contact pressure. It is a lite solver.

On top of the common keys in [study-file.md](study-file.md#common-keys), it will take:

- `connections`: `[{"between": [A, B], "type": "contact", "friction": 0.2}]`; other touching pairs stay bonded.
- `rigid_planes`: `[{"point_mm": [0, 0, 0], "normal": [0, 0, 1], "parts": [...]}]`.
- `fixtures`, `loads` and `steps`: as `nonlinear`.
- Checks `stress` and `contact_pressure` (`limit_MPa`, optional `faces`).
