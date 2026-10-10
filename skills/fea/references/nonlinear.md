# Permanent bend / Stretch (`nonlinear`)

**Not available in this cadgen yet.** `cadgen fea solve` refuses a study with `"analysis": "nonlinear"` ("'nonlinear' is planned but not in this cadgen yet"), so do not write one; tell the user it is coming, and see the skill's "When the question needs an analysis that is not here yet". This page is filled in, with its schema, an example, a hand check, its limits and its adapted steps, when it ships.

It will answer "does it bend for good" (metal past yield, with a simple two-slope plasticity) and "how does a rubber part stretch" (a Neo-Hookean material, large deformation), with the load applied in steps. A load the part cannot carry is a result ("Collapses at about 70 % of the load"), not a refusal. It is a lite solver.

On top of the common keys in [study-file.md](study-file.md#common-keys), it will take:

- `fixtures` and `loads`: as `static`.
- `material` with `plasticity: {"tangent_MPa": 2000}`, or `hyperelastic: {"model": "neo_hookean", "mu_MPa": 0.6, "bulk_MPa": 300}`.
- `steps`: the starting number of load steps.
- Checks `plastic_strain` (`limit_percent`: "0.4 % permanent, limit 0.2 %") and `displacement`.
