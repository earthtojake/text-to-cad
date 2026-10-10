# Heat (`thermal`)

**Not available in this cadgen yet.** `cadgen fea solve` refuses a study with `"analysis": "thermal"` ("'thermal' is planned but not in this cadgen yet"), so do not write one; tell the user it is coming, and see the skill's "When the question needs an analysis that is not here yet". This page is filled in, with its schema, an example, a hand check, its limits and its adapted steps, when it ships.

It will answer "how hot does it get once it has settled": the steady temperature across the part from faces held at a temperature, heat put in (a chip, a heater) and heat carried away by air or liquid (convection). A part that is only heated, with nowhere for the heat to go, has no steady temperature, so at least one held temperature or convection is required.

On top of the common keys in [study-file.md](study-file.md#common-keys), it will take:

- `temperatures`: `[{"faces": [...], "C": 25}]`, faces held at a temperature in °C.
- `heat`: `[{"faces": [...], "W": 15}]` (total power) or `{"faces": [...], "W_per_m2": 2000}` (heat flux).
- `convection`: `[{"faces": [...], "h_W_m2K": 10, "ambient_C": 25}]`.
- The material needs a conductivity (`conductivity_W_mK`).
- Check `temperature`: `max_C`, optional `faces`: "Hottest 84 °C, limit 100 °C".
