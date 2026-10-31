"""F1 part: airbox.

Built in car coordinates by `lib/engine_cover.py`; the `engine_bodywork` stage
(`stages.py`) builds it.
"""

from lib import engine_cover as engine_cover_lib


def airbox():
    built = engine_cover_lib.build_airbox()
    return built
