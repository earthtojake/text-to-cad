# Lay out a board

Place and route a board from its schematic in board scripts (`@kicad_pcb`), one checked step at a time.
A layout of 100 or more nets takes hours, so work in steps: each board script saves the board when its
function returns, and the next step reads what the last one saved.

## The method

1. **Start from the schematic.** Export its netlist with KiCad's command line (`kicad-cli sch export
   netlist -o tmp/board.net board.kicad_sch`; `kicode.executable()` is that command line, run with
   `kicode.environment()`), then bring the parts and nets onto the board in a board script:
   `b.import_netlist("tmp/board.net")` (`dry_run=True` first to see what it would change). The
   schematic, not the footprints, says what connects to what.
2. **Rules before copper.** Set the clearances, netclasses and track widths from the fab's limits and
   each net's current (`b.get_design_rules()`, `b.set_design_rules(...)`, the project's
   `.kicad_pro`). Width for current: IPC-2221, `I = k * dT^0.44 * A^0.725` (A in mil², k = 0.048 on
   outer layers, 0.024 inner); size power nets and their pours from it, signals at the netclass width.
3. **Place one part or one small functional group at a time.** Fixed parts first (connectors,
   mounting holes, anything the enclosure locates), then each IC with its own group: decoupling at its
   power pins, crystal at its clock pins, the passives of one function together. Move parts with
   `b.update_items(...)` and `b.flip_items(...)` in one script per group, then look:
   `cad kicad_pcb snapshot board.kicad_pcb tmp/placement.png --display placement` shows the pads and
   every unrouted connection (the ratsnest). Short, uncrossed ratsnest lines mean the group is placed
   well.
4. **Plan the fan-outs before routing.** For each fine-pitch part, decide which way each pin escapes
   and where its vias go, so buses leave it in order and nothing has to cross back.
5. **Route by hand, not with an autorouter** (no Freerouting). Tracks run octolinear (0°, 45°, 90°).
   Run a bus as parallel tracks at one even pitch. Take the shortest path a signal can, with no
   detours. Give power the width or pour its current needs. Routes are written as geometry: tracks,
   arcs and vias in a commit (`b.begin_commit()`, `b.create_items([...])`, `b.push_commit(...)`);
   headless KiCad has no interactive router.
6. **Refill and check after every routing step.** `b.refill_zones()`, save, then
   `cad kicad_pcb check board.kicad_pcb`: its unconnected items are the routing still to do, and its
   errors are what to fix now. Moving a part after routing is fine: reroute what it touched.
7. **Check what DRC doesn't.** Write a script of the layout's own properties and run it after every
   step (below). Fix what it finds the same way.

## A property check

Save it beside the board and run it with `cad run layout_checks.py board.kicad_pcb`. It reads the saved
board and prints what breaks the method: segments off the 45° grid, two-pad nets much longer than the
straight line between their pads, and tracks too narrow for their current.

```python
import math
import sys
from collections import defaultdict

from cad.kicad_pcb import read_board

board = read_board(sys.argv[1] if len(sys.argv) > 1 else "board.kicad_pcb")

# 1. Octolinear: every straight segment runs at a multiple of 45 degrees (arcs excluded).
off_angle = []
for track in board.tracks:
    if track.arc:
        continue
    for (x0, y0), (x1, y1) in zip(track.points, track.points[1:]):
        angle = math.degrees(math.atan2(y1 - y0, x1 - x0)) % 45
        if min(angle, 45 - angle) > 0.5:
            off_angle.append((track.net, track.layer, (round(x0, 2), round(y0, 2))))
print(f"{len(off_angle)} segment(s) off 45-degree steps", off_angle[:5])

# 2. Detours: a two-pad net's copper length against the straight line between its pads.
length = defaultdict(float)
for track in board.tracks:
    length[track.net] += sum(math.dist(a, b) for a, b in zip(track.points, track.points[1:]))
for net in board.nets:
    straight = math.dist(net.pads[0].at, net.pads[1].at) if len(net.pads) == 2 else 0
    if straight > 1 and length[net.name]:  # pads 1 mm or more apart
        ratio = length[net.name] / straight
        if ratio > 1.6:
            print(f"detour: {net.name} is {ratio:.1f}x its straight line")

# 3. Width for current (IPC-2221, outer layers, 10 C rise, 35 um copper): I = 0.048 * dT^0.44 * A^0.725.
def amps(width_mm, rise_c=10.0, copper_um=35.0):
    area_mil2 = (width_mm / 0.0254) * (copper_um / 25.4)
    return 0.048 * rise_c ** 0.44 * area_mil2 ** 0.725

needs = {"+5V": 1.0, "GND": 1.0}  # amps, from the circuit: fill in per net
for track in board.tracks:
    if track.net in needs and amps(track.width) < needs[track.net]:
        print(f"narrow: {track.net} {track.width} mm carries {amps(track.width):.2f} A < {needs[track.net]} A")
```

Grow it with the board's own rules as they come up: even pitch within each bus, differential pairs
matched in length and gap, the ground plane unbroken under fast signals, each decoupling capacitor's
distance to its power pin. Thresholds come from the circuit and datasheets, not from a universal number.
