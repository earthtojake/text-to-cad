import { createPortal } from "react-dom";
import { VIEWPORT_BOTTOM_CENTER } from "./viewportLayout.js";
import { useEffect, useMemo, useRef, useState } from "react";
import { Play, Pause, Maximize2 } from "lucide-react";
import { ToolbarButton } from "../tools/ToolbarButton.js";
import PreviewChrome from "../tools/PreviewChrome.jsx";
import { cn } from "@hardcore/ui/utils";
import { CAD_PANEL } from "../../../file-viewer/navigation/panels.js";
import FilePanelTabs from "../inspector/FilePanelTabs.jsx";
import FileSheet, { HostPanelSlotContext } from "../inspector/FileSheet.js";
import ViewerAlertCard from "../status/ViewerAlertCard.jsx";
import { ViewUpdateStatus } from "../status/ViewUpdateStatus.jsx";
import ViewerLoadingOverlay from "../status/ViewerLoadingOverlay.js";
import { presentationDisplaySettings } from "../view-settings/viewerDisplaySettings.js";
import DisplaySettingsPopover from "../view-settings/DisplaySettingsPopover.jsx";
import PlayMenu from "../tools/PlayMenu.jsx";
import OrbitMenu from "../tools/OrbitMenu.jsx";
import FloatingToolBar from "../tools/FloatingToolBar.js";
import { ToolPanelStackContext } from "../tools/toolPanelStack.js";
import { ViewportAnimationBar } from "../tools/playbar/ViewportAnimationBar.js";
import ShellViewport from "./ShellViewport.jsx";
import ViewportBottomAction, { drawingCaptureAction } from "./ViewportBottomAction.jsx";
import { AnnotateButton } from "../../../host/AnnotateButton.jsx";
import ViewportContextMenu from "./ViewportContextMenu.jsx";

const TOOLBAR_POSITION = Object.freeze({ top: "14px", left: "14px", maxWidth: "calc(100% - 60px)" });
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
 *   toolPanels?: import("react").ReactNode,
 *   playback?: any,
 *   panel?: { title: string, sections: object[] } | null,
 *   bottomAction?: { label: string, shortLabel?: string, title?: string, disabled?: boolean,
 *     onInvoke?(): void, render?: (props: object) => import("react").ReactNode, children?: import("react").ReactNode } | null,
 *   contextMenuItems?: ((press: { clientX: number, clientY: number, shiftKey: boolean }) => object[] | null) | null,
 *   onContextMenuOpenChange?: ((open: boolean) => void) | null,
 *   className?: string,
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
export default function RendererShell({ shell, tools, playback = null, toolPanels = null, panel = null, bottomAction = null, contextMenuItems = null,
  onContextMenuOpenChange = null, viewportOverlay = null, className = "",
  frameProvider = null, onCanvasPointerDown = null }) {
  const frame = shell.frame;
  const { view, resolvedScene, viewerLoading, scene } = frame;
  // The one presentation state: every gate — the viewport's, the renderer's — reads it.
  const { presenting, setPresenting } = shell;
  const animation = playback || frame.animation;
  const hasAnimation = Boolean(animation?.clips?.length);
  const animationTool = tools.find(tool => tool.id === "animate");
  const [orbitPlaying, setOrbitPlaying] = useState(true);
  const panelStackRef = useRef(null);
  const [localAnimationActive, setLocalAnimationActive] = useState(false);
  useEffect(() => { setPresenting(false); setLocalAnimationActive(false); }, [frame.modelKey, setPresenting]);
  const displayActive = shell.toolMode === "display";
  const animationActive = !displayActive && (animationTool ? animationTool.active : localAnimationActive || animation?.enabled);
  const activateDisplay = () => {
    if (displayActive) return;
    shell.selectTool("display");
    setLocalAnimationActive(false);
    if (!animationTool && animation?.enabled) animation.onRestart?.();
  };
  useEffect(() => {
    view.onPanelVisibilityChange?.(!presenting);
    return () => view.onPanelVisibilityChange?.(true);
  }, [presenting, view.onPanelVisibilityChange]);
  const previewDisplay = useMemo(() => presenting ? presentationDisplaySettings(resolvedScene.display) : resolvedScene.display, [presenting, resolvedScene.display]);
  const leaveFullscreen = () => setPresenting(false);
  // A renderer's own Animate tool is drawn as it is handed over; the shell adds only the
  // routine menu. A renderer without one gets the shell's.
  const playMenu = trigger => <PlayMenu trigger={trigger} animation={animation} />;
  const animateTool = !hasAnimation ? null : animationTool ? { ...animationTool, secondPressOpensMenu: true, menu: playMenu } : {
    id: "animate", label: "Animate", icon: <Play className="size-3" aria-hidden="true" />,
    active: Boolean(animationActive), disabled: shell.idle,
    secondPressOpensMenu: true,
    onSelect: () => {
      if (animationActive) return;
      shell.selectTool("animate"); setLocalAnimationActive(true); if (!animation.playing) animation.onPlayToggle();
    },
    menu: playMenu,
  };
  // Display takes the pointer from whichever tool had it (each tool's own `active` says so); a
  // retained effect (a panel the person keeps) stays highlighted beside it.
  const viewerTools = [...tools.filter(tool => tool !== animationTool), ...(animateTool ? [animateTool] : [])];

  const hasContent = Boolean(scene) && !viewerLoading;
  const filePanelOpen = frame.openPanel === CAD_PANEL.file;
  const action = bottomAction || (frame.drawToolActive && frame.drawing.hasContent
    ? { ...drawingCaptureAction({ disabled: viewerLoading || !hasContent, onInvoke: frame.copyDrawing }),
      // Beside Copy Drawing: the drawing and a note on it, to the chat box as an annotation.
      children: <AnnotateButton disabled={viewerLoading || !hasContent || !frame.annotateDrawing.available}
        onSubmit={note => void frame.annotateDrawing.annotate(note).then(frame.reportDelivery)} placeholder="What should change here?" /> }
    : null);
  frame.copyActionRef.current = () => {
    if (presenting) return false;
    if (frame.drawToolActive && frame.drawing.hasContent) { frame.copyDrawing(); return true; }
    if (bottomAction?.onInvoke && !bottomAction.disabled) { bottomAction.onInvoke(); return true; }
    return false;
  };
  // The renderer's overlay and the shell's own layers share one viewport context.
  const overlay = viewport => <>
    {presenting || !contextMenuItems ? null : <ViewportContextMenu viewport={viewport} items={contextMenuItems} onOpenChange={onContextMenuOpenChange} />}
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
                    modelKey={frame.modelKey}
                    presentationKey={frame.presentationKey}
                    sceneScaleMode={frame.sceneScaleMode}
                    perspective={frame.viewerPerspective}
                    perspectiveRef={frame.activePerspectiveRef}
                    projection={resolvedScene.camera.projection}
                    focalLength={resolvedScene.camera.focalLength}
                    themeSettings={resolvedScene.theme}
                    displaySettings={previewDisplay}
                    appearance={resolvedScene.appearance}
                    receiveShadows={resolvedScene.view.lighting.enabled}
                    renderMode={resolvedScene.render.enabled}
                    renderConfiguration={resolvedScene.render.configuration}
                    quality={resolvedScene.quality}
                    orbitPreview={presenting && orbitPlaying}
                    controlsHidden={presenting}
                    previewMode={presenting}
                    previewOrbitSpeed={frame.previewOrbitSpeed ?? 1}
                    isLoading={viewerLoading}
                    viewUpdate={frame.viewUpdate}
                    loadingPresentation={frame.loading}
                    drawingEnabled={frame.drawToolActive}
                    drawing={frame.drawing}
                    onPerspectiveChange={frame.handlePerspectiveChange}
                    onPresentationChange={frame.handlePresentationChange}
                    onViewerAlertChange={frame.setRuntimeAlert}
                    onCameraSettled={frame.onCameraSettled}
                    preserveInteractionPixelRatio={frame.preserveInteractionPixelRatio}
                    runtimeLifecycle={frame.runtimeLifecycle}
                  >{overlay}</ShellViewport>
                  {!presenting ? <ViewerAlertCard key={frame.modelKey} alert={frame.viewerAlert} hasContent={hasContent} onReload={view.reload} /> : null}
                  {!presenting && action ? <ViewportBottomAction shortcut={frame.copyShortcut} {...action} /> : null}
                </div>
              </div>

              <PreviewChrome active={presenting} surface={frame.hostElement} onExit={leaveFullscreen}
                settings={onOpenChange => <>
                  {hasAnimation && <PlayMenu onOpenChange={onOpenChange} allowInactive
                    trigger={<ToolbarButton label="Animation settings"><Play className="size-3.5" strokeWidth={1.5} aria-hidden="true" /></ToolbarButton>}
                    animation={animation} />}
                  <OrbitMenu enabled={orbitPlaying} onEnabledChange={setOrbitPlaying}
                    speed={frame.previewOrbitSpeed || 1} onSpeedChange={frame.setPreviewOrbitSpeed} onOpenChange={onOpenChange} />
                </>}
                playbar={hasAnimation && (animationActive || presenting) ? <ViewportAnimationBar key={frame.modelKey} runtime={animation}
                  avoidViewControl={!presenting} className="pointer-events-auto" disabled={viewerLoading || !scene} /> : presenting ?
                  <div role="toolbar" aria-label="Orbit playback" data-preview-hover-hold="" style={{ bottom: VIEWPORT_BOTTOM_CENTER }}
                    className="pointer-events-auto absolute left-1/2 -translate-x-1/2 translate-y-1/2 px-6 py-4">
                    <ToolbarButton tooltip={false} label={orbitPlaying ? "Pause orbit" : "Play orbit"} onClick={() => setOrbitPlaying(value => !value)}>
                      {orbitPlaying ? <Pause className="size-3.5" /> : <Play className="size-3.5" />}
                    </ToolbarButton>
                  </div> : null}>

              <ToolPanelStackContext.Provider value={panelStackRef}>
                <div className="pointer-events-none absolute z-20 flex max-h-[calc(100%-28px)] flex-col items-start gap-2" style={TOOLBAR_POSITION} data-cad-tool-groups="">
                  <FloatingToolBar tools={viewerTools} trailing={<DisplaySettingsPopover
                    container={frame.hostElement} disabled={shell.idle} active={displayActive} onActivate={activateDisplay} onDeactivate={() => shell.selectTool("")}
                    settings={frame.display} actions={view.displayActions} />} />
                  <div className="contents" ref={panelStackRef}>{!presenting && toolPanels}</div>
                </div>
              </ToolPanelStackContext.Provider>
              <div className="pointer-events-auto absolute flex h-[34px] items-center" style={{ top: TOOLBAR_POSITION.top, right: TOOLBAR_POSITION.left }}>
                <ToolbarButton tooltip={false} label="Fullscreen" className="size-6 bg-transparent hover:bg-transparent dark:hover:bg-transparent"
                  disabled={shell.idle} onClick={() => { setOrbitPlaying(true); setPresenting(true); }}>
                  <Maximize2 className="size-3" strokeWidth={1.5} aria-hidden="true" />
                </ToolbarButton>
              </div>

              </PreviewChrome>

              {/* One place says the view is catching up: a newer revision of the file loading behind the
                  model on screen, or a Display change being prepared — the latter's failure first, since
                  it is the one with something to retry. */}
              {view.navigationStatusSlot ? createPortal(<ViewUpdateStatus status={frame.loading.updating && !frame.viewUpdate.status.error
                ? MODEL_UPDATE_STATUS : frame.viewUpdate.status} onRetry={frame.viewUpdate.retry} />, view.navigationStatusSlot) : null}
              <ViewerLoadingOverlay
                loading={frame.presentationState?.file === frame.modelKey && frame.presentationState?.covering ? null : frame.loading}
                operationKey={frame.modelKey}
              />
            </div>

            {/* Display floats over the viewport; the file sidebar keeps its own scroll and state. */}
            {panel ? <FileSheet open={filePanelOpen} title={panel.title}>
              <div className="contents" inert={presenting} aria-disabled={presenting}><FilePanelTabs key={frame.modelKey} sections={panel.sections} active={filePanelOpen} revealRequest={shell.panelRevealRequest}
                selected={shell.panelSection} onSelectedChange={shell.setPanelSection} /></div>
            </FileSheet> : null}
          </div>
        </div>

      </div>
    </div>
  );
  return (
    <HostPanelSlotContext.Provider value={view.panelSlot}>
      {frameProvider ? frameProvider(body) : body}
    </HostPanelSlotContext.Provider>
  );
}
