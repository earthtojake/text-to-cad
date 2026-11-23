import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { useControlUsage } from "../../../usage/controls.js";
import { normalizePlayback } from "../tools/playbar/playbackPreferences.js";
import { useViewSettings } from "../view-settings/useViewSettings.js";
import { previewViewScene } from "../viewport/previewViewScene.js";
import { usePreviewFrame } from "./usePreviewFrame.jsx";
import { usePreviewState } from "./usePreviewState.js";

// A Preview setting's group and field, as one control's name: `preview_lighting_exposure`.
const previewControl = (group, field) => `preview_${group}_${field.replace(/[A-Z]/g, letter => `_${letter.toLowerCase()}`)}`;

/**
 * Preview for a view outside the renderer shell: a flat view whose picture can be shown in 3D, lit
 * (`FlatViewFrame.jsx`'s `preview`). It holds what `useRendererShell.js` holds of Preview for a 3D view, the same
 * state under the same rules, and hands the frame the same pieces (`usePreviewFrame.jsx`):
 *
 * - the one `previewing` state (`usePreviewState`); Preview opens still, its Orbit off at every entry and exit;
 * - Preview's own settings, the file's (`restored.preview`): Render's lighting, background and floor, in a view
 *   settings store of their own, and the scene Preview draws from them (`previewViewScene.js`);
 * - Orbit's speed, the file's (`restored.playback`);
 * - what the file's view keeps of them (`record`: `preview`, `playback`), told as it changes (`onRecordChange`);
 * - Preview's viewport's handle (`viewRef`), for what acts on the view on screen (a live capture, a fit).
 *
 * The view brings Preview's own view (`View`, mounted only while Preview is up: where its 3D code loads) and what it
 * draws (`view`; `view.complete` false while that is still arriving). A view whose scene wears no surface look hides
 * Part colours (`partColours: false`). Nothing is prepared ahead: the view has no viewport until Preview is entered.
 *
 * @param {object} options
 * @param {object} options.fileView  The renderer's props (the file's name, `onPreviewChange`).
 * @param {string} options.modelKey  The file on screen.
 * @param {ReturnType<typeof import("../look/useViewportTheme.js").useViewportTheme>} options.viewport  The viewport's theme.
 * @param {{ preview?: object, playback?: object }} options.restored  The file's view as stored (`fileView.js`'s `readFileView`).
 * @param {import("react").ComponentType<object>} options.View
 * @param {object | null} options.view
 * @param {string} options.stageColor  The view's own canvas colour: Preview's cover's.
 * @param {string} options.sceneScaleMode
 * @param {boolean} options.offered  The view offers Preview at all (its picture can be shown in 3D): its button is drawn.
 * @param {boolean} options.available  The view can be previewed now (its picture is in): the button is live.
 * @param {boolean} options.mobile
 * @param {boolean} [options.partColours]
 * @param {(record: { preview: object, playback: object }) => void} [options.onRecordChange]
 */
export function useFlatPreview({ fileView, modelKey, viewport, restored, View, view, stageColor, sceneScaleMode, offered, available, mobile,
  partColours = true, onRecordChange = null }) {
  const controls = useControlUsage();
  const colorScheme = viewport.scheme;
  const state = usePreviewState();
  // A view that cannot be previewed (yet, or any more) never is, whatever asks.
  const previewing = available && state.previewing;
  // Preview's Orbit, on or off: its alone, off each time it opens until its settings turn it on.
  const [orbiting, setOrbitingState] = useState(false);
  const setOrbiting = useCallback(next => { controls.used("preview_orbit"); setOrbitingState(next); }, [controls]);
  const { set: setState, now } = state;
  const availableRef = useRef(available);
  availableRef.current = available;
  const setPreviewing = useCallback(next => {
    const entering = Boolean(next) && availableRef.current;
    if (entering === now()) return;
    setOrbitingState(false);
    setState(entering);
  }, [setState, now]);
  useEffect(() => { if (!available) setPreviewing(false); }, [available, setPreviewing]);
  // Counted while it is up (`usage/controls.js`), as every view's Preview is.
  useEffect(() => {
    if (!previewing) return undefined;
    controls.active("preview", true);
    return () => controls.active("preview", false);
  }, [previewing, controls]);

  // Preview's own settings (Render's), in a store of their own: the view has no Display settings of the store's.
  const { display, preview: look, scene, store } = useViewSettings(colorScheme, null, viewport.gradient || viewport.canvas);
  const [stored] = useState(() => restored);
  // Before the first paint, like every later edit: through the store, never around it.
  useLayoutEffect(() => { store.restore({}, stored.preview); }, [store, stored]);
  const [playback, setPlaybackState] = useState(() => normalizePlayback(stored.playback));
  const setOrbitSpeed = useCallback(speed => {
    controls.used("preview_orbit_speed");
    setPlaybackState(current => normalizePlayback({ ...current, orbitSpeed: speed }));
  }, [controls]);
  const record = useMemo(() => ({ preview: look, playback }), [look, playback]);
  const recordChange = useRef(onRecordChange);
  recordChange.current = onRecordChange;
  useEffect(() => { recordChange.current?.(record); }, [record]);
  // The scene Preview's own view draws (`PreviewView.jsx`): Render over its settings as they stand, keyed on the
  // store's resolved scene (which a new colour scheme reaches after this render), not on the scheme.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const desired = useMemo(() => previewViewScene(store.renderScene()), [store, scene, display, look]);
  const render = { settings: look, display, appearance: colorScheme, lightingQuality: "preview", partColours,
    onReset: () => { controls.used("preview_reset"); store.resetPreview(); },
    onPatch: patch => {
      for (const [group, change] of Object.entries(patch || {})) for (const field of Object.keys(change || {})) controls.changed(previewControl(group, field));
      store.patchPreview(patch);
    } };

  // The frame's root: where Preview's chrome watches the pointer rest.
  const rootRef = useRef(null);
  const [hostElement, setHostElement] = useState(null);
  useEffect(() => { setHostElement(rootRef.current); }, []);
  const viewRef = useRef(null);
  const frame = usePreviewFrame({ previewing, setPreviewing, modelKey, fileView, hostElement, stageColor, viewportScheme: colorScheme,
    View, view, desired, sceneScaleMode, viewRef, moving: orbiting, orbit: orbiting, onOrbitChange: setOrbiting,
    orbitSpeed: playback.orbitSpeed, onOrbitSpeedChange: setOrbitSpeed, render, disabled: !available, mobile });
  return { ...frame, offered, rootRef, viewRef, record };
}
