/**
 * A board's colours, in the viewer's two themes. **Dark** is KiCad's default colour theme, as the
 * board view draws a board: the "KiCad Default" board colours, by layer
 * (`common/settings/builtin_color_themes.h`), on the viewer's neutral dark canvas (`#292929`, the
 * app's dark `--background`, in place of KiCad's navy). **Light** is the same layers on the app's
 * light canvas (`#ffffff`): KiCad ships no light board theme (its built-ins, Default and Classic,
 * are both dark), so it is derived, one rule for every colour — each kept where it already reads on
 * white at WCAG's 3:1 for graphics (both outer coppers, the magenta courtyard, ...), else its OKLCH
 * lightness lowered, its hue kept and its chroma only as far as sRGB needs, until it does — so a
 * layer is the colour it is in KiCad, darkened enough to read: copper stays KiCad's red and blue,
 * the yellow silkscreen turns ochre, the light fab and outline grey. What the rule cannot decide is
 * set by hand: the board's area a faint shade under the board rather than a light one, the ratsnest
 * more opaque, the masks and paste at KiCad's own opacity.
 *
 * Both draw as KiCad's PCB editor opens a board (`project_local_settings.cpp`, `pcb_painter.cpp`):
 * zones at 60% opacity, everything else opaque; a plated hole the canvas with a golden wall, a via's
 * hole golden with a light wall; names on copper light or dark against the copper's own colour. The
 * payload carries geometry only (`docs/plot-payload.md`); what colour a layer is, is this module's,
 * so a change of theme draws the board again in the browser, never on the server.
 * `render/board.py` (`cad kicad_pcb snapshot`) mirrors both tables.
 */

/** KiCad's zone opacity: a pour's fill is drawn at this share of its layer's colour. */
export const ZONE_OPACITY = 0.6;
/** KiCad's "Inactive layers: Dim": every layer but the active one is drawn at this share. */
export const DIM_OPACITY = 0.3;

const DARK = Object.freeze({
  background: "#292929",
  copper: { "F.Cu": "#C83434", "B.Cu": "#4D7FC4" },
  // Inner copper, In1 to In30, in KiCad's order.
  inner: [
    "#7FC87F", "#CE7D2C", "#4FCBCB", "#DB628B", "#A7A5C6", "#28CCD9", "#E8B2A7", "#F2EDA1", "#8DCB81", "#ED7C33",
    "#5BC3EB", "#F76F8E", "#A7A5C6", "#28CCD9", "#E8B2A7", "#F2EDA1", "#ED7C33", "#5BC3EB", "#F76F8E", "#A7A5C6",
    "#28CCD9", "#E8B2A7", "#F2EDA1", "#ED7C33", "#5BC3EB", "#F76F8E", "#A7A5C6", "#28CCD9", "#E8B2A7", "#F2EDA1"
  ],
  layers: {
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
    // The board area's shade, and a through-hole pad's names.
    area: "rgba(100, 100, 100, 0.35)", names: "rgba(255, 255, 255, 0.9)"
  },
  holes: { pad: { fill: null, wall: "#E3B72E" }, via: { fill: "#E3B72E", wall: "#ECECEC" }, npth: { fill: "#1AC4D2", wall: null } },
  names: { pad: "rgba(255, 255, 255, 0.9)", via: "rgba(50, 50, 50, 0.9)" }
});

// The light theme: DARK's colours by the rule above (each at 3:1 or more on #ffffff, its hue kept).
const LIGHT = Object.freeze({
  background: "#FFFFFF",
  copper: { "F.Cu": "#C83434", "B.Cu": "#4D7FC4" },
  inner: [
    "#5BA35C", "#CE7D2C", "#14A5A5", "#DB628B", "#9391B1", "#03A3AE", "#BC887E", "#9C964D", "#67A35B", "#E6762B",
    "#32A0C7", "#EE6786", "#9391B1", "#03A3AE", "#BC887E", "#9C964D", "#E6762B", "#32A0C7", "#EE6786", "#9391B1",
    "#03A3AE", "#BC887E", "#9C964D", "#E6762B", "#32A0C7", "#EE6786", "#9391B1", "#03A3AE", "#BC887E", "#9C964D"
  ],
  layers: {
    "F.SilkS": "#9C964D", "B.SilkS": "#BC887E",
    "F.Fab": "#939393", "B.Fab": "#585D84",
    "F.CrtYd": "#FF26E2", "B.CrtYd": "#0AA3B4",
    "F.Mask": "rgba(213, 97, 252, 0.4)", "B.Mask": "rgba(15, 166, 155, 0.4)",
    "F.Paste": "rgba(163, 143, 137, 0.9)", "B.Paste": "rgba(21, 164, 164, 0.9)",
    "F.Adhes": "#840084", "B.Adhes": "#000084",
    "Edge.Cuts": "#939590", "Margin": "#FF26E2",
    "Dwgs.User": "#939393", "Cmts.User": "#5994DC", "Eco1.User": "#769B93", "Eco2.User": "#A59503",
    "User.1": "#939393", "User.2": "#5994DC", "User.3": "#769B93", "User.4": "#A59503", "User.5": "#939393",
    "User.6": "#5994DC", "User.7": "#769B93", "User.8": "#A59503", "User.9": "#BC887E",
    vias: "#B58F0E", ratsnest: "rgba(20, 164, 169, 0.6)", drills: "#B58F0E",
    // The board's area a faint shade darker than the canvas, as the dark theme's is a shade lighter.
    area: "rgba(0, 0, 0, 0.07)", names: "rgba(255, 255, 255, 0.9)"
  },
  holes: { pad: { fill: null, wall: "#B58F0E" }, via: { fill: "#B58F0E", wall: "#949494" }, npth: { fill: "#0BA3B0", wall: null } },
  names: { pad: "rgba(255, 255, 255, 0.9)", via: "rgba(50, 50, 50, 0.9)" }
});

const LIGHT_NAME = "rgba(255, 255, 255, 0.7)";
const DARK_NAME = "rgba(0, 0, 0, 0.7)";

function palette(scheme, table) {
  const freeze = (value) => Object.freeze(Object.fromEntries(Object.entries(value).map(([key, entry]) => [key, Object.freeze(entry)])));
  /** The colour a layer is drawn in. A layer the theme does not name is drawn as a user layer. */
  const layer = (id) => {
    if (Object.hasOwn(table.copper, id)) return table.copper[id];
    if (Object.hasOwn(table.layers, id)) return table.layers[id];
    const inner = /^In(\d+)\.Cu$/.exec(String(id));
    if (inner) return table.inner[(Number(inner[1]) - 1) % table.inner.length];
    return table.layers["Dwgs.User"];
  };
  /**
   * The colour of the names written on a copper layer (a surface pad's): KiCad's white, or its
   * inverse on a copper colour bright enough (KiCad's `GetBrightness() > 0.5`) for white not to read.
   */
  const netname = (id) => {
    const hex = /^#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(layer(id));
    if (!hex) return LIGHT_NAME;
    const [r, g, b] = hex.slice(1).map((part) => Number.parseInt(part, 16) / 255);
    return r * 0.299 + g * 0.587 + b * 0.117 > 0.5 ? DARK_NAME : LIGHT_NAME;
  };
  const names = Object.freeze({ ...table.names });
  /** The colour one item is drawn in: its layer's, unless it is a label. */
  const item = (layerId, entry) => (entry.t === "label" ? (layerId === "names" ? names[entry.kind] || names.pad : netname(layerId)) : layer(layerId));
  return Object.freeze({ scheme, background: table.background, layer, netname, item, holes: freeze(table.holes), names });
}

/** A board's palette in each of the viewer's themes. */
export const BOARD_PALETTES = Object.freeze({ dark: palette("dark", DARK), light: palette("light", LIGHT) });

/** The palette a board is drawn in for a colour scheme: `"light"`, or anything else for dark. */
export function boardPalette(scheme) {
  return scheme === "light" ? BOARD_PALETTES.light : BOARD_PALETTES.dark;
}

// The dark palette's, by name, for what draws without a theme (KiCad's own colours).
export const HOLE_COLORS = BOARD_PALETTES.dark.holes;
/** A label's colour by what it names: a through-hole pad's (white), a via's (dark grey). */
export const NAME_COLORS = BOARD_PALETTES.dark.names;
export const layerColor = BOARD_PALETTES.dark.layer;
export const netnameColor = BOARD_PALETTES.dark.netname;
export const itemColor = BOARD_PALETTES.dark.item;
