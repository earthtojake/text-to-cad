import { useCallback, useContext, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { clonePerspectiveSnapshot } from "@text-to-cad/core/lib/perspective.js";
import { VIEWER_SCENE_SCALE } from "@text-to-cad/core/lib/viewer/sceneScale.js";
import { ViewerElementContext, useViewerHost, usePromptDestination } from "../../../host/context.js";
import { hasOpenPopup } from "../../../lib/popups.js";
import { useAnnotationSession } from "../../../annotation/session.js";
import { DRAWING_TOOLS, annotationToolIcon, drawingToolVariant } from "../../../annotation/toolbar.jsx";
import { DRAWING_SHORTCUTS, pressToolKey } from "../tools/toolShortcuts.js";
import { useViewerHistory } from "./useViewerHistory.js";
import { promptView, promptViews } from "../../../annotation/views.js";
import { sceneBackdropEdgeColor } from "../look/chromeBackdrop.js";
import { useChromeBackdropColor } from "../look/useChromeBackdropColor.js";
import { previewViewScene } from "../viewport/previewViewScene.js";
import { CAD_ANNOTATION_DEFAULTS } from "../tools/annotate/AnnotationOverlay.jsx";
import { annotationDocumentOf } from "../tools/annotate/annotation3d.js";
import { normalizeToolStack } from "../tools/toolStackLayout.js";
import { normalizePlayback } from "../tools/playbar/playbackPreferences.js";
import { PreviewRenderSettings } from "../view-settings/PreviewRenderSettings.jsx";
import { useAppliedViewSettings } from "../view-settings/useAppliedViewSettings.js";
import { useViewSettings } from "../view-settings/useViewSettings.js";
import { cameraForViewSettings, viewerDisplaySettingsForCamera } from "../view-settings/viewerDisplaySettings.js";
import { attachLiveBinding } from "./liveBinding.js";
import { shellLoadReport } from "./loadReport.js";
import { createViewPromptContext, promptDeliveryError } from "./promptContext.js";
import { fileViewsEqual, plainShellCamera, readFileView, readFileViewSlices, scopeShellCamera, shellPresentationKey, writeFileView } from "./fileView.js";
import { useViewerShortcuts } from "./useViewerShortcuts.js";
import { DISPLAY_MODE_OPTIONS } from "../view-settings/DisplayModeOptions.js";
import { normalizeViewFeatures } from "@text-to-cad/core/common/viewSettings.js";
import { useWhenSettled } from "./useWhenSettled.js";


/**
 * Preview mode's one state: the viewer with its tools put away, the model drawn in Render, where its
 * routines play and it orbits on request. The shell holds it unless the renderer passes it in
 * (`useRendererShell`'s `preview`).
 * `now()` is the state as last set, before React renders it: what a command preview's own crossing
 * calls (its routine played on the way in) asks of it.
 * @returns {{ previewing: boolean, set: (previewing: boolean) => void, now: () => boolean }}
 */

export function usePreviewState() {
  const [previewing, setPreviewing] = useState(false);
  const latest = useRef(false);
  const set = useCallback(next => { latest.current = Boolean(next); setPreviewing(Boolean(next)); }, []);
  const now = useCallback(() => latest.current, []);
  return useMemo(() => ({ previewing, set, now }), [previewing, set, now]);
}

/**
 * What the viewport reports it is previewing (`ShellViewport`'s `onPresentationChange`): the file, the
 * presentation key, the render mode, and whether it is still preparing or covering a transition. Held once;
 * the shell holds it unless the renderer passes it in (`useRendererShell`'s `presentationReport`).
 * @returns {{ state: { file: string, key: string, renderMode: boolean, covering: boolean, preparing: boolean } | null,
 *   report: (next: object) => void }}
 */
export function usePresentationReport() {
  const [state, setState] = useState(null);
  const report = useCallback(next => setState(previous => previous?.file === next.file && previous?.renderMode === next.renderMode &&
    previous?.key === next.key && previous?.covering === next.covering && previous?.preparing === next.preparing ? previous : next), []);
  return useMemo(() => ({ state, report }), [state, report]);
}

/** What is on screen is not yet `key` of `modelKey` in `renderMode`, or is still being prepared. */
export function presentationIsPending(state, { modelKey, key, renderMode }) {
  return state?.file !== modelKey || state?.key !== key || state?.renderMode !== renderMode || state?.preparing === true;
}

/**
 * The tool ids the shell itself understands. A renderer's own tools use any other id. A renderer
 * that offers one of these declares it in its `toolModes` too, as a mode that toggles.
 */
export const SHELL_TOOL = Object.freeze({ PENCIL: "pencil", SHAPES: "shapes" });

const SESSION_SAVE_DELAY_MS = 180;
const EMPTY = Object.freeze({});

/**
 * Everything a file-family renderer needs from its host that is not about its
 * scene. The renderer loads its document and builds its scene; this hook owns
 * the rest and hands back one `shell` object for `<RendererShell>`:
 *
 *  - the file's view through the host (`state` / `onStateChange`, `fileView.js`): the
 *    camera, the Display settings, the playback settings, and the renderer's own
 *    slices of view state — written soon after a change and once more on unmount, and
 *    read back before the first paint, the camera restored in place of the open-time fit;
 *  - Display settings: store, resolution against the renderer's FEATURES, the
 *    queued application to the viewport, and the content of Display's dropdown;
 *  - tools: the mode state machine and Annotate's session, or none at all for a renderer
 *    whose viewport is the camera's alone;
 *  - the host contract: prompt snapshots, clipboard screenshots,
 *    preview, alerts, shortcuts (a file's controls are tool-stack panels the renderer
 *    shows with its tools, never a host panel);
 *  - the live command surface, with the renderer's added and declined commands.
 *
 * @param {object} options
 * @param {import("../../../file-viewer/types.js").RendererViewProps} options.view  The host's props, unchanged.
 * @param {{ preferences: { toolStack: object }, onPreferenceChange(patch: object): void, live?: object,
 *   captureRequest?: { key: string | number } | null,
 *   acknowledgeCommand?: (kind: string, key: string | number) => void }} options.services  `preferences` is the
 *   tab's settings (`@text-to-cad/ui/tab-store`), the person's in every file of the tab.
 * @param {import("@text-to-cad/core/prompt").ResourceRef} options.resource  The document on screen, for prompt context and live state.
 * @param {string} options.modelKey  Stable per file: scopes the camera and the presentation.
 * @param {string} [options.revisionKey]  Changes when the file's bytes do.
 * @param {import("@text-to-cad/core/common/viewSettings.js").ViewFeatures} options.features
 * @param {object} [options.viewSettings]  The result of `useViewSettings`, when the renderer needs the
 *   display settings earlier in its own render than this hook could hand them back. It may also carry
 *   `applied`: the renderer's own `useAppliedViewSettings` result, for a renderer that must read the
 *   RESOLVED view that early too — a renderer that decides what to load, and at what detail, from the
 *   view it is showing. Such a renderer owns the viewport's handle as well and passes it as `viewerRef`.
 * @param {{ current: object | null }} [options.viewerRef]  The ref the viewport's handle lands in, when
 *   the renderer made it itself (see `viewSettings.applied`).
 * @param {ReturnType<typeof import("../tools/toolModes.js").createToolModes> | null} [options.toolModes]  Omitted
 *   by a renderer with no tools: the shell then has no active tool and a saved tab records none.
 * @param {boolean} [options.previewable]  The renderer's view is 3D and offers Preview: the model
 *   in Render, its tools put away. Each renderer of a 3D view declares it; without it (a 2D view)
 *   there is no Preview at all — no button on the strip, not a disabled one — and anything that asks for it
 *   leaves the normal view on screen (`previewing` stays false, `setPreviewing` does nothing).
 * @param {{ previewing: boolean, set: (previewing: boolean) => void }} [options.preview]  Preview mode
 *   (`usePreviewState`), when the renderer holds that state itself: a renderer whose own gates
 *   (picking, tool effects) and whose scene's inputs run before this hook cannot wait for it.
 *   Every gate reads this one state; Preview button, Escape and its X write it, through the returned
 *   `setPreviewing`. Omitted: the shell holds it. While it is on, the renderer draws the model as it opens
 *   (at rest, nothing hidden, isolated, picked or measured) and leaves its own state as it is, so leaving
 *   finds the tools view exactly as it was.
 * @param {{ mode: string, set: (update: (current: string) => string) => void }} [options.tool]  The tool in
 *   hand, when the renderer holds that state itself: a renderer whose LOAD, or what Escape means in it,
 *   turns on which tool is up cannot wait for this hook to hand it back. The rules stay the shell's —
 *   `set` is given the mode `toolModes` decided. Omitted: the shell holds the state.
 * @param {import("../scene.js").KitScene | null} options.scene
 * @param {{ busy: boolean, updating?: boolean, progress?: object | null, alert?: object | null,
 *   editPending?: boolean, finding?: boolean }} options.load  The
 *   renderer's document load. `busy`: nothing to show yet. `updating`: a newer revision is loading behind the scene on
 *   screen. The rest are for a renderer whose document is more than a download — see `loadReport.js`.
 * @param {object | null} [options.animation]  The tools view's routine runtime (with its own `clock`),
 *   when the file has routines. They play from the file sidebar's Animation section, whose frame stays
 *   on the model as a pose does. Preview's routine is its own, on its own scene (`RendererShell`'s
 *   `previewView.animation`).
 * @param {{ commands?: Record<string, (...args: any[]) => void>, declined?: Record<string, string>,
 *   state?: () => object, resource?: () => object }} [options.live]  Live commands this renderer adds (by name) or
 *   declines (name to the error its caller reads), and extra fields for the live state. Every name in
 *   `HOST_LIVE_COMMANDS` must be one or the other. `resource` is the document the viewport is SHOWING, when that
 *   can lag the one being loaded (a rebuild whose predecessor is retained): live state reports what is on screen,
 *   never what is on its way in. Omitted: the resource the renderer was handed.
 * @param {() => import("@text-to-cad/core/prompt").PromptReference[]} [options.promptReferences]  What a snapshot
 *   depicts, when that is narrower than the whole file (a selection). Default: the file.
 * @param {(input: { resource: object, references: object[], capture: Promise<Blob> }) => object} [options.promptContext]
 *   How this renderer assembles a snapshot's prompt context. Default `createViewPromptContext`, which takes
 *   references already in the prompt grammar; a renderer with a reference vocabulary of its own supplies the
 *   builder that speaks it, and then `promptReferences` may return that vocabulary instead — and such a
 *   renderer reports its live `selection` itself, in the prompt grammar, through `live.state`.
 * @param {{ active?: boolean, handle?: () => boolean }} [options.escape]  Escape, innermost first: `handle` returns
 *   true when it spent the key. After it there is nothing of the viewer's own left to close.
 * @param {{ signatures?: Record<string, string>, read: () => Record<string, unknown> } | null} [options.rendererState]
 *   The renderer's own slices of the file's view (`fileView.js`): `read()` is called when the view is written,
 *   never at render — state a renderer keeps outside React (a pose written per frame) is saved as it is at that
 *   moment, its last change before unmount included — and `signatures` says, per slice, what it is written
 *   against; a slice comes back (`readFileView`, which the renderer calls itself on mount) only under the same
 *   signature. The renderer calls `shell.scheduleStateSave()` when a slice changed. Null, or omitted, keeps
 *   what is stored as it is: a renderer that has not loaded yet, or one with no slices of its own.
 * @param {() => void} [options.onCameraSettled]  The camera came to rest on a new view: it moved and was
 *   recorded, a preview camera moved (preview mode, which records nothing), or the viewport's size
 *   changed — which can expose part of a scene without changing position, target or zoom at all. For a
 *   renderer that samples the camera to decide what detail its scene needs. It is called often; debounce
 *   it if that matters.
 * @param {boolean} [options.preserveInteractionPixelRatio]  The scene is drawn with hairlines just now: keep the
 *   idle pixel ratio while the camera moves, instead of dropping it for the duration of the gesture.
 * @param {{ onRelease?(runtime: object, detail: { handoff: boolean }): void, onContextLost?(): void,
 *   onInitializationError?(error: unknown): void }} [options.runtimeLifecycle]  What happens to the WebGL runtime
 *   under the scene, for a renderer that hangs its own objects or in-flight work on it (`ShellViewport.jsx`).
 * @param {(alert: object | null) => void} [options.onRuntimeAlert]  The viewport reported an alert, or
 *   cleared one. A renderer that folds the viewport's alert into an alert of its own keeps that state
 *   itself and hands the composed result back as `load.alert`; the shell then holds none of its own.
 *   Omitted: the shell keeps it and folds it into the report.
 * @param {ReturnType<typeof usePresentationReport>} [options.presentationReport]  What the viewport is
 *   previewing, when the renderer holds that state itself: a renderer that must answer "is what is on screen
 *   the document I asked for" before this hook runs — a live preview deciding whether its own result has
 *   landed (`presentationIsPending` with `shellPresentationKey(modelKey, revisionKey)`). Omitted: the shell holds it.
 * @param {string} [options.sceneScaleMode]
 * @param {boolean} [options.sceneEffects]  The viewport applies the view's model effects to the scene,
 *   through the scene contract (`ShellViewport`'s `sceneEffects`); a renderer whose own layers apply
 *   them leaves this off.
 */
export function useRendererShell({
  view, services, resource, modelKey, revisionKey = "", features, toolModes = null, tool = null, previewable = false, preview = null, scene, load,
  viewSettings = null, viewerRef: providedViewerRef = null,
  animation = null, live = EMPTY, promptReferences = null, promptContext = createViewPromptContext,
  escape = EMPTY, rendererState = null, viewState = null, annotationUnits = "mm", deleteSelection = null,
  sceneEffects = false,
  onCameraSettled = null, preserveInteractionPixelRatio = false, runtimeLifecycle = null,
  onRuntimeAlert = null, presentationReport = null,
  sceneScaleMode = VIEWER_SCENE_SCALE.CAD
}) {
  const host = useViewerHost();
  const viewerElement = useContext(ViewerElementContext);
  const destination = usePromptDestination();
  const promptAvailable = destination.available;
  const composer = destination.kind === "composer";
  const { onStateChange, appearance } = view;
  const colorScheme = appearance?.colorScheme === "dark" ? "dark" : "light";
  const ownPreview = usePreviewState();
  const previewState = preview || ownPreview;
  // Preview is a 3D view's alone: one whose renderer did not declare it never enters it, whatever asks.
  const previewing = previewable && previewState.previewing;
  const previewingRef = useRef(previewing);
  previewingRef.current = previewing;
  // Preview and the tools view are two views (`PreviewView.jsx`): Preview mounts a viewport,
  // a scene, a pose and a routine of its own over the editor's, which stays as it is. Crossing
  // touches nothing of either: it mounts Preview or takes it away.
  // Preview's Orbit, on or off: its alone, off each time it opens until its settings turn it on.
  const [orbiting, setOrbiting] = useState(false);
  // Preview's environment and code, prepared ahead of it (`previewPrepare`, below).
  const previewPrepare = useRef(null);
  const commitPreviewing = useCallback(entering => {
    if (entering === previewingRef.current) return;
    previewingRef.current = entering;
    setOrbiting(false);
    previewState.set(entering);
  }, [previewState.set]);
  const setPreviewing = useCallback(next => {
    // A view that does not offer Preview never enters it, whatever asks.
    if (next && !previewable) return;
    commitPreviewing(Boolean(next));
  }, [previewable, commitPreviewing]);
  // A view that stops offering Preview while it is up leaves it the way every exit does.
  useEffect(() => {
    if (!previewable && previewState.previewing) {
      previewingRef.current = true;
      setPreviewing(false);
    }
  }, [previewable, previewState.previewing, setPreviewing]);

  // ---- the file's view --------------------------------------------------------
  const [restored] = useState(() => readFileView(view.state));
  // The renderer's slices as stored, echoed back until the renderer says what they are.
  const [storedSlices] = useState(() => readFileViewSlices(view.state));
  // A renderer whose own work needs the display settings BEFORE it can hand this hook a scene
  // — one that reads them while it is still deciding what to load — creates them itself and passes
  // them in. It is the same store either way; owning it here is a convenience, not a rule.
  const { display: displaySettings, preview: previewLook, scene: desiredScene, store: viewSettingsStore } = useViewSettings(colorScheme, viewSettings);
  useLayoutEffect(() => { viewSettingsStore.configure({ features }); }, [viewSettingsStore, features]);
  // Before the first paint, like every later edit: through the store, never around it.
  useLayoutEffect(() => { viewSettingsStore.restore(restored.display, restored.preview); }, [viewSettingsStore, restored]);
  const ownViewerRef = useRef(null);
  const viewerRef = providedViewerRef || ownViewerRef;
  // Preview's viewport, while it is open (`PreviewView.jsx`), and the view on screen: what a live
  // camera or capture acts on.
  const previewViewRef = useRef(null);
  const viewOnScreen = () => (previewingRef.current ? previewViewRef.current : viewerRef.current);
  // Exactly one coordinator drives one viewport. A renderer that resolved the view itself
  // hands the result in, and this call stands down (`useAppliedViewSettings`).
  const appliedByRenderer = viewSettings?.applied || null;
  const ownViewUpdate = useAppliedViewSettings(desiredScene, appliedByRenderer ? null : modelKey, viewerRef, viewSettingsStore);
  const viewUpdate = appliedByRenderer || ownViewUpdate;
  const resolvedScene = viewUpdate.scene;
  const rendering = resolvedScene.render.enabled;
  // What Preview will need, prepared ahead while the model is on screen: Render's studio code and
  // its environment at Preview's quality, into the GPU device's cache Preview draws from
  // (`studioEnvironmentCacheFor`). Preparing changes nothing the editor draws.
  // Not on a software renderer (SwiftShader, llvmpipe): compiling there holds the page's one thread
  // for seconds, unasked; Preview prepares as it is entered instead, under its cover.
  previewPrepare.current = signal => {
    const prepare = viewerRef.current?.prepareViewSettings;
    if (!prepare || viewerRef.current.softwareRendering?.()) return null;
    return prepare(previewViewScene(viewSettingsStore.renderScene()), signal);
  };

  // The camera the file was left at, scoped to this model: the viewport applies it in place of
  // its open-time fit, and fits when there is none (or it is not a camera at all).
  const [restoredCamera] = useState(() => scopeShellCamera(restored.camera, modelKey, sceneScaleMode));
  const activePerspectiveRef = useRef(restoredCamera);
  const [viewerPerspective, setViewerPerspective] = useState(restoredCamera);
  // "" is a renderer with no tools at all. The tool in hand is never saved: a file opens in its
  // default tool.
  const [ownToolMode, setOwnToolMode] = useState(() => (toolModes ? toolModes.defaultMode : ""));
  const toolMode = tool ? tool.mode : ownToolMode;
  const setToolMode = tool ? tool.set : setOwnToolMode;
  const recordRef = useRef(null);
  const onStateChangeRef = useRef(onStateChange);
  onStateChangeRef.current = onStateChange;
  // The file's playback settings — preview's Orbit speed, Autoplay, and the routine's Speed and Loop
  // once chosen — kept between leaving and re-entering preview, and in its view.
  const [playback, setPlaybackState] = useState(() => restored.playback);
  const setPlayback = useCallback(patch => setPlaybackState(current => normalizePlayback({ ...current, ...patch })), []);
  const rendererStateRef = useRef(rendererState);
  rendererStateRef.current = rendererState;
  const latestRecord = useRef(null);
  latestRecord.current = () => {
    const slices = rendererStateRef.current;
    // The camera is the last one the viewport reported for the tools view (`handlePerspectiveChange`):
    // never preview's, and never a runtime that has no model under it yet.
    return writeFileView({
      camera: plainShellCamera(activePerspectiveRef.current),
      display: viewSettingsStore.getSnapshot().display,
      preview: viewSettingsStore.getSnapshot().preview,
      playback,
      renderer: slices ? slices.read() : storedSlices.values,
      signatures: slices ? slices.signatures : storedSlices.signatures
    });
  };
  const saveTimer = useRef(0);
  // A view that has gone writes nothing more: its last write is the flush as it unmounts, and a host
  // that drops the view of a file it left (`CadViewer`) must not see it written again by a camera
  // report or a slice that lands after that.
  const closed = useRef(false);
  const flushSession = useCallback(() => {
    window.clearTimeout(saveTimer.current);
    saveTimer.current = 0;
    if (closed.current) return;
    const next = latestRecord.current();
    if (fileViewsEqual(recordRef.current, next)) return;
    recordRef.current = next;
    onStateChangeRef.current?.(next);
  }, []);
  const scheduleSessionSave = useCallback(() => {
    if (closed.current) return;
    window.clearTimeout(saveTimer.current);
    saveTimer.current = window.setTimeout(flushSession, SESSION_SAVE_DELAY_MS);
  }, [flushSession]);
  useEffect(() => {
    closed.current = false;
    return () => { flushSession(); closed.current = true; };
  }, [flushSession]);
  // The display's and playback's every edit is saved soon after; the camera's on every move (below);
  // a renderer's slices when it says so. The tool in hand is not saved at all.
  useEffect(() => { scheduleSessionSave(); }, [displaySettings, previewLook, playback, scheduleSessionSave]);

  // Stable across renders: the viewport keeps it in a ref for the life of the runtime.
  const cameraSettledRef = useRef(onCameraSettled);
  cameraSettledRef.current = onCameraSettled;
  const reportCameraSettled = useCallback(() => cameraSettledRef.current?.(), []);
  const runtimeLifecycleRef = useRef(runtimeLifecycle);
  runtimeLifecycleRef.current = runtimeLifecycle;
  const stableRuntimeLifecycle = useMemo(() => ({
    onRelease: (runtime, detail) => runtimeLifecycleRef.current?.onRelease?.(runtime, detail),
    onContextLost: () => runtimeLifecycleRef.current?.onContextLost?.(),
    onInitializationError: (error) => runtimeLifecycleRef.current?.onInitializationError?.(error)
  }), []);
  const handlePerspectiveChange = useCallback((nextPerspective) => {
    // A camera that moved is a camera that settled, whether or not the file records it.
    cameraSettledRef.current?.();
    const snapshot = clonePerspectiveSnapshot(nextPerspective);
    if (!snapshot) return;
    activePerspectiveRef.current = snapshot;
    scheduleSessionSave();
  }, [scheduleSessionSave]);

  // ---- host chrome ----------------------------------------------------------
  const chromeBackdropColor = useChromeBackdropColor(colorScheme === "dark");
  const sceneBackdrop = useMemo(
    () => resolvedScene.view.background.enabled && resolvedScene.view.background.opacity === 1
      ? resolvedScene.view.background.color
      : resolvedScene.view.background.enabled ? chromeBackdropColor
        : sceneBackdropEdgeColor(resolvedScene.theme?.background, chromeBackdropColor),
    [chromeBackdropColor, resolvedScene.theme, resolvedScene.view.background]
  );
  // The tab's settings (`@text-to-cad/ui/tab-store`): the person's, in every file of the tab. Read
  // through their own normalizers, so a host that hands over less is still whole here.
  const preferences = services.preferences;
  const previewOrbitSpeed = playback.orbitSpeed;
  const setPreviewOrbitSpeed = useCallback(speed => setPlayback({ orbitSpeed: speed }), [setPlayback]);
  // The tool stack's layout — the sizes of the panels a person can size, the folded panels. A
  // change is a patch over the layout as it last stood (or a function of it), so two panels
  // written back in one turn both land.
  const toolStack = useMemo(() => normalizeToolStack(preferences?.toolStack), [preferences?.toolStack]);
  const toolStackRef = useRef(toolStack);
  toolStackRef.current = toolStack;
  const changeToolStack = useCallback(patch => {
    const next = normalizeToolStack({ ...toolStackRef.current, ...(typeof patch === "function" ? patch(toolStackRef.current) : patch) });
    toolStackRef.current = next;
    services.onPreferenceChange({ toolStack: next });
  }, [services.onPreferenceChange]);
  const autoplay = playback.autoplay;
  const setAutoplay = useCallback(value => setPlayback({ autoplay: value === true }), [setPlayback]);
  const hostRef = useRef(null);
  const [hostElement, setHostElement] = useState(null);
  useEffect(() => { setHostElement(hostRef.current); }, []);

  // ---- loading and alerts ---------------------------------------------------
  const [ownRuntimeAlert, setOwnRuntimeAlert] = useState(null);
  // A renderer that composes the viewport's alert into its own keeps that state; the shell
  // then holds none, so the composed `load.alert` is not counted a second time here.
  const runtimeAlertRef = useRef(onRuntimeAlert);
  runtimeAlertRef.current = onRuntimeAlert;
  const setRuntimeAlert = useCallback(alert => (runtimeAlertRef.current || setOwnRuntimeAlert)(alert || null), []);
  const reportActionError = useCallback(error => {
    if (!error) return;
    setRuntimeAlert({ severity: "error", kind: "status", blocking: false,
      title: "Couldn’t complete the action", message: error instanceof Error ? error.message : String(error) });
  }, [setRuntimeAlert]);
  const runtimeAlert = onRuntimeAlert ? null : ownRuntimeAlert;
  const viewerLoading = Boolean(load.busy);
  const hasContent = Boolean(scene) && !viewerLoading;
  // Preview warmed a moment after the model is on screen, before anyone asks for it.
  useEffect(() => {
    if (!previewable || !hasContent) return undefined;
    const controller = new AbortController();
    const timer = setTimeout(() => { void Promise.resolve(previewPrepare.current?.(controller.signal)).catch(() => {}); }, 600);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [previewable, hasContent, modelKey]);
  const presentationKey = shellPresentationKey(modelKey, revisionKey);
  const ownPresentationReport = usePresentationReport();
  const { state: presentationState, report: handlePresentationChange } = presentationReport || ownPresentationReport;
  const presentationPending = hasContent && presentationIsPending(presentationState, { modelKey, key: presentationKey, renderMode: rendering });
  const completedView = useRef(false);
  useEffect(() => { if (hasContent && !presentationPending) completedView.current = true; }, [hasContent, presentationPending]);
  const viewerAlert = runtimeAlert?.blocking ? runtimeAlert : viewerLoading ? null : load.alert || runtimeAlert || null;
  const loading = shellLoadReport({
    load, alert: viewerAlert, busy: presentationPending,
    previousView: completedView.current && hasContent, preparing: presentationPending && !viewerLoading
  });

  // ---- tools ----------------------------------------------------------------
  const idle = viewerLoading || !scene;
  // Pencil or Shapes is in hand: the drawing tools, which share one annotation.
  const drawingFamily = toolMode === SHELL_TOOL.PENCIL || toolMode === SHELL_TOOL.SHAPES ? toolMode : null;
  const annotateToolActive = !previewing && drawingFamily !== null;
  const selectTool = useCallback((mode) => setToolMode(current => (toolModes ? toolModes.next(current, mode) : mode)), [toolModes, setToolMode]);
  // A tool panel's X: back to the file's default tool (Select, where there is one), from any tool.
  const selectDefaultTool = useCallback(() => setToolMode(toolModes ? toolModes.defaultMode : ""), [toolModes, setToolMode]);
  // The annotation's undo history (`useViewerHistory.js`): Annotate's panel's Undo and Redo, and ⌘Z.
  const history = useViewerHistory();
  const historyRef = useRef(history);
  historyRef.current = history;
  const annotation = useAnnotationSession(drawingFamily, CAD_ANNOTATION_DEFAULTS, history);


  // ---- prompt snapshots, clipboard ------------------------------------------
  const showPromptResult = useCallback((result) => reportActionError(promptDeliveryError(result)), [reportActionError]);
  const deliverPrompt = useCallback((context) => {
    let pending;
    try { pending = host.promptContext.deliver(context); }
    catch (error) { pending = Promise.reject(error); }
    return Promise.resolve(pending).catch(error => ({ status: "failed", message: error instanceof Error ? error.message : String(error) }))
      .then(result => { showPromptResult(result); return result; });
  }, [host.promptContext, showPromptResult]);
  const referencesRef = useRef(promptReferences);
  referencesRef.current = promptReferences;
  const promptContextRef = useRef(promptContext);
  promptContextRef.current = promptContext;
  const liveResourceRef = useRef(live.resource);
  liveResourceRef.current = live.resource;
  // Freeze references now; the host binds its destination before waiting for the PNG.
  const capture = useCallback(() => {
    if (!modelKey || !promptAvailable || viewerLoading) return;
    try {
      if (!viewerRef.current?.captureScreenshotBlob) throw new Error("The viewer is not ready");
      const pixels = viewerRef.current.captureScreenshotBlob();
      void pixels.catch(() => {});
      if (!composer) {
        void host.clipboard.writeImage(pixels).catch(reportActionError);
        return;
      }
      void deliverPrompt(promptContextRef.current({
        resource: liveResourceRef.current?.() || resource, references: referencesRef.current?.() || [], capture: pixels
      }));
    } catch (error) { reportActionError(error); }
  }, [modelKey, promptAvailable, viewerLoading, deliverPrompt, resource, composer, host.clipboard, reportActionError]);
  const copyActionRef = useRef(null);
  // Annotate's Copy: the view with its ink, or the view alone before there is any, to the clipboard;
  // true once it is there.
  const copyAnnotation = useCallback(async () => {
    if (!viewerRef.current?.captureScreenshotBlob) return false;
    try {
      await host.clipboard.writeImage(viewerRef.current.captureScreenshotBlob());
      return true;
    } catch (error) { reportActionError(error); return false; }
  }, [host.clipboard, reportActionError]);
  // ---- a prompt's views and files ---------------------------------------------
  // The view on screen as a prompt carries it: the camera, the mode on screen and the Grid switch, and
  // what places or hides the parts — the renderer's pose and visibility (`viewState`) — (`annotation/views.js`).
  const viewStateRef = useRef(viewState);
  viewStateRef.current = viewState;
  const currentView = useCallback(() => {
    const { display, scene: shown } = viewSettingsStore.getSnapshot();
    return promptView(viewerRef.current?.promptCamera?.() ?? null, {
      display: { ...display, mode: shown.view.mode, grid: shown.view.grid.enabled }, state: viewStateRef.current?.() ?? null
    });
  }, [viewSettingsStore]);
  const annotationRef = useRef(annotation);
  annotationRef.current = annotation;
  // The annotation as an annotation file says it; none without ink.
  const annotationNow = useCallback(() => (annotationRef.current.items.length ? annotationDocumentOf(annotationRef.current.items, annotationUnits) : null), [annotationUnits]);
  const resourceRef = useRef(resource);
  resourceRef.current = resource;
  // The file a prompt's views render: the one shown, by its absolute path.
  const promptFile = useCallback(() => {
    const shown = liveResourceRef.current?.() || resourceRef.current;
    return shown?.kind === "workspace-file" || shown?.kind === "cad-model" ? shown.path : null;
  }, []);
  // Quick Edit captures the current view and annotation views; the host prepares JSON at the press.
  const replayUnavailable = useRef("");
  replayUnavailable.current = String(load.replayUnavailable || "");
  const quickEditPrompt = useMemo(() => ({
    unavailable: () => replayUnavailable.current,
    views: () => (!replayUnavailable.current && host.promptFiles && promptFile() ? promptViews(currentView(), annotationRef.current.views, annotationRef.current.items) : []),
    files: views => {
      const input = promptFile();
      if (!host.promptFiles || !input || !views.length) return null;
      return host.promptFiles.create({ name: input.split("/").pop(), input, views, annotation: annotationNow() });
    },
    read: path => host.promptFiles.read(path),
  }), [host.promptFiles, currentView, annotationNow, promptFile]);
  // The view as it is on screen, the annotation's ink in it: the annotation's Copy.
  const captureView = useCallback(() => {
    if (!viewerRef.current?.captureScreenshotBlob) return Promise.reject(new Error("The viewer is not ready"));
    return viewerRef.current.captureScreenshotBlob();
  }, []);
  const captureKey = services.captureRequest?.key ?? null;
  const appliedCaptureKey = useRef(null);
  useEffect(() => {
    if (captureKey === null || appliedCaptureKey.current === captureKey || viewerLoading || !promptAvailable) return;
    appliedCaptureKey.current = captureKey;
    services.acknowledgeCommand?.("captureRequest", captureKey);
    capture();
  }, [captureKey, viewerLoading, promptAvailable, services.acknowledgeCommand, capture]);

  // ---- shortcuts ------------------------------------------------------------
  const escapeRef = useRef(escape.handle);
  escapeRef.current = escape.handle;
  const escapeView = useCallback(() => escapeRef.current?.() || false, []);
  // What Select has picked of the annotation: Delete deletes it with whatever the renderer's own
  // selection can lose (`deleteSelection`: a measurement), and Escape lets go of it first.
  // The strip's tools as the frame last drew them (`RendererShell.jsx`): what a tool's letter takes up.
  const toolKeysRef = useRef([]);
  const deleteSelectionRef = useRef(deleteSelection);
  deleteSelectionRef.current = deleteSelection;
  // Everything Select has picked that can go: the annotation's ink and the renderer's own; true if any went.
  const deletePicked = useCallback(() => {
    const session = annotationRef.current;
    const ink = session.selected.length > 0;
    if (ink) session.remove(session.selected);
    return Boolean(deleteSelectionRef.current?.()) || ink;
  }, []);
  useViewerShortcuts({
    viewerElement,
    onCopy: () => copyActionRef.current?.() || false,
    onDelete: () => !previewing && !annotateToolActive && deletePicked(),
    // ⌘Z and ⇧⌘Z walk the annotation's history, whatever tool is in hand; never in preview.
    onUndo: () => !previewing && historyRef.current.undo(),
    onRedo: () => !previewing && historyRef.current.redo(),
    // A tool's letter takes it up, F frames the model (`toolShortcuts.js`), over the strip the frame
    // has on screen (`toolKeys`, RendererShell's); never in preview.
    onKey: event => !previewing && !idle && pressToolKey(event, {
      tools: toolKeysRef.current, selectDrawing: tool => annotationRef.current.selectTool(tool),
      fit: () => viewerRef.current?.resetZoom?.() }),
    escapeActive: Boolean(escape.active || previewing || annotation.selected.length || (toolModes && toolMode !== toolModes.defaultMode)),
    onEscape(event) {
      // A popup opened in THIS viewer (a menu, a Select, a colour picker, Display) owns Escape before
      // preview; another viewer's popup is not this one's business.
      if (hasOpenPopup(viewerElement.current)) return;
      if (previewing) { setPreviewing(false); return; }
      // Annotate's surface spends its own Escape (its editor deselects, or drops the stroke in hand).
      if (annotateToolActive && event.target instanceof Element && event.target.closest("[data-cad-annotation-overlay]")) return;
      if (annotationRef.current.selected.length) { annotationRef.current.select([]); return; }
      if (escapeRef.current?.()) return;
      // A renderer that left it: the tool in hand goes down, back to the file's default (Select).
      if (toolModes && toolMode !== toolModes.defaultMode) selectDefaultTool();
    }
  });

  // ---- live command surface ---------------------------------------------------
  const liveRuntimeRef = useRef(null);
  liveRuntimeRef.current = {
    readState() {
      const display = viewSettingsStore.getSnapshot().display;
      // What is SHOWN, which is not always what is loading: a rebuild that keeps its
      // predecessor on screen reports the predecessor's revision until it is replaced.
      const shown = liveResourceRef.current?.() || resource;
      const rendererState = live.state?.() || {};
      return {
        resource: { ...shown }, revision: String(shown.revision || ""),
        // Live state reads the selection in the prompt grammar. References are already in it
        // only where the default builder assembles the snapshot; a renderer that keeps its own
        // vocabulary reports its selection through `live.state`, so it is never passed on raw.
        selection: promptContextRef.current === createViewPromptContext ? referencesRef.current?.() || [] : [],
        camera: clonePerspectiveSnapshot(viewerRef.current?.getPerspective?.() || activePerspectiveRef.current),
        display,
        ...rendererState,
        loading: Boolean(viewerLoading || !scene || load.updating || presentationPending || rendererState.loading)
      };
    },
    setCamera(camera) {
      const validVector = vector => Array.isArray(vector) && vector.length === 3 && vector.every(Number.isFinite);
      if (!["position", "target", "up"].every(key => validVector(camera?.[key]))
        || (camera.projection != null && !["perspective", "orthographic"].includes(camera.projection))
        || ["zoom", "focalLength", "orthographicHalfHeight"].some(key => camera[key] != null && (!Number.isFinite(camera[key]) || camera[key] <= 0))) {
        throw new Error("Camera vectors must contain three finite numbers and camera scales must be positive.");
      }
      const nextDisplay = viewerDisplaySettingsForCamera(viewSettingsStore.getSnapshot().display, camera);
      const requested = clonePerspectiveSnapshot(camera);
      if (previewing) {
        if (!previewViewRef.current?.setPerspective?.(requested)) throw new Error("The viewer could not apply this camera.");
        return;
      }
      const snapshot = cameraForViewSettings(requested, nextDisplay, { lightingQuality: "preview" });
      if (!snapshot || !viewerRef.current?.setPerspective?.(snapshot, { resetZoomBaseline: true })) throw new Error("The viewer could not apply this camera.");
      const scoped = scopeShellCamera(snapshot, modelKey, sceneScaleMode);
      viewSettingsStore.restore(nextDisplay);
      setViewerPerspective(scoped);
      handlePerspectiveChange(scoped);
    },
    // Frame the model again, without turning the camera. The name is the host
    // protocol's ("cad-reset-camera"); the viewport calls the same act resetZoom.
    resetCamera() {
      if (!viewOnScreen()?.resetZoom?.()) throw new Error("The viewer camera is unavailable.");
    },
    setDisplaySettings(patch) { viewSettingsStore.patch(patch); },
    capture() {
      const view = viewOnScreen();
      if (!view?.captureScreenshotBlob) throw new Error("The viewer cannot capture this model yet.");
      return view.captureScreenshotBlob();
    },
    thumbnail(size) {
      if (!viewerRef.current?.captureThumbnail) throw new Error("The viewer cannot picture this model yet.");
      return viewerRef.current.captureThumbnail(size);
    },
    ...(live.commands || {})
  };
  // Settled is what live state says: the file whole, on screen, drawn, and the renderer not busy.
  const whenSettled = useWhenSettled(() => !liveRuntimeRef.current.readState().loading);
  const liveBinding = services.live;
  const commandNames = Object.keys(live.commands || {}).sort().join("\n");
  const declinedRef = useRef(live.declined);
  declinedRef.current = live.declined;
  useEffect(() => {
    if (!liveBinding) return undefined;
    return attachLiveBinding(liveBinding, () => liveRuntimeRef.current, {
      commands: commandNames ? commandNames.split("\n") : [], declined: declinedRef.current || {}, ready: whenSettled
    });
  }, [liveBinding, commandNames, whenSettled]);

  // ---- what the frame and the renderer read ---------------------------------
  // The mode on screen, chosen from the modes the file offers, and the Grid switch, which every mode draws.
  const offeredModes = normalizeViewFeatures(features).modes;
  const displayMode = {
    value: desiredScene.view.mode,
    options: DISPLAY_MODE_OPTIONS.filter(option => offeredModes.includes(option.value)),
    onChange: viewSettingsStore.selectMode,
  };
  const grid = { value: desiredScene.view.grid.enabled, onChange: viewSettingsStore.setGrid };
  // The scene Preview's own view draws (`PreviewView.jsx`): Render over the file's settings as they stand.
  // Keyed on the store's resolved scene, not the colour scheme: the store takes a new scheme (its
  // `configure`) after this render, and only its scene says the appearance has arrived — keyed on
  // the scheme, Preview kept the old look until a setting changed.
  const previewDesiredScene = useMemo(() => previewViewScene(viewSettingsStore.renderScene()),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [viewSettingsStore, desiredScene, displaySettings, previewLook, features]);
  // Preview's own settings, its panel's (`PreviewSettings.jsx`): Render's lighting, background, floor and part colours.
  const previewSettings = <PreviewRenderSettings settings={previewLook} display={displaySettings}
    appearance={colorScheme} lightingQuality="preview" onPatch={viewSettingsStore.patchPreview} onReset={viewSettingsStore.resetPreview} />;
  const projection = {
    value: desiredScene.view.camera.projection,
    onChange: value => viewSettingsStore.patch({ camera: { projection: value } }),
  };
  const stripTool = ({ id, label, icon, ...rest }) => ({
    id, label, icon, active: !previewing && toolMode === id, disabled: idle, onSelect: () => selectTool(id), ...rest
  });
  // Pencil and Shapes: the strip tools that draw, plain buttons. Each shows the tool it draws with (the pen, the line first), kept
  // when it is put down, and a press takes that one up; choosing another is the one row under the strip
  // (`RendererShell.jsx`, `annotation/toolbar.jsx`'s `AnnotationToolbar`), up while either is. A second press does nothing.
  // Its tooltip names what it draws with now, with that tool's key ("Rectangle R").
  const drawing = DRAWING_TOOLS.map(({ id, label, entries }) => {
    const variant = drawingToolVariant(id, annotation);
    const Icon = annotationToolIcon(variant);
    return stripTool({ id, label, tooltip: entries.find(entry => entry.id === variant)?.label ?? label, shortcut: DRAWING_SHORTCUTS[variant],
      icon: <Icon className="size-3" strokeWidth={2} aria-hidden="true" /> });
  });
  const tools = {
    /** A tool of the renderer's own: `{ id, label, icon }` plus anything the strip reads. */
    own: stripTool,
    /** Pencil, then Shapes: the strip tools that draw, one annotation between them. */
    drawing,
  };

  return {
    // Renderer-facing.
    toolMode, selectTool, selectDefaultTool, tools, idle, previewable, previewing, setPreviewing,
    // The file's playback settings: Orbit's speed, Autoplay, and the routine's chosen Speed and Loop.
    autoplay, setAutoplay, playback, setPlayback,
    // Preview's Orbit, on or off: off each time preview opens.
    orbiting, setOrbiting,
    // Deliver a prompt context through the host, reporting a failure as the viewport's alert.
    reportActionError, deliverPrompt, requestRender: () => viewerRef.current?.requestRender?.(),
    // A frame that keeps the shadow maps, for what moves and reshapes no shadow caster (a highlight).
    requestFrame: () => viewerRef.current?.requestFrame?.(),
    // The scene moved its own bounds: lighting, shadows and the floor follow, with no React render.
    syncSceneBounds: () => viewerRef.current?.syncSceneBounds?.(),
    // State the renderer keeps outside React changed: write the record soon (and on unmount).
    scheduleStateSave: scheduleSessionSave,
    // The view as the person set it, and its store: what a tool that edits it (a model effect) reads and writes.
    viewSettings: { view: desiredScene.view, store: viewSettingsStore },
    // Frame-facing (RendererShell).
    frame: {
      view, hostRef, hostElement, sceneBackdrop, modelKey, presentationKey, sceneScaleMode, scene,
      viewerRef, previewViewRef, viewUpdate, resolvedScene, viewerPerspective, activePerspectiveRef, handlePerspectiveChange,
      onCameraSettled: reportCameraSettled,
      preserveInteractionPixelRatio: preserveInteractionPixelRatio === true,
      runtimeLifecycle: stableRuntimeLifecycle,
      previewOrbitSpeed, setPreviewOrbitSpeed, toolStack, changeToolStack, viewerLoading, loading, presentationState,
      handlePresentationChange, viewerAlert, setRuntimeAlert,
      copyActionRef, copyAnnotation, copyShortcut: host.environment.platform === "darwin" ? "⌘C" : "Ctrl+C",
      // Quick Edit's: the file it is about, how a copied prompt spells its paths, its annotation, and
      // the renderer's own Escape, which an empty Quick Edit passes on.
      resource, captureView, escape: escapeView, currentView, quickEditPrompt,
      // Select is the tool in hand (the default one), where a press on ink picks it before a part.
      selecting: !previewing && Boolean(toolModes) && toolMode === toolModes.defaultMode,
      annotateToolActive, annotation, history, deletePicked, toolKeys: toolKeysRef, animation, previewSettings, displayMode, grid, projection, sceneEffects,
      previewDesiredScene
    }
  };
}
