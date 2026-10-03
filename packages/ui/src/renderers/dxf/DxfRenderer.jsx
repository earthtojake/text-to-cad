import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { cn } from "@text-to-cad/ui/utils";
import { usePromptDestination, useViewerHost } from "../../host/context.js";
import ViewerAlertCard, { useAlertDismissal } from "../kit/status/ViewerAlertCard.jsx";
import ViewerLoadingOverlay from "../kit/status/ViewerLoadingOverlay.js";
import { ViewUpdateStatus } from "../kit/status/ViewUpdateStatus.jsx";
import { VIEWPORT_INSET_PX, VIEWPORT_TOP_BAR_PX } from "../kit/shell/viewportLayout.js";
import { ViewportTopRight } from "../kit/shell/ViewportTopRight.jsx";
import { attachLiveBinding } from "../kit/shell/liveBinding.js";
import { useWhenSettled } from "../kit/shell/useWhenSettled.js";
import { createViewPromptContext, promptDeliveryError } from "../kit/shell/promptContext.js";
import { useWorkspaceDocument } from "../workspace/useWorkspaceDocument.js";
import { drawingLoadAlert, useDrawingPayload } from "./useDrawingPayload.js";
import { useDrawingView } from "./useDrawingView.js";
import { readFileView, writeFileView } from "../kit/shell/fileView.js";
import { planeTransformCamera, readPlaneTransform } from "../kit/plane/planeTransform.js";

/**
 * A `.dxf` is a straight render: the drawing, on a canvas, and nothing else but Quick Edit,
 * the note to the agent about the file that every view offers.
 *
 * No 3D, no fold preview, no thickness or material, no tools, no toolbar and no
 * panel — not a file panel, not Display settings, not a layer list. A DXF is a
 * finished 2D document; the questions those controls answered were about a
 * sheet-metal part the viewer was inventing from it.
 *
 * The picture comes from the BACKEND (`GET /__cad/drawing`), which runs ezdxf
 * over the file and returns flat primitives. This renderer never parses DXF.
 */

/** Host commands a 2D drawing cannot answer, each with the sentence its caller reads. */
const DECLINED_LIVE_COMMANDS = Object.freeze({
  select: "A DXF is a 2D drawing without CAD references: it has no parts, faces or edges to select. "
    + "Selection needs a model with topology, such as a STEP file.",
  clearSelection: "A DXF is a 2D drawing without CAD references, so it never has a selection to clear."
});
const NO_CAMERA = "A DXF is a flat drawing shown head on: it has no camera to pose. "
  + "Zoom and pan it in the view, or call resetCamera to fit the whole drawing again.";
const NO_DISPLAY = "A DXF has no Display settings: a drawing is painted in the pens it declares, on the "
  + "theme's background, with no surfaces, lighting or render mode to configure.";
const SAVE_DELAY_MS = 180;
const DRAWING_UPDATE_STATUS = Object.freeze({ pending: true, label: "Updating drawing…" });

function DxfSurface({ view, data }) {
  const host = useViewerHost();
  const destination = usePromptDestination();
  const workspace = useWorkspaceDocument({ view, data });
  const file = workspace.entry?.file || view.file.path;
  const payload = useDrawingPayload({ client: workspace.client, file, revision: workspace.resource.revision });
  const [actionError, setActionError] = useState(null);
  const { onReady, onStateChange } = view;

  // ---- the view this file was left at ---------------------------------------
  // The file's view (`kit/shell/fileView.js`) with the drawing's transform as its camera and
  // nothing else: a drawing has no Display settings and no slices of its own.
  const [restored] = useState(() => readPlaneTransform(readFileView(view.state).camera));
  const storedRef = useRef(JSON.stringify(writeFileView({ camera: planeTransformCamera(restored, Boolean(restored)) })));
  const saveTimer = useRef(0);
  const stateChangeRef = useRef(onStateChange);
  stateChangeRef.current = onStateChange;
  // A view that is still the fit stores nothing — `null` is "fit me", and it is
  // what a drawing dropped back to the fit must write, not a stale transform.
  const rememberView = useCallback((transform) => {
    const record = writeFileView({ camera: planeTransformCamera(transform, Boolean(transform)) });
    const serialized = JSON.stringify(record);
    if (serialized === storedRef.current) return;
    storedRef.current = serialized;
    window.clearTimeout(saveTimer.current);
    saveTimer.current = window.setTimeout(() => stateChangeRef.current?.(record), SAVE_DELAY_MS);
  }, []);
  useEffect(() => () => window.clearTimeout(saveTimer.current), []);

  const drawingView = useDrawingView({
    drawing: payload.drawing, restored, colorScheme: view.appearance?.colorScheme === "dark" ? "dark" : "light",
    onViewMoved: rememberView
  });
  const { canvasRef, capture, containerRef, dragging, fit, thumbnail } = drawingView;

  // ---- host chrome -----------------------------------------------------------
  useEffect(() => { onReady?.(true); }, [onReady]);

  // With a drawing on screen, a failure to read the file again leaves that drawing to use.
  const shown = Boolean(payload.drawing);
  const alert = useMemo(() => {
    if (workspace.catalogError && !shown) {
      return {
        severity: "error", kind: "status", title: "Couldn’t open the drawing",
        message: "The viewer couldn’t retrieve this file’s information.",
        recovery: "Try again. If this continues, check that the viewer is running.",
        details: String(workspace.catalogError), reload: true
      };
    }
    const failed = drawingLoadAlert(workspace.modelKey || file, payload.error);
    return failed && shown ? { ...failed, blocking: false, message: `${failed.message} The existing drawing remains visible.` } : failed;
  }, [workspace.catalogError, workspace.modelKey, file, payload.error, shown]);
  const empty = shown && !payload.drawing.bounds;
  // Settled is this revision's drawing painted: a capture waits out an update.
  const ready = shown && !payload.loading && !payload.updating && !alert;

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

  // A host asking to select a reference is answered rather than dropped.
  const selectKey = workspace.commands.selectReference?.key ?? null;
  const declinedSelect = useRef(null);
  useEffect(() => {
    if (selectKey === null || declinedSelect.current === selectKey) return;
    declinedSelect.current = selectKey;
    workspace.acknowledgeCommand?.("selectReference", selectKey);
  }, [selectKey, workspace.acknowledgeCommand]);

  // ---- the live command surface ----------------------------------------------
  const runtimeRef = useRef(null);
  runtimeRef.current = {
    readState: () => ({
      resource: { ...workspace.resource }, revision: String(workspace.resource.revision || ""),
      loading: payload.loading || payload.updating, selection: [], camera: null, display: {}, renderMode: "inspect"
    }),
    setCamera() { throw new Error(NO_CAMERA); },
    resetCamera() { fit(); },
    setDisplaySettings() { throw new Error(NO_DISPLAY); },
    setRenderMode() { throw new Error(NO_DISPLAY); },
    capture,
    thumbnail
  };
  // A drawing has settled once it is read and painted: a library card's picture waits for that.
  const whenSettled = useWhenSettled(() => ready);
  // The card the viewport shows, and its dismissal: put away, its icon in the navbar brings it back.
  const cardAlert = alert || (actionError ? { severity: "error", kind: "status", blocking: false, title: "Couldn’t capture the drawing", message: actionError } : null);
  const alertDismissal = useAlertDismissal(cardAlert, { hasContent: shown, scope: file, onNavigationActionsChange: view.onNavigationActionsChange });
  const binding = data.services.live;
  useEffect(() => {
    if (!binding) return undefined;
    return attachLiveBinding(binding, () => runtimeRef.current, { declined: DECLINED_LIVE_COMMANDS, ready: whenSettled });
  }, [binding, whenSettled]);

  return (
    <div className="relative flex h-full min-h-0 flex-col overflow-hidden bg-background text-foreground"
      data-slot="cad-file-view" data-drawing-surface>
      <div ref={containerRef} className="relative min-h-0 flex-1" aria-busy={payload.loading || payload.updating ? "true" : "false"}>
        <canvas ref={canvasRef} aria-label={`Drawing: ${view.file.name}`} role="img"
          className={cn("absolute inset-0 block touch-none select-none", dragging ? "cursor-grabbing" : "cursor-grab")} />
        {empty ? (
          <p className="pointer-events-none absolute inset-0 flex items-center justify-center px-6 text-center text-sm text-muted-foreground"
            data-drawing-empty>
            This drawing has no geometry in its modelspace, so there is nothing to show.
          </p>
        ) : null}
        {payload.updating && !alert ? <div className="pointer-events-none absolute left-1/2 z-30 flex max-w-[calc(100%-1rem)] -translate-x-1/2 items-center"
          style={{ top: VIEWPORT_INSET_PX, height: VIEWPORT_TOP_BAR_PX }} data-viewport-status="">
          <ViewUpdateStatus status={DRAWING_UPDATE_STATUS} className="rounded-md bg-background/95 px-1 py-0.5 shadow-sm" />
        </div> : null}
        {/* The host's notice, top-right, once the drawing is on screen: a rebuild, or a failed update the
            drawing survives, keeps it there, as the 3D views do. */}
        <ViewportTopRight notice={shown && !payload.loading ? view.notice : null} />
        <ViewerLoadingOverlay loading={{ opening: payload.loading && !alert, progress: { label: "Reading drawing" } }}
          operationKey={file} />
        <ViewerAlertCard alert={cardAlert} hasContent={shown} dismissed={alertDismissal.dismissed} onDismiss={alertDismissal.dismiss} onReload={view.reload} file={file} />
      </div>
    </div>
  );
}

export default function DxfRenderer(props) {
  const { data, ...view } = props;
  return <DxfSurface key={JSON.stringify([view.source.id, view.file.path])} view={view} data={data} />;
}
