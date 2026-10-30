"""The camera presets: one table, each name's ``(side, up)`` -- ``side`` the direction from the
target toward the eye, ``up`` the camera's up -- in the document's frame. The stills draw by it
(``occt.py``'s ``direction_of``, which makes ``side`` a unit vector), ``cadgen snapshot --camera``
takes its names (``snapshot.CAMERA_PRESETS``), and a PMI view names one (``cadgen.ap242``'s
``view``). It imports nothing, so the engine reads it without the renderer."""

PRESETS = {
    "front": ((0, -1, 0), (0, 0, 1)), "back": ((0, 1, 0), (0, 0, 1)), "right": ((1, 0, 0), (0, 0, 1)),
    "left": ((-1, 0, 0), (0, 0, 1)), "top": ((0, 0, 1), (0, 1, 0)), "bottom": ((0, 0, -1), (0, 1, 0)),
    "iso": ((1, -1, 0.8), (0, 0, 1)),
}
