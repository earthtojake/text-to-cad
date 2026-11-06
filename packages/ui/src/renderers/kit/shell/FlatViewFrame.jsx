import { english, useI18n } from "@cad/ui/i18n";
import { MousePointer2 } from "lucide-react";
import { AnnotationToolbar, DRAWING_TOOLS, annotationToolIcon, drawingToolVariant, drawingToolLabel } from "../../../annotation/toolbar.jsx";
import { ViewUpdateStatus } from "../status/ViewUpdateStatus.jsx";
import { MeasureIcon } from "../tools/measure/SceneMeasure.jsx";
import { MeasurementsBar } from "../tools/measure/measurementChips.jsx";
import QuickEdit from "../tools/quick-edit/QuickEdit.jsx";
import { DRAWING_SHORTCUTS, TOOL_SHORTCUTS } from "../tools/toolShortcuts.js";
import { FLAT_TOOL } from "./useFlatView.js";
import ViewFrame from "./ViewFrame.jsx";
import ZoomPill, { zoomViewControl } from "./ZoomControl.jsx";
import { ViewCornerRow, ViewCubeColumn } from "./ViewCorner.jsx";
import { VIEWPORT_CUBE_COLUMN_POSITION, VIEWPORT_PILL_POSITION } from "./viewportLayout.js";

/**
 * A FLAT view's frame — a picture on a canvas, head on (a board, a schematic, a drawing) — which is
 * every view's (`ViewFrame.jsx`) with what a flat view puts in it: its strip (`flatViewTools`), its
 * update under the strip, Quick Edit (`useFlatHandover`'s `quickEdit`), its panel's tabs (`panel`),
 * and its corner: the view's own controls on the bottom row (`views`' `corner`s, `ViewCorner.jsx`)
 * beside its zoom pill, or, while the picture is shown in 3D, the 3D views' column over the cube. On a
 * phone those are rows of the strip's More, with the zoom. The renderer brings the picture (its
 * canvases and layers, `children`, in the box the canvas view measures: `containerRef`).
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
 *   panel?: { kind: string, label: string, searchLabel: string, tabs: { id: string, label: string, content: import("react").ReactNode }[],
 *     detail?: import("react").ReactNode } | null,
 *   panelControl?: { current: object | null },
 *   toolStack: object, onToolStackChange(patch: object): void, notice?: import("react").ReactNode,
 *   quickEdit: object | null, alert: object | null, cardAlert: object | null, alertDismissal: { dismissed: boolean, dismiss(): void },
 *   shown: boolean, onReload?: () => void, canvasRef?: import("react").RefObject<HTMLCanvasElement>,
 *   contextMenuItems?: ((press: { clientX: number, clientY: number, shiftKey: boolean }) => object[] | null) | null }} props
 *   `surface`: the frame's own data attributes, which say what is drawn (`{ "data-drawing-surface": "" }`).
 *   `quickEdit`: null for a view whose picture has nothing a note could carry.
 *   `zoom`: the view's zoom (`ZoomControl.jsx`'s): the corner's pill, at the bottom-right where a 3D view's cube stands,
 *   and the zoom's keys either way.
 *   A view control's `corner` is its control on the corner's bottom row, left of the pill (a button, a switch).
 *   `corner`: "pill", or "cube" while the picture is shown in 3D: the view the frame holds draws the cube
 *   (`ShellViewport.jsx`'s), and the frame puts every 3D view's column over it (`ViewCorner.jsx`'s `ViewCubeColumn`:
 *   Projection, `cube.projection`, and Home, `cube.onHome`). Nothing else of the frame changes.
 *   `contextMenuItems`: the view's menu on a secondary tap over its canvas (`canvasRef`), every view's
 *   (`ViewportContextMenu.jsx`, its entries `viewMenu.js`'s); a right drag still pans.
 */
export default function FlatViewFrame({ surface, containerRef, busy, children, file, mobile, compact, chromeHidden, loading, loadingLabel,
  updating, updateStatus, tools, toolRow = null, views = undefined, panel = null, panelControl = null, toolStack, onToolStackChange, notice = null, quickEdit,
  alert, cardAlert, alertDismissal, shown, onReload, canvasRef = null, contextMenuItems = null, zoom = null,
  corner = "pill", cube = null }) {
  const { t } = useI18n();
  const status = updating && !alert ? <div className="pointer-events-none flex max-w-full items-center" data-viewport-status="">
    <ViewUpdateStatus status={updateStatus} className="rounded-md bg-background/95 px-1 py-0.5 shadow-sm" />
  </div> : null;
  // The view's corner: its own controls on the bottom row, then its zoom pill, or, while the picture
  // is shown in 3D, the cube (the 3D view's own) with Projection and Home over it. The row stands where
  // it stands either way. A phone's are More's.
  const cornerNode = !shown || !zoom ? null : <>
    {views?.some(view => view.corner) ? <ViewCornerRow>
      {views.map(view => (view.corner ? <span key={view.id} className="contents">{view.corner}</span> : null))}
    </ViewCornerRow> : null}
    {corner === "cube" && cube ? <ViewCubeColumn style={VIEWPORT_CUBE_COLUMN_POSITION} projection={cube.projection} onHome={cube.onHome} />
      : <ZoomPill zoom={zoom} style={VIEWPORT_PILL_POSITION} />}
  </>;
  return (
    <ViewFrame surface={surface} canvasBoxRef={containerRef} busy={busy} file={file} mobile={mobile} compact={compact} chromeHidden={chromeHidden}
      tools={tools} views={mobile ? [...(views || []), ...(zoom && shown ? [zoomViewControl(zoom, { t })] : [])] : []} toolRow={toolRow} status={status}
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
