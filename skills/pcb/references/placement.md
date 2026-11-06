# Place the parts

Placement settles most of what routing can do. A part in the wrong place makes a loop large, a track
long or a pad unreachable, and no track fixes that afterwards. This is [layout](layout.md)'s third
step in full.

## Why parts go where they go

Every rule below follows from one of these. Where a rule and its reason disagree on a board, follow
the reason.

- **Current goes round a loop.** It leaves on one conductor and comes back on another, usually
  ground. The loop's area sets what it radiates and picks up; its length sets its inductance. A
  decoupling capacitor works only when the loop through its pads and the IC's supply and ground pins
  is small. A switching regulator has one loop whose current switches in nanoseconds, and its
  datasheet's layout section names it.
- **Connections differ in how much length they bear.** A slow GPIO can cross the board. A decoupler,
  a switch node, a crystal pin, an RF node or the filter on a sensitive input cannot. Rank the
  connections before placing anything, and give the space at the pins to the least tolerant.
- **Noisy and sensitive circuits are kept apart.** Switch nodes, clocks and buses are noisy; crystals,
  analog inputs, references and RF are sensitive. Give them distance or a barrier, and route nothing
  sensitive past a noisy part.
- **The mechanics place some parts.** Connectors, buttons, LEDs, mounting holes, an antenna and its
  keepout, anything the enclosure locates: these go first and are locked.
- **Every pad stays reachable.** A track that leaves the area can bend, change layer or take another
  edge; a decoupler's pad or a crystal's cannot. A pad no track can reach is a defect, and a long
  escape is only a cost.
- **The board is built and tested.** Courtyards apart, parts on one side where they fit, polarised
  parts turned one way, test points a probe can reach, hot parts with copper and air round them.

## What each part needs

Read the schematic first (`kicad_sch.read`): note each part's job and the pin or part it serves.
Where a pin is on the package comes from the board's pads (`board.part("U1").pads`), never from how
the sheet draws the symbol.

| Part | Its place must give it |
| --- | --- |
| Decoupling capacitor | the pin it serves, supply pad toward that pin, the vendor's ground return; the smallest value nearest unless the vendor orders them otherwise |
| Bulk capacitor | near the pins it feeds, behind the small capacitor it backs, on the same supply track |
| Switching regulator | the datasheet's hot loop as small as it goes (a buck's input capacitor across VIN and ground); a short switch node; the output capacitor at the regulated pin with the inductor's output pad beside it |
| Crystal or resonator | both pads close to their two pins, at nearly equal distances, nothing routed between |
| RF matching network | the series parts in schematic order on one line from the RF pin to the port; each shunt's signal pad on that line in a gap between series parts, its ground pad turned away |
| Input filter | the capacitor at the pin it filters, its series resistor on the far side from the IC |
| Ferrite between supplies | between the two domains' pins or capacitors |
| Connector, button, LED | where the enclosure and the person need it |
| Termination, pull-up | a series termination at the driving pin; a pull-up on a slow net anywhere along it, unless the datasheet says where |

Use the parts the schematic gives and add none: no ferrite, capacitor or via pattern that neither
the schematic nor the vendor's reference design has. With a capacitor for every supply pin, give each
pin its own, on whichever side of the package it is; with fewer, neighbouring pins share as the
vendor groups them. A datasheet's layout notes (a ground pad tied to one pin, a via to one layer only,
a length limit) are requirements. Where the documents leave a choice open, make it, say it is your
inference, and go on.

## Orient each IC

After the fixed parts, choose each large IC's rotation and position by where its pins must go: pins
to a fixed part (a connector, the RF port) face it; pins that leave the area face the edge they leave
by; pins with local parts face room for them. Score all four rotations against those and keep the
best. The distance to a fixed part is the length of what sits between: an RF pin is its matching
network's length from the port, a connector's pins their protection parts' length. When the network
does not fit, move the IC rather than stretch the links between its parts. When the IC cannot move,
keep the network together, take the extra length in the port's track, and say so.

## Place in order of tolerance

The parts that most need a short connection go first, while the space at the pins is free:

1. What the vendor fixes, and the high-frequency paths: an RF network, a regulator's hot loop, a
   ground tied to one pin.
2. Decoupling and filter capacitors, each at its own pin, even when a neighbour's escape then needs a
   bend or a via.
3. Crystals and their load capacitors.
4. Bulk capacitors, series resistors, ferrites, pull-ups: near what they serve, clear of the above.
5. Everything that tolerates distance.

When a part that must be close cannot reach its pin, move what holds the space and tolerates distance
(a bulk capacitor, a resistor, a crystal, the IC itself), never the close part. Parts competing for
one region (round a regulator, at neighbouring pins) are placed as one group, and the orders compared.

Where it most often goes wrong:

- **Parts at neighbouring pins.** Two parts side by side, each in line with its pin, fit only when
  their courtyard widths add up to no more than twice the pin pitch. Stagger them, push one out by
  its own length, or swap which pin gets the nearer place.
- **A switch pin beside the regulated pin,** usual where the DC/DC converter is inside the IC. The
  inductor joins the two, and the output capacitor belongs at the regulated pin. Laid along the pin
  row, the inductor keeps both pads near their pins; turned across it, it pushes its output pad, and
  the capacitor behind that, away.
- **A matching network.** A shunt set beside a series pad needs a branch track back to the line, and
  at RF that branch adds inductance and capacitance the part values never allowed for. A ground the
  vendor ties to one pin or one layer still wins: put the ground pad there, bring the signal pad as
  near the line as the courtyards let it, and report the branch. Count the gaps before setting the
  IC's distance from the port. Placement settles the geometry only; the match itself needs the
  vendor's values or a measurement.
- **A two-pad part across two pins** (a crystal, a flying capacitor). Each pin's track adds to its
  load capacitance, so the two gaps should be nearly equal. Rotate, mirror or slide the part to even
  them; on a four-pad crystal the signal pads are diagonal, so measure all four rotations. Trade a
  little length for balance, not much.
- **A row of capacitors with a part beyond it.** Its tracks need a gap through the row: leave one
  while placing the row.

## Keep every pad reachable

Every size here comes from the board's own rules (the `.kicad_pro`'s netclasses and constraints, the
`.kicad_dru`), never from habit:

- **A channel** wherever a track passes between parts: a track's width and a clearance each side.
- **A clear front** before each fine-pitch row, deep enough for its tracks to spread before they turn.
  Put nothing in front of a pin it does not connect to unless that pin can leave at 45°.
- **A via site** beside each ground pad of a decoupler, crystal or shunt that returns to a plane: a
  via's diameter plus its clearance to other nets. Where the vendor ties that pad elsewhere, follow
  the vendor and add no via.
- **Courtyards apart.** Touching passes DRC; leave a gap where a track or via must pass between.
- **In line with the pin, not across the row,** so both neighbours keep a straight way out.

Compute every position from pad coordinates (`pad.at` and `part.outline` from `kicad_pcb.read`),
never by eye from a snapshot: a guess is easily a few tenths of a millimetre out, half a small part.

## Move, then check

Move each group in one `kicad_pcb.edit` block: position and rotation with `b.update_items(...)` on the
footprints read back from the board, set to where each belongs (never moved by an offset, so the block
can run again), and a change of side with `b.flip_items(...)`, KiCad's own flip, which mirrors pads,
courtyard and graphics to the other side, only for a part not on that side already. Never set a
footprint's layer by hand.

**On the back** a part keeps KiCad's orientation: its pads are its library footprint's mirrored top to
bottom (each local y negated), then turned by its orientation. So 0 on the back is the library
footprint upside down (a SOT-23's pin 1 at the bottom left), and `flip_items` leaves a part that was at
θ on the front at 180° − θ, mirrored left to right as seen from the front. For a back part that reads
as the front part at θ seen through the board, flip it and set 180° − θ; read the pads back to check.

**A footprint's own zones** (a module's antenna keep-out, a jack's) are moved twice by KiPy's position
setter: KiCad hands their outlines over in the footprint's frame, and KiPy shifts them by the move as if
they were in the board's, so the keep-out lands off the part and keeps nothing out, DRC silent. Keep each
outline as it was across the move; KiCad then places it with the footprint (a turn and a flip are right):

```python
from copy import deepcopy
from kicode.board_types import Zone
from kicode.geometry import Angle, Vector2

def place(footprint, x_mm, y_mm, degrees):
    zones = [item for item in footprint.definition.items if isinstance(item, Zone)]
    outlines = [deepcopy(zone.proto.outline) for zone in zones]
    footprint.position = Vector2.from_xy_mm(x_mm, y_mm)
    footprint.orientation = Angle.from_degrees(degrees)
    for zone, outline in zip(zones, outlines):
        zone.proto.outline.CopyFrom(outline)
```

KiPy also turns a footprint's pads and drawings itself, truncating to the nanometre: after a quarter or
half turn some are 1 nm off (`7.499999`), and DRC warns `lib_footprint_mismatch` ("does not match copy in
library") on a footprint nobody changed. On a turned part that warning is this rounding; KiCad's flip and
a move are exact.

After each group:

- **DRC.** `cad kicad_pcb drc board.kicad_pcb`: fix every courtyard, clearance and edge error.
  Unconnected items are expected until routing.
- **Your own measurements.** A check script reading the saved board measures each pin to its part,
  each ground pad's via site and each crystal's gaps ([layout's list](layout.md#a-property-check)).
- **The ratsnest.** `cad kicad_pcb snapshot board.kicad_pcb tmp/placement.png --display placement`.
  Short, uncrossed lines mean the group sits well. A line that must cross a pad row, or ends at a pad
  walled in by parts, is a lane still to open. DRC's unconnected items list every connection still
  to route; each needs a way through.

When a short critical connection and an escaping track want the same space, keep the critical part
and say what the escape needs instead (a bend, a via, another edge). Before moving a critical part
off its pin, try at least two alternatives (another rotation, the other side of a neighbour, swapping
two parts at adjacent pins, moving what holds the space), measure each, and keep the one with the
shortest worst gap that still leaves every pad a way out. When one side of an IC cannot hold its
parts, move or rotate the IC. Report what could not be satisfied, and why.

Placement is iterative: routing shows where lanes run short, so expect to move parts again and to
reroute what a move touched. A routed part moved leaves its tracks and vias where they were, and those
now cross other pads (`shorting_items` at the next DRC): delete its nets' copper round it before the
move, and route them again after.

## What this establishes

Geometry: distances, order and lanes. It does not tune an RF match, prove a regulator stable or a
clock within its budget, or route the board. A clean placement is not a finished route, and a hard
one is not proof that the board cannot be routed. Where the datasheet or the vendor's reference
layout disagrees with this method, follow them.
