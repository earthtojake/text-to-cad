import { buildDxfDrawingLineGroups, drawingLineBounds } from "@hardcore/core/lib/dxf/buildDrawingLines.js";

// ACI 7 is the DXF "default ink" colour: it means "whatever reads against the background",
// which is why a package resolves it to a near-white grey suited to a dark sheet. Taking that
// literally paints a drawing invisible on a light theme, so only a layer that names a real
// colour gets its own; the rest use this slate, which reads on both themes. Deliberately a
// theme-independent constant.
const DEFAULT_INK = 0x5f6775;

// Mesher space is Y-up; the scene is CAD Z-up. (x, y, z) -> (x, z, -y), a rotation about X
// with determinant +1 — the same map the flat pattern rides, so a drawing and a layout share
// one orientation, one camera fit and one set of view controls.
function toCadSpace(source) {
  const mapped = new Float32Array(source.length);
  for (let index = 0; index < source.length; index += 3) {
    mapped[index] = source[index];
    mapped[index + 1] = source[index + 2];
    mapped[index + 2] = -source[index + 1];
  }
  return mapped;
}

/**
 * The DOCUMENT presentation: a dimensioned drawing — plan views, sections, centre lines, a
 * title block — drawn as what it is, one `LineSegments` per layer and no mesh at all. It
 * encloses nothing to extrude, so there is no flat pattern, and the only setting that reaches
 * it is which layers are visible.
 *
 * It is also what a LAYOUT falls back to when its contours will not mesh.
 *
 * @param {typeof import("three")} THREE
 * @param {object} dxf  `parseDxf` output, in millimetres.
 * @returns {import("./presentation.js").DxfPresentation | null}  Null when there is no line-work.
 */
export function createDxfDocumentPresentation(THREE, dxf) {
  const { layers: lineLayers } = buildDxfDrawingLineGroups(dxf);
  if (!lineLayers.length) return null;
  const tableColors = new Map((Array.isArray(dxf?.layers) ? dxf.layers : [])
    .map(layer => [layer?.name, Number(layer?.colorAci) === 7 ? null : layer?.colorHex]));

  const root = new THREE.Group();
  root.name = "dxf-lines";
  for (const layer of lineLayers) {
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.BufferAttribute(toCadSpace(layer.positions), 3));
    const colorHex = tableColors.get(layer.name);
    const segments = new THREE.LineSegments(geometry, new THREE.LineBasicMaterial({
      color: typeof colorHex === "string" && colorHex ? new THREE.Color(colorHex) : new THREE.Color(DEFAULT_INK),
      transparent: false
    }));
    segments.userData.dxfDrawingLayer = layer.name;
    root.add(segments);
  }
  // A drawing has no mesh for the camera to frame, so its own extent stands in.
  const box = drawingLineBounds({ layers: lineLayers });
  const restBounds = box
    ? { min: [box.min[0], box.min[2], -box.max[1]], max: [box.max[0], box.max[2], -box.min[1]] }
    : { min: [0, 0, 0], max: [0, 0, 0] };

  let disposed = false;
  return {
    kind: "document",
    object3D: root,
    restBounds,
    update(settings) {
      if (disposed) return;
      // A line-work presentation IS its layers: hiding one hides its object, nothing rebuilds.
      const hidden = new Set(Array.isArray(settings.hiddenLayers) ? settings.hiddenLayers : []);
      for (const child of root.children) child.visible = !hidden.has(child.userData.dxfDrawingLayer);
    },
    dispose() {
      if (disposed) return;
      disposed = true;
      root.removeFromParent();
      for (const child of root.children) {
        child.geometry.dispose();
        child.material.dispose();
      }
    }
  };
}
