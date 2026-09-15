# Edit the imported planetary STEP

This ordinary `@step` model reads the fixed nine-part planetary STEP through
the public `read_step` API. A geometry edit changes only the carrier diameter
from 105 to 106 mm. A placement edit moves the original carrier down 0.5 mm.
The other eight imported parts retain their geometry, names and colors.
The replacement carrier uses the same cylinder and three hole cuts as the
FreeCAD comparison: a 4 mm plate starting at Z = −5 mm, with 6.4 mm holes
on a 42 mm radius. No gear-generation code runs.

Prepare a scratch copy with an existing nine-part `planetary.step`:

```sh
python scripts/bench/cadgen-performance/imported_step_edit.py prepare \
  --step models/tmp/performance-study/planetary.step \
  --directory models/tmp/planetary-imported-study
```

The command copies the model into `src/` and the exact foreign input bytes
into `input/`. The model writes a different `STEP/planetary.step`; it never
reads its own output. The example does not carry a generated STEP input.
Keep all study inputs, outputs and stores under the repository's `models/`
directory. Run `imported_step_edit.py validate` before collecting
timings; it verifies the source result and saved STEP for all three variants,
including retained native topology for the other eight source parts.

With the checkout's cadgen on `PYTHONPATH` and `CAD_PYTHON` pointing to its
CAD-capable Python environment:

```sh
"$CAD_PYTHON" scripts/bench/cadgen-performance/imported_step_edit.py validate \
  --directory models/tmp/planetary-imported-study \
  --report tmp/performance-study/imported-validation.json

"$CAD_PYTHON" scripts/bench/cadgen-performance/warm_build.py \
  --model models/tmp/planetary-imported-study/src/planetary_gear_assembly.py \
  --placement-from 'CARRIER_OFFSET_Z = 0.0' \
  --placement-to 'CARRIER_OFFSET_Z = -0.5' \
  --store models/tmp/planetary-imported-study/store \
  --report tmp/performance-study/imported-warm.json \
  --iterations 3 --skip-imports

python scripts/bench/cadgen-performance/imported_step_edit.py verify-report \
  --report tmp/performance-study/imported-warm.json \
  --output tmp/performance-study/imported-checks.json
```

Validation uses a separate store and restores the source's exact bytes and
timestamps. Each saved-file check starts with a fresh store. Timing uses the
warm harness's normal priming/restoration schedule, with a different store;
the first build includes foreign-input preparation. The report checker
requires nine occurrences on every call, exactly one replaced component for
diameter edits, and no replaced components for placement edits. Repeated
occurrences may share one component.

The benchmark includes public STEP loading on each executed edit, source
preview preparation and whole-assembly STEP publication. Current cadgen can
materialize a previously imported STEP from its byte-addressed store. The
reviewed baseline parses a foreign STEP again. FreeCAD instead retains its
imported document in memory. Report those boundaries and cold import costs
separately; none of these headless timings measures a visible GUI frame.
