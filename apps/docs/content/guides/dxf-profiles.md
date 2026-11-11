---
title: DXF profiles and flat patterns
description: Ask for a 2D profile, gasket or flat pattern and get a checked DXF cut file for laser, plasma or waterjet cutting, with a cut-file check for sheet metal.
---

A DXF is the 2D file that laser, plasma, waterjet and routing shops cut from. Your agent draws the profile as a model, derives it from a 3D part when there is one, and writes the DXF only after a set of drawing checks pass. You end up with a `.dxf` in millimetres, a picture of it, and a check of whether it is a well-formed cut layout.

## What to ask

- "Draw a gasket, 60 by 40 mm, with a 4.5 mm hole, as a DXF for waterjet cutting."
- "Make the flat pattern of this plate as a DXF for a laser. It is 3 mm 5052 aluminium and I want 0.15 mm kerf compensation."
- "Make a DXF of the outline of `vendor_panel.step`."
- "Check `part.dxf` for laser cutting. It is 3 mm aluminium, drawn in millimetres."

## What your agent does

1. **Writes the drawing as a model.** A drawing is a `@model` function with no parameters that returns build123d 2D geometry on z=0. One returned shape is one layer, `CUT`.

   ```python
   import build123d as bd
   from cad import model

   HOLE_D = 4.5


   @model
   def gasket():
       with bd.BuildSketch() as cut:
           bd.Rectangle(60, 40)
           bd.Circle(HOLE_D / 2, mode=bd.Mode.SUBTRACT)
       return cut.sketch


   if __name__ == "__main__":
       gasket()
   ```

   When a drawing needs more than one CAM operation, it returns a `Compound` of children, and each child's label is its layer (`CUT`, `ENGRAVE`). A bend or fold line goes on a layer whose name contains `bend` or `fold`.
2. **Derives the profile from the part when there is one.** A drawing script sits beside the model it comes from, calls it, and uses `flat_pattern(shape, coordinate=, kerf=)` from `cad.build123d`. For a vendor STEP with no source, it reads the file with `step.read` first. Kerf is added with `offset_profile` or `kerf=`, never by hand-offsetting coordinates.
3. **Builds and exports.**

   ```bash
   cad run src/gasket.py
   cad model export "$ID" DXF/gasket.dxf
   ```

   `cad run` writes nothing. The export runs the drawing checks first and refuses the file if one fails: units are set, nothing is drawn twice, no entity has zero length, every cut profile closes, and something is drawn. Open geometry is allowed only on bend, engraving and reference layers.
4. **Looks at the file.** `cad dxf snapshot DXF/gasket.dxf tmp/gasket.png` draws the DXF itself, whole and from above, in the pens the file declares. A dimension you gave is checked by reading the file with `ezdxf`.
5. **Checks the cut file for sheet work** when a thickness or a process is named:

   ```bash
   cad dxf dfm part.dxf --process sheet --material aluminum --thickness 3 --kerf 0.2
   ```

   It reads every entity on a cut layer as a cutter would. It reports open contours, curves cut twice, contours that cross, pieces that fall out of a hole, and holes, webs and gaps that are small against the thickness. A file that declares no units is `NOT CHECKED` until you or your agent state them with `--units mm`.
6. **Unfolds bent parts.** For a folded STEP or model the sheet check unfolds it with a K-factor and measures the flat pattern. Without the shop's `--k-factor` it reads one from a chart and says so, and the flat is not a production blank.

## What you get

- **A DXF in millimetres**, normally in a `DXF/` folder, with `$INSUNITS` set. Arcs stay arcs and holes stay circles, kerf included. An unchanged drawing exports an identical file on any machine.
- **A snapshot PNG** of the file, drawn on white paper whatever the viewer's theme.
- **The viewer's drawing pane.** Open the exported `.dxf` in the CAD Viewer for a read-only 2D drawing with its layers. You can select entities, measure, and send what you picked back to your agent. The model's own page only shows a flat face in 3D.
- **A cut-file verdict**: `OK`, `FAILED` or `NOT CHECKED`, with each finding at the geometry it names. The states are the ones in [manufacturing checks](/docs/guides/manufacturing-checks).

## Limits

- A DXF is made from 2D geometry on z=0 only. The export refuses a solid, and a face taken from a solid must be moved onto the plane first.
- `flat_pattern` selects faces at one height. It lays out a flat plate, not a folded part, and faces laid side by side are not an unfolded blank with bend allowance.
- The drawing checks show a file is well formed as a cut layout. They do not show a shop can cut it. A shop's own upload checks, material limits and kerf rules still apply, and a clean file does not show that every bend can be made.
- A cut file has no bend radius, so holes near a bend line are held to the least any bend needs. The full distances are checked on the bent part.
- Say whether a file is drawn to the finished size or already offset for kerf. Offsetting twice takes the kerf off twice.

## Go deeper

- [Manufacturing checks](/docs/guides/manufacturing-checks) explains the verdicts and the sheet-metal rules. [SendCutSend](/docs/guides/sendcutsend) covers ordering cut parts. [Parts and assemblies](/docs/guides/parts-and-assemblies) covers the models a flat pattern comes from.
- Document types: [DXF](/docs/document-types/dxf) and [STEP](/docs/document-types/step). Integration: [build123d](/docs/integrations/build123d).
- In the repository: [the cad skill](repo:skills/cad/SKILL.md), [2D profiles and DXF](repo:skills/cad/references/2d-profiles-and-dxf.md), [sheet metal](repo:skills/cad/references/manufacturing-sheet-metal.md), [cut files](repo:skills/cad/references/manufacturing-sheet-metal.md#cut-files-dxf) and [exports](repo:skills/cad/references/exports.md).
