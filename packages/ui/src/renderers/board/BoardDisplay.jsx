import { useI18n, english } from "@cad/ui/i18n";
import { Box, Square } from "lucide-react";
import {
  BOARD_DISPLAY_DEFAULTS, BOARD_DISPLAY_OTHERS, boardDisplayDrawsCopper, boardDisplayIsCustom, readBoardDisplay, selectBoardMode
} from "@cad/core/lib/plot2d/index.js";
import { Checkbox } from "@cad/ui/primitives/checkbox";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@cad/ui/primitives/select";
import { cn } from "@cad/ui/utils";
import {
  FILE_SHEET_SELECT_TRIGGER_CLASSES, FileSheetSettingRow, FileSheetSettingsSection, parseFileSheetNumberInput
} from "../kit/inspector/FileSheet.js";
import { SliderField } from "../kit/inspector/SliderField.jsx";
import DisplayPopover, { DisplayMenuItems } from "../kit/shell/DisplayPopover.jsx";
import { VIEW_CORNER_BUTTON_CLASS, ViewCornerSided, ViewCornerState, viewCornerAway } from "../kit/shell/ViewCorner.jsx";
import { SolidModeIcon } from "../kit/view-settings/DisplayModeOptions.js";
import { BoardBottomSideIcon, BoardTopSideIcon } from "./boardSideIcons.jsx";

/**
 * How a board is drawn (`settings-ui.md`), by how often it is changed (the rule: on the screen what is
 * changed often, in the panel or behind a menu what is changed now and then):
 *
 * - **On the screen** (`boardViewControls`), the corner's column over the zoom pill
 *   (`kit/shell/ViewCorner.jsx`; on a phone, rows of the strip's More): **Display**, the presets (the
 *   modes, `plot2d/boardDisplay.js`'s layer sets, KiCad's layer presets: Board, Copper, Assembly,
 *   Placement, and **Custom** while the Layers tab's eyes have left the mode's set: choosing a mode goes
 *   back to it), and in 3D the camera's projection under them; **2D/3D**; and **Flip** (KiCad's View ▸
 *   Flip Board View), the side the board is seen from, top or bottom: from the bottom the board is
 *   mirrored, its back layers on top. 2D/3D and Flip are each one button whose icon is the state on screen.
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

export const BOARD_MODE_OPTIONS = Object.freeze([
  Object.freeze({ value: "board", labelKey: "board.text.board" }),
  Object.freeze({ value: "copper", labelKey: "board.text.copper" }),
  Object.freeze({ value: "assembly", labelKey: "board.text.assembly" }),
  Object.freeze({ value: "placement", labelKey: "board.text.placement" }),
]);
const CUSTOM = "custom";
const percent = value => `${Math.round(value * 100)}%`;
// Every control fills the row's control column at the row's 24px height, a choice too: the room is the control's.
// A row is as tall as its control where that is taller (a phone's 32px Select), never cut by it.
const CONTROL_CLASS = "!h-6 w-full min-w-0";
const ROW_CLASS = "h-auto min-h-6";

/** What the layers but the active one are, as Others names them. */
export const BOARD_OTHERS_OPTIONS = Object.freeze(BOARD_DISPLAY_OTHERS.map(value => Object.freeze({ value, labelKey: `board.text.others_${value}` })));

/** The mode on screen, or Custom, as Preset names it. */
export function boardDisplayChoice(display, sheet) {
  if (boardDisplayIsCustom(display, sheet)) return { value: CUSTOM, labelKey: "board.text.custom" };
  return BOARD_MODE_OPTIONS.find(option => option.value === display.mode) || BOARD_MODE_OPTIONS[0];
}

function Choice({ label, name, value, options, onChange, data }) {
  return <FileSheetSettingRow label={label} className={ROW_CLASS}>
    <Select value={value} onValueChange={onChange}>
      <SelectTrigger aria-label={name} size="sm" className={cn(FILE_SHEET_SELECT_TRIGGER_CLASSES, CONTROL_CLASS)} {...data}><SelectValue /></SelectTrigger>
      <SelectContent>{options.map(([id, title]) => <SelectItem key={id} value={id} data-board-option={id}>{title}</SelectItem>)}</SelectContent>
    </Select>
  </FileSheetSettingRow>;
}

/** An opacity: the slider control, its committed percentage, which a draft changes only on Enter or blur. */
function Opacity({ id, label, name, value, onChange }) {
  const { t } = useI18n();
  const commit = draft => {
    if (draft === percent(value)) return;
    const next = parseFileSheetNumberInput(draft, { fallback: value * 100, min: 0, max: 100 }) / 100;
    if (next !== value) onChange(next);
  };
  return <SliderField data-board-opacity={id} label={label} name={name} value={value} min={0} max={1} step={0.01}
    onValueChange={onChange} text={percent(value)} onTextCommit={commit} textLabel={t("render.valueOf", { name })} />;
}

/**
 * The board's **Display**: its presets (KiCad's layer presets, `plot2d/boardDisplay.js`'s modes) as a
 * 3D view's Display lists its modes (`kit/shell/DisplayPopover.jsx`), the one on screen ticked, and
 * Custom, a state rather than a choice, while the Layers tab's eyes have left the preset's set
 * (choosing a preset goes back to it).
 * @param {{ display: ReturnType<typeof readBoardDisplay>, sheet: object | null, onChange(display: object): void, t?: Function }} options
 */
export function boardPresetMode({ display, sheet, onChange, t = english }) {
  const choice = boardDisplayChoice(display, sheet);
  const options = BOARD_MODE_OPTIONS.map(({ value, labelKey }) => ({ value, label: t(labelKey) }));
  if (choice.value === CUSTOM) options.push({ value: CUSTOM, label: t("board.text.custom"), disabled: true });
  return { value: choice.value, options, onChange: value => { if (value !== CUSTOM && value !== choice.value) onChange(selectBoardMode(display, value)); } };
}

/**
 * **Layer display**: the other layers, the pours and the opacities.
 * @param {{ display: ReturnType<typeof readBoardDisplay>, sheet: object | null, onChange(display: object): void }} props
 */
export function BoardLayerDisplaySettings({ display, sheet, onChange }) {
  const { t } = useI18n();
  return <FileSheetSettingsSection title={t("board.text.layer_display")} sectionId="board-layer-display">
    <Choice label={t("board.text.others")} name={t("board.text.other_layers")} value={display.others}
      options={BOARD_OTHERS_OPTIONS.map(({ value, labelKey }) => [value, t(labelKey)])}
      onChange={value => { if (BOARD_DISPLAY_OTHERS.includes(value)) onChange({ ...display, others: value }); }} data={{ "data-board-others": display.others }} />
    {boardDisplayDrawsCopper(display, sheet) ? <FileSheetSettingRow label={t("board.text.pours")} className={ROW_CLASS}>
      <Checkbox className="ml-auto" aria-label={t("board.text.copper_pours")} checked={display.poured}
        onCheckedChange={value => onChange({ ...display, poured: value === true })} data-board-pours="" />
    </FileSheetSettingRow> : null}
    <Opacity id="zones" label={t("board.text.zones")} name={t("board.text.zone_opacity")}
      value={display.zones ?? BOARD_DISPLAY_DEFAULTS.zones} onChange={zones => onChange({ ...display, zones })} />
    <Opacity id="tracks" label={t("board.text.tracks")} name={t("board.text.track_opacity")}
      value={display.tracks ?? BOARD_DISPLAY_DEFAULTS.tracks} onChange={tracks => onChange({ ...display, tracks })} />
  </FileSheetSettingsSection>;
}

/** The key that turns the board over, Flip's (EasyEDA's Shift+F: F is Zoom to fit, `kit/tools/toolShortcuts.js`). */
export const BOARD_FLIP_SHORTCUT = "⇧F";
/** The key that draws the board in 3D and flat again (KiCad's Alt+3 opens its 3D viewer). */
export const BOARD_DIMENSION_SHORTCUT = "3";

/**
 * The board's view controls on the screen (`FloatingToolBar.js`'s `ViewportViewControl`), the ones
 * switched often enough to keep there: in the corner's column over the zoom pill, from the top down
 * (`kit/shell/ViewCorner.jsx`'s `ViewPillColumn`), the same column in 2D and in 3D, each one 24px corner
 * button, and on a phone rows of the strip's More —
 *
 * - **Display**, the corner button a 3D view has for it, its menu the presets (`boardPresetMode`;
 *   on a phone More's submenu) and, in 3D, the camera's projection (`projection`), changed seldom, so
 *   there and not a button of its own;
 * - **2D/3D**, the board drawn flat or as a board in 3D: the view's state button (`kit/shell/StateButton.jsx`,
 *   Projection's), a square while it is flat and a box in 3D, its name the state ("View: 2D"), its tooltip
 *   what a press does ("Switch to 3D", and its key, 3); on a phone More's row 3D view, ticked in 3D;
 * - **Flip**, the side it is seen from (KiCad's View ▸ Flip Board View): the same state button, the board as
 *   two stacked layers, the side it is seen from solid (`boardSideIcons.jsx`), lit in the strip's pressed
 *   fill while it is seen from the bottom (the view people lose track of), its name the side ("Side: Bottom"),
 *   its tooltip what a press does ("View from top", and its key, ⇧F). From the bottom the board is mirrored, its back
 *   layers on top; in 3D the camera turns over to the other side (`onSide`), and the button follows the
 *   camera, whichever side of the board's plane it is on. On a phone More's row View from bottom, ticked
 *   while it is.
 *
 * The rest of how the board is drawn — its layers and its layer display — is the Layers tab's
 * (`LayersSection.jsx`), opened now and then.
 * @param {{ display: ReturnType<typeof readBoardDisplay>, sheet?: object | null, onChange(display: object): void,
 *   dimension?: "2d" | "3d", onDimensionChange?: ((dimension: "2d" | "3d") => void) | null,
 *   onSide?: ((side: "top" | "bottom") => void) | null, projection?: { value: string, onChange(value: string): void } | null,
 *   disabled?: boolean, boundary?: HTMLElement | null, t?: Function }} options
 *   `onSide`: what choosing a side does where it is more than the Display's (a 3D view turns its camera to it).
 *   `projection`: the 3D camera's, while the board is in 3D; null in 2D, which has none.
 */
export function boardViewControls({ display, sheet = null, onChange, dimension = "2d", onDimensionChange = null, onSide = null, projection = null,
  disabled = false, boundary = null, t = english }) {
  const below = display.side === "bottom";
  const flip = () => { const next = below ? "top" : "bottom"; if (onSide) onSide(next); else onChange({ ...display, side: next }); };
  const solid = dimension === "3d";
  const switchDimension = () => onDimensionChange(solid ? "2d" : "3d");
  const presets = boardPresetMode({ display, sheet, onChange, t });
  const [flat, inThreeD] = [t("board.text.view_2d"), t("board.text.view_3d")];
  // Each state's icon: Lucide's square for the board flat and box for it in 3D; the board's two layers, the
  // side facing the viewer solid, from the top or the bottom.
  return [
    { id: "display", label: t("display.label"), icon: <SolidModeIcon />, disabled, tile: null,
      submenu: () => <DisplayMenuItems mode={presets} projection={projection} />,
      // Its tooltip and menu open beside it, away from the corner, as a 3D view's column's Display does.
      corner: <ViewCornerSided>{corner => <DisplayPopover disabled={disabled} boundary={boundary} mode={presets} projection={projection}
        icon={SolidModeIcon} className={VIEW_CORNER_BUTTON_CLASS} tooltipSide={viewCornerAway(corner).side} side={viewCornerAway(corner).side}
        align="end" />}</ViewCornerSided> },
    ...(onDimensionChange ? [{
      id: "dimension", label: t("board.text.view_in_3d"), icon: <Box />, disabled, active: solid, tile: null, onSelect: switchDimension,
      corner: <ViewCornerState icon={solid ? Box : Square} label={t("board.text.dimension_current", { mode: solid ? inThreeD : flat })}
        tooltip={t("board.text.dimension_switch", { mode: solid ? flat : inThreeD })} shortcut={BOARD_DIMENSION_SHORTCUT}
        disabled={disabled} onPress={switchDimension} data-board-dimension={solid ? "3d" : "2d"} />
    }] : []),
    { id: "side", label: t("board.text.view_from_bottom"), icon: <BoardBottomSideIcon />, disabled, active: below, tile: null, onSelect: flip,
      corner: <ViewCornerState icon={below ? BoardBottomSideIcon : BoardTopSideIcon} label={t("board.text.side_current", { side: t(below ? "board.text.bottom" : "board.text.top") })}
        tooltip={t(below ? "board.text.view_from_top" : "board.text.view_from_bottom")} shortcut={BOARD_FLIP_SHORTCUT} lit={below}
        disabled={disabled} onPress={flip} data-board-side={below ? "bottom" : "top"} /> }
  ];
}
