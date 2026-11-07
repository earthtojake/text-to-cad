// A viewport outside the renderer shell: what `ShellViewport.jsx` needs from the view settings when
// nothing else applies them. Preview's own view (`PreviewView.jsx`) is one; a flat view's frame
// showing a 3D view of its picture is another. The shell (`useRendererShell.js`) applies its own, the
// same way, through the same pieces: `useAppliedViewSettings` and `projectionControl`.
import { useLayoutEffect, useMemo } from "react";
import { useAppliedViewSettings } from "../view-settings/useAppliedViewSettings.js";
import { useViewSettings } from "../view-settings/useViewSettings.js";

/**
 * The projection as Projection's tile on the strip and a phone's More row switch it: the view's
 * settings' own, written back through its store. `used(value)` counts the press, where the view counts them.
 */
export function projectionControl(store, scene, used = null) {
  return {
    value: scene.view.camera.projection,
    onChange: value => { used?.(value); store.patch({ camera: { projection: value } }); }
  };
}

/**
 * The applied view settings as a viewport's props: one coordinator over `desired` for the viewport in
 * `viewRef` (`scope`: what the viewport shows; a new one starts afresh). `update` is the coordinator's
 * result, the scene it has applied and its binding.
 * @returns {{ update: ReturnType<typeof useAppliedViewSettings>, props: object }}
 */
export function useStageView(desired, scope, viewRef, store = null) {
  const update = useAppliedViewSettings(desired, scope, viewRef, store);
  const drawn = update.scene;
  const props = {
    projection: drawn.camera.projection,
    focalLength: drawn.camera.focalLength,
    themeSettings: drawn.theme,
    displaySettings: drawn.display,
    appearance: drawn.appearance,
    receiveShadows: drawn.view.lighting.enabled,
    renderMode: drawn.render.enabled,
    renderConfiguration: drawn.render.configuration,
    quality: drawn.quality,
    viewUpdate: update
  };
  return { update, props };
}

/**
 * A 3D view of a picture that is not a model (a flat view's, turned): its own view settings — the
 * projection the person chooses, no grid and no floor, its stage's background `background` (the colour
 * the flat view's own canvas is) — applied to the viewport in `viewRef`.
 *
 * @param {{ appearance: "light" | "dark", scope: string, viewRef: object, background: string,
 *   projection?: string | null, onProjectionChange?: (projection: string) => void }} options
 *   `projection`: the one the view was left with; `onProjectionChange`: told as it changes, to keep it.
 */
export function useStageViewport({ appearance, scope, viewRef, background, projection = null, onProjectionChange = null }) {
  const settings = useViewSettings(appearance);
  const { store, scene } = settings;
  // Before the first paint: the grid off, and the projection it was left with.
  useLayoutEffect(() => { store.restore({ grid: false, ...(projection ? { camera: { projection } } : {}) }); }, [store]);
  const desired = useMemo(() => (scene.theme ? { ...scene, theme: { ...scene.theme, floor: { ...scene.theme.floor, enabled: false },
    background: { ...scene.theme.background, type: "solid", solidColor: background } } } : scene), [scene, background]);
  const stage = useStageView(desired, scope, viewRef, null);
  const control = projectionControl(store, scene, onProjectionChange);
  return { ...stage, projection: control, store };
}
