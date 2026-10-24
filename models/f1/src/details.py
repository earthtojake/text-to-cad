"""F1 part: details.

Built in car coordinates by `lib/details.py`; `f1.py` calls it in the car's body,
a `@memo` stage of its own.
"""

from cadgen import memo

from lib import details as details_lib


@memo
def details():
    built = details_lib.build_details()
    return built
