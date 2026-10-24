"""The meshes ../lyra.urdf references: a 3MF of each link model, in the link's own frame.

Run it after changing a link, before loading the URDF; the URDF scales each mesh by 0.001
(a 3MF is in millimetres).
"""
from pathlib import Path

from cadgen import export

from lyra import (
    index_distal,
    index_middle,
    index_proximal,
    middle_distal,
    middle_middle,
    middle_proximal,
    palm,
    pinky_distal,
    pinky_middle,
    pinky_proximal,
    ring_distal,
    ring_middle,
    ring_proximal,
    thumb_base,
    thumb_distal,
    thumb_metacarpal,
    thumb_proximal,
)

ROOT = Path(__file__).resolve().parent.parent      # models/lyra
LINKS = (palm, index_proximal, index_middle, index_distal, middle_proximal, middle_middle,
         middle_distal, ring_proximal, ring_middle, ring_distal, pinky_proximal, pinky_middle,
         pinky_distal, thumb_base, thumb_metacarpal, thumb_proximal, thumb_distal)

if __name__ == "__main__":
    for link in LINKS:
        export(link, ROOT / "3MF" / f"{link.__name__}.3mf")
