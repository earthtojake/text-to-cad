# Shaking (`harmonic`)

**Not available in this cadgen yet.** `cadgen fea solve` refuses a study with `"analysis": "harmonic"` ("'harmonic' is planned but not in this cadgen yet"), so do not write one; tell the user it is coming, and see the skill's "When the question needs an analysis that is not here yet". This page is filled in, with its schema, an example, a hand check, its limits and its adapted steps, when it ships.

It will answer "what happens on a shaker, or across a motor's speed range": the part's response to a steady sine shake swept across a frequency range, either shaken at its fixtures or pushed by a force, with the worst stress and acceleration and the frequencies where they peak.

On top of the common keys in [study-file.md](study-file.md#common-keys), it will take:

- `fixtures`: as `static`.
- `excitation`: `{"type": "base", "direction": [0, 0, 1], "amplitude_g": 1}` (shaken at the fixtures) or `{"type": "force"}` (the `loads` as amplitudes).
- `sweep_Hz`: `[low, high]`; `damping_ratio`: default 0.02.
- Checks `stress`, `displacement` and `acceleration` (`limit_g`, optional `faces`: "Peak 12 g, limit 10 g").
