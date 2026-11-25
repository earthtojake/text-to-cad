"""Step 6: tidy what the search left, from KiCad's own DRC report: a via DRC calls dangling (it joins copper on
one layer only: the path crossed over it) is removed, and of two same-net vias too close together (hole_to_hole)
the one no track ends at goes. Then the pours refill.
Run after board_05_islands.py:
    cad kicad_pcb drc twin_orbit.kicad_pcb --json > tmp/drc_before_cleanup.json
    cad run scripts/board_06_cleanup.py tmp/drc_before_cleanup.json"""
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from boardlib import BOARD  # noqa: E402

from cad import kicad_pcb  # noqa: E402

drc = json.loads(Path(sys.argv[1]).read_text())["measurements"]["drc"]
board = kicad_pcb.read(BOARD)
ends = [(t.net, e) for t in board.tracks for e in (t.points[0], t.points[-1])]
drop = set()
for f in drc:
    vias = [i for i in f.get("items", []) if i["description"].startswith("Via ")]
    if f["type"] == "via_dangling":
        drop |= {tuple(i["pos"]) for i in vias}
    elif f["type"] == "hole_to_hole" and len(vias) == 2 and vias[0]["description"] == vias[1]["description"]:
        def ended(i):
            return min(math.dist(e, i["pos"]) for n, e in ends)
        drop.add(tuple(max(vias, key=ended)["pos"]))
with kicad_pcb.edit(BOARD) as b:
    gone = [v for v in b.get_vias() if v.net.name != "GND" and any(
        math.dist((v.position.x / 1e6, v.position.y / 1e6), p) < 0.01 for p in drop)]
    if gone:
        b.remove_items(gone)
    b.refill_zones()
print(f"vias removed {len(gone)} of {len(drop)} flagged")
