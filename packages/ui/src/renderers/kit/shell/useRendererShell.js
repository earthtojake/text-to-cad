import { useCallback, useContext, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { Camera, Pencil } from "lucide-react";
import { clonePerspectiveSnapshot } from "@hardcore/core/lib/perspective.js";
import { VIEWER_SCENE_SCALE } from "@hardcore/core/lib/viewer/sceneScale.js";
import { ViewerElementContext, useViewerHost, usePromptDestination } from "../../../host/context.js";
import { CAD_PANEL } from "../../../file-viewer/navigation/panels.js";
import { useDrawingSession } from "../../../drawing/session.js";
import { DrawingToolbar } from "../../../drawing/toolbar.jsx";
import { sceneBackdropEdgeColor } from "../look/chromeBackdrop.js";
import { useChromeBackdropColor } from "../look/useChromeBackdropColor.js";
import { prefetchRenderStudio } from "../look/renderStudioChunk.js";
import { resolveFileStatus } from "../status/fileStatus.js";
import { fileStatusAlertKey, resolveFileStatusAlert } from "../status/loadAlerts.js";
import { viewerLoadingState } from "../status/loadingState.js";
import { useFileActivityReport } from "../status/useFileActivityReport.js";
import { CAD_DRAWING_DEFAULTS } from "../tools/draw/DrawingOverlay.jsx";
import { normalizeOrbit } from "../tools/fullscreen/orbitPreferences.js";
import { animationControlsHaveContent } from "../tools/playbar/ViewportAnimationBar.js";
import { buildDisplaySettingsTab } from "../view-settings/DisplaySettingsTab.js";
import { useAppliedViewSettings } from "../view-settings/useAppliedViewSettings.js";
import { useViewSettings } from "../view-settings/useViewSettings.js";
import { cameraForViewSettings, viewerDisplaySettingsForCamera } from "../view-settings/viewerDisplaySettings.js";
import { attachLiveBinding } from "./liveBinding.js";
import { createViewPromptContext, promptDeliveryMessage } from "./promptContext.js";
import { readShellState, scopeShellCamera, shellStatesEqual, writeShellState } from "./shellState.js";
import { useViewerShortcuts } from "./useViewerShortcuts.js";

/** The tool ids the shell itself understands. A renderer's own tools use any other id. */
export const SHELL_TOOL = Object.freeze({ DRAW: "draw" });

const SESSION_SAVE_DELAY_MS = 180;
const INSPECTOR_REVEAL_MIN_WIDTH_PX = 520;
const EMPTY = Object.freeze({});

/**
 * Everything a file-family renderer needs from its host that is not about its
 * scene. The renderer loads its document and builds its scene; this hook owns
 * the rest and hands back one `shell` object for `<RendererShell>`:
 *
 *  - per-file state through the host (`state` / `onStateChange`): camera,
 *    Display settings, the open Inspector tab, the recorded tool, and one
 *    `renderer` slot that is the renderer's own;
 *  - Display settings: store, resolution against the renderer's FEATURES, the
 *    queued application to the viewport, and the Display tab;
 *  - tools: the mode state machine and Draw's session, or none at all for a
 *    renderer whose viewport is the camera's alone;
 *  - the host contract: Inspector panel, navbar actions, prompt snapshots,
 *    clipboard screenshots, fullscreen, file activity, alerts, shortcuts;
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
 * @param {ReturnType<typeof import("../tools/toolModes.js").createToolModes> | null} [options.toolModes]  Omitted
 *   by a renderer with no tools: the shell then has no active tool and a saved tab records none.
 * @param {import("../scene.js").KitScene | null} options.scene
 * @param {{ busy: boolean, updating?: boolean, progress?: object | null, alert?: object | null }} options.load  The
 *   renderer's document load. `busy`: nothing to show yet. `updating`: a newer revision is loading behind the scene on screen.
 * @param {object | null} [options.animation]  A playbar runtime (with its own `clock`), when the file has
 *   routines. The playbar is then always under the model; it is not a tool to take up and leave.
 * @param {{ commands?: Record<string, (...args: any[]) => void>, declined?: Record<string, string>,
 *   state?: () => object }} [options.live]  Live commands this renderer adds (by name) or declines (name to the
 *   error its caller reads), and extra fields for the live state. Every name in `HOST_LIVE_COMMANDS` must be one or the other.
 * @param {() => import("@hardcore/core/prompt").PromptReference[]} [options.promptReferences]  What a snapshot
 *   depicts, when that is narrower than the whole file (a selection). Default: the file.
 * @param {{ active?: boolean, handle?: () => boolean }} [options.escape]  Escape, innermost first: `handle` returns
 *   true when it spent the key; otherwise the shell closes the alert dialog and the Inspector.
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
 * @param {object} [options.displayTabProps]  Extra Display tab props for sections the renderer's FEATURES opt into.
 * @param {string} [options.sceneScaleMode]
 */
export function useRendererShell({
  view, services, resource, modelKey, revisionKey = "", features, toolModes = null, scene, load,
  animation = null, live = EMPTY, promptReferences = null,
  escape = EMPTY, rendererState = EMPTY, toolRestore = EMPTY, displayTabProps = EMPTY,
  onCameraSettled = null, preserveInteractionPixelRatio = false, runtimeLifecycle = null,
  sceneScaleMode = VIEWER_SCENE_SCALE.CAD
}) {
  const host = useViewerHost();
  const viewerElement = useContext(ViewerElementContext);
  const destination = usePromptDestination();
  const promptAvailable = destination.available;
  const composer = destination.kind === "composer";
  const { fullscreen = false, openPanel = "", onPanelOpen, onChromeVisibilityChange, onActivityChange,
    onNavigationActionsChange, onStateChange, appearance } = view;
  const colorScheme = appearance?.colorScheme === "dark" ? "dark" : "light";
  const previewMode = fullscreen;

  // ---- per-file state -------------------------------------------------------
  const [restored] = useState(() => readShellState(view.state));
  const { display: displaySettings, scene: desiredScene, store: viewSettingsStore } = useViewSettings(colorScheme);
  useLayoutEffect(() => { viewSettingsStore.configure({ features }); }, [viewSettingsStore, features]);
  // Before the first paint, like every later edit: through the store, never around it.
  useLayoutEffect(() => { viewSettingsStore.restore(restored.display); }, [viewSettingsStore, restored]);
  const viewerRef = useRef(null);
  const viewUpdate = useAppliedViewSettings(desiredScene, modelKey, viewerRef, viewSettingsStore);
  const resolvedScene = viewUpdate.scene;
  const rendering = resolvedScene.render.enabled;
  useEffect(() => { if (rendering) prefetchRenderStudio(); }, [rendering]);

  const activePerspectiveRef = useRef(null);
  const [viewerPerspective, setViewerPerspective] = useState(() => {
    // Only a camera this file actually recorded comes back; otherwise the viewport fits the model.
    const camera = cameraForViewSettings(restored.camera, restored.display, { lightingQuality: "preview" });
    const scoped = camera ? scopeShellCamera(camera, modelKey, sceneScaleMode) : null;
    activePerspectiveRef.current = scoped;
    return scoped;
  });
  const [inspectorTab, setInspectorTab] = useState(restored.inspectorTab);
  // "" is a renderer with no tools at all: there is no active tool to be in, and
  // nothing for a saved tab to record.
  const [toolMode, setToolMode] = useState(() => (toolModes ? toolModes.restore(restored.tool, toolRestore) : ""));
  const recordRef = useRef(null);
  const onStateChangeRef = useRef(onStateChange);
  onStateChangeRef.current = onStateChange;
  const latestRecord = useRef(null);
  latestRecord.current = () => writeShellState({
    camera: activePerspectiveRef.current, display: viewSettingsStore.getSnapshot().display,
    inspectorTab, tool: toolModes ? toolModes.persisted(toolMode) : "",
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
  useEffect(() => { scheduleSessionSave(); }, [displaySettings, inspectorTab, toolMode, rendererState, scheduleSessionSave]);
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
    scheduleSessionSave();
  }, [previewMode, scheduleSessionSave]);

  // ---- host chrome ----------------------------------------------------------
  useEffect(() => { onChromeVisibilityChange?.(!previewMode); }, [onChromeVisibilityChange, previewMode]);
  const panelRef = useRef({ openPanel, onPanelOpen });
  panelRef.current = { openPanel, onPanelOpen };
  const inspectorOpen = openPanel === CAD_PANEL.fileSheet;
  const setInspectorOpen = useCallback((value) => {
    const current = panelRef.current.openPanel === CAD_PANEL.fileSheet;
    const next = typeof value === "function" ? value(current) : value;
    if (next !== current) panelRef.current.onPanelOpen?.(next ? CAD_PANEL.fileSheet : "");
  }, []);
  const revealInspectorTab = useCallback((tab) => {
    // Below this width the panel covers the model it was asked about, so it stays the person's to open.
    if (window.matchMedia?.(`(min-width: ${INSPECTOR_REVEAL_MIN_WIDTH_PX}px)`)?.matches ?? true) setInspectorOpen(true);
    setInspectorTab(String(tab || ""));
  }, [setInspectorOpen]);
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

  // ---- loading, alerts, activity -------------------------------------------
  const [copyStatus, setCopyStatus] = useState("");
  const [screenshotStatus, setScreenshotStatus] = useState("");
  const [viewerAlertOpen, setViewerAlertOpen] = useState(false);
  const [runtimeAlert, setRuntimeAlert] = useState(null);
  const viewerLoading = Boolean(load.busy);
  const hasContent = Boolean(scene) && !viewerLoading;
  const presentationKey = modelKey ? `${modelKey}:${revisionKey}:complete` : "";
  const [presentationState, setPresentationState] = useState(null);
  const handlePresentationChange = useCallback((next) => {
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
  const loading = viewerLoadingState({
    busy: viewerLoading || Boolean(load.updating) || presentationPending,
    previousView: completedView.current && hasContent,
    error: viewerAlert,
    progress: load.progress || null,
    preparing: presentationPending && !viewerLoading
  });
  const fileStatus = resolveFileStatus({
    hasFile: Boolean(modelKey), error: viewerAlert, opening: loading.opening, updating: loading.updating,
    loadingProgress: loading.progress, renderMode: rendering, hasGeometry: hasContent
  });
  const fileStatusAlert = resolveFileStatusAlert(fileStatus, viewerAlert);
  const alertKey = fileStatusAlertKey(modelKey, fileStatusAlert);
  useEffect(() => { setViewerAlertOpen(false); }, [alertKey]);
  const activity = useMemo(() => fileStatus ? {
    loading: fileStatus.busy === true, label: fileStatus.label, title: fileStatus.title, tone: fileStatus.tone,
    onActivate: fileStatusAlert ? () => setViewerAlertOpen(true) : undefined
  } : null, [fileStatus?.busy, fileStatus?.label, fileStatus?.title, fileStatus?.tone, Boolean(fileStatusAlert)]);
  useFileActivityReport(activity, onActivityChange);

  // ---- tools ----------------------------------------------------------------
  const idle = viewerLoading || !scene;
  // A file with routines shows the playbar, always: it is not a tool to take up and
  // leave, so the file simply opens at rest with its transport under the model.
  const animationAvailable = animationControlsHaveContent(animation);
  const drawToolActive = !previewMode && toolMode === SHELL_TOOL.DRAW;
  const selectTool = useCallback((mode) => setToolMode(current => (toolModes ? toolModes.next(current, mode) : current)), [toolModes]);
  const drawing = useDrawingSession(drawToolActive, CAD_DRAWING_DEFAULTS);

  // ---- prompt snapshots, clipboard ------------------------------------------
  const showPromptResult = useCallback((result) => setCopyStatus(promptDeliveryMessage(result)), []);
  const deliverPrompt = useCallback((context) => {
    let pending;
    try { pending = host.promptContext.deliver(context); }
    catch (error) { pending = Promise.reject(error); }
    return Promise.resolve(pending).catch(error => ({ status: "failed", message: error instanceof Error ? error.message : String(error) }))
      .then(result => { showPromptResult(result); return result; });
  }, [host.promptContext, showPromptResult]);
  const referencesRef = useRef(promptReferences);
  referencesRef.current = promptReferences;
  // Freeze references now; the host binds its destination before waiting for the PNG.
  const capture = useCallback(() => {
    if (!modelKey || !promptAvailable || viewerLoading) return;
    try {
      if (!viewerRef.current?.captureScreenshotBlob) throw new Error("The viewer is not ready");
      const pixels = viewerRef.current.captureScreenshotBlob();
      void pixels.catch(() => {});
      void deliverPrompt(createViewPromptContext({ resource, references: referencesRef.current?.() || [], capture: pixels }));
    } catch (error) { setScreenshotStatus(error instanceof Error ? error.message : "Capture failed"); }
  }, [modelKey, promptAvailable, viewerLoading, deliverPrompt, resource]);
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
  const escapeRef = useRef(escape.handle);
  escapeRef.current = escape.handle;
  useViewerShortcuts({
    viewerElement, previewMode, copyStatus, screenshotStatus, setCopyStatus, setScreenshotStatus,
    escapeActive: Boolean(viewerAlertOpen || inspectorOpen || escape.active),
    onEscape() {
      if (escapeRef.current?.() === true) return;
      setViewerAlertOpen(false);
      setInspectorOpen(false);
    }
  });

  // ---- live command surface ---------------------------------------------------
  const liveRuntimeRef = useRef(null);
  liveRuntimeRef.current = {
    readState() {
      const display = viewSettingsStore.getSnapshot().display;
      return {
        resource: { ...resource }, revision: String(resource.revision || ""), loading: viewerLoading || !scene,
        selection: referencesRef.current?.() || [],
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
  const displayTab = buildDisplaySettingsTab({
    features, viewSettings: displaySettings, hostAppearance: colorScheme, lightingQuality: "preview",
    resolvedView: desiredScene.view, onViewSettingsPatch: viewSettingsStore.patch,
    onGroupEnabledChange: viewSettingsStore.setEnabled, onModeChange: viewSettingsStore.selectPreset,
    onViewReset: viewSettingsStore.reset,
    // What only an opted-in section reads (its bounds, its status): the renderer that opted in supplies it.
    ...displayTabProps
  });
  const tool = ({ id, label, icon, ...rest }) => ({
    id, label, icon, active: !previewMode && toolMode === id, disabled: idle, onSelect: () => selectTool(id), ...rest
  });
  const tools = {
    /** A tool of the renderer's own: `{ id, label, icon }` plus anything the strip reads. */
    own: tool,
    draw: tool({ id: SHELL_TOOL.DRAW, label: "Draw", icon: <Pencil className="size-3" strokeWidth={2} aria-hidden="true" />,
      subToolbar: drawToolActive ? <DrawingToolbar drawing={drawing} /> : null })
  };

  return {
    // Renderer-facing.
    toolMode, selectTool, tools, displayTab, idle, previewMode, rendering, resolvedScene, viewerRef,
    setCopyStatus, setScreenshotStatus, capture, requestRender: () => viewerRef.current?.requestRender?.(),
    // The scene moved its own bounds: lighting, shadows and the floor follow, with no React render.
    syncSceneBounds: () => viewerRef.current?.syncSceneBounds?.(),
    // State the renderer keeps outside React changed: write the record soon (and on unmount).
    scheduleStateSave: scheduleSessionSave,
    // The Inspector is the host's panel. `reveal(tab)` is for something in the viewport that
    // has details to show (a pick): it turns to the tab, and opens the panel where there
    // is room for it beside the model.
    inspector: { open: inspectorOpen, setOpen: setInspectorOpen, tab: inspectorTab, setTab: setInspectorTab, reveal: revealInspectorTab },
    // Frame-facing (RendererShell).
    frame: {
      view, hostRef, hostElement, viewerElement, sceneBackdrop, colorScheme, modelKey, presentationKey, sceneScaleMode, scene,
      viewerRef, viewUpdate, resolvedScene, viewerPerspective, activePerspectiveRef, handlePerspectiveChange,
      onCameraSettled: reportCameraSettled,
      preserveInteractionPixelRatio: preserveInteractionPixelRatio === true,
      runtimeLifecycle: stableRuntimeLifecycle,
      previewMode, previewOrbitSpeed, setPreviewOrbitSpeed, viewerLoading, loading, presentationState,
      handlePresentationChange, viewerAlert, fileStatusAlert, viewerAlertOpen, setViewerAlertOpen, setRuntimeAlert,
      drawToolActive, drawing, animationAvailable, animation, composer, capture,
      inspectorOpen, setInspectorOpen, inspectorTab, setInspectorTab,
      copyStatus, screenshotStatus, setCopyStatus, setScreenshotStatus
    }
  };
}
