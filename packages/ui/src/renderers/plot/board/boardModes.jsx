import ToolModeMenu from "../../kit/tools/ToolModeMenu.jsx";
import { ToolModeIcon, modeMenuItems } from "../../kit/tools/modeGlyphs.jsx";

// A board's Select modes, drawn as every file's are (`kit/tools/modeGlyphs.jsx`): a chip with its
// legs for Parts, a solid pad for Pads, two pads joined by a trace for Nets.
export const BOARD_MODE_GLYPHS = Object.freeze({
  parts: (weight) => <g strokeWidth={2 * weight}><rect x="7" y="5" width="10" height="14" rx="1" /><path d="M3.5 8.5H7M3.5 12H7M3.5 15.5H7M17 8.5h3.5M17 12h3.5M17 15.5h3.5" /></g>,
  pads: (weight) => <rect x="6.5" y="6.5" width="11" height="11" rx="2" fill="currentColor" strokeWidth={1.5 * weight} />,
  nets: (weight) => <g strokeWidth={2 * weight}>
    <rect x="2.5" y="14.5" width="6" height="6" rx="1" fill="currentColor" />
    <rect x="15.5" y="3.5" width="6" height="6" rx="1" fill="currentColor" />
    <path d="M8.5 17.5H12l3.5-11" />
  </g>,
});

/** Select's modes on a board. All picks the most specific thing: a pad, a via or track, a part. */
export const BOARD_SELECT_MODES = Object.freeze([
  { id: "all", label: "All" }, { id: "parts", label: "Parts" }, { id: "pads", label: "Pads" }, { id: "nets", label: "Nets" },
]);

const known = (mode) => (BOARD_SELECT_MODES.some((item) => item.id === mode) ? mode : "all");

/** Select's strip icon: the pointer, badged with the mode in hand. */
export function BoardSelectIcon({ mode, ...props }) {
  const value = known(mode);
  return <ToolModeIcon tool="select" glyphs={BOARD_MODE_GLYPHS} mode={value} data-select-mode={value} {...props} />;
}

/** Select's mode menu, in the tree's filter row. */
export function BoardSelectModeMenu({ mode, onModeChange, disabled = false }) {
  return <ToolModeMenu label="Select mode" modes={modeMenuItems("select", BOARD_MODE_GLYPHS, BOARD_SELECT_MODES)}
    value={known(mode)} onChange={onModeChange} disabled={disabled} />;
}
