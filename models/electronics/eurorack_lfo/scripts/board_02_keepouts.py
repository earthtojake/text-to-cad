"""Step 2b: put each footprint's own keepout zones back over the footprint. Moving a footprint over KiCad's IPC API
(board_02_place.py) moved its pads, lines and texts but left its rule-area zones behind, a little further each move
(KiPy moves a footprint zone's outline by the move in the footprint's frame): the PJ398SM's F.Cu keepout ended up
tens of millimetres from its jack, some off the board. KiCad 11 holds a footprint's own zones in the footprint's
frame, as it holds its pads, so this writes each such zone's outline in the saved board as its library footprint has
it: every point as the library writes it (its y negated on the back, which KiCad's flip mirrors), and KiCad places
it with the footprint. Text edit of the saved board (no KiCad running): run it after board_02_place.py, before
routing.
Run: python3 scripts/board_02_keepouts.py"""
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
BOARD = HERE.parent / "twin_orbit.kicad_pcb"
LIB = HERE.parent / "twin_orbit.pretty"

XY = re.compile(r"\(xy (-?[\d.]+) (-?[\d.]+)\)")


def zones_of(text):
    """Each `(zone ...)` block's span in `text` (balanced parentheses)."""
    out, i = [], 0
    while (i := text.find("(zone", i)) >= 0:
        if text[i + 5] not in "\n\t (":  # (zone_connect ...), a pad's setting
            i += 5
            continue
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
    lib_text = lib.read_text() if lib.exists() else ""
    lib_zones = [lib_text[a:b] for a, b in zones_of(lib_text)]
    if not lib_zones:
        continue
    end = board.find("\n\t(footprint ", m.end())
    end = len(board) if end < 0 else end
    seg = board[m.start():end]
    assert "(transform" in seg[:400], "a footprint placed by (at ...), as KiCad 10 wrote it, holds its zones in the board's frame"
    back = '(layer "B.Cu")' in seg[:200]
    spans = zones_of(seg)
    assert len(spans) == len(lib_zones), (m.group(1), len(spans), len(lib_zones))
    new_seg, k = [], 0
    for (s0, s1), lz in zip(spans, lib_zones):
        it = iter([(x, f"{-float(y):g}" if back else y) for x, y in XY.findall(lz)])
        zone = XY.sub(lambda _m: "(xy %s %s)" % next(it), seg[s0:s1])
        new_seg += [seg[k:s0], zone]
        k = s1
        fixed += 1
    new_seg.append(seg[k:])
    pieces += [board[last:m.start()], "".join(new_seg)]
    last = end
pieces.append(board[last:])
BOARD.write_text("".join(pieces))
print(f"footprint keepout zones put back over their footprints: {fixed}")
