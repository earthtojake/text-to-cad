import { useI18n } from "@cad/ui/i18n";
import { FlipHorizontal2, SlidersHorizontal } from "lucide-react";
import { Popover, PopoverContent, PopoverTrigger } from "@cad/ui/primitives/popover";
import { ToolbarButton } from "@cad/ui/primitives/toolbar-button";
import { FLOATING_CHROME_SURFACE_CLASS, FLOATING_SURFACE_CLASS } from "../../lib/floatingSurface.js";
import { STRIP_BUTTON_CLASS, TOUCH_STRIP_BUTTON_CLASS } from "../kit/tools/stripTouch.js";
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
 * A board's view controls (`settings-ui.md`), the only ones a board has, because its picture is a
 * choice: the view cluster at the canvas's bottom-right (`FlatViewFrame.jsx`'s `viewControls`), apart
 * from the strip's tools, as SOLIDWORKS' Heads-up View toolbar, Onshape's render menu under its
 * view cube and Fusion's navigation bar keep them. Two tiles:
 *
 * - **Flip** (KiCad's View ▸ Flip Board): the board seen from below, mirrored, its back layers on top,
 *   and back; pressed while it is from below.
 * - **Display**, a popover of settings sections, as the settings form's rows are (a label in its
 *   muted column, the control filling the rest): **Display** — **Preset**, the modes
 *   (`plot2d/boardDisplay.js`'s layer sets, KiCad's layer presets: Board, Copper, Assembly,
 *   Placement), and **Custom** while the Layers tab's eyes have left the mode's set (choosing the mode
 *   goes back to it); then **Layer display**, KiCad's Layer Display Options: **Others**, every layer
 *   but the active one (a press on its row in the Layers tab chooses it) **Shown**, **Dimmed** or
 *   **Hidden** — the board's outline and the holes through an active copper layer at full strength
 *   either way (`plot2d/plot.js`'s `focusedLayers`); Ctrl+H (⌘H) cycles them while the board has the
 *   keyboard, as KiCad's does — **Pours** (while copper is drawn), and the **Zones**' (60%) and
 *   **Tracks**' (100%) opacities.
 *
 * The layer list itself is the panel's Layers tab (`LayersSection.jsx`). The contract — `{ mode, side,
 * poured, layers, active, others, zones, tracks }` — is core's, shared with `cad <type> snapshot
 * --display`, so what is drawn here is drawn there, and kept with the file's view.
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
      <FileSheetValueInput ariaLabel={t("render.valueOf", { name })} value={percent(value)} onValueCommit={commit} className="h-6 w-11 shrink-0 px-1.5" />
    </div>
  </FileSheetSettingRow>;
}

/**
 * **Display**: the preset.
 * @param {{ display: ReturnType<typeof readBoardDisplay>, sheet: object | null, onChange(display: object): void }} props
 */
function BoardPresetSettings({ display, sheet, onChange }) {
  const { t } = useI18n();
  const choice = boardDisplayChoice(display, sheet);
  const presets = BOARD_MODE_OPTIONS.map(({ value, labelKey }) => [value, t(labelKey)]);
  if (choice.value === CUSTOM) presets.push([CUSTOM, t("board.text.custom")]);
  return <FileSheetSettingsSection title={t("display.label")} sectionId="board-display">
    <Choice label={t("board.text.preset")} name={t("board.text.board_display_mode")} value={choice.value} options={presets}
      onChange={value => { if (value !== CUSTOM) onChange(selectBoardMode(display, value)); }} data={{ "data-board-display": choice.value }} />
  </FileSheetSettingsSection>;
}

/**
 * **Layer display**: the other layers, the pours and the opacities.
 * @param {{ display: ReturnType<typeof readBoardDisplay>, sheet: object | null, onChange(display: object): void }} props
 */
function BoardLayerDisplaySettings({ display, sheet, onChange }) {
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

/**
 * The board's view cluster: Flip, then Display and its popover. `touch`: a phone's 36px tiles.
 * @param {{ display: ReturnType<typeof readBoardDisplay>, sheet: object | null, onChange(display: object): void,
 *   disabled?: boolean, touch?: boolean }} props
 */
export function BoardViewControls({ display, sheet, onChange, disabled = false, touch = false }) {
  const { t } = useI18n();
  const tile = touch ? TOUCH_STRIP_BUTTON_CLASS : STRIP_BUTTON_CLASS;
  const below = display.side === "bottom";
  return <div role="group" aria-label={t("board.text.view_controls")} data-board-view-controls=""
    className={cn("pointer-events-auto inline-flex items-center gap-0.5 rounded-md p-1", FLOATING_CHROME_SURFACE_CLASS)}>
    <ToolbarButton label={t("board.text.flip_board")} tooltipSide="top" className={tile} active={below} aria-pressed={below} disabled={disabled}
      onClick={() => onChange({ ...display, side: below ? "top" : "bottom" })} data-board-side={display.side}>
      <FlipHorizontal2 aria-hidden="true" />
    </ToolbarButton>
    <Popover modal={false}>
      <PopoverTrigger asChild>
        <ToolbarButton label={t("display.label")} tooltipSide="top" className={tile} disabled={disabled} data-board-display-button="">
          <SlidersHorizontal aria-hidden="true" />
        </ToolbarButton>
      </PopoverTrigger>
      {/* A settings form over the canvas: the menus' surface, the form's rows, 15rem for a slider beside its value. */}
      <PopoverContent side="top" align="end" sideOffset={6} collisionPadding={8} aria-label={t("display.label")} data-board-display-menu=""
        className={cn(FLOATING_SURFACE_CLASS, "w-60 p-1 text-tiny data-[state=closed]:animate-none!")}>
        <BoardPresetSettings display={display} sheet={sheet} onChange={onChange} />
        <BoardLayerDisplaySettings display={display} sheet={sheet} onChange={onChange} />
      </PopoverContent>
    </Popover>
  </div>;
}
