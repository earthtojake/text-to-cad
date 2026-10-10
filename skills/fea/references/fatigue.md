# Fatigue life (`fatigue`)

**Not available in this cadgen yet.** `cadgen fea solve` refuses a study with `"analysis": "fatigue"` ("'fatigue' is planned but not in this cadgen yet"), so do not write one; tell the user it is coming, and see the skill's "When the question needs an analysis that is not here yet". This page is filled in, with its schema, an example, a hand check, its limits and its adapted steps, when it ships.

It will answer "how long will it last": the number of load cycles the part survives and its fatigue safety factor (S-N curve with a Goodman mean-stress correction), from a static load case repeated, a harmonic dwell or a random vibration spec.

On top of the common keys in [study-file.md](study-file.md#common-keys), it will take:

- `fatigue`: `{"from": "static" | "harmonic" | "random_vibration", "loading": "fully_reversed" | "zero_based" | {"ratio": R}, "cycles": 1e6, "surface": "machined"}`, plus `dwell_s` or `duration_s` for the dynamic sources.
- The source study's own keys at top level (for example the `fixtures` and `loads` of the static case).
- The material needs an ultimate strength and fatigue data. Polymers carry none, so a polymer study asks for `fatigue_strength_MPa` and `fatigue_cycles` in the material object.
- Check `fatigue`: `cycles` (the life needed) and `margin` (default 1.5): "Lasts 2.1 million cycles, needs 1 million".
