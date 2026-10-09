# Materials

Isotropic, linear, room temperature. Name one in the study's `material`, or
give the numbers yourself. These are textbook values for a first pass; a
study that matters uses the supplier's datasheet through the object form
(`{"name": "...", "E_MPa": ..., "nu": ..., "yield_MPa": ...}`).

| name (and aliases) | E (MPa) | ν | yield (MPa) | density (t/mm³) | notes |
| --- | --- | --- | --- | --- | --- |
| `steel` (`mild-steel`) | 200 000 | 0.30 | 250 | 7.85e-9 | generic structural / low-carbon |
| `stainless-304` (`304`, `stainless`, `ss304`) | 193 000 | 0.29 | 215 | 8.00e-9 | annealed |
| `aluminum-6061-t6` (`6061`, `6061-t6`, `aluminum`, `aluminium`) | 68 900 | 0.33 | 276 | 2.70e-9 | the default aluminium |
| `aluminum-7075-t6` (`7075`, `7075-t6`) | 71 700 | 0.33 | 503 | 2.81e-9 | |
| `titanium-6al-4v` (`titanium`, `ti-6al-4v`) | 113 800 | 0.342 | 880 | 4.43e-9 | |
| `brass` | 97 000 | 0.31 | 310 | 8.50e-9 | C36000, half hard |
| `abs` | 2 200 | 0.35 | 40 | 1.04e-9 | injection moulded; printed parts are weaker and anisotropic |
| `pla` | 3 500 | 0.36 | 60 | 1.24e-9 | printed; treat yield as an upper bound |
| `petg` | 2 100 | 0.38 | 50 | 1.27e-9 | printed |
| `nylon-pa12` (`nylon`, `pa12`) | 1 700 | 0.40 | 48 | 1.01e-9 | SLS / MJF |

Names are case-insensitive; spaces and underscores read as hyphens.

For printed polymers the model's assumptions are loose: layer adhesion,
infill and orientation change stiffness and strength by a factor of two or
more. Say so, and use a larger safety factor than for a machined metal part.
