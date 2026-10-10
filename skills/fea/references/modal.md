# Vibration (`modal`)

**Not available in this cadgen yet.** `cadgen fea solve` refuses a study with `"analysis": "modal"` ("'modal' is planned but not in this cadgen yet"), so do not write one; tell the user it is coming, and see the skill's "When the question needs an analysis that is not here yet". This page is filled in, with its schema, an example, a hand check, its limits and its adapted steps, when it ships.

It will answer "will it rattle or resonate, and at what frequencies does it ring": the part's natural frequencies and the shape it vibrates in at each, so you can check that the first one stays above a limit or clear of a motor's or a road's frequency band. With no fixture the part is free in space, and the six rigid-body motions are dropped and counted.

On top of the common keys in [study-file.md](study-file.md#common-keys), it will take:

- `fixtures`: optional; none means free-free.
- `modes`: how many to find, 1 to 30, default 6.
- `range_Hz`: an optional `[low, high]` window to search in.
- Check `frequency`: `min_Hz` (and optional `mode`, default 1), or `avoid_Hz: [low, high]`; exactly one of them. Plain word Vibration: "First mode 85 Hz, must stay above 60 Hz".
