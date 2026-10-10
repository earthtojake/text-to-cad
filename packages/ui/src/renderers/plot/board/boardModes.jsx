import ToolModeMenu from "../../kit/tools/ToolModeMenu.jsx";
import { ToolModeIcon, modeMenuItems } from "../../kit/tools/modeGlyphs.jsx";

// A board's tool modes, drawn as every file's are (`kit/tools/modeGlyphs.jsx`): a chip with its
// legs for Parts, a solid pad for Pads, two pads joined by a trace for Nets; for Measure's snapping,
// a pad, a via (a ring round a hole) and the board's rounded outline.
const PAD = (weight) => <rect x="6.5" y="6.5" width="11" height="11" rx="2" fill="currentColor" strokeWidth={1.5 * weight} />;
export const BOARD_MODE_GLYPHS = Object.freeze({
  parts: (weight) => <g strokeWidth={2 * weight}><rect x="7" y="5" width="10" height="14" rx="1" /><path d="M3.5 8.5H7M3.5 12H7M3.5 15.5H7M17 8.5h3.5M17 12h3.5M17 15.5h3.5" /></g>,
  pads: PAD,
  nets: (weight) => <g strokeWidth={2 * weight}>
    <rect x="2.5" y="14.5" width="6" height="6" rx="1" fill="currentColor" />
    <rect x="15.5" y="3.5" width="6" height="6" rx="1" fill="currentColor" />
    <path d="M8.5 17.5H12l3.5-11" />
  </g>,
  copper: (weight) => <g strokeWidth={2 * weight}><circle cx="12" cy="12" r="7.5" /><circle cx="12" cy="12" r="2.5" fill="currentColor" /></g>,
  outline: (weight) => <rect x="3" y="5" width="18" height="14" rx="3.5" strokeWidth={2 * weight} />,
});

/** Select's modes on a board. All picks the most specific thing: a pad, a via or track, a part. */
export const BOARD_SELECT_MODES = Object.freeze([
  { id: "all", label: "All" }, { id: "parts", label: "Parts" }, { id: "pads", label: "Pads" }, { id: "nets", label: "Nets" },
]);
// A schematic's: a symbol with its legs for Parts, a pin (its line and the dot a wire meets) for
// Pins, two wires meeting at a junction for Nets.
export const SCHEMATIC_MODE_GLYPHS = Object.freeze({
  parts: BOARD_MODE_GLYPHS.parts,
  pads: (weight) => <g strokeWidth={2 * weight}><path d="M3.5 12H15" /><circle cx="18" cy="12" r="2.75" fill="currentColor" /></g>,
  nets: (weight) => <g strokeWidth={2 * weight}><path d="M3 17h9V5M12 17h9" /><circle cx="12" cy="17" r="2.25" fill="currentColor" /></g>,
});
/** Select's modes on a schematic. All picks the most specific thing: a pin, a wire or label, a symbol. */
export const SCHEMATIC_SELECT_MODES = Object.freeze([
  { id: "all", label: "All" }, { id: "parts", label: "Parts" }, { id: "pads", label: "Pins" }, { id: "nets", label: "Nets" },
]);
const selectModes = (document) => (document === "schematic"
  ? { glyphs: SCHEMATIC_MODE_GLYPHS, modes: SCHEMATIC_SELECT_MODES } : { glyphs: BOARD_MODE_GLYPHS, modes: BOARD_SELECT_MODES });
/** What Measure snaps to on a board. */
export const BOARD_MEASURE_MODES = Object.freeze([
  { id: "all", label: "All" }, { id: "pads", label: "Pads" }, { id: "copper", label: "Vias and tracks" }, { id: "outline", label: "Edges and holes" },
]);

const known = (modes, mode) => (modes.some((item) => item.id === mode) ? mode : "all");

/** Select's strip icon: the pointer, badged with the mode in hand. */
export function BoardSelectIcon({ mode, document = "board", ...props }) {
  const { glyphs, modes } = selectModes(document);
  const value = known(modes, mode);
  return <ToolModeIcon tool="select" glyphs={glyphs} mode={value} data-select-mode={value} {...props} />;
}

/** Measure's strip icon: the ruler, badged with what it snaps to. */
export function BoardMeasureIcon({ mode, ...props }) {
  const value = known(BOARD_MEASURE_MODES, mode);
  return <ToolModeIcon tool="measure" glyphs={MEASURE_GLYPHS} mode={value} data-measure-mode={value} {...props} />;
}
const MEASURE_GLYPHS = Object.freeze({ pads: BOARD_MODE_GLYPHS.pads, copper: BOARD_MODE_GLYPHS.copper, outline: BOARD_MODE_GLYPHS.outline });

/** Select's mode menu, in the tree's filter row. */
export function BoardSelectModeMenu({ mode, onModeChange, document = "board", disabled = false }) {
  const { glyphs, modes } = selectModes(document);
  return <ToolModeMenu label="Select mode" modes={modeMenuItems("select", glyphs, modes)}
    value={known(modes, mode)} onChange={onModeChange} disabled={disabled} />;
}

/** Measure's snapping menu, in the Measure panel's heading. */
export function BoardMeasureModeMenu({ mode, onModeChange, disabled = false }) {
  return <ToolModeMenu label="Measure snapping" modes={modeMenuItems("measure", MEASURE_GLYPHS, BOARD_MEASURE_MODES)}
    value={known(BOARD_MEASURE_MODES, mode)} onChange={onModeChange} disabled={disabled} />;
}
