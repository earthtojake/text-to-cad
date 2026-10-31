"""F1 part: the carbon engine cover shell, nine tenths of the engine cover's build.

Built in car coordinates by `lib/engine_cover.py`; `engine_cover.py` calls it.
"""

from lib import engine_cover as engine_cover_lib


def cover_panel():
    built = engine_cover_lib.build_cover_panel()
    return built
