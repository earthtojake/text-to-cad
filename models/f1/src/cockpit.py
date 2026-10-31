"""F1 part: cockpit furniture.

Built in car coordinates by `lib/cockpit.py`; the `survival_cell` stage
(`stages.py`) builds it.
"""

from lib import cockpit as cockpit_lib


def cockpit():
    built = cockpit_lib.build_cockpit()
    return built
