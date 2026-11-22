# Electrical

Read this for the electrical area of a [review before ordering](../SKILL.md#before-ordering): what to
measure on the board's own circuits, and what to look at by hand. These are design reviews a fab never
performs: a board that breaks them is made fine and works badly.

## Sources

- [IPC-2221B](https://www.ipc.org/TOC/IPC-2221B.pdf) section 6.2 for conductor width
  against current and temperature rise; use its outer-layer chart.
- The datasheet of each IC for decoupling values and placement, which wins over
  the distance guide below.

## Measure

Read the board back ([checks](checks.md#read-it)): every part with its pads and their nets, every net with
its tracks, vias and pours. Two inputs may have to come from elsewhere:

- **Which pads are IC power inputs.** A board imported from its schematic's netlist carries each pad's pin
  type (`pad.type == "power_in"`); one made without a schematic carries none, and the datasheets say.
- **What current each power net carries**: the person, or the brief. Without one, compute nothing: ask, or
  mark the check **unverified**.

| Measurement | How | Read it as |
| --- | --- | --- |
| Decoupling missing | for each IC power pad, no capacitor pad on the same net whose other pad is on ground | **fail** unless the datasheet needs none or the capacitor sits on a differently named net; say which |
| Decoupling far | the nearest such capacitor pad is over 3 mm from the pin, pad centre to pad centre | **review**: move it beside the pin, on the same side, short return to the ground pour; bulk capacitors may sit further |
| Track too thin | a power net's narrowest track (`min(track.width for track in net.tracks)`) is below what its current needs ([IPC-2221](layout.md#the-method): at 1 oz outer copper and a 10 °C rise, 0.30 mm for 1 A, 0.78 mm for 2 A, 1.37 mm for 3 A) | **fail** for a power net carrying that current; widen, pour, or split across layers. A short stub at a fine-pitch pad's width is the connector's limit, not a defect, if it widens within a millimetre or two |
| Ground path | every ground pad reaches the pour: a via within a millimetre or two of each surface-mount ground pad, through-hole ground pins in the pour | **review** when a pad hangs on a thin track to a distant via |

Then by inspection:

- No pour island is cut off from its net (KiCad removes islands by default; a
  kept one is copper connected to nothing).
- Power entry: reverse-polarity, inrush and ESD parts beside the connector, before
  anything else on the net.
- Thermal: regulators and FETs dissipating more than a few hundred milliwatts have
  copper area and vias under them as the datasheet asks.
- High-speed and analog nets, if any: differential pairs routed together, no
  splits under them in the reference plane, crystals with short traces and
  ground guard ([layout](layout.md#return-current-and-the-reference-plane)).
- Connectors: a horizontal one at a board edge with its mating face out
  ([placement](placement.md#decide-where-each-part-goes)).

This review answers layout questions, not circuit ones: whether the circuit
works is the datasheets' and the designer's, and the report says which kind a
finding is.
