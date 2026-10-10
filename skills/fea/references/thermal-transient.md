# Heat over time (`thermal_transient`)

**Not available in this cadgen yet.** `cadgen fea solve` refuses a study with `"analysis": "thermal_transient"` ("'thermal_transient' is planned but not in this cadgen yet"), so do not write one; tell the user it is coming, and see the skill's "When the question needs an analysis that is not here yet". This page is filled in, with its schema, an example, a hand check, its limits and its adapted steps, when it ships.

It will answer "how hot does it get during a warm-up or a duty cycle, and when is it hottest": temperature against time from a starting temperature, with heat, held temperatures and convection that can switch on and off over time.

On top of the common keys in [study-file.md](study-file.md#common-keys), it will take:

- The `thermal` keys (`temperatures`, `heat`, `convection`).
- `initial_C`: the starting temperature.
- `end_s`: how long to run, in seconds; `step_s`: the time step, or `"auto"`.
- `history`: `[[t_s, factor], ...]` on any heat, temperature or ambient entry, a straight-line schedule.
- The material needs a conductivity and a specific heat (`conductivity_W_mK`, `specific_heat_J_kgK`).
- Check `temperature`: `max_C`, judged at the hottest moment.
