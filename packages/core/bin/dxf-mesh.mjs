#!/usr/bin/env node
/**
 * Mesh a DXF drawing for the snapshot CLI: DXF text on stdin, one GLB out.
 *
 * The drawing-package Node builder this replaces baked `preview.glb` into a
 * cached package; there is no package any more (design/standalone-viewer.md
 * Phase A — the viewer parses the `.dxf` itself and meshes client-side), but
 * the HEADLESS snapshot renderer still consumes a mesh file, so this one-shot
 * produces the identical GLB on demand: parse (parseDxf) -> mesh
 * (buildDxfPreviewMeshData) -> write (writeGlb, export preset — stock
 * GLTFLoader-openable, no meshopt requirement).
 *
 * Contract:
 *   node dxf-mesh.mjs --out <abs path.glb> [--name N]  < drawing.dxf
 *   stdout is exactly one JSON line: {"ok":true,"path":...,"triangleCount":...}
 *   or {"ok":false,"error":...}. No locks, no packages, no progress protocol —
 *   this writes only the file the caller named.
 *
 * A dimensioned drawing (no cut geometry to prism) reports ok:false with a
 * reason instead of an empty mesh, matching the old builder's refusal.
 */

import fs from "node:fs";
import path from "node:path";

import { parseDxf } from "../dist/lib/dxf/parseDxf.js";
import { buildDxfPreviewMeshData } from "../dist/lib/dxf/buildPreviewMesh.js";
import {
  drawingLinesToRibbonPositions,
  dxfEngraveRibbonPositions,
  DXF_ENGRAVE_STROKE_COLOR,
} from "../dist/lib/dxf/drawingLineMesh.js";
import {
  dxfPreviewPositions,
  dxfSoupToGlbPositions,
  DXF_PREVIEW_REFERENCE_THICKNESS_MM,
} from "../dist/lib/dxf/previewGlb.js";
import { writeGlb } from "../dist/lib/glb/writeGlb.js";

function parseArgs(argv) {
  const args = {};
  for (let index = 0; index < argv.length; index += 1) {
    const token = argv[index];
    if (!token.startsWith("--")) continue;
    const next = argv[index + 1];
    if (next === undefined || next.startsWith("--")) {
      args[token.slice(2)] = "true";
    } else {
      args[token.slice(2)] = next;
      index += 1;
    }
  }
  return args;
}

function fail(message) {
  process.stdout.write(`${JSON.stringify({ ok: false, error: String(message) })}\n`);
  process.exit(1);
}

const args = parseArgs(process.argv.slice(2));
const outPath = String(args.out || "");
if (!outPath || !path.isAbsolute(outPath)) {
  fail("--out must be an absolute .glb path");
}
const name = String(args.name || "drawing");

let dxfText = "";
try {
  dxfText = fs.readFileSync(0, "utf8");
} catch (error) {
  fail(`could not read DXF from stdin: ${error.message}`);
}

try {
  const dxfData = parseDxf(dxfText, { fileRef: name });
  // Same geometry contract the deleted bake used: reference-thickness prism,
  // Y-up -> CAD Z-up soup in glTF metres — so snapshots look identical.
  let positions = new Float32Array(0);
  let renderMode = "prism";
  let prismError = null;
  try {
    const meshData = buildDxfPreviewMeshData(dxfData, DXF_PREVIEW_REFERENCE_THICKNESS_MM, null);
    positions = dxfPreviewPositions(meshData);
  } catch (error) {
    // "could not resolve any closed cut contours" is how a DOCUMENT profile
    // (dimensions, sections, a title block) arrives here; kept to rethrow when
    // the fallback below also has nothing to draw.
    prismError = error;
  }
  // ENGRAVE/score markings: the drawing's serial numbers, score lines, witness
  // lines and dimension callouts. They are not cut contours, so the prism above
  // never sees them — without this primitive an engraved plate snapshots as a
  // blank sheet, which is what `cadgen dxf snapshot` used to do.
  //
  // elevationSign -1: `dxfSoupToGlbPositions` maps mesher +y to CAD -Z, so the sheet's
  // top face in the rendered scene is its MINUS-y side in the mesher's frame. Marking
  // the +y side puts every stroke under the plate, where it renders as nothing at all.
  const engravePositions = positions.length
    ? dxfSoupToGlbPositions(
        dxfEngraveRibbonPositions(dxfData, DXF_PREVIEW_REFERENCE_THICKNESS_MM, {
          elevationSign: -1,
        }),
      )
    : new Float32Array(0);
  if (!positions.length) {
    // A document profile is still a drawing: render its line work as hairline
    // ribbons in the sheet plane, the mesh twin of the viewer's LineSegments
    // rendering. Text markings are not drawn (the viewer rasterizes strings
    // itself), so a dimensioned drawing snapshots as its line graphics.
    //
    // Converted through the SAME axis map and mm->metre scale as the prism: the
    // ribbon builder emits in the mesher's Y-up frame, and handing that straight
    // to writeGlb stood the sheet on its edge at a thousand times its size.
    positions = dxfSoupToGlbPositions(drawingLinesToRibbonPositions(dxfData));
    renderMode = "lines";
  }
  const triangleCount = (positions.length + engravePositions.length) / 9;
  if (!triangleCount) {
    if (prismError) {
      throw prismError;
    }
    fail("the DXF has no renderable geometry (no cut contours and no line work)");
  }
  // A stroke is ink, not sheet: shading alone cannot separate a marking floating
  // 0.03 mm over the face from the face itself, so both stroke primitives carry
  // the engrave colour explicitly. writeGlb makes one material per primitive.
  const primitives = renderMode === "lines"
    ? [{ positions, name, color: DXF_ENGRAVE_STROKE_COLOR }]
    : [{ positions, name }];
  if (engravePositions.length) {
    primitives.push({
      positions: engravePositions,
      name: `${name}_engrave`,
      color: DXF_ENGRAVE_STROKE_COLOR,
    });
  }
  const glb = writeGlb(
    { primitives, name, units: "mm" },
    // upAxis: "z" — the positions above went through dxfSoupToGlbPositions, which
    // rotates the mesher's Y-up frame into CAD Z-up. This file is therefore NOT in the
    // glTF convention, and the declaration is what keeps the sheet lying flat instead of
    // being rotated a second time by the viewer's Y-up correction.
    { preset: "export", sourceKind: "dxf", occurrenceIdPrefix: "dxf", upAxis: "z" },
  );
  fs.mkdirSync(path.dirname(outPath), { recursive: true });
  const temporary = `${outPath}.${process.pid}.tmp`;
  fs.writeFileSync(temporary, glb);
  fs.renameSync(temporary, outPath);
  process.stdout.write(
    `${JSON.stringify({ ok: true, path: outPath, triangleCount, renderMode, bytes: glb.length })}\n`,
  );
} catch (error) {
  fail(error && error.stack ? error.stack.split("\n")[0] : error);
}
