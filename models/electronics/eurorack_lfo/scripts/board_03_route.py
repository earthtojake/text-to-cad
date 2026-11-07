"""Step 3: the tracks and vias, routed by cad.kicad.route as this plan directs. Run: cad run scripts/board_03_route.py

The plan is the agent's, and the router routes only what it names, in its order:

- first the nets that walled others in when they came later (the router names a connection's wall when it
  cannot route one): each LFO's integrator node, its rate wiper, and the -12 V rail;
- then every other net, the shortest first (the sum of each pad's distance to its nearest pad of the net), so
  a short link between neighbouring pins takes its room before a long net crosses it;
- last, the GND ties: a ground pad the pours cannot reach, fenced in by the tracks round it, joined to a ground
  pad nearby by a track of its own: each LFO's square divider (R113.2, R213.2) to its LM13700's ground pin,
  and LFO A's TL074 pin 3 to its pin 6 (DRC found pin 3's patch of pour joined to nothing else; LFO B's pin 3
  the pour reaches).

Every net keeps to the back (a millimetre on the front costs 2.5 there) but +12V, which keeps to the front;
a via costs as much as 2.5 mm of track. Widths and clearances are the netclasses' (the .kicad_pro: 0.25 mm,
0.4 mm for the rails, 0.2 mm apart). GND is the pours' (board_04_pour.py).

The edit first takes every track and via off the board, the stitching's too (board_04_pour.py makes those
again round the new copper), so the board holds the copper of this plan alone whatever it held before, and
running the step again gives the same copper."""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from boardlib import BOARD  # noqa: E402

from cad import kicad_pcb  # noqa: E402
from cad.kicad import route  # noqa: E402

FIRST = ["/LFO A/INTEG", "/LFO B/INTEG", "/LFO A/RATE_W", "/LFO B/RATE_W", "-12V"]
TIES = [("R113.2", "U102.3"), ("R213.2", "U202.3"), ("U101.3", "U101.6")]
BACK = {"B.Cu": 1.0, "F.Cu": 2.5}
FRONT = {"F.Cu": 1.0, "B.Cu": 2.5}

board = kicad_pcb.read(BOARD)
pads: dict[str, list] = {}
for pad in board.pads:
    if pad.net and pad.net != "GND" and not pad.net.startswith("unconnected"):
        pads.setdefault(pad.net, []).append(pad.at)


def span(net: str) -> float:
    """How far a net's pads lie apart: each pad's distance to its nearest pad of the net, summed."""
    at = pads[net]
    return sum(min(math.dist(a, b) for b in at if b is not a) for a in at)


nets = FIRST + sorted((net for net in pads if len(pads[net]) > 1 and net not in FIRST), key=lambda net: (span(net), net))
plan = [{"net": net, "layers": FRONT if net == "+12V" else BACK} for net in nets]
plan += [{"pads": list(tie), "layers": {"B.Cu": 1.0, "F.Cu": 3.0}, "via_cost": 4.0} for tie in TIES]

with kicad_pcb.edit(BOARD) as b:
    copper = list(b.get_tracks()) + list(b.get_vias())
    if copper:
        b.remove_items(copper)
    routed = route(b, plan, via_cost=2.5)
print("\n".join(routed.human_lines()))
if not routed.ok:
    raise SystemExit(1)
