import { extractOrderedDxfBendLines } from "@hardcore/core/lib/dxf/buildPreviewMesh.js";
import { dxfDataIsDocument } from "@hardcore/core/lib/dxf/parseDxf.js";
import { createDxfDocumentPresentation } from "./presentation/document.js";
import { createDxfLayoutPresentation } from "./presentation/layout.js";

/**
 * The DXF renderer's scene (`kit/scene.js`): one owned group holding ONE presentation, chosen
 * from the parse (`presentation/presentation.js`).
 *
 *  - a LAYOUT — closed cut contours — is a flat pattern that folds, with the drawing's
 *    annotations on its top face;
 *  - a DOCUMENT — a dimensioned drawing, which encloses nothing — is its line-work.
 *
 * A layout whose contours will not mesh falls back to the document presentation and says so
 * through `meshFailure`; the alternative is an empty scene under an endless spinner.
 *
 * A renderer reads `presentation` to decide what it offers: which Inspector tabs, which tools,
 * and whether 2D/3D means anything (a document is already a plan). Adding a third presentation
 * is a file under `presentation/` and a branch here.
 *
 * @param {typeof import("three")} THREE
 * @param {object} dxf  `parseDxf` output — already scaled to millimetres, the scene's unit.
 * @returns {import("../kit/scene.js").KitScene & { presentation: string, bendLines: object[],
 *   layers: object[], meshFailure: Error | null, update(settings: object): void }}
 */
export function createDxfScene(THREE, dxf) {
  const layers = Array.isArray(dxf?.layers) ? dxf.layers : [];
  let bendLines = [];
  try {
    bendLines = extractOrderedDxfBendLines(dxf).map(line => ({ start: line.start, end: line.end }));
  } catch { bendLines = []; }

  let presentation = null;
  let meshFailure = null;
  if (!dxfDataIsDocument(dxf)) {
    try {
      presentation = createDxfLayoutPresentation(THREE, dxf, {
        bendLines,
        layerKinds: new Map(layers.map(layer => [layer.name, String(layer.kind || "").toLowerCase()])),
        layerColors: new Map(layers.map(layer => [layer.name, layer.colorHex]))
      });
    } catch (error) {
      meshFailure = error instanceof Error ? error : new Error(String(error));
    }
  }
  presentation ||= createDxfDocumentPresentation(THREE, dxf);

  const root = new THREE.Group();
  root.name = "dxf-document";
  if (presentation) root.add(presentation.object3D);
  const restBounds = presentation?.restBounds || { min: [0, 0, 0], max: [0, 0, 0] };

  let disposed = false;
  return {
    object3D: root,
    bounds: restBounds,
    restBounds,
    presentation: presentation?.kind || "document",
    bendLines: presentation?.kind === "layout" ? bendLines : [],
    layers,
    meshFailure,
    setSurfaceLook(look) { if (!disposed) presentation?.setSurfaceLook?.(look); },
    update(settings) { if (!disposed) presentation?.update(settings); },
    dispose() {
      if (disposed) return;
      disposed = true;
      root.removeFromParent();
      presentation?.dispose();
    }
  };
}
