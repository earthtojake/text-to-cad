# FDM Printability Reference Values

Typical value ranges observed for desktop FDM printing. **Every value here
is reference-only and non-binding.** They exist so you can sanity-check a
design when the user gave no explicit requirement — they are not defaults
you must assert, and no part type is required to satisfy any of them. When
the user or a design note states a requirement, that requirement wins.

## Walls and features

- Minimum wall thickness: 0.8-1.2 mm for a single-extrusion wall with a
  0.4 mm nozzle; 1.5-2.0 mm for a wall that should survive handling.
  Structural walls are usually 2.0 mm and up.
- Minimum feature/pin diameter: roughly 2-3 mm below which FDM features
  become fragile and dimensionally unreliable.
- Embossed/debossed text or detail: about 0.4-0.6 mm of depth/height to
  survive slicing.

## Overhangs and supports

- Self-supporting overhang angle: up to about 45 degrees from vertical is
  routinely printable; 50-60 degrees often works with tuned cooling;
  beyond that, expect support material or surface degradation.
- Bridging: short horizontal spans of roughly 5-10 mm usually print
  without support; longer spans sag.

## Holes and fits

- Horizontal holes print slightly small due to arc sag; expect to oversize
  by about 0.1-0.3 mm for clearance fits.
- Typical clearance fits: about 0.15-0.3 mm radial clearance for a slip
  fit; 0.05-0.15 mm for a snug fit. Press fits are material- and
  printer-dependent.
- First-layer elephant's foot can shrink bottom-edge dimensions by about
  0.1-0.4 mm; chamfered bottom edges mitigate it.

## Tolerances and accuracy

- General dimensional accuracy of a calibrated desktop FDM printer:
  roughly +/- 0.1-0.3 mm on small features, worse on long spans.
- Layer height commonly 0.12-0.28 mm with a 0.4 mm nozzle; Z resolution is
  quantized to layer height, so Z-critical dimensions should land on a
  layer multiple.

## Warping and orientation

- Large flat bases in ABS/ASA warp without an enclosure; PLA is far more
  forgiving.
- Part strength is anisotropic: layers delaminate under Z tension. A part
  loaded in tension across its layer lines may need reorientation or a
  redesign, which no mesh check can detect — flag it in the design note
  instead.
