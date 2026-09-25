import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Camera } from "lucide-react";
import { cn } from "@hardcore/ui/utils";
import { usePromptDestination, useViewerHost } from "../../host/context.js";
import ViewerAlertCard from "../kit/status/ViewerAlertCard.jsx";
import ViewerLoadingOverlay from "../kit/status/ViewerLoadingOverlay.js";
import { attachLiveBinding } from "../kit/shell/liveBinding.js";
import { createViewPromptContext, promptDeliveryError } from "../kit/shell/promptContext.js";
import { useWorkspaceDocument } from "../workspace/useWorkspaceDocument.js";
import { drawingLoadAlert, useDrawingPayload } from "./useDrawingPayload.js";
import { useDrawingView } from "./useDrawingView.js";
import { dxfViewStateRecord, readDxfViewState } from "./viewState.js";

/**
 * A `.dxf` is a straight render: the drawing, on a canvas, and nothing else.
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

function DxfSurface({ view, data }) {
  const host = useViewerHost();
  const destination = usePromptDestination();
  const workspace = useWorkspaceDocument({ view, data });
  const file = workspace.entry?.file || view.file.path;
  const payload = useDrawingPayload({ client: workspace.client, file, revision: workspace.resource.revision });
  const [actionError, setActionError] = useState(null);
  const { onReady, onNavigationActionsChange, onStateChange } = view;

  // ---- the view this file was left at ---------------------------------------
  const [restored] = useState(() => readDxfViewState(view.state));
  const storedRef = useRef(JSON.stringify(dxfViewStateRecord(restored, Boolean(restored))));
  const saveTimer = useRef(0);
  const stateChangeRef = useRef(onStateChange);
  stateChangeRef.current = onStateChange;
  // A view that is still the fit stores nothing — `null` is "fit me", and it is
  // what a drawing dropped back to the fit must write, not a stale transform.
  const rememberView = useCallback((transform) => {
    const record = dxfViewStateRecord(transform, Boolean(transform));
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
  const { canvasRef, capture, containerRef, dragging, fit } = drawingView;

  // ---- host chrome -----------------------------------------------------------
  useEffect(() => { onReady?.(true); }, [onReady]);

  const alert = useMemo(() => {
    if (workspace.catalogError) {
      return {
        severity: "error", kind: "status", title: "Couldn’t open the drawing",
        message: "The viewer couldn’t retrieve this file’s information.",
        recovery: "Try again. If this continues, check that the viewer is running.",
        details: String(workspace.catalogError), reload: true
      };
    }
    return drawingLoadAlert(workspace.modelKey || file, payload.error);
  }, [workspace.catalogError, workspace.modelKey, file, payload.error]);
  const empty = Boolean(payload.drawing) && !payload.drawing.bounds;
  const ready = Boolean(payload.drawing) && !payload.loading && !alert;

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

  // ---- the navbar ------------------------------------------------------------
  // One action, and it is not the camera's. Zooming a drawing is the pointer's job —
  // wheel or pinch about the pointer, drag to pan, double-click to fit — so there are
  // no zoom buttons to press, here or anywhere else in the viewer.
  const actionsRef = useRef({ snapshot });
  actionsRef.current = { snapshot };
  useEffect(() => {
    const actions = [
      { id: "snapshot", label: "Take snapshot", icon: Camera, disabled: !ready || !promptAvailable,
        onInvoke: () => actionsRef.current.snapshot() }
    ];
    onNavigationActionsChange?.(actions);
    return () => onNavigationActionsChange?.([]);
  }, [onNavigationActionsChange, ready, promptAvailable]);

  // ---- the live command surface ----------------------------------------------
  const runtimeRef = useRef(null);
  runtimeRef.current = {
    readState: () => ({
      resource: { ...workspace.resource }, revision: String(workspace.resource.revision || ""),
      loading: payload.loading, selection: [], camera: null, display: {}, renderMode: "inspect"
    }),
    setCamera() { throw new Error(NO_CAMERA); },
    resetCamera() { fit(); },
    setDisplaySettings() { throw new Error(NO_DISPLAY); },
    setRenderMode() { throw new Error(NO_DISPLAY); },
    capture
  };
  const binding = data.services.live;
  useEffect(() => {
    if (!binding) return undefined;
    return attachLiveBinding(binding, () => runtimeRef.current, { declined: DECLINED_LIVE_COMMANDS });
  }, [binding]);

  return (
    <div className="relative flex h-full min-h-0 flex-col overflow-hidden bg-background text-foreground"
      data-slot="cad-file-view" data-drawing-surface>
      <div ref={containerRef} className="relative min-h-0 flex-1" aria-busy={payload.loading ? "true" : "false"}>
        <canvas ref={canvasRef} aria-label={`Drawing: ${view.file.name}`} role="img"
          className={cn("absolute inset-0 block touch-none select-none", dragging ? "cursor-grabbing" : "cursor-grab")} />
        {empty ? (
          <p className="pointer-events-none absolute inset-0 flex items-center justify-center px-6 text-center text-sm text-muted-foreground"
            data-drawing-empty>
            This drawing has no geometry in its modelspace, so there is nothing to show.
          </p>
        ) : null}
        <ViewerLoadingOverlay loading={{ opening: payload.loading && !alert, progress: { label: "Reading drawing" } }}
          operationKey={file} />
        <ViewerAlertCard alert={alert || (actionError ? { severity: "error", kind: "status", blocking: false, title: "Couldn’t capture the drawing", message: actionError } : null)} hasContent={Boolean(payload.drawing)} onReload={view.reload} />
      </div>
    </div>
  );
}

export default function DxfRenderer(props) {
  const { data, ...view } = props;
  return <DxfSurface key={JSON.stringify([view.source.id, view.file.path])} view={view} data={data} />;
}
