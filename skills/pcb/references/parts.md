# Parts and footprints

Read this to choose a part or its footprint, to give a part a 3D model, or to draw a footprint.

## Check the footprint against the datasheet

Pad numbering, pitch, body outline, exposed pad, polarity, courtyard and connector mating direction: a name
or a rendering does not prove a match, so read the library footprint before placing it and measure its pads
(`kicad_pcb.read`) against the datasheet's drawing. Several pads may share one number (a shield, a thermal
pad's islands): check connectivity and geometry across them all ([checks](checks.md#read-it)). A hole
without copper is not an electrical pad.

Derate from the maker's data, not the nominal value: a class II ceramic (X5R, X7R) keeps only part of its
capacitance under DC bias, less in a smaller package (the maker's curve at the working voltage:
[Murata SimSurfing](https://ds.murata.com/simsurfing/index.html), [KEMET K-SIM](https://ksim3.kemet.com/)),
so use C0G where the value must hold (RF matching, timing, filters, an audio path). An inductor's saturation
current is held against the peak current, a resistor's rating against what it dissipates.

## Libraries, part numbers and the BOM

A board embeds its footprints, so it opens without their libraries. A netlist import and DRC's library
checks read them through the project's `fp-lib-table`, beside the `.kicad_pro`: a project library is a
`.pretty` folder of `.kicad_mod` files, listed as
`(lib (name "parts")(type "KiCad")(uri "${KIPRJMOD}/parts.pretty")(options "")(descr ""))`. A row naming a
stock library (`${KICAD9_FOOTPRINT_DIR}/...`) is read in the KiCad the person installed
([SKILL.md](../SKILL.md#setup)). Hand a board over with its project libraries.

Manufacturer and part number live in the schematic's fields (`MPN`, `LCSC`) and DNP on its symbols, and the
BOM, with its quantities, is exported from them ([manufacturing](manufacturing.md#exports)), never
inferred from the board's pads. Never edit an exported BOM: change the schematic's field and export it
again, since a hand edit to the CSV disagrees with the board and is lost at the next export.

## 3D models

A part stands on the STEP its footprint names ([where it is looked for](views.md#3d-and-part-models)).
`cad kicad_pcb inspect board.kicad_pcb --json` lists the missing ones (`models.missing`, each with its
reason) before any export. Report them: an enclosure checked against a board without its parts' bodies
establishes no component clearance.

KiCad's library has no model for many parts a case is built round (keyboard switches, EC11 encoders, 3.5 mm
Eurorack jacks, 9 mm pots, several LEDs and USB-C receptacles): draw each from its datasheet with the cad
skill, export it as STEP into the project (`board.3dshapes/`), and name it in the project's copy of the
footprint as `${KIPRJMOD}/board.3dshapes/<name>.step`. Check its offset, scale and rotation in the board's
3D view.

## A new footprint

1. Look in KiCad's stock library first; a footprint there has been reviewed against its conventions.
2. Otherwise describe the land pattern from the datasheet in words and numbers (pad sizes, pitch,
   each pad's centre from the part's origin, the exposed pad, pin 1) and have the person confirm it
   before drawing it.
3. Draw it to IPC-7351B, *Generic Requirements for Surface Mount Design and Land Pattern Standard*
   (2010), and to KiCad's footprint conventions, the [KLC's F rules](https://klc.kicad.org/footprint/)
   (pads, courtyard, silkscreen, fabrication layer).
4. Place it on a board, snapshot it, and compare with the datasheet's drawing, measuring the pads from
   `kicad_pcb.read`.
