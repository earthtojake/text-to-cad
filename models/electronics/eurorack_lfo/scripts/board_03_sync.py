"""Put the board's tracks and vias back to scripts/routes.json (what assist_route.py last wrote), without searching
again. GND stitching vias are left alone. Run: cad run scripts/board_03_sync.py"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from boardlib import BOARD  # noqa: E402
from routelib import Routes, sync  # noqa: E402

from cad import kicad_pcb  # noqa: E402

data = json.loads((Path(__file__).parent / "routes.json").read_text())
routes = Routes()
routes.tracks = [(n, layer, w, tuple(a), tuple(b)) for n, layer, w, a, b in data["tracks"]]
routes.vias = [(n, tuple(p)) for n, p in data["vias"]]
with kicad_pcb.edit(BOARD) as b:
    print("sync (tracks+, vias+, tracks-, vias-):", sync(b, routes))
