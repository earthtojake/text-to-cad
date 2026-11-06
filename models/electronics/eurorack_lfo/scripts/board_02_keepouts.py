"""Step 2b: put each footprint's own keepout zones back over the footprint. Moving a footprint over KiCad's IPC API
(board_02_place.py) moved its pads, lines and texts but left its rule-area zones behind, a little further each move
(KiPy moves a footprint zone's outline by the move in the footprint's frame): the PJ398SM's F.Cu keepout ended up tens of millimetres from its jack, some off the board. This rewrites
each such zone's outline in the saved board from the library footprint, through the footprint's place and rotation.
Text edit of the saved board (no KiCad running): run it after board_02_place.py, before routing.
Run: python3 scripts/board_02_keepouts.py"""
import math
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BOARD = HERE.parent / "twin_orbit.kicad_pcb"
LIB = HERE.parent / "twin_orbit.pretty"

XY = re.compile(r"\(xy (-?[\d.]+) (-?[\d.]+)\)")


def zones_of(text):
    """Each `(zone ...)` block's span in `text` (balanced parentheses)."""
    out, i = [], 0
    while (i := text.find("(zone", i)) >= 0:
        depth, j = 0, i
        while True:
            depth += {"(": 1, ")": -1}.get(text[j], 0)
            j += 1
            if depth == 0:
                break
        out.append((i, j))
        i = j
    return out


board = BOARD.read_text()
fixed = 0
pieces, last = [], 0
for m in re.finditer(r'\n\t\(footprint "twin_orbit:([^"]+)"', board):
    lib = LIB / f"{m.group(1)}.kicad_mod"
    lib_zones = [lib.read_text()[a:b] for a, b in zones_of(lib.read_text())] if lib.exists() else []
    if not lib_zones:
        continue
    end = board.find("\n\t(footprint ", m.end())
    end = len(board) if end < 0 else end
    seg = board[m.start():end]
    assert '(layer "F.Cu")' in seg[:200], "a back-side footprint would also need its x mirrored"
    tx, ty = map(float, re.search(r"\(translate (-?[\d.]+) (-?[\d.]+)\)", seg).groups())
    rot = re.search(r"\(rotate (-?[\d.]+)\)", seg)
    a = math.radians(float(rot.group(1)) if rot else 0.0)
    spans = zones_of(seg)
    assert len(spans) == len(lib_zones), (m.group(1), len(spans), len(lib_zones))
    new_seg, k = [], 0
    for (s0, s1), lz in zip(spans, lib_zones):
        pts = XY.findall(lz)
        # KiCad's y points down and its rotation is counter-clockwise on screen
        world = [(tx + float(x) * math.cos(a) + float(y) * math.sin(a), ty - float(x) * math.sin(a) + float(y) * math.cos(a)) for x, y in pts]
        it = iter(world)
        zone = XY.sub(lambda _m: "(xy %.6f %.6f)" % next(it), seg[s0:s1])
        new_seg += [seg[k:s0], zone]
        k = s1
        fixed += 1
    new_seg.append(seg[k:])
    pieces += [board[last:m.start()], "".join(new_seg)]
    last = end
pieces.append(board[last:])
BOARD.write_text("".join(pieces))
print(f"footprint keepout zones put back over their footprints: {fixed}")
