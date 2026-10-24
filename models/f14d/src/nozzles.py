"""F-14D system: nozzles — C-D nozzles, petals, seals, actuator rings.

A part of the aircraft: the group `lib/nozzles.py` builds, already on its gear
stance, which `f14d.py` calls in its body. A plain function, not a `@memo`
stage: it holds under a second of kernel work, which the kernel memo replays
whenever the aircraft's body runs.
"""

from lib import nozzles as nozzles_lib


def nozzles():
    group = nozzles_lib.build()
    return group
