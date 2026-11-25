# Lay out a board

Read this to place and route a board from its schematic. A layout of 100 or more nets takes hours: work in
edits ([SKILL.md](../SKILL.md#native-files-are-the-source)), one checked step each, the next reading what
the last saved.

## Contents

- [The method](#the-method)
- [Return current and the reference plane](#return-current-and-the-reference-plane)
- [A property check](#a-property-check)

## The method

1. **Start from the schematic.** Export its netlist and bring the parts and nets onto the board in an
   edit ([schematic](schematic.md#into-the-board-and-back)): `b.import_netlist("tmp/board.net")`,
   `dry_run=True` first to see what it would change.
2. **Rules before copper.** Set the board's minimums and its netclasses from the fab's limits and each
   net's current ([where each lives](board-api.md#design-rules)). Width for current is IPC-2221's
   `I = k * dT^0.44 * A^0.725` (A in mil², k = 0.048 on outer layers, 0.024 inner): size power nets and
   their pours from it, signals at the netclass width.
3. **Place one part or one small functional group at a time** ([placement](placement.md)), fixed parts
   first, each group checked before the next.
4. **Plan the fan-outs before routing.** For each fine-pitch part, decide which way each pin escapes and
   where its vias go, so buses leave it in order and nothing has to cross back. Where tracks still
   tangle, swap pins or gates in the schematic (two inputs of one gate, two units of a quad op-amp, pins
   the datasheet says are interchangeable), export and import the netlist again, and run ERC; never swap
   on the board alone.
5. **Route the nets whose path matters by hand, then direct the router through the rest; never hand the
   board to an autorouter** (no Freerouting). Tracks run octolinear (0°, 45°, 90°).
   - **By hand**, however large the board: power whose current or noise sets its path, and its return (a
     regulator's loops, a high-current feed; a low-current rail can go to the router at its netclass's
     width), analog and reference nodes, crystals, fast nets and differential pairs
     ([below](#return-current-and-the-reference-plane)), each fine-pitch part's fan-out, and any net a
     datasheet's layout notes or the person gives a reason for. Headless KiCad has no interactive
     router: a route is tracks, arcs and vias created in a commit (`commit = b.begin_commit()`,
     `b.create_items([...])`, `b.push_commit(commit)`).
   - **The rest with `route(b, plan)`**, which routes only the connections the plan names, in the plan's
     order, round everything already on the board, and moves and deletes nothing. It is no autorouter:
     with no plan it writes no copper.

     ```python
     from cad import kicad_pcb
     from cad.kicad import route

     with kicad_pcb.edit("board.kicad_pcb") as b:
         routed = route(b, [
             ("U1.3", "C4.1"),                                    # one connection, pad to pad
             {"net": "/SENSE", "layers": ["F.Cu"], "vias": 0},    # this net on the top alone
             "/LED", "/BTN",                                      # whole nets, with the options below
         ], layers={"F.Cu": 1, "B.Cu": 2}, via_cost=2)             # a millimetre on B.Cu costs two on F.Cu
         b.refill_zones()
     print("\n".join(routed.human_lines()))   # each connection; one NOT routed says why and what walls it in
     ```

     An entry or the call gives `layers` (required: a list, or each layer's cost per millimetre), `width`
     and `clearance` (default: the net's netclass's), `vias` (the most the entry may place) and `via_cost`
     (in millimetres of track, default 2). A value the board's rules do not allow is refused by name.
     - Put the connections with the least room first (a pin between two others, a short link) and the
       long nets last. One it cannot route is answered by name, with what walls it in and what to
       change, and the rest go on (`routed.failed`).
     - It routes no differential pair: a net KiCad pairs by name (`D+`/`D-`, `_P`/`_N`) is refused.
     - Leave a poured net out of the plan: a pour is no connection to the router, so it would track
       every pad. Name as a pair only a pad its pour cannot reach, and refill after.
     - A custom rule it does not keep (one with a condition, or a length, skew or track-angle rule) is a
       `route: warning: ...` before routing that names the rule: read DRC after.
     - A connection already joined gets no copper, so the step runs again harmlessly, and a block that
       raises saves nothing, so raising after `route` is a dry run.
     - Route a large board in steps, the nets of one area each, checking after each: a plan whose
       region would not fit the router's memory is narrowed (a warning says so) or refused.

     Say in the handover which nets the router placed.
   - **Then fix by hand** whatever reads badly in DRC and the copper snapshots: a detour, a needless via,
     a track crowding a pad. KiCad's DRC on the saved board, not the plan, says the result is clear.
6. **Refill and check after every routing step.** `b.refill_zones()` in the edit, then DRC (its
   unconnected items are the routing still to do) and a snapshot of each side's copper
   ([views](views.md#board-snapshots)). Two things to look for:
   - A pour's thermal reliefs round dense small pads can neck below the minimum connection width
     (`connection_width`): connect such a pour to its pads solid (the zone's pad connection).
   - KiCad gives copper that overlaps another net's pad, on any layer the copper spans (a through via
     spans them all), that pad's net when it loads, edits or saves the board. A ground stitching via
     through a supply pad becomes a supply via, with any copper polygon joined to it, and DRC reports
     that net's copper, not a short. The edit says each on stderr (`warning: board.kicad_pcb: KiCad saved
     via #via:<uuid> on +9V, not GND: it overlaps pad #J3.1 of +9V; ...`) and lists them as
     `b.net_changes` after the block (`ref`, `was`, `now`, `pad`). Treat each as an error: move the item
     clear of the pad and give it its net again in the next edit. The net alone does not hold while it
     still overlaps.
7. **Check what DRC doesn't.** Write a script of the layout's own properties and run it after every
   step ([below](#a-property-check)).

## Return current and the reference plane

What fast nets and pairs are routed to. Each IC's layout notes come first. Sources: Henry W. Ott,
*Electromagnetic Compatibility Engineering* (Wiley, 2009); Eric Bogatin,
*Signal and Power Integrity — Simplified*, 3rd ed. (Prentice Hall, 2018); TI's
[PCB Design Guidelines for Reduced EMI](https://www.ti.com/lit/pdf/szza009) (SZZA009, 1999) and
[High-Speed Interface Layout Guidelines](https://www.ti.com/lit/pdf/spraar7) (SPRAAR7J, 2023);
IPC-2141A, *Design Guide for High-Speed Controlled Impedance Circuit Boards* (2004).

- **An unbroken reference under every fast track**, since the return runs in the plane beneath it: no
  fast signal over a split, slot or gap. Where a signal via moves the return to another plane, a ground
  via beside it (SPRAAR7J: symmetric, within 200 mil, closer better). Where the reference changes from a
  ground plane to a power plane, or a split cannot be avoided, a stitching capacitor between the two at
  the crossing (SPRAAR7J: 1 µF or less, as close as it can go).
- **The plane kept whole.** The anti-pads round a dense row of vias (a BGA's fan-out, a connector's pins)
  can merge into one slot across it: look at that layer's copper snapshot and space the vias so the webs
  between them survive. A pour necked down to a strip between parts, or an island held by one via, is no
  plane: widen the neck, stitch the island or remove it. On a two-layer board the plane is the other
  side's pour: a track cut into it under a fast signal is short and runs along the signal, not across.
- **Ground pours stitched together** with vias at a pitch well under λ/10 of the highest frequency of
  concern, λ taken in the board's dielectric (λ = c / (f·√εr)): a clock's harmonics, a digital edge's
  bandwidth (about 0.35 / rise time, Bogatin), an RF carrier. At 2.4 GHz on FR-4 (εr about 4.3) λ is some
  60 mm, so well under 6 mm. Stitch an unstitched finger or island of pour at both ends, or delete it.
- **Controlled impedance from the fab's stackup calculator** for the actual stackup, never a width that
  worked elsewhere: the track's width, and the gap to any pour beside it on its own layer, which lowers
  its impedance and so stays constant along the run. Set them in a netclass.
- **A differential pair's width and gap** from the same calculator, as the netclass's `diff_pair_width`
  and `diff_pair_gap` (the `.kicad_pro`). The impedance is the interface's: USB 2.0 90 Ω differential (the
  USB 2.0 Specification allows ±15 %; SPRAAR7J asks 81–99 Ω), Ethernet's MDI 100 Ω ±10 % (TI's
  [Ethernet PHY PCB Design Layout Checklist](https://www.ti.com/lit/pdf/snla387), SNLA387), LVDS 100 Ω
  (TIA/EIA-644-A; TI's [LVDS Owner's Manual](https://www.ti.com/lit/pdf/snla187), 4th ed., SNLA187). The
  PHY's or transceiver's datasheet wins.
- **The two legs together**: parallel at the one gap, symmetric round bends and pads, on one layer, with
  equal via counts placed side by side, and skew within the interface's budget (SPRAAR7J: 50 mil within
  a USB 2.0 pair), tuned with a serpentine near the end where the mismatch arises. `route` routes no pair
  and headless KiCad has no pair router or length tuner: write the pair as two offset copies of one
  centre path, and any tuning bumps as geometry too.

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

# 1. Octolinear: every straight segment runs at a multiple of 45 degrees (arcs excluded). On a board
# whose parts are turned to their place (a ring of LEDs on a round board), measure a part's escapes
# against its own rotation instead.
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

Grow it with the board's own properties as they come up, each measured from `kicad_pcb.read`
([checks](checks.md#read-it)), every threshold from the board's netclasses, its `.kicad_pro` rules and
the datasheets, never a built-in number:

- each IC pin to the part serving it, pad to pad: a capacitor near another capacitor but far from its pin;
- a decoupler the wrong way round: its ground pad nearer the pin than its supply pad;
- a via site beside each small part's ground pad, free of other nets, and a lane out of each pin front,
  straight or at 45°, each sized as [placement](placement.md#keep-every-pad-reachable) says;
- a crystal's two gaps to its pins, and their difference;
- an RF or filter chain, link by link, with each shunt's branch length from the line;
- the ground under each fast net: points along its tracks `inside` a fill of the ground zone on the layer
  that references it (the fills are KiCad's, so refill and save first);
- each pair's skew (the difference of its legs' `track.length`), its legs' via counts, and the gap from
  one leg's points to the other, edge to edge, which stays at the netclass's where the pair runs coupled
  and opens only at the pads.

The script adds to KiCad's DRC and ERC, which stay the rule checks and run every step; it replaces neither.
