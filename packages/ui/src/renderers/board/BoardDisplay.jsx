import { useI18n } from "@cad/ui/i18n";
import {
  BOARD_DISPLAY_DEFAULTS, BOARD_DISPLAY_OTHERS, boardDisplayDrawsCopper, boardDisplayIsCustom, readBoardDisplay, selectBoardMode
} from "@cad/core/lib/plot2d/index.js";
import { Checkbox } from "@cad/ui/primitives/checkbox";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@cad/ui/primitives/select";
import { Slider } from "@cad/ui/primitives/slider";
import { cn } from "@cad/ui/utils";
import {
  FILE_SHEET_SELECT_TRIGGER_CLASSES, FileSheetSettingRow, FileSheetSettingsSection, FileSheetValueInput, parseFileSheetNumberInput
} from "../kit/inspector/FileSheet.js";
import { SUB_TOOLBAR_SLIDER_CLASS } from "../kit/tools/SubToolbar.jsx";

/**
 * A board's view settings (`settings-ui.md`), the only ones a board has, because its picture is a
 * choice: two settings sections of the panel's **Layers** tab (`LayersSection.jsx`), where KiCad's
 * Appearance panel keeps them, as the settings form's rows are (a label in its muted column, the
 * control filling the rest; a choice a Select, a range a slider and its committed value).
 *
 * - **View**, over the layer list: **Preset**, the modes (`plot2d/boardDisplay.js`'s layer sets,
 *   KiCad's layer presets: Board, Copper, Assembly, Placement), and **Custom** while the layers' eyes
 *   have left the mode's set (choosing the mode goes back to it); **Side**, Top or Bottom (the board
 *   mirrored, its back layers on top).
 * - **Layer display**, under it, KiCad's Layer Display Options: **Others**, every layer but the active
 *   one (a press on its row chooses it) **Shown**, **Dimmed** or **Hidden** — the board's outline and
 *   the holes through an active copper layer at full strength either way (`plot2d/plot.js`'s
 *   `focusedLayers`); Ctrl+H (⌘H) cycles them while the board has the keyboard, as KiCad's does —
 *   **Pours** (while copper is drawn), and the **Zones**' (60%) and **Tracks**' (100%) opacities.
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
// Every control fills the row's control column at the row's 24px height; a choice is as wide as its value, at the row's end.
// A row is as tall as its control where that is taller (a phone's 32px Select), never cut by it.
const CONTROL_CLASS = "!h-6 w-full min-w-0";
const ROW_CLASS = "h-auto min-h-6";
const CHOICE_WIDTH_CLASS = "ml-auto w-fit max-w-full";

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
      <SelectTrigger aria-label={name} size="sm" className={cn(FILE_SHEET_SELECT_TRIGGER_CLASSES, CONTROL_CLASS, CHOICE_WIDTH_CLASS)} {...data}><SelectValue /></SelectTrigger>
      <SelectContent>{options.map(([id, title]) => <SelectItem key={id} value={id} data-board-option={id}>{title}</SelectItem>)}</SelectContent>
    </Select>
  </FileSheetSettingRow>;
}

/** An opacity's row: shadcn's slider and its committed percentage, which a draft changes only on Enter or blur. */
function Opacity({ id, label, name, value, onChange }) {
  const { t } = useI18n();
  const commit = draft => {
    if (draft === percent(value)) return;
    const next = parseFileSheetNumberInput(draft, { fallback: value * 100, min: 0, max: 100 }) / 100;
    if (next !== value) onChange(next);
  };
  return <FileSheetSettingRow label={label} className={ROW_CLASS}>
    <div className="contents" data-board-opacity={id}>
      <Slider className={cn(SUB_TOOLBAR_SLIDER_CLASS, "px-1")} value={[value]} min={0} max={1} step={0.01}
        thumbProps={{ "aria-label": name }} onValueChange={([next]) => onChange(next)} />
      <FileSheetValueInput ariaLabel={t("render.valueOf", { name })} value={percent(value)} onValueCommit={commit} className="h-6 w-13 px-1.5" />
    </div>
  </FileSheetSettingRow>;
}

/**
 * **View**: the preset and the side.
 * @param {{ display: ReturnType<typeof readBoardDisplay>, sheet: object | null, onChange(display: object): void }} props
 */
export function BoardViewSettings({ display, sheet, onChange }) {
  const { t } = useI18n();
  const choice = boardDisplayChoice(display, sheet);
  const presets = BOARD_MODE_OPTIONS.map(({ value, labelKey }) => [value, t(labelKey)]);
  if (choice.value === CUSTOM) presets.push([CUSTOM, t("board.text.custom")]);
  return <FileSheetSettingsSection title={t("board.text.view")} sectionId="board-view">
    <Choice label={t("board.text.preset")} name={t("board.text.board_display_mode")} value={choice.value} options={presets}
      onChange={value => { if (value !== CUSTOM) onChange(selectBoardMode(display, value)); }} data={{ "data-board-display": choice.value }} />
    <Choice label={t("board.text.side")} name={t("board.text.board_side")} value={display.side === "bottom" ? "bottom" : "top"}
      options={[["top", t("board.text.top")], ["bottom", t("board.text.bottom")]]} onChange={side => onChange({ ...display, side })} data={{ "data-board-side": display.side }} />
  </FileSheetSettingsSection>;
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
