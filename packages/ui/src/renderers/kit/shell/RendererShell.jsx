import { VIEWPORT_INSET_PX, VIEWPORT_STACK_BOTTOM, VIEWPORT_TOP_BAR_PX } from "./viewportLayout.js";
import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Maximize2, X } from "lucide-react";
import { Button } from "@text-to-cad/ui/primitives/button";
import { TooltipHint } from "@text-to-cad/ui/primitives/tooltip";
import PreviewChrome from "../tools/PreviewChrome.jsx";
import { useViewerMobile } from "../../../file-viewer/responsive.js";
import ViewerAlertCard, { alertDismissible, useAlertDismissal } from "../status/ViewerAlertCard.jsx";
import { modelUpdateStatus, ViewUpdateStatus } from "../status/ViewUpdateStatus.jsx";
import ViewerLoadingOverlay from "../status/ViewerLoadingOverlay.js";
import { VIEWER_RENDER_PROFILE, renderProfileKeepsPixelRatio, sceneForRenderProfile } from "../viewport/renderProfile.js";
import { NAVBAR_CONTROL_CLASS } from "../../../lib/navbarRow.js";
import DisplayPopover from "./DisplayPopover.jsx";
import { DrawingToolbar } from "../../../drawing/toolbar.jsx";
import ToolPanel, { ToolPanelFooterButton } from "../tools/ToolPanel.jsx";
import PlaybackMenu, { OrbitMenu, RoutineMenu } from "../tools/PlaybackMenu.jsx";
import FloatingToolBar from "../tools/FloatingToolBar.js";
import ToolStack from "../tools/ToolStack.jsx";
import { toolPanelClosed } from "../tools/toolStackLayout.js";
import AnimationPanel from "../tools/playbar/AnimationPanel.jsx";
import { ViewportAnimationBar, animationControlsHaveContent } from "../tools/playbar/ViewportAnimationBar.js";
import QuickEdit from "../tools/quick-edit/QuickEdit.jsx";
import { ViewportTopRight } from "./ViewportTopRight.jsx";
import ShellViewport from "./ShellViewport.jsx";
import ViewportContextMenu from "./ViewportContextMenu.jsx";

// The strip and the panels under it share one column, inset from the viewer's top and left
// edges and stopping above the cube in the bottom-left corner: the column is exactly the height
// the stack may take, so however many panels are up, it never runs past the viewer or under the
// cube (`ToolPanel.jsx` decides which of them gives way).
const INSET = `${VIEWPORT_INSET_PX}px`;
// The strip and its stack stop short of Quick Edit's button at the top-right.
const TOOLBAR_POSITION = Object.freeze({ top: INSET, left: INSET, bottom: VIEWPORT_STACK_BOTTOM, maxWidth: "calc(100% - 3.5rem)" });

/** One of the view's controls: an icon button, the navbar's, with its name on hover, below it. */
function NavbarControl({ label, disabled = false, onClick, children }) {
  return <TooltipHint content={label}>
    <Button type="button" variant="ghost" size="icon-xs" aria-label={label} disabled={disabled} onClick={onClick} className={NAVBAR_CONTROL_CLASS}>
      {children}
    </Button>
  </TooltipHint>;
}

/**
 * The frame every file-family renderer draws itself in: the viewport box with the tool strip at
 * its top-left corner and the tool stack under it, Quick Edit at the top-right, the cube in the
 * bottom-left corner, a 3D view's controls at the navbar's right end (Display's settings and
 * Preview, in the renderer's `navbarSlot`), the loading, update and alert overlays, and preview
 * mode's controls. The same
 * structure, classes and data attributes for every renderer: hosts, stylesheets and tests key on
 * them. A file's controls are never a sidebar: they are panels in the tool stack, shown by the
 * tool they belong to. Nothing sits at the bottom centre but preview's playbar.
 *
 * @param {{ shell: ReturnType<typeof import("./useRendererShell.js").useRendererShell>,
 *   tools: import("../tools/FloatingToolBar.js").ViewportTool[],
 *   toolPanels?: import("react").ReactNode,
 *   references?: readonly import("@text-to-cad/core/prompt").PromptReference[],
 *   copySelection?: (() => unknown) | null,
 *   contextMenuItems?: ((press: { clientX: number, clientY: number, shiftKey: boolean }) => object[] | null) | null,
 *   onContextMenuOpenChange?: ((open: boolean) => void) | null,
 *   frameProvider?: ((frame: import("react").ReactNode) => import("react").ReactNode) | null,
 *   onCanvasPointerDown?: ((event: import("react").PointerEvent) => void) | null,
 *   viewportOverlay?: import("react").ReactNode | ((viewport: { runtimeRef: object, hostRef: object,
 *     mountRef: object, viewerReadyTick: number, commitScene: () => boolean }) => import("react").ReactNode) }} props
 *   `tools`: left to right, from `shell.tools`; an EMPTY list draws no strip at all, which is what
 *   a file whose viewport only orbits, pans and zooms hands over. A tool the
 *   file cannot offer is left out, never handed over disabled. A tool that names a `closable`
 *   panel of its own (`panel: { id, label, startsClosed }`: Select's tree, which a single part
 *   opens with closed) is marked while that panel is closed, and a press on it while it is up
 *   opens the panel again.
 *   `toolPanels`: the tool stack's panels, top to bottom — each a `ToolPanel`
 *   (`kit/tools/ToolPanel.jsx`), shown or `hidden` by the renderer as its tools say: what
 *   the tool in hand shows (Select's tree and Reference, Position's joints), then the
 *   effects a person keeps. The stack is one column the viewer's height, gone in preview. The
 *   shell's own tools' panels lead it: Draw's, and the Animation tool's.
 *   `references`: what is selected, in the prompt grammar — the references a Quick Edit attaches
 *   (`kit/tools/quick-edit/QuickEdit.jsx`), counted in its header; the file itself always goes. A
 *   renderer that hands none has no Quick Edit: only a view whose picks and sketches a note can
 *   carry offers one, and only while the person has left it on (the host's `view.features`). The box sizes itself, for as long as it is open: a drag of its corner renders nothing
 *   here. `onClearReferences`: the renderer's clear of that selection, as a press on the
 *   background makes it; Quick Edit's X calls it, and clears Draw's ink too.
 *   `copySelection`: the viewer's copy key (⌘C / Ctrl+C) while the renderer's own tool is up and
 *   something is selected (Draw's copies the view with its ink); null when there is nothing to copy.
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
export default function RendererShell({ shell, tools, toolPanels = null, references = null, onClearReferences = null, copySelection = null, contextMenuItems = null,
  onContextMenuOpenChange = null, viewportOverlay = null,
  frameProvider = null, onCanvasPointerDown = null }) {
  const frame = shell.frame;
  const mobile = useViewerMobile();
  const { view, resolvedScene, viewerLoading, scene } = frame;
  // The one presentation state: every gate — the viewport's, the renderer's — reads it.
  const { previewing, setPreviewing } = shell;
  const animation = frame.animation;
  const hasAnimation = animationControlsHaveContent(animation);
  // Speed and Loop, once chosen in Playback settings — the playbar's, or the Animation tool's — are
  // the file's: its routine plays with them, whatever it authored, until they are chosen again.
  // Unset, the routine's own apply.
  const { speed: chosenSpeed, loop: chosenLoop } = shell.playback;
  const animationRef = useRef(animation);
  animationRef.current = animation;
  useEffect(() => {
    const runtime = animationRef.current;
    if (!animationControlsHaveContent(runtime)) return;
    if (chosenSpeed != null && Number(runtime.speed) !== chosenSpeed) runtime.onSpeedChange(chosenSpeed);
    if (chosenLoop != null && (runtime.loopEnabled !== false) !== chosenLoop) runtime.onLoopToggle(chosenLoop);
  }, [hasAnimation, animation?.speed, animation?.loopEnabled, animation?.activeClipId, chosenSpeed, chosenLoop]);
  // What those settings change is chosen for the file and applied to its routine at once.
  const playbackRuntime = hasAnimation ? {
    ...animation,
    onSpeedChange: value => { shell.setPlayback({ speed: value }); animation.onSpeedChange(value); },
    onLoopToggle: value => { shell.setPlayback({ loop: value }); animation.onLoopToggle(value); }
  } : null;
  // Preview orbits the model from the moment it starts, unless the file's Orbit says otherwise:
  // orbit on or off is the file's, kept from one preview to the next.
  const orbitPlaying = shell.playback.orbit;
  const setOrbitPlaying = value => shell.setPlayback({ orbit: typeof value === "function" ? value(shell.playback.orbit) : value });
  // Display's settings: a dropdown from its button at the navbar's right end — and in preview, from
  // the same place in preview's corner — not a tool: opening it leaves the tool in hand as it is.
  // Entering or leaving preview puts it away, as another file does.
  const [displayOpen, setDisplayOpen] = useState(false);
  useEffect(() => { setPreviewing(false); setDisplayOpen(false); }, [frame.modelKey, setPreviewing]);
  useEffect(() => { setDisplayOpen(false); }, [previewing]);
  // One viewport, two render profiles over the same Display settings (`renderProfile.js`): the
  // tools view is drawn for working on the model, preview for looking at it.
  const renderProfile = previewing ? VIEWER_RENDER_PROFILE.PREVIEW : VIEWER_RENDER_PROFILE.TOOLS;
  const drawnScene = useMemo(() => sceneForRenderProfile(resolvedScene, renderProfile), [resolvedScene, renderProfile]);
  // Routines play in preview and under the Animation tool: entering preview starts one when
  // Autoplay is on, as taking up the tool does (`useRendererShell`'s `tools.animate`).
  const enterPreview = () => {
    setPreviewing(true);
    if (hasAnimation && shell.autoplay && !animation.playing) animation.onPlayToggle();
  };
  const leavePreview = () => setPreviewing(false);
  // Preview is fullscreen: the page around the view steps aside while it lasts.
  const onFullscreenChange = view.onFullscreenChange;
  useEffect(() => {
    if (!previewing) return undefined;
    onFullscreenChange?.(true);
    return () => onFullscreenChange?.(false);
  }, [previewing, onFullscreenChange]);
  // Once neither preview nor the Animation tool holds the routine, the model goes back to rest (its
  // Routine, Speed and Loop stay for the next time). Leaving preview with the tool up is not that:
  // the routine carries on under the tool.
  const releaseRef = useRef(null);
  releaseRef.current = animation?.onRelease || null;
  const routineHeld = previewing || frame.animateToolActive;
  const wasHeld = useRef(routineHeld);
  useEffect(() => {
    if (wasHeld.current && !routineHeld) releaseRef.current?.();
    wasHeld.current = routineHeld;
  }, [routineHeld]);
  // Every tool's panel but Select's has an X that puts the tool down, back to Select (the default
  // tool, which cannot be put down). Select's tree has an X of its own that closes the tree alone:
  // the tool it belongs to then carries the strip's corner mark, and a press on that tool while it
  // is up opens the tree again; from another tool, a press only takes it up, the tree still closed.
  // Until the person has closed or opened it, the tree starts as the tool says this file starts it
  // (`panel.startsClosed`: a single part's) and closed on a phone.
  // One object while those starts stay the same: the stack's panels read it.
  const panelStarts = JSON.stringify(tools.filter(tool => tool.panel).map(tool => [tool.panel.id, Boolean(tool.panel.startsClosed)]));
  const startsClosed = useMemo(() => Object.fromEntries(JSON.parse(panelStarts)), [panelStarts]);
  const stripTools = tools.map(tool => {
    if (!tool.panel || !toolPanelClosed(frame.toolStack, tool.panel.id, { mobile, startsClosed: startsClosed[tool.panel.id] })) return tool;
    const reopen = () => frame.changeToolStack(current => ({ closed: { ...current.closed, [tool.panel.id]: false } }));
    return { ...tool, panelClosed: true, description: tool.description || `${tool.panel.label} closed`,
      onSelect: () => { if (tool.active) reopen(); tool.onSelect(); } };
  });
  // The shell's own tools' panels lead the stack while their tool is up: Draw's tools, color and
  // history, or the Animation tool's routine, transport and settings, whose X puts it down, back to
  // the default tool -- no X where Animation is the file's one tool, never put down. The
  // renderer's follow.
  // Draw's controls, and once there is ink, Copy Drawing (the view with its ink) at their foot.
  const shellPanels = <>
    {frame.drawToolActive ? <ToolPanel id="drawing" label="Drawing controls" collapsible={false}
      footer={frame.drawing.hasContent ? <ToolPanelFooterButton label="Copy Drawing" shortcut={mobile ? "" : frame.copyShortcut}
        disabled={viewerLoading || !scene} onClick={frame.copyDrawing} /> : null}>
      <DrawingToolbar drawing={frame.drawing} layout="panel" className="p-1" />
    </ToolPanel> : null}
    {frame.animateToolActive ? <AnimationPanel runtime={playbackRuntime} autoplay={shell.autoplay}
      onAutoplayChange={shell.setAutoplay} onClose={frame.animateToolFixed ? null : shell.selectDefaultTool}
      disabled={viewerLoading || !scene} /> : null}
  </>;

  const hasContent = Boolean(scene) && !viewerLoading;
  // A load the model did not survive: an alert that cannot be put away (a failed update that
  // keeps the previous version on screen can be, and keeps its chrome).
  const failed = Boolean(frame.viewerAlert) && !alertDismissible(frame.viewerAlert, hasContent);
  // The card's dismissal is the frame's, so it outlives the card (gone in preview): while the person
  // has the card put away, its icon is the navbar's way back to it, leftmost of the right-hand group.
  const alertDismissal = useAlertDismissal(frame.viewerAlert, { hasContent, scope: frame.modelKey, onNavigationActionsChange: view.onNavigationActionsChange });
  // While the model loads, or once it has failed to, the viewer shows none of its own chrome: no
  // tools, no Quick Edit, no cube, no view actions and no update status -- only the load itself,
  // or the card saying why it failed. They arrive with the model, and stay through a rebuild that
  // keeps it on screen (that is `updating`, not loading).
  const chromeHidden = viewerLoading || failed;
  // A host showing the view small (inline in a conversation: `appearance.compact`) gets the model
  // alone, not the tools, Quick Edit, the view actions or the cube; shown full size, all return.
  const compact = Boolean(view.appearance?.compact);
  // Quick Edit is the person's to turn off (in the app menu): off, it is not there at all — no
  // box, so nothing a pick or a sketch opens and no keyboard it takes.
  const quickEdit = view.features?.quickEdit !== false;
  const toolsHidden = chromeHidden || compact;
  const copyAction = () => {
    if (previewing) return false;
    if (frame.drawToolActive && frame.drawing.hasContent) { frame.copyDrawing(); return true; }
    if (copySelection) { copySelection(); return true; }
    return false;
  };
  frame.copyActionRef.current = copyAction;
  // Quick Edit's sketch: while Draw is up, and the view with its ink once there is some.
  // Quick Edit's X: nothing picked and nothing drawn, as the person would clear each.
  const clearQuickEdit = () => { onClearReferences?.(); if (frame.drawing.hasContent) frame.drawing.clear(); };
  const sketch = useMemo(() => frame.drawToolActive ? { ink: frame.drawing.hasContent, capture: frame.captureView } : null,
    [frame.drawToolActive, frame.drawing.hasContent, frame.captureView]);
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
                centres in what is visible and a change of the pane's size reaches the scene
                as a plain resize. Its background is the
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
                    viewCube={!compact && !failed}
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
                </div>
              </div>

              {/* The view's controls, at the navbar's right end: Display's settings, then Preview, for a
                  3D view (`useRendererShell`'s `previewable`); another has neither. Not while the model
                  loads or after it failed to, not in a host that shows the view small, and not in
                  Preview, which has the page to itself. */}
              {view.navbarSlot && shell.previewable && !toolsHidden && !previewing ? createPortal(<>
                <DisplayPopover open={displayOpen} onOpenChange={setDisplayOpen} disabled={shell.idle} boundary={frame.hostElement}>{frame.display}</DisplayPopover>
                <NavbarControl label="Preview" disabled={shell.idle} onClick={enterPreview}><Maximize2 className="size-3.5" aria-hidden="true" /></NavbarControl>
              </>, view.navbarSlot) : null}
              {/* Preview: fullscreen, the navbar and the tools put away and the model orbiting, its
                  routines playing. At the top-right, where Display and Preview sit outside it: Orbit,
                  then Display in its own place, then the way out where Preview was. Under the model, a
                  file with routines has its playbar, its Routines at its left end and its Playback
                  settings at its right; a static file has nothing there at all. */}
              <PreviewChrome active={previewing} surface={frame.hostElement}
                corner={menu => <>
                  <OrbitMenu orbit={orbitPlaying} onOrbitChange={setOrbitPlaying} onOpenChange={menu("orbit")}
                    speed={frame.previewOrbitSpeed || 1} onSpeedChange={frame.setPreviewOrbitSpeed} />
                  <DisplayPopover open={displayOpen} onOpenChange={open => { setDisplayOpen(open); menu("display")(open); }}
                    disabled={shell.idle} boundary={frame.hostElement}>{frame.display}</DisplayPopover>
                  <NavbarControl label="Exit preview" onClick={leavePreview}><X className="size-3.5" aria-hidden="true" /></NavbarControl>
                </>}
                playbar={menu => hasAnimation ? <ViewportAnimationBar key={frame.modelKey} runtime={animation}
                  className="pointer-events-auto" disabled={viewerLoading || !scene}
                  leading={<RoutineMenu animation={animation} onOpenChange={menu("routines")} />}
                  trailing={<PlaybackMenu animation={playbackRuntime} onOpenChange={menu("playback")}
                    autoplay={shell.autoplay} onAutoplayChange={shell.setAutoplay} />} /> : null}>

              {/* The file explorer floats over this corner, above the tools, which stay drawn under it. */}
              {toolsHidden ? null : <div className="group/tool-stack pointer-events-none absolute z-20 flex flex-col items-start gap-2" style={TOOLBAR_POSITION}
                data-mobile={mobile ? "" : undefined} data-cad-tool-groups="">
                <FloatingToolBar tools={stripTools} />
                <ToolStack hidden={previewing} mobile={mobile} startsClosed={startsClosed} layout={frame.toolStack} onLayoutChange={frame.changeToolStack}>{shellPanels}{toolPanels}</ToolStack>
              </div>}
              {/* The top-right: the host's notice once a model is on screen (`view.notice`), and Quick Edit
                  under it -- hidden, not unmounted, while the view loads: a note being written outlives a
                  reload of the model. */}
              <ViewportTopRight notice={chromeHidden ? null : view.notice} belowStrip={!toolsHidden}>
                {compact || !references || !quickEdit ? null : <QuickEdit key={frame.modelKey} className="self-stretch" hidden={chromeHidden}
                  resource={frame.resource} references={references} sketch={sketch}
                  onCopy={copyAction} onEscape={frame.escape} onClear={clearQuickEdit} disabled={viewerLoading || !scene} />}
              </ViewportTopRight>

              </PreviewChrome>

              {/* One place says the view is catching up: a newer revision of the file loading behind the
                  model on screen, or a Display change being prepared — the latter's failure first, since
                  it is the one with something to retry. */}
              {failed ? null : <div className="pointer-events-none absolute left-1/2 z-30 flex max-w-[calc(100%-1rem)] -translate-x-1/2 items-center"
                style={{ top: VIEWPORT_INSET_PX, height: VIEWPORT_TOP_BAR_PX }} data-viewport-status="">
                <ViewUpdateStatus status={frame.loading.updating && !frame.viewUpdate.status.error
                  ? modelUpdateStatus(frame.loading.progress) : frame.viewUpdate.status} onRetry={frame.viewUpdate.retry}
                  className="rounded-md bg-background/95 px-1 py-0.5 shadow-sm" />
              </div>}
              <ViewerLoadingOverlay
                loading={frame.presentationState?.file === frame.modelKey && frame.presentationState?.covering ? null : frame.loading}
                operationKey={frame.modelKey}
              />
              {/* The alert card, last: over the tools, the parts tree among them, which a warning the
                  model survives keeps on screen. The file as the alert names it (the catalog's absolute
                  path), which Report Issue keeps out of its issue. */}
              {!previewing ? <ViewerAlertCard alert={frame.viewerAlert} hasContent={hasContent} dismissed={alertDismissal.dismissed} onDismiss={alertDismissal.dismiss}
                onReload={view.reload} file={frame.modelKey || view.file?.path} /> : null}
            </div>

          </div>
        </div>

      </div>
    </div>
  );
  return frameProvider ? frameProvider(body) : body;
}
