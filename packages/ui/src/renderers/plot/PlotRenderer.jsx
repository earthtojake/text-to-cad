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
import { readFileView, writeFileView } from "../kit/shell/fileView.js";
import { planeTransformCamera, readPlaneTransform } from "../kit/plane/planeTransform.js";
import { useWorkspaceDocument } from "../workspace/useWorkspaceDocument.js";
import { plotLoadAlert, usePlotPayload } from "./usePlotPayload.js";
import { usePlotView } from "./usePlotView.js";
import { plotKindForPath, plotWords } from "./plotWords.js";

/**
 * A KiCad board or schematic is a straight render: the picture KiCad draws of it, on a canvas,
 * and nothing else.
 *
 * No 3D (a board model exports its STEP and GLB as files of their own), no tools, no toolbar,
 * no panel — not Display settings, not a layer list. The picture is KiCad's own plot, in KiCad's
 * colours: a board with all its layers stacked back to front on KiCad's board background, its
 * unrouted connections as a ratsnest; a schematic's sheets one under another, root first.
 *
 * The picture comes from the BACKEND (`GET /__cad/plot`), which runs `kicad-cli` over the file
 * and returns its SVG plot. This renderer never parses KiCad's files. What a plot is (`kind`)
 * changes the words it uses and nothing it draws.
 */

const SAVE_DELAY_MS = 180;

function PlotSurface({ view, data }) {
  const host = useViewerHost();
  const destination = usePromptDestination();
  const workspace = useWorkspaceDocument({ view, data });
  const file = workspace.entry?.file || view.file.path;
  const payload = usePlotPayload({ client: workspace.client, file, revision: workspace.resource.revision });
  const words = plotWords(payload.plot?.layout.kind || plotKindForPath(view.file.path));
  const [actionError, setActionError] = useState(null);
  const { onReady, onStateChange } = view;

  // ---- the view this file was left at ---------------------------------------
  // The file's view (`kit/shell/fileView.js`) with the plot's transform as its camera and
  // nothing else: a plot has no Display settings and no slices of its own.
  const [restored] = useState(() => readPlaneTransform(readFileView(view.state).camera));
  const storedRef = useRef(JSON.stringify(writeFileView({ camera: planeTransformCamera(restored, Boolean(restored)) })));
  const saveTimer = useRef(0);
  const stateChangeRef = useRef(onStateChange);
  stateChangeRef.current = onStateChange;
  // A view that is still the fit stores nothing — `null` is "fit me", and it is what a plot
  // dropped back to the fit must write, not a stale transform.
  const rememberView = useCallback((transform) => {
    const record = writeFileView({ camera: planeTransformCamera(transform, Boolean(transform)) });
    const serialized = JSON.stringify(record);
    if (serialized === storedRef.current) return;
    storedRef.current = serialized;
    window.clearTimeout(saveTimer.current);
    saveTimer.current = window.setTimeout(() => stateChangeRef.current?.(record), SAVE_DELAY_MS);
  }, []);
  useEffect(() => () => window.clearTimeout(saveTimer.current), []);

  const plotView = usePlotView({
    plot: payload.plot, restored, colorScheme: view.appearance?.colorScheme === "dark" ? "dark" : "light",
    onViewMoved: rememberView, noun: words.noun
  });
  const { canvasRef, capture, containerRef, dragging, fit, thumbnail } = plotView;

  // ---- host chrome -----------------------------------------------------------
  useEffect(() => { onReady?.(true); }, [onReady]);

  // With a plot on screen, a failure to read the file again leaves that plot to use.
  const shown = Boolean(payload.plot);
  const alert = useMemo(() => {
    if (workspace.catalogError && !shown) {
      return {
        severity: "error", kind: "status", title: words.openFailed,
        message: "The viewer couldn’t retrieve this file’s information.",
        recovery: "Try again. If this continues, check that the viewer is running.",
        details: String(workspace.catalogError), reload: true
      };
    }
    const failed = plotLoadAlert(workspace.modelKey || file, payload.error);
    return failed && shown ? { ...failed, blocking: false, message: `${failed.message} ${words.remains}` } : failed;
  }, [workspace.catalogError, workspace.modelKey, file, payload.error, shown, words]);
  // Settled is this revision's plot read and decoded: a capture waits out an update.
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
    setCamera() { throw new Error(words.noCamera); },
    resetCamera() { fit(); },
    setDisplaySettings() { throw new Error(words.noDisplay); },
    setRenderMode() { throw new Error(words.noDisplay); },
    capture,
    thumbnail
  };
  // A plot has settled once it is read and decoded: a library card's picture waits for that.
  const whenSettled = useWhenSettled(() => ready);
  // The card the viewport shows, and its dismissal: put away, its icon in the navbar brings it back.
  const cardAlert = alert || (actionError ? { severity: "error", kind: "status", blocking: false, title: words.captureFailed, message: actionError } : null);
  const alertDismissal = useAlertDismissal(cardAlert, { hasContent: shown, scope: file, onNavigationActionsChange: view.onNavigationActionsChange });
  const binding = data.services.live;
  const declined = words.declined;
  useEffect(() => {
    if (!binding) return undefined;
    return attachLiveBinding(binding, () => runtimeRef.current, { declined, ready: whenSettled });
  }, [binding, whenSettled, declined]);

  return (
    <div className="relative flex h-full min-h-0 flex-col overflow-hidden bg-background text-foreground"
      data-slot="cad-file-view" data-plot-surface>
      <div ref={containerRef} className="relative min-h-0 flex-1" aria-busy={payload.loading || payload.updating ? "true" : "false"}>
        <canvas ref={canvasRef} aria-label={`${words.label}: ${view.file.name}`} role="img"
          className={cn("absolute inset-0 block touch-none select-none", dragging ? "cursor-grabbing" : "cursor-grab")} />
        {payload.updating && !alert ? <div className="pointer-events-none absolute left-1/2 z-30 flex max-w-[calc(100%-1rem)] -translate-x-1/2 items-center"
          style={{ top: VIEWPORT_INSET_PX, height: VIEWPORT_TOP_BAR_PX }} data-viewport-status="">
          <ViewUpdateStatus status={words.updateStatus} className="rounded-md bg-background/95 px-1 py-0.5 shadow-sm" />
        </div> : null}
        {/* The host's notice, top-right, once the plot is on screen: a rebuild, or a failed update the
            plot survives, keeps it there, as the 3D views do. */}
        <ViewportTopRight notice={shown && !payload.loading ? view.notice : null} />
        <ViewerLoadingOverlay loading={{ opening: payload.loading && !alert, progress: { label: words.reading } }}
          operationKey={file} />
        <ViewerAlertCard alert={cardAlert} hasContent={shown} dismissed={alertDismissal.dismissed} onDismiss={alertDismissal.dismiss} onReload={view.reload} file={file} />
      </div>
    </div>
  );
}

export default function PlotRenderer(props) {
  const { data, ...view } = props;
  return <PlotSurface key={JSON.stringify([view.source.id, view.file.path])} view={view} data={data} />;
}
