"""F1 part: rear suspension.

Built in car coordinates by `lib/suspension.py`; `f1.py` calls it in the car's body,
a `@memo` stage of its own.
"""

from cadgen import memo

from lib import suspension as suspension_lib


@memo
def suspension_rear():
    built = suspension_lib.build_suspension_rear()
    return built
