# Checks: each quality property as a DRC rule or a script

Two kinds of check. A **DRC rule** is KiCad's own, declared by the script in `.kicad_dru` form and run
by every build (and by `cadgen pcb drc`); a finding names KiCad's type, the items and a position. A
**script** reads the saved board with `read_board` and prints board references the person can click in
the viewer (`#U1.3`, `#net:D_P@x8.5y-1.1`). Every rule and script below ran against KiCad 10.99
(the 2026-10-14 nightly) and fired on a board built to break it.

## Declaring rules

Custom rules are KiCad's own text in `<board>.kicad_dru` beside the board (`blinky.kicad_dru` for
`blinky.kicad_pcb`), written like `fp-lib-table` and read by every build and by `cadgen pcb drc`; the
rules below are in that form. The file starts with `(version 2)`; a `#` comment stands on its own
line; where two rules match one item the later wins; a rule KiCad cannot parse stops the DRC with the
file, line and offset (the build reports it and exits 1, the board saved). The API writes the same
file from `CustomRule` objects (`set_custom_design_rules`, [board API](board-api.md#custom-rules))
and replaces a hand-written one when a script calls it, so a board declares its rules one way, not
both; today's nightly refuses its own text for `track_angle` (`90deg`) and `min_resolved_spokes`
(`(min 2)`), refusing the whole set with it, and has no type for `return_path`, `stub_length` and
`net_chain_length`, which is why the file is the form here.

Conditions are KiCad's expressions over `A` (the item) and `B` (the other item in a two-item check):
`A.NetName == 'VBUS'`, `A.hasNetclass('Power')`, `A.Type == 'Track'` (`'Via'`, `'Pad'`, `'Zone'`),
`A.memberOfFootprint('J1')` (wildcards: `'R*'`), `A.intersectsCourtyard('U1')`,
`A.intersectsArea('keepout')` (a rule area by name), `A.inDiffPair('D')` (nets `D_P`/`D_N`;
KiCad pairs `_P`/`_N` and `+`/`-`), `A.Width`, `B.Type == 'Via'`. `(layer "F.Cu")`, `(layer outer)`,
`(layer inner)` scope a rule; `(severity warning|error|ignore)` sets what a finding counts as
(`hole_to_hole` reports a warning unless the rule says `error`). Lengths take `mm` or `mil`.

## The fab's limits, scoped

Board-wide limits are `set_design_rules` ([manufacturing](manufacturing.md)). A custom rule holds one
net, part or layer to a tighter number; the type in its finding is in brackets.

```text
(version 2)
# [hole_to_hole] between mechanically drilled holes
(rule "drill bits"
  (constraint hole_to_hole (min 0.5mm))
  (condition "A.Type == 'Via' && B.Type == 'Via'")
  (severity error))
# [copper_edge_clearance], including cutouts
(rule "copper to edge"
  (constraint edge_clearance (min 0.3mm)))
# [silk_overlap]: silkscreen to copper and silk
(rule "silk off pads"
  (constraint silk_clearance (min 0.15mm)))
# [courtyards_overlap]
(rule "courtyards apart"
  (constraint courtyard_clearance (min 0.25mm)))
# [clearance] on the outer layers, one net
(rule "outer clearance"
  (layer outer)
  (constraint clearance (min 0.25mm))
  (condition "A.NetName == 'VBUS'"))
# [creepage] along the surface between two nets
(rule "mains to ground"
  (constraint creepage (min 1mm))
  (condition "A.NetName == 'VBUS' && B.NetName == 'GND'"))
# finer rules under one part only
(rule "U1 fanout"
  (constraint track_width (min 0.2mm) (opt 0.25mm))
  (constraint clearance (min 0.15mm))
  (condition "A.intersectsCourtyard('U1')"))
# [via_diameter], [hole_size]
(rule "vias on power"
  (constraint via_diameter (min 0.6mm))
  (constraint hole_size (min 0.3mm))
  (condition "A.NetName == 'VBUS' || A.NetName == 'GND'"))
```

## Width from current

IPC-2221: `I = k · ΔT^0.44 · A^0.725`, `I` in amperes, `ΔT` the rise in °C, `A` the copper cross-section
in mil² (width in mil × 1.378 mil per oz), `k` 0.048 outside and 0.024 on inner layers. 1 oz outer
copper, 10 °C rise:

| Current | Width |
| --- | --- |
| 1 A | 0.30 mm |
| 2 A | 0.78 mm |
| 3 A | 1.37 mm |

Inner layers need 2.6× the width; a pour carries what a track cannot. The rule holds every segment of
the net to it, so a fine-pitch pad's stub needs its own scope (`U1 fanout` above, listed later).

```text
# [track_width]
(rule "VBUS carries 2 A"
  (constraint track_width (min 0.78mm))
  (condition "A.NetName == 'VBUS'"))
# the same for every net in a class
(rule "power class"
  (constraint track_width (min 0.5mm))
  (condition "A.hasNetclass('Power')"))
# [too_many_vias]: at least 6 vias on the net
(rule "GND stitched"
  (constraint via_count (min 6))
  (condition "A.NetName == 'GND'"))
```

## Bends

`track_angle` measures the angle between two joined segments at their junction, both directions taken
away from it: 180 when collinear, 135 at a 45° bend, 90 at a right angle, under 90 at a hairpin. It
checks joined tracks, not a segment's heading, so a segment at an arbitrary angle passes it; the
octolinear discipline is the script's (`track()` points with `|dx| == |dy|` or one of them 0). A
junction on a pad is not checked. Hand-written only (above).

```text
# [track_angle]
(rule "no acute bends"
  (constraint track_angle (min 90))
  (condition "A.Type == 'Track'"))
# [track_segment_length], as a warning
(rule "no long segments"
  (layer "F.Cu")
  (constraint track_segment_length (max 25mm))
  (condition "A.Type == 'Track'")
  (severity warning))
```

## Pairs and lengths

KiCad pairs nets by suffix (`D_P`/`D_N`, `D+`/`D-`); the gap is edge to edge; uncoupled length is
where the two run apart (fanouts included); skew is the difference of the two routed lengths.

```text
# [diff_pair_gap_out_of_range], [diff_pair_uncoupled_length_too_long], [skew_out_of_range]
(rule "USB pair"
  (constraint diff_pair_gap (min 0.15mm) (opt 0.2mm) (max 0.25mm))
  (constraint diff_pair_uncoupled (max 1mm))
  (constraint skew (max 0.1mm) (within_diff_pairs))
  (condition "A.inDiffPair('D')"))
# [length_out_of_range]: the net's routed length
(rule "LED short"
  (constraint length (max 10mm))
  (condition "A.NetName == 'LED'"))
```

## Pours, thermals, keepouts

`zone_connection`, `thermal_relief_gap` and `thermal_spoke_width` set how a pour meets pads when it
fills (no finding; `min_resolved_spokes` reports pads with too few spokes, hand-written only).
`disallow` and `assertion` report what they name.

```text
# a connector's ground pins, solid instead of spokes
(rule "J1 solid to pour"
  (constraint zone_connection solid)
  (condition "A.memberOfFootprint('J1') && A.NetName == 'GND'"))
(rule "thermals"
  (constraint thermal_relief_gap (min 0.3mm))
  (constraint thermal_spoke_width (min 0.4mm))
  (constraint min_resolved_spokes 2))
# [items_not_allowed]; the API writes `through_via`
(rule "no via under R1"
  (constraint disallow via)
  (condition "A.intersectsCourtyard('R1')"))
# a rule area named keepout (board API: zones)
(rule "no copper under the antenna"
  (constraint disallow track via zone)
  (condition "A.intersectsArea('keepout')"))
# [assertion_failure]: any expression over A
(rule "tracks at least 0.25"
  (constraint assertion "A.Width >= 0.25mm")
  (condition "A.Type == 'Track'"))
```

## Return path

KiCad's `return_path` constraint (`(constraint return_path (layer "B.Cu") (net "GND"))`) and its
`stub_length` and `net_chain_length` check a **net chain**, which a schematic defines; a `@pcb` board
has no schematic, so they parse and never fire. The script instead: every outer-layer signal segment
runs over the ground pour of the layer beneath, sampled every 0.5 mm from 2 mm in at each end (pads
and vias cut the pour where a segment ends).

```python
import math
from cadgen.kicad.board_index import read_board
from cadgen.kicad.geometry import inside

board = read_board("rules.kicad_pcb")
SIGNAL, REFERENCE = "F.Cu", ("B.Cu", "GND")        # the layer checked, and the pour that should lie under it
fills = [fill for zone in board.zones if (zone.layer, zone.net) == REFERENCE for fill in zone.fills]
for track in board.tracks:
    if track.layer != SIGNAL or track.net in (REFERENCE[1], None):
        continue
    for a, b in zip(track.points, track.points[1:]):
        length = math.dist(a, b)
        for along in [2.0 + 0.5 * i for i in range(int((length - 4.0) / 0.5) + 1)]:
            p = (a[0] + (b[0] - a[0]) * along / length, a[1] + (b[1] - a[1]) * along / length)
            if not any(inside(p, fill) for fill in fills):
                print(f"#net:{track.net}@x{p[0]:.1f}y{p[1]:.1f}: no {REFERENCE[1]} on {REFERENCE[0]} under it")
                break
```

## Scripts

Each reads the saved board with `read_board` (`cadgen.kicad.board_index`: the viewer's own data, KiCad's
frame in millimetres, y down; it runs nothing) and prints the selectors of what fails.
`board.resolve("#R1.2")` is a `Pad` (`.part`, `.number`, `.net`, `.side`, `.at`, `.polygon`, `.selector`),
`board.resolve("#net:VBUS")` and `board.net("VBUS")` a `Net` (`.pads`, `.tracks`, `.vias`, `.zones`,
`.selector`), and `.parts` (`.ref`, `.footprint`, `.at`, `.pads`), `.pads`, `.nets`, `.tracks` (`.net`,
`.layer`, `.width`, `.points`), `.vias` (`.net`, `.at`, `.layers`, `.diameter`), `.zones` (`.net`,
`.layer`, `.fills`), `.holes` and `.outline` are the board. Shared head:

```python
import math
from cadgen.kicad.board_index import read_board

board = read_board("rules.kicad_pcb")

def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])
```

**Detour**: a net's routed length against the shortest tree through its pads (a two-pad net's is the
pad-to-pad distance).

```python
def shortest_tree(points):
    left, total, tree = list(points[1:]), 0.0, [points[0]]
    while left:
        d, p = min((min(dist(p, t) for t in tree), p) for p in left)
        total, left = total + d, [q for q in left if q is not p]
        tree.append(p)
    return total

for net in board.nets:
    if len(net.pads) < 2 or not net.tracks:
        continue
    routed = sum(dist(a, b) for track in net.tracks for a, b in zip(track.points, track.points[1:]))
    shortest = shortest_tree([pad.at for pad in net.pads])
    if routed > 1.3 * shortest:
        print(f"{net.selector}: {routed:.1f} mm routed for {shortest:.1f} mm between {' '.join(pad.selector for pad in net.pads)}")
```

**Decoupling**: for each IC power pad, the nearest capacitor pad on its net within 3 mm. Which pads are
power inputs is the script's pad-to-net dict (here: the nets named).

```python
POWER = {"VBUS"}
for part in board.parts:
    if not part.ref.startswith("U"):
        continue
    for pad in part.pads:
        if pad.net not in POWER:
            continue
        caps = [p for p in board.net(pad.net).pads if p.part.startswith("C")]
        near = min(caps, key=lambda p: dist(p.at, pad.at), default=None)
        if near is None or dist(near.at, pad.at) > 3.0:
            print(f"{pad.selector}: nearest capacitor {near.selector if near else 'none'}" + (f" {dist(near.at, pad.at):.2f} mm away" if near else ""))
```

**Ground vias**: every surface-mount ground pad within 1.5 mm of a ground via; a through-hole pin sits
in the pour itself.

```python
gnd = board.net("GND")
for pad in gnd.pads:
    if pad.side == "both":
        continue
    near = min((dist(pad.at, via.at) for via in gnd.vias), default=math.inf)
    if near > 1.5:
        print(f"{pad.selector}: nearest GND via {near:.2f} mm away")
```

**Bus spacing**: for each pair of adjacent nets in the bus, every parallel, overlapping pair of segments
must sit at one spacing.

```python
BUS = ["A0", "A1", "A2"]

def runs(net):
    return [(a, b) for track in net.tracks for a, b in zip(track.points, track.points[1:])]

for first, second in zip(BUS, BUS[1:]):
    spacings = set()
    for a0, a1 in runs(board.net(first)):
        for b0, b1 in runs(board.net(second)):
            ua, ub = (a1[0] - a0[0], a1[1] - a0[1]), (b1[0] - b0[0], b1[1] - b0[1])
            if abs(ua[0] * ub[1] - ua[1] * ub[0]) > 1e-6 * dist(a0, a1) * dist(b0, b1):
                continue                                           # not parallel
            la = dist(a0, a1)
            offset = abs((b0[0] - a0[0]) * ua[1] - (b0[1] - a0[1]) * ua[0]) / la
            along = sorted(((p[0] - a0[0]) * ua[0] + (p[1] - a0[1]) * ua[1]) / la for p in (b0, b1))
            if along[1] > 0 and along[0] < la:                     # the runs overlap along the bus
                spacings.add(round(offset, 2))
    if len(spacings) != 1:
        print(f"#net:{first} to #net:{second}: spacings {sorted(spacings) or 'none (no parallel runs)'}")
```

**Every pad reached**: the build line's `unconnected` count, as names. cadgen's connectivity
(`cadgen.kicad.connectivity`, the viewer's ratsnest) joins copper that touches on a shared layer and
returns one line per connection still to make, between the two nearest pads.

```python
from cadgen.kicad.connectivity import Copper, ratsnest

copper_layers = {"F.Cu", "B.Cu"} | {t.layer for t in board.tracks} | {z.layer for z in board.zones}
side = {"top": ["F.Cu"], "bottom": ["B.Cu"], "both": sorted(copper_layers)}
items, pads = [], {}
for pad in board.pads:
    if pad.net:
        items.append(Copper.polygon(pad.net, side[pad.side], pad.polygon, anchor=pad.at, pad=True))
        pads[pad.at] = pad
for track in board.tracks:
    if track.net:
        items += [Copper.segment(track.net, track.layer, a, b, track.width) for a, b in zip(track.points, track.points[1:])]
for via in board.vias:
    if via.net:
        items.append(Copper.disc(via.net, via.layers, via.at, via.diameter))
for zone in board.zones:
    if zone.net:
        items += [Copper.polygon(zone.net, [zone.layer], fill) for fill in zone.fills if len(fill) >= 3]
for start, end in ratsnest(items):
    a, b = pads.get(start), pads.get(end)
    print(f"{a.selector if a else start} and {b.selector if b else end} are not joined")
```

Inside the build, the same questions have kipy answers on the live board before it is saved:
`board.get_tracks()`, `board.get_items_by_net(Net(name="VBUS"))`, `board.get_connected_items([pad])`,
`zone.filled_polygons` after `board.refill_zones()`. An assertion there stops the build and saves
nothing, which is what a failed check should do once a property is settled.
