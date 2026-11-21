import { Fragment } from "react";
import { english, useI18n } from "@cad/ui/i18n";
import { MousePointer2 } from "lucide-react";
import { AnnotationToolbar, drawStripTool } from "../../../annotation/toolbar.jsx";
import { MeasureIcon } from "../tools/measure/SceneMeasure.jsx";
import { MeasurementsBar } from "../tools/measure/measurementChips.jsx";
import { ToolModeIcon } from "../tools/select/modeGlyphs.jsx";
import QuickEdit from "../tools/quick-edit/QuickEdit.jsx";
import { TOOL_SHORTCUTS } from "../tools/toolShortcuts.js";
import { FLAT_TOOL } from "./useFlatView.js";
import ViewFrame from "./ViewFrame.jsx";
import ZoomPill, { zoomViewControl } from "./ZoomControl.jsx";
import ViewCornerStack from "./ViewCornerStack.jsx";
import NavbarViewControls, { useNavbarViewControls } from "./NavbarViewControls.jsx";
import { ViewMenu } from "./ViewSettingsMenu.jsx";

/**
 * A FLAT view's frame — a picture on a canvas, head on (a board, a schematic, a drawing) — which is
 * every view's (`ViewFrame.jsx`) with what a flat view puts in it: its strip (`flatViewTools`), ended
 * after its rule by the view's own controls (`views`' `tile`s, where they have no place in the corner), its
 * update under the strip, Quick Edit (`useFlatHandover`'s `quickEdit`), its panel's tabs (`panel`), and
 * its corner, at the top-right: the zoom pill (`ZoomControl.jsx`) and under it the corner's stack (a board's Display, side and 2D/3D),
 * the same corner while the picture is shown in 3D, whose zoom the pill then is (Home then in the stack too). On a phone the view's controls are rows of the strip's More, with the
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
    // Draw: one button over Pencil's and Shapes' modes, its menu every drawing tool (`drawStripTool`).
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
 *   `zoom`: the view's zoom (`ZoomControl.jsx`'s): the corner's pill, at the top-right where a 3D view's cube stands,
 *   and the zoom's keys either way; while the picture is shown in 3D, the 3D view's (`viewportZoom`).
 *   `views`: the view's own controls (`FloatingToolBar.js`'s `ViewportViewControl`s), left to right at the strip's end; one
 *   with a `cornerTile` stands in the corner's stack instead on a desktop (`ViewCornerStack.jsx`).
 *   `viewGroups`: the view's settings as the navbar's View draws them (`ViewSettingsMenu.jsx`: a board's Side, Mode, Display and
 *   Background, a drawing's Background), under a file's navbar in place of `views`' corner tiles; `onResetView`, a
 *   phone's View menu's Reset view (a fit, or a board's 3D Home).
 *   `contextMenuItems`: the view's menu on a secondary tap over its canvas (`canvasRef`), every view's
 *   (`ViewportContextMenu.jsx`, its entries `viewMenu.js`'s); a right drag still pans.
 */
export default function FlatViewFrame({ surface, containerRef, busy, children, file, mobile, compact, chromeHidden, failed = undefined, loading, loadingLabel,
  updating, updateStatus, tools, toolRow = null, views = undefined, panel = null, panelControl = null, toolStack, onToolStackChange, notice = null, quickEdit,
  alert, cardAlert, alertDismissal, shown, onReload, canvasRef = null, contextMenuItems = null, zoom = null, inspect = null, viewport = null,
  viewGroups = null, onResetView = null }) {
  const { t } = useI18n();
  // The picture catching up: said as every view says it (`ViewFrame.jsx`'s status). A flat view's update
  // has nothing of its own to retry: one that fails is the card's, whose Retry reloads the file.
  const status = { update: updating ? updateStatus : null };
  // The view's corner: its zoom pill, the same whether the picture is drawn flat or in 3D. A phone's zoom is More's.
  // Under it, the corner's stack (`ViewCornerStack.jsx`), as a 3D view's stands under its cube: the view's controls that
  // have a `cornerTile` (a board's Display, side, 2D/3D, and in 3D Home), by `cornerRank`. A phone keeps them as rows
  // of the strip's More. The rest end the strip.
  // Under a file's navbar they are the navbar's instead (`NavbarViewControls.jsx`): View ▾, the same menu on a desktop
  // and a phone (`ViewSettingsMenu.jsx`), and the zoom stands alone in the corner (a phone's none: gestures, and the
  // menu's Reset view). A camera control (a board's 3D Home) stays on a desktop's picture, beside the zoom.
  const inNavbar = useNavbarViewControls() && Boolean(viewGroups);
  const cornerViews = mobile ? [] : (views || []).filter(view => view.cornerTile).sort((a, b) => (a.cornerRank ?? 0) - (b.cornerRank ?? 0));
  const stripViews = inNavbar ? [] : mobile ? views || [] : (views || []).filter(view => !view.cornerTile);
  const cameraViews = cornerViews.filter(view => view.cornerCamera);
  const navbarNode = shown && inNavbar ? <NavbarViewControls>
    <ViewMenu groups={viewGroups} onReset={onResetView} />
  </NavbarViewControls> : null;
  const cornerNode = !shown ? null : <>
    {zoom ? <ZoomPill zoom={zoom} /> : null}
    {inNavbar ? cameraViews.length ? <ViewCornerStack under="pillHome">{place => cameraViews.map(view => <Fragment key={view.id}>{view.cornerTile(place)}</Fragment>)}</ViewCornerStack> : null
      : cornerViews.length ? <ViewCornerStack under={zoom ? "pill" : "cube"}>{place => cornerViews.map(view => <Fragment key={view.id}>{view.cornerTile(place)}</Fragment>)}</ViewCornerStack> : null}
  </>;
  return (
    <ViewFrame surface={surface} viewport={viewport} canvasBoxRef={containerRef} busy={busy} file={file} mobile={mobile} compact={compact} chromeHidden={chromeHidden} failed={failed}
      selecting={!tools.length || tools.some(tool => tool.id === FLAT_TOOL.SELECT && tool.active)} inspect={inspect}
      tools={tools} views={mobile && !inNavbar ? [...stripViews, ...(zoom && shown ? [zoomViewControl(zoom, { t })] : [])] : stripViews} toolRow={toolRow} status={status}
      panel={panel?.tabs.length ? panel : null} panelControl={panelControl} layout={toolStack} onLayoutChange={onToolStackChange}
      corner={cornerNode} navbar={navbarNode} notice={notice}
      quickEdit={quickEdit ? <QuickEdit key={file} className="self-stretch" hidden={chromeHidden} docked={mobile} {...quickEdit} /> : null}
      contextMenu={canvasRef && contextMenuItems ? { viewport: { hostRef: containerRef, canvasRef }, items: contextMenuItems } : null}
      loading={{ opening: loading && !alert, progress: { label: loadingLabel } }}
      alert={{ alert: cardAlert, hasContent: shown, dismissed: alertDismissal.dismissed, onDismiss: alertDismissal.dismiss, onReload }}>
      {children}
    </ViewFrame>
  );
}
