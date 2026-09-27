import { SCENE_QUALITY, resolveSceneQuality } from "@text-to-cad/core/common/sceneSettings.js";
import { previewDisplaySettings } from "../view-settings/viewerDisplaySettings.js";

// The two ways one viewport draws the SAME Display settings. The settings are the file's and are
// carried between the two unchanged; a profile decides only how the model and its environment
// are rendered.
//
// TOOLS, the regular view, is for working on the model: picking, hover, overlays, handles and
// the tool effects are live, the scene is drawn at the quality the Display
// settings resolve to, and the pixel ratio drops while the camera moves so a gesture stays
// responsive.
//
// PREVIEW is for looking at it: no picking, overlays or tool effects, the routines playing and
// the camera orbiting. It is drawn one scene-quality tier up (finer tessellation, a higher idle
// pixel ratio, and at the top tier larger shadow and environment maps), and keeps its full pixel
// ratio while it moves: an orbit never rests, so the interaction drop would be all it ever showed.
export const VIEWER_RENDER_PROFILE = Object.freeze({ TOOLS: "tools", PREVIEW: "preview" });

const PREVIEW_QUALITY_TIER = Object.freeze({
  [SCENE_QUALITY.INTERACTIVE]: SCENE_QUALITY.STANDARD,
  [SCENE_QUALITY.STANDARD]: SCENE_QUALITY.HIGH,
  [SCENE_QUALITY.HIGH]: SCENE_QUALITY.HIGH
});

/** The scene quality preview draws a scene resolved at `quality` with: the next tier up, capped at High. */
export function previewSceneQuality(quality) {
  const id = PREVIEW_QUALITY_TIER[quality?.id] || SCENE_QUALITY.STANDARD;
  return id === quality?.id ? quality : resolveSceneQuality(id);
}

/**
 * A resolved scene (`resolveViewSceneSettings`'s) as `profile` draws it. TOOLS is the scene
 * itself; PREVIEW suspends the tool effects and raises the quality — never a Display setting.
 */
export function sceneForRenderProfile(scene, profile) {
  if (profile !== VIEWER_RENDER_PROFILE.PREVIEW || !scene) return scene;
  return { ...scene, display: previewDisplaySettings(scene.display), quality: previewSceneQuality(scene.quality) };
}

/** Whether the viewport keeps its idle pixel ratio while the camera moves. */
export function renderProfileKeepsPixelRatio(profile) {
  return profile === VIEWER_RENDER_PROFILE.PREVIEW;
}
