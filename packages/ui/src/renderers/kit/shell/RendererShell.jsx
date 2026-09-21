import { cn } from "@hardcore/ui/utils";
import FileSheet, { FileSheetPortalContext, HostPanelSlotContext } from "../inspector/FileSheet.js";
import FileSheetTabbedSurface from "../inspector/FileSheetTabbedSurface.js";
import BlockingViewerAlert, { blockingViewerAlert } from "../status/BlockingViewerAlert.jsx";
import StatusToast from "../status/StatusToast.js";
import { ViewUpdateStatus } from "../status/ViewUpdateStatus.jsx";
import ViewerAlertDialog from "../status/ViewerAlertDialog.js";
import ViewerLoadingOverlay from "../status/ViewerLoadingOverlay.js";
import FloatingToolBar from "../tools/FloatingToolBar.js";
import FullscreenToolbar from "../tools/fullscreen/FullscreenToolbar.jsx";
import { ViewportAnimationBar } from "../tools/playbar/ViewportAnimationBar.js";
import ShellViewport from "./ShellViewport.jsx";
import ViewportBottomAction, { drawingCaptureAction } from "./ViewportBottomAction.jsx";
import ViewportContextMenu from "./ViewportContextMenu.jsx";

const TOOLBAR_POSITION = Object.freeze({ top: "14px", right: "14px" });
// The host's panel column sizes the Inspector; this is only the sheet's nominal width.
const INSPECTOR_WIDTH = 365;

/**
 * The frame every file-family renderer draws itself in: the viewport box with
 * the tool strip at its corner, the active tool's bottom action, the loading,
 * update and alert overlays, fullscreen's controls, and the Inspector portaled
 * into the host's panel column. The same structure, classes and data attributes
 * for every renderer: hosts, stylesheets and tests key on them.
 *
 * @param {{ shell: ReturnType<typeof import("./useRendererShell.js").useRendererShell>,
 *   tools: import("../tools/FloatingToolBar.js").ViewportTool[],
 *   inspector: { title: string, tabs: object[] },
 *   bottomAction?: { label: string, shortLabel?: string, title?: string, disabled?: boolean,
 *     onInvoke?(): void, render?: (props: object) => import("react").ReactNode, children?: import("react").ReactNode } | null,
 *   contextMenuItems?: ((press: { clientX: number, clientY: number, shiftKey: boolean }) => object[] | null) | null,
 *   sceneRevision?: number, className?: string,
 *   viewportOverlay?: import("react").ReactNode | ((viewport: { runtimeRef: object, hostRef: object, viewerReadyTick: number }) => import("react").ReactNode) }} props
 *   `tools`: left to right, from `shell.tools`; an EMPTY list draws no strip at all,
 *   which is what a file whose viewport only orbits, pans and zooms hands over.
 *   `inspector.tabs`: tab descriptors
 *   (`{ id, title, content }`), usually ending with `shell.displayTab`. `bottomAction`
 *   replaces Draw's (copy the view with its ink) while the renderer's own tool is active.
 *   `contextMenuItems`: what THIS renderer offers on a secondary tap over the canvas; the
 *   gesture, the anchor and the dismissal are the shell's (`ViewportContextMenu.jsx`), and a
 *   renderer that passes none has no viewport menu at all.
 *   `viewportOverlay`: the renderer's own layer over the canvas; as a function it is given
 *   the viewport (its live runtime, the element its pointer events arrive on, and a tick
 *   that changes when the runtime is replaced), which is what a handle overlay or a
 *   pointer pick (`kit/tools/select/usePointerPick.js`) needs.
 */
export default function RendererShell({ shell, tools, inspector, bottomAction = null, contextMenuItems = null,
  sceneRevision = 0, viewportOverlay = null, className = "" }) {
  const frame = shell.frame;
  const { view, resolvedScene, previewMode, viewerLoading, scene } = frame;
  const hasContent = Boolean(scene) && !viewerLoading;
  const blockingAlert = blockingViewerAlert(frame.viewerAlert, hasContent);
  const action = bottomAction || (frame.drawToolActive
    ? drawingCaptureAction({ composer: frame.composer, disabled: viewerLoading || !hasContent, onInvoke: frame.capture })
    : null);
  // The renderer's overlay and the shell's own layers share one viewport context.
  const overlay = viewport => <>
    {previewMode || !contextMenuItems ? null : <ViewportContextMenu viewport={viewport} items={contextMenuItems} />}
    {typeof viewportOverlay === "function" ? viewportOverlay(viewport) : viewportOverlay}
  </>;
  return (
    <HostPanelSlotContext.Provider value={view.panelSlot}>
    <FileSheetPortalContext.Provider value={frame.hostElement}>
    <div
      className={cn("relative flex h-full min-h-0 flex-col overflow-hidden bg-background text-foreground", className)}
      data-slot="cad-file-view"
      data-cad-surface
      tabIndex={-1}
      onPointerDownCapture={event => {
        if (event.target instanceof Element && event.target.closest("canvas")) event.currentTarget.focus({ preventScroll: true });
      }}
      ref={frame.hostRef}
    >
      <div className="relative z-10 flex h-full min-w-0 flex-col overflow-hidden bg-transparent">
        <div className="relative min-h-0 flex-1 overflow-hidden">
          <div className="flex h-full min-w-0">
            {/* The render pane's box: the column left of the panel column. The canvas fills
                exactly this area, so a camera fit centres in what is visible and a sheet
                opening or closing reaches the scene as a plain resize. Its background is the
                scene's edge colour: the canvas is resized on the next frame, and one frame of
                the chrome's background above a dark stage is a visible band. */}
            <div
              className="@container/cad-viewport pointer-events-none relative min-w-0 flex-1 overflow-hidden"
              data-cad-scene-backdrop={frame.sceneBackdrop}
              style={{ backgroundColor: frame.sceneBackdrop }}
            >
              <div className="pointer-events-auto absolute inset-0 z-0">
                <div className="absolute inset-0">
                  <ShellViewport
                    ref={frame.viewerRef}
                    scene={scene}
                    sceneRevision={sceneRevision}
                    modelKey={frame.modelKey}
                    presentationKey={frame.presentationKey}
                    sceneScaleMode={frame.sceneScaleMode}
                    perspective={frame.viewerPerspective}
                    perspectiveRef={frame.activePerspectiveRef}
                    projection={resolvedScene.camera.projection}
                    focalLength={resolvedScene.camera.focalLength}
                    themeSettings={resolvedScene.theme}
                    displaySettings={resolvedScene.display}
                    appearance={resolvedScene.appearance}
                    receiveShadows={resolvedScene.view.lighting.enabled}
                    renderMode={resolvedScene.render.enabled}
                    renderConfiguration={resolvedScene.render.configuration}
                    quality={resolvedScene.quality}
                    previewMode={previewMode}
                    previewOrbitSpeed={frame.previewOrbitSpeed}
                    isLoading={viewerLoading}
                    viewUpdate={frame.viewUpdate}
                    loadingPresentation={frame.loading}
                    drawingEnabled={frame.drawToolActive}
                    drawing={frame.drawing}
                    onPerspectiveChange={frame.handlePerspectiveChange}
                    onCameraZoomPercentChange={frame.setZoomPercent}
                    onPresentationChange={frame.handlePresentationChange}
                    onViewerAlertChange={frame.setRuntimeAlert}
                    onCameraSettled={frame.onCameraSettled}
                  >{overlay}</ShellViewport>
                  {!previewMode ? <BlockingViewerAlert alert={blockingAlert} onReload={view.reload} /> : null}
                  {!previewMode && action ? <ViewportBottomAction composer={frame.composer} {...action} /> : null}
                </div>
              </div>

              {previewMode && <FullscreenToolbar key={frame.modelKey} surface={frame.hostElement}
                orbitSpeed={frame.previewOrbitSpeed} onOrbitSpeedChange={frame.setPreviewOrbitSpeed}
                animation={frame.animation}
                disabled={viewerLoading || !scene}
                onExit={view.onExitFullscreen}/>}

              {/* Routines, so the playbar — whatever tool is in hand, and with the file at rest
                  until somebody presses play. Its appearance alone changes nothing on screen. */}
              {!previewMode && frame.animationAvailable && (
                <ViewportAnimationBar key={frame.modelKey} runtime={frame.animation} avoidViewControl
                  className="pointer-events-auto"
                  disabled={viewerLoading || !scene}/>
              )}

              {/* A renderer with no tools has no strip: the viewport is the camera's alone. */}
              {previewMode || tools.length === 0 ? null : <FloatingToolBar tools={tools} position={TOOLBAR_POSITION} />}

              <ViewUpdateStatus status={frame.viewUpdate.status} onRetry={frame.viewUpdate.retry} className="absolute bottom-3 left-3 z-30" />
              <ViewerLoadingOverlay
                loading={frame.presentationState?.file === frame.modelKey && frame.presentationState?.covering ? null : frame.loading}
                previewMode={previewMode}
                operationKey={frame.modelKey}
              />
            </div>

            <FileSheet
              open={frame.inspectorOpen}
              title={inspector.title}
              isDesktop
              width={INSPECTOR_WIDTH}
              onOpenChange={frame.setInspectorOpen}
              scrollBody={false}
            >
              <FileSheetTabbedSurface headerActions={frame.zoomHeader}
                sections={inspector.tabs}
                openSectionIds={frame.inspectorTab ? [frame.inspectorTab] : []}
                onOpenSectionIdsChange={ids => frame.setInspectorTab(ids.at(-1) || "")}
              />
            </FileSheet>
          </div>
        </div>

        <StatusToast
          copyStatus={frame.copyStatus}
          screenshotStatus={frame.screenshotStatus}
          previewMode={previewMode}
          onClear={() => { frame.setCopyStatus(""); frame.setScreenshotStatus(""); }}
        />

        <ViewerAlertDialog
          onReload={view.reload}
          viewerAlertOpen={frame.viewerAlertOpen}
          viewerAlert={frame.fileStatusAlert}
          previewMode={previewMode}
          setViewerAlertOpen={frame.setViewerAlertOpen}
        />
      </div>
    </div>
    </FileSheetPortalContext.Provider>
    </HostPanelSlotContext.Provider>
  );
}
