/**
 * KiCad's default colour theme, as the board view draws a board: the "KiCad Default" board colours,
 * by layer, with the via, hole and ratsnest colours KiCad draws over every layer. The payload
 * carries geometry only (`docs/plot-payload.md`); what colour a layer is, is this module's.
 */

const COPPER = Object.freeze({ "F.Cu": "#C83434", "B.Cu": "#4D7FC4" });
// Inner copper, In1 to In30, in KiCad's order; a deeper board cycles through them.
const INNER = Object.freeze([
  "#7FC87F", "#CE7D2C", "#4FCBCB", "#DB628B", "#A7A5C6", "#28CCD9", "#E8B2A7", "#F2EDA1", "#8DCB81", "#ED7C33",
  "#5BC3C3", "#D379A6", "#B0B0B0", "#3FC9E8", "#F0A388", "#F3EC75", "#61B363", "#FF8342", "#5BB7B5", "#C86D9A",
  "#C8C8C8", "#2FB7D6", "#F68661", "#E5DE45", "#58A456", "#F8925B", "#44B4AE", "#C36491", "#818181", "#1FA4C5"
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
  vias: "#ECECEC", ratsnest: "rgba(245, 255, 213, 0.7)", drills: "#C2C200"
});
/** A via by its kind, and a hole by what was drilled: the colours KiCad draws them in over the copper. */
export const VIA_COLORS = Object.freeze({ through: "#ECECEC", blind: "#BB9726", micro: "#008484" });
export const HOLE_COLORS = Object.freeze({ pad: "#C2C200", via: "#E3B72E", npth: "#1AC4D2" });

/** The colour a layer is drawn in. A layer the theme does not name is drawn as a user layer. */
export function layerColor(id) {
  if (Object.hasOwn(COPPER, id)) return COPPER[id];
  if (Object.hasOwn(LAYERS, id)) return LAYERS[id];
  const inner = /^In(\d+)\.Cu$/.exec(String(id));
  if (inner) return INNER[(Number(inner[1]) - 1) % INNER.length];
  return LAYERS["Dwgs.User"];
}

/** The colour one item is drawn in: its layer's, unless it is a via or a hole of a kind. */
export function itemColor(layerId, item) {
  if (item.via && Object.hasOwn(VIA_COLORS, item.via)) return VIA_COLORS[item.via];
  if (item.hole && Object.hasOwn(HOLE_COLORS, item.hole)) return HOLE_COLORS[item.hole];
  return layerColor(layerId);
}
