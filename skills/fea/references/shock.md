# Shock (`shock`)

**Not available in this cadgen yet.** `cadgen fea solve` refuses a study with `"analysis": "shock"` ("'shock' is planned but not in this cadgen yet"), so do not write one; tell the user it is coming, and see the skill's "When the question needs an analysis that is not here yet". This page is filled in, with its schema, an example, a hand check, its limits and its adapted steps, when it ships.

It will answer "will it survive this shock spec", given as a shock response spectrum (SRS): the peak stress and movement, combining each vibration shape's response by SRSS or CQC.

On top of the common keys in [study-file.md](study-file.md#common-keys), it will take:

- `fixtures`: as `static`.
- `srs`: `{"direction": [0, 0, 1], "table": [[10, 5], [100, 50], ...], "damping_ratio": 0.05}`, frequency in Hz against peak g.
- `combination`: `"srss"` or `"cqc"`.
- Check `stress` (labelled "Shock") and `displacement`.
