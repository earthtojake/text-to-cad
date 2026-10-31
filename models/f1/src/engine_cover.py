"""F1 part: engine cover -- the carbon shell (`cover_panel.py`) and the parts around it.

Built in car coordinates by `lib/engine_cover.py`; the `engine_bodywork` stage
(`stages.py`) builds it.
"""

from cover_panel import cover_panel
from lib import engine_cover as engine_cover_lib
from lib import surfaces


def engine_cover():
    built = surfaces.group("engine_cover", [
        cover_panel(),
        *engine_cover_lib.build_engine_cover_parts(),
    ])
    return built
