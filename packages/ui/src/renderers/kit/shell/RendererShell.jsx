import { createPortal } from "react-dom";
import { VIEWPORT_BOTTOM_CENTER } from "./viewportLayout.js";
import { useEffect, useMemo, useState } from "react";
import { Play, Pause, Maximize2 } from "lucide-react";
import { TooltipProvider } from "@hardcore/ui/primitives/tooltip";
import { ToolbarButton } from "../tools/ToolbarButton.js";
import PreviewChrome from "../tools/PreviewChrome.jsx";
import { cn } from "@hardcore/ui/utils";
import { CAD_PANEL } from "../../../file-viewer/navigation/panels.js";
import FilePanelTabs from "../inspector/FilePanelTabs.jsx";
import FileSheet, { FileSheetPortalContext, HostPanelSlotContext } from "../inspector/FileSheet.js";
import ViewerAlertCard from "../status/ViewerAlertCard.jsx";
import StatusToast from "../status/StatusToast.js";
import { ViewUpdateStatus } from "../status/ViewUpdateStatus.jsx";
import ViewerLoadingOverlay from "../status/ViewerLoadingOverlay.js";
import DisplaySettingsPopover from "../view-settings/DisplaySettingsPopover.jsx";
import PlayMenu from "../tools/PlayMenu.jsx";
import OrbitMenu from "../tools/OrbitMenu.jsx";
import FloatingToolBar from "../tools/FloatingToolBar.js";
import { ViewportAnimationBar } from "../tools/playbar/ViewportAnimationBar.js";
import ShellViewport from "./ShellViewport.jsx";
import ViewportBottomAction, { drawingCaptureAction } from "./ViewportBottomAction.jsx";
import ViewportContextMenu from "./ViewportContextMenu.jsx";

const TOOLBAR_POSITION = Object.freeze({ top: "14px", left: "14px", maxWidth: "calc(100% - 60px)" });
// The host's panel column sizes a panel; this is only the sheet's nominal width.
const PANEL_WIDTH = 365;
const MODEL_UPDATE_STATUS = Object.freeze({ pending: true, label: "Updating model…" });

/**
 * The frame every file-family renderer draws itself in: the viewport box with
 * the tool strip at its corner, the active tool's bottom action, the loading,
 * update and alert overlays, fullscreen's controls, and the file's file panel
 * portaled into the host's panel column, and the Display toolbar popover. The same
 * structure, classes and data attributes for every renderer: hosts, stylesheets
 * and tests key on them.
 *
 * @param {{ shell: ReturnType<typeof import("./useRendererShell.js").useRendererShell>,
 *   tools: import("../tools/FloatingToolBar.js").ViewportTool[],
 *   onPreviewActiveChange?: (active: boolean) => void,
 *   toolPanels?: import("react").ReactNode,
 *   playback?: any,
 *   panel?: { title: string, sections: object[] } | null,
 *   bottomAction?: { label: string, shortLabel?: string, title?: string, disabled?: boolean,
 *     onInvoke?(): void, render?: (props: object) => import("react").ReactNode, children?: import("react").ReactNode } | null,
 *   contextMenuItems?: ((press: { clientX: number, clientY: number, shiftKey: boolean }) => object[] | null) | null,
 *   onContextMenuOpenChange?: ((open: boolean) => void) | null,
 *   sceneRevision?: number, className?: string,
 *   frameProvider?: ((frame: import("react").ReactNode) => import("react").ReactNode) | null,
 *   onCanvasPointerDown?: ((event: import("react").PointerEvent) => void) | null,
 *   viewportOverlay?: import("react").ReactNode | ((viewport: { runtimeRef: object, hostRef: object,
 *     mountRef: object, viewerReadyTick: number, commitScene: () => boolean }) => import("react").ReactNode) }} props
 *   `tools`: left to right, from `shell.tools`; an EMPTY list draws no strip at all,
 *   which is what a file whose viewport only orbits, pans and zooms hands over.
 *   `panel`: the file's own panel, whose nav-row button the renderer's registration
 *   declares (`viewerPanels`): its sections (`FilePanelSections`), or none for a file
 *   whose only settings are Display's. `bottomAction`
 *   replaces Draw's (copy the view with its ink) while the renderer's own tool is active.
 *   `contextMenuItems`: what THIS renderer offers on a secondary tap over the canvas; the
 *   gesture, the anchor and the dismissal are the shell's (`ViewportContextMenu.jsx`), and a
 *   renderer that passes none has no viewport menu at all. `onContextMenuOpenChange(open)`
 *   says while that menu is up, for a renderer that marks what the menu is about.
 *   `viewportOverlay`: the renderer's own layer over the canvas; as a function it is given
 *   the viewport, which is five things: its live runtime, the element its pointer events
 *   arrive on, the element the canvas is mounted in, a tick that changes when the runtime is
 *   replaced, and `commitScene()` for a scene that changed IN PLACE. A handle overlay or a
 *   pointer pick (`kit/tools/select/usePointerPick.js`) reads the first, second and fourth;
 *   a renderer that draws its own canvas over the model or publishes a scene progressively
 *   needs the other two.
 *   `frameProvider`: the renderer wraps the WHOLE frame — its own context, above the panels'
 *   portal as well as the viewport, because both halves read it. It is given the frame and returns
 *   it wrapped; a renderer that passes none is mounted exactly as it is.
 *   `onCanvasPointerDown`: a press that landed on the canvas, before anything in the viewport sees
 *   it. The frame focuses itself on such a press whatever the renderer does; this is for a renderer
 *   that also has something to put down when the person reaches for the model.
 */
export default function RendererShell({ shell, tools, playback = null, onPreviewActiveChange = null, toolPanels = null, panel = null, bottomAction = null, contextMenuItems = null,
  onContextMenuOpenChange = null, sceneRevision = 0, viewportOverlay = null, className = "",
  frameProvider = null, onCanvasPointerDown = null }) {
  const frame = shell.frame;
  const { view, resolvedScene, previewMode, viewerLoading, scene } = frame;
  const animation = playback || frame.animation;
  const hasAnimation = Boolean(animation?.clips?.length);
  const animationTool = tools.find(tool => tool.id === "animate");
  const [fullscreen, setFullscreen] = useState(false);
  const [orbitPlaying, setOrbitPlaying] = useState(true);
  const [localAnimationActive, setLocalAnimationActive] = useState(false);
  useEffect(() => { setFullscreen(false); setLocalAnimationActive(false); }, [frame.modelKey]);
  const fullscreenActive = previewMode || fullscreen;
  const displayActive = shell.toolMode === "display";
  const animationActive = !displayActive && (animationTool ? animationTool.active : localAnimationActive || animation?.enabled);
  const activateDisplay = () => {
    if (displayActive) return;
    shell.selectTool("display");
    setLocalAnimationActive(false);
    if (!animationTool && animation?.enabled) animation.onRestart?.();
  };
  useEffect(() => {
    view.onPanelVisibilityChange?.(!fullscreenActive);
    return () => view.onPanelVisibilityChange?.(true);
  }, [fullscreenActive, view.onPanelVisibilityChange]);
  useEffect(() => { onPreviewActiveChange?.(fullscreenActive); }, [fullscreenActive, onPreviewActiveChange]);
  const previewDisplay = useMemo(() => fullscreenActive ? { ...resolvedScene.display, clip: { ...resolvedScene.display.clip, enabled: false }, exploded: { ...resolvedScene.display.exploded, enabled: false, amount: 0 } } : resolvedScene.display, [fullscreenActive, resolvedScene.display]);
  const leaveFullscreen = () => { setFullscreen(false); if (previewMode) view.onFullscreenChange?.(false); };
  if (shell.previewExitRef) shell.previewExitRef.current = fullscreenActive ? () => { leaveFullscreen(); return true; } : null;
  const animateTool = hasAnimation ? {
    ...animationTool,
    id: "animate", label: "Animate", icon: <Play className="size-3" aria-hidden="true" />,
    active: Boolean(animationActive), disabled: shell.idle,
    secondPressOpensMenu: true,
    onSelect: () => {
      if (animationActive) return;
      if (animationTool) animationTool.onSelect();
      else { shell.selectTool("animate"); setLocalAnimationActive(true); if (!animation.playing) animation.onPlayToggle(); }
    },
    menu: trigger => <PlayMenu trigger={trigger} animation={animation} />,
  } : null;
  const viewerTools = [...tools.filter(tool => tool !== animationTool), ...(animateTool ? [animateTool] : [])]
    .map(tool => displayActive ? { ...tool, active: false } : tool);

  const hasContent = Boolean(scene) && !viewerLoading;
  const filePanelOpen = frame.openPanel === CAD_PANEL.file;
  const action = bottomAction || (frame.drawToolActive && frame.drawing.hasContent
    ? drawingCaptureAction({ composer: frame.composer, disabled: viewerLoading || !hasContent, onInvoke: frame.copyDrawing })
    : null);
  frame.copyActionRef.current = () => {
    if (fullscreenActive || previewMode) return false;
    if (frame.drawToolActive && frame.drawing.hasContent) { frame.copyDrawing(); return true; }
    if (bottomAction?.onInvoke && !bottomAction.disabled) { bottomAction.onInvoke(); return true; }
    return false;
  };
  // The renderer's overlay and the shell's own layers share one viewport context.
  const overlay = viewport => <>
    {previewMode || fullscreenActive || !contextMenuItems ? null : <ViewportContextMenu viewport={viewport} items={contextMenuItems} onOpenChange={onContextMenuOpenChange} />}
    {typeof viewportOverlay === "function" ? viewportOverlay(viewport) : viewportOverlay}
  </>;
  const body = (
    <div
      className={cn("relative flex h-full min-h-0 flex-col overflow-hidden bg-background text-foreground", className)}
      data-slot="cad-file-view"
      data-cad-surface
      tabIndex={-1}
      onPointerDownCapture={event => {
        if (!(event.target instanceof Element) || !event.target.closest("canvas")) return;
        onCanvasPointerDown?.(event);
        event.currentTarget.focus({ preventScroll: true });
      }}
      ref={frame.hostRef}
    >
      <div className="relative flex h-full min-w-0 flex-col overflow-hidden bg-transparent">
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
                    onProjectionChange={frame.setProjection}
                    displayMode={frame.displayMode}
                    displayPreset={frame.displayPreset}
                    displayModes={frame.displayModes}
                    onDisplayModeChange={frame.setDisplayMode}
                    focalLength={resolvedScene.camera.focalLength}
                    themeSettings={resolvedScene.theme}
                    displaySettings={previewDisplay}
                    appearance={resolvedScene.appearance}
                    receiveShadows={resolvedScene.view.lighting.enabled}
                    renderMode={resolvedScene.render.enabled}
                    renderConfiguration={resolvedScene.render.configuration}
                    quality={resolvedScene.quality}
                    orbitPreview={fullscreenActive && orbitPlaying}
                    controlsHidden={Boolean(fullscreenActive)}
                    previewMode={previewMode}
                    previewOrbitSpeed={frame.previewOrbitSpeed || 1}
                    isLoading={viewerLoading}
                    viewUpdate={frame.viewUpdate}
                    loadingPresentation={frame.loading}
                    drawingEnabled={!fullscreenActive && frame.drawToolActive}
                    drawing={frame.drawing}
                    onPerspectiveChange={frame.handlePerspectiveChange}
                    onPresentationChange={frame.handlePresentationChange}
                    onViewerAlertChange={frame.setRuntimeAlert}
                    onCameraSettled={frame.onCameraSettled}
                    preserveInteractionPixelRatio={frame.preserveInteractionPixelRatio}
                    runtimeLifecycle={frame.runtimeLifecycle}
                  >{overlay}</ShellViewport>
                  {!previewMode && !fullscreenActive ? <ViewerAlertCard key={frame.modelKey} alert={frame.viewerAlert} hasContent={hasContent} onReload={view.reload} /> : null}
                  {!previewMode && !fullscreenActive && action ? <ViewportBottomAction composer={frame.composer} shortcut={frame.copyShortcut} {...action} /> : null}
                </div>
              </div>

              <PreviewChrome active={fullscreenActive} surface={frame.hostElement} onExit={leaveFullscreen}
                settings={onOpenChange => <>
                  {hasAnimation && <PlayMenu onOpenChange={onOpenChange} allowInactive
                    trigger={<ToolbarButton label="Animation settings"><Play className="size-3.5" strokeWidth={1.5} aria-hidden="true" /></ToolbarButton>}
                    animation={animation} />}
                  <OrbitMenu enabled={orbitPlaying} onEnabledChange={setOrbitPlaying}
                    speed={frame.previewOrbitSpeed || 1} onSpeedChange={frame.setPreviewOrbitSpeed} onOpenChange={onOpenChange} />
                </>}
                playbar={hasAnimation && (animationActive || fullscreenActive) ? <ViewportAnimationBar key={frame.modelKey} runtime={animation}
                  avoidViewControl={!fullscreenActive} className="pointer-events-auto" disabled={viewerLoading || !scene} /> : fullscreenActive ?
                  <div role="toolbar" aria-label="Orbit playback" data-preview-hover-hold="" style={{ bottom: VIEWPORT_BOTTOM_CENTER }}
                    className="pointer-events-auto absolute left-1/2 -translate-x-1/2 translate-y-1/2 px-6 py-4">
                    <ToolbarButton tooltip={false} label={orbitPlaying ? "Pause orbit" : "Play orbit"} onClick={() => setOrbitPlaying(value => !value)}>
                      {orbitPlaying ? <Pause className="size-3.5" /> : <Play className="size-3.5" />}
                    </ToolbarButton>
                  </div> : null}>

              {previewMode ? null : <>
                <div className="pointer-events-none absolute z-20 flex max-h-[calc(100%-28px)] flex-col items-start gap-2" style={TOOLBAR_POSITION} data-cad-tool-groups="">
                  <FloatingToolBar inline tools={viewerTools} trailing={<DisplaySettingsPopover
                    container={frame.hostElement} disabled={shell.idle} active={displayActive} onActivate={activateDisplay}
                    settings={frame.display} actions={view.displayActions} />} />
                  {!fullscreenActive && toolPanels}
                </div>
                <TooltipProvider delayDuration={250}>
                  <div className="pointer-events-auto absolute flex h-[34px] items-center" style={{ top: TOOLBAR_POSITION.top, right: TOOLBAR_POSITION.left }}>
                    <ToolbarButton tooltip={false} label="Fullscreen" className="size-6 bg-transparent hover:bg-transparent dark:hover:bg-transparent"
                      disabled={shell.idle} onClick={() => { setOrbitPlaying(true); setFullscreen(true); }}>
                      <Maximize2 className="size-3" strokeWidth={1.5} aria-hidden="true" />
                    </ToolbarButton>
                  </div>
                </TooltipProvider>
              </>}

              </PreviewChrome>

              {/* One place says the view is catching up: a newer revision of the file loading behind the
                  model on screen, or a Display change being prepared — the latter's failure first, since
                  it is the one with something to retry. */}
              {view.navigationStatusSlot ? createPortal(<ViewUpdateStatus status={frame.loading.updating && !frame.viewUpdate.status.error
                ? MODEL_UPDATE_STATUS : frame.viewUpdate.status} onRetry={frame.viewUpdate.retry} />, view.navigationStatusSlot) : null}
              <ViewerLoadingOverlay
                loading={frame.presentationState?.file === frame.modelKey && frame.presentationState?.covering ? null : frame.loading}
                previewMode={previewMode}
                operationKey={frame.modelKey}
              />
            </div>

            {/* Display floats over the viewport; the file sidebar keeps its own scroll and state. */}
            {panel ? <FileSheet open={filePanelOpen} title={panel.title}
              isDesktop width={PANEL_WIDTH} scrollBody={false}>
              <div className="contents" inert={Boolean(fullscreenActive)} aria-disabled={Boolean(fullscreenActive)}><FilePanelTabs key={frame.modelKey} sections={panel.sections} active={filePanelOpen} revealRequest={shell.panelRevealRequest} /></div>
            </FileSheet> : null}
          </div>
        </div>

        <StatusToast
          copyStatus={frame.copyStatus}
          screenshotStatus={frame.screenshotStatus}
          previewMode={previewMode || fullscreenActive}
          onClear={() => { frame.setCopyStatus(""); frame.setScreenshotStatus(""); }}
        />
      </div>
    </div>
  );
  return (
    <HostPanelSlotContext.Provider value={view.panelSlot}>
    <FileSheetPortalContext.Provider value={frame.hostElement}>
      {frameProvider ? frameProvider(body) : body}
    </FileSheetPortalContext.Provider>
    </HostPanelSlotContext.Provider>
  );
}
