# Routing: by hand and with Freerouting

A board is finished when nothing is unrouted and KiCad's DRC has no error. Get there in
this order: place, draw what must run one way, pour ground, autoroute the rest, read the
result, look at the board.

## Place first

The router never moves a part, and a board that routes badly almost always needs a better
placement, not more passes ([layout](layout.md)):

- Connectors on the edges, mating side outward; the parts of one subcircuit together.
- Decoupling capacitors at their IC's power pins, on the same side.
- The power path in a line: input, protection, regulator, its capacitors, the loads.
- Room between parts for tracks: a few millimetres between rows of fine-pitch pads.
- Pins that connect facing each other (rotate a part rather than route around it).

## Draw what must run one way

The router keeps every track and via the script draws, routes around them, and continues
from their ends. Draw by hand:

- high-current paths, wider in a net class: `board.netclass("Power", track_width=0.5, clearance=0.2)`;
- anything whose shape matters: a switching regulator's loop, a crystal's short traces,
  differential pairs (USB, CAN: side by side, equal length). The router knows neither
  length matching nor pairs.

A net class sets the width of every connection the router makes on its nets, the thin ones
too: a 1 mm power class cannot reach the same net's pad on a 0.65 mm-pitch transistor or a
0603 enable resistor between fine-pitch pins, and those connections stay unrouted. For a
power net with small pads on it, draw its current path wide by hand (`width=`) and leave the
net in the default class; the router finishes its thin branches. End a hand-drawn branch on a
vertex of the track it leaves (a point of both polylines) or on a pad, never mid-segment.

## Pour ground

Ground is a zone (`board.zone`), filled by KiCad after routing, around the routes.

- **2 layers**: pour ground on both sides, `board.zone(gnd, layers=["F.Cu", "B.Cu"])`, and
  let the router route ground like any net: every ground pad gets a track and the pours join
  them. Leaving ground to the pours alone (`skip=[gnd]`) needs more: routes crowd the ground
  pads until the pour reaches some through one thermal spoke (DRC `starved_thermal`: use
  `pads="solid"`), and a pour that routes cut in two is an island the draft lists as
  unrouted until a via or track joins it.
- **Starved thermals after routing**: through-hole header pins at 2.54 mm leave the router's
  tracks no room for two spokes. With every SMD part on top, only through-hole pads reach the
  bottom pour, so connect it solid there (`board.zone(gnd, layers=["B.Cu"], pads="solid")`)
  and keep the top's thermals for reflow. A ground pad in a fine-pitch row (a USB-C
  receptacle's) is reached by one spoke: tie it with a short track to the connector's own
  ground (its shell tab) or into the pour.
- **4 layers** (signal, ground, power, signal): planes on the inner layers, and keep the
  router's tracks off them so they stay whole:
  `board.zone(gnd, layers=["In1.Cu"])`, `board.zone(v33, layers=["In2.Cu"])`,
  `board.autoroute(layers=["F.Cu", "B.Cu"])`. A plane joins its net only where one of the
  net's vias or through-hole pads passes through it: route the plane's net too (its vias
  join the plane), or skip it and put a via beside each of its pads by hand.

## Autoroute the rest

```python
board.netclass("Power", track_width=0.5, clearance=0.2)
vin = board.net("VIN", power_flag=True, netclass="Power")
...                                            # parts, connections, placement
board.track(vin, [j1[1], (-10, 0), u1["VI"]])  # drawn: kept as drawn
board.zone(gnd, layers=["F.Cu", "B.Cu"])       # ground pours; the router routes ground too
board.autoroute()                              # everything not drawn, when the board is built
return board
```

`board.autoroute(skip=(), layers=None, passes=100, timeout=600)`, called once:

- `skip`: nets (or net names) the router leaves alone. Their pads stay obstacles.
- `layers`: the copper layers tracks may run on (all of them by default). Vias still pass
  through every layer.
- `passes`: the most routing passes Freerouting may make. It stops sooner when everything
  is routed or when it stops improving. The same board and passes always route the same way.
- `timeout`: seconds. A run that takes longer fails the build; a half-routed board is never
  written because a machine was slow.

The router follows each net's class (track width, clearance, via size), the board's
minimum clearance, the copper-to-edge and hole clearances, the outline and its holes,
keepouts (`board.keepout`), and copper text or graphics. It does not know custom rules
(`board.rule`); KiCad's DRC checks them on the routed board.

Tracks keep their class width all the way to the pad, so a wide net into a fine-pitch pad
(0.5 mm power into a 0.45 mm TSSOP pad) can stay unrouted. Draw a stub out of the pad at
the pad's width, clear of the pad row, and the router continues from its end:

```python
x, y = u2["VDD"].position
board.track(v33, [u2["VDD"], (x + 2.5, y)], width=0.3)   # out of the right-hand pad row
```

## Reading the result

- `built board.kicad_pcb`: everything routed, no DRC error.
- `built board.kicad_pcb (draft: N unrouted connections)` and the list: what the router
  could not finish (or a skipped net's pads its pour did not reach). In order: move or
  rotate the parts involved to open a path; give a crowded net a narrower class; draw that
  connection by hand; allow another layer; only then raise `passes`.
- A failed build lists KiCad's errors, each with its items and their positions in the
  script's coordinates. After autorouting, an error means a rule the router did not know
  (a custom rule, a hand-drawn item breaking a rule): fix it, or draw that part by hand.
- `Freerouting did not finish routing in 600 s`: the board is too hard as placed. Spread
  the parts, route the densest nets by hand, or lower `passes`.
- Then look: `cadgen pcb snapshot board.kicad_pcb tmp/board.png`. Long detours, tracks
  cutting a ground pour in two, a via under a part are not errors, but fix them by placement
  or by drawing that net.

## Installing Freerouting

cadgen runs Freerouting 2.4 or newer as a separate program (GPL-3.0, never bundled).
Releases: https://github.com/freerouting/freerouting/releases

- **macOS (Apple Silicon)**: open `freerouting-<version>-macos-arm64.dmg` and drag
  `freerouting.app` into Applications. It carries its own Java.
- **Windows**: run `freerouting-<version>-windows-x64.msi`. It carries its own Java.
- **Linux**: unzip `freerouting-<version>-linux-x64.zip` (it carries its own Java) and
  `export CADGEN_FREEROUTING=/path/to/freerouting-<version>-linux-x64/bin/freerouting`.
- **Any system, the jar**: download `freerouting-<version>.jar`, install Java 25 or newer
  (macOS `brew install openjdk`; Ubuntu `sudo apt install openjdk-25-jre-headless`;
  anywhere https://adoptium.net) and `export CADGEN_FREEROUTING=/path/to/freerouting-<version>.jar`.

cadgen looks at `CADGEN_FREEROUTING` (a jar, a launcher or `freerouting.app`), then
`freerouting` on `PATH`, then where the installers put it. For a jar it finds Java at
`CADGEN_JAVA`, `JAVA_HOME`, on `PATH` or in Homebrew's `openjdk`. A build without them, or
with a Java too old, fails and says which one to install.
