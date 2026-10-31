import { resolveCadEdgeSettings } from "../../common/cadInk.js";
import { syncMaterialClipPlanes } from "./clipPlane.js";
import {
  PART_HOVER_EMISSIVE_INTENSITY, PART_HOVER_HIGHLIGHT_BLEND, PART_SELECTED_EMISSIVE_INTENSITY,
  PART_SELECTED_HIGHLIGHT_BLEND, partHighlightSurfaceColor, syncPartOcclusionGhost
} from "./partHighlight.js";
import { REFERENCE_HOVER_COLOR } from "./referenceGeometry.js";

const HIGHLIGHT_RENDER_ORDER = 23;

/**
 * The selection and hover ink over a family's scene whose surfaces a look dresses
 * (`surfaceLook.js`): a robot's links, a GLB's nodes, a 3MF's objects. A pick wears the colour a
 * selected STEP part does, drawn over its neighbours and, where something hides it, as a ghost
 * through what hides it; what the pointer rests on is lit fainter, and never ghosted. A highlight
 * puts back what it changed of a material before the look is applied again: the look restores
 * every base it owns, and a material it does not own (an unlit one a GLB authored) is the file's.
 *
 * @param {typeof import("three")} THREE
 * @param {{ apply(look: object | null): void }} look
 * @returns {{ apply(look: object | null, ink: { hovered?: { mesh: object }[], selected?: { mesh: object }[] },
 *   clipPlanes?: object[]): void, dispose(): void }}
 *   `apply`: the look, then the ink over it. Records are the scene's own, one per mesh; a record
 *   keeps its ghost (`ghostRecord`) from one selection to the next.
 */
export function createSceneHighlight(THREE, look) {
  const hoverColor = new THREE.Color(REFERENCE_HOVER_COLOR);
  const selectedColor = new THREE.Color(resolveCadEdgeSettings().highlightColor);
  const highlighted = new Map();
  const ghosted = new Set();
  function paint(record, selected) {
    const material = record.mesh.material;
    if (!material?.color || highlighted.has(record)) return;
    highlighted.set(record, { material, color: material.color.clone(), emissive: material.emissive?.clone() ?? null,
      emissiveIntensity: material.emissiveIntensity, transparent: material.transparent, opacity: material.opacity });
    // Unlit authored materials are not dressed by surfaceLook. Keep their
    // normal base hue too, before the temporary highlight changes it.
    record.mesh.userData.cadBaseColor = material.color.clone();
    const color = selected ? selectedColor : hoverColor;
    material.color.copy(partHighlightSurfaceColor(THREE, material.color, color, selected ? PART_SELECTED_HIGHLIGHT_BLEND : PART_HOVER_HIGHLIGHT_BLEND));
    if (material.emissive) {
      material.emissive.copy(color);
      material.emissiveIntensity = selected ? PART_SELECTED_EMISSIVE_INTENSITY : PART_HOVER_EMISSIVE_INTENSITY;
    }
    // A highlighted surface is drawn after its neighbours, opaque: the cue must not
    // depend on the surface opacity the Display tab set.
    if (!material.transparent) { material.transparent = true; material.needsUpdate = true; }
    material.opacity = 1;
    record.mesh.renderOrder = HIGHLIGHT_RENDER_ORDER;
  }
  return {
    apply(lookSettings, { hovered = [], selected = [] } = {}, clipPlanes = []) {
      for (const [record, was] of highlighted) {
        record.mesh.renderOrder = 0;
        syncPartOcclusionGhost(THREE, record.ghostRecord, { visible: false });
        const { material } = was;
        material.color.copy(was.color);
        if (was.emissive) { material.emissive.copy(was.emissive); material.emissiveIntensity = was.emissiveIntensity; }
        if (material.transparent !== was.transparent) { material.transparent = was.transparent; material.needsUpdate = true; }
        material.opacity = was.opacity;
      }
      highlighted.clear();
      look.apply(lookSettings);
      const picked = new Set(selected);
      // Selection outranks hover: hovering what is already picked must not weaken it.
      for (const record of hovered) if (!picked.has(record)) paint(record, false);
      for (const record of selected) {
        paint(record, true);
        // Only a SELECTED part shows through what hides it.
        record.ghostRecord ||= { mesh: record.mesh, geometry: record.mesh.geometry, partId: record.mesh.userData.partId, baseColor: selectedColor };
        syncPartOcclusionGhost(THREE, record.ghostRecord, { visible: true, color: selectedColor });
        syncMaterialClipPlanes(record.ghostRecord.ghostMaterial, clipPlanes);
        ghosted.add(record);
      }
    },
    dispose() {
      for (const record of ghosted) {
        record.ghostRecord?.ghostMesh?.removeFromParent();
        record.ghostRecord?.ghostMaterial?.dispose();
        record.ghostRecord = null;
      }
      ghosted.clear();
      highlighted.clear();
    }
  };
}
