import { useCallback, useContext, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { useI18n } from "@cad/ui/i18n";
import { cn } from "@cad/ui/utils";
import { PANEL_SHEET_LEFT_CLASS } from "../../../file-viewer/panelPeek.js";
import ViewerAlertCard from "../status/ViewerAlertCard.jsx";
import ViewerLoadingOverlay from "../status/ViewerLoadingOverlay.js";
import { ViewPreviewLabel, ViewUpdateStatus } from "../status/ViewUpdateStatus.jsx";
import FloatingToolBar, { StripTouchProvider } from "../tools/FloatingToolBar.js";
import PreviewChrome from "../tools/PreviewChrome.jsx";
import { ToolbarTooltipScope } from "@cad/ui/primitives/toolbar-button";
import { InspectContext } from "../inspector/inspect.js";
import FlatPanel, { flatPanelShortcut, useFlatPanelState } from "./FlatPanel.jsx";
import HoverTip, { useFrameHoverTip } from "./HoverTip.jsx";
import { usePanelToggles } from "../../../file-viewer/panelToggles.js";
import { ViewerElementContext, ViewerHostContext } from "../../../host/context.js";
import { Sheet, SheetContent, SheetTitle } from "@cad/ui/primitives/sheet";
import { usePhoneSheetPlace } from "./usePhoneSheetPlace.js";
import { sidebarLayout, toggleSidebar } from "./sidebars.js";
import { PanelPeekContext, usePanelPeek } from "./usePanelPeek.js";
import { useTouchGestures } from "../viewport/touchGestures.js";
import { hasOpenPopup } from "../../../lib/popups.js";
import { ViewCornerSideProvider, viewCornerSide } from "./ViewCorner.jsx";
import ViewportContextMenu from "./ViewportContextMenu.jsx";
import { ViewportTopRight } from "./ViewportTopRight.jsx";
import { SETTINGS_CARD_GAP_PX, SETTINGS_CARD_LAYER_CLASS, SettingsCardDock } from "../view-settings/SettingsCard.jsx";
import { VIEWPORT_INSET_PX, VIEWPORT_STACK_BOTTOM, VIEWPORT_TOP_BAR_PX } from "./viewportLayout.js";

/**
 * The ONE frame every view is drawn in, 2D or 3D: the canvas is the only thing a renderer brings
 * that differs (`children`); everything round it is this, so the strip, the panel, the corner and the
 * cards stand in one place and behave one way in every renderer. `RendererShell.jsx` (a 3D view) and
 * `FlatViewFrame.jsx` (a picture drawn flat) mount it; nothing else draws the frame's parts.
 *
 * - **The panel** (`sidebars.js`), the one sidebar, at the left (`FlatPanel.jsx`, `panel`; its width and tab the
 *   file's, `filePanel.js`): the file's structure, then the file's own settings (Parameters, Joints, Animation), as
 *   its tabs. Open, it always pushes the model aside (a view that would leave the model under 640px beside it starts it collapsed, unwritten:
 *   `sidebars.js`); ⌘\ (Ctrl+\) toggles it (`panelControl`). Its toggle is the
 *   navbar's (`file-viewer/panelToggles.js`), its first control: a collapsed panel leaves nothing over the model but
 *   while a mouse rests on that toggle, when it peeks over the view, pushing nothing (`usePanelPeek.js`), until the
 *   pointer has left both, Escape, a press on the model, or a click on the toggle (or ⌘\) pins it. On a
 *   phone the same toggle opens it as a sheet from the left (shadcn's Sheet) under the navbar, over the model with no scrim,
 *   sliding in and out as the peek does (100ms in, 80ms out: `panelPeek.js`'s `PANEL_SHEET_LEFT_CLASS`), starting
 *   closed each time: a tap outside it, a swipe back to the left or Escape put it away. Preview keeps the
 *   docked panel mounted, out of sight, so a tree keeps its state.
 * - **The strip's column** at the top centre of the WHOLE view, always: no panel moves it, and where it meets one it
 *   stands over it (a layer of its own over the panels, `data-view-top-layer`); on a phone, the same. In it the strip (`tools`),
 *   the tool in hand's row (`toolRow`), the view catching up (`status`), and the tool stack
 *   (`toolStack`).
 * - **The update status** (`status`: what the view says while it catches up, `ViewUpdateStatus`'s
 *   `status` as `update`, its Retry where the update offers one, `onRetry`, and whether what is drawn is
 *   a build's preview, `preview`), one rule for every view: under the strip, or where there is no strip
 *   (Preview, a compact host, a load) at the top centre in the strip's row; none while the alert card
 *   says why the view's chrome is gone.
 * - **One measure** of that column, onto the frame's root: `--cad-tools-bottom` (what a flat canvas's
 *   fit keeps clear of) and `--cad-top-right-left` (where the top-right column starts, clear of the
 *   strip), again whenever the column, the stage or what stands in the top-right corner changes.
 * - **The top-right**: the corner (below), and under it (`ViewportTopRight`, `--cad-corner-below`, measured) the host's
 *   notice once the view is up.
 * - **Quick Edit's bar** (`quickEdit`), in the same layer, at the bottom, centred on the WHOLE view: 400px at
 *   most, narrower only with the view (16px in from each side); where it would stand over a pinned panel (a narrow
 *   window), centred on the model's area right of it instead; a phone's the view's full
 *   width less its 8px inset a side, never capped, above its safe area. The measure writes where it stands (`--cad-quick-edit-left`,
 *   `--cad-quick-edit-width`, from the view's left), and how far its top stands off the view's bottom
 *   (`--cad-quick-edit-reserve`), which the tool stack's column stops clear of, the bar one row or two.
 * - **The navbar's view settings** (`navbar`: what a view portals into the file's navbar, `NavbarViewControls.jsx`),
 *   drawn while the chrome is, on a desktop and a phone alike (the corner is a desktop's alone), and **Display's
 *   card** (`card`: `{ open, content }`, `DisplaySettings.jsx`'s), docked under the navbar at the view's right edge,
 *   over the corner and the strip's layer (`docs/design-system.md`, "Layering").
 * - **The corner** (`corner`, the view's top-right — the cube, or a flat view's zoom — or its
 *   top-left where the host anchors the cube there: the side read off the root with the measure, `viewCornerSide`, and said to everything in
 *   the corner, `ViewCornerSideProvider`), **the bottom centre** (`bottomCentre`, a
 *   playbar), the renderer's `underlay` (between the canvas and the chrome: Preview's view) and its
 *   `overlays` (over everything but the cards: Preview's cover).
 * - **Loading** (`loading`, `ViewerLoadingOverlay`'s) and **the alert card** (`alert`,
 *   `ViewerAlertCard`'s props), and the view's menu on a secondary press over a canvas the frame is
 *   handed (`contextMenu`: `ViewportContextMenu`'s props).
 * - A press on a canvas focuses the frame, so the view's keys are its own (`onCanvasPress` is told
 *   after).
 * - **Select in hand** (`selecting`), said on the root (`data-cad-selecting`): a double-click fits only
 *   then, in every view (`viewport/dom.js`'s `doubleClickFits`, which the canvas hooks read).
 * - **What is picked** (`inspect`, `inspector/inspect.js`'s: the view's picks and its description of
 *   each), one way in every view: Quick Edit's chip list, where a pick is read with its key facts (the panel holds
 *   only its lists); the **hover tip** over the canvas under Select
 *   (`HoverTip.jsx`), what a press would pick, named short; and the view's name for its marks to both
 *   (`InspectContext`).
 *
 * `preview`: Preview's chrome (`PreviewChrome`'s `active`, `name`, `controls`, `panel`, `panelOpen`
 * and `idle`), which wraps exactly the strip's column, the top-right and the corner. While it is
 * `active`, no tool row, status, pill, corner or card.
 *
 * @param {object} props
 * @param {{ current: HTMLElement | null }} [props.rootRef]  The frame's root, where the caller keeps one.
 * @param {Record<string, string>} [props.surface]  Data attributes on the root, which say what is drawn.
 * @param {string} [props.className]  The root's own classes past the frame's (a cursor).
 * @param {object} [props.rootHandlers]  Pointer handlers on the root (capture or not), past the frame's own.
 * @param {string} [props.stageColor]  The canvas's colour, where it is the scene's (the stage under it).
 * @param {{ current: HTMLElement | null }} [props.canvasBoxRef]  The box the canvas is drawn in.
 * @param {boolean} [props.busy]  `aria-busy` on that box, where the view says so.
 * @param {string} props.file  The view's file: the loading overlay's and the card's.
 * @param {boolean} props.mobile
 * @param {boolean} props.compact  A compact host: the picture alone.
 * @param {boolean} props.chromeHidden  The view loads, or has failed to: none of the frame's own chrome.
 * @param {boolean} [props.failed]  The load failed: no panel either (while it loads the panel is there, its first tab
 *   empty until the file arrives). Not given, the panel follows `chromeHidden`.
 * @param {boolean} [props.selecting]  Select is the tool in hand (or the view has no tools).
 * @param {{ update?: object | null, onRetry?: (() => void) | null, preview?: boolean } | null} [props.status]
 * @param {object[]} props.tools
 * @param {{ kind: string, label: string, searchLabel: string, tabs?: object[], sections?: import("react").ReactNode } | null} [props.panel]
 * @param {import("../inspector/inspect.js").Inspect | null} [props.inspect]
 */
export default function ViewFrame({ rootRef = null, surface = null, className = "", rootHandlers = null, stageColor = undefined,
  canvasBoxRef = null, busy = undefined, children, underlay = null, overlays = null, file, mobile, compact, chromeHidden, failed = undefined, previewing = false, selecting = false,
  preview = null, tools, toolRow = null, toolStack = null, status = null, panel = null, panelControl = null,
  layout, onLayoutChange, corner = null, navbar = null, card = null, notice = null, quickEdit = null, bottomCentre = null, loading = null, alert = null,
  contextMenu = null, onCanvasPress = null, inspect = null, viewport = null }) {
  const { t } = useI18n();
  // The viewport's theme (`look/useViewportTheme.js`): what stands on the picture — the canvas box (labels, chips,
  // the cube, the hover tip, the loading cover) and the corner's bare buttons — is scoped to its light or dark (the
  // `.light` / `.dark` token scopes, `styles/tokens.css`), on its canvas (`--canvas`); the chrome on surfaces of
  // its own (the strip, the panels, Quick Edit, the playbar, menus) keeps the app's theme.
  const scheme = viewport?.scheme === "dark" ? "dark" : viewport ? "light" : null;
  const toolsHidden = chromeHidden || compact;
  // The view catching up, said as every view says it, unless the card says why the chrome is gone.
  // It says what the picture is doing, over the picture: in its scheme (Preview's backdrop's while Preview is up), never
  // the app's, under the strip as at the top centre.
  const statusScheme = previewing ? (preview?.scheme ?? scheme) : scheme;
  const statusNode = !status || (chromeHidden && alert?.alert) ? null : <div className={cn("pointer-events-none flex max-w-full items-center gap-2", statusScheme)}
    data-viewport-status="" data-scheme={statusScheme ?? undefined}>
    {status.preview ? <ViewPreviewLabel /> : null}
    <ViewUpdateStatus status={status.update ?? IDLE_STATUS} onRetry={status.onRetry ?? undefined} className="rounded-md bg-background/95 px-1 py-0.5 shadow-sm" />
  </div>;
  const ownRoot = useRef(null);
  const root = rootRef ?? ownRoot;
  // A finger's double tap and long press on the picture, said as a double-click and a right-click (`touchGestures.js`).
  useTouchGestures(root);
  const stageRef = useRef(null);
  const topControls = useRef(null);
  const quickEditRow = useRef(null);
  const [cornerSide, setCornerSide] = useState("right");

  // ---- the panel (`sidebars.js`): the file's structure and its own settings, as tabs; a phone's a sheet ----------------
  const sided = Boolean(panel && (panel.sections || panel.tabs?.length));
  // A phone's sheet: closed until its toggle opens it, and kept nowhere.
  const [sheetOpen, setSheetOpen] = useState(false);
  const viewerElement = useContext(ViewerElementContext);
  // What a press would pick, beside the pointer.
  const hoverTip = useFrameHoverTip({ hovered: inspect?.hovered || "", describe: inspect?.describe || null, tip: inspect?.tip || null, enabled: selecting && !toolsHidden && !previewing });
  const flat = useFlatPanelState({ frameRef: root, kind: panel?.kind ?? "", toolStack: layout, onToolStackChange: onLayoutChange, compact: Boolean(compact) });
  // The person's choice on this file (its entry in the tab's settings, `filePanel.js`): open, closed, or none yet (the
  // view's width decides, `sidebars.js`).
  const kept = flat.record;
  // The panel is there from the view's first frame, the file still loading: its kind says it has one (its tabs fill as
  // the file arrives), so neither it nor its toggle comes in late and pushes the model aside. A load that failed, or a
  // compact host, has none.
  const has = sided && !(failed ?? chromeHidden) && !compact;
  const sidebarState = { frameWidth: flat.frameWidth, choice: kept.open, has: has && !mobile, mobile, phoneHas: has };
  const { mode } = sidebarLayout(sidebarState);
  const stateRef = useRef(sidebarState);
  stateRef.current = sidebarState;
  // A choice the person made is kept, for the file, and holds at any width; what the width does is never kept.
  const change = flat.change;
  // A peek (`usePanelPeek.js`): the collapsed panel over the view while a mouse rests on its toggle; never kept. Inside a
  // file viewer it is the page's one peek (`PanelPeekContext`), up from the first frame, its enabled state what this
  // frame says with its toggle (`peekable`); outside one, the frame's own.
  const peekable = has && !mobile && !previewing && mode === "closed";
  const pagePeek = useContext(PanelPeekContext);
  const ownPeek = usePanelPeek({ enabled: !pagePeek && peekable });
  const peek = pagePeek ?? ownPeek;
  const closePeek = peek.close;
  const toggle = useCallback(() => {
    const current = stateRef.current;
    if (current.mobile) { if (current.phoneHas) setSheetOpen(open => !open); return; }
    if (!current.has) return;
    // A click (or ⌘\) while it peeks pins it: the panel opens as a click on a collapsed one always has, where the peek
    // is (no slide: the card becomes the docked panel in place), and that is the person's choice on this file, kept. A
    // peek on its own is none.
    closePeek(false, true);
    change({ open: toggleSidebar(current).open });
  }, [change, closePeek]);
  // Escape puts a peek away, before anything else of the view's (the tool in hand, the selection: the view's ladder
  // leaves it to the peek, `lib/popups.js`), after a popup or the search box in it has spent its own.
  useEffect(() => {
    if (!peek.peeking) return undefined;
    const onKeyDown = event => {
      if (event.key !== "Escape" || event.defaultPrevented || hasOpenPopup(peek.panelRef.current)) return;
      event.preventDefault();
      closePeek();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [peek.peeking, peek.panelRef, closePeek]);
  if (panelControl) panelControl.current = previewing ? null : {
    toggle,
    search: () => {
      if (stateRef.current.mobile) return false;
      if (!stateRef.current.has) return false;
      // A peek opens its search where it is: only the toggle pins it.
      if (sidebarLayout(stateRef.current).mode === "closed" && !peek.peeking) toggle();
      flat.askSearch();
      return true;
    }
  };
  // While the file loads (the frame's chrome hidden, the panel there): a structure tab with no row yet shows placeholders.
  const panelLoading = has && chromeHidden;
  const panelNode = has && !mobile ? <FlatPanel mode="docked" open={mode !== "closed" || peek.shown} peek={mode === "closed" && peek.shown}
    peekLeaving={peek.leaving} peekEntered={peek.entered} onPeekExited={peek.exited} loading={panelLoading}
    surfaceRef={peek.panelRef} surfaceProps={peek.panelHandlers} hidden={previewing} onClose={toggle}
    label={panel.label} searchLabel={panel.searchLabel} tabs={panel.tabs ?? null} sections={panel.sections ?? null} tab={flat.tab} onTabChange={flat.changeTab}
    width={flat.width} maxWidth={flat.maxWidth} onWidthChange={flat.changeWidth} focusSearch={flat.focusSearch} /> : null;
  // A phone's: the same panel, its tabs, search and every tab's content, the same components at the same sizes (a tree
  // row's own touch height aside), in a sheet from the left over the model (`FlatPanel`'s "page" mode), in the viewer's element.
  // Under the navbar, with no scrim (`usePhoneSheetPlace`), sliding in and out from the left as the Display card does
  // from the right: the peek's one slide (`panelPeek.js`), so a phone's two popovers move alike.
  const closeSheet = useCallback(() => setSheetOpen(false), []);
  const sheetPlace = usePhoneSheetPlace(viewerElement, has && mobile && sheetOpen && !previewing);
  const sheetNode = has && mobile ? <Sheet open={sheetOpen && !previewing} onOpenChange={setSheetOpen}>
    <SheetContent side="left" showCloseButton={false} onSwipeClose={closeSheet} container={viewerElement?.current ?? undefined}
      scrim={false} animated={false} style={sheetPlace.style} overlayStyle={sheetPlace.style} onCloseAutoFocus={sheetPlace.onCloseAutoFocus}
      onPointerDownOutside={sheetPlace.onPointerDownOutside}
      aria-describedby={undefined} className={cn("h-auto w-[85%] max-w-[20rem] gap-0 overflow-hidden border-border p-0", PANEL_SHEET_LEFT_CLASS)} data-panel-sheet="">
      <SheetTitle className="sr-only">{panel.label}</SheetTitle>
      <FlatPanel mode="page" open onClose={closeSheet} loading={panelLoading} label={panel.label} searchLabel={panel.searchLabel} tabs={panel.tabs ?? null}
        sections={panel.sections ?? null} tab={flat.tab} onTabChange={flat.changeTab} width={flat.width} maxWidth={flat.maxWidth}
        onWidthChange={flat.changeWidth} focusSearch={flat.focusSearch} />
    </SheetContent>
  </Sheet> : null;
  // The toggle, the navbar's (`file-viewer/panelToggles.js`), its first control. A collapsed panel leaves nothing over the model.
  const platform = useContext(ViewerHostContext)?.environment?.platform;
  const panelOpen = mobile ? sheetOpen : mode === "push";
  const showToggle = has && !previewing;
  const toggles = useMemo(() => (!showToggle ? null : {
    left: { open: panelOpen, label: t(panelOpen ? "flatPanel.hide" : "flatPanel.show"), shortcut: flatPanelShortcut(platform), toggle,
      // Whether it may peek, once the frame has measured its width (before, its mode is not yet known: not said).
      hover: mobile ? null : peek.toggleHandlers, peeking: peek.peeking, peekable: flat.frameWidth > 0 ? peekable : undefined }
  }), [showToggle, panelOpen, platform, toggle, t, mobile, peek.toggleHandlers, peek.peeking, peekable, flat.frameWidth > 0]);
  // Leaving a phone's width (or Preview) puts its sheet away.
  useLayoutEffect(() => { if (!mobile || previewing) setSheetOpen(false); }, [mobile, previewing]);
  usePanelToggles(toggles);

  // ---- the strip's column and Quick Edit: centred on the whole view, over the panels -------------
  const hasQuickEdit = Boolean(quickEdit);
  useLayoutEffect(() => {
    const controls = topControls.current, stage = stageRef.current, frame = root.current;
    if (!controls || !stage || !frame) return undefined;
    const measure = () => {
      // Where the host anchors the corner (its variables are its own, on an ancestor), read as the
      // rest is: whenever the view's box or what stands in it changes.
      setCornerSide(viewCornerSide(frame));
      const stageBox = stage.getBoundingClientRect();
      // Quick Edit's bar, always there: centred on the whole view, 400px at most, else the view's width less its margins; a
      // phone's the view's full width less its inset, uncapped. Where, so centred, it would stand over a pinned panel (a
      // narrow window), it centres on the model's area instead, as it is always on screen and the panel's foot is under
      // it there. A peek, over the view a moment, moves nothing.
      const viewWidth = frame.getBoundingClientRect().width;
      const margin = mobile ? VIEWPORT_INSET_PX : QUICK_EDIT_MARGIN_PX;
      const fit = room => Math.max(0, mobile ? room - 2 * margin : Math.min(QUICK_EDIT_MAX_PX, room - 2 * margin));
      let barWidth = fit(viewWidth), barLeft = (viewWidth - barWidth) / 2;
      const pinned = mobile ? null : frame.querySelector(":scope > aside[data-flat-panel]:not([hidden]):not([data-panel-peek])");
      const panelRight = pinned ? pinned.getBoundingClientRect().right - frame.getBoundingClientRect().left : 0;
      if (panelRight > barLeft - margin) { barWidth = fit(viewWidth - panelRight); barLeft = panelRight + (viewWidth - panelRight - barWidth) / 2; }
      frame.style.setProperty("--cad-quick-edit-left", `${Math.round(barLeft)}px`);
      frame.style.setProperty("--cad-quick-edit-width", `${Math.round(barWidth)}px`);
      // What the bar takes of the view's bottom (its height, its 16px off the bottom, and 8px): the tool stack's column
      // stops above it, as it always stands now.
      const bar = quickEditRow.current?.getBoundingClientRect();
      if (bar?.height) frame.style.setProperty("--cad-quick-edit-reserve", `${Math.round(frame.getBoundingClientRect().bottom - bar.top + VIEWPORT_INSET_PX)}px`);
      else frame.style.removeProperty("--cad-quick-edit-reserve");
      // The rows with something in them: an empty one (no update under way) still takes the
      // column's gap, which would leave a wider gap under the strip than at its sides.
      const rows = [...controls.children].map(row => row.getBoundingClientRect()).filter(box => box.height > 0);
      const top = controls.getBoundingClientRect().top;
      frame.style.setProperty("--cad-tools-bottom", `${Math.round(VIEWPORT_INSET_PX * 2 + Math.max(top, ...rows.map(box => box.bottom)) - top)}px`);
      // The corner at the top-right (the cube or the zoom): the host's notice stands under it,
      // an inset away. A corner the host anchors at the left leaves the top-right to the notice.
      const corner = () => [...stage.querySelectorAll(CORNER_CONTROLS)].map(element => element.getBoundingClientRect()).filter(box => box.height > 0);
      const cornerBoxes = viewCornerSide(frame) === "right" ? corner() : [];
      if (cornerBoxes.length) frame.style.setProperty("--cad-corner-below", `${Math.round(Math.max(...cornerBoxes.map(box => box.bottom)) - stageBox.top + VIEWPORT_INSET_PX)}px`);
      else frame.style.removeProperty("--cad-corner-below");
      if (mobile || !rows.length) {
        frame.style.removeProperty("--cad-top-right-left");
        return;
      }
      // The column's right side, the widest of its rows, from the stage's left: the top-right
      // corner (the host's notice) starts past it, an inset away, so it never reaches under the strip.
      const right = Math.max(...rows.map(row => row.right)) - stageBox.left;
      frame.style.setProperty("--cad-top-right-left", `${Math.round(right + VIEWPORT_INSET_PX)}px`);
    };
    measure();
    if (typeof ResizeObserver === "undefined") return () => { for (const name of MEASURED) frame.style.removeProperty(name); };
    // What moves them: the controls, the stage, and what comes and goes in the top-right corner
    // (the host's notice; the corner's cube, pill and stack).
    const resized = new ResizeObserver(measure);
    resized.observe(controls);
    resized.observe(stage);
    if (quickEditRow.current) resized.observe(quickEditRow.current);
    const watch = () => { for (const element of stage.querySelectorAll(CORNER_BOXES)) resized.observe(element); };
    watch();
    const changed = typeof MutationObserver === "undefined" ? null : new MutationObserver(() => { watch(); measure(); });
    for (const element of stage.querySelectorAll("[data-viewport-top-right]")) {
      changed?.observe(element, { attributes: true, attributeFilter: ["data-open"], childList: true, subtree: true });
    }
    return () => {
      resized.disconnect(); changed?.disconnect();
      for (const name of MEASURED) frame.style.removeProperty(name);
    };
  }, [root, toolsHidden, mobile, sided, mode, hasQuickEdit]);

  // The stage's own variables: its colour, where it is the scene's.
  const stageVariables = {
    ...(stageColor ? { backgroundColor: stageColor } : {})
  };
  return (
    <InspectContext.Provider value={inspect}>
    <div ref={root} className={cn("relative flex h-full min-h-0 flex-row overflow-hidden bg-canvas text-foreground", className)}
      style={{ ...(viewport?.canvas ? { "--canvas": viewport.canvas } : {}), "--cad-host-corner-right": "var(--cad-viewport-corner-right, 2px)", "--cad-host-corner-left": "var(--cad-viewport-corner-left, 0px)" }}
      data-viewport-scheme={scheme ?? undefined} data-sidebar={mode} data-sidebar-peek={peek.peeking ? "" : undefined}
      data-slot="cad-file-view" data-cad-surface="" data-cad-selecting={selecting ? "" : undefined} {...surface} tabIndex={-1} {...rootHandlers}
      onPointerDownCapture={event => {
        if (!(event.target instanceof Element) || !event.target.closest("canvas")) return;
        // A press on the model puts a peek away (the keyboard goes to the view, below).
        closePeek(false);
        event.currentTarget.focus({ preventScroll: true });
        onCanvasPress?.(event);
      }}>
      {panelNode}
      {sheetNode}
      {/* The stage: what the pushed panels leave of the view. The canvas fills it, so a fit centres in what
          is visible and a change of its size reaches the picture as a plain resize. */}
      <div ref={stageRef} className="@container/cad-viewport pointer-events-none relative min-h-0 min-w-0 flex-1"
        data-cad-canvas={stageColor ?? ""} style={stageVariables}>
        <div ref={canvasBoxRef} className={cn("pointer-events-auto absolute inset-0", scheme)} style={viewport?.canvas ? { "--canvas": viewport.canvas } : undefined} aria-busy={busy === undefined ? undefined : busy ? "true" : "false"}
          data-cad-canvas-box="" {...hoverTip.handlers}>
          {children}
          <HoverTip tip={hoverTip.tip} />
        </div>
        {underlay}
        <PreviewChrome active={false} {...preview}>
          {toolsHidden || previewing || mobile ? null : <ViewCornerSideProvider value={cornerSide}>
            {/* The corner's buttons stand bare on the picture: in the viewport's theme, so they and their halo read on it. */}
            <div className={cn("contents", scheme)} data-view-corner="">{corner}</div>
          </ViewCornerSideProvider>}
          {/* What the view portals into the file's navbar (its view settings), on a desktop and a phone alike. */}
          {toolsHidden || previewing ? null : navbar}
          {/* The host's notice once the view is up. */}
          <ViewportTopRight notice={chromeHidden ? null : notice} />
        </PreviewChrome>
        {bottomCentre}
        {overlays}
        {/* The view catching up, at the top centre while there is no strip. */}
        {statusNode && (toolsHidden || previewing) ? <div className="pointer-events-none absolute left-1/2 z-30 flex max-w-[calc(100%-1rem)] -translate-x-1/2 items-center"
          style={{ top: VIEWPORT_INSET_PX, height: VIEWPORT_TOP_BAR_PX }}>{statusNode}</div> : null}
        {chromeHidden || previewing || !contextMenu ? null : <ViewportContextMenu {...contextMenu} />}
        <div className={cn("contents", scheme)}><ViewerLoadingOverlay loading={loading} operationKey={file} /></div>
        {/* The alert card, last: over the tools, which a warning the view survives keeps on screen. */}
        {previewing || !alert ? null : <div className={cn("contents", scheme)} data-view-alert-scope=""><ViewerAlertCard {...alert} file={alert.file ?? file} /></div>}
      </div>
      {/* The strip's column and Quick Edit's bar: centred on the whole view (the bar on the model's area where it would
          stand over a pinned panel), and over the panels where they meet (a layer of their own over the panels, an overlaid one too); hidden and inert in Preview,
          as the rest of the chrome is (`PreviewChrome`). */}
      <div className="pointer-events-none absolute inset-0 z-50" hidden={previewing} inert={previewing} data-view-top-layer="">
        <ToolbarTooltipScope enabled={!previewing}>
          {toolsHidden ? null : <div className="group/tool-stack pointer-events-none absolute z-20 flex flex-col items-center gap-2"
            style={TOOLBAR_POSITION} data-mobile={mobile ? "" : undefined} data-cad-tool-groups="">
            <StripTouchProvider value={mobile}>
              <div ref={topControls} className="relative flex max-w-full shrink-0 flex-col items-center gap-2" data-cad-top-controls="">
                <FloatingToolBar tools={tools} touch={mobile} />
                {previewing ? null : toolRow}
                {previewing ? null : statusNode}
              </div>
              {toolStack}
            </StripTouchProvider>
          </div>}
          {/* Quick Edit's bar, at the bottom on the model's area's centre line (above): hidden, not unmounted, while the view
              loads, as a note being written outlives a reload. */}
          {compact || !quickEdit ? null : <div ref={quickEditRow} className="pointer-events-none absolute z-30 flex flex-col justify-end" data-quick-edit-row=""
            style={{ left: `var(--cad-quick-edit-left, ${INSET})`, width: `var(--cad-quick-edit-width, calc(100% - 2 * ${INSET}))`,
              bottom: mobile ? `calc(${INSET} + env(safe-area-inset-bottom, 0px))` : 2 * VIEWPORT_INSET_PX }}>{quickEdit}</div>}
        </ToolbarTooltipScope>
      </div>
      {card && !toolsHidden && !previewing ? <SettingsCardDock open={card.open} className={SETTINGS_CARD_LAYER_CLASS} style={{ top: SETTINGS_CARD_GAP_PX }}
        data-display-settings-dock="">{card.content}</SettingsCardDock> : null}
    </div>
    </InspectContext.Provider>
  );
}

// The strip and the tool stack under it share one column at the top centre of the WHOLE view, its height the room
// down to Quick Edit's bar (its measured top, one row or two), so however many panels are up it never runs past the view. Where the view is narrow enough
// for the strip to reach the corner's cube, the strip (a layer over the corner) stands over it. It spans the view within its
// inset and centres what it holds: positioned from the centre (`left: 50%`) it would shrink to the half right of it,
// and the strip would wrap at half the view. No panel moves it; it stands over them.
const INSET = `${VIEWPORT_INSET_PX}px`;
const TOOLBAR_POSITION = Object.freeze({ top: INSET, left: INSET, right: INSET, bottom: `max(${VIEWPORT_STACK_BOTTOM}, var(--cad-quick-edit-reserve, 0px))` });
// What stands in the top-right corner: the corner's control (the cube, or a flat view's zoom), and the host's notice
// under it (not its column).
const CORNER_CONTROLS = "[data-view-cube], [data-zoom-pill]";
const CORNER_BOXES = `[data-viewport-top-right] [data-viewport-notice], ${CORNER_CONTROLS}`;
const MEASURED = ["--cad-tools-bottom", "--cad-top-right-left", "--cad-corner-below", "--cad-quick-edit-left", "--cad-quick-edit-width", "--cad-quick-edit-reserve"];
// Quick Edit's bar: 400px at most, centred on the whole view (or the model's area beside a pinned panel); narrower only
// with the view, 16px in from each side.
const QUICK_EDIT_MAX_PX = 400;
const QUICK_EDIT_MARGIN_PX = 16;
// Nothing to say: the status draws nothing.
const IDLE_STATUS = Object.freeze({ pending: false });
