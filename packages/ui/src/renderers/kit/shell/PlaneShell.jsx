import { useState } from "react";
import { createPortal } from "react-dom";
import { cn } from "@text-to-cad/ui/utils";
import { useViewerMobile } from "../../../file-viewer/responsive.js";
import ViewerAlertCard from "../status/ViewerAlertCard.jsx";
import ViewerLoadingOverlay from "../status/ViewerLoadingOverlay.js";
import { ViewUpdateStatus } from "../status/ViewUpdateStatus.jsx";
import DrawingOverlay from "../tools/draw/DrawingOverlay.jsx";
import DrawingPanel from "../tools/draw/DrawingPanel.jsx";
import QuickEdit from "../tools/quick-edit/QuickEdit.jsx";
import DisplayPopover from "./DisplayPopover.jsx";
import ToolColumn from "./ToolColumn.jsx";
import { ViewportTopRight } from "./ViewportTopRight.jsx";
import { VIEWPORT_INSET_PX, VIEWPORT_TOP_BAR_PX } from "./viewportLayout.js";

/**
 * The frame a view drawn as a flat picture draws itself in (`usePlaneShell.js`): the canvas filling
 * the pane, the tool strip at its top-left with the tool stack under it, Quick Edit at the top-right
 * under the host's notice, the picture's own Display settings (when it has any) at the navbar's right
 * end where a 3D view's sit, the update status at the top centre, the loading overlay and the alert
 * card. It is `RendererShell`'s structure without a scene: no cube, no preview, no Preview button.
 * While the picture loads, or once it has failed to, it draws none of its controls; in a compact host,
 * the picture alone.
 *
 * @param {{ shell: ReturnType<typeof import("./usePlaneShell.js").usePlaneShell>, label: string,
 *   surface: string, tools?: import("../tools/FloatingToolBar.js").ViewportTool[], toolPanels?: import("react").ReactNode,
 *   display?: import("react").ReactNode, reportBody?: import("react").ReactNode, onClearReferences?: (() => void) | null,
 *   overlay?: import("react").ReactNode, interactive?: boolean, style?: object }} props
 *   `label`: the canvas's name. `surface`: the data attribute the view's root carries (`data-<surface>`),
 *   which hosts and tests key on. `tools`: left to right, from `shell.tools`; an empty list draws no strip
 *   and no stack. `display`: Display's dropdown content, or null for a picture with none. `reportBody`: the
 *   card's body while it shows the renderer's report. `overlay`: the renderer's own layer over the canvas. `interactive`: the picture's parts can be pointed
 *   at, so its idle cursor is the pointer's, not a hand. `style`: the pane's, such as the chrome's alpha.
 */
export default function PlaneShell({ shell, label, surface, tools = [], toolPanels = null, display = null, reportBody = null,
  onClearReferences = null, overlay = null, interactive = false, style = undefined }) {
  const frame = shell.frame;
  const { view, plane, load, draw } = frame;
  const mobile = useViewerMobile();
  const [displayOpen, setDisplayOpen] = useState(false);
  const toolsShown = tools.length > 0 && !frame.chromeHidden && !frame.compact;
  // Quick Edit is the person's to turn off (in the app menu): off, it is not there at all.
  const quickEdit = !frame.compact && frame.references && view.features?.quickEdit !== false;
  const clearQuickEdit = () => { onClearReferences?.(); if (draw.drawing.hasContent) draw.drawing.clear(); };
  return (
    <div ref={frame.rootRef} className="relative flex h-full min-h-0 flex-col overflow-hidden bg-background text-foreground"
      data-slot="cad-file-view" {...{ [`data-${surface}`]: "" }} tabIndex={-1}>
      <div ref={plane.containerRef} className="@container/cad-viewport relative min-h-0 flex-1" aria-busy={load.busy || load.updating ? "true" : "false"}
        data-cad-scene-backdrop="" style={style}>
        <canvas ref={plane.canvasRef} aria-label={label} role="img"
          className={cn("absolute inset-0 block touch-none select-none", plane.dragging ? "cursor-grabbing" : interactive ? "cursor-default" : "cursor-grab")} />
        {overlay}
        {toolsShown && frame.drawToolActive ? <DrawingOverlay {...draw.overlay} /> : null}
        {/* Display at the navbar's right end, where a 3D view's is (its `navbarSlot`), after the alert's icon. No Preview. */}
        {toolsShown && display && view.navbarSlot ? createPortal(<DisplayPopover open={displayOpen} onOpenChange={setDisplayOpen} boundary={frame.rootElement}>
          {display}
        </DisplayPopover>, view.navbarSlot) : null}
        {toolsShown ? <ToolColumn tools={tools} layout={frame.toolStack} onLayoutChange={frame.changeToolStack} mobile={mobile}>
          {/* Draw's controls lead the stack while it is up. */}
          {frame.drawToolActive ? <DrawingPanel drawing={draw.drawing} onCopy={frame.copyDrawing} copyShortcut={mobile ? "" : frame.copyShortcut} /> : null}
          {toolPanels}
        </ToolColumn> : null}
        {load.updating && !load.alert ? <div className="pointer-events-none absolute left-1/2 z-30 flex max-w-[calc(100%-1rem)] -translate-x-1/2 items-center"
          style={{ top: VIEWPORT_INSET_PX, height: VIEWPORT_TOP_BAR_PX }} data-viewport-status="">
          <ViewUpdateStatus status={load.updateStatus} className="rounded-md bg-background/95 px-1 py-0.5 shadow-sm" />
        </div> : null}
        {/* The host's notice, top-right, once the picture is on screen: a rebuild, or a failed update the
            picture survives, keeps it there, as the 3D views do. Quick Edit under it. */}
        <ViewportTopRight notice={load.shown && !load.busy ? view.notice : null} belowStrip={toolsShown}>
          {quickEdit ? <QuickEdit key={frame.modelKey} className="self-stretch" hidden={frame.chromeHidden}
            resource={frame.resource} references={frame.references} sketch={frame.sketch}
            onCopy={frame.copyAction} onEscape={frame.escape} onClear={clearQuickEdit} disabled={!shell.ready} /> : null}
        </ViewportTopRight>
        <ViewerLoadingOverlay loading={{ opening: load.busy && !load.alert, progress: { label: load.reading } }} operationKey={frame.modelKey} />
        <ViewerAlertCard alert={frame.cardAlert} hasContent={load.shown} dismissed={frame.dismissal.dismissed} onDismiss={frame.dismissal.dismiss}
          onReload={view.reload} file={frame.modelKey} body={frame.showingReport ? reportBody : null} />
      </div>
    </div>
  );
}
