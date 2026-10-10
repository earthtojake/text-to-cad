# Over time (`transient`)

**Not available in this cadgen yet.** `cadgen fea solve` refuses a study with `"analysis": "transient"` ("'transient' is planned but not in this cadgen yet"), so do not write one; tell the user it is coming, and see the skill's "When the question needs an analysis that is not here yet". This page is filled in, with its schema, an example, a hand check, its limits and its adapted steps, when it ships.

It will answer "what happens under a load that changes over time", such as a hammer blow or a sudden step: the movement and stress through time, and their peak.

On top of the common keys in [study-file.md](study-file.md#common-keys), it will take:

- `fixtures` and `loads`: as `static`, each load with a `history`: `[[t_s, factor], ...]` or `{"shape": "step" | "ramp" | "half_sine", "duration_s": 0.002}`.
- `excitation`: a shake at the fixtures instead, as in `harmonic`, with a `history`.
- `end_s`, `step_s` (or `"auto"`), `damping_ratio` (default 0.02).
- `method`: `"modal"` (default) or `"direct"`.
- Checks `stress` and `displacement`.
