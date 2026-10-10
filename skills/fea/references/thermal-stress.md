# Heat stress (`thermal_stress`)

**Not available in this cadgen yet.** `cadgen fea solve` refuses a study with `"analysis": "thermal_stress"` ("'thermal_stress' is planned but not in this cadgen yet"), so do not write one; tell the user it is coming, and see the skill's "When the question needs an analysis that is not here yet". This page is filled in, with its schema, an example, a hand check, its limits and its adapted steps, when it ships.

It will answer "it gets hot: does that stress it or warp it": the stress and movement that come from the part's temperature field (from a `thermal` solve that runs first), with optional mechanical loads on top.

On top of the common keys in [study-file.md](study-file.md#common-keys), it will take:

- The `thermal` keys (`temperatures`, `heat`, `convection`).
- `fixtures` and optional `loads`: as `static`.
- `reference_C`: the temperature at which the part is stress-free, default 20.
- The material needs a conductivity and a thermal expansion (`conductivity_W_mK`, `expansion_per_K`).
- Checks `stress` and `displacement`, as `static`.
