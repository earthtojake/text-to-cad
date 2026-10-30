/**
 * The FEA result viewer GlbRenderer loads only for a GLB that carries a result (`cadgen fea solve`): one module, so the
 * bundler makes it a chunk of its own and a plain GLB never fetches it. Everything GlbRenderer uses of the FEA viewer
 * is here, by name.
 */
import { useLayoutEffect } from "react";
import { clamp } from "@text-to-cad/core/common/numbers.js";
import { framingInset } from "./feaChrome.js";

export { default as FeaSurface } from "./FeaSurface.jsx";
export { default as FeaStudyPanel, FaceCard } from "./FeaStudyPanel.jsx";
export { default as FeaColourBar } from "./FeaColourBar.jsx";
export { default as FeaLoadLabels } from "./FeaLoadLabels.jsx";
export {
  applyDeformation, faceIndices, facePartDetail, faceTitle, facePromptSummary, faceRole, feaControls, feaShowsParts,
  feaVerdict, findingSelector, pickFace, readFeaResult, recolorByField, resultSourcePath, partRows, studySections, weakestPartIndex
} from "./feaResult.js";
export { createFeaMarkers, markerGateText } from "./feaMarkers.js";
export { feaDrawnBounds } from "./feaBounds.js";

/**
 * A result's routine, which Preview and the sidebar's Animation play: the Load ramp, the load going on from none
 * to the load shown over `duration` seconds, colours, deformation and markers together.
 */
export const LOAD_RAMP = Object.freeze({ id: "fea:load-ramp", key: "fea.loadRamp", duration: 2 });
// What the markers are drawn in. The theme has no colour of its own to spare: every saturated hue is
// the ramp's or the chosen faces' magenta, so a load is the ink and a fixture a muted grey.
export const MARKER_COLOURS = Object.freeze({
  light: Object.freeze({ load: "#18181b", fixture: "#71717a", halo: "rgba(255, 255, 255, 0.9)" }),
  dark: Object.freeze({ load: "#fafafa", fixture: "#a1a1aa", halo: "rgba(18, 19, 21, 0.9)" }),
});

/** Study's row for a face, where it has one (a fixed face, a loaded face), so a pick of it marks that row. */
export function faceRow(rows, ref) {
  for (const row of rows) {
    const found = row.faces?.length === 1 && row.faces[0] === ref && !row.children ? row : row.children ? faceRow(row.children, ref) : null;
    if (found) return found;
  }
  return null;
}

/** A control's value: what was chosen, where it is still one of the control's; else its default. */
export function controlValue(control, chosen) {
  if (control.type === "enum") return control.options.some((option) => option.value === chosen) ? chosen : control.defaultValue;
  return Number.isFinite(chosen) ? clamp(chosen, control.min, control.max) : control.defaultValue;
}

// Study's setup rows by the marker kind they stand for: a row `<row kind>:<group>` chooses its entry's markers.
const ROW_MARKERS = Object.freeze({ load: "load", fixed: "fixture", roller: "roller", body: "body_load" });

/**
 * Whether a marker is of what Study chose: a setup row's markers (a load's arrows on its faces, a
 * fixed row's cones, a roller row's cones on their plates; a body load's by its row alone, standing on
 * no face), and every marker on a face picked on the result. A part or a joint has none.
 */
export function markerChosen(faces, site) {
  const [kind, group] = String(faces.id).split(":");
  const own = ROW_MARKERS[kind];
  const ofRow = own === site.kind && (group === undefined || Number(group) === site.group);
  if (!site.ref) return ofRow;
  if (!faces.faces.includes(site.ref)) return false;
  if (own) return ofRow;
  return kind !== "joint";
}

/**
 * A result's camera frames the model right of the chrome on its left (the file sidebar, Study or Parts
 * open in it) and above the colour bar: the viewport reads what they cover whenever it fits the camera
 * (`runtime.framingInset`, read at the fit, so a section opened or widened since counts as it is then). Installed before the shell's first fit of the result: a child's layout effect runs first.
 */
export function FeaFraming({ runtimeRef, hostRef }) {
  useLayoutEffect(() => {
    const runtime = runtimeRef.current;
    if (!runtime) return undefined;
    runtime.framingInset = () => framingInset(hostRef.current);
    return () => { if (runtime.framingInset) delete runtime.framingInset; };
  }, [runtimeRef, hostRef]);
  return null;
}
