# Electrical

What to measure on the board's own circuits, and what to look at by hand. These
are design reviews a fab never performs: a board that breaks them is made fine
and works badly.

## Sources

- [IPC-2221B](https://www.ipc.org/TOC/IPC-2221B.pdf) section 6.2 for conductor width
  against current and temperature rise; use its outer-layer chart.
- The datasheet of each IC for decoupling values and placement, which wins over
  the distance guide below.

## Measure

Read the board back with $pcb's `read_board` (its checks reference has the
API): every part with its pads and their nets, every net with its tracks, vias
and pours. A board carries no pin types and no currents, so two inputs come from
elsewhere: which pads are IC power inputs (the circuit specification's pad-to-net
dicts, or the datasheets) and what current each power net carries (the user, or
the brief).

| Measurement | How | Read it as |
| --- | --- | --- |
| Decoupling missing | for each IC power pad, no capacitor pad on the same net whose other pad is on ground | **fail** unless the datasheet needs none or the capacitor sits on a differently named net; say which |
| Decoupling far | the nearest such capacitor pad is over 3 mm from the pin, pad centre to pad centre | **review**: move it beside the pin, on the same side, short return to the ground pour; bulk capacitors may sit further |
| Track too thin | a power net's narrowest track (`min(track.width for track in net.tracks)`) is below what its current needs (IPC-2221, 1 oz outer copper, 10 °C rise: roughly 0.3 mm per ampere at low currents, less per ampere as width grows) | **fail** for a power net carrying that current; widen, pour, or split across layers. A short stub at a fine-pitch pad's width is the connector's limit, not a defect, if it widens within a millimetre or two |
| Ground path | every ground pad reaches the pour: a via within a millimetre or two of each surface-mount ground pad, through-hole ground pins in the pour | **review** when a pad hangs on a thin track to a distant via |

Without a current for a power net, compute nothing: ask, or mark the check
**unverified**.

Then by inspection:

- No pour island is cut off from its net (KiCad removes islands by default; a
  kept one is copper connected to nothing).
- Power entry: reverse-polarity, inrush and ESD parts beside the connector, before
  anything else on the net.
- Thermal: regulators and FETs dissipating more than a few hundred milliwatts have
  copper area and vias under them as the datasheet asks.
- High-speed and analog nets, if any: differential pairs routed together, no
  splits under them in the reference plane, crystals with short traces and
  ground guard.

This review answers layout questions, not circuit ones: whether the circuit
works is the datasheets' and the designer's, and the report says which kind a
finding is.

## Worked reasoning example

The following numbers are illustrative inputs, not default limits.

`U2` pad 3 (VDD) to `C8` measures 3.67 mm centre to centre. The datasheet asks
for 100 nF "as close as possible" to each supply pin. 3.67 mm on a 2-layer board
with a solid ground pour is a **review** item, not a fail: move `C8` to the pad's
side if routing allows, and say what was traded if it does not.
