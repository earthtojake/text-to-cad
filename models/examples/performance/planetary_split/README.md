# Planetary assembly with decorated children

This is the nine-part planetary benchmark expressed as a root assembly and
nine ordinary `@step` child models. It preserves the monolithic fixture's
geometry, labels, linear RGBA colors, leaf order and placements. Every child
declares a real STEP output so a benchmark includes its save obligation.

The geometry is in millimeters: ring centered on the origin, gears in XY,
axes along +Z, 140 mm outside diameter, and Z from −5 to 9 mm. The assembly
contains one carrier, one ring, one sun, three planets and three pins. The
carrier is 105 mm in diameter and 4 mm thick; its geometry edit changes that
diameter to 106 mm. The placement edit moves only the carrier down 0.5 mm.
No kinematics, mesh exports or additional runtime authoring API are used.

The files under `src/` are runnable models. `src/lib/geometry.py` contains
plain geometry factories copied from the original fixture; the carrier's
diameter is an argument supplied only by `src/carrier_plate.py`. The root
imports only model functions, calls all nine before reading their geometry,
and owns the `CARRIER_OFFSET_Z` placement constant. These source boundaries
let unchanged children retain their pinned results.

For experiments, copy this project with the repository benchmark command:

```sh
python scripts/bench/cadgen-performance/prepare.py split-fixture \
  --directory models/tmp/planetary-split-study
```

Then run the copied `src/planetary_gear_assembly.py`; it writes the root and
child STEP files into that copy's `STEP/` folder. Use one dedicated store for
the copied project. Keep generation scratch under `models/tmp/`.

This example measures the architectural benefit of authored child boundaries.
It is not a same-script optimization or a replacement for the original
monolithic fixture's preview target. Compare baseline volume, bounds, saved
document/component identities and colors before interpreting timings. The
benchmark must verify that a carrier edit replaces only its child pin and a
root placement edit preserves every child pin.
