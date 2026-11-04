/**
 * What a person is pointing at, drawn over a schematic's sheet: what is isolated, the hovered thing and
 * the selection, over the picture in the same pass, so a capture of the view shows them.
 *
 * Each thing is the sheet's own ink (`schematicIndex.js`'s `itemsOf`: the drawn items of a part, a pin,
 * a net, a label, a wire, a sheet), drawn again: under it a soft shadow, as KiCad shadows what it
 * selects, then the ink itself in the selection's blue. A net or what is isolated steps the rest of the
 * sheet back first — the paper laid over it, faint — as KiCad's net highlight does, and an isolated
 * thing is drawn again in its own colours. Widths are screen pixels, as the person reads them, at any
 * zoom. Pure canvas 2D, in page millimetres (`plot2d`'s page space).
 */
import { schematicItemColor } from "../plot2d/theme.js";

/** The schematic's highlight on its paper: the viewer's blue, dark enough to read on it. */
export const SCHEMATIC_OVERLAY_COLORS = Object.freeze({
  selection: "#1f6feb",
  shadow: "rgba(31, 111, 235, 0.28)",
  hover: "rgba(31, 111, 235, 0.22)",
  // The paper over what steps back.
  dim: "rgba(245, 244, 239, 0.72)",
  draft: "rgba(31, 111, 235, 0.08)",
  draftEdge: "rgba(31, 111, 235, 0.7)"
});
// How far a shadow reaches past its ink, in screen pixels, and an ink's least width.
const SHADOW_PX = 3;
const INK_PX = 1.5;

function pageSpace(ctx, transform, pixelRatio) {
  const s = transform.scale * pixelRatio;
  ctx.setTransform(s, 0, 0, s, transform.offsetX * pixelRatio, transform.offsetY * pixelRatio);
}

function trace(ctx, item) {
  ctx.beginPath();
  if (item.t === "circle") {
    ctx.moveTo(item.at[0] + item.r, item.at[1]);
    ctx.arc(item.at[0], item.at[1], item.r, 0, Math.PI * 2);
    return;
  }
  const lines = item.t === "text" ? item.strokes : [item.pts];
  for (const points of lines) {
    if (item.pairs) {
      for (let index = 0; index + 1 < points.length; index += 2) {
        ctx.moveTo(points[index][0], points[index][1]);
        ctx.lineTo(points[index + 1][0], points[index + 1][1]);
      }
      continue;
    }
    ctx.moveTo(points[0][0], points[0][1]);
    for (let index = 1; index < points.length; index += 1) ctx.lineTo(points[index][0], points[index][1]);
    if (item.t === "poly" || item.closed) ctx.closePath();
  }
}

const filled = (item) => item.t === "poly" || (item.t === "circle" && item.w === 0);

/** Draw `entries` (`{ item, kind }`) in `color`, `extra` screen pixels wider than their ink; a fill as a fill. */
function ink(ctx, entries, { color, extra = 0, own = false, px, visible }) {
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  for (const { item, kind } of entries) {
    if (visible && !(item.box[0] <= visible[2] && item.box[2] >= visible[0] && item.box[1] <= visible[3] && item.box[3] >= visible[1])) continue;
    const paint = own ? schematicItemColor(kind, item) : color;
    // A symbol body's background is lit by its outline, never filled over.
    if (!own && item.t === "poly" && item.fill === "background") continue;
    trace(ctx, item);
    if (filled(item)) {
      ctx.fillStyle = paint;
      ctx.fill();
      if (extra > 0) { ctx.strokeStyle = paint; ctx.lineWidth = extra * px; ctx.stroke(); }
      continue;
    }
    ctx.strokeStyle = paint;
    ctx.lineWidth = Math.max(item.w || 0, INK_PX * px) + extra * px;
    ctx.stroke();
  }
}

/**
 * @param {CanvasRenderingContext2D} ctx
 * @param {{ width: number, height: number, x?: number, y?: number }} sheet  The drawn sheet (its paper).
 * @param {{ transform: { scale: number, offsetX: number, offsetY: number }, pixelRatio?: number, width?: number, height?: number,
 *   hovered?: readonly object[], selected?: readonly object[], isolated?: readonly object[], dim?: boolean,
 *   draft?: readonly [number, number, number, number] | null }} options
 *   `hovered`, `selected`, `isolated`: drawn entries (`{ item, kind }`); `dim`: the rest of the sheet stepped back
 *   (a net selected); `draft`: Select's box being dragged, page millimetres.
 */
export function drawSchematicOverlay(ctx, sheet, { transform, pixelRatio = 1, width = 0, height = 0, hovered = [], selected = [], isolated = [],
  dim = false, draft = null }) {
  if (!transform) return;
  const px = 1 / transform.scale;
  const visible = width > 0 && height > 0
    ? [-transform.offsetX * px, -transform.offsetY * px, (width - transform.offsetX) * px, (height - transform.offsetY) * px] : null;
  ctx.save();
  pageSpace(ctx, transform, pixelRatio);
  if (isolated.length || dim) {
    ctx.fillStyle = SCHEMATIC_OVERLAY_COLORS.dim;
    ctx.fillRect(sheet.x || 0, sheet.y || 0, sheet.width, sheet.height);
    if (isolated.length) ink(ctx, isolated, { own: true, px, visible });
  }
  if (hovered.length) ink(ctx, hovered, { color: SCHEMATIC_OVERLAY_COLORS.hover, extra: SHADOW_PX * 2, px, visible });
  if (selected.length) {
    ink(ctx, selected, { color: SCHEMATIC_OVERLAY_COLORS.shadow, extra: SHADOW_PX * 2, px, visible });
    ink(ctx, selected, { color: SCHEMATIC_OVERLAY_COLORS.selection, px, visible });
  }
  if (draft) {
    const [x0, y0, x1, y1] = draft;
    ctx.fillStyle = SCHEMATIC_OVERLAY_COLORS.draft;
    ctx.fillRect(x0, y0, x1 - x0, y1 - y0);
    ctx.strokeStyle = SCHEMATIC_OVERLAY_COLORS.draftEdge;
    ctx.lineWidth = px;
    ctx.strokeRect(x0, y0, x1 - x0, y1 - y0);
  }
  ctx.restore();
}

