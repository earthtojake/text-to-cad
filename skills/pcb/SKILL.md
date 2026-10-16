---
name: pcb
description: Design printed circuit boards as Python scripts on KiCad's own API and get a KiCad board file. Use for PCBs and circuit boards, .kicad_pcb files, footprints and footprint libraries (fp-lib-table), placement, hand routing, vias and copper pours, design rules and DRC, Gerbers, drill, pick-and-place and KiCad's other exports, and for opening a board in CAD Viewer. Needs the KiCad 10.99 nightly (the KiCad 11 API).
license: MIT
---

# PCB design

Provenance: maintained in [earthtojake/text-to-cad](https://github.com/earthtojake/text-to-cad).
Use the installed local skill files as the runtime source of truth.

## Setup

Run cadgen through [uv](https://docs.astral.sh/uv/), so this skill's commands share one
installation, and its warm build daemon, with the CAD app's server:

- `cadgen` below means `uvx --no-config --managed-python --python 3.13 --from cadgen==0.7.21 cadgen`
- `python` below means `uvx --no-config --managed-python --python 3.13 --from cadgen==0.7.21 python`

KiCad builds the board: `@pcb` starts KiCad's headless API server (`kicad-cli api-server`), which only
the **KiCad 10.99 nightly** (the KiCad 11 API) has; 10.0 is refused at start. It is installed, never bundled:

- Ubuntu: `sudo add-apt-repository ppa:kicad/kicad-dev-nightly && sudo apt install kicad-nightly kicad-nightly-footprints`
- macOS: the nightly installer at https://www.kicad.org/download/macos/ (KiCad.app carries `kicad-cli`)
- Windows: the nightly installer at https://www.kicad.org/download/windows/ (`Program Files\KiCad\<version>\bin\kicad-cli.exe`)

cadgen finds `kicad-cli-nightly` or `kicad-cli` on `PATH`, then in those install folders; `CADGEN_KICAD_CLI`
names one anywhere. `cadgen doctor` reports the KiCad found and its version, or the install line.

## The contract

A board is a Python script: the decorated function receives an empty KiCad board (`cadgen.kipy.board.Board`,
kicad-python vendored) and fills it with raw kicad-python calls. The script is the source and
`blinky.kicad_pcb` its output, as a STEP is a part's: never edit the board file, edit the script and run it.

```python
from cadgen import pcb
from cadgen.kipy.board_types import BoardLayer, BoardPolygon, Net, Track, Via, Zone
from cadgen.kipy.geometry import Angle, PolygonWithHoles, PolyLineNode, Vector2
from cadgen.kipy.util.units import from_mm

PARTS = {  # ref: footprint (from a library fp-lib-table declares), (x, y) mm, rotation, pad number -> net
    "J1": ("Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical", (-15, 0), 0, {"1": "VBUS", "2": "GND"}),
    "R1": ("Resistor_SMD:R_0603_1608Metric", (0, 5), -90, {"1": "VBUS", "2": "LED"}),
    "D1": ("LED_SMD:LED_0603_1608Metric", (8, -5), 0, {"1": "GND", "2": "LED"}),
}

def rectangle(w, h):
    poly = PolygonWithHoles()
    for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
        poly.outline.append(PolyLineNode.from_xy(from_mm(sx * w / 2), from_mm(sy * h / 2)))
    poly.outline.closed = True
    return poly

def track(net, width, *points, layer=BoardLayer.BL_F_Cu):
    """One straight Track per pair of points (Vector2 or (x, y) mm): a route is several."""
    nodes = [p if isinstance(p, Vector2) else Vector2.from_xy_mm(*p) for p in points]
    for a, b in zip(nodes, nodes[1:]):
        t = Track()
        t.start, t.end, t.width, t.layer, t.net = a, b, from_mm(width), layer, Net(name=net)
        yield t

@pcb
def blinky(board):
    pads, placed = {}, []
    for ref, (footprint, at, rotation, nets) in PARTS.items():
        fp = board.place_footprint_from_library(footprint, Vector2.from_xy_mm(*at), Angle.from_degrees(rotation))
        fp.reference_field.text.value = ref
        for pad in fp.definition.pads:
            pad.net = Net(name=nets[pad.number])
            pads[f"{ref}.{pad.number}"] = pad.position            # absolute, in nm: route from these
        placed.append(fp)
    board.update_items(placed)
    edge = BoardPolygon()                                         # the outline, centred on KiCad's origin
    edge.polygons.append(rectangle(40, 30))
    edge.layer, edge.attributes.stroke.width = BoardLayer.BL_Edge_Cuts, from_mm(0.1)
    via = Via()
    via.position, via.net, via.diameter, via.drill_diameter = Vector2.from_xy_mm(7.2125, -8), Net(name="GND"), from_mm(0.6), from_mm(0.3)
    pour = Zone()                                                 # a copper zone by default
    pour.outline, pour.layers, pour.net, pour.name = rectangle(39, 29), [BoardLayer.BL_B_Cu], Net(name="GND"), "GND"
    board.create_items([edge, via, pour,
                        *track("VBUS", 0.3, pads["J1.1"], (0, 0), pads["R1.1"]),
                        *track("LED", 0.25, pads["R1.2"], (0, 8), (12, 8), (12, -5), pads["D1.2"]),
                        *track("GND", 0.25, pads["D1.1"], via.position)])
    rules = board.get_design_rules().rules                        # the fab's limits: what DRC checks against
    rules.constraints.min_clearance = rules.constraints.min_track_width = from_mm(0.15)
    board.set_design_rules(rules)

if __name__ == "__main__":
    blinky()
```

```bash
python blinky.py      # blinky.kicad_pcb: 3 parts, 7 tracks, 1 via, 1 zone, 0 unconnected, DRC 0 errors 0 warnings, 6.2 s
```

The run starts a server with an empty settings directory, creates the document (`<function>.kicad_pcb` beside
the script, or `@pcb(path=...)` relative to it), loads the libraries `fp-lib-table` declares, calls the function,
`refill_zones()`, counts pads no copper path joins to the rest of their net, saves `.kicad_pcb`, `.kicad_pro`,
`.kicad_prl` (and `.kicad_dru` when the script sets custom rules through the API), stops the server, runs KiCad's DRC on the saved
file and prints the line above (the path cwd-relative, the seconds including the DRC), then every finding below it,
errors first, in `cadgen pcb drc`'s text: `error: clearance at (-15, 2.54) mm: Clearance violation (...): PTH pad 2
[GND] of J1; PTH pad 1 [VBUS] of J1`. The board is saved before it is checked and the exit code stays 0 whatever DRC
finds; `--no-drc` skips the check and the `DRC` segment. KiCad assigns ids; every run rebuilds from nothing.

- An exception in the function stops the server and propagates: nothing is saved. `footprint 'Lib:Name' not
  found` means a library `fp-lib-table` does not declare.
- A board saved by anything but the script since its last build (KiCad, an editor, another tool) is refused
  with one sentence naming the file; `--force` overwrites it. The record is the `CADGEN_BUILD` text variable KiCad
  keeps in the board and the project file: the SHA-256 of the board's bytes. A missing board file needs nothing.
- `cadgen pcb drc blinky.kicad_pcb` is the standalone check: one line per violation or unconnected item
  (severity, type, description, position), exit 1 on any error-severity violation or unconnected item;
  `--json` for the report. Nothing on the KiCad path is cached.

Everything on the board is raw kicad-python: lengths are integers in nanometres (`from_mm`, `to_mm`), positions
`Vector2.from_xy_mm`, angles `Angle.from_degrees`, layers `BoardLayer.BL_F_Cu`, `BL_B_Cu`, `BL_Edge_Cuts`...; the
frame is KiCad's, millimetres, **y down**. A net exists by being named (`Net(name="VBUS")` on a pad, track, via or
zone); a placed footprint returns with its pads at absolute positions, so route from `pad.position`. Design rules,
custom rules, net classes, text, keepouts, exports: [the board API](references/board-api.md). Beside the script,
`fp-lib-table` (KiCad's project library table) declares every footprint library the board uses, one row each:
`(lib (name "Resistor_SMD") (type "KiCad") (uri "${KICAD10_FOOTPRINT_DIR}/Resistor_SMD.pretty") (options "") (descr ""))`
for a stock one (`${KICAD10_FOOTPRINT_DIR}` is the nightly's name for KiCad's folder; it changes per major), `${KIPRJMOD}/my.pretty`
for the board's own. Only listed rows load (~0.3 s, ~60 MB each); `blinky.kicad_dru` beside them holds the board's custom rules
([checks](references/checks.md)). Names and a footprint's pads: [parts](references/parts.md).

## The quality bar

A board is done when every line holds. **DRC rule**: KiCad measures it from a rule the board declares (the fab's
limits through `set_design_rules`, the rest as custom rules in `blinky.kicad_dru`). **Script**: a check on the saved
file with `read_board`. Each rule and script, verified on the nightly, is in [checks](references/checks.md).

| Property | Measure | By |
| --- | --- | --- |
| Clearance, track width, drill, annular ring, copper to edge, silk and courtyards at the fab's limits | the capability page's numbers ([manufacturing](references/manufacturing.md)); `clearance`, `hole_to_hole`, `edge_clearance`, `silk_clearance`, `courtyard_clearance`, `creepage` scope one net or part | DRC rule |
| Power tracks sized for their current | IPC-2221 `I = 0.048 · ΔT^0.44 · A^0.725` (I in A, ΔT in °C, A the copper section in mil²; 1 oz is 1.378 mil thick). Outer layer, 10 °C rise: 1 A → 0.30 mm, 2 A → 0.78 mm, 3 A → 1.37 mm; inner layers 2.6×. `track_width (min)` per net | DRC rule |
| Decoupling at the pin | each IC power pad has a capacitor pad on its net within 3 mm, centre to centre | script |
| Ground pads reach the pour | every SMD ground pad within 1.5 mm of a ground via; through-hole pins sit in the pour | script |
| No detours | a net's routed length under 1.3× the shortest tree through its pads | script |
| Bends at 45° or 90°, none acute | `track_angle (min 90)`: the angle between joined segments (90 at a right angle, 135 at a 45° bend, under 90 at a hairpin) | DRC rule |
| Buses parallel and equally spaced | adjacent nets' parallel runs at one spacing | script |
| Pairs coupled and matched | `diff_pair_gap (min) (max)`, `diff_pair_uncoupled (max)`, `skew (max) (within_diff_pairs)` | DRC rule |
| Ground under every signal | each outer-layer signal segment over the ground pour of the layer beneath | script |
| Connectors at the edge they are reached from | mating face toward the outline, the housing and cable clear of parts | inspection |
| Routed | `0 unconnected` and `DRC 0 errors` in the build line | build |

## The loop

Build; look (show the board, or `cadgen pcb snapshot blinky.kicad_pcb tmp/blinky.png`, with `--display copper` or
`--display '{"mode":"copper","layers":["F.Cu","Edge.Cuts"]}'` for one layer set); read the findings and
run your checks; change the script; again. A round is seconds, a real board hours of them, with the person
pointing in the viewer. Keep the checks you repeat as `check_*.py` beside the board, run with `python`.
Confirm when unspecified: the outline and mounting holes (from the enclosure, drill/place origin on a corner);
the fab and service (its limits are the rules; JLCPCB standard 2-layer when none is named, said so); layer
count (2 for most small boards; 4 as signal, ground, power, signal for fast digital, RF, dense MCU); parts on
both sides (costs more); any package or part change from what was asked; each power net's current.

## The viewer and references

The viewer draws a `.kicad_pcb` read-only from the file, no KiCad. Board tools: Select (hover, net highlight),
the tree, the Reference, copy reference, Quick Edit; Display with a checkbox per layer (front, inner, back,
other; vias, drills, ratsnest) under the Mode presets (Board, Copper, Assembly, Placement). No measure, no
draw on a board. Drag to pan, wheel or pinch to zoom, double-click to fit. What the person points at reaches
you as a board reference `<file>#<selector>`: `#R1` a part, `#R1.2` its pad as the footprint numbers it,
`#net:VBUS` a net, `#net:VBUS@x40.1y21.6` that net's copper at a point, `#@x40.1y21.6` a point; several share
one `#`, comma-joined. Points are millimetres in KiCad's frame, y down, the one `Vector2.from_xy_mm` takes; the
file is the board's absolute path, quoted when it holds a space or `#`. `read_board(path).resolve(selector)` answers
it from the saved file ([checks](references/checks.md#scripts) has the API); a failing check prints the same
selectors (`#U1.3`), so the person can click what it names; after a rebuild, resolve against the new board.

## Handoff

Report the files written, the build line (parts, tracks, vias, zones, unconnected, DRC counts), every finding left
and why, the checks you scripted and their results, and your assumptions (footprints, pad-to-pin mapping, currents,
the fab's limits in the rules). Show the board. Before ordering, $pcb-dfm reviews it for fabrication, assembly and sourcing.

## What works today (2026-10)

There is no autorouter and none is wanted: place one functional group (a connector and what it feeds, a regulator and
its capacitors, an IC with its decoupling) and route it before placing the next, looking after each. Fan out every
fine-pitch part (a stub per pad, a via where it changes layer) before any long track exists to block it. Octolinear
segments only; related signals as a bus generated in a loop, parallel and turning together. Widths from the table
above; ground as a pour with a via beside every surface-mount ground pad; on two layers route on top and keep the
bottom pour whole, crossing it only for short jumps. Moving a part after routing is fine when routes start and end
on `pad.position`: rerun and the tracks follow.

## Show the model

Show the user each file you create or change, and any they ask to see. Snapshots and
validation don't replace this.

- If your tools include `cad_show` (your host may prefix it), use it with the file's
  absolute path, and follow its description for when to call it again. `cad_view` reads
  what the user selected; `cad_screenshot` shows you what they see. Neither is a review
  of your own work.
- Otherwise run the CAD Viewer, from any folder:

  ```bash
  cadgen viewer --host 127.0.0.1 --json --detach
  ```

  `--detach` returns once the viewer answers requests and leaves it running in the
  background: always pass it, since a foreground viewer never exits (and piping its
  output through `tail` can hide the URL for good). It starts this machine's one viewer,
  or reuses it. Read `url` from its one JSON line (never guess the port), and for each
  file return `url?file=<its URL-encoded absolute path>`. If it fails to launch, say so.
