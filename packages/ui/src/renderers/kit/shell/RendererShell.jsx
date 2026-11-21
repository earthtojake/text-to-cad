import { useEffect, useMemo, useRef, useState } from "react";
import { useI18n } from "@cad/ui/i18n";
import { useViewerMobile } from "../../../file-viewer/responsive.js";
import { alertDismissible, useAlertDismissal } from "../status/ViewerAlertCard.jsx";
import { modelUpdateStatus } from "../status/ViewUpdateStatus.jsx";
import { viewportZoom, zoomViewControl } from "./ZoomControl.jsx";
import { withGroups } from "../../../annotation/geometry.js";
import { BoxSelectGesture } from "../tools/select/useBoxSelectGesture.js";
import { takeInkInBox } from "../tools/select/boxTake.js";
import { AnnotationToolbar } from "../../../annotation/toolbar.jsx";
import ToolStack from "../tools/ToolStack.jsx";
import PreviewPlaybar from "../tools/playbar/PreviewPlaybar.jsx";
import AnimationSection from "../tools/playbar/AnimationSection.jsx";
import { DisplayMenuItems } from "./DisplayPopover.jsx";
import { OrthographicProjectionIcon, PerspectiveProjectionIcon } from "../camera/ProjectionModeIcons.js";
import NavbarViewControls, { useNavbarViewControls } from "./NavbarViewControls.jsx";
import { StripViewMenu, ViewMenu, viewGroups3d, viewIcon } from "./ViewSettingsMenu.jsx";
import { animationControlsHaveContent } from "../tools/playbar/AnimationTimeControl.js";
import QuickEdit from "../tools/quick-edit/QuickEdit.jsx";
import ShellViewport from "./ShellViewport.jsx";
import PreviewView from "./PreviewView.jsx";
import { usePreviewFrame } from "./usePreviewFrame.jsx";
import ViewportContextMenu from "./ViewportContextMenu.jsx";
import DoubleClickFit from "./DoubleClickFit.jsx";
import AnnotationSelectionBar from "../tools/annotate/AnnotationSelectionBar.jsx";
import ViewFrame from "./ViewFrame.jsx";
import { useControlUsage } from "../../../usage/controls.js";

// The projection on screen, as an icon (a row of a phone's More, where the host has no navbar).
function ProjectionIcon({ value }) {
  const Icon = value === "perspective" ? PerspectiveProjectionIcon : OrthographicProjectionIcon;
  return <Icon />;
}

// Two presses on the same ink this close together are one double-click.
const DOUBLE_PRESS_MS = 600;

/**
 * A 3D view's frame: every view's one frame (`ViewFrame.jsx`: the root, the docked panel, the strip
 * at the centre of the whole view, the top-right, the corner, the cards) with what a 3D view puts in
 * it — its viewport (`ShellViewport`) as the canvas, Preview's frame (`usePreviewFrame.jsx`: Preview's view over it,
 * its cover, its bar and its button), for a file with routines its panel's Animation tab
 * (`AnimationSection.jsx`; no playbar under the model), the
 * tool stack, and Preview's own chrome (its playbar among it); its corner is the viewport's cube alone (the view's
 * settings are View's, in the navbar beside Preview). The same
 * structure, classes and data attributes for every renderer: hosts, stylesheets and tests key on
 * them. The toolbar is for using tools, the sidebar for reading the file: a tool's own controls are
 * panels in the tool stack, shown by the tool they belong to; what there is to read of the file (a
 * tree, parameters, joints, routines) is the sidebar's tabs, whatever the tool.
 *
 * @param {{ shell: ReturnType<typeof import("./useRendererShell.js").useRendererShell>,
 *   tools: import("../tools/FloatingToolBar.js").ViewportTool[],
 *   toolPanels?: import("react").ReactNode, sidebar?: import("react").ReactNode,
 *   references?: readonly import("@cad/core/prompt").PromptReference[],
 *   referenceChips?: readonly import("../tools/quick-edit/ReferenceChips.jsx").ReferenceChip[] | null,
 *   nameReference?: ((reference: import("@cad/core/prompt").PromptReference) => string | import("../inspector/pickGlyph.jsx").CompactName) | null,
 *   promptNotes?: { take(): { text: string, done(): void, cancel?(): void } | null } | null,
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
 *   `sidebar`: the file's structure, in order — each a `ToolPanel`, drawn as a tab of the panel
 *   (`FlatPanel.jsx`): a tree, links, metadata, first.
 *   `fileSections`: the file's own settings — each a `ToolPanel`, drawn as a tab of the panel after the structure's:
 *   Parameters, Joints (the shell's Animation after them).
 *   `inspect`: what is picked and how the renderer describes it (`inspector/inspect.js`): the hover tip under Select
 *   and the frame's name for its marks.
 *   Gone in preview, kept mounted, so a tree keeps its expansion and scroll.
 *   `referenceChips`: the renderer's description of that selection, as Quick Edit shows it (its
 *   chips, `kit/tools/quick-edit/ReferenceChips.jsx`): a chip each for one or several picks of a kind
 *   on one part, its card, its hover and its removal. Without them Quick Edit counts the references.
 *   `nameReference`: what the renderer calls a reference into its file, for a reference pasted
 *   into Quick Edit's note ("cam"); "" for one it cannot name.
 *   `promptNotes`: what the renderer has to tell the agent with the next Quick Edit, said once
 *   (`{ take() }`, Quick Edit's `notes`).
 *   `references`: what is selected, in the prompt grammar — the references a Quick Edit attaches
 *   (`kit/tools/quick-edit/QuickEdit.jsx`), counted in its header; the file itself always goes. A
 *   renderer that hands none has no Quick Edit: only a view whose picks and annotations a note can
 *   carry offers one. `onClearReferences`: the renderer's clear of that selection, as a press on the
 *   background makes it; a note that has gone (Queue, Send) calls it, and clears Annotate's ink too.
 *   Quick Edit's X only puts the bar away, the selection kept.
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
 *   `boxSelect`: `{ enabled, onBox(box), mayStart?(event) }`, a renderer's Box select
 *   (`kit/tools/select/useBoxSelectGesture.js`). While Select is up and `enabled`, a drag that starts on
 *   empty space draws a box -- not on the annotation's ink (the shell's own test) nor wherever the
 *   renderer's `mayStart` says no (the model, a measurement): a drag from there is Select's, the camera's
 *   -- and its release takes the annotation's ink it touches (`selectsAnnotations`; with what was drawn
 *   with it), then hands the box to `onBox` for what is the renderer's own: the model and its overlays
 *   (a measurement, `measureSelectHandlers`' `box`). Shift adds to each; otherwise the box replaces
 *   each, the ink included, so parts, measurements and ink one box takes stay picked together
 *   (`kit/tools/select/boxTake.js`). Without it, no box.
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
// The update status with nothing to say (`ViewUpdateStatus`'s).
const NO_UPDATE = Object.freeze({ pending: false, error: null });

export default function RendererShell({ shell, tools, toolPanels = null, subToolbar = null, sidebar = null, fileSections = null, references = null, referenceChips = null, nameReference = null, onClearReferences = null, copySelection = null, contextMenuItems = null,
  onContextMenuOpenChange = null, viewportOverlay = null, previewView = null,
  frameProvider = null, onCanvasPointerDown = null, onSelectPress = null, onSelectHover = null, selectsAnnotations = true, boxSelect = null, inkTouches = null,
  doubleClickFits = true, zoomToSelection = null, inspect = null, promptNotes = null }) {
  const { t } = useI18n();
  const frame = shell.frame;
  // What a tool's letter takes up (`useRendererShell`'s `onKey`): the strip as drawn now.
  frame.toolKeys.current = tools;
  const mobile = useViewerMobile();
  const { view, resolvedScene, viewerLoading, scene } = frame;
  // The one presentation state: every gate — the viewport's, the renderer's — reads it.
  const { previewing, setPreviewing } = shell;
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
  const counted = animation => (animationControlsHaveContent(animation) ? {
    ...animation,
    onPlayToggle: (...args) => { controls.used("animation_play"); return animation.onPlayToggle?.(...args); },
    onClipSelect: (...args) => { controls.used("animation_clip"); return animation.onClipSelect?.(...args); },
    onRelease: (...args) => { controls.used("animation_release"); return animation.onRelease?.(...args); },
    onSpeedChange: value => { controls.used("animation_speed"); shell.setPlayback({ speed: value }); animation.onSpeedChange(value); },
    onLoopToggle: value => { controls.used("animation_loop"); shell.setPlayback({ loop: value }); animation.onLoopToggle(value); },
    // The tools view's playbar's menu: a routine chosen there plays from its start (one use, the choice).
    playClip: id => { controls.used("animation_clip"); animation.onClipSelect?.(id); animation.onPlayToggle?.(); }
  } : null);
  const playbackRuntime = counted(animation);
  // The Animation tab's: the tools view's routine, kept mounted (out of sight) through Preview, so the tab stays the panel's.
  const toolsRuntime = previewing ? counted(frame.animation) : playbackRuntime;
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
  // The view's settings as View draws them (`ViewSettingsMenu.jsx`), and the cube its button wears: Preview settings' too.
  const viewGroups = viewGroups3d({ mode: frame.displayMode, projection: frame.projection, grid: frame.grid, background: frame.background, t, used: controls.used });
  // Preview's frame (`usePreviewFrame.jsx`): its cover, entering and leaving it, the host's navbar stepping aside, its
  // bar and settings panel, its view over the editor's (`PreviewView.jsx`) and its button. What moves its picture on
  // purpose is its Orbit, or its routine playing.
  const previewFrame = usePreviewFrame({ previewing, setPreviewing, modelKey: frame.modelKey, fileView: view, hostElement: frame.hostElement,
    stageColor: frame.stageColor, viewportScheme: frame.viewport.scheme, View: PreviewView, view: previewView, desired: frame.previewDesiredScene,
    sceneScaleMode: frame.sceneScaleMode, viewRef: frame.previewViewRef, moving: shell.orbiting || previewView?.animation?.playing === true,
    orbit: orbitPlaying, onOrbitChange: shell.setOrbiting, orbitSpeed: frame.previewOrbitSpeed, onOrbitSpeedChange: frame.setPreviewOrbitSpeed,
    render: frame.previewSettings, disabled: shell.idle, mobile, ViewIcon: viewIcon(viewGroups) });
  const previewIdle = previewFrame.idle, previewScheme = previewFrame.scheme;
  // The drawing tools' sub-toolbar, one row under the strip while Draw is the tool: what it draws with, what the next mark
  // looks like, and Undo, Redo and Clear (`annotation/toolbar.jsx`). The annotation itself has no
  // panel: it is Quick Edit's chip (its X clears it, a click copies it).
  // What is drawn on the model (ink's neutral colour) reads against the viewport, in its scheme, not the app's.
  const colorScheme = frame.viewport.scheme;
  // Otherwise the renderer supplies its active tool's row.
  const toolRow = frame.annotateToolActive
    ? <AnnotationToolbar annotation={frame.annotation} colorScheme={colorScheme} takeFamily={family => shell.selectTool(family)} />
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
  // A file with routines has its Animation tab, last (`AnimationSection.jsx`): the tools view's routine; Preview's is its playbar's.
  const animationTab = toolsRuntime ? <AnimationSection key={`animation-${frame.modelKey}`} runtime={toolsRuntime}
    kind={toolsRuntime.noun === "Motion" ? "motion" : "animation"} disabled={viewerLoading || !scene} autoplay={shell.autoplay} onAutoplayChange={shell.setAutoplay} /> : null;
  // The panel's tabs: the file's structure (`sidebar`), then its own settings (`fileSections`: Parameters, Joints),
  // then Animation, each only where the file has it.
  const panelTabs = sidebar || fileSections || animationTab ? <>{sidebar}{fileSections}{animationTab}</> : null;
  const panel = panelTabs ? { kind: "model", label: t("flatPanel.modelPanel"), searchLabel: t("flatPanel.searchModel"), sections: panelTabs } : null;
  const copyAction = () => {
    if (previewing) return false;
    if (frame.annotateToolActive) { frame.copyAnnotation(); return true; }
    if (copySelection) { copySelection(); return true; }
    return false;
  };
  frame.copyActionRef.current = copyAction;
  // A note gone (Queue, Send): nothing picked and nothing drawn, as the person would clear each.
  const clearQuickEdit = () => { onClearReferences?.(); if (frame.annotation.hasAnnotation) frame.annotation.forget(); };
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
  // Box select's box: the ink it touches, as it takes the model (`annotationsInBox`), then
  // the renderer's own. Shift adds; otherwise the ink picked is what the box took, none if nothing.
  const takeBox = box => {
    const session = frame.annotation;
    const touched = selectsAnnotations && session.items.length ? frame.viewerRef.current?.annotationsInBox?.(box.client) || [] : [];
    takeInkInBox(session, touched, box.additive);
    boxSelect?.onBox?.(box);
  };
  // A drag from the ink is Select's, never a box: the ink is drawn there whatever the filter picks.
  const boxMayStart = event => !(frame.annotation.items.length && frame.viewerRef.current?.annotationAt?.(event.clientX, event.clientY, event.pointerType))
    && (boxSelect?.mayStart ? boxSelect.mayStart(event) : true);
  const overlay = viewport => <>
    {previewing || !contextMenuItems ? null : <ViewportContextMenu viewport={viewport} items={contextMenuItems} onOpenChange={onContextMenuOpenChange} />}
    {previewing || !doubleClickFits ? null : <DoubleClickFit viewport={viewport} scene={scene} viewerRef={frame.viewerRef} />}
    {/* The ink Select has picked, its bar: restyle, fill, delete. */}
    {frame.selecting && frame.annotation.selected.length ? <AnnotationSelectionBar annotation={frame.annotation} colorScheme={colorScheme} runtimeRef={viewport.runtimeRef}
      viewerReadyTick={viewport.viewerReadyTick} onDelete={frame.deletePicked} disabled={viewerLoading || !scene} /> : null}
    {typeof viewportOverlay === "function" ? viewportOverlay(viewport) : viewportOverlay}
    {boxSelect ? <BoxSelectGesture viewport={viewport} enabled={frame.selecting && Boolean(boxSelect.enabled)} onBox={takeBox} mayStart={boxMayStart} /> : null}
  </>;
  // One place says the view is catching up: a newer revision of the file loading behind the model on
  // screen, or a Display change being prepared — the latter's failure first, since it is the one with
  // something to retry. Under the strip at the top centre, or in its place where there is no strip.
  // While the file first loads there is no picture to catch up: the loading cover says what is happening,
  // and the settings the model will open with, waiting for it, are no update (only their failure is said).
  const viewUpdateStatus = viewerLoading && !frame.viewUpdate.status.error ? NO_UPDATE : frame.viewUpdate.status;
  const updateStatus = { preview: Boolean(frame.loading.preview), onRetry: frame.viewUpdate.retry,
    update: frame.loading.updating && !frame.viewUpdate.status.error ? modelUpdateStatus(frame.loading.progress) : viewUpdateStatus };
  const quickEdit = references ? <QuickEdit key={frame.modelKey} className="self-stretch" hidden={chromeHidden} docked={mobile}
    resource={frame.resource} references={references} chips={referenceChips} nameReference={nameReference} annotation={annotation} prompt={frame.quickEditPrompt}
    notes={promptNotes} onCopy={copyAction} onEscape={frame.escape} onClear={clearQuickEdit} disabled={viewerLoading || !scene} /> : null;
  // The view's own controls: **View** (`ViewSettingsMenu.jsx`: Projection, Display, Background, Show grid, then Reset
  // view, what Home was) and **Preview**, a play triangle, in that order: the file's navbar's right end, a phone's too;
  // in a host's inline card (no navbar) the strip's end, and on a phone rows of its More with the zoom. The picture's
  // corner is the cube alone.
  // Reset view: the view the file opened with, framed whole from the opening direction, eased (`ShellViewport.jsx`'s
  // `goHome`), counted as Home always was (`view_home`).
  const goHome = () => { controls.used("view_home"); frame.viewerRef.current?.goHome?.(); };
  const inNavbar = useNavbarViewControls();
  // Display's mode on screen, as its More row's icon on a phone with no navbar.
  const DisplayIcon = (frame.displayMode?.options?.find(option => option.value === frame.displayMode.value) || frame.displayMode?.options?.[0])?.Icon;
  const viewControls = shell.previewable && !previewing;
  const viewSettings = viewControls && inNavbar ? <NavbarViewControls>
    <ViewMenu groups={viewGroups} onReset={goHome} disabled={shell.idle} boundary={frame.hostElement} />
    {previewFrame.navbarButton}
  </NavbarViewControls> : null;
  const views = viewControls && !inNavbar ? [
    ...(mobile ? [
      // A phone's More has no room for a menu of submenus: Projection a row that switches it, Display's list (its modes,
      // Show grid and the Background) under its row, then the zoom.
      { id: "projection", label: t("projection.label"), icon: <ProjectionIcon value={frame.projection.value} />, disabled: shell.idle,
        onSelect: () => frame.projection.onChange(frame.projection.value === "perspective" ? "orthographic" : "perspective") },
      { id: "display", label: t("display.label"), icon: DisplayIcon ? <DisplayIcon /> : null, disabled: shell.idle,
        submenu: () => <DisplayMenuItems mode={frame.displayMode} grid={frame.grid} background={frame.background} /> },
      zoomViewControl(zoom, { t, disabled: shell.idle })
    ] : [{ id: "view", label: t("view.menu"), tile: <StripViewMenu groups={viewGroups} onReset={goHome} disabled={shell.idle} boundary={frame.hostElement} /> }]),
    previewFrame.stripView
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
  const body = (
    <ViewFrame rootRef={frame.hostRef} className={pointing ? "cursor-pointer" : ""} rootHandlers={rootHandlers} onCanvasPress={pressCanvas} selecting={frame.selecting}
      inspect={inspect}
      stageColor={frame.stageColor} viewport={frame.viewport} file={frame.modelKey} mobile={mobile} compact={compact} chromeHidden={chromeHidden} failed={failed} {...previewFrame.frame}
      tools={tools} views={views} toolRow={toolRow} status={updateStatus}
      toolStack={<ToolStack hidden={previewing} layout={frame.toolStack} onLayoutChange={frame.changeToolStack}>{toolPanels}</ToolStack>}
      panel={panel} panelControl={frame.panelControl} layout={frame.toolStack} onLayoutChange={frame.changeToolStack}
      notice={view.notice} quickEdit={quickEdit} navbar={viewSettings}
      // A file with routines: in the tools view, its Animation tab (above), no playbar; in Preview, Preview's
      // playbar, its own routine.
      bottomCentre={<>
        {previewing && hasAnimation ? <PreviewPlaybar key={frame.modelKey} runtime={playbackRuntime} disabled={viewerLoading || !scene}
          autoplay={shell.autoplay} onAutoplayChange={shell.setAutoplay} idle={previewIdle} scheme={previewScheme} /> : null}
      </>}
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
