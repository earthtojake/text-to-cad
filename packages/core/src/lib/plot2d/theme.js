/**
 * KiCad's default colour theme, as the board view draws a board: the "KiCad Default" board colours,
 * by layer (`common/settings/builtin_color_themes.h`), and the display settings KiCad's PCB editor
 * opens a board with (`project_local_settings.cpp`, `pcb_painter.cpp`): zones at 60% opacity,
 * everything else opaque; a plated hole the board's background with a golden wall, a via's hole
 * golden with a white wall; names on copper light or dark against the copper's own colour. The
 * payload carries geometry only (`docs/plot-payload.md`); what colour a layer is, is this module's.
 */

const COPPER = Object.freeze({ "F.Cu": "#C83434", "B.Cu": "#4D7FC4" });
// Inner copper, In1 to In30, in KiCad's order.
const INNER = Object.freeze([
  "#7FC87F", "#CE7D2C", "#4FCBCB", "#DB628B", "#A7A5C6", "#28CCD9", "#E8B2A7", "#F2EDA1", "#8DCB81", "#ED7C33",
  "#5BC3EB", "#F76F8E", "#A7A5C6", "#28CCD9", "#E8B2A7", "#F2EDA1", "#ED7C33", "#5BC3EB", "#F76F8E", "#A7A5C6",
  "#28CCD9", "#E8B2A7", "#F2EDA1", "#ED7C33", "#5BC3EB", "#F76F8E", "#A7A5C6", "#28CCD9", "#E8B2A7", "#F2EDA1"
]);
const LAYERS = Object.freeze({
  "F.SilkS": "#F2EDA1", "B.SilkS": "#E8B2A7",
  "F.Fab": "#AFAFAF", "B.Fab": "#585D84",
  "F.CrtYd": "#FF26E2", "B.CrtYd": "#26E9FF",
  "F.Mask": "rgba(216, 100, 255, 0.4)", "B.Mask": "rgba(2, 255, 238, 0.4)",
  "F.Paste": "rgba(180, 160, 154, 0.9)", "B.Paste": "rgba(0, 194, 194, 0.9)",
  "F.Adhes": "#840084", "B.Adhes": "#000084",
  "Edge.Cuts": "#D0D2CD", "Margin": "#FF26E2",
  "Dwgs.User": "#C2C2C2", "Cmts.User": "#5994DC", "Eco1.User": "#B4DBD2", "Eco2.User": "#D8C852",
  "User.1": "#C2C2C2", "User.2": "#5994DC", "User.3": "#B4DBD2", "User.4": "#D8C852", "User.5": "#C2C2C2",
  "User.6": "#5994DC", "User.7": "#B4DBD2", "User.8": "#D8C852", "User.9": "#E8B2A7",
  // What goes through the board, by the colour of what it draws most: a via's hole, the ratsnest, a pad's hole wall.
  vias: "#E3B72E", ratsnest: "rgba(0, 248, 255, 0.35)", drills: "#E3B72E",
  // The board area's shadow, and a through-hole pad's names.
  area: "rgba(100, 100, 100, 0.35)", names: "rgba(255, 255, 255, 0.9)"
});
/** KiCad's zone opacity: a pour's fill is drawn at this share of its layer's colour. */
export const ZONE_OPACITY = 0.6;
/** KiCad's "Inactive layers: Dim": every layer but the active one is drawn at this share. */
export const DIM_OPACITY = 0.3;
/**
 * A hole's fill and its plated wall, by what was drilled: a pad's hole is the board's background
 * (`null`: seen through) in a golden wall, a via's golden in a white one, an unplated hole cyan.
 */
export const HOLE_COLORS = Object.freeze({
  pad: Object.freeze({ fill: null, wall: "#E3B72E" }),
  via: Object.freeze({ fill: "#E3B72E", wall: "#ECECEC" }),
  npth: Object.freeze({ fill: "#1AC4D2", wall: null })
});
/** A label's colour by what it names: a through-hole pad's (white), a via's (dark grey). */
export const NAME_COLORS = Object.freeze({ pad: "rgba(255, 255, 255, 0.9)", via: "rgba(50, 50, 50, 0.9)" });
const LIGHT_NAME = "rgba(255, 255, 255, 0.7)";
const DARK_NAME = "rgba(0, 0, 0, 0.7)";

/** The colour a layer is drawn in. A layer the theme does not name is drawn as a user layer. */
export function layerColor(id) {
  if (Object.hasOwn(COPPER, id)) return COPPER[id];
  if (Object.hasOwn(LAYERS, id)) return LAYERS[id];
  const inner = /^In(\d+)\.Cu$/.exec(String(id));
  if (inner) return INNER[(Number(inner[1]) - 1) % INNER.length];
  return LAYERS["Dwgs.User"];
}

/**
 * The colour of the names written on a copper layer (a surface pad's): KiCad's white, or its
 * inverse on a copper colour bright enough (KiCad's `GetBrightness() > 0.5`) for white not to read.
 */
export function netnameColor(id) {
  const hex = /^#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(layerColor(id));
  if (!hex) return LIGHT_NAME;
  const [r, g, b] = hex.slice(1).map((part) => Number.parseInt(part, 16) / 255);
  return r * 0.299 + g * 0.587 + b * 0.117 > 0.5 ? DARK_NAME : LIGHT_NAME;
}

/** The colour one item is drawn in: its layer's, unless it is a label. */
export function itemColor(layerId, item) {
  if (item.t === "label") return layerId === "names" ? NAME_COLORS[item.kind] || NAME_COLORS.pad : netnameColor(layerId);
  return layerColor(layerId);
}
