// Preview's view: a viewport of its own, mounted over the editor's while Preview is
// open and unmounted as it closes.
//
// Its canvas, scene, camera, look and view-update coordinator are its own; only the GPU device is
// shared (`kit/viewport/gpuDevice.js`), so the model's buffers and compiled programs are uploaded
// once. The editor's viewport stays mounted underneath and is never told Preview exists:
// entering and leaving change nothing of it, and what shows when Preview closes is the editor's
// own last frame, untouched.
//
// The scene is the renderer's (`view.scene`): built for Preview by its family's own builder
// over the editor's geometry, posed and played by Preview's own pose and routine. What drives
// it from inside the viewport, if anything does (a renderer's own layers), is
// `view.overlay(viewport, drawn)`, handed the Render scene Preview draws.
import { useCallback } from "react";
import ShellViewport from "./ShellViewport.jsx";
import { useStageView } from "./useStageViewport.js";

/**
 * @param {{ view: { scene: object | null, overlay?: ((viewport: object, drawn: object) => import("react").ReactNode) | null,
 *   runtimeLifecycle?: object | null, onCameraSettled?: (() => void) | null },
 *   desired: object, modelKey: string, sceneScaleMode: string, viewRef: import("react").RefObject<object>,
 *   orbit?: boolean, orbitSpeed?: number, onPresented?: (presented: boolean) => void }} props
 */
export default function PreviewView({ view, desired, modelKey, sceneScaleMode, viewRef, orbit = false, orbitSpeed = 1, onPresented = null }) {
  const previewKey = `${modelKey}#preview`;
  // The file's Render as Preview draws it (`previewViewScene.js`), applied by its own coordinator.
  const { update, props } = useStageView(desired, previewKey, viewRef, null);
  const drawn = update.scene;
  const overlay = view.overlay;
  const children = useCallback(viewport => overlay?.(viewport, drawn) ?? null, [overlay, drawn]);
  const presentationChange = useCallback(state => onPresented?.(state.key === previewKey && !state.preparing), [onPresented, previewKey]);
  return <ShellViewport
    ref={viewRef}
    preview
    scene={view.scene}
    modelKey={modelKey}
    presentationKey={previewKey}
    sceneScaleMode={sceneScaleMode}
    {...props}
    orbit={orbit}
    orbitSpeed={orbitSpeed}
    viewCube={false}
    onPresentationChange={presentationChange}
    onCameraSettled={view.onCameraSettled || null}
    runtimeLifecycle={view.runtimeLifecycle || null}
    preserveInteractionPixelRatio
  >{children}</ShellViewport>;
}
