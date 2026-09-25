import { useViewerMobile } from "../../../file-viewer/responsive.js";
import { useCallback, useContext, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { Camera, Pencil } from "lucide-react";
import { clonePerspectiveSnapshot } from "@hardcore/core/lib/perspective.js";
import { VIEWER_SCENE_SCALE } from "@hardcore/core/lib/viewer/sceneScale.js";
import { ViewerElementContext, useViewerHost, usePromptDestination } from "../../../host/context.js";
import { CAD_PANEL } from "../../../file-viewer/navigation/panels.js";
import { useDrawingSession } from "../../../drawing/session.js";
import { DrawingToolbar, DRAWING_TOOLBAR_TOOLS } from "../../../drawing/toolbar.jsx";
import { sceneBackdropEdgeColor } from "../look/chromeBackdrop.js";
import { useChromeBackdropColor } from "../look/useChromeBackdropColor.js";
import { prefetchRenderStudio } from "../look/renderStudioChunk.js";
import ToolPopover from "../tools/ToolPopover.jsx";
import { CAD_DRAWING_DEFAULTS } from "../tools/draw/DrawingOverlay.jsx";
import { normalizeOrbit } from "../tools/fullscreen/orbitPreferences.js";
import { animationControlsHaveContent } from "../tools/playbar/ViewportAnimationBar.js";
import { DisplaySettingsSection } from "../view-settings/DisplaySettingsSection.js";
import { useAppliedViewSettings } from "../view-settings/useAppliedViewSettings.js";
import { useViewSettings } from "../view-settings/useViewSettings.js";
import { cameraForViewSettings, viewerDisplaySettingsForCamera } from "../view-settings/viewerDisplaySettings.js";
import { attachLiveBinding } from "./liveBinding.js";
import { shellLoadReport } from "./loadReport.js";
import { createViewPromptContext, promptDeliveryError } from "./promptContext.js";
import { readShellState, scopeShellCamera, shellPresentationKey, shellStatesEqual, writeShellState } from "./shellState.js";
import { useViewerShortcuts } from "./useViewerShortcuts.js";

/** The tool ids the shell itself understands. A renderer's own tools use any other id. */
export const SHELL_TOOL = Object.freeze({ DRAW: "draw", DISPLAY: "display" });

const SESSION_SAVE_DELAY_MS = 180;
const EMPTY = Object.freeze({});

/**
 * Everything a file-family renderer needs from its host that is not about its
 * scene. The renderer loads its document and builds its scene; this hook owns
 * the rest and hands back one `shell` object for `<RendererShell>`:
 *
 *  - per-file state through the host (`state` / `onStateChange`): camera,
 *    Display settings, the recorded tool, and one `renderer` slot that is the
 *    renderer's own;
 *  - Display settings: store, resolution against the renderer's FEATURES, the
 *    queued application to the viewport, and the Display panel's content;
 *  - tools: the mode state machine and Draw's session, or none at all for a
 *    renderer whose viewport is the camera's alone;
 *  - the host contract: the file's panels, navbar actions, prompt snapshots,
 *    clipboard screenshots, fullscreen, alerts, shortcuts;
 *  - the live command surface, with the renderer's added and declined commands.
 *
 * @param {object} options
 * @param {import("../../../file-viewer/types.js").RendererViewProps} options.view  The host's props, unchanged.
 * @param {{ preferences: { orbit?: { speed: number } }, onPreferenceChange(patch: object): void,
 *   live?: object, captureRequest?: { key: string | number } | null,
 *   acknowledgeCommand?: (kind: string, key: string | number) => void }} options.services
 * @param {import("@hardcore/core/prompt").ResourceRef} options.resource  The document on screen, for prompt context and live state.
 * @param {string} options.modelKey  Stable per file: scopes the stored camera and the presentation.
 * @param {string} [options.revisionKey]  Changes when the file's bytes do.
 * @param {import("@hardcore/core/common/viewSettings.js").ViewFeatures} options.features
 * @param {object} [options.viewSettings]  The result of `useViewSettings`, when the renderer needs the
 *   display settings earlier in its own render than this hook could hand them back. It may also carry
 *   `applied`: the renderer's own `useAppliedViewSettings` result, for a renderer that must read the
 *   RESOLVED view that early too — a renderer that decides what to load, and at what detail, from the
 *   view it is showing. Such a renderer owns the viewport's handle as well and passes it as `viewerRef`.
 * @param {{ current: object | null }} [options.viewerRef]  The ref the viewport's handle lands in, when
 *   the renderer made it itself (see `viewSettings.applied`).
 * @param {ReturnType<typeof import("../tools/toolModes.js").createToolModes> | null} [options.toolModes]  Omitted
 *   by a renderer with no tools: the shell then has no active tool and a saved tab records none.
 * @param {{ mode: string, set: (update: (current: string) => string) => void }} [options.tool]  The tool in
 *   hand, when the renderer holds that state itself: a renderer whose LOAD, or what Escape means in it,
 *   turns on which tool is up cannot wait for this hook to hand it back. The rules stay the shell's —
 *   `set` is given the mode `toolModes` decided. Omitted: the shell holds the state.
 * @param {import("../scene.js").KitScene | null} options.scene
 * @param {{ busy: boolean, updating?: boolean, progress?: object | null, alert?: object | null,
 *   editPending?: boolean, currentPreview?: boolean, finding?: boolean }} options.load  The
 *   renderer's document load. `busy`: nothing to show yet. `updating`: a newer revision is loading behind the scene on
 *   screen. The rest are for a renderer whose document is more than a download — see `loadReport.js`.
 * @param {object | null} [options.animation]  A playbar runtime (with its own `clock`), when the file has
 *   routines. The playbar is then always under the model; it is not a tool to take up and leave.
 * @param {{ commands?: Record<string, (...args: any[]) => void>, declined?: Record<string, string>,
 *   state?: () => object, resource?: () => object }} [options.live]  Live commands this renderer adds (by name) or
 *   declines (name to the error its caller reads), and extra fields for the live state. Every name in
 *   `HOST_LIVE_COMMANDS` must be one or the other. `resource` is the document the viewport is SHOWING, when that
 *   can lag the one being loaded (a rebuild whose predecessor is retained): live state reports what is on screen,
 *   never what is on its way in. Omitted: the resource the renderer was handed.
 * @param {() => import("@hardcore/core/prompt").PromptReference[]} [options.promptReferences]  What a snapshot
 *   depicts, when that is narrower than the whole file (a selection). Default: the file.
 * @param {(input: { resource: object, references: object[], capture: Promise<Blob> }) => object} [options.promptContext]
 *   How this renderer assembles a snapshot's prompt context. Default `createViewPromptContext`, which takes
 *   references already in the prompt grammar; a renderer with a reference vocabulary of its own supplies the
 *   builder that speaks it, and then `promptReferences` may return that vocabulary instead — and such a
 *   renderer reports its live `selection` itself, in the prompt grammar, through `live.state`.
 * @param {{ active?: boolean, handle?: () => boolean }} [options.escape]  Escape, innermost first: `handle` returns
 *   true when it spent the key; otherwise the shell closes the file's open panel.
 * @param {object | (() => object)} [options.rendererState]  The renderer's own slice of the per-file record. A
 *   FUNCTION is read when the record is written, never at render: state a renderer keeps outside React (a pose
 *   written per frame) is saved as it is at that moment, its last change before unmount included. Such a
 *   renderer calls `shell.scheduleStateSave()` when that state changes.
 * @param {{ opensIn?: string, never?: string[] }} [options.toolRestore]  How this FILE restores its tool
 *   (`toolModes.restore`): `opensIn` is the tool a file with nothing recorded opens in, while the tool modes'
 *   default stays what a session falls back to; `never` lists recorded tools this file does not come back in.
 * @param {() => void} [options.onCameraSettled]  The camera came to rest on a new view: it moved and was
 *   recorded, a presentation camera moved (fullscreen, which records nothing), or the viewport's size
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
 * @param {(presentation: { file: string, key: string, renderMode: boolean, covering: boolean,
 *   preparing: boolean }) => void} [options.onPresentationChange]  The viewport published what it is
 *   presenting. The shell always keeps this for its own report; this is for a renderer that must
 *   answer "is what is on screen the document I asked for" itself — a live preview deciding whether
 *   its own result has landed. Compare `key` with `shellPresentationKey(modelKey, revisionKey)`.
 * @param {object} [options.displayProps]  Extra Display props for sections the renderer's FEATURES opt into.
 * @param {string} [options.sceneScaleMode]
 */
export function useRendererShell({
  view, services, resource, modelKey, revisionKey = "", features, toolModes = null, tool = null, scene, load,
  viewSettings = null, viewerRef: providedViewerRef = null,
  animation = null, live = EMPTY, promptReferences = null, promptContext = createViewPromptContext,
  escape = EMPTY, rendererState = EMPTY, toolRestore = EMPTY, displayProps = EMPTY,
  onCameraSettled = null, preserveInteractionPixelRatio = false, runtimeLifecycle = null,
  onRuntimeAlert = null, onPresentationChange = null,
  sceneScaleMode = VIEWER_SCENE_SCALE.CAD
}) {
  const host = useViewerHost();
  const viewerElement = useContext(ViewerElementContext);
  const destination = usePromptDestination();
  const promptAvailable = destination.available;
  const composer = destination.kind === "composer";
  const { fullscreen = false, openPanel = "", onPanelOpen,
    onNavigationActionsChange, onStateChange, appearance } = view;
  const colorScheme = appearance?.colorScheme === "dark" ? "dark" : "light";
  const previewMode = fullscreen;

  // ---- per-file state -------------------------------------------------------
  const [restored] = useState(() => readShellState(view.state));
  // A renderer whose own work needs the display settings BEFORE it can hand this hook a scene
  // — one that reads them while it is still deciding what to load — creates them itself and passes
  // them in. It is the same store either way; owning it here is a convenience, not a rule.
  const ownViewSettings = useViewSettings(colorScheme);
  const { display: displaySettings, scene: desiredScene, store: viewSettingsStore } =
    viewSettings || ownViewSettings;
  useLayoutEffect(() => { viewSettingsStore.configure({ features }); }, [viewSettingsStore, features]);
  // Before the first paint, like every later edit: through the store, never around it.
  useLayoutEffect(() => { viewSettingsStore.restore(restored.display); }, [viewSettingsStore, restored]);
  const ownViewerRef = useRef(null);
  const viewerRef = providedViewerRef || ownViewerRef;
  // Exactly one coordinator drives one viewport. A renderer that resolved the view itself
  // hands the result in, and this call stands down (`useAppliedViewSettings`).
  const appliedByRenderer = viewSettings?.applied || null;
  const ownViewUpdate = useAppliedViewSettings(desiredScene, appliedByRenderer ? null : modelKey, viewerRef, viewSettingsStore);
  const viewUpdate = appliedByRenderer || ownViewUpdate;
  const resolvedScene = viewUpdate.scene;
  const rendering = resolvedScene.render.enabled;
  useEffect(() => { if (rendering) prefetchRenderStudio(); }, [rendering]);

  const activePerspectiveRef = useRef(null);
  const [viewerPerspective, setViewerPerspective] = useState(null);
  // "" is a renderer with no tools at all: there is no active tool to be in, and
  // nothing for a saved tab to record.
  const [ownToolMode, setOwnToolMode] = useState(() => (toolModes ? toolModes.restore(restored.tool, toolRestore) : ""));
  const toolMode = tool ? tool.mode : ownToolMode;
  const setToolMode = tool ? tool.set : setOwnToolMode;
  const recordRef = useRef(null);
  const onStateChangeRef = useRef(onStateChange);
  onStateChangeRef.current = onStateChange;
  const latestRecord = useRef(null);
  latestRecord.current = () => writeShellState({
    display: viewSettingsStore.getSnapshot().display,
    tool: toolModes ? toolModes.persisted(toolMode) : "",
    renderer: typeof rendererState === "function" ? rendererState() : rendererState
  });
  const saveTimer = useRef(0);
  const flushSession = useCallback(() => {
    window.clearTimeout(saveTimer.current);
    saveTimer.current = 0;
    const next = latestRecord.current();
    if (shellStatesEqual(recordRef.current, next)) return;
    recordRef.current = next;
    onStateChangeRef.current?.(next);
  }, []);
  const scheduleSessionSave = useCallback(() => {
    window.clearTimeout(saveTimer.current);
    saveTimer.current = window.setTimeout(flushSession, SESSION_SAVE_DELAY_MS);
  }, [flushSession]);
  useEffect(() => { scheduleSessionSave(); }, [displaySettings, toolMode, rendererState, scheduleSessionSave]);
  useEffect(() => () => flushSession(), [flushSession]);

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
    if (previewMode) return;
    const snapshot = clonePerspectiveSnapshot(nextPerspective);
    if (!snapshot) return;
    activePerspectiveRef.current = snapshot;
  }, [previewMode]);

  // ---- host chrome ----------------------------------------------------------
  // The file's panels are the host's (its nav row is their tab strip); the shell draws the
  // one that is open. A sidebar that is open turns to the file's own panel when there is
  // something to show in it — a pick, the Position tool — the file tree giving way to what
  // was picked; an explicit tool request opens the panel even when nothing is open, a
  // selection does not. On mobile the sheets stay the person's to open.
  const mobile = useViewerMobile();
  const panelRef = useRef({ openPanel, onPanelOpen });
  panelRef.current = { openPanel, onPanelOpen };
  const panelOpen = openPanel === CAD_PANEL.file;
  const closePanel = useCallback(() => {
    const current = panelRef.current.openPanel;
    if (current === CAD_PANEL.file) panelRef.current.onPanelOpen?.("");
  }, []);
  const [panelRevealRequest, setPanelRevealRequest] = useState(null);
  const revealFilePanel = useCallback(() => {
    // Below this width the panel covers the model it was asked about, so it stays the person's to open.
    if (mobile) return;
    if (panelRef.current.openPanel !== CAD_PANEL.file) panelRef.current.onPanelOpen?.(CAD_PANEL.file);
  }, [mobile]);
  const revealFileSection = useCallback((sectionId, { open = true } = {}) => {
    if (mobile || (!open && !panelRef.current.openPanel)) return;
    revealFilePanel();
    setPanelRevealRequest(previous => ({ sectionId, key: (previous?.key || 0) + 1 }));
  }, [mobile, revealFilePanel]);
  const chromeBackdropColor = useChromeBackdropColor(colorScheme === "dark");
  const sceneBackdrop = useMemo(
    () => resolvedScene.view.background.enabled && resolvedScene.view.background.opacity === 1
      ? resolvedScene.view.background.color
      : resolvedScene.view.background.enabled ? chromeBackdropColor
        : sceneBackdropEdgeColor(resolvedScene.theme?.background, chromeBackdropColor),
    [chromeBackdropColor, resolvedScene.theme, resolvedScene.view.background]
  );
  const previewOrbitSpeed = normalizeOrbit(services.preferences?.orbit).speed;
  const setPreviewOrbitSpeed = useCallback(speed => services.onPreferenceChange({ orbit: normalizeOrbit({ speed }) }),
    [services.onPreferenceChange]);
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
  const presentationKey = shellPresentationKey(modelKey, revisionKey);
  const [presentationState, setPresentationState] = useState(null);
  const presentationReportRef = useRef(onPresentationChange);
  presentationReportRef.current = onPresentationChange;
  const handlePresentationChange = useCallback((next) => {
    presentationReportRef.current?.(next);
    setPresentationState(previous => previous?.file === next.file && previous?.renderMode === next.renderMode &&
      previous?.key === next.key && previous?.covering === next.covering && previous?.preparing === next.preparing ? previous : next);
  }, []);
  const presentationPending = hasContent && (
    presentationState?.file !== modelKey || presentationState?.key !== presentationKey ||
    presentationState?.renderMode !== rendering || presentationState?.preparing === true
  );
  const completedView = useRef(false);
  useEffect(() => { if (hasContent && !presentationPending) completedView.current = true; }, [hasContent, presentationPending]);
  const viewerAlert = runtimeAlert?.blocking ? runtimeAlert : viewerLoading ? null : load.alert || runtimeAlert || null;
  const loading = shellLoadReport({
    load, alert: viewerAlert, busy: presentationPending,
    previousView: completedView.current && hasContent, preparing: presentationPending && !viewerLoading
  });

  // ---- tools ----------------------------------------------------------------
  const idle = viewerLoading || !scene;
  // A file with routines shows the playbar, always: it is not a tool to take up and
  // leave, so the file simply opens at rest with its transport under the model.
  const animationAvailable = animationControlsHaveContent(animation);
  const drawToolActive = !previewMode && toolMode === SHELL_TOOL.DRAW;
  const selectTool = useCallback((mode) => setToolMode(current => (toolModes ? toolModes.next(current, mode) : mode)), [toolModes, setToolMode]);
  const drawing = useDrawingSession(drawToolActive, CAD_DRAWING_DEFAULTS);

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
  const copyDrawing = useCallback(async () => {
    if (!drawing.hasContent || !viewerRef.current?.captureScreenshotBlob) return;
    try {
      await host.clipboard.writeImage(viewerRef.current.captureScreenshotBlob());
    } catch (error) { reportActionError(error); }
  }, [drawing.hasContent, host.clipboard, reportActionError]);
  const captureKey = services.captureRequest?.key ?? null;
  const appliedCaptureKey = useRef(null);
  useEffect(() => {
    if (captureKey === null || appliedCaptureKey.current === captureKey || viewerLoading || !promptAvailable) return;
    appliedCaptureKey.current = captureKey;
    services.acknowledgeCommand?.("captureRequest", captureKey);
    capture();
  }, [captureKey, viewerLoading, promptAvailable, services.acknowledgeCommand, capture]);

  // Publishing navbar actions must not feed parent renders back into this renderer.
  const captureRef = useRef(capture);
  captureRef.current = capture;
  useEffect(() => {
    const actions = modelKey ? [{ id: "snapshot", label: "Take snapshot", icon: Camera,
      disabled: viewerLoading || !scene || !promptAvailable, onInvoke: () => captureRef.current() }] : [];
    onNavigationActionsChange?.(actions);
    return () => onNavigationActionsChange?.([]);
  }, [onNavigationActionsChange, modelKey, viewerLoading, Boolean(scene), promptAvailable]);

  // ---- shortcuts ------------------------------------------------------------
  const previewExitRef = useRef(null);
  const escapeRef = useRef(escape.handle);
  escapeRef.current = escape.handle;
  useViewerShortcuts({
    viewerElement, previewMode,
    onCopy: () => copyActionRef.current?.() || false,
    escapeActive: Boolean(panelOpen || escape.active),
    onEscape() {
      // Menu dismissal owns Escape before either Preview or the hidden sidebar.
      if (viewerElement.current?.ownerDocument.querySelector('[role="menu"][data-state="open"], [role="listbox"], [data-cad-display-popover][data-state="open"]')) return;
      if (previewExitRef.current?.() === true) return;
      if (escapeRef.current?.() === true) return;
      closePanel();
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
      return {
        resource: { ...shown }, revision: String(shown.revision || ""), loading: viewerLoading || !scene,
        // Live state reads the selection in the prompt grammar. References are already in it
        // only where the default builder assembles the snapshot; a renderer that keeps its own
        // vocabulary reports its selection through `live.state`, so it is never passed on raw.
        selection: promptContextRef.current === createViewPromptContext ? referencesRef.current?.() || [] : [],
        camera: clonePerspectiveSnapshot(viewerRef.current?.getPerspective?.() || activePerspectiveRef.current),
        display, renderMode: display.mode === "render" ? "render" : "inspect",
        ...(live.state?.() || {})
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
      if (previewMode) {
        if (!viewerRef.current?.setPerspective?.(requested)) throw new Error("The viewer could not apply this camera.");
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
      if (!viewerRef.current?.resetZoom?.()) throw new Error("The viewer camera is unavailable.");
    },
    setDisplaySettings(patch) { viewSettingsStore.patch(patch); },
    setRenderMode(enabled) { viewSettingsStore.selectPreset(enabled ? "render" : "solid"); },
    capture() {
      if (!viewerRef.current?.captureScreenshotBlob) throw new Error("The viewer cannot capture this model yet.");
      return viewerRef.current.captureScreenshotBlob();
    },
    ...(live.commands || {})
  };
  const liveBinding = services.live;
  const commandNames = Object.keys(live.commands || {}).sort().join("\n");
  const declinedRef = useRef(live.declined);
  declinedRef.current = live.declined;
  useEffect(() => {
    if (!liveBinding) return undefined;
    return attachLiveBinding(liveBinding, () => liveRuntimeRef.current, {
      commands: commandNames ? commandNames.split("\n") : [], declined: declinedRef.current || {}
    });
  }, [liveBinding, commandNames]);

  // ---- what the frame and the renderer read ---------------------------------
  // The Display panel's content: every renderer's, built here from its display settings.
  const display = <DisplaySettingsSection
    features={features} viewSettings={displaySettings} hostAppearance={colorScheme} lightingQuality="preview"
    resolvedView={desiredScene.view} onViewSettingsPatch={viewSettingsStore.patch}
    onGroupEnabledChange={viewSettingsStore.setEnabled} onModeChange={viewSettingsStore.selectPreset}
    onViewReset={viewSettingsStore.reset}
    // What only an opted-in section reads (its bounds, its status): the renderer that opted in supplies it.
    {...displayProps} />;
  const stripTool = ({ id, label, icon, ...rest }) => ({
    id, label, icon, active: !previewMode && toolMode === id, disabled: idle, onSelect: () => selectTool(id), ...rest
  });
  const [drawMenuOpen, setDrawMenuOpen] = useState(false);
  const DrawIcon = DRAWING_TOOLBAR_TOOLS.find(item => item.id === drawing.tool)?.Icon || Pencil;
  const tools = {
    /** A tool of the renderer's own: `{ id, label, icon }` plus anything the strip reads. */
    own: stripTool,
    draw: stripTool({ id: SHELL_TOOL.DRAW, label: "Draw", icon: <DrawIcon data-drawing-tool={drawing.tool} className="size-3" strokeWidth={2} aria-hidden="true" />,
      secondPressOpensMenu: true,
      description: "Open the corner menu for drawing tools and settings",
      onSelect: () => { if (!drawToolActive) selectTool(SHELL_TOOL.DRAW); },
      menu: trigger => <ToolPopover trigger={trigger} label="Drawing controls" className="w-auto p-1"
        onFocusOutside={event => event.preventDefault()}
        open={drawMenuOpen} onOpenChange={setDrawMenuOpen}>
        <DrawingToolbar drawing={drawing} layout="panel" onToolSelect={() => setDrawMenuOpen(false)} onClear={() => setDrawMenuOpen(false)} />
      </ToolPopover> }),
  };

  return {
    // Renderer-facing.
    toolMode, selectTool, tools, display, idle, previewMode, rendering, resolvedScene, viewerRef, openPanel,
    reportActionError, capture, requestRender: () => viewerRef.current?.requestRender?.(),
    // The scene moved its own bounds: lighting, shadows and the floor follow, with no React render.
    syncSceneBounds: () => viewerRef.current?.syncSceneBounds?.(),
    // State the renderer keeps outside React changed: write the record soon (and on unmount).
    scheduleStateSave: scheduleSessionSave,
    revealFilePanel, revealFileSection, panelRevealRequest, previewExitRef,
    // Frame-facing (RendererShell).
    frame: {
      view, hostRef, hostElement, viewerElement, sceneBackdrop, colorScheme, modelKey, presentationKey, sceneScaleMode, scene,
      viewerRef, viewUpdate, resolvedScene, viewerPerspective, activePerspectiveRef, handlePerspectiveChange,
      onCameraSettled: reportCameraSettled,
      preserveInteractionPixelRatio: preserveInteractionPixelRatio === true,
      runtimeLifecycle: stableRuntimeLifecycle,
      previewMode, previewOrbitSpeed, setPreviewOrbitSpeed, viewerLoading, loading, presentationState,
      handlePresentationChange, viewerAlert, setRuntimeAlert,
      copyActionRef, copyDrawing, copyShortcut: host.environment.platform === "darwin" ? "⌘C" : "Ctrl+C",
      drawToolActive, drawing, animationAvailable, animation, composer, capture, openPanel, display
    }
  };
}
