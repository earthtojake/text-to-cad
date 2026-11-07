import { english, useI18n } from "@cad/ui/i18n";
import { MousePointer2 } from "lucide-react";
import { AnnotationToolbar, DRAWING_TOOLS, annotationToolIcon, drawingToolVariant, drawingToolLabel } from "../../../annotation/toolbar.jsx";
import { MeasureIcon } from "../tools/measure/SceneMeasure.jsx";
import { MeasurementsBar } from "../tools/measure/measurementChips.jsx";
import QuickEdit from "../tools/quick-edit/QuickEdit.jsx";
import { DRAWING_SHORTCUTS, TOOL_SHORTCUTS } from "../tools/toolShortcuts.js";
import { FLAT_TOOL } from "./useFlatView.js";
import ViewFrame from "./ViewFrame.jsx";
import ZoomPill, { zoomViewControl } from "./ZoomControl.jsx";

/**
 * A FLAT view's frame — a picture on a canvas, head on (a board, a schematic, a drawing) — which is
 * every view's (`ViewFrame.jsx`) with what a flat view puts in it: its strip (`flatViewTools`), ended
 * after its rule by the view's own controls (`views`' `tile`s: a board's Flip, 2D/3D and Display), its
 * update under the strip, Quick Edit (`useFlatHandover`'s `quickEdit`), its panel's tabs (`panel`), and
 * its corner: the zoom pill alone (`ZoomControl.jsx`), the same corner while the picture is shown in 3D,
 * whose zoom the pill then is. On a phone the view's controls are rows of the strip's More, with the
 * zoom. The renderer brings the picture (its canvases and layers, `children`, in the box the canvas
 * view measures: `containerRef`).
 *
 * The panel, the strip at the view's centre, the measure, the loading cover and the card are the
 * frame's, the same as a 3D view's: see `ViewFrame.jsx`. ⌘\ (Ctrl+\) shows and hides the panel,
 * and / opens it on its search (`useFlatHandover`'s `panelControl`, which the frame fills in).
 */

const SELECT_ICON = <MousePointer2 className="size-3" strokeWidth={2} aria-hidden="true" />;
const MEASURE_ICON = <MeasureIcon className="size-3.5" aria-hidden="true" />;


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
 *   panel?: { kind: string, label: string, searchLabel: string, tabs: { id: string, label: string, content: import("react").ReactNode }[] } | null,
 *   inspect?: import("../inspector/inspect.js").Inspect | null,
 *   panelControl?: { current: object | null },
 *   toolStack: object, onToolStackChange(patch: object): void, notice?: import("react").ReactNode,
 *   quickEdit: object | null, alert: object | null, cardAlert: object | null, alertDismissal: { dismissed: boolean, dismiss(): void },
 *   shown: boolean, onReload?: () => void, canvasRef?: import("react").RefObject<HTMLCanvasElement>,
 *   contextMenuItems?: ((press: { clientX: number, clientY: number, shiftKey: boolean }) => object[] | null) | null }} props
 *   `surface`: the frame's own data attributes, which say what is drawn (`{ "data-drawing-surface": "" }`).
 *   `quickEdit`: null for a view whose picture has nothing a note could carry.
 *   `inspect`: what is picked and how the view describes it: the frame's Selected pane and hover tip (`ViewFrame.jsx`).
 *   `zoom`: the view's zoom (`ZoomControl.jsx`'s): the corner's pill, at the bottom-right where a 3D view's cube stands,
 *   and the zoom's keys either way; while the picture is shown in 3D, the 3D view's (`viewportZoom`).
 *   `views`: the view's own controls (`FloatingToolBar.js`'s `ViewportViewControl`s), left to right at the strip's end.
 *   `contextMenuItems`: the view's menu on a secondary tap over its canvas (`canvasRef`), every view's
 *   (`ViewportContextMenu.jsx`, its entries `viewMenu.js`'s); a right drag still pans.
 */
export default function FlatViewFrame({ surface, containerRef, busy, children, file, mobile, compact, chromeHidden, loading, loadingLabel,
  updating, updateStatus, tools, toolRow = null, views = undefined, panel = null, panelControl = null, toolStack, onToolStackChange, notice = null, quickEdit,
  alert, cardAlert, alertDismissal, shown, onReload, canvasRef = null, contextMenuItems = null, zoom = null, inspect = null }) {
  const { t } = useI18n();
  // The picture catching up: said as every view says it (`ViewFrame.jsx`'s status). A flat view's update
  // has nothing of its own to retry: one that fails is the card's, whose Retry reloads the file.
  const status = { update: updating ? updateStatus : null };
  // The view's corner: its zoom pill, the same whether the picture is drawn flat or in 3D. A phone's zoom is More's.
  const cornerNode = !shown || !zoom ? null : <ZoomPill zoom={zoom} />;
  return (
    <ViewFrame surface={surface} canvasBoxRef={containerRef} busy={busy} file={file} mobile={mobile} compact={compact} chromeHidden={chromeHidden}
      selecting={!tools.length || tools.some(tool => tool.id === FLAT_TOOL.SELECT && tool.active)} inspect={inspect}
      tools={tools} views={mobile ? [...(views || []), ...(zoom && shown ? [zoomViewControl(zoom, { t })] : [])] : views || []} toolRow={toolRow} status={status}
      panel={panel?.tabs.length ? panel : null} panelControl={panelControl} layout={toolStack} onLayoutChange={onToolStackChange}
      corner={cornerNode} notice={notice}
      quickEdit={quickEdit ? <QuickEdit key={file} className="self-stretch" hidden={chromeHidden} docked={mobile} {...quickEdit} /> : null}
      contextMenu={canvasRef && contextMenuItems ? { viewport: { hostRef: containerRef, canvasRef }, items: contextMenuItems } : null}
      loading={{ opening: loading && !alert, progress: { label: loadingLabel } }}
      alert={{ alert: cardAlert, hasContent: shown, dismissed: alertDismissal.dismissed, onDismiss: alertDismissal.dismiss, onReload }}>
      {children}
    </ViewFrame>
  );
}
