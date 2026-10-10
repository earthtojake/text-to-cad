import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Pencil } from "lucide-react";
import { useViewerHost, usePromptDestination } from "../../../host/context.js";
import { hasOpenPopup } from "../../../lib/popups.js";
import { DRAWING_TOOLBAR_TOOLS } from "../../../drawing/toolbar.jsx";
import { useAlertDismissal } from "../status/ViewerAlertCard.jsx";
import { SHELL_TOOL } from "../tools/toolModes.js";
import { usePlaneDrawing } from "../plane/usePlaneDrawing.js";
import { planeTransformCamera, readPlaneTransform } from "../plane/planeTransform.js";
import { createViewPromptContext, deliverPromptContext, promptDeliveryError } from "./promptContext.js";
import { readFileView, readFileViewSlices, writeFileView } from "./fileView.js";
import { useCaptureRequest, useFileViewWriter, useLiveSurface, useToolStackLayout } from "./shellHooks.js";
import { useViewerShortcuts } from "./useViewerShortcuts.js";
import { useWhenSettled } from "./useWhenSettled.js";

const EMPTY = Object.freeze({});
const NO_COMMANDS = Object.freeze({});

/**
 * The file's view of a flat picture (`fileView.js`): the picture's transform as its camera (only once
 * the person has moved it: an untouched picture is fitted to whatever pane it lands in), and the
 * renderer's own slices. Called before the picture's view, which opens at `restored` and reports
 * every move to `rememberView`.
 *
 * @param {{ view: import("../../../file-viewer/types.js").RendererViewProps,
 *   rendererState?: { signatures?: Record<string, string>, read: () => Record<string, unknown> } | null }} options
 *   `rendererState`: the renderer's slices, read when the view is written; a new one is written soon.
 *   The renderer restores them itself (`readFileView(view.state, signatures)`). Null keeps what is stored.
 * @returns {{ restored: object | null, rememberView: (transform: object | null) => void, schedule: () => void }}
 */
export function usePlaneFileView({ view, rendererState = null }) {
  const [stored] = useState(() => ({ camera: readFileView(view.state).camera, slices: readFileViewSlices(view.state) }));
  const [restored] = useState(() => readPlaneTransform(stored.camera));
  const cameraRef = useRef(planeTransformCamera(restored, Boolean(restored)));
  const stateRef = useRef(rendererState);
  stateRef.current = rendererState;
  const record = () => {
    const slices = stateRef.current;
    return writeFileView({
      camera: cameraRef.current,
      renderer: slices ? slices.read() : stored.slices.values,
      signatures: slices ? slices.signatures : stored.slices.signatures
    });
  };
  // What the host holds already is not written back to it unchanged.
  const [written] = useState(record);
  const writer = useFileViewWriter({ onStateChange: view.onStateChange, record, written });
  const { schedule } = writer;
  useEffect(() => { schedule(); }, [rendererState, schedule]);
  // A view that is still the fit stores nothing — `null` is "fit me", and it is what a picture
  // dropped back to the fit must write, not a stale transform.
  const rememberView = useCallback((transform) => {
    cameraRef.current = planeTransformCamera(transform, Boolean(transform));
    schedule();
  }, [schedule]);
  return { restored, rememberView, schedule };
}

/**
 * The shell of a view drawn as a flat picture on a canvas (`kit/plane/`): everything it needs from
 * its host that is not about its picture, as `useRendererShell` is for a 3D view's scene. The
 * renderer brings its picture's view (`plane`, from `usePlaneView` or a hook over it) and its own
 * tools and panels; this hook owns the rest and hands back one `shell` for `<PlaneShell>`:
 *
 *  - tools: the mode state machine (`toolModes`), Draw's session and its view lock over the picture
 *    (`usePlaneDrawing`), the tool stack's layout;
 *  - the host contract: prompt snapshots (the host's `captureRequest`), the clipboard (a copy of the
 *    selection's text, Draw's copy of the view with its ink), Escape and the copy key, alerts (a
 *    load's, a failed action's, and the renderer's own report, such as what a check found);
 *  - the live command surface: a flat picture's base commands (`resetCamera` fits, `capture`,
 *    `thumbnail`; no camera, no Display), with the renderer's added and declined commands.
 *
 * @param {object} options
 * @param {import("../../../file-viewer/types.js").RendererViewProps} options.view  The host's props, unchanged.
 * @param {object} options.services  `useWorkspaceDocument`'s `services`.
 * @param {import("@text-to-cad/core/prompt").ResourceRef} options.resource
 * @param {string} options.modelKey  The file, as alerts name it and as Quick Edit and the alert card are scoped.
 * @param {object} options.plane  The picture's view: `containerRef`, `canvasRef`, `dragging`, `fit`, `capture`,
 *   `thumbnail`, and for Draw `transformRef`, `setView`, `paintNow`, `settle`.
 * @param {{ shown: boolean, busy: boolean, updating?: boolean, alert?: object | null, reading: string,
 *   updateStatus: object }} options.load  `shown`: a picture is on screen; `busy`: nothing to show yet; `updating`: a
 *   newer revision is read behind the one on screen. `reading` names the open's progress, `updateStatus` the update's.
 * @param {{ noun: string, captureFailed: string, copyFailed: string, noCamera: string, noDisplay: string, displayInView?: string }} options.words
 *   What the picture is called, and the sentences of a failed capture or copy and of the commands it cannot take.
 * @param {ReturnType<typeof import("../tools/toolModes.js").createToolModes> | null} [options.toolModes]
 * @param {{ mode: string, set: (update: (current: string) => string) => void }} [options.tool]  The tool in hand, when
 *   the renderer holds it itself (its pointer is decided before this hook runs). Omitted: the shell holds it.
 * @param {{ commands?: Record<string, (...args: any[]) => void>, declined?: Record<string, string>, state?: () => object }} [options.live]
 * @param {readonly import("@text-to-cad/core/prompt").PromptReference[] | null} [options.references]  What is selected,
 *   in the prompt grammar: live state's selection, and with it the view has Quick Edit. Null: neither.
 * @param {(() => unknown) | null} [options.copySelection]  The copy key's, while something is selected.
 * @param {() => Promise<Blob>} [options.capture]  The view as a picture, when it is more than `plane.capture`.
 * @param {{ active?: boolean, handle?: () => boolean }} [options.escape]  Escape, innermost first.
 * @param {{ alert: object, startDismissed?: boolean } | null} [options.report]  The renderer's own alert, under a
 *   load's and a failed action's: put away from the start when `startDismissed`.
 * @param {boolean} [options.displayInView]  The picture has Display settings of its own, the person's, in the view.
 */
export function usePlaneShell({
  view, services, resource, modelKey, plane, load, words, toolModes = null, tool = null, live = EMPTY,
  references = null, copySelection = null, capture: captureView = null, escape = EMPTY, report = null, displayInView = false
}) {
  const host = useViewerHost();
  const destination = usePromptDestination();
  const { onReady } = view;
  useEffect(() => { onReady?.(true); }, [onReady]);
  const rootRef = useRef(null);
  // The pane, once mounted: Display's dropdown keeps inside it, as a 3D view's keeps inside its viewer.
  const [rootElement, setRootElement] = useState(null);
  useEffect(() => { setRootElement(rootRef.current); }, []);
  const ready = load.shown && !load.busy && !load.updating && !load.alert;
  const idle = load.busy || !load.shown;

  // ---- tools ----------------------------------------------------------------
  const [ownToolMode, setOwnToolMode] = useState(() => (toolModes ? toolModes.defaultMode : ""));
  const toolMode = tool ? tool.mode : ownToolMode;
  const setToolMode = tool ? tool.set : setOwnToolMode;
  const selectTool = useCallback((mode) => setToolMode((current) => (toolModes ? toolModes.next(current, mode) : mode)), [toolModes, setToolMode]);
  const selectDefaultTool = useCallback(() => setToolMode(toolModes ? toolModes.defaultMode : ""), [toolModes, setToolMode]);
  const drawToolActive = toolMode === SHELL_TOOL.DRAW;
  const draw = usePlaneDrawing({ active: drawToolActive, plane, noun: words.noun });
  const { toolStack, changeToolStack } = useToolStackLayout(services);
  const stripTool = ({ id, label, icon, ...rest }) => ({ id, label, icon, active: toolMode === id, disabled: idle, onSelect: () => selectTool(id), ...rest });
  const DrawIcon = DRAWING_TOOLBAR_TOOLS.find((item) => item.id === draw.drawing.tool)?.Icon || Pencil;
  const tools = {
    /** A tool of the renderer's own: `{ id, label, icon }` plus anything the strip reads. */
    own: stripTool,
    // The button shows the drawing tool in hand; a second press puts it down (its mode toggles).
    draw: stripTool({ id: SHELL_TOOL.DRAW, label: "Draw", icon: <DrawIcon data-drawing-tool={draw.drawing.tool} className="size-3" strokeWidth={2} aria-hidden="true" /> }),
  };

  // ---- alerts ---------------------------------------------------------------
  // A failed action's card: its title says which action failed (a copy, a capture), its message why.
  const [actionError, setActionError] = useState(null);
  const failAction = useCallback((title, error) => setActionError({ title, message: error instanceof Error ? error.message : String(error) }), []);
  const clearActionError = useCallback((title) => setActionError((current) => (current?.title === title ? null : current)), []);
  // A failure, the picture's or an action's, owns the card; the renderer's report has it otherwise.
  const cardAlert = load.alert || (actionError ? { severity: "error", kind: "status", blocking: false, title: actionError.title, message: actionError.message } : null)
    || report?.alert || null;
  const showingReport = Boolean(report?.alert) && cardAlert === report.alert;
  const dismissal = useAlertDismissal(cardAlert, { hasContent: load.shown, scope: modelKey, onNavigationActionsChange: view.onNavigationActionsChange,
    startDismissed: showingReport && Boolean(report.startDismissed) });

  // ---- the clipboard and the prompt -------------------------------------------
  const copyText = useCallback(async (text) => {
    if (!text) return false;
    try {
      await host.clipboard.writeText(text);
      clearActionError(words.copyFailed);
      return true;
    } catch (error) { failAction(words.copyFailed, error); return false; }
  }, [host.clipboard, words.copyFailed, clearActionError, failAction]);
  // Draw's copy: the view with its ink.
  const copyDrawing = useCallback(async () => {
    if (!draw.drawing.hasContent) return false;
    try {
      await host.clipboard.writeImage(draw.capture());
      clearActionError(words.copyFailed);
      return true;
    } catch (error) { failAction(words.copyFailed, error); return false; }
  }, [draw, host.clipboard, words.copyFailed, clearActionError, failAction]);
  const copyAction = () => {
    if (drawToolActive && draw.drawing.hasContent) { void copyDrawing(); return true; }
    if (copySelection) { void copySelection(); return true; }
    return false;
  };
  const capture = captureView || plane.capture;
  const resourceRef = useRef(resource);
  resourceRef.current = resource;
  const snapshot = useCallback(() => {
    setActionError(null);
    // The host binds its destination during the gesture, BEFORE the PNG exists.
    const pixels = capture();
    void pixels.catch(() => {});
    void deliverPromptContext(host, createViewPromptContext({ resource: resourceRef.current, capture: pixels })).then((result) => {
      const message = promptDeliveryError(result);
      setActionError(message ? { title: words.captureFailed, message } : null);
    });
  }, [capture, host, words.captureFailed]);
  useCaptureRequest({ services, ready: ready && destination.available, capture: snapshot });

  // ---- shortcuts ------------------------------------------------------------
  const escapeRef = useRef(escape.handle);
  escapeRef.current = escape.handle;
  const escapeView = useCallback(() => escapeRef.current?.() || false, []);
  useViewerShortcuts({
    viewerElement: rootRef, escapeActive: Boolean(escape.active), onCopy: copyAction,
    onEscape(event) {
      // A popup opened in THIS view (Display, a mode menu) owns Escape first.
      if (hasOpenPopup(rootRef.current)) return;
      // Draw's surface spends its own Escape (its editor deselects, or drops the stroke in hand).
      if (drawToolActive && event.target instanceof Element && event.target.closest("[data-cad-drawing-overlay]")) return;
      escapeView();
    }
  });

  // ---- the live command surface ----------------------------------------------
  const runtimeRef = useRef(null);
  runtimeRef.current = {
    readState: () => ({
      resource: { ...resource }, revision: String(resource.revision || ""),
      loading: Boolean(load.busy || load.updating),
      selection: (references || []).map((reference) => ({ ...reference, resource: { ...reference.resource } })),
      camera: null, display: {}, renderMode: "inspect", ...(live.state?.() || {})
    }),
    setCamera() { throw new Error(words.noCamera); },
    resetCamera() { plane.fit(); },
    setDisplaySettings() { throw new Error(displayInView && words.displayInView ? words.displayInView : words.noDisplay); },
    setRenderMode() { throw new Error(words.noDisplay); },
    capture,
    thumbnail: plane.thumbnail,
    ...(live.commands || NO_COMMANDS)
  };
  // A picture has settled once it is read and drawn: a library card's picture waits for that.
  const whenSettled = useWhenSettled(() => ready);
  useLiveSurface({ binding: services.live, runtime: runtimeRef, commands: Object.keys(live.commands || NO_COMMANDS), declined: live.declined, ready: whenSettled });

  // While the picture loads, or once it has failed to, there is no chrome: no tools, no Quick Edit.
  const chromeHidden = !load.shown || load.busy;
  const compact = Boolean(view.appearance?.compact);
  const sketch = useMemo(() => (drawToolActive ? { ink: draw.drawing.hasContent, capture: draw.capture } : null),
    [drawToolActive, draw.drawing.hasContent, draw.capture]);
  return {
    toolMode, selectTool, selectDefaultTool, tools, idle, ready, copyText, dismissAlert: dismissal.dismiss,
    frame: {
      view, plane, modelKey, resource, load, rootRef, rootElement, chromeHidden, compact, toolStack, changeToolStack,
      references, copyAction, copyDrawing, copyShortcut: host.environment?.platform === "darwin" ? "⌘C" : "Ctrl+C",
      escape: escapeView, drawToolActive, draw, sketch, cardAlert, showingReport, dismissal
    }
  };
}
