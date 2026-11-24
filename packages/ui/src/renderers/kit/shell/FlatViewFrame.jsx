import { english } from "@cad/ui/i18n";
import { MousePointer2 } from "lucide-react";
import { AnnotationToolbar, drawStripTool } from "../../../annotation/toolbar.jsx";
import { MeasureIcon } from "../tools/measure/SceneMeasure.jsx";
import { MeasurementsBar } from "../tools/measure/measurementChips.jsx";
import { ToolModeIcon } from "../tools/select/modeGlyphs.jsx";
import QuickEdit from "../tools/quick-edit/QuickEdit.jsx";
import { TOOL_SHORTCUTS } from "../tools/toolShortcuts.js";
import { FLAT_TOOL } from "./useFlatView.js";
import ViewFrame from "./ViewFrame.jsx";
import ZoomPill from "./ZoomControl.jsx";
import NavbarViewControls from "./NavbarViewControls.jsx";
import { useDisplaySettings } from "./DisplaySettings.jsx";

/**
 * A FLAT view's frame — a picture on a canvas, head on (a board, a schematic, a drawing) — which is
 * every view's (`ViewFrame.jsx`) with what a flat view puts in it: its strip (`flatViewTools`), Display in the
 * navbar (`viewGroups`), its update under the strip, Quick Edit (`useFlatHandover`'s `quickEdit`), its panel's tabs
 * (`panel`), and its corner, at the top-right: the zoom (`ZoomControl.jsx`) alone, the same corner while the picture is
 * shown in 3D, whose zoom it then is. The renderer brings the picture (its canvases and layers, `children`, in the box
 * the canvas view measures: `containerRef`). A flat view whose picture can be shown in 3D, lit, offers Preview
 * (`preview`, `usePreviewFrame.jsx`'s result, through `useFlatPreview.jsx`): its button after Display, in the navbar,
 * and while it is up the frame's Preview chrome, view and cover, exactly a 3D view's.
 *
 * The panel, the strip at the view's centre, the measure, the loading cover and the card are the
 * frame's, the same as a 3D view's: see `ViewFrame.jsx`. ⌘\ (Ctrl+\) shows and hides the panel,
 * and / opens it on its search (`useFlatHandover`'s `panelControl`, which the frame fills in).
 */

const SELECT_ICON = <MousePointer2 className="size-3" strokeWidth={2} aria-hidden="true" />;
const MEASURE_ICON = <MeasureIcon className="size-3.5" aria-hidden="true" />;


/**
 * A flat view's strip, Select, Draw and Measure, each with its key, and the row of the
 * tool in hand under it: the drawing tools' (their tools, colours and widths) or Measure's (its
 * measurements, while there are any); Select has none. `selectMenu`: Select's filter, the chevron
 * after its button, where the view offers one; `selectBadge`, the badge its button wears for what the
 * filter ticks (`selectFilter.js`'s `filterBadge`: none for "all").
 *
 * @param {ReturnType<typeof import("./useFlatView.js").useFlatTools>} tools
 * @param {{ colorScheme: "light" | "dark", shown: boolean, t?: Function, selectMenu?: import("react").ReactNode, selectBadge?: string }} options
 */
export function flatViewTools(tools, { colorScheme, shown, selectMenu = null, selectBadge = "all", t = english }) {
  const { toolMode, selectTool, annotation, annotating, measuring, measure, toolKeys } = tools;
  const stripTool = (id, label, icon, extra = {}) => ({ id, label, icon, active: toolMode === id, disabled: !shown, onSelect: () => selectTool(id), ...extra });
  const strip = [
    stripTool(FLAT_TOOL.SELECT, t("tool.select"), selectBadge === "all" ? SELECT_ICON
      : <ToolModeIcon tool="select" mode={selectBadge} className="size-3" aria-hidden="true" />, { shortcut: TOOL_SHORTCUTS.select, ...(selectMenu ? { menu: selectMenu } : {}) }),
    // Draw: one plain button over the `pencil` and `shapes` modes, no menu (`drawStripTool`): its tools are the rows under the strip.
    drawStripTool({ toolMode, annotation, takeFamily: family => selectTool(family), disabled: !shown, t }),
    stripTool(FLAT_TOOL.MEASURE, t("tool.measure"), MEASURE_ICON, { shortcut: TOOL_SHORTCUTS.measure })
  ];
  toolKeys.current = strip;
  const row = annotating
    ? <AnnotationToolbar annotation={annotation} colorScheme={colorScheme} placements={false} takeFamily={family => selectTool(family)} />
    : measuring ? <MeasurementsBar measure={measure} /> : null;
  return { strip, row };
}

/**
 * @param {{ surface: object, containerRef: import("react").RefObject<HTMLDivElement>,
 *   busy: boolean, children: import("react").ReactNode, file: string, mobile: boolean, compact: boolean,
 *   chromeHidden: boolean, failed?: boolean, loading: boolean, loadingLabel: string, updating: boolean, updateStatus: { pending: boolean, label: string },
 *   tools: object[], toolRow?: import("react").ReactNode,
 *   panel?: { kind: string, label: string, searchLabel: string, tabs: { id: string, label: string, content: import("react").ReactNode }[] } | null,
 *   inspect?: import("../inspector/inspect.js").Inspect | null,
 *   panelControl?: { current: object | null },
 *   toolStack: object, onToolStackChange(patch: object): void, notice?: import("react").ReactNode,
 *   quickEdit: object | null, alert: object | null, cardAlert: object | null, alertDismissal: { dismissed: boolean, dismiss(): void },
 *   shown: boolean, onReload?: () => void, canvasRef?: import("react").RefObject<HTMLCanvasElement>,
 *   contextMenuItems?: ((press: { clientX: number, clientY: number, shiftKey: boolean }) => object[] | null) | null }} props
 *   `surface`: the frame's own data attributes, which say what is drawn (`{ "data-drawing-surface": "" }`).
 *   `quickEdit`: null for a view whose picture has nothing a note could carry.
 *   `inspect`: what is picked and how the view describes it: Quick Edit's chips' cards and the frame's hover tip (`ViewFrame.jsx`).
 *   `zoom`: the view's zoom (`ZoomControl.jsx`'s): the corner's one control, at the top-right where a 3D view's cube
 *   stands, and the zoom's keys either way; while the picture is shown in 3D, the 3D view's (`viewportZoom`).
 *   `viewGroups`: the view's settings as Display's card draws them (`DisplaySettings.jsx`: a board's Side, Mode, in 3D
 *   Projection, then Style and Background; a drawing's Background): the navbar's Display. `onResetDisplay`: the card's
 *   Reset, where the view has settings of its own to put back (a board's).
 *   `contextMenuItems`: the view's menu on a secondary tap over its canvas (`canvasRef`), every view's
 *   (`ViewportContextMenu.jsx`, its entries `viewMenu.js`'s); a right drag still pans.
 *   `preview`: Preview, for a view that can offer it (`useFlatPreview.jsx`'s result: `offered`, whether this file does;
 *   `frame`, what `ViewFrame` takes while it is up; `navbarButton`, its button; `rootRef`, the frame's
 *   root, where its chrome watches the pointer); null or omitted, or not `offered`, the view has no Preview at all.
 */
export default function FlatViewFrame({ surface, containerRef, busy, children, file, mobile, compact, chromeHidden, failed = undefined, loading, loadingLabel,
  updating, updateStatus, tools, toolRow = null, panel = null, panelControl = null, toolStack, onToolStackChange, notice = null, quickEdit,
  alert, cardAlert, alertDismissal, shown, onReload, canvasRef = null, contextMenuItems = null, zoom = null, inspect = null, viewport = null,
  viewGroups = null, onResetDisplay = null, preview = null }) {
  // The picture catching up: said as every view says it (`ViewFrame.jsx`'s status). A flat view's update
  // has nothing of its own to retry: one that fails is the card's, whose Retry reloads the file.
  const status = { update: updating ? updateStatus : null };
  // The view's settings are Display's (`DisplaySettings.jsx`): the navbar's button and its card, docked at the view's
  // right edge, the same on a desktop and a phone. The corner holds the zoom alone, the same whether the picture is
  // drawn flat or in 3D (a phone's none).
  const previewing = Boolean(preview?.previewing);
  const display = useDisplaySettings({ groups: shown && viewGroups ? viewGroups : [], onReset: onResetDisplay, closeKey: file, closed: previewing });
  // Preview, where the view offers it, after Display.
  const previewOffered = Boolean(preview?.offered);
  const navbarNode = shown && viewGroups ? <NavbarViewControls>
    {display.navbarButton}
    {previewOffered ? preview.navbarButton : null}
  </NavbarViewControls> : null;
  const cornerNode = shown && zoom ? <ZoomPill zoom={zoom} /> : null;
  return (
    <ViewFrame rootRef={preview?.rootRef ?? null} surface={surface} viewport={viewport} canvasBoxRef={containerRef} busy={busy} file={file} mobile={mobile} compact={compact} chromeHidden={chromeHidden} failed={failed}
      selecting={!preview?.previewing && (!tools.length || tools.some(tool => tool.id === FLAT_TOOL.SELECT && tool.active))} inspect={inspect} {...preview?.frame}
      tools={tools} toolRow={toolRow} status={status}
      panel={panel?.tabs.length ? panel : null} panelControl={panelControl} layout={toolStack} onLayoutChange={onToolStackChange}
      corner={cornerNode} navbar={navbarNode} card={display.card} notice={notice}
      quickEdit={quickEdit ? <QuickEdit key={file} className="self-stretch" hidden={chromeHidden} docked={mobile} {...quickEdit} /> : null}
      contextMenu={canvasRef && contextMenuItems ? { viewport: { hostRef: containerRef, canvasRef }, items: contextMenuItems } : null}
      loading={{ opening: loading && !alert, progress: { label: loadingLabel } }}
      alert={{ alert: cardAlert, hasContent: shown, dismissed: alertDismissal.dismissed, onDismiss: alertDismissal.dismiss, onReload }}>
      {children}
    </ViewFrame>
  );
}
