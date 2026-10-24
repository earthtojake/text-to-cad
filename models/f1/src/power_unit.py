"""F1 part: power unit.

Built in car coordinates by `lib/power_unit.py`; `f1.py` calls it in the car's body,
a `@memo` stage of its own.
"""

from cadgen import memo

from lib import power_unit as power_unit_lib


@memo
def power_unit():
    built = power_unit_lib.build_power_unit()
    return built
