import { useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { usePromptDestination, useViewerHost, ViewerElementContext } from "../../../host/context.js";
import { hasOpenPopup } from "../../../lib/popups.js";
import { useAnnotationSession } from "../../../annotation/session.js";
import { promptViews } from "../../../annotation/views.js";
import { useAlertDismissal } from "../status/ViewerAlertCard.jsx";
import { CAD_ANNOTATION_DEFAULTS } from "../tools/annotate/AnnotationOverlay.jsx";
import { useMeasureSession } from "../tools/measure/useMeasureSession.js";
import { normalizeToolStack } from "../tools/toolStackLayout.js";
import { pressToolKey } from "../tools/toolShortcuts.js";
import { attachLiveBinding } from "./liveBinding.js";
import { createViewPromptContext, promptDeliveryError } from "./promptContext.js";
import { useViewerHistory } from "./useViewerHistory.js";
import { useViewerShortcuts } from "./useViewerShortcuts.js";
import { useWhenSettled } from "./useWhenSettled.js";

/**
 * What every FLAT view does around its picture (a 2D drawing, a board: `FlatViewFrame.jsx`), so a
 * person moving between them meets one viewer. Two halves, in the order a renderer needs them:
 *
 * `useFlatTools` is the tools: Select, Pencil, Shapes and Measure, the one in hand never saved (a
 * file opens in Select), the drawing tools' session and Measure's over the viewer's one history.
 * Measurements are the person's alone: Measure's row lists them, and they never go to Quick Edit.
 *
 * `useFlatHandover` is what goes out of the view: Quick Edit's props (its references and chips, the
 * annotation, and the prompt's views and files: the views with ink, the one on screen and the
 * annotation file, as `host.promptFiles` writes them), the keys (Escape lets go, Delete deletes what
 * Select picked, ⌘Z walks the history, a tool's letter takes it up and F fits, the copy key copies
 * the annotated view while a drawing tool is up, else what `copySelection` copies), a host's capture
 * request, the live binding, and the alert card with its dismissal.
 */

/** A flat view's tools: the ids the strip and the tool modes share. */
export const FLAT_TOOL = Object.freeze({ SELECT: "select", PENCIL: "pencil", SHAPES: "shapes", MEASURE: "measure" });

/**
 * @param {{ toolModes: ReturnType<typeof import("../tools/toolModes.js").createToolModes>, file: string, revision: string,
 *   ready: boolean }} options  `ready`: the picture is in, so Measure can pick.
 */
export function useFlatTools({ toolModes, file, revision, ready }) {
  // The tool in hand is never saved: a file opens in Select.
  const [toolMode, setToolMode] = useState(toolModes.defaultMode);
  const modesRef = useRef(toolModes);
  modesRef.current = toolModes;
  const selectTool = useCallback(mode => setToolMode(current => modesRef.current.next(current, mode)), []);
  const drawingFamily = toolMode === FLAT_TOOL.PENCIL || toolMode === FLAT_TOOL.SHAPES ? toolMode : null;
  const annotating = drawingFamily !== null;
  const measuring = toolMode === FLAT_TOOL.MEASURE;
  const selecting = toolMode === FLAT_TOOL.SELECT;
  const history = useViewerHistory();
  const annotation = useAnnotationSession(drawingFamily, CAD_ANNOTATION_DEFAULTS, history);
  const measure = useMeasureSession({ fileKey: file, revision, picking: measuring && ready });
  // A measurement taken, deleted or cleared is a step of the view's one history, with the ink's.
  measure.history.current = history;
  // The strip as last drawn (`flatViewTools` writes it): what a tool's letter takes up.
  const toolKeys = useRef([]);
  return { toolMode, selectTool, annotating, measuring, selecting, history, annotation, measure, toolKeys };
}

/**
 * @param {object} options
 * @param {object} options.view  The renderer's props (`onReady`, `onNavigationActionsChange`).
 * @param {object} options.data  The prepared document (`services.live`).
 * @param {object} options.workspace  `useWorkspaceDocument`'s.
 * @param {string} options.file
 * @param {boolean} options.shown  A picture is on screen.
 * @param {boolean} options.ready  This revision's picture is painted: a capture waits out an update.
 * @param {object | null} options.alert  The load's alert.
 * @param {ReturnType<typeof useFlatTools>} options.tools
 * @param {ReturnType<typeof import("../tools/select/useSceneSelection.js").useSceneSelection>} options.selection
 * @param {readonly object[]} options.references  The selection, as prompt references.
 * @param {readonly object[]} options.chips  Quick Edit's chips for them.
 * @param {(reference: object) => string | object} options.nameReference
 * @param {() => Promise<Blob>} options.capture  The view on screen as a PNG.
 * @param {() => object | null} options.currentView  The view on screen as a prompt carries it.
 * @param {(items: readonly object[]) => object | null} options.annotationDocument  The ink as an annotation file says it.
 * @param {object} options.runtime  The live surface the binding reads (`readState`, `setCamera`, ...).
 * @param {{ commands: readonly string[], declined: Record<string, string> }} options.live
 * @param {(() => boolean) | null} [options.copySelection]  The copy key's, while no drawing tool is up.
 * @param {() => unknown} options.fit  Fits the picture to the pane: the F key's.
 * @param {string} options.captureFailed  The card's title when a capture or copy fails.
 */
export function useFlatHandover({ view, data, workspace, file, shown, ready, alert, tools, selection, references, chips, nameReference,
  capture, currentView, annotationDocument, runtime, live, copySelection = null, fit, captureFailed }) {
  const host = useViewerHost();
  const destination = usePromptDestination();
  const viewerElement = useContext(ViewerElementContext);
  const [actionError, setActionError] = useState(null);
  const { onReady } = view;
  const { annotation, measure, history, annotating, selecting, selectTool, toolKeys } = tools;
  // The live values the keys and the prompt read when they fire.
  const annotationRef = useRef(annotation);
  annotationRef.current = annotation;
  const measureRef = useRef(measure);
  measureRef.current = measure;
  const selectionRef = useRef(selection);
  selectionRef.current = selection;
  const currentViewRef = useRef(currentView);
  currentViewRef.current = currentView;
  const documentRef = useRef(annotationDocument);
  documentRef.current = annotationDocument;

  // ---- host chrome -----------------------------------------------------------
  useEffect(() => { onReady?.(true); }, [onReady]);

  // ---- snapshot to the prompt ------------------------------------------------
  const resourceRef = useRef(workspace.resource);
  resourceRef.current = workspace.resource;
  const promptAvailable = destination.available;
  const snapshot = useCallback(() => {
    setActionError(null);
    // The host binds its destination during the gesture, BEFORE the PNG exists.
    const pixels = capture();
    void pixels.catch(() => {});
    let pending;
    try { pending = host.promptContext.deliver(createViewPromptContext({ resource: resourceRef.current, capture: pixels })); }
    catch (error) { pending = Promise.reject(error); }
    Promise.resolve(pending)
      .catch((error) => ({ status: "failed", message: error instanceof Error ? error.message : String(error) }))
      .then((result) => setActionError(promptDeliveryError(result)));
  }, [capture, host.promptContext]);

  // A host's own capture request is the same act, acknowledged.
  const snapshotRef = useRef(snapshot);
  snapshotRef.current = snapshot;
  const captureKey = workspace.commands.captureRequest?.key ?? null;
  const appliedCapture = useRef(null);
  useEffect(() => {
    if (captureKey === null || appliedCapture.current === captureKey || !ready || !promptAvailable) return;
    appliedCapture.current = captureKey;
    workspace.acknowledgeCommand?.("captureRequest", captureKey);
    snapshotRef.current();
  }, [captureKey, ready, promptAvailable, workspace.acknowledgeCommand]);

  // ---- Quick Edit ------------------------------------------------------------
  // A note carries the views with annotation ink as JSON files — the window on screen as a plan-view
  // camera, which a snapshot job frames again, and the annotation.
  const promptFile = useCallback(() => (resourceRef.current?.kind === "workspace-file" ? resourceRef.current.path : null), []);
  const annotationNow = useCallback(() => documentRef.current(annotationRef.current.items), []);
  const viewNow = useCallback(() => currentViewRef.current(), []);
  const quickEditPrompt = useMemo(() => ({
    views: () => (host.promptFiles && promptFile() ? promptViews(viewNow(), annotationRef.current.views, annotationRef.current.items) : []),
    files: views => {
      const input = promptFile();
      if (!host.promptFiles || !input || !views.length) return null;
      return host.promptFiles.create({ name: input.split("/").pop(), input, views, annotation: annotationNow() });
    },
    read: path => host.promptFiles.read(path),
  }), [host.promptFiles, promptFile, viewNow, annotationNow]);
  const forgetAnnotation = annotation.forget;
  const quickEditAnnotation = useMemo(() => (annotating || annotation.hasAnnotation
    ? { present: annotation.hasAnnotation, clear: forgetAnnotation } : null), [annotating, annotation.hasAnnotation, forgetAnnotation]);
  const clearQuickEdit = () => { selection.clear(); measure.select([]); if (annotation.hasAnnotation) annotation.forget(); };
  // A drawing tool's copy: the picture with its ink, to the clipboard; otherwise the view's own (its selection).
  const copyAction = () => {
    if (annotating) {
      if (!shown) return false;
      void host.clipboard.writeImage(capture()).catch(error => setActionError(error instanceof Error ? error.message : String(error)));
      return true;
    }
    return copySelection ? copySelection() : false;
  };

  // ---- keys: Escape lets go, Delete deletes what Select picked, ⌘Z walks the history ----
  const letGo = () => {
    const session = annotationRef.current, now = measureRef.current;
    if (session.selected.length) { session.select([]); return true; }
    if (now.drafting) { now.cancelDraft(); return true; }
    if (now.selected.length) { now.select([]); return true; }
    if (selectionRef.current.active) { selectionRef.current.clear(); return true; }
    return false;
  };
  useViewerShortcuts({
    viewerElement,
    onCopy: () => copyAction(),
    onDelete: () => {
      if (annotating) return false;
      const session = annotationRef.current;
      const ink = session.selected.length > 0;
      if (ink) session.remove(session.selected);
      return Boolean(measureRef.current.removeSelected()) || ink;
    },
    onUndo: () => history.undo(),
    onRedo: () => history.redo(),
    // A tool's letter takes it up, F fits the picture (`toolShortcuts.js`), over the strip as drawn.
    onKey: event => shown && pressToolKey(event, { tools: toolKeys.current,
      selectDrawing: tool => annotationRef.current.selectTool(tool), fit }),
    escapeActive: Boolean(selection.active || measure.drafting || measure.selected.length || annotation.selected.length || !selecting),
    onEscape(event) {
      if (hasOpenPopup(viewerElement?.current)) return;
      // The drawing tools' layer spends its own Escape (its editor, the stroke in hand).
      if (annotating && event.target instanceof Element && event.target.closest("[data-cad-annotation-overlay]")) return;
      if (letGo()) return;
      // Nothing to let go of: the tool in hand goes down, back to Select.
      if (!selecting) selectTool(FLAT_TOOL.SELECT);
    }
  });

  // ---- the live command surface ----------------------------------------------
  const runtimeRef = useRef(null);
  runtimeRef.current = runtime;
  const liveRef = useRef(live);
  liveRef.current = live;
  // A picture has settled once it is read and painted: a library card's picture waits for that.
  const whenSettled = useWhenSettled(() => ready);
  // The card the viewport shows, and its dismissal: put away, its icon in the navbar brings it back.
  const cardAlert = alert || (actionError ? { severity: "error", kind: "status", blocking: false, title: captureFailed, message: actionError } : null);
  const alertDismissal = useAlertDismissal(cardAlert, { hasContent: shown, scope: file, onNavigationActionsChange: view.onNavigationActionsChange });
  const binding = data.services.live;
  useEffect(() => {
    if (!binding) return undefined;
    const { commands, declined } = liveRef.current;
    return attachLiveBinding(binding, () => runtimeRef.current, { commands, declined, ready: whenSettled });
  }, [binding, whenSettled]);

  // ---- the file sidebar's layout: the person's, across files ------------------
  const toolStack = useMemo(() => normalizeToolStack(workspace.services.preferences?.toolStack), [workspace.services.preferences?.toolStack]);
  const toolStackRef = useRef(toolStack);
  toolStackRef.current = toolStack;
  const onPreferenceChange = workspace.services.onPreferenceChange;
  const changeToolStack = useCallback(patch => {
    const next = normalizeToolStack({ ...toolStackRef.current, ...(typeof patch === "function" ? patch(toolStackRef.current) : patch) });
    toolStackRef.current = next;
    onPreferenceChange?.({ toolStack: next });
  }, [onPreferenceChange]);

  const quickEdit = {
    resource: workspace.resource, references, chips, nameReference, annotation: quickEditAnnotation,
    prompt: quickEditPrompt, onCopy: copyAction, onEscape: letGo, onClear: clearQuickEdit, disabled: !shown
  };
  return { quickEdit, cardAlert, alertDismissal, toolStack, changeToolStack, reportActionError: setActionError };
}
