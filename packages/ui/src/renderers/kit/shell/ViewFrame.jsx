import { useLayoutEffect, useRef } from "react";
import { useI18n } from "@cad/ui/i18n";
import { cn } from "@cad/ui/utils";
import ViewerAlertCard from "../status/ViewerAlertCard.jsx";
import ViewerLoadingOverlay from "../status/ViewerLoadingOverlay.js";
import FloatingToolBar, { StripTouchProvider } from "../tools/FloatingToolBar.js";
import PreviewChrome from "../tools/PreviewChrome.jsx";
import FlatPanel, { FlatPanelPill, useFlatPanelState } from "./FlatPanel.jsx";
import { stripLeft, useStageReach } from "./useStageReach.js";
import ViewportContextMenu from "./ViewportContextMenu.jsx";
import { ViewportTopRight } from "./ViewportTopRight.jsx";
import { VIEWPORT_INSET_PX, VIEWPORT_STACK_BOTTOM, VIEWPORT_TOP_BAR_PX } from "./viewportLayout.js";

/**
 * The ONE frame every view is drawn in, 2D or 3D: the canvas is the only thing a renderer brings
 * that differs (`children`); everything round it is this, so the strip, the panel, the corner and the
 * cards stand in one place and behave one way in every renderer. `RendererShell.jsx` (a 3D view) and
 * `FlatViewFrame.jsx` (a picture drawn flat) mount it; nothing else draws the frame's parts.
 *
 * - **The panel** (`FlatPanel.jsx`, `useFlatPanelState`): docked at the view's left, the canvas the
 *   narrower for it while it is open, at any width; its open or shut state, width and tab are the
 *   file's (`filePanel.js`). Collapsed, its expand button on a pill at the canvas's top-left. A phone
 *   has none: no pill, no keys (`panelControl` stays empty). Preview keeps it mounted, out of sight,
 *   so a tree keeps its state.
 * - **The strip's column** at the top centre of the WHOLE view: it reaches back over the docked panel
 *   (`useStageReach.js`), so opening or shutting the panel never moves it, and it draws over the panel
 *   where they meet; on a phone, the same. In it the strip (`tools`, and its view controls `views`),
 *   the tool in hand's row (`toolRow`), the view catching up (`status`), and the tool stack
 *   (`toolStack`). With no strip (a compact host, Preview) `status` stands at the top centre alone.
 * - **One measure** of that column, onto the frame's root: `--cad-tools-bottom` (what a flat canvas's
 *   fit keeps clear of) and `--cad-top-right-left` (where the top-right column starts, clear of the
 *   strip), again whenever the column, the stage or what stands in the top-right corner changes.
 * - **The top-right** (`ViewportTopRight`): the host's notice once the view is up, and `quickEdit`.
 * - **The corner** (`corner`, the view's bottom-right), **the bottom centre** (`bottomCentre`, a
 *   playbar), the renderer's `underlay` (between the canvas and the chrome: Preview's view) and its
 *   `overlays` (over everything but the cards: Preview's cover).
 * - **Loading** (`loading`, `ViewerLoadingOverlay`'s) and **the alert card** (`alert`,
 *   `ViewerAlertCard`'s props), and the view's menu on a secondary press over a canvas the frame is
 *   handed (`contextMenu`: `ViewportContextMenu`'s props).
 * - A press on a canvas focuses the frame, so the view's keys are its own (`onCanvasPress` is told
 *   after).
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
 * @param {object[]} props.tools
 * @param {object[]} [props.views]
 * @param {{ kind: string, label: string, searchLabel: string, tabs?: object[], sections?: import("react").ReactNode,
 *   detail?: import("react").ReactNode } | null} [props.panel]
 */
export default function ViewFrame({ rootRef = null, surface = null, className = "", rootHandlers = null, stageColor = undefined,
  canvasBoxRef = null, busy = undefined, children, underlay = null, overlays = null, file, mobile, compact, chromeHidden, previewing = false,
  preview = null, tools, views = [], toolRow = null, toolStack = null, status = null, panel = null, panelControl = null,
  layout, onLayoutChange, corner = null, notice = null, quickEdit = null, bottomCentre = null, loading = null, alert = null,
  contextMenu = null, onCanvasPress = null }) {
  const { t } = useI18n();
  const toolsHidden = chromeHidden || compact;
  const ownRoot = useRef(null);
  const root = rootRef ?? ownRoot;
  const stageRef = useRef(null);
  const topControls = useRef(null);

  // ---- the panel: docked, open at first in a wide view; none on a phone --------------------------
  const sided = Boolean(panel && (panel.sections || panel.tabs?.length)) && !mobile;
  const flat = useFlatPanelState({ frameRef: root, mobile, enabled: sided && !toolsHidden, kind: panel?.kind ?? "", toolStack: layout, onToolStackChange: onLayoutChange });
  if (panelControl) panelControl.current = previewing ? null : flat.control;
  const panelNode = sided && !toolsHidden ? <FlatPanel mode="docked" open={flat.open} hidden={previewing} onClose={() => flat.setOpen(false)}
    label={panel.label} searchLabel={panel.searchLabel} tabs={panel.tabs ?? null} sections={panel.sections ?? null} tab={flat.tab} onTabChange={flat.changeTab}
    width={flat.width} maxWidth={flat.maxWidth} onWidthChange={flat.changeWidth} focusSearch={flat.focusSearch} detail={panel.detail ?? null}
    detailHeight={flat.detailHeight} onDetailHeightChange={flat.changeDetailHeight} /> : null;

  // ---- the strip's column: at the view's centre, reaching back over the docked panel -------------
  useStageReach(stageRef, root);
  const hasQuickEdit = Boolean(quickEdit);
  useLayoutEffect(() => {
    const controls = topControls.current, stage = stageRef.current, frame = root.current;
    if (!controls || !stage || !frame) return undefined;
    const measure = () => {
      // The rows with something in them: an empty one (no update under way) still takes the
      // column's gap, which would leave a wider gap under the strip than at its sides.
      const rows = [...controls.children].map(row => row.getBoundingClientRect()).filter(box => box.height > 0);
      const top = controls.getBoundingClientRect().top;
      frame.style.setProperty("--cad-tools-bottom", `${Math.round(VIEWPORT_INSET_PX * 2 + Math.max(top, ...rows.map(box => box.bottom)) - top)}px`);
      if (mobile || !rows.length) {
        frame.style.removeProperty("--cad-top-right-left");
        return;
      }
      // The column's right side, the widest of its rows, from the stage's left: the top-right
      // corner (Quick Edit) starts past it, an inset away, so it never reaches under the strip.
      const right = Math.max(...rows.map(row => row.right)) - stage.getBoundingClientRect().left;
      frame.style.setProperty("--cad-top-right-left", `${Math.round(right + VIEWPORT_INSET_PX)}px`);
    };
    measure();
    if (typeof ResizeObserver === "undefined") return () => { for (const name of MEASURED) frame.style.removeProperty(name); };
    // What moves them: the controls, the stage, and what comes and goes in the top-right corner
    // (Quick Edit opening, closing, resized).
    const resized = new ResizeObserver(measure);
    resized.observe(controls);
    resized.observe(stage);
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
  }, [root, toolsHidden, mobile, sided, flat.open, hasQuickEdit]);

  return (
    <div ref={root} className={cn("relative flex h-full min-h-0 flex-row overflow-hidden bg-canvas text-foreground", className)}
      data-slot="cad-file-view" data-cad-surface="" {...surface} tabIndex={-1} {...rootHandlers}
      onPointerDownCapture={event => {
        if (!(event.target instanceof Element) || !event.target.closest("canvas")) return;
        event.currentTarget.focus({ preventScroll: true });
        onCanvasPress?.(event);
      }}>
      {panelNode}
      {/* The stage: what the panel leaves of the view. The canvas fills it, so a fit centres in what
          is visible and a change of its size reaches the picture as a plain resize. */}
      <div ref={stageRef} className="@container/cad-viewport pointer-events-none relative min-h-0 min-w-0 flex-1"
        data-cad-canvas={stageColor ?? ""} style={stageColor ? { backgroundColor: stageColor } : undefined}>
        <div ref={canvasBoxRef} className="pointer-events-auto absolute inset-0" aria-busy={busy === undefined ? undefined : busy ? "true" : "false"}
          data-cad-canvas-box="">{children}</div>
        {underlay}
        <PreviewChrome active={false} {...preview}>
          {toolsHidden ? null : <div className="group/tool-stack pointer-events-none absolute z-20 flex flex-col items-center gap-2"
            style={{ ...TOOLBAR_POSITION, left: stripLeft(VIEWPORT_INSET_PX) }} data-mobile={mobile ? "" : undefined} data-cad-tool-groups="">
            <StripTouchProvider value={mobile}>
              <div ref={topControls} className="relative flex max-w-full shrink-0 flex-col items-center gap-2" data-cad-top-controls="">
                <FloatingToolBar tools={tools} views={views} touch={mobile} />
                {previewing ? null : toolRow}
                {previewing ? null : status}
              </div>
              {toolStack}
            </StripTouchProvider>
          </div>}
          {toolsHidden || previewing || mobile ? null : corner}
          {/* The host's notice once the view is up, and Quick Edit under it — hidden, not unmounted,
              while the view loads: a note being written outlives a reload. On a phone Quick Edit is a
              bottom sheet, portalled out of this corner. */}
          <ViewportTopRight notice={chromeHidden ? null : notice}>{compact ? null : quickEdit}</ViewportTopRight>
        </PreviewChrome>
        {/* Collapsed, the panel's expand button, alone on a pill at the canvas's top-left. */}
        {sided && !toolsHidden && !previewing && !flat.open ? <FlatPanelPill touch={mobile} onOpen={() => flat.setOpen(true)} /> : null}
        {bottomCentre}
        {overlays}
        {/* The view catching up, at the top centre while there is no strip. */}
        {status && (toolsHidden || previewing) ? <div className="pointer-events-none absolute left-1/2 z-30 flex max-w-[calc(100%-1rem)] -translate-x-1/2 items-center"
          style={{ top: VIEWPORT_INSET_PX, height: VIEWPORT_TOP_BAR_PX }}>{status}</div> : null}
        {chromeHidden || previewing || !contextMenu ? null : <ViewportContextMenu {...contextMenu} />}
        <ViewerLoadingOverlay loading={loading} operationKey={file} />
        {/* The alert card, last: over the tools, which a warning the view survives keeps on screen. */}
        {previewing || !alert ? null : <ViewerAlertCard {...alert} file={alert.file ?? file} />}
      </div>
    </div>
  );
}

// The strip and the tool stack under it share one column at the top centre, its height the room down
// to the corner's line, so however many panels are up it never runs past the view. It spans the view
// within its inset and centres what it holds: positioned from the centre (`left: 50%`) it would shrink
// to the half right of it, and the strip would wrap at half the view.
const INSET = `${VIEWPORT_INSET_PX}px`;
const TOOLBAR_POSITION = Object.freeze({ top: INSET, left: INSET, right: INSET, bottom: VIEWPORT_STACK_BOTTOM });
// What stands in the top-right corner: the host's notice and Quick Edit's box (not its column).
const CORNER_BOXES = "[data-viewport-top-right] :is([data-viewport-notice], [data-quick-edit-box])";
const MEASURED = ["--cad-tools-bottom", "--cad-top-right-left"];
