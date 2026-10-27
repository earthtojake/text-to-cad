# Read and check the saved board

```python
from cadgen.pcb import read_board, drc

board = read_board("board.kicad_pcb")
part = board.part("J1")
pin = part.pad("1")
print(pin.at, pin.net)
print(board.resolve("#J1.1"))
result = drc("board.kicad_pcb")
print(result)
```

Each `read_board` call reads the current file. Its dataclasses hold a read-only view of that
revision: parts, pads, tracks, vias, zones, holes, nets and outline, in board millimetres with
y down. It does not launch KiCad, validate electrical design, or serve as a file serializer.
Project netclass names are read from the sibling `.kicad_pro` when present. Refresh the index
after an edit. `part.pads_numbered(number)` includes all shapes for a shared pin number.

References name parts (`#U1`), pads (`#U1.3`), nets (`#net:GND`) and positions
(`#net:GND@x12y8`). The viewer uses the same references for selection and Quick Edit. Quote a
path containing spaces before its reference, such as `"my board.kicad_pcb"#U1.3`.

Check facts DRC does not establish from the actual saved geometry: distance from each power
pad to its assigned decoupling capacitor, connector access and mating clearance, narrowest
power path against the current and copper specification, differential pair geometry, and
return paths under signals. Thresholds come from the circuit/datasheets and stackup; do not
apply an arbitrary universal distance or current rule. Report assumptions and inaccessible
information. Measure repeated pad shapes together and account for vias and both copper sides.

KiCad's `cadgen pcb drc` result is the connectivity and rule gate. A zone outline is not proof
of connected copper: regenerate the fill in KiCad, save it, then run DRC. An unfilled or stale
zone must not be called routed solely because its outline encloses a pin.
