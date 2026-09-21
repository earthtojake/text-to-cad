// A DXF's TEXT/MTEXT entities, drawn as canvas-textured planes lying on the sheet: string,
// height and rotation from the file; no font tables, no glyph outlines.
//
// The canvas is the expensive part and it depends on NOTHING that a slider moves — only the
// string, its colour and its height. So it is built once per distinct label and kept; a
// thickness or bend change re-places the planes and repaints not one pixel of text.

const FONT_PX = 64;
const FONT_SPEC = `600 ${FONT_PX}px ui-sans-serif, system-ui, sans-serif`;
const DEFAULT_TEXT_COLOR = "#8a93a3";

/**
 * The pool of text planes under one group, with its label cache.
 *
 * @param {typeof import("three")} THREE
 * @returns {{ group: import("three").Group,
 *   update(markings: object[], place: (marking: object, size: { width: number, height: number }) =>
 *     { position: number[], basis: import("three").Matrix4 } | null): void,
 *   dispose(): void }}
 */
export function createDxfTextMarkings(THREE) {
  const group = new THREE.Group();
  group.name = "dxf-texts";
  // key -> { geometry, material, texture, width, height }: one per distinct label.
  const labels = new Map();
  const meshes = [];

  const label = (value, colorHex, heightMm) => {
    const key = JSON.stringify([heightMm, colorHex, value]);
    const cached = labels.get(key);
    if (cached) return cached;
    const canvas = document.createElement("canvas");
    const measure = canvas.getContext("2d");
    if (!measure) return null;
    measure.font = FONT_SPEC;
    const firstLine = value.split("\n")[0];
    const textWidthPx = Math.max(measure.measureText(firstLine).width, FONT_PX * 0.5);
    canvas.width = Math.ceil(textWidthPx) + 8;
    canvas.height = Math.ceil(FONT_PX * 1.35);
    // Sizing the canvas resets its state, so the draw context is configured after.
    const paint = canvas.getContext("2d");
    paint.font = FONT_SPEC;
    paint.fillStyle = colorHex;
    paint.textBaseline = "alphabetic";
    paint.fillText(firstLine, 4, FONT_PX);
    const texture = new THREE.CanvasTexture(canvas);
    texture.colorSpace = THREE.SRGBColorSpace;
    const width = heightMm * (canvas.width / FONT_PX);
    const height = heightMm * (canvas.height / FONT_PX);
    const entry = {
      texture, width, height,
      geometry: new THREE.PlaneGeometry(width, height),
      material: new THREE.MeshBasicMaterial({ map: texture, transparent: true, depthWrite: false, side: THREE.DoubleSide })
    };
    labels.set(key, entry);
    return entry;
  };

  return {
    group,
    update(markings, place) {
      let used = 0;
      // A headless build (node tests, SSR) has no canvas: a DXF's labels are simply not drawn.
      if (typeof document !== "undefined") {
        for (const marking of markings) {
          const value = String(marking?.value || "").trim();
          if (!value) continue;
          const heightMm = Math.max(Number(marking.heightMm) || 2.5, 0.2);
          const entry = label(value, marking.colorHex || DEFAULT_TEXT_COLOR, heightMm);
          if (!entry) continue;
          const placement = place(marking, entry);
          if (!placement) continue;
          let mesh = meshes[used];
          if (!mesh) {
            mesh = new THREE.Mesh(entry.geometry, entry.material);
            mesh.renderOrder = 2;
            meshes.push(mesh);
            group.add(mesh);
          }
          mesh.geometry = entry.geometry;
          mesh.material = entry.material;
          mesh.position.set(placement.position[0], placement.position[1], placement.position[2]);
          mesh.quaternion.setFromRotationMatrix(placement.basis);
          mesh.visible = true;
          used += 1;
        }
      }
      for (let index = used; index < meshes.length; index += 1) meshes[index].visible = false;
    },
    dispose() {
      for (const mesh of meshes) group.remove(mesh);
      meshes.length = 0;
      for (const entry of labels.values()) {
        entry.geometry.dispose();
        entry.material.dispose();
        entry.texture.dispose();
      }
      labels.clear();
      group.removeFromParent();
    }
  };
}
