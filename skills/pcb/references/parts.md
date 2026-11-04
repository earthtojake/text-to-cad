# Parts and footprints

Check the part's datasheet against the footprint: pad numbering, pitch, body outline, exposed
pad, polarity, courtyard and connector mating direction. Names and rendered graphics alone do
not prove a match. Keep manufacturer, MPN, sourcing reference and DNP in footprint fields or a
project BOM; do not infer purchase quantities from pad count.

A native board embeds its footprints. `fp-lib-table` is needed to resolve or update the original
library, not to display an existing board. A project-local footprint library is a `.pretty`
folder containing `.kicad_mod` files, referenced with `${KIPRJMOD}`. Stock libraries use the
installed KiCad major's environment variable, such as `${KICAD9_FOOTPRINT_DIR}`. Preserve
project-local libraries when handing off a board. Read the library footprint before placing it.

Several physical pads may share one number (a shield or thermal pad). `part.pads_numbered("1")`
returns every shape for that logical pin; `part.pad("1")` returns the first. Check connectivity
and geometry across all those shapes. A hole without copper is not an electrical pad.

STEP export needs the footprint's actual 3D models. Verify model path, offset, scale and rotation.
`--subst-models` can substitute a matching STEP/IGES model for VRML. Missing models must be
reported; an enclosure check based on the bare board cannot establish component clearance.

## Derate

- A class II ceramic capacitor (X5R, X7R) loses capacitance under DC bias, more in a smaller package
  and a lower voltage rating. Read the maker's curve at the working voltage
  ([Murata SimSurfing](https://ds.murata.com/simsurfing/index.html),
  [KEMET K-SIM](https://ksim3.kemet.com/)) and choose the part for the capacitance that remains.
- C0G (NP0) for RF matching, timing and filters, with high-Q inductors in RF. No class II dielectric
  in an audio path: it is piezoelectric, so it sings and picks up vibration, and its capacitance moves
  with the signal.
- A resistor's power rating with margin over what it dissipates; thin film where noise or precision
  matters.
- An inductor's saturation current above the peak current, not the average, and its DCR within the
  loss and voltage-drop budget.

## The BOM is the schematic's

Never edit an exported BOM. Change the schematic's field (`Value`, `MPN`, `LCSC`) and export it again
(`cad kicad_sch export --to bom`): a hand edit to the CSV disagrees with the board and is lost at the
next export.

## A new footprint

1. Look in KiCad's stock library first; a footprint there has been reviewed against its conventions.
2. Otherwise describe the land pattern from the datasheet in words and numbers (pad sizes, pitch,
   each pad's centre from the part's origin, the exposed pad, pin 1) and have the person confirm it
   before drawing it.
3. Draw it to IPC-7351B, *Generic Requirements for Surface Mount Design and Land Pattern Standard*
   (2010), and to KiCad's footprint conventions, the [KLC's F rules](https://klc.kicad.org/footprint/)
   (pads, courtyard, silkscreen, fabrication layer).
4. Place it on a board, snapshot it, and compare with the datasheet's drawing, measuring the pads from
   `kicad_pcb.read`, never from the picture.
