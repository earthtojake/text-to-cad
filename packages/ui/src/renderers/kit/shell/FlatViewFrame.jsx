import { english } from "@cad/ui/i18n";
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { MousePointer2 } from "lucide-react";
import { cn } from "@cad/ui/utils";
import { AnnotationToolbar, DRAWING_TOOLS, annotationToolIcon, drawingToolVariant, drawingToolLabel } from "../../../annotation/toolbar.jsx";
import ViewerAlertCard from "../status/ViewerAlertCard.jsx";
import ViewerLoadingOverlay from "../status/ViewerLoadingOverlay.js";
import { ViewUpdateStatus } from "../status/ViewUpdateStatus.jsx";
import FloatingToolBar, { StripTouchProvider } from "../tools/FloatingToolBar.js";
import PreviewChrome from "../tools/PreviewChrome.jsx";
import { MeasureIcon } from "../tools/measure/SceneMeasure.jsx";
import { MeasurementsBar } from "../tools/measure/measurementChips.jsx";
import QuickEdit from "../tools/quick-edit/QuickEdit.jsx";
import { DRAWING_SHORTCUTS, TOOL_SHORTCUTS } from "../tools/toolShortcuts.js";
import { FLAT_TOOL } from "./useFlatView.js";
import { VIEWPORT_INSET_PX, VIEWPORT_TOP_BAR_PX } from "./viewportLayout.js";
import { ViewportTopRight } from "./ViewportTopRight.jsx";
import FlatPanel, { FLAT_PANEL_DEFAULT_WIDTH, FLAT_PANEL_MIN_WIDTH, FlatPanelPill } from "./FlatPanel.jsx";

/**
 * The frame every FLAT view is drawn in — a picture on a canvas, head on (a board, a schematic):
 * its panel docked at the left (`FlatPanel.jsx`: search, then a tab per list), and on the canvas
 * beside it the strip at the top centre — the view's centre, open panel or not — with the tool's row
 * and the update under it, the view cluster at the canvas's bottom-right (`viewControls`: how the
 * picture is drawn, a board's flip and Display), Quick Edit at
 * the top-right, the loading cover and the alert card, laid out as every view's
 * (`RendererShell.jsx`'s), from the kit's parts. The renderer brings the picture (its canvases and
 * layers, `children`, in the pane the canvas view measures: `containerRef`), its tools
 * (`flatViewTools`), its view controls after the strip's rule (`views`), its panel's tabs (`panel`)
 * and Quick Edit's props (`useFlatHandover`'s `quickEdit`).
 *
 * The panel is docked, the canvas always the narrower for it while it is open. In a view 1024px wide
 * or more it is open until the person collapses it (kept: `toolStack.collapsed.flat`, its width
 * `toolStack.panels.flat`, its tab by the kind of file `toolStack.tabs`); narrower, it starts
 * collapsed. Collapsed, its expand button stands on a pill at the canvas's top-left. On a phone it
 * opens as the whole view.
 * ⌘\ (Ctrl+\) shows and hides it, and / opens it on its search (`useFlatHandover`'s `panelControl`).
 *
 * While the picture loads, or once it has failed to, none of the viewer's own chrome: the load
 * itself, or the card saying why. A compact host gets the picture alone.
 */

const SELECT_ICON = <MousePointer2 className="size-3" strokeWidth={2} aria-hidden="true" />;
const MEASURE_ICON = <MeasureIcon className="size-3.5" aria-hidden="true" />;
const INSET = `${VIEWPORT_INSET_PX}px`;
// The strip and what hangs under it: one column at the top centre, as every view's (`RendererShell.jsx`).
const TOOLBAR_POSITION = Object.freeze({ top: INSET, left: INSET, right: INSET, bottom: INSET });
// On a phone with a panel, its pill stands at the left of the strip's line (a 36px tile in 4px of padding and a border).
const TOOLBAR_POSITION_PHONE_SIDEBAR = Object.freeze({ ...TOOLBAR_POSITION, left: `${VIEWPORT_INSET_PX + 46 + 8}px` });
// Narrower than this, the panel starts collapsed (GitHub's file tree's breakpoint); opened, it docks all the same.
export const FLAT_PANEL_OPEN_PX = 1024;
const FLAT_PANEL_ID = "flat";

/**
 * A flat view's strip, Select, Pencil, Shapes and Measure, each with its key, and the row of the
 * tool in hand under it: the drawing tools' (their tools, colours and widths) or Measure's (its
 * measurements, while there are any); Select has none. `selectMenu`: Select's filter, the chevron
 * after its button, where the view offers one.
 *
 * @param {ReturnType<typeof import("./useFlatView.js").useFlatTools>} tools
 * @param {{ colorScheme: "light" | "dark", shown: boolean, t?: Function, selectMenu?: import("react").ReactNode }} options
 */
export function flatViewTools(tools, { colorScheme, shown, selectMenu = null, t = english }) {
  const { toolMode, selectTool, annotation, annotating, measuring, measure, toolKeys } = tools;
  const stripTool = (id, label, icon, extra = {}) => ({ id, label, icon, active: toolMode === id, disabled: !shown, onSelect: () => selectTool(id), ...extra });
  const strip = [
    stripTool(FLAT_TOOL.SELECT, t("tool.select"), SELECT_ICON, { shortcut: TOOL_SHORTCUTS.select, ...(selectMenu ? { menu: selectMenu } : {}) }),
    // Pencil and Shapes: plain buttons, each the tool last chosen in it, its tooltip that tool and its key; the tools are the row's.
    ...DRAWING_TOOLS.map(({ id }) => {
      const label = drawingToolLabel(id, t);
      const variant = drawingToolVariant(id, annotation);
      const Icon = annotationToolIcon(variant);
      return stripTool(id, label, <Icon className="size-3" strokeWidth={2} aria-hidden="true" />,
        { tooltip: drawingToolLabel(variant, t), shortcut: DRAWING_SHORTCUTS[variant] });
    }),
    stripTool(FLAT_TOOL.MEASURE, t("tool.measure"), MEASURE_ICON, { shortcut: TOOL_SHORTCUTS.measure })
  ];
  toolKeys.current = strip;
  const row = annotating
    ? <AnnotationToolbar annotation={annotation} colorScheme={colorScheme} placements={false} />
    : measuring ? <MeasurementsBar measure={measure} /> : null;
  return { strip, row };
}

/**
 * @param {{ surface: object, containerRef: import("react").RefObject<HTMLDivElement>,
 *   busy: boolean, children: import("react").ReactNode, file: string, mobile: boolean, compact: boolean,
 *   chromeHidden: boolean, loading: boolean, loadingLabel: string, updating: boolean, updateStatus: { pending: boolean, label: string },
 *   tools: object[], toolRow?: import("react").ReactNode, views?: object[],
 *   panel?: { kind: string, label: string, searchLabel: string, searchPlaceholder: string, tabs: { id: string, label: string, content: import("react").ReactNode }[] } | null,
 *   panelControl?: { current: object | null }, viewControls?: import("react").ReactNode,
 *   toolStack: object, onToolStackChange(patch: object): void, notice?: import("react").ReactNode,
 *   quickEdit: object | null, alert: object | null, cardAlert: object | null, alertDismissal: { dismissed: boolean, dismiss(): void },
 *   shown: boolean, onReload?: () => void }} props
 *   `surface`: the frame's own data attributes, which say what is drawn (`{ "data-drawing-surface": "" }`).
 *   `quickEdit`: null for a view whose picture has nothing a note could carry.
 */
export default function FlatViewFrame({ surface, containerRef, busy, children, file, mobile, compact, chromeHidden, loading, loadingLabel,
  updating, updateStatus, tools, toolRow = null, views = undefined, panel = null, panelControl = null, viewControls = null, toolStack, onToolStackChange, notice = null, quickEdit,
  alert, cardAlert, alertDismissal, shown, onReload }) {
  const toolsHidden = chromeHidden || compact;
  const sided = Boolean(panel?.tabs.length);
  const besideSidebarTile = mobile && sided;

  // ---- the panel: docked, or on a phone the whole view; open at first in a wide view ----
  const frameRef = useRef(null);
  const [frameWidth, setFrameWidth] = useState(0);
  useLayoutEffect(() => {
    const element = frameRef.current;
    if (!element) return undefined;
    const measure = () => setFrameWidth(Math.round(element.getBoundingClientRect().width));
    measure();
    if (typeof ResizeObserver === "undefined") return undefined;
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  // Unmeasured (jsdom), a view is wide.
  const mode = mobile ? "page" : "docked";
  const docked = mode === "docked";
  // In a wide view it is the person's, kept; narrower, and on a phone, it starts collapsed each time.
  const kept = docked && !(frameWidth && frameWidth < FLAT_PANEL_OPEN_PX);
  const [sessionOpen, setSessionOpen] = useState(false);
  useEffect(() => { setSessionOpen(false); }, [kept, mode]);
  // The layout as the person last changed it here, the host's store's once it answers (a host
  // without one keeps it for as long as the view is open).
  const [layout, setLayout] = useState(toolStack);
  useEffect(() => { setLayout(toolStack); }, [toolStack]);
  const changeStack = useCallback(patch => {
    setLayout(current => ({ ...current, ...patch(current) }));
    onToolStackChange(patch);
  }, [onToolStackChange]);
  const open = sided && !toolsHidden && (kept ? layout?.collapsed?.[FLAT_PANEL_ID] !== true : sessionOpen);
  const setOpen = useCallback(next => {
    if (!kept) { setSessionOpen(next); return; }
    changeStack(current => {
      const collapsed = { ...current?.collapsed };
      if (next) delete collapsed[FLAT_PANEL_ID]; else collapsed[FLAT_PANEL_ID] = true;
      return { collapsed };
    });
  }, [kept, changeStack]);
  const tabs = panel?.tabs ?? [];
  const storedTab = panel ? layout?.tabs?.[panel.kind] : undefined;
  const tab = tabs.some(entry => entry.id === storedTab) ? storedTab : tabs[0]?.id;
  const changeTab = id => changeStack(current => ({ tabs: { ...current?.tabs, [panel.kind]: id } }));
  const maxWidth = Math.max(FLAT_PANEL_MIN_WIDTH, Math.floor((frameWidth || 2 * FLAT_PANEL_DEFAULT_WIDTH) / 2));
  const width = layout?.panels?.[FLAT_PANEL_ID]?.width ?? FLAT_PANEL_DEFAULT_WIDTH;
  const changeWidth = next => changeStack(current => ({ panels: { ...current?.panels, [FLAT_PANEL_ID]: { width: next } } }));
  const [focusSearch, setFocusSearch] = useState(0);
  // The keys (`useFlatHandover`): ⌘\ shows or hides the panel, / opens it on its search.
  const openRef = useRef(open);
  openRef.current = open;
  if (panelControl) {
    panelControl.current = sided && !toolsHidden ? {
      toggle: () => setOpen(!openRef.current),
      search: () => { setOpen(true); setFocusSearch(count => count + 1); return true; }
    } : null;
  }
  const status = updating && !alert ? <div className="pointer-events-none flex max-w-full items-center" data-viewport-status="">
    <ViewUpdateStatus status={updateStatus} className="rounded-md bg-background/95 px-1 py-0.5 shadow-sm" />
  </div> : null;

  // The strip's column is measured into the canvas's variables, as every view's is: the top-right
  // corner (Quick Edit) starts past its right.
  const stageRef = useRef(null);
  const topControls = useRef(null);
  // How far the canvas starts from the view's left edge (the docked panel's width, open): the strip
  // reaches back by that much, so it stands at the view's centre whether the panel is open or not.
  const [stageLeft, setStageLeft] = useState(0);
  useLayoutEffect(() => {
    const stage = stageRef.current, frame = frameRef.current;
    if (!stage || !frame) return undefined;
    const measure = () => setStageLeft(Math.round(stage.getBoundingClientRect().left - frame.getBoundingClientRect().left));
    measure();
    if (typeof ResizeObserver === "undefined") return undefined;
    const observer = new ResizeObserver(measure);
    observer.observe(stage);
    return () => observer.disconnect();
  }, []);
  useLayoutEffect(() => {
    const controls = topControls.current, viewport = stageRef.current, frame = frameRef.current;
    if (!controls || !viewport || !frame) return undefined;
    const measureColumn = () => {
      const rows = [...controls.children].map(row => row.getBoundingClientRect()).filter(box => box.height > 0);
      const top = controls.getBoundingClientRect().top;
      // On the frame, where the canvas view's fit reads it (`useFlatCanvasView.js`).
      frame.style.setProperty("--cad-tools-bottom", `${Math.round(VIEWPORT_INSET_PX * 2 + Math.max(top, ...rows.map(box => box.bottom)) - top)}px`);
      if (mobile || !rows.length) {
        viewport.style.removeProperty("--cad-file-sidebar-max-width");
        viewport.style.removeProperty("--cad-top-right-left");
        return;
      }
      const box = viewport.getBoundingClientRect();
      const left = Math.min(...rows.map(row => row.left)) - box.left, right = Math.max(...rows.map(row => row.right)) - box.left;
      viewport.style.setProperty("--cad-file-sidebar-max-width", `${Math.max(0, Math.round(left - 2 * VIEWPORT_INSET_PX))}px`);
      viewport.style.setProperty("--cad-top-right-left", `${Math.round(right + VIEWPORT_INSET_PX)}px`);
    };
    measureColumn();
    if (typeof ResizeObserver === "undefined") return undefined;
    const resized = new ResizeObserver(measureColumn);
    resized.observe(controls);
    resized.observe(viewport);
    return () => {
      resized.disconnect();
      frame.style.removeProperty("--cad-tools-bottom");
      for (const name of ["--cad-file-sidebar-max-width", "--cad-top-right-left"]) viewport.style.removeProperty(name);
    };
  }, [toolsHidden, mobile, sided, open, docked]);

  const panelNode = sided && !toolsHidden ? <FlatPanel mode={mode} open={open} onClose={() => setOpen(false)} label={panel.label}
    searchLabel={panel.searchLabel} searchPlaceholder={panel.searchPlaceholder} tabs={tabs} tab={tab} onTabChange={changeTab}
    width={width} maxWidth={maxWidth} onWidthChange={changeWidth} focusSearch={focusSearch} /> : null;

  return (
    <div ref={frameRef} className="relative flex h-full min-h-0 flex-row overflow-hidden bg-background text-foreground"
      data-slot="cad-file-view" {...surface} data-cad-scene-backdrop="" tabIndex={-1}
      onPointerDownCapture={event => { if (event.target instanceof Element && event.target.closest("canvas")) event.currentTarget.focus({ preventScroll: true }); }}>
      {docked ? panelNode : null}
      <div ref={stageRef} className="@container/cad-viewport relative flex min-h-0 min-w-0 flex-1 flex-col" data-flat-stage="">
        <div ref={containerRef} className="relative min-h-0 flex-1" aria-busy={busy ? "true" : "false"}>{children}</div>
        <PreviewChrome active={false}>
          {toolsHidden ? null : <div className={cn("pointer-events-none absolute z-20 flex flex-col gap-2", besideSidebarTile ? "items-start" : "items-center")}
            style={besideSidebarTile ? TOOLBAR_POSITION_PHONE_SIDEBAR : { ...TOOLBAR_POSITION, left: `${VIEWPORT_INSET_PX - stageLeft}px` }} data-mobile={mobile ? "" : undefined} data-cad-tool-groups="">
            <StripTouchProvider value={mobile}>
              <div ref={topControls} className={cn("flex max-w-full shrink-0 flex-col gap-2", besideSidebarTile ? "items-start" : "items-center")} data-cad-top-controls="">
                <FloatingToolBar tools={tools} views={views} touch={mobile} />
                {toolRow}
                {status}
              </div>
            </StripTouchProvider>
          </div>}
          {/* The top-right: the host's notice once the picture is on screen, and Quick Edit under it —
              hidden, not unmounted, while the picture loads: a note being written outlives a reload. */}
          <ViewportTopRight notice={chromeHidden ? null : notice}>
            {compact || !quickEdit ? null : <QuickEdit key={file} className="self-stretch" hidden={chromeHidden} docked={mobile} {...quickEdit} />}
          </ViewportTopRight>
        </PreviewChrome>
        {/* The view cluster: how the picture is drawn, apart from the strip's tools, at the canvas's
            bottom-right (on a phone, just over Quick Edit's peek). */}
        {viewControls && !toolsHidden ? <StripTouchProvider value={mobile}><div className="pointer-events-none absolute z-20 flex"
          style={{ right: INSET, bottom: mobile ? `calc(var(--cad-quick-edit-peek, 0px) + ${INSET})` : INSET }} data-cad-view-cluster="">
          {viewControls}
        </div></StripTouchProvider> : null}
        {/* Collapsed, the panel's expand button, alone on a pill at the canvas's top-left. */}
        {sided && !toolsHidden && !open ? <FlatPanelPill touch={mobile} onOpen={() => setOpen(true)} /> : null}
        {/* Where there is no strip (a compact host), the picture catching up says so at the top centre. */}
        {toolsHidden && updating && !alert ? <div className="pointer-events-none absolute left-1/2 z-30 flex max-w-[calc(100%-1rem)] -translate-x-1/2 items-center"
          style={{ top: VIEWPORT_INSET_PX, height: VIEWPORT_TOP_BAR_PX }} data-viewport-status="">
          <ViewUpdateStatus status={updateStatus} className="rounded-md bg-background/95 px-1 py-0.5 shadow-sm" />
        </div> : null}
        <ViewerLoadingOverlay loading={{ opening: loading && !alert, progress: { label: loadingLabel } }} operationKey={file} />
        <ViewerAlertCard alert={cardAlert} hasContent={shown} dismissed={alertDismissal.dismissed} onDismiss={alertDismissal.dismiss} onReload={onReload} file={file} />
      </div>
      {mode === "page" ? panelNode : null}
    </div>
  );
}
