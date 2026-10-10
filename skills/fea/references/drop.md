# Drop (estimate) (`drop`)

**Not available in this cadgen yet.** `cadgen fea solve` refuses a study with `"analysis": "drop"` ("'drop' is planned but not in this cadgen yet"), so do not write one; tell the user it is coming, and see the skill's "When the question needs an analysis that is not here yet". This page is filled in, with its schema, an example, a hand check, its limits and its adapted steps, when it ships.

It will answer "what if I drop it" as an estimate: an equivalent steady load from the drop height and how quickly the part stops, solved as a static study with the landing faces held. It is an estimate, never an impact simulation, and every result says so. Until it ships, the same estimate runs today as a `static` study with an `acceleration` load ([linear-static.md](linear-static.md#body-loads-gravity-and-acceleration)).

On top of the common keys in [study-file.md](study-file.md#common-keys), it will take:

- `drop`: `{"height_mm": 1000, "onto": [faces that hit], "stop_mm": 2}`, or `impact_ms` (a half-sine stop) instead of `stop_mm`; optional `direction`.
- `dynamic`: `true` to also run a `transient` with a half-sine pulse and report the larger answer.
- The material needs a density.
- Check `stress` (labelled "Drop") and `displacement`.
