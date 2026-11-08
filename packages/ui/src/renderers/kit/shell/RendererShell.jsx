import { useEffect, useMemo, useRef, useState } from "react";
import { LoaderCircle, Play, SlidersHorizontal, X } from "lucide-react";
import { Button } from "@cad/ui/primitives/button";
import { ToolbarButton } from "@cad/ui/primitives/toolbar-button";
import { TooltipHint } from "@cad/ui/primitives/tooltip";
import { NAVBAR_CONTROL_CLASS } from "../../../lib/navbarRow.js";
import { cn } from "@cad/ui/utils";
import { useI18n } from "@cad/ui/i18n";
import { usePreviewIdle } from "../tools/PreviewChrome.jsx";
import { useViewerMobile } from "../../../file-viewer/responsive.js";
import { alertDismissible, useAlertDismissal } from "../status/ViewerAlertCard.jsx";
import { modelUpdateStatus } from "../status/ViewUpdateStatus.jsx";
import DisplayPopover, { DisplayMenuItems } from "./DisplayPopover.jsx";
import ProjectionToggle, { otherProjection } from "./ProjectionToggle.jsx";
import { viewportZoom, zoomViewControl } from "./ZoomControl.jsx";
import { ViewHome } from "./ViewCorner.jsx";
import { OrthographicProjectionIcon, PerspectiveProjectionIcon } from "../camera/ProjectionModeIcons.js";
import PreviewSettings from "./PreviewSettings.jsx";
import { withGroups } from "../../../annotation/geometry.js";
import { useStripButtonClass } from "../tools/FloatingToolBar.js";
import { AnnotationToolbar } from "../../../annotation/toolbar.jsx";
import ToolStack from "../tools/ToolStack.jsx";
import PreviewPlaybar from "../tools/playbar/PreviewPlaybar.jsx";
import { animationControlsHaveContent } from "../tools/playbar/AnimationTimeControl.js";
import QuickEdit from "../tools/quick-edit/QuickEdit.jsx";
import ShellViewport from "./ShellViewport.jsx";
import PreviewView from "./PreviewView.jsx";
import { previewCoverStep } from "./previewCover.js";
import ViewportContextMenu from "./ViewportContextMenu.jsx";
import DoubleClickFit from "./DoubleClickFit.jsx";
import AnnotationSelectionBar from "../tools/annotate/AnnotationSelectionBar.jsx";
import ViewFrame from "./ViewFrame.jsx";
import { useControlUsage } from "../../../usage/controls.js";

// The sidebar sections Preview offers: posing the model and playing its routines.
// Preview's cover: at least this long, then until publication and the picture are ready.
// The picture is checked this often until it has converged.
// The cover waits at least MIN; at MAX it stops waiting for more components, and lets the picture on
// screen finish converging for at most FINISH more.
const PREVIEW_COVER_MIN_MS = 700, PREVIEW_COVER_QUIET_MS = 400, PREVIEW_COVER_MAX_MS = 5000, PREVIEW_COVER_FINISH_MS = 1000,
  PREVIEW_COVER_CONVERGE_MS = 50;

/** One of Preview's bar's controls: the navbar's icon button, named on hover, below it. */
function BarControl({ label, active = undefined, disabled = false, onClick, children, ...props }) {
  return <TooltipHint content={label} side="bottom" disabled={active === true}>
    <Button type="button" variant="ghost" size="icon-xs" aria-label={label} aria-pressed={active} disabled={disabled} onClick={onClick}
      className={NAVBAR_CONTROL_CLASS} {...props}>{children}</Button>
  </TooltipHint>;
}
// The projection on screen, as an icon (a More menu's row on a phone's strip).
function ProjectionIcon({ value }) {
  const Icon = value === "perspective" ? PerspectiveProjectionIcon : OrthographicProjectionIcon;
  return <Icon />;
}

function ViewControl({ label, disabled = false, tooltipSide = "top", onClick, children }) {
  return <ToolbarButton label={label} tooltipSide={tooltipSide} disabled={disabled} onClick={onClick} className={useStripButtonClass()}>
    {children}
  </ToolbarButton>;
}

// Two presses on the same ink this close together are one double-click.
const DOUBLE_PRESS_MS = 600;

/**
 * A 3D view's frame: every view's one frame (`ViewFrame.jsx`: the root, the docked panel, the strip
 * at the centre of the whole view, the top-right, the corner, the cards) with what a 3D view puts in
 * it — its viewport (`ShellViewport`) as the canvas, Preview's view over it and Preview's cover, the
 * strip's view controls (Projection, Display, then Preview), the tool stack, Home at the cube's
 * upper-left in the corner, the playbar at the bottom centre and Preview's own chrome. The same
 * structure, classes and data attributes for every renderer: hosts, stylesheets and tests key on
 * them. The toolbar is for using tools, the sidebar for reading the file: a tool's own controls are
 * panels in the tool stack, shown by the tool they belong to; what there is to read of the file (a
 * tree, joints, metadata) is the sidebar's sections, whatever the tool.
 *
 * @param {{ shell: ReturnType<typeof import("./useRendererShell.js").useRendererShell>,
 *   tools: import("../tools/FloatingToolBar.js").ViewportTool[],
 *   toolPanels?: import("react").ReactNode, sidebar?: import("react").ReactNode,
 *   references?: readonly import("@cad/core/prompt").PromptReference[],
 *   referenceChips?: readonly import("../tools/quick-edit/ReferenceChips.jsx").ReferenceChip[] | null,
 *   requests?: ReadonlyArray<import("../tools/quick-edit/ReferenceChips.jsx").ReferenceChip & { request: string }> | null,
 *   onClearRequests?: (() => void) | null,
 *   nameReference?: ((reference: import("@cad/core/prompt").PromptReference) => string | import("../inspector/pickGlyph.jsx").CompactName) | null,
 *   copySelection?: (() => unknown) | null,
 *   contextMenuItems?: ((press: { clientX: number, clientY: number, shiftKey: boolean }) => object[] | null) | null,
 *   onContextMenuOpenChange?: ((open: boolean) => void) | null,
 *   frameProvider?: ((frame: import("react").ReactNode) => import("react").ReactNode) | null,
 *   onCanvasPointerDown?: ((event: import("react").PointerEvent) => void) | null,
 *   viewportOverlay?: import("react").ReactNode | ((viewport: { runtimeRef: object, hostRef: object,
 *     mountRef: object, viewerReadyTick: number, commitScene: () => boolean }) => import("react").ReactNode) }} props
 *   `tools`: left to right, from `shell.tools`; an EMPTY list draws no strip at all, which is what
 *   a file whose viewport only orbits, pans and zooms hands over. A tool the
 *   file cannot offer is left out, never handed over disabled.
 *   `toolPanels`: the tool stack's panels, top to bottom — each a `ToolPanel`
 *   (`kit/tools/ToolPanel.jsx`), shown or `hidden` by the renderer as its tools say: the
 *   effects a person keeps. The stack is one column under the strip, gone in preview. The
 *   shell's own tool's panel leads it: Annotate's.
 *   `subToolbar`: the renderer's tool in hand's own row under the strip (`kit/tools/SubToolbar.jsx`:
 *   the active tool); the shell's own tool's row (Annotate's) takes its place while it is up.
 *   `sidebar`: the file's sections, in order — each a `ToolPanel`, drawn as a tab of the view's panel
 *   (`FlatPanel.jsx`): a tree, joints, metadata. None (null): no panel.
 *   `inspect`: what is picked and how the renderer describes it (`inspector/inspect.js`): the frame's
 *   Selected pane under the panel's tabs, the hover tip under Select, and the rows of both.
 *   Gone in preview, kept mounted, so a tree keeps its expansion and scroll.
 *   `referenceChips`: the renderer's description of that selection, as Quick Edit shows it (its
 *   chips, `kit/tools/quick-edit/ReferenceChips.jsx`): a chip each for one or several picks of a kind
 *   on one part, its card, its hover and its removal. Without them Quick Edit counts the references.
 *   `nameReference`: what the renderer calls a reference into its file, for a reference pasted
 *   into Quick Edit's note ("cam"); "" for one it cannot name.
 *   `references`: what is selected, in the prompt grammar — the references a Quick Edit attaches
 *   (`kit/tools/quick-edit/QuickEdit.jsx`), counted in its header; the file itself always goes. A
 *   renderer that hands none has no Quick Edit: only a view whose picks and annotations a note can
 *   carry offers one. The box sizes itself, for as long as it is open: a drag of its corner renders nothing
 *   here. `onClearReferences`: the renderer's clear of that selection, as a press on the
 *   background makes it; Quick Edit's X calls it, and clears Annotate's ink too.
 *   `requests`: the changes the renderer was asked for in the view that its file's code should make
 *   (a value or a placement the code holds, say), each a chip in Quick Edit
 *   with what its prompt carries (`request`); `onClearRequests`: drops them all, as Quick Edit's
 *   X does and a note that has gone does.
 *   `copySelection`: the viewer's copy key (⌘C / Ctrl+C) while the renderer's own tool is up and
 *   something is selected (Annotate's copies the view with its ink); null when there is nothing to copy.
 *   `zoomToSelection`: `{ run(), available }`, the zoom menu's Zoom to selection (`ZoomControl.jsx`): what
 *   is picked, framed; off without it.
 *   `doubleClickFits`: a double-click on empty space under Select fits the model (`DoubleClickFit`);
 *   false for a renderer whose double-click is its own (an engine document's isolates and looks at).
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
 *   `onSelectPress`: under Select, a press on the canvas, before the annotation's ink and any part:
 *   the renderer's own pickable overlays (a measurement). True when it picked something, and the
 *   press goes no further; false to let it on.
 *   `onSelectHover`: under Select, the pointer resting on the canvas (null: it left, or Select went
 *   down): the renderer lights its own overlay under it, and returns true when there is one.
 *   `selectsAnnotations`: whether Select picks the annotation's ink, as the renderer's Select filter says; the
 *   ink is drawn either way.
 *   `inkTouches`: what the model is under a point of the view, `(clientX, clientY) => [{ part, ref? }]` —
 *   the part, with the face or edge there as a prompt reference where the renderer can name one: what
 *   Annotate records a mark as touching. Without it, a mark touches parts alone.
 *   `previewView`: Preview's own, while it is open (`shell.previewing`), for a 3D view: the scene the
 *   renderer built for it (`scene`, its family's builder over the editor's geometry, null until it can be
 *   drawn), what drives that scene from inside Preview's viewport (`overlay(viewport, drawn)`, given
 *   the Render scene Preview draws), its routine (`animation`, the Animation section's in Preview),
 *   its publication readiness (`complete`, false while components are arriving),
 *   and Preview viewport's `runtimeLifecycle` and `onCameraSettled`. Preview is a view of its own
 *   (`PreviewView.jsx`) over the editor's, which nothing of it reaches.
 */
export default function RendererShell({ shell, tools, toolPanels = null, subToolbar = null, sidebar = null, references = null, referenceChips = null, nameReference = null, onClearReferences = null,
  requests = null, onClearRequests = null, copySelection = null, contextMenuItems = null,
  onContextMenuOpenChange = null, viewportOverlay = null, previewView = null,
  frameProvider = null, onCanvasPointerDown = null, onSelectPress = null, onSelectHover = null, selectsAnnotations = true, inkTouches = null,
  doubleClickFits = true, zoomToSelection = null, inspect = null }) {
  const { t } = useI18n();
  const frame = shell.frame;
  // What a tool's letter takes up (`useRendererShell`'s `onKey`): the strip as drawn now.
  frame.toolKeys.current = tools;
  const mobile = useViewerMobile();
  const { view, resolvedScene, viewerLoading, scene } = frame;
  // The one presentation state: every gate — the viewport's, the renderer's — reads it.
  const { previewing, setPreviewing } = shell;
  // A phone's open section is a sheet up from the bottom, where Quick Edit's peek is: it steps aside.
  // Preview's settings panel: closed as Preview opens, until its button brings it out.
  const [previewPanelOpen, setPreviewPanelOpen] = useState(false);
  // Preview is a view of its own, mounted over the editor's as it opens (`PreviewView.jsx`), and
  // its first picture takes a moment on a large model — its scene built from the published mesh
  // and remaining components arriving — so it is covered ("Preparing preview…") until
  // its first frame is presented (`previewPresented`), the publication is complete,
  // and its picture converged (every sample of its frame drawn: the view's `pictureProgress`) — unless
  // it starts over, the view moving (a routine playing), when there is nothing to wait for — or at most
  // a few seconds. Then the cover fades away from the finished picture. Leaving needs no cover: the
  // Preview's view goes, and under it is the editor's, as it was.
  const previewViewRef = frame.previewViewRef;
  const [previewPresented, setPreviewPresented] = useState(false);
  const previewPresentedRef = useRef(false);
  previewPresentedRef.current = previewing && previewPresented;
  // A press covers the view first, in its own frame, and preview is entered under it: preview's
  // first render can take a moment on a large model, and the cover answers the press at once.
  const [coverRequested, setCoverRequested] = useState(false);
  // The cover is preview's from the render that enters it, so not one frame of preview shows
  // before it: settled is reset there, and set once preview has come together. Each crossing is
  // taken in the render that makes it, never in an effect after it (another commit): entering also
  // answers the press's request and closes the settings panel.
  const [previewSettled, setPreviewSettled] = useState(false);
  const [coverFor, setCoverFor] = useState(previewing);
  if (coverFor !== previewing) {
    setCoverFor(previewing);
    setPreviewSettled(false);
    setPreviewPresented(false);
    if (previewing) { setCoverRequested(false); setPreviewPanelOpen(false); }
  }
  const previewCovered = coverRequested || (previewing && !previewSettled);
  // What moves Preview's picture on purpose: its Orbit, or its routine playing (`previewCover.js`).
  const previewMovingRef = useRef(false);
  previewMovingRef.current = shell.orbiting || previewView?.animation?.playing === true;
  const previewLoadingRef = useRef(false);
  previewLoadingRef.current = previewView?.complete === false;
  useEffect(() => {
    if (!previewing) return undefined;
    let quiet = 0, done = false, capped = false;
    const finish = () => { if (done) return; done = true; setPreviewSettled(true); };
    // Published components still streaming (a model opened cold) is waited for this long, no longer; then the
    // picture on screen converges, and the cover lifts on it, or at the last at FINISH more.
    const cap = setTimeout(() => { capped = true; settle(0); }, PREVIEW_COVER_MAX_MS);
    const last = setTimeout(finish, PREVIEW_COVER_MAX_MS + PREVIEW_COVER_FINISH_MS);
    const settle = (delay = PREVIEW_COVER_QUIET_MS) => {
      clearTimeout(quiet);
      quiet = setTimeout(() => {
        const step = previewCoverStep({ presented: previewPresentedRef.current, loading: previewLoadingRef.current && !capped, moving: previewMovingRef.current,
          progress: previewViewRef.current?.pictureProgress?.() ?? null });
        if (step === "wait") settle();
        else if (step === "converge") settle(PREVIEW_COVER_CONVERGE_MS);
        else finish();
      }, delay);
    };
    settle(PREVIEW_COVER_MIN_MS);
    return () => { done = true; clearTimeout(cap); clearTimeout(last); clearTimeout(quiet); };
  }, [previewing]);
  // The routine the Animation section plays: the tools view's, or in Preview its own.
  const animation = previewing ? previewView?.animation ?? null : frame.animation;
  const hasAnimation = animationControlsHaveContent(animation);
  // Speed and Loop, once chosen in the Animation section's Playback settings, are the file's, and what its
  // routines play with, whatever they authored, until they are chosen again. Unset, the routine's own apply.
  const { speed: chosenSpeed, loop: chosenLoop } = shell.playback;
  const controls = useControlUsage();
  const animationRef = useRef(animation);
  animationRef.current = animation;
  useEffect(() => {
    const runtime = animationRef.current;
    if (!animationControlsHaveContent(runtime)) return;
    if (chosenSpeed != null && Number(runtime.speed) !== chosenSpeed) runtime.onSpeedChange(chosenSpeed);
    if (chosenLoop != null && (runtime.loopEnabled !== false) !== chosenLoop) runtime.onLoopToggle(chosenLoop);
  }, [previewing, hasAnimation, animation?.speed, animation?.loopEnabled, animation?.activeClipId, chosenSpeed, chosenLoop]);
  // Preview opens at rest, its routine started only by Autoplay.
  const autoplayRef = useRef(shell.autoplay);
  autoplayRef.current = shell.autoplay;
  useEffect(() => {
    const runtime = animationRef.current;
    if (previewing && autoplayRef.current && animationControlsHaveContent(runtime) && !runtime.playing) runtime.onPlayToggle();
  }, [previewing, hasAnimation]);
  // What those settings change is the file's, and applied to its routine at once.
  // The person's presses on them are counted (`usage/controls.js`); the shell's own, above, are not.
  const playbackRuntime = hasAnimation ? {
    ...animation,
    onPlayToggle: (...args) => { controls.used("animation_play"); return animation.onPlayToggle?.(...args); },
    onClipSelect: (...args) => { controls.used("animation_clip"); return animation.onClipSelect?.(...args); },
    onRelease: (...args) => { controls.used("animation_release"); return animation.onRelease?.(...args); },
    onSpeedChange: value => { controls.used("animation_speed"); shell.setPlayback({ speed: value }); animation.onSpeedChange(value); },
    onLoopToggle: value => { controls.used("animation_loop"); shell.setPlayback({ loop: value }); animation.onLoopToggle(value); }
  } : null;
  // Preview opens still: its Orbit tile starts the camera turning, and a second press stops it.
  const orbitPlaying = shell.orbiting;
  // Under Select, what the pointer rests on is lit as a part is: the annotation's mark (and the marks
  // drawn with it) or the renderer's overlay, and the part under it is not.
  const [hoveredAnnotation, setHoveredAnnotation] = useState(null);
  const overSelectable = useRef(false);
  // The ink a press under Select last picked, and the ink picked before it: a double-click on it
  // puts that back, as it selects nothing.
  const inkPress = useRef(null);
  // The pointer cursor over them, as a renderer shows over a part.
  const [pointing, setPointing] = useState(false);
  const selectHover = useRef(onSelectHover);
  selectHover.current = onSelectHover;
  const leaveSelectHover = () => {
    overSelectable.current = false;
    setPointing(false);
    selectHover.current?.(null);
    setHoveredAnnotation(current => (current ? null : current));
  };
  useEffect(() => { if (!frame.selecting) leaveSelectHover(); }, [frame.selecting]);
  const hoverSelectable = event => {
    if (!frame.selecting || event.buttons !== 0 || !(event.target instanceof Element) || !event.target.closest("canvas")) {
      if (overSelectable.current || hoveredAnnotation) leaveSelectHover();
      return;
    }
    const session = frame.annotation;
    const overlay = Boolean(selectHover.current?.(event));
    const id = !overlay && selectsAnnotations && session.items.length ? frame.viewerRef.current?.annotationAt?.(event.clientX, event.clientY, event.pointerType) : null;
    const ids = id ? withGroups([id], session.items) : null;
    setHoveredAnnotation(current => (ids && current && current.join() === ids.join()) || (!ids && !current) ? current : ids);
    const over = overlay || Boolean(id);
    if (over && !overSelectable.current) {
      // The part lit under the pointer lets go, as when the pointer leaves the model.
      for (let node = event.target; node && node !== event.currentTarget; node = node.parentElement) {
        node.dispatchEvent(new PointerEvent("pointerleave", { bubbles: false, pointerId: event.pointerId, pointerType: event.pointerType }));
      }
    }
    overSelectable.current = over;
    setPointing(over);
    // Over a mark or a measurement the part under it hears nothing of the pointer.
    if (over) event.stopPropagation();
  };
  useEffect(() => { setPreviewing(false); }, [frame.modelKey, setPreviewing]);
  // Preview is a view of its own (`PreviewView.jsx`): it opens on the model as authored, in Render,
  // still, its routine at rest and started only by Autoplay, and leaving it takes it away.
  const enterPreview = () => {
    setCoverRequested(true);
    // After the frame the cover is painted in (a hidden page paints none: a timer stands in).
    let entered = false;
    const enter = () => { if (!entered) { entered = true; setPreviewing(true); } };
    requestAnimationFrame(() => setTimeout(enter, 0));
    setTimeout(enter, 100);
  };
  const leavePreview = () => setPreviewing(false);
  // Preview's bar names what it shows: the file's name, or its path's last part.
  const previewName = view.file?.name || String(view.file?.path ?? "").split("/").pop() || "";
  // While Preview is up the host's chrome steps aside (FileViewer's navbar): said as it opens, and as
  // it closes or the view goes.
  // Preview's bar and its playbar, shown and gone together while the pointer rests; its settings open hold them.
  const previewIdle = usePreviewIdle(frame.hostElement, previewing, previewPanelOpen);
  const onPreviewChange = view.onPreviewChange;
  useEffect(() => {
    if (!previewing || !onPreviewChange) return undefined;
    onPreviewChange(true);
    return () => onPreviewChange(false);
  }, [previewing, onPreviewChange]);
  // The drawing tools' sub-toolbar, one row under the strip while Pencil or Shapes is the tool: what it draws with, what the next mark
  // looks like, and Undo, Redo and Clear (`annotation/toolbar.jsx`). The annotation itself has no
  // panel: it is Quick Edit's chip (its X clears it, a click copies it).
  const colorScheme = view.appearance?.colorScheme === "dark" ? "dark" : "light";
  // Otherwise the renderer supplies its active tool's row.
  const toolRow = frame.annotateToolActive
    ? <AnnotationToolbar annotation={frame.annotation} colorScheme={colorScheme} />
    : subToolbar;

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
  const toolsHidden = chromeHidden || compact;
  // The view's panel (`FlatPanel.jsx`, placed by the frame): docked at the left, its tabs the renderer's
  // sections, one state with every view's; none on a phone; Preview keeps it mounted out of sight.
  const panel = sidebar ? { kind: "model", label: t("flatPanel.modelPanel"), searchLabel: t("flatPanel.searchModel"), sections: sidebar } : null;
  // Display's tile is its mode's sphere; on a phone with no room for it, its More row shows the same.
  const DisplayIcon = (frame.displayMode?.options?.find(option => option.value === frame.displayMode.value) || frame.displayMode?.options?.[0])?.Icon;
  const copyAction = () => {
    if (previewing) return false;
    if (frame.annotateToolActive) { frame.copyAnnotation(); return true; }
    if (copySelection) { copySelection(); return true; }
    return false;
  };
  frame.copyActionRef.current = copyAction;
  // Quick Edit's X: nothing picked and nothing drawn, as the person would clear each.
  const clearQuickEdit = () => { onClearReferences?.(); onClearRequests?.(); if (frame.annotation.hasAnnotation) frame.annotation.forget(); };
  const forgetAnnotation = frame.annotation.forget;
  // Quick Edit's annotation: while Annotate is up or there is ink. The annotation goes with a note whenever
  // there is one (its views and annotation file, `frame.quickEditPrompt`); its Annotation chip's X wipes it.
  const annotation = useMemo(() => frame.annotateToolActive || frame.annotation.hasAnnotation
    ? { present: frame.annotation.hasAnnotation, clear: forgetAnnotation } : null,
  [frame.annotateToolActive, frame.annotation.hasAnnotation, forgetAnnotation]);
  // The renderer's overlay and the shell's own layers share one viewport context.
  // The view's zoom (`ZoomControl.jsx`'s `ViewZoom`): the viewport's zoom against the authored box, read live,
  // for the keys and a phone's More.
  const viewerRef = frame.viewerRef;
  // A model's viewport, once it is up: its camera is the one the readout follows.
  const zoomBase = useMemo(() => viewportZoom(viewerRef), [viewerRef, scene, viewerLoading]);
  const zoom = { ...zoomBase, zoomToSelection: zoomToSelection?.run || null, selectionAvailable: Boolean(zoomToSelection?.available) };
  // What the zoom's keys reach (`useRendererShell`'s `zoom`): the zoom as the strip has it now.
  frame.zoomKeys.current = zoom;
  const overlay = viewport => <>
    {previewing || !contextMenuItems ? null : <ViewportContextMenu viewport={viewport} items={contextMenuItems} onOpenChange={onContextMenuOpenChange} />}
    {previewing || !doubleClickFits ? null : <DoubleClickFit viewport={viewport} scene={scene} viewerRef={frame.viewerRef} />}
    {/* The ink Select has picked, its bar: restyle, fill, delete. */}
    {frame.selecting && frame.annotation.selected.length ? <AnnotationSelectionBar annotation={frame.annotation} colorScheme={colorScheme} runtimeRef={viewport.runtimeRef}
      viewerReadyTick={viewport.viewerReadyTick} onDelete={frame.deletePicked} disabled={viewerLoading || !scene} /> : null}
    {typeof viewportOverlay === "function" ? viewportOverlay(viewport) : viewportOverlay}
  </>;
  // One place says the view is catching up: a newer revision of the file loading behind the model on
  // screen, or a Display change being prepared — the latter's failure first, since it is the one with
  // something to retry. Under the strip at the top centre, or in its place where there is no strip.
  const updateStatus = { preview: Boolean(frame.loading.preview), onRetry: frame.viewUpdate.retry,
    update: frame.loading.updating && !frame.viewUpdate.status.error ? modelUpdateStatus(frame.loading.progress) : frame.viewUpdate.status };
  const quickEdit = references ? <QuickEdit key={frame.modelKey} className="self-stretch" hidden={chromeHidden} docked={mobile}
    resource={frame.resource} references={references} chips={referenceChips} nameReference={nameReference} annotation={annotation} requests={requests} prompt={frame.quickEditPrompt}
    onCopy={copyAction} onEscape={frame.escape} onClear={clearQuickEdit} disabled={viewerLoading || !scene} /> : null;
  // The corner (`ViewCorner.jsx`): the cube, the viewport's, and Home, a ghost button at its upper-left.
  const corner = failed || !shell.previewable ? null : <ViewHome onHome={() => frame.viewerRef.current?.goHome?.()} disabled={shell.idle} />;
  // The view's own controls end the strip, after its rule: Projection (the state button), Display (its menu),
  // then Preview. A phone has no room for them on its strip: they are rows of its More, with the zoom.
  const views = shell.previewable && !previewing ? [
    { id: "projection", label: t("projection.label"), icon: <ProjectionIcon value={frame.projection.value} />, disabled: shell.idle,
      tile: <ProjectionToggle disabled={shell.idle} projection={frame.projection} />,
      // In a phone's More, a row that switches it the same way.
      onSelect: () => frame.projection.onChange(otherProjection(frame.projection.value)) },
    { id: "display", label: t("display.label"), icon: DisplayIcon ? <DisplayIcon /> : null, disabled: shell.idle,
      tile: <DisplayPopover disabled={shell.idle} boundary={frame.hostElement} mode={frame.displayMode} grid={frame.grid} />,
      // In a phone's More, the same list opened under its row, in More itself (`FloatingToolBar.js`'s TouchStrip):
      // the modes, then Grid.
      submenu: () => <DisplayMenuItems mode={frame.displayMode} grid={frame.grid} /> },
    ...(mobile ? [zoomViewControl(zoom, { t, disabled: shell.idle })] : []),
    { id: "preview", label: t("preview.label"), icon: <Play aria-hidden="true" />, disabled: shell.idle, onSelect: enterPreview,
      tile: <ViewControl label={t("preview.label")} disabled={shell.idle} onClick={enterPreview}><Play aria-hidden="true" /></ViewControl> }
  ] : [];
  // Under Select a press on the canvas picks, front to back: the renderer's own overlays (a
  // measurement), then the annotation's mark (and the marks drawn with it), then a part. Shift adds or
  // takes away; a press that picks one kind lets go of the others, unless Shift keeps them.
  const pressCanvas = event => {
    onCanvasPointerDown?.(event);
    if (!frame.selecting || event.button !== 0) return;
    const session = frame.annotation;
    if (onSelectPress?.(event)) {
      event.stopPropagation();
      event.preventDefault();
      if (!event.shiftKey && session.selected.length) session.select([]);
      return;
    }
    const id = selectsAnnotations && session.items.length ? frame.viewerRef.current?.annotationAt?.(event.clientX, event.clientY, event.pointerType) : null;
    if (!id) { if (!event.shiftKey && session.selected.length) session.select([]); return; }
    event.stopPropagation();
    event.preventDefault();
    // The second press of a double-click keeps what the first found.
    const again = inkPress.current?.id === id && event.timeStamp - inkPress.current.at < DOUBLE_PRESS_MS;
    inkPress.current = { id, before: again ? inkPress.current.before : session.selected, at: event.timeStamp };
    const picked = event.shiftKey
      ? (session.selected.includes(id) ? session.selected.filter(other => other !== id) : [...session.selected, id])
      : [id];
    if (!event.shiftKey) onClearReferences?.();
    session.select(withGroups(picked, session.items));
  };
  const rootHandlers = {
    // Under Select a double-click on ink turns the view square to it (`ShellViewport.jsx`'s
    // `lookAtAnnotation`), as one on a face or edge does, and selects nothing: the ink picked is as
    // its first click found it. Never on to the part under it.
    onDoubleClickCapture: event => {
      if (!frame.selecting || !selectsAnnotations || !frame.annotation.items.length) return;
      if (!(event.target instanceof Element) || !event.target.closest("canvas")) return;
      const id = frame.viewerRef.current?.annotationAt?.(event.clientX, event.clientY, event.nativeEvent?.pointerType || "");
      if (!id) return;
      event.stopPropagation();
      event.preventDefault();
      if (inkPress.current?.id === id) frame.annotation.select(inkPress.current.before);
      inkPress.current = null;
      frame.viewerRef.current?.lookAtAnnotation?.(id);
    },
    onPointerMoveCapture: hoverSelectable,
    onPointerLeave: () => { if (overSelectable.current || hoveredAnnotation) leaveSelectHover(); }
  };
  // Preview: the tools put away and the host's navbar too (FileViewer hides it while
  // `view.onPreviewChange` says Preview is up), the model in Render — the tools view never is — and
  // still until Orbit is turned on. In the navbar's place, Preview's own bar over the view's top edge,
  // on no surface, gone while the pointer rests (`PreviewChrome`): the file's name, and at its right its
  // settings (a toggle, the panel docked under it at the view's right edge: Orbit, Render's own), closed
  // as it opens, and the way out. The same in every host.
  const preview = { active: previewing, name: previewName, idle: previewIdle, panelOpen: previewPanelOpen,
    controls: <>
      <BarControl label={t("preview.settings")} active={previewPanelOpen} disabled={shell.idle}
        onClick={() => { if (!previewPanelOpen) controls.used("preview_settings"); setPreviewPanelOpen(open => !open); }} data-preview-settings=""><SlidersHorizontal className="size-3.5" aria-hidden="true" /></BarControl>
      <BarControl label={t("preview.exit")} onClick={leavePreview}><X className="size-3.5" aria-hidden="true" /></BarControl>
    </>,
    panel: <PreviewSettings orbit={orbitPlaying} onOrbitChange={shell.setOrbiting}
      speed={frame.previewOrbitSpeed || 1} onSpeedChange={frame.setPreviewOrbitSpeed}
      onClose={() => setPreviewPanelOpen(false)} render={frame.previewSettings} /> };
  const body = (
    <ViewFrame rootRef={frame.hostRef} className={pointing ? "cursor-pointer" : ""} rootHandlers={rootHandlers} onCanvasPress={pressCanvas} selecting={frame.selecting}
      inspect={inspect}
      stageColor={frame.stageColor} file={frame.modelKey} mobile={mobile} compact={compact} chromeHidden={chromeHidden} previewing={previewing}
      preview={preview} tools={tools} views={views} toolRow={toolRow} status={updateStatus}
      toolStack={<ToolStack hidden={previewing} layout={frame.toolStack} onLayoutChange={frame.changeToolStack}>{toolPanels}</ToolStack>}
      panel={panel} panelControl={frame.panelControl} layout={frame.toolStack} onLayoutChange={frame.changeToolStack}
      corner={corner} notice={view.notice} quickEdit={quickEdit}
      // Preview: a view of its own over the editor's, mounted while it is open.
      underlay={previewing && previewView ? <div className="pointer-events-auto absolute inset-0 z-[1]" data-preview-view="">
        <PreviewView view={previewView} desired={frame.previewDesiredScene} modelKey={frame.modelKey}
          sceneScaleMode={frame.sceneScaleMode} viewRef={previewViewRef} onPresented={setPreviewPresented}
          orbit={orbitPlaying} orbitSpeed={frame.previewOrbitSpeed ?? 1} />
      </div> : null}
      // A file with routines: its playbar under the model, in the tools view as in Preview (the same
      // transparent row, with Reset first, and on a phone over Quick Edit's peek), Preview's its own routine.
      bottomCentre={<>
        {!previewing && !toolsHidden && hasAnimation ? <PreviewPlaybar key={`tools-${frame.modelKey}`} runtime={playbackRuntime} disabled={viewerLoading || !scene}
          autoplay={shell.autoplay} onAutoplayChange={shell.setAutoplay} toolsView phone={mobile} /> : null}
        {previewing && hasAnimation ? <PreviewPlaybar key={frame.modelKey} runtime={playbackRuntime} disabled={viewerLoading || !scene}
          autoplay={shell.autoplay} onAutoplayChange={shell.setAutoplay} idle={previewIdle} /> : null}
      </>}
      // Preview coming together underneath: the view as it was, held, until the picture is ready.
      overlays={<div aria-hidden={!previewCovered} data-preview-cover={previewCovered ? "" : undefined}
        className={cn("absolute inset-0 z-40 flex items-center justify-center",
          // At once over the press, so nothing of preview shows first; it fades only as it lifts.
          previewCovered ? "pointer-events-auto opacity-100" : "pointer-events-none opacity-0 transition-opacity duration-300 motion-reduce:transition-none")}
        style={{ backgroundColor: frame.stageColor }}>
        {previewCovered ? <span role="status" className="flex items-center gap-2 text-tiny text-muted-foreground">
          <LoaderCircle className="size-3.5 animate-spin" aria-hidden="true" />{t("preview.preparing")}
        </span> : null}
      </div>}
      loading={frame.presentationState?.file === frame.modelKey && frame.presentationState?.covering ? null : frame.loading}
      // The card: the file as the alert names it (the catalog's absolute path), which Report Issue keeps out of its issue.
      alert={{ alert: frame.viewerAlert, hasContent, dismissed: alertDismissal.dismissed, onDismiss: alertDismissal.dismiss,
        onReload: view.reload, file: frame.modelKey || view.file?.path }}>
      {/* The canvas is clipped to the stage; the strip is not, so it reaches over the docked panel. Its
          box's background is the scene's edge colour (the stage's): the scene is resized on the next
          frame, and one frame of another colour above a dark stage is a visible band. */}
      <div className="pointer-events-auto absolute inset-0 z-0 overflow-hidden">
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
            displaySettings={resolvedScene.display}
            sceneEffects={frame.sceneEffects}
            appearance={resolvedScene.appearance}
            receiveShadows={resolvedScene.view.lighting.enabled}
            renderMode={resolvedScene.render.enabled}
            renderConfiguration={resolvedScene.render.configuration}
            quality={resolvedScene.quality}
            // Under Preview the editor draws nothing; it draws what it owes as Preview goes.
            suspended={previewing}
            isLoading={viewerLoading}
            viewCube={!compact && !failed && !mobile}
            viewUpdate={frame.viewUpdate}
            loadingPresentation={frame.loading}
            annotationEnabled={frame.annotateToolActive}
            annotation={frame.annotation}
            hoveredAnnotation={hoveredAnnotation}
            annotationView={frame.currentView}
            annotationTouches={inkTouches}
            onPerspectiveChange={frame.handlePerspectiveChange}
            onPresentationChange={frame.handlePresentationChange}
            onViewerAlertChange={frame.setRuntimeAlert}
            onCameraSettled={frame.onCameraSettled}
            preserveInteractionPixelRatio={frame.preserveInteractionPixelRatio}
            runtimeLifecycle={frame.runtimeLifecycle}
          >{overlay}</ShellViewport>
        </div>
      </div>
    </ViewFrame>
  );
  return frameProvider ? frameProvider(body) : body;
}
