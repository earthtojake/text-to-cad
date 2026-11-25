# Place the parts

Read this for [layout](layout.md)'s third step: where each part goes, how a move is written, and how a
placement is checked. Placement settles most of what routing can do: no track repairs a large loop or an
unreachable pad afterwards.

## Contents

- [Decide where each part goes](#decide-where-each-part-goes)
- [Keep every pad reachable](#keep-every-pad-reachable)
- [Move, then check](#move-then-check)

## Decide where each part goes

Every rule here serves a small current loop, a short sensitive connection, or a pad a track can still
reach. Where a rule and that purpose disagree on a board, follow the purpose; where a datasheet's layout
notes or the vendor's reference layout disagree with either, follow them: a ground pad tied to one pin, a
via to one layer only and a length limit are requirements.

Read the schematic first (`kicad_sch.read`): note each part's job and the pin or part it serves. Where a pin
is on the package comes from the board's pads (`board.part("U1").pads`), never from how the sheet draws the
symbol. Use the parts the schematic gives and add none: no ferrite, capacitor or via pattern that neither
the schematic nor the vendor's reference design has. Where the documents leave a choice open, make it, say
it is your inference, and go on.

Rank the connections by how little length each bears, and place in that order, while the space at the
pins is free:

1. What the mechanics fix: connectors, buttons, LEDs, mounting holes, an antenna and its keep-out, anything
   the enclosure locates. These go first and are locked. A horizontal connector sits at a board edge with
   its mating face out over it: check it in a GLB export opened in the viewer (`cad kicad_pcb export
   board.kicad_pcb --to glb -o tmp/glb`).
2. What the vendor fixes, and the high-frequency paths: an RF network, a regulator's hot loop, a ground
   tied to one pin.
3. Decoupling and filter capacitors, each at its own pin, supply pad toward the pin, even when a
   neighbour's escape then needs a bend or a via. With a capacitor for every supply pin, each pin gets its
   own, on whichever side of the package it is; with fewer, neighbouring pins share as the vendor groups them.
4. Crystals and their load capacitors.
5. Bulk capacitors, series resistors, ferrites, pull-ups: near what they serve, clear of the above.
6. Everything that tolerates distance.

Keep the parts on one side, and ask the person before putting any on the other.

Choose each large IC's rotation and position by where its pins must go: pins to a fixed part (a connector,
the RF port) face it, pins that leave the area face the edge they leave by, pins with local parts face room
for them. Score all four rotations and keep the best. The distance to a fixed part is the length of what
sits between: an RF pin is its matching network's length from the port. When the network does not fit, move
the IC rather than stretch the links between its parts; when the IC cannot move, keep the network together,
take the extra length in the port's track, and say so.

When a part that must be close cannot reach its pin, move what holds the space and tolerates distance (a
bulk capacitor, a resistor, a crystal, the IC itself), never the close part. Parts competing for one region
(round a regulator, at neighbouring pins) are placed as one group, and the orders compared. Before moving a
critical part off its pin, try at least two alternatives (another rotation, the other side of a neighbour,
swapping two parts at adjacent pins), measure each, and keep the one with the shortest worst gap that still
leaves every pad a way out. Report what could not be satisfied, and why.

Where it most often goes wrong:

- **Parts at neighbouring pins.** Two parts side by side, each in line with its pin, fit only when their
  courtyard widths add up to no more than twice the pin pitch. Stagger them, push one out by its own
  length, or swap which pin gets the nearer place.
- **A switch pin beside the regulated pin**, usual where the DC/DC converter is inside the IC. The inductor
  joins the two, and the output capacitor belongs at the regulated pin. Laid along the pin row, the
  inductor keeps both pads near their pins; turned across it, it pushes its output pad, and the capacitor
  behind that, away.
- **A matching network.** The series parts go in schematic order on one line from the RF pin to the port,
  each shunt's signal pad on that line in a gap between them: a shunt set beside a series pad needs a
  branch track back to the line, which the part values never allowed for. A ground the vendor ties to
  one pin or one layer still wins: put the ground pad there, bring the signal pad as near the line as the
  courtyards let it, and report the branch. Count the gaps before setting the IC's distance from the port.
- **A two-pad part across two pins** (a crystal, a flying capacitor). Each pin's track adds to its load
  capacitance, so the two gaps should be nearly equal: rotate, mirror or slide the part to even them,
  trading a little length for balance, not much. On a four-pad crystal the signal pads are diagonal, so
  measure all four rotations.
- **A row of capacitors with a part beyond it.** Its tracks need a gap through the row: leave one while
  placing the row.

## Keep every pad reachable

Every size here comes from the board's own rules ([where they live](board-api.md#design-rules)), never
from habit, and every position from pad coordinates (`pad.at` and `part.outline` from `kicad_pcb.read`): a
position judged from a snapshot is easily a few tenths of a millimetre out, half a small part.

- **A channel** wherever a track passes between parts: a track's width and a clearance each side.
- **A clear front** before each fine-pitch row, deep enough for its tracks to spread before they turn.
  Put nothing in front of a pin it does not connect to unless that pin can leave at 45°.
- **A via site** beside each ground pad of a decoupler, crystal or shunt that returns to a plane: a
  via's diameter plus its clearance to other nets. Where the vendor ties that pad elsewhere, add no via.
- **Courtyards apart.** Touching passes DRC; leave a gap where a track or via must pass between.
- **In line with the pin, not across the row,** so both neighbours keep a straight way out.

When a short critical connection and an escaping track want the same space, keep the critical part and say
what the escape needs instead (a bend, a via, another edge).

## Move, then check

Move each group in one `kicad_pcb.edit` block: position and rotation set on the footprints read back from
the board and sent with `b.update_items(...)`, and a change of side with `b.flip_items(...)`, KiCad's own
flip, which mirrors pads, courtyard and graphics to the other side, only for a part not on that side
already. Never set a footprint's layer by hand.

**On the back** a part keeps KiCad's orientation: its pads are its library footprint's mirrored top to
bottom (each local y negated), then turned by its orientation. So 0 on the back is the library footprint
upside down (a SOT-23's pin 1 at the bottom left), and `flip_items` leaves a part that was at θ on the
front at 180° − θ, mirrored left to right as seen from the front. For a back part that reads as the front
part at θ seen through the board, flip it and set 180° − θ; read the pads back to check.

**A footprint's own zones** (a module's antenna keep-out, a jack's) are moved twice by KiPy's position
setter: KiCad hands their outlines over in the footprint's frame, and KiPy shifts them by the move all the
same, so the keep-out lands off the part and keeps nothing out. DRC says at most `lib_footprint_mismatch`.
Keep each outline as it was across the move; KiCad then places it with the footprint (a turn and a flip
are right):

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

A zone already off its part goes back to its library footprint's outline, in the footprint's frame: each
point as the library has it, its y negated on the back (KiCad's flip mirrors it), never turned and moved
onto the board by hand, which KiCad then places a second time.

**A nanometre off.** `Vector2.from_xy_mm` and `from_mm` truncate, so 8.2 mm is saved as 8.199999: compare
what you read back within a tolerance. KiPy turns a footprint's pads, fields and drawings itself. A turn
by a multiple of 90° is exact, as are a move and KiCad's flip; any other angle rounds each to the
nanometre, and after several such turns some stay 1 nm off (`3.169999`) even with the part turned back.
DRC then warns `lib_footprint_mismatch` ("does not match copy in library") on a footprint nobody changed.

After each group:

- **DRC.** `cad kicad_pcb drc board.kicad_pcb`: fix every courtyard, clearance and edge error.
  Unconnected items are expected until routing.
- **Your own measurements.** A check script reading the saved board measures each pin to its part,
  each ground pad's via site and each crystal's gaps ([layout's list](layout.md#a-property-check)).
- **The ratsnest**, in the placement snapshot ([SKILL.md](../SKILL.md#check-each-change)). A line that
  must cross a pad row, or ends at a pad walled in by parts, is a lane still to open.

Routing shows where lanes run short, so expect to move parts again. A routed part moved leaves its tracks
and vias where they were, and those now cross other pads (`shorting_items` at the next DRC): delete its
nets' copper round it before the move (`b.remove_items(...)`), and route them again after.

A placement that passes these checks has its distances, order and lanes right. It does not tune an RF
match or prove a regulator stable or a clock within its budget, and a hard placement is no proof that the
board cannot be routed.
