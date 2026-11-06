# Lay out a board

Place and route a board from its schematic in edits (`with kicad_pcb.edit("board.kicad_pcb") as b:`), one
checked step at a time. A layout of 100 or more nets takes hours, so work in steps: each edit saves the
board at its block's end, and the next step reads what the last one saved. Each states the board it wants
("U1 at (10, 20)", "VBUS 0.8 mm"), so running a step again is harmless.

## The method

1. **Start from the schematic.** Export its netlist (`cad kicad_sch export board.kicad_sch --to netlist
   -o tmp`, or `kicad_sch.export("board.kicad_sch", "netlist", "tmp")` in the script), then bring the
   parts and nets onto the board in an edit:
   `b.import_netlist("tmp/board.net")` (`dry_run=True` first to see what it would change). The
   schematic, not the footprints, says what connects to what.
2. **Rules before copper.** Set the clearances, netclasses and track widths from the fab's limits and
   each net's current (`b.get_design_rules()`, `b.set_design_rules(...)`, the project's
   `.kicad_pro`). Width for current: IPC-2221, `I = k * dT^0.44 * A^0.725` (A in mil², k = 0.048 on
   outer layers, 0.024 inner); size power nets and their pours from it, signals at the netclass width.
3. **Place one part or one small functional group at a time,** as [placement](placement.md) sets
   out: fixed parts first (connectors, mounting holes, anything the enclosure locates), then each IC
   with its own group, in order of how little distance each connection tolerates. Draw the outline
   with rounded or chamfered corners, as the person confirms. A horizontal connector sits at a board
   edge with its mating face out over it; check it in a GLB export opened in the viewer (`cad kicad_pcb
   export board.kicad_pcb --to glb -o tmp/glb`). Keep the parts on one side, and ask the person before
   putting any on the other. Move parts with `b.update_items(...)` and `b.flip_items(...)` in one
   script per group, then look: `cad kicad_pcb snapshot board.kicad_pcb tmp/placement.png --display
   placement` shows the pads and every unrouted connection (the ratsnest). Short, uncrossed ratsnest
   lines mean the group is placed well. Placement is iterative: routing will move parts again.
4. **Plan the fan-outs before routing.** For each fine-pitch part, decide which way each pin escapes
   and where its vias go, so buses leave it in order and nothing has to cross back. Where tracks
   still tangle, swap pins or gates in the schematic (two inputs of one gate, two units of a quad
   op-amp, pins the datasheet says are interchangeable), export and import the netlist again, and run
   ERC; never swap on the board alone.
5. **Route by hand, not with an autorouter** (no Freerouting). Tracks run octolinear (0°, 45°, 90°).
   Run a bus as parallel tracks at one even pitch. Take the shortest path a signal can, with no
   detours. Give power the width or pour its current needs. Routes are written as geometry: tracks,
   arcs and vias in a commit (`b.begin_commit()`, `b.create_items([...])`, `b.push_commit(...)`);
   headless KiCad has no interactive router. Fast nets and differential pairs follow the next section.
6. **Refill and check after every routing step.** `b.refill_zones()`, save, then
   `cad kicad_pcb drc board.kicad_pcb`: its unconnected items are the routing still to do, and its
   errors are what to fix now. Moving a part after routing is fine: reroute what it touched.
7. **Check what DRC doesn't.** Write a script of the layout's own properties and run it after every
   step (below). Fix what it finds the same way.

## Return current and the reference plane

Sources: Henry W. Ott, *Electromagnetic Compatibility Engineering* (Wiley, 2009); Eric Bogatin,
*Signal and Power Integrity — Simplified*, 3rd ed. (Prentice Hall, 2018); TI's
[PCB Design Guidelines for Reduced EMI](https://www.ti.com/lit/pdf/szza009) (SZZA009, 1999) and
[High-Speed Interface Layout Guidelines](https://www.ti.com/lit/pdf/spraar7) (SPRAAR7J, 2023);
IPC-2141A, *Design Guide for High-Speed Controlled Impedance Circuit Boards* (2004). Each IC's
layout notes come first.

**The return runs under the track.** A fast edge's return current takes the path of least
inductance, which is the plane directly beneath its track, so the loop stays small. Route no fast
signal over a split, slot or gap in its reference plane: the return detours round it and the loop
becomes an antenna. A signal via that changes layer moves its return to another plane: put a ground
via beside it (SPRAAR7J: symmetric, within 200 mil, closer better). Where the reference changes from
a ground plane to a power plane, or a split cannot be avoided, a stitching capacitor between the two
planes at the crossing carries the return (SPRAAR7J: 1 µF or less, as close as it can go).

**Keep the plane whole.** The anti-pads round a dense row of vias (a BGA's fan-out, a connector's
pins) can merge into one slot across the plane: look at that layer's copper snapshot and space the
vias so the webs between them survive. A pour necked down to a strip between parts, or an island
held by one via, is no plane: widen the neck, stitch the island or remove it. On a two-layer board,
keep the bottom an unbroken ground under the fast signals on top; a bottom-layer track there should
be short and run along the signals, not across them.

**A cheap check:** a ground fill under every fast net's track, on the layer that references it. The
fills are KiCad's, so refill and save first (step 6):

```python
import math
import sys

from cad import kicad_pcb
from cad.kicad_pcb import inside

board = kicad_pcb.read(sys.argv[1] if len(sys.argv) > 1 else "board.kicad_pcb")
fast = {"/USB_D+", "/USB_D-", "/CLK"}       # the fast nets, from the circuit
under = {"F.Cu": "In1.Cu", "B.Cu": "In2.Cu"}  # each signal layer's reference plane, from the stackup
for track in board.tracks:
    if track.net not in fast or track.layer not in under:
        continue
    fills = [fill for zone in board.zones if zone.net == "GND" and zone.layer == under[track.layer]
             for fill in zone.fills]
    for (x0, y0), (x1, y1) in zip(track.points, track.points[1:]):
        steps = max(1, math.ceil(math.dist((x0, y0), (x1, y1)) / 0.25))  # every 0.25 mm
        for i in range(steps + 1):
            point = (x0 + (x1 - x0) * i / steps, y0 + (y1 - y0) * i / steps)
            if not any(inside(point, fill) for fill in fills):
                print(f"no ground under {track.net} at {point[0]:.2f}, {point[1]:.2f}")
                break
```

**Stitching.** Tie the ground pours of every layer together with vias at a pitch well under λ/10 of
the highest frequency of concern, λ taken in the board's dielectric (λ = c / (f·√εr)): a clock's
harmonics, a digital edge's bandwidth (about 0.35 / rise time, Bogatin), an RF carrier. At 2.4 GHz
on FR-4 (εr about 4.3) λ is some 60 mm, so well under 6 mm. Fence the board's edges and each side of
an RF line with a row of vias. Remove dead copper: an unstitched finger or island of pour resonates
and couples high-frequency noise; stitch it to ground at both ends or delete it.

**Coplanar ground changes impedance.** A pour beside a track on its own layer lowers the track's
impedance, more as the gap narrows. Size each controlled-impedance track (and its pour gap, kept
constant along the run) from the fab's stackup calculator for the actual stackup, not from a width
that worked elsewhere, and set it in a netclass.

### Differential pairs

- **Width and gap from the stackup,** from the fab's calculator for the pair's impedance, set as the
  netclass's pair width and gap (`diff_pair_width`, `diff_pair_gap` in the `.kicad_pro`). The
  impedance is the interface's: USB 2.0 90 Ω differential (the USB 2.0 Specification allows ±15 %;
  SPRAAR7J asks 81–99 Ω), Ethernet's MDI 100 Ω ±10 % (TI's
  [Ethernet PHY PCB Design Layout Checklist](https://www.ti.com/lit/pdf/snla387), SNLA387), LVDS
  100 Ω (TIA/EIA-644-A; TI's [LVDS Owner's Manual](https://www.ti.com/lit/pdf/snla187), 4th ed.,
  SNLA187). The PHY's or transceiver's datasheet wins.
- **The two legs together,** parallel at the one gap, symmetric round bends and pads, on one layer
  over an unbroken reference.
- **Skew within the interface's budget** (SPRAAR7J: 50 mil within a USB 2.0 pair), tuned with a
  serpentine near the end where the mismatch arises, not at the far end.
- **Equal via counts** on both legs, the vias placed side by side.
- **The script draws both legs.** Headless KiCad has no interactive router or length tuner: route the
  pair as two offset copies of one centre path, and any tuning bumps as geometry too.

Check each pair from the saved board, appended to the script above: its length difference, its via
counts, and the gap along the run.

```python
def gap(point, tracks):
    """Edge-to-edge distance from a point on one leg's centreline to the other leg."""
    def to_segment(p, a, b):
        dx, dy = b[0] - a[0], b[1] - a[1]
        t = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / ((dx * dx + dy * dy) or 1)))
        return math.dist(p, (a[0] + t * dx, a[1] + t * dy))
    return min(to_segment(point, a, b) - t.width for t in tracks for a, b in zip(t.points, t.points[1:]))

for p, n in [("/USB_D+", "/USB_D-")]:          # the pairs, from the schematic's names
    pos, neg = board.net(p), board.net(n)
    skew = abs(sum(t.length for t in pos.tracks) - sum(t.length for t in neg.tracks))
    gaps = [gap(pt, neg.tracks) for t in pos.tracks for pt in t.points]
    print(f"{p}/{n}: skew {skew:.3f} mm, vias {len(pos.vias)}/{len(neg.vias)}, "
          f"gap {min(gaps):.3f}..{max(gaps):.3f} mm")
```

Measured where the pair runs coupled, the gap should stay at the netclass's; it opens at the pads
where the legs split.

## A property check

Save it beside the board and run it with `cad run layout_checks.py board.kicad_pcb`. It reads the saved
board and prints what breaks the method: segments off the 45° grid, two-pad nets much longer than the
straight line between their pads, and tracks too narrow for their current.

```python
import math
import sys
from collections import defaultdict

from cad import kicad_pcb

board = kicad_pcb.read(sys.argv[1] if len(sys.argv) > 1 else "board.kicad_pcb")

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

Grow it with the board's own properties as they come up, each measured from `kicad_pcb.read`, every
threshold from the board's netclasses and `.kicad_pro` design rules and the datasheets, never a
built-in number:

- each IC pin to the part serving it, pad to pad: a capacitor near another capacitor but far from its pin;
- a decoupler the wrong way round: its ground pad nearer the pin than its supply pad;
- a via site beside each small part's ground pad: a via's diameter plus clearance, free of other nets;
- a crystal's two gaps to its pins, and their difference;
- a blocked pin front: no lane a track wide plus two clearances straight out of a pin, or at 45°;
- an RF or filter chain, link by link, with each shunt's branch length from the line;
- the ground under each fast net and each pair's skew and gap ([above](#return-current-and-the-reference-plane)).

These complement KiCad's DRC and ERC; they do not replace them. DRC and ERC stay the authoritative
rule checks (clearances, unconnected items, electrical rules) and still run every step; the script
measures the design properties KiCad does not.
