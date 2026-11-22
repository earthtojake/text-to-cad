import { useI18n, english } from "@cad/ui/i18n";
import {
  BOARD_DISPLAY_DEFAULTS, BOARD_DISPLAY_OTHERS, boardDisplayDrawsCopper, boardDisplayIsCustom, readBoardDisplay, selectBoardMode
} from "@cad/core/lib/plot2d/index.js";
import { TreeRowHeading } from "@cad/ui/primitives/tree-row";
import { parseFileSheetNumberInput } from "../kit/inspector/FileSheet.js";
import { SliderField } from "../kit/inspector/SliderField.jsx";
import { CircuitBoard, Cpu, Route, SquareDashed } from "lucide-react";
import { backgroundGroup, displayGroup, projectionGroup } from "../kit/shell/DisplaySettings.jsx";
import { PanelSelectRow, PanelSwitchRow } from "../kit/inspector/panelRows.jsx";
import { BoardBottomSideIcon, BoardTopSideIcon } from "./boardSideIcons.jsx";

/**
 * How a board is drawn (`docs/viewer-ux.md`, "The Display card"), by how often it is changed (the rule: on the screen what is
 * changed often, in the panel or behind a menu what is changed now and then):
 *
 * - **Display's card** (`boardViewGroups`, `kit/shell/DisplaySettings.jsx`), opened by the navbar's Display
 *   button: **Side** (KiCad's View ▸ Flip Board View), the side the board is seen from, top or bottom: from the
 *   bottom the board is mirrored, its back layers on top; **Mode**, 2D or 3D, and in 3D the camera's **Projection**;
 *   then **Style**, the presets (the modes, `plot2d/boardDisplay.js`'s layer sets, KiCad's layer presets: Board,
 *   Copper, Assembly, Placement, and **Custom** while the Layers tab's eyes have left the mode's set: choosing a mode
 *   goes back to it), and the Background.
 * - **Layer display**, in the panel's Layers tab (`LayersSection.jsx`), under its layers, as KiCad's
 *   Appearance panel has them, KiCad's Layer
 *   Display Options: **Others**, every layer but the active one (a press on its row chooses it) **Shown**,
 *   **Dimmed** or **Hidden** — the board's outline and the holes through an active copper layer at full
 *   strength either way (`plot2d/plot.js`'s `focusedLayers`); Ctrl+H (⌘H) cycles them while the board has
 *   the keyboard, as KiCad's does — **Pours** (while copper is drawn), and the **Zones**' (60%) and
 *   **Tracks**' (100%) opacities.
 *
 * The contract — `{ mode, side, poured, layers, active, others, zones, tracks }` — is core's, shared
 * with `cad <type> snapshot --display`, so what is drawn here is drawn there, and kept with the file's view.
 */
export { BOARD_DISPLAY_DEFAULTS, readBoardDisplay };

// Each preset's icon, lucide's at the display modes' stroke (`DisplayModeOptions.js`, 1.7): the whole board, its copper
// routes, its parts, and their placement (the courtyards' dashed outlines).
const boardIcon = Icon => Object.assign(props => <Icon strokeWidth={1.7} {...props} />, { displayName: `Board${Icon.displayName || "Icon"}` });
export const BOARD_MODE_OPTIONS = Object.freeze([
  Object.freeze({ value: "board", labelKey: "board.text.board", Icon: boardIcon(CircuitBoard) }),
  Object.freeze({ value: "copper", labelKey: "board.text.copper", Icon: boardIcon(Route) }),
  Object.freeze({ value: "assembly", labelKey: "board.text.assembly", Icon: boardIcon(Cpu) }),
  Object.freeze({ value: "placement", labelKey: "board.text.placement", Icon: boardIcon(SquareDashed) }),
]);
// 2D and 3D as the right panel's Mode row draws them: a flat square and a box.
const CUSTOM = "custom";
const percent = value => `${Math.round(value * 100)}%`;
/** What the layers but the active one are, as Others names them. */
export const BOARD_OTHERS_OPTIONS = Object.freeze(BOARD_DISPLAY_OTHERS.map(value => Object.freeze({ value, labelKey: `board.text.others_${value}` })));

/** The mode on screen, or Custom, as Preset names it. */
export function boardDisplayChoice(display, sheet) {
  if (boardDisplayIsCustom(display, sheet)) return { value: CUSTOM, labelKey: "board.text.custom" };
  return BOARD_MODE_OPTIONS.find(option => option.value === display.mode) || BOARD_MODE_OPTIONS[0];
}

/** An opacity: the slider control, its committed percentage, which a draft changes only on Enter or blur. */
function Opacity({ id, label, name, value, onChange }) {
  const { t } = useI18n();
  const commit = draft => {
    if (draft === percent(value)) return;
    const next = parseFileSheetNumberInput(draft, { fallback: value * 100, min: 0, max: 100 }) / 100;
    if (next !== value) onChange(next);
  };
  return <SliderField data-board-opacity={id} label={label} name={name} value={value} min={0} max={1} step={0.01} scale={100}
    onValueChange={onChange} text={percent(value)} onTextCommit={commit} textLabel={t("render.valueOf", { name })} />;
}

/**
 * The board's **Style**: its presets (KiCad's layer presets, `plot2d/boardDisplay.js`'s modes) as a
 * 3D view's Style lists its modes (`kit/shell/DisplaySettings.jsx`), the one on screen ticked, and
 * Custom, a state rather than a choice, while the Layers tab's eyes have left the preset's set
 * (choosing a preset goes back to it).
 * @param {{ display: ReturnType<typeof readBoardDisplay>, sheet: object | null, onChange(display: object): void, t?: Function }} options
 */
export function boardPresetMode({ display, sheet, onChange, t = english }) {
  const choice = boardDisplayChoice(display, sheet);
  const options = BOARD_MODE_OPTIONS.map(({ value, labelKey, Icon }) => ({ value, label: t(labelKey), Icon }));
  if (choice.value === CUSTOM) options.push({ value: CUSTOM, label: t("board.text.custom"), disabled: true });
  return { value: choice.value, options, onChange: value => { if (value !== CUSTOM && value !== choice.value) onChange(selectBoardMode(display, value)); } };
}

/**
 * **Layer display**: the other layers, the pours and the opacities.
 * @param {{ display: ReturnType<typeof readBoardDisplay>, sheet: object | null, onChange(display: object): void }} props
 */
export function BoardLayerDisplaySettings({ display, sheet, onChange }) {
  const { t } = useI18n();
  // The panel's own parts at its rhythm, as the Joints and Params tabs draw theirs: a heading as the layer groups' over
  // it (`TreeRowHeading`), the one dropdown's row, a switch's row, then the slider rows.
  return <section aria-label={t("board.text.layer_display")} data-settings-section="board-layer-display">
    <TreeRowHeading as="h4">{t("board.text.layer_display")}</TreeRowHeading>
    <PanelSelectRow label={t("board.text.others")} triggerLabel={t("board.text.other_layers")} value={display.others}
      options={BOARD_OTHERS_OPTIONS.map(({ value, labelKey }) => ({ value, label: t(labelKey) }))}
      onChange={value => { if (BOARD_DISPLAY_OTHERS.includes(value)) onChange({ ...display, others: value }); }}
      triggerProps={{ "data-board-others": display.others }} optionProps={option => ({ "data-board-option": option.value })} />
    {boardDisplayDrawsCopper(display, sheet) ? <PanelSwitchRow label={t("board.text.pours")} checked={display.poured}
      onChange={poured => onChange({ ...display, poured })} switchProps={{ "aria-label": t("board.text.copper_pours"), "data-board-pours": "" }} /> : null}
    <Opacity id="zones" label={t("board.text.zones")} name={t("board.text.zone_opacity")}
      value={display.zones ?? BOARD_DISPLAY_DEFAULTS.zones} onChange={zones => onChange({ ...display, zones })} />
    <Opacity id="tracks" label={t("board.text.tracks")} name={t("board.text.track_opacity")}
      value={display.tracks ?? BOARD_DISPLAY_DEFAULTS.tracks} onChange={tracks => onChange({ ...display, tracks })} />
  </section>;
}

/** The key that turns the board over, Flip's (EasyEDA's Shift+F: F is Zoom to fit, `kit/tools/toolShortcuts.js`). */
export const BOARD_FLIP_SHORTCUT = "⇧F";
/** The key that draws the board in 3D and flat again (KiCad's Alt+3 opens its 3D viewer). */
export const BOARD_DIMENSION_SHORTCUT = "3";

/**
 * The board's view settings as Display's card draws them (`kit/shell/DisplaySettings.jsx`), the camera's section
 * first: **Side** (Top, Bottom; ⇧F), **Mode** (2D, 3D; 3), in 3D the camera's **Projection**; then the picture's:
 * **Style**, its presets (`boardPresetMode`), and the **Background**. A side or a mode chosen is counted as the keys
 * count them (`board_side`, `board_dimension`), and does what they do (`onSide` turns a 3D view's camera over).
 * `defaults`: `{ side, dimension, style, projection }`, what a board opened for the first time gets (Reset's).
 * @param {{ display: ReturnType<typeof readBoardDisplay>, sheet?: object | null, onChange(display: object): void,
 *   dimension?: "2d" | "3d", onDimensionChange?: ((dimension: "2d" | "3d") => void) | null,
 *   onSide?: ((side: "top" | "bottom") => void) | null, projection?: { value: string, onChange(value: string): void } | null,
 *   background?: object | null, defaults?: object | null, t?: Function, used?: ((control: string) => void) | null }} options
 *   `onSide`: what choosing a side does where it is more than the Display's (a 3D view turns its camera to it).
 *   `projection`: the 3D camera's, while the board is in 3D; null in 2D, which has none.
 */
export function boardViewGroups({ display, sheet = null, onChange, dimension = "2d", onDimensionChange = null, onSide = null, projection = null,
  background = null, defaults = null, t = english, used = null }) {
  const side = display.side === "bottom" ? "bottom" : "top";
  const sideGroup = { id: "side", label: t("board.text.side"), value: side, data: "data-board-side-option", reset: defaults?.side,
    options: [{ value: "top", label: t("board.text.top"), Icon: BoardTopSideIcon }, { value: "bottom", label: t("board.text.bottom"), Icon: BoardBottomSideIcon }],
    onChange: next => {
      if (next === side) return;
      used?.("board_side");
      if (onSide) onSide(next); else onChange({ ...display, side: next });
    } };
  const solid = dimension === "3d";
  const modeGroup = onDimensionChange ? { id: "dimension", label: t("board.text.mode"), value: solid ? "3d" : "2d", data: "data-board-dimension-option",
    reset: defaults?.dimension,
    // Its options are the words alone ("2D", "3D"): an icon of the same words would say them twice.
    options: [{ value: "2d", label: t("board.text.view_2d") }, { value: "3d", label: t("board.text.view_3d") }],
    onChange: next => { if (next === dimension) return; used?.("board_dimension"); onDimensionChange(next); } } : null;
  return [sideGroup, modeGroup, projectionGroup(projection, t, defaults?.projection),
    displayGroup(boardPresetMode({ display, sheet, onChange, t }), t, defaults?.style), backgroundGroup(background, t, used)].filter(Boolean);
}
