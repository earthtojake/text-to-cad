# Random vibration (`random_vibration`)

**Not available in this cadgen yet.** `cadgen fea solve` refuses a study with `"analysis": "random_vibration"` ("'random_vibration' is planned but not in this cadgen yet"), so do not write one; tell the user it is coming, and see the skill's "When the question needs an analysis that is not here yet". This page is filled in, with its schema, an example, a hand check, its limits and its adapted steps, when it ships.

It will answer "will it survive this transport or vibration spec", given as a power spectral density in g²/Hz: the RMS stress and movement the random shaking causes, judged at 1 or 3 sigma.

On top of the common keys in [study-file.md](study-file.md#common-keys), it will take:

- `fixtures`: as `static`.
- `psd`: `{"direction": [0, 0, 1], "table": [[20, 0.01], [80, 0.04], ...]}`, frequency in Hz against g²/Hz.
- `damping_ratio`: default 0.02; `sigma`: 1 or 3, default 3, the level the checks judge at.
- Checks `stress` (labelled "Random vibration") and `displacement`.
