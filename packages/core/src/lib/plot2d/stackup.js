/**
 * What a board is made in: its stack-up's colours and its copper finish (`board.stackup`, the file's
 * `(setup (stackup ...))` as it names them: `docs/plot-payload.md`), resolved to the colours a 3D view
 * draws the made board in. They are KiCad's 3D viewer's with "Use board stackup colors"
 * (`3d-viewer/3d_canvas/board_adapter.cpp`, `GetLayerColors`): the same named colours, the same
 * defaults where the stack-up names none, the same reading of the finish (`kicad-cli pcb render
 * --use-board-stackup-colors` draws a board in these).
 *
 * - **Solder mask** (`F.Mask`, `B.Mask`): its named colour at KiCad's 83% opacity, so the copper under it
 *   shows faintly, as it does through real mask; `#RRGGBB[AA]` as written. A side the stack-up gives no
 *   mask layer is bare.
 * - **Silkscreen** (`F.SilkS`, `B.SilkS`): its named colour, opaque.
 * - **Substrate**: the dielectric layers' colours mixed as KiCad mixes them (each layer over the last by
 *   its own transparency), else KiCad's default board body.
 * - **Copper finish** for the copper: OSP copper, ENIG / ENEPIG / gold gold, HASL / tin / nickel tin, silver
 *   silver, anything else (and `None`) KiCad's default surface finish.
 *
 * A board whose stack-up names no colour and no finish (or that has none: an older board, a board KiCad
 * never saved a stack-up for) is not drawn as made: `boardFinish` answers null and the 3D view draws the
 * editor's layer colours, as before. The colours are the board's own, the same in either theme.
 *
 * Importing this module has no environmental effects.
 */

/** KiCad's solder mask opacity in its 3D view: the named mask colours' alpha. */
export const MASK_OPACITY = 0.83;

// KiCad's named colours (board_adapter.cpp's g_MaskColors, g_SilkColors, g_BoardColors, g_FinishColors), [r, g, b, a].
const MASK_COLORS = Object.freeze({
  "Green": [20, 51, 36], "Light Green": [91, 168, 12], "Saturated Green": [13, 104, 11], "Red": [181, 19, 21],
  "Light Red": [210, 40, 14], "Red/Orange": [239, 53, 41], "Blue": [2, 59, 162], "Light Blue 1": [54, 79, 116],
  "Light Blue 2": [61, 85, 130], "Green/Blue": [21, 70, 80], "Black": [11, 11, 11], "White": [245, 245, 245],
  "Purple": [32, 2, 53], "Light Purple": [119, 31, 91], "Yellow": [194, 195, 0]
});
const SILK_COLORS = Object.freeze({
  "Green": [20, 51, 36], "Red": [181, 19, 21], "Blue": [2, 59, 162], "Black": [11, 11, 11], "White": [245, 245, 245],
  "Purple": [32, 2, 53], "Yellow": [194, 195, 0]
});
const BOARD_COLORS = Object.freeze({
  "FR4 natural, dark": [51, 43, 22, 0.83], "FR4 natural": [109, 116, 75, 0.83], "PTFE natural": [252, 252, 250, 0.9],
  "Polyimide": [205, 130, 0, 0.68], "Phenolic natural": [92, 17, 6, 0.9], "Brown 1": [146, 99, 47, 0.83],
  "Brown 2": [160, 123, 54, 0.83], "Brown 3": [146, 99, 47, 0.83], "Aluminum": [213, 213, 213, 1]
});
const FINISH_COLORS = Object.freeze({ copper: [184, 115, 50], gold: [178, 156, 0], silver: [213, 213, 213], tin: [160, 160, 160] });
// KiCad's defaults where a stack-up names nothing (g_DefaultSolderMask, g_DefaultSilkscreen, g_DefaultBoardBody,
// g_DefaultSurfaceFinish).
const DEFAULT_MASK = [20, 51, 36];
const DEFAULT_SILK = [240, 240, 240];
const DEFAULT_BODY = [110, 115, 77];
const DEFAULT_FINISH = [191, 156, 59];

const HEX = /^#([0-9a-f]{6})([0-9a-f]{2})?$/i;

/** A colour as the stack-up names it, in `table`, or written `#RRGGBB[AA]`: `[r, g, b, a]`, or null. */
function named(name, table) {
  if (typeof name !== "string" || !name.trim()) return null;
  const hex = HEX.exec(name.trim());
  if (hex) {
    const value = Number.parseInt(hex[1], 16);
    return [(value >> 16) & 255, (value >> 8) & 255, value & 255, hex[2] ? Number.parseInt(hex[2], 16) / 255 : 1];
  }
  const found = table[name.trim()];
  return found ? [found[0], found[1], found[2], found[3] ?? 1] : null;
}

const css = ([r, g, b]) => `rgb(${Math.round(r)}, ${Math.round(g)}, ${Math.round(b)})`;

/** The copper's colour for a finish, as KiCad's 3D view reads the name. */
export function finishColor(finish) {
  const name = typeof finish === "string" ? finish.trim() : "";
  if (name.endsWith("OSP")) return css(FINISH_COLORS.copper);
  if (name.endsWith("IG") || name.endsWith("gold")) return css(FINISH_COLORS.gold);
  if (name.startsWith("HAL") || name.startsWith("HASL") || name.endsWith("tin") || name.endsWith("nickel")) return css(FINISH_COLORS.tin);
  if (name.endsWith("silver")) return css(FINISH_COLORS.silver);
  return css(DEFAULT_FINISH);
}

/**
 * The colours a board is made in, from its index's `stackup` (`{ layers: [{ name, type, color }], finish }`), or
 * null when it names no colour and no finish: `{ substrate, copper, sides: { top, bottom } }`, each side
 * `{ mask: { color, opacity } | null, silk: string | null }`, every colour a CSS `rgb()`.
 */
export function boardFinish(stackup) {
  const layers = Array.isArray(stackup?.layers) ? stackup.layers.filter((layer) => layer && typeof layer.name === "string") : [];
  const finish = typeof stackup?.finish === "string" && stackup.finish.trim() ? stackup.finish : null;
  if (!finish && !layers.some((layer) => typeof layer.color === "string" && layer.color.trim())) return null;
  const byName = new Map(layers.map((layer) => [layer.name, layer]));
  const side = (prefix) => {
    const mask = byName.get(`${prefix}.Mask`), silk = byName.get(`${prefix}.SilkS`);
    const maskColor = mask ? named(mask.color, MASK_COLORS) ?? [...DEFAULT_MASK, MASK_OPACITY] : null;
    return Object.freeze({
      mask: maskColor ? Object.freeze({ color: css(maskColor), opacity: HEX.test(String(mask.color ?? "").trim()) ? maskColor[3] : MASK_OPACITY }) : null,
      silk: silk ? css(named(silk.color, SILK_COLORS) ?? DEFAULT_SILK) : null
    });
  };
  // The dielectrics' colours mixed as KiCad mixes them: the first as it is, each next over it by its own transparency.
  let body = null;
  for (const layer of layers) {
    if (!/^dielectric/i.test(layer.name)) continue;
    const color = named(layer.color, BOARD_COLORS);
    if (!color) continue;
    body = body ? body.map((value, index) => (index < 3 ? value * color[3] + color[index] * (1 - color[3]) : value)) : color;
  }
  return Object.freeze({
    substrate: css(body ?? DEFAULT_BODY),
    copper: finishColor(finish),
    sides: Object.freeze({ top: side("F"), bottom: side("B") })
  });
}
