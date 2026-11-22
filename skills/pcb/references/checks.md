# Read and check the saved board

Read this to read a board in a script, to answer a reference the viewer handed you, or to read DRC's
findings as data.

## Read it

```python
from cad import kicad_pcb

board = kicad_pcb.read("board.kicad_pcb")
part = board.part("J1")
pin = part.pad("1")
print(pin.at, pin.net)
print(board.resolve("#J1.1"))
```

Run it with `cad run inspect_board.py`. Each `kicad_pcb.read` reads the file as it is now, so read again after
an edit. It answers a read-only view in the board's frame (millimetres, y down): `parts` (each with its
`pads`), `tracks`, `vias`, `zones` (each layer's `fills`), `rule_areas`, `holes`, `outline`, `texts`,
`dimensions`, `shapes` (the graphics), and `nets`, each with its pads, tracks, vias and zones and the
`netclass` the `.kicad_pro` beside the board gives it. Printing one says what it holds
(`Net('/GND', class 'Power': 4 pads, 8 tracks, 2 vias, 1 zones)`).

- `part.pad("3")` is the first pad of that number. A shell's, a tab's or a thermal pad's several are
  `part.pads_numbered("3")`: measure a pin over them all.
- An arc or a circle of the outline or a graphic is points along it, every chord within 0.005 mm of it, so a
  part fitted to the outline read back fits the board as drawn. A track's arc is coarser: a point each
  10 degrees.
- `from cad.kicad_pcb import inside`: whether a point lies in a polygon (a pour's fill, the outline), by the
  even-odd rule, in the same millimetres.
- `cad kicad_pcb inspect board.kicad_pcb` prints the board in one look (`--json`: `format`, `thickness`,
  `size`, `layers`, `parts`, `nets`, `counts`, and `models`, each part's 3D model found or why not).

What DRC does not establish (decoupling distances, width for current, a pair's geometry, the ground under a
fast net) is measured from this view, each threshold from the circuit, the datasheets and the stackup:
[layout](layout.md#a-property-check) has the script.

## DRC as data

```bash
cad kicad_pcb drc board.kicad_pcb --json
```

`findings` are the lines it prints without `--json` (`severity`, `code`, `message`, `location`), and
`measurements.drc` each one as KiCad reported it (`check`, `severity`, `type`, `description`, `at`, `layer`).
Both carry the finding's `items`, each with KiCad's `uuid`, `description` and `pos`, and what the board says
it is: `kind` (track, via, pad, zone, footprint, shape, text, field), `layers`, `net`, `part`, and `ref`, the
reference `board.resolve` takes (`#track:<uuid>`, `#U3.7`, `#U3`). KiCad reports a copper sliver with no item
and no position: the check finds it again in that layer's saved copper (`at_source: "board"`), and where it
cannot, `note` says why. `kicad_pcb.drc(path)` answers the same in a script run with `cad run` (`.ok`,
`.findings`, `.measurements["drc"]`, `.human_lines()`).

DRC checks the copper as saved and refills nothing. A zone outline is not proof of connected copper: a
missing or stale fill says nothing true of what the zone joins, so refill in an edit (`b.refill_zones()`)
and save before trusting the result.

## References

The viewer hands you what the person picked as references, the file then `#` then selectors
(comma-joined, one token). `board.resolve(ref)` answers one, `board.resolve_all(ref)` each of a token's:

| Reference | Names | `resolve` answers |
| --- | --- | --- |
| `#U1` | a part (footprint) by reference | `Part` |
| `#U1.3` | its pad 3 | `Pad` |
| `#net:GND` | a net, everything on it | `Net` |
| `#net:GND@x12y8` | that net's copper at a point (a board saved without uuids names copper so) | `Copper` |
| `#track:<uuid>` | a track or an arc | `Track`: net, layer, width, `length`, `points` |
| `#via:<uuid>` | a via | `Via`: net, `at`, diameter, drill, `layers` (its two ends), `type` |
| `#zone:<uuid>` | a zone, on each of its layers, or a rule area (a keepout) | `Zone` (its first layer's): net, `layers`, `name`, `priority`, `filled_area`; a rule area's `rule` is true, its net none (`board.rule_areas` lists them, never among `board.zones`) |
| `#text:<uuid>` | a board's text, or a footprint's shown field or `fp_text` | `Text`: `text`, layer, `at`, `angle`, `size`, `part` |
| `#dimension:<uuid>` | a dimension | `Dimension`: `type`, layer, `value` (as KiCad shows it), `lines` |
| `#shape:<uuid>` | a graphic: a `gr_*` or `fp_*` line, rect, circle, arc, poly or curve | `Shape`: `shape`, layer, width, `points`, `part` |
| `#@x12y8` | a point | `Point`: what is there (`board.at(x, y)`) |
| `#F.Cu@x12y8` | a point on a layer | `Point` with `layer`: what that layer holds there (`board.at(x, y, layer="F.Cu")`) |
| `#@x10y5..x20y15` | an area, the box between two corners | `Area`: `box`, `size`, and what lies wholly inside (`board.area(x0, y0, x1, y1)`) |
| `#F.Cu@x10y5..x20y15` | an area on a layer | `Area` with `layer`: that layer's part of it, the parts on its side |

- **An area** is what the viewer names when the person's box takes nothing (it names no point; a point is
  yours to write). Its layer is the one they were working on (the copper nearest them, or the layer they
  isolated), so put what they ask for there unless the note says otherwise.
- **A `<uuid>`** is the one the board file saved the item with (`(uuid "...")`), kept by every save and by
  KiCad's API, so it still names the item after you move it: find it in the file by that uuid
  (case-insensitive), or in a `kicad_pcb.edit` block with `b.get_items_by_id(KIID(value=uuid))`
  (`from kicode.proto.common.types import KIID`). Copies of one footprint can share their items' uuids;
  such an item is named under its footprint's uuid, `#text:<footprint uuid>/<uuid>`. A reference whose
  item is gone raises `ValueError`.
- **A path containing spaces** is quoted before its reference: `"my board.kicad_pcb"#U1.3`.
- **A Quick Edit's packet** (`cad kicad_pcb snapshot --job PACKET`) lights the same references on the
  board it draws, as the person saw them; one that no longer resolves is listed in its warnings.
