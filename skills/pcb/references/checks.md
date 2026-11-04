# Read and check the saved board

```python
from cad import kicad_pcb

board = kicad_pcb.read("board.kicad_pcb")
part = board.part("J1")
pin = part.pad("1")
print(pin.at, pin.net)
print(board.resolve("#J1.1"))
```

Run it with `cad run inspect_board.py`, and KiCad's rule check with the command:

```bash
cad kicad_pcb drc board.kicad_pcb --json
```

Each `kicad_pcb.read` call reads the current file. Its dataclasses hold a read-only view of that
revision: parts, pads, tracks, vias, zones, holes, nets, outline, texts, dimensions and graphics
(`shapes`), in board millimetres with y down. It does not launch KiCad, validate electrical design, or serve as a file serializer.
Project netclass names are read from the sibling `.kicad_pro` when present. Refresh the index
after an edit. `part.pads_numbered(number)` includes all shapes for a shared pin number.
`from cad.kicad_pcb import inside` tests whether a point lies in a polygon (a pour's fill, the
outline) by the even-odd rule, in the same millimetres. DRC is `cad kicad_pcb drc` (`--json`: each
finding's items with their uuids and positions under `measurements.drc`), and
`cad.kicad_pcb.drc(path)` in a script run with `cad run` whose header names `cad[kicad]` (a
`# /// script` block's `dependencies`); both run kicode's `kicad-cli`.

## References

The viewer hands you what the person picked as references, the file then `#` then selectors
(comma-joined, one token). `board.resolve(ref)` answers one, `board.resolve_all(ref)` each of a token's:

| Reference | Names | `resolve` answers |
| --- | --- | --- |
| `#U1` | a part (footprint) by reference | `Part` |
| `#U1.3` | its pad 3 (a shell's or a tab's several pads: `part.pads_numbered("3")`) | `Pad` |
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

Coordinates are millimetres in KiCad's frame, y down, as the file holds them. The viewer names an
area when the person drags a box (it names no point; a point is yours to write): its layer is the
one they were working on (the copper nearest them, or the layer they isolated), so put what they
ask for there unless the note says otherwise. A `<uuid>` is the one the
board file saved the item with (`(uuid "...")`), kept by every save and by KiCad's API, so it
still names the item after you move it: find it in the file by that uuid (case-insensitive), or
in a `kicad_pcb.edit` block with `board.get_items_by_id(KIID(value=uuid))` (`from
kicode.proto.common.types import KIID`). Copies of one footprint can share their items' uuids; such
an item is named under its footprint's uuid, `#text:<footprint uuid>/<uuid>`. A reference whose
item is gone raises `ValueError`.
Quote a path containing spaces before its reference, such as `"my board.kicad_pcb"#U1.3`.

A Quick Edit's packet (`cad kicad_pcb snapshot --job PACKET`) lights the same references on the
board it draws, as the person saw them; one that no longer resolves is listed in its warnings.

Check facts DRC does not establish from the actual saved geometry: distance from each power
pad to its assigned decoupling capacitor, connector access and mating clearance, narrowest
power path against the current and copper specification, differential pair geometry, and
return paths under signals. Thresholds come from the circuit/datasheets and stackup; do not
apply an arbitrary universal distance or current rule. Report assumptions and inaccessible
information. Measure repeated pad shapes together and account for vias and both copper sides.

KiCad's `cad kicad_pcb drc` result is the connectivity and rule gate. A zone outline is not proof
of connected copper: regenerate the fill in KiCad, save it, then run DRC. An unfilled or stale
zone must not be called routed solely because its outline encloses a pin.
