import { VIEWPORT_BOTTOM_CENTER, VIEWPORT_INSET_PX, VIEWPORT_TOP_BAR_PX } from "./viewportLayout.js";
import { useEffect, useMemo, useRef, useState } from "react";
import { Play, Pause, RotateCcw, X } from "lucide-react";
import { ToolbarButton } from "@text-to-cad/ui/primitives/toolbar-button";
import PreviewChrome from "../tools/PreviewChrome.jsx";
import { useViewerMobile } from "../../../file-viewer/responsive.js";
import ViewerAlertCard from "../status/ViewerAlertCard.jsx";
import { ViewUpdateStatus } from "../status/ViewUpdateStatus.jsx";
import ViewerLoadingOverlay from "../status/ViewerLoadingOverlay.js";
import { VIEWER_RENDER_PROFILE, renderProfileKeepsPixelRatio, sceneForRenderProfile } from "../viewport/renderProfile.js";
import DisplayPopover from "./DisplayPopover.jsx";
import { DrawingToolbar } from "../../../drawing/toolbar.jsx";
import ToolPanel from "../tools/ToolPanel.jsx";
import PlaybackMenu from "../tools/PlaybackMenu.jsx";
import FloatingToolBar from "../tools/FloatingToolBar.js";
import ToolStack from "../tools/ToolStack.jsx";
import { ViewportAnimationBar, animationControlsHaveContent } from "../tools/playbar/ViewportAnimationBar.js";
import ShellViewport from "./ShellViewport.jsx";
import ViewportBottomAction, { drawingCaptureAction } from "./ViewportBottomAction.jsx";
import ViewportContextMenu from "./ViewportContextMenu.jsx";

// The strip and the panels under it share one column, inset from the viewer's top, left and
// bottom edges: the column is exactly the height the stack may take, so however many panels
// are up, it never runs past the viewer (`ToolPanel.jsx` decides which of them gives way).
const INSET = `${VIEWPORT_INSET_PX}px`;
// The strip and its stack stop short of the top-right bar (Display settings, Preview).
const TOOLBAR_POSITION = Object.freeze({ top: INSET, left: INSET, bottom: INSET, maxWidth: "calc(100% - 76px)" });
const MODEL_UPDATE_STATUS = Object.freeze({ pending: true, label: "Updating model…" });
// The top-right bar's buttons are transparent over the model.
const BAR_BUTTON_CLASS = "size-5 bg-transparent hover:bg-transparent dark:hover:bg-transparent";

/**
 * The frame every file-family renderer draws itself in: the viewport box with
 * the tool strip at its corner and the tool stack under it, the active tool's bottom
 * action, the loading, update and alert overlays, the top-right bar (Display settings and
 * Preview), and preview mode's controls. The same structure, classes and data attributes for every renderer:
 * hosts, stylesheets and tests key on them. A file's controls are never a sidebar: they are
 * panels in the tool stack, shown by the tool they belong to.
 *
 * @param {{ shell: ReturnType<typeof import("./useRendererShell.js").useRendererShell>,
 *   tools: import("../tools/FloatingToolBar.js").ViewportTool[],
 *   toolPanels?: import("react").ReactNode,
 *   playback?: any,
 *   bottomAction?: { label: string, shortLabel?: string, disabled?: boolean,
 *     onInvoke?(): void, render?: (props: object) => import("react").ReactNode, children?: import("react").ReactNode } | null,
 *   contextMenuItems?: ((press: { clientX: number, clientY: number, shiftKey: boolean }) => object[] | null) | null,
 *   onContextMenuOpenChange?: ((open: boolean) => void) | null,
 *   frameProvider?: ((frame: import("react").ReactNode) => import("react").ReactNode) | null,
 *   onCanvasPointerDown?: ((event: import("react").PointerEvent) => void) | null,
 *   viewportOverlay?: import("react").ReactNode | ((viewport: { runtimeRef: object, hostRef: object,
 *     mountRef: object, viewerReadyTick: number, commitScene: () => boolean }) => import("react").ReactNode) }} props
 *   `tools`: left to right, from `shell.tools`; an EMPTY list draws no strip at all,
 *   which is what a file whose viewport only orbits, pans and zooms hands over. A tool the
 *   file cannot offer is left out, never handed over disabled.
 *   `toolPanels`: the tool stack's panels, top to bottom — each a `ToolPanel`
 *   (`kit/tools/ToolPanel.jsx`), shown or `hidden` by the renderer as its tools say: what
 *   the tool in hand shows (Select's tree and Reference, Position's joints), then the
 *   effects a person keeps. The stack is one column the viewer's height, gone in preview.
 *   `playback`: the playbar runtime, when the renderer hands the shell one of its own rather
 *   than through `useRendererShell`'s `animation`. Routines play in preview alone.
 *   `bottomAction`
 *   replaces Draw's (copy the view with its ink) while the renderer's own tool is active.
 *   A composer destination's Add To Prompt (`frame.promptAction`) takes the place of both:
 *   it carries the view and whatever is selected.
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
 *   `frameProvider`: the renderer wraps the WHOLE frame — its own context, above the tool
 *   stack as well as the viewport, because both read it. It is given the frame and returns
 *   it wrapped; a renderer that passes none is mounted exactly as it is.
 *   `onCanvasPointerDown`: a press that landed on the canvas, before anything in the viewport sees
 *   it. The frame focuses itself on such a press whatever the renderer does; this is for a renderer
 *   that also has something to put down when the person reaches for the model.
 */
export default function RendererShell({ shell, tools, playback = null, toolPanels = null, bottomAction = null, contextMenuItems = null,
  onContextMenuOpenChange = null, viewportOverlay = null,
  frameProvider = null, onCanvasPointerDown = null }) {
  const frame = shell.frame;
  const mobile = useViewerMobile();
  const { view, resolvedScene, viewerLoading, scene } = frame;
  // The one presentation state: every gate — the viewport's, the renderer's — reads it.
  const { previewing, setPreviewing } = shell;
  const animation = playback || frame.animation;
  const hasAnimation = animationControlsHaveContent(animation);
  // Speed and Loop, once chosen in Playback settings, are the file's: its routine plays with
  // them, whatever it authored, until they are chosen again. Unset, the routine's own apply.
  const { speed: chosenSpeed, loop: chosenLoop } = shell.playback;
  const animationRef = useRef(animation);
  animationRef.current = animation;
  useEffect(() => {
    const runtime = animationRef.current;
    if (!animationControlsHaveContent(runtime)) return;
    if (chosenSpeed != null && Number(runtime.speed) !== chosenSpeed) runtime.onSpeedChange(chosenSpeed);
    if (chosenLoop != null && (runtime.loopEnabled !== false) !== chosenLoop) runtime.onLoopToggle(chosenLoop);
  }, [hasAnimation, animation?.speed, animation?.loopEnabled, animation?.activeClipId, chosenSpeed, chosenLoop]);
  // What Playback settings change is chosen for the file and applied to its routine at once.
  const playbackMenuRuntime = hasAnimation ? {
    ...animation,
    onSpeedChange: value => { shell.setPlayback({ speed: value }); animation.onSpeedChange(value); },
    onLoopToggle: value => { shell.setPlayback({ loop: value }); animation.onLoopToggle(value); }
  } : null;
  // Preview orbits the model from the moment it starts, unless the file's Playback settings say
  // otherwise: orbit on or off is the file's, kept from one preview to the next.
  const orbitPlaying = shell.playback.orbit;
  const setOrbitPlaying = value => shell.setPlayback({ orbit: typeof value === "function" ? value(shell.playback.orbit) : value });
  // Display's settings: a popover from its button in the top-right bar, not a tool — opening it
  // leaves the tool in hand as it is. Another file starts with it shut.
  const [displayOpen, setDisplayOpen] = useState(false);
  useEffect(() => { setPreviewing(false); setDisplayOpen(false); }, [frame.modelKey, setPreviewing]);
  // One viewport, two render profiles over the same Display settings (`renderProfile.js`): the
  // tools view is drawn for working on the model, preview for looking at it.
  const renderProfile = previewing ? VIEWER_RENDER_PROFILE.PREVIEW : VIEWER_RENDER_PROFILE.TOOLS;
  const drawnScene = useMemo(() => sceneForRenderProfile(resolvedScene, renderProfile), [resolvedScene, renderProfile]);
  // Preview is the one place routines play: entering it starts one when Autoplay is on, and
  // leaving it puts the model back at rest (its Routine, Speed and Loop stay for the next time).
  const enterPreview = () => {
    setDisplayOpen(false); setPreviewing(true);
    if (hasAnimation && shell.autoplay && !animation.playing) animation.onPlayToggle();
  };
  const leavePreview = () => { setDisplayOpen(false); setPreviewing(false); };
  const releaseRef = useRef(null);
  releaseRef.current = animation?.onRelease || null;
  const wasPreviewing = useRef(previewing);
  useEffect(() => {
    if (wasPreviewing.current && !previewing) releaseRef.current?.();
    wasPreviewing.current = previewing;
  }, [previewing]);
  // Every tool's panel but Select's has an X that puts the tool down, back to Select (the default
  // tool, which cannot be put down: its panels fold instead).
  // The shell's own tool's panel leads the stack while its tool is up: Draw's tools, color and
  // history. The renderer's follow.
  const shellPanels = <>
    {/* Headed "Draw", with its X; the buttons under it wrap as they are. */}
    {frame.drawToolActive ? <ToolPanel id="drawing" label="Drawing controls" collapsible={false}>
      <DrawingToolbar drawing={frame.drawing} layout="panel" className="p-1" />
    </ToolPanel> : null}
  </>;

  const hasContent = Boolean(scene) && !viewerLoading;
  const action = frame.promptAction || bottomAction || (frame.drawToolActive && frame.drawing.hasContent
    ? drawingCaptureAction({ disabled: viewerLoading || !hasContent, onInvoke: frame.copyDrawing }) : null);
  frame.copyActionRef.current = () => {
    if (previewing) return false;
    if (frame.drawToolActive && frame.drawing.hasContent) { frame.copyDrawing(); return true; }
    if (bottomAction?.onInvoke && !bottomAction.disabled) { bottomAction.onInvoke(); return true; }
    return false;
  };
  // The renderer's overlay and the shell's own layers share one viewport context.
  const overlay = viewport => <>
    {previewing || !contextMenuItems ? null : <ViewportContextMenu viewport={viewport} items={contextMenuItems} onOpenChange={onContextMenuOpenChange} />}
    {typeof viewportOverlay === "function" ? viewportOverlay(viewport) : viewportOverlay}
  </>;
  const body = (
    <div
      className="relative flex h-full min-h-0 flex-col overflow-hidden bg-background text-foreground"
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
            {/* The render pane's box. The canvas fills exactly this area, so a camera fit
                centres in what is visible and the host's panel column (the file tree) opening
                or closing reaches the scene as a plain resize. Its background is the
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
                    displaySettings={drawnScene.display}
                    appearance={resolvedScene.appearance}
                    receiveShadows={resolvedScene.view.lighting.enabled}
                    renderMode={resolvedScene.render.enabled}
                    renderConfiguration={resolvedScene.render.configuration}
                    quality={drawnScene.quality}
                    orbitPreview={previewing && orbitPlaying}
                    previewMode={previewing}
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
                    preserveInteractionPixelRatio={frame.preserveInteractionPixelRatio || renderProfileKeepsPixelRatio(renderProfile)}
                    runtimeLifecycle={frame.runtimeLifecycle}
                  >{overlay}</ShellViewport>
                  {!previewing ? <ViewerAlertCard key={frame.modelKey} alert={frame.viewerAlert} hasContent={hasContent} onReload={view.reload} /> : null}
                  {!previewing && action ? <ViewportBottomAction shortcut={frame.promptAction ? "" : frame.copyShortcut} {...action} /> : null}
                </div>
              </div>

              {/* Preview: the tools put away and the model orbiting, its routines playing. The
                  top-right bar stays where it is — Display settings in the same place — with an X
                  for Preview; under the model, the playbar (a static file's, the orbit's play and
                  pause), with Playback settings' cog at its right end. */}
              <PreviewChrome active={previewing} surface={frame.hostElement} hold={displayOpen}
                actions={() => <>
                  <DisplayPopover open={displayOpen} onOpenChange={setDisplayOpen} disabled={shell.idle}>{frame.display}</DisplayPopover>
                  <ToolbarButton label="Reset view" className={BAR_BUTTON_CLASS} disabled={shell.idle} onClick={shell.resetView}>
                    <RotateCcw className="size-3" strokeWidth={1.5} aria-hidden="true" />
                  </ToolbarButton>
                  {previewing
                    ? <ToolbarButton key="exit" tooltip={false} label="Exit preview" className={BAR_BUTTON_CLASS} onClick={leavePreview}>
                      <X className="size-3" strokeWidth={1.5} aria-hidden="true" />
                    </ToolbarButton>
                    : <ToolbarButton key="preview" label="Preview" className={BAR_BUTTON_CLASS} disabled={shell.idle} onClick={enterPreview}>
                      <Play className="size-3" strokeWidth={1.5} aria-hidden="true" />
                    </ToolbarButton>}
                </>}
                playbar={onMenuOpenChange => {
                  const settings = <PlaybackMenu animation={playbackMenuRuntime} onOpenChange={onMenuOpenChange}
                    autoplay={shell.autoplay} onAutoplayChange={shell.setAutoplay}
                    orbit={orbitPlaying} onOrbitChange={setOrbitPlaying}
                    orbitSpeed={frame.previewOrbitSpeed || 1} onOrbitSpeedChange={frame.setPreviewOrbitSpeed} />;
                  return hasAnimation ? <ViewportAnimationBar key={frame.modelKey} runtime={animation} trailing={settings}
                    className="pointer-events-auto" disabled={viewerLoading || !scene} /> :
                  <div role="toolbar" aria-label="Orbit playback" data-preview-hover-hold="" style={{ bottom: VIEWPORT_BOTTOM_CENTER }}
                    className="pointer-events-auto absolute left-1/2 flex -translate-x-1/2 translate-y-1/2 items-center gap-1 px-6 py-4">
                    <ToolbarButton tooltip={false} label={orbitPlaying ? "Pause orbit" : "Play orbit"} onClick={() => setOrbitPlaying(value => !value)}>
                      {orbitPlaying ? <Pause className="size-3.5" /> : <Play className="size-3.5" />}
                    </ToolbarButton>
                    {settings}
                  </div>;
                }}>

              <div className="group/tool-stack pointer-events-none absolute z-20 flex flex-col items-start gap-2" style={TOOLBAR_POSITION}
                data-mobile={mobile ? "" : undefined} data-cad-tool-groups="">
                <FloatingToolBar tools={tools} />
                <ToolStack hidden={previewing} mobile={mobile} layout={frame.toolStack} onLayoutChange={frame.changeToolStack}>{shellPanels}{toolPanels}</ToolStack>
              </div>

              </PreviewChrome>

              {/* One place says the view is catching up: a newer revision of the file loading behind the
                  model on screen, or a Display change being prepared — the latter's failure first, since
                  it is the one with something to retry. */}
              <div className="pointer-events-none absolute left-1/2 z-30 flex max-w-[calc(100%-1rem)] -translate-x-1/2 items-center"
                style={{ top: VIEWPORT_INSET_PX, height: VIEWPORT_TOP_BAR_PX }} data-viewport-status="">
                <ViewUpdateStatus status={frame.loading.updating && !frame.viewUpdate.status.error
                  ? MODEL_UPDATE_STATUS : frame.viewUpdate.status} onRetry={frame.viewUpdate.retry}
                  className="rounded-md bg-background/95 px-1 py-0.5 shadow-sm" />
              </div>
              <ViewerLoadingOverlay
                loading={frame.presentationState?.file === frame.modelKey && frame.presentationState?.covering ? null : frame.loading}
                operationKey={frame.modelKey}
              />
            </div>

          </div>
        </div>

      </div>
    </div>
  );
  return frameProvider ? frameProvider(body) : body;
}
