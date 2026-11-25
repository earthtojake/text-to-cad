"""Layout step 4: the silkscreen. Reference designators where they can be read (the ICs, the
connector, the buttons, the keys and LEDs); the 0402 passives' references hidden (they are on the
fab drawing and in the placement file; at 0.4 mm pitch there is no room to print them legibly),
and labels for what a person handles: BOOT, RESET, the SWD pads, the board's name.
Run: cad run scripts/step4_silk.py"""
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
os.chdir(HERE.parent)
from cad import kicad_pcb  # noqa: E402
from kicode.board_types import BoardText  # noqa: E402
from kicode.geometry import Vector2  # noqa: E402
from kicode.proto.board.board_types_pb2 import BoardLayer  # noqa: E402
from kicode.util.units import from_mm  # noqa: E402

BOARD = "macropad.kicad_pcb"
# reference positions (board mm, as seen from the top); None hides it
from board_common import key_xy  # noqa: E402

SHOW = {"U1": (104.6, 69.0), "U2": (99.5, 53.4), "U3": (77.6, 52.0), "U4": (86.0, 59.6), "U5": (72.2, 82.0),
        "J1": (90.0, 49.7), "F1": (82.0, 51.7)}
SHOW.update({f"SW{i + 1}": (key_xy(i)[0] + 6.6, key_xy(i)[1] + 8.4) for i in range(9)})
LABELS = [("BOOT", (114.0, 53.1)), ("RESET", (89.4, 67.0)), ("SWCLK", (98.1, 75.1)), ("SWDIO", (95.5, 76.3)),
          ("GND", (93.0, 75.1)), ("3V3", (84.0, 66.6)), ("NINE  rev A", (83.0, 68.6)),
          ("texttocad.dev", (83.0, 70.4))]

with kicad_pcb.edit(BOARD) as b:
    changed = []
    for f in b.get_footprints():
        ref = f.reference_field.text.value
        want_visible = ref in SHOW
        fld = f.reference_field
        if ref in SHOW:
            pos = Vector2.from_xy_mm(*SHOW[ref])
            if (fld.text.position.x, fld.text.position.y) != (pos.x, pos.y):
                fld.text.position = pos
                f.reference_field = fld
                changed.append(f)
        if fld.visible != want_visible:
            fld.visible = want_visible
            f.reference_field = fld
            if f not in changed:
                changed.append(f)
    if changed:
        b.update_items(changed)
    have = {t.value: t for t in b.get_text() if isinstance(t, BoardText)}
    known = {text for text, _ in LABELS}
    stale = [t for v_, t in have.items() if v_ not in known and t.layer == BoardLayer.BL_B_SilkS]
    if stale:
        b.remove_items(stale)
    new, moved = [], []
    for text, (x, y) in LABELS:
        if text in have:
            t = have[text]
            pos = Vector2.from_xy_mm(x, y)
            if (t.position.x, t.position.y) != (pos.x, pos.y):
                t.position = pos
                moved.append(t)
            continue
        t = BoardText()
        t.value, t.position, t.layer = text, Vector2.from_xy_mm(x, y), BoardLayer.BL_B_SilkS
        a = t.attributes
        a.size = Vector2.from_xy_mm(1.0, 1.0)
        a.stroke_width = from_mm(0.15)
        a.mirrored = True
        t.attributes = a
        new.append(t)
    if new:
        b.create_items(new)
    if moved:
        b.update_items(moved)
print("silkscreen set")
