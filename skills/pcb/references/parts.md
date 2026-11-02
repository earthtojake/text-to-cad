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
