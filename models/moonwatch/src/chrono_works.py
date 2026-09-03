"""Chronograph works entry: column wheel, levers, clutch, runners, hammers —
the grey-steel chronograph layer of the caliber-321-lineage movement.

Movement local frame (see `lib/spec.py`): bridge side up, z = 0 at the main
plate's bridge-side surface. Chronograph parts ride z ~ 2.85..4.1 above the
bridges; the hour recorder lives on the dial side (z < -1.5).
"""

from cadgen import build123d as bd
from cadgen import step

from lib import mvt_chrono as C


@step(out="../STEP/chrono_works.step")
def chrono_works():
    return bd.Compound(children=C.build_chrono(), label="chronograph_works")


if __name__ == "__main__":
    chrono_works()
