"""F1 part: nose.

Built in car coordinates by `lib/nose.py`; the `front_end` stage
(`stages.py`) builds it.
"""

from lib import nose as nose_lib


def nose():
    built = nose_lib.build_nose()
    return built
