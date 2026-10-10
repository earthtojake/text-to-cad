# Flow (`cfd`)

**Not available in this cadgen yet.** `cadgen fea solve` refuses a study with `"analysis": "cfd"` ("'cfd' is planned but not in this cadgen yet"), so do not write one; tell the user it is coming, and see the skill's "When the question needs an analysis that is not here yet". This page is filled in, with its schema, an example, a hand check, its limits and its adapted steps, when it ships.

It will answer "how does fluid flow through or around it, what is the pressure drop, and how hard does the flow push on it": steady, laminar, incompressible flow, with the wall pressure optionally applied to a static solve of the part. It is a lite solver: laminar, steady, incompressible, no turbulence model. Above a Reynolds number of 2000 inside a pipe (1000 around a body) it still solves but warns that the real flow is likely turbulent, so the pressure drop is a lower bound.

On top of the common keys in [study-file.md](study-file.md#common-keys), it will take:

- `flow`: `{"kind": "internal" | "external", "fluid": "air" | "water" | {"density_kg_m3", "viscosity_Pa_s"}, "inlets": [{"opening": "x_min", "velocity_m_s": 0.5}], "outlets": [{"opening": "x_max", "pressure_Pa": 0}]}`; an external flow gives `velocity_m_s` as a vector.
- `map_to_structure`: optional `{"material", "fixtures"}` to solve the part's stress under the flow's pressure.
- Checks `pressure_drop` (`limit_Pa`), `velocity` (`limit_m_s`), and `stress` and `displacement` when mapped.
