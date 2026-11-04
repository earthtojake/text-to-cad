import { useI18n, english } from "@cad/ui/i18n";
import { Eye, EyeOff, FlipHorizontal2, Layers2, PaintBucket, SlidersHorizontal, SunDim } from "lucide-react";
import {
  BOARD_DISPLAY_DEFAULTS, BOARD_DISPLAY_OTHERS, boardDisplayDrawsCopper, boardDisplayIsCustom, readBoardDisplay, selectBoardMode
} from "@cad/core/lib/plot2d/index.js";
import {
  DropdownMenu, DropdownMenuCheckboxItem, DropdownMenuContent, DropdownMenuLabel, DropdownMenuRadioGroup,
  DropdownMenuRadioItem, DropdownMenuSeparator, DropdownMenuTrigger
} from "@cad/ui/primitives/dropdown-menu";
import { Slider } from "@cad/ui/primitives/slider";
import { ToolbarButton } from "@cad/ui/primitives/toolbar-button";
import { TooltipHint } from "@cad/ui/primitives/tooltip";
import { cn } from "@cad/ui/utils";
import { FLOATING_SURFACE_CLASS } from "../../lib/floatingSurface.js";
import { FileSheetValueInput, parseFileSheetNumberInput } from "../kit/inspector/FileSheet.js";
import { useStripButtonClass } from "../kit/tools/FloatingToolBar.js";
import { SUB_TOOLBAR_SLIDER_CLASS } from "../kit/tools/SubToolbar.jsx";
import { AssemblyModeIcon, BoardModeIcon, CopperModeIcon, PlacementModeIcon, TrackKindIcon, ZoneKindIcon } from "./boardIcons.jsx";

/**
 * A board's view controls (`settings-ui.md`), the only ones a board has, because its picture is a
 * choice: two tiles at the strip's end, each a stock dropdown as a 3D view's Display is
 * (`kit/shell/DisplayPopover.jsx`), each hinted by its name.
 *
 * - **Display** (the mode on screen's glyph): **Display modes**, under a muted label, the modes as a
 *   radio group — each a layer set (`plot2d/boardDisplay.js`) — and **Custom** while the Layers
 *   section's eyes have left the mode's set (choosing the mode goes back to it). Choosing a mode
 *   closes the menu.
 * - **Settings** (a sliders glyph): the switches, kept through a change of mode as a 3D view's Grid
 *   is — **Copper pours** (while copper is drawn) and **View from below** (the board mirrored, its back
 *   layers on top) — then a rule and **Other layers**, KiCad's high-contrast modes, a radio group:
 *   every layer but the active one (which a press on its row in the Layers section chooses) **Shown**,
 *   **Dimmed** or **Hidden**, the board's outline and the holes through an active copper layer at full
 *   strength either way (`plot2d/plot.js`'s `focusedLayers`); Ctrl+H (⌘H) cycles them while the board
 *   has the keyboard, as KiCad's does — then a rule and **Opacity**, KiCad's Layer Display Options' — the **Zones**' fill (60%) and the **Tracks**'
 *   (100%), each a row of its glyph, its name, a slider and its committed percentage, as a settings
 *   form's slider is. Ticking or sliding leaves it open; Escape in a value puts the draft back.
 *
 * A phone's More has a submenu of each, in the same order. The contract — `{ mode, side, poured,
 * layers, active, others, zones, tracks }` — is core's, shared with `cad <type> snapshot --display`, so
 * what is drawn here is drawn there, and kept with the file's view.
 */
export { BOARD_DISPLAY_DEFAULTS, readBoardDisplay };

export const BOARD_MODE_OPTIONS = Object.freeze([
  Object.freeze({ value: "board", labelKey: "board.text.board", Icon: BoardModeIcon }),
  Object.freeze({ value: "copper", labelKey: "board.text.copper", Icon: CopperModeIcon }),
  Object.freeze({ value: "assembly", labelKey: "board.text.assembly", Icon: AssemblyModeIcon }),
  Object.freeze({ value: "placement", labelKey: "board.text.placement", Icon: PlacementModeIcon }),
]);
const CUSTOM = "custom";
const keepOpen = event => event.preventDefault();
const percent = value => `${Math.round(value * 100)}%`;
// A key in an opacity row is the slider's or the value's, never the menu's: no typeahead, no Tab
// swallowed. Escape the menu's content takes first (`keepEscapeForField`).
const keepKeys = event => { if (event.key !== "Escape") event.stopPropagation(); };
/**
 * The menu's Escape, while a value is being typed, is the value's: it puts the draft back and leaves
 * the menu open, as a nested control owns Escape before its surface (`settings-ui.md`).
 */
export function keepEscapeForField(event) {
  if (event.target instanceof HTMLInputElement) event.preventDefault();
}

/**
 * An opacity's row: its glyph and name where an item's are, so every row's text starts on one line,
 * then shadcn's slider and its committed percentage, which a draft changes only on Enter or blur.
 */
function OpacityRow({ id, Icon, label, name, value, onChange }) {
  const { t } = useI18n();
  const commit = draft => {
    if (draft === percent(value)) return;
    const next = parseFileSheetNumberInput(draft, { fallback: value * 100, min: 0, max: 100 }) / 100;
    if (next !== value) onChange(next);
  };
  return <div className="flex h-7 min-w-0 items-center gap-2 px-2" data-board-opacity={id} onKeyDown={keepKeys}>
    <Icon className="size-4 shrink-0 text-muted-foreground" />
    <TooltipHint content={name} overflowOnly><span className="w-10 shrink-0 truncate">{label}</span></TooltipHint>
    <Slider className={cn(SUB_TOOLBAR_SLIDER_CLASS, "px-1")} value={[value]} min={0} max={1} step={0.01}
      thumbProps={{ "aria-label": name }} onValueChange={([next]) => onChange(next)} />
    <FileSheetValueInput ariaLabel={t("render.valueOf", { name })} value={percent(value)} onValueCommit={commit} className="h-6 w-13 px-1.5" />
  </div>;
}

/** What the layers but the active one are, as Other layers' rows name them. */
export const BOARD_OTHERS_OPTIONS = Object.freeze(BOARD_DISPLAY_OTHERS.map(value => Object.freeze({
  value, labelKey: `board.text.others_${value}`, Icon: { shown: Eye, dimmed: SunDim, hidden: EyeOff }[value]
})));

/** The mode on screen, or Custom, as the Display tile and its rows name it. */
export function boardDisplayChoice(display, sheet) {
  if (boardDisplayIsCustom(display, sheet)) return { value: CUSTOM, labelKey: "board.text.custom", Icon: Layers2 };
  return BOARD_MODE_OPTIONS.find(option => option.value === display.mode) || BOARD_MODE_OPTIONS[0];
}

/**
 * Display's rows, one list wherever it is shown (the Display tile's menu, a phone's More submenu):
 * the modes alone.
 * @param {{ display: ReturnType<typeof readBoardDisplay>, sheet: object | null, onChange(display: object): void }} props
 */
export function BoardDisplayItems({ display, sheet, onChange }) {
  const { t } = useI18n();
  const choice = boardDisplayChoice(display, sheet);
  return <>
    <DropdownMenuLabel className="text-muted-foreground">{t("board.text.display_modes")}</DropdownMenuLabel>
    <DropdownMenuRadioGroup aria-label={t("board.text.board_display_mode")} value={choice.value}
      onValueChange={value => { if (value !== CUSTOM) onChange(selectBoardMode(display, value)); }}>
      {BOARD_MODE_OPTIONS.map(({ value, labelKey, Icon }) => <DropdownMenuRadioItem key={value} value={value} data-board-mode-option={value}>
        <Icon className="size-4" />{t(labelKey)}
      </DropdownMenuRadioItem>)}
      {choice.value === CUSTOM ? <DropdownMenuRadioItem value={CUSTOM} data-board-mode-option={CUSTOM}>
        <Layers2 className="size-4" />{t("board.text.custom")}
      </DropdownMenuRadioItem> : null}
    </DropdownMenuRadioGroup>
  </>;
}

/**
 * Settings' rows, one list wherever it is shown (the Settings tile's menu, a phone's More submenu):
 * the switches, then the opacities.
 * @param {{ display: ReturnType<typeof readBoardDisplay>, sheet: object | null, onChange(display: object): void }} props
 */
export function BoardSettingsItems({ display, sheet, onChange }) {
  const { t } = useI18n();
  return <>
    <DropdownMenuLabel className="text-muted-foreground">{t("preview.settingsTitle")}</DropdownMenuLabel>
    {/* Ticking leaves the menu open, as every checkbox row in a menu does: the board is seen changing. */}
    {boardDisplayDrawsCopper(display, sheet) ? <DropdownMenuCheckboxItem checked={display.poured} onSelect={keepOpen}
      onCheckedChange={value => onChange({ ...display, poured: value === true })} data-board-pours="">
      <PaintBucket className="size-4" />{t("board.text.copper_pours")}
    </DropdownMenuCheckboxItem> : null}
    <DropdownMenuCheckboxItem checked={display.side === "bottom"} onSelect={keepOpen}
      onCheckedChange={value => onChange({ ...display, side: value === true ? "bottom" : "top" })} data-board-side="">
      <FlipHorizontal2 className="size-4" />{t("board.text.view_from_below")}
    </DropdownMenuCheckboxItem>
    <DropdownMenuSeparator />
    {/* Choosing leaves the menu open, as a switch does: the board is seen changing. */}
    <DropdownMenuLabel className="text-muted-foreground">{t("board.text.other_layers")}</DropdownMenuLabel>
    <DropdownMenuRadioGroup aria-label={t("board.text.other_layers")} value={display.others}
      onValueChange={value => { if (BOARD_DISPLAY_OTHERS.includes(value)) onChange({ ...display, others: value }); }}>
      {BOARD_OTHERS_OPTIONS.map(({ value, labelKey, Icon }) => <DropdownMenuRadioItem key={value} value={value} onSelect={keepOpen} data-board-others={value}>
        <Icon className="size-4" />{t(labelKey)}
      </DropdownMenuRadioItem>)}
    </DropdownMenuRadioGroup>
    <DropdownMenuSeparator />
    <DropdownMenuLabel className="text-muted-foreground">{t("render.opacity")}</DropdownMenuLabel>
    <OpacityRow id="zones" Icon={ZoneKindIcon} label={t("board.text.zones")} name={t("board.text.zone_opacity")}
      value={display.zones ?? BOARD_DISPLAY_DEFAULTS.zones} onChange={zones => onChange({ ...display, zones })} />
    <OpacityRow id="tracks" Icon={TrackKindIcon} label={t("board.text.tracks")} name={t("board.text.track_opacity")}
      value={display.tracks ?? BOARD_DISPLAY_DEFAULTS.tracks} onChange={tracks => onChange({ ...display, tracks })} />
  </>;
}

/** A board's view-control tile and its menu: its glyph, its name as its hint, opening `children`. */
function BoardMenuTile({ label, hint, Icon, disabled, tileProps, contentProps, className, children }) {
  const tileClass = useStripButtonClass();
  return <DropdownMenu modal={false}>
    <DropdownMenuTrigger asChild>
      <ToolbarButton label={label} tooltip={hint} tooltipSide="top" disabled={disabled} className={tileClass} {...tileProps}>
        <Icon />
      </ToolbarButton>
    </DropdownMenuTrigger>
    {/* Closes with no exit animation, so a quick second press always reaches the tile. */}
    <DropdownMenuContent align="center" sideOffset={6} collisionPadding={8} aria-label={hint} {...contentProps}
      className={cn(FLOATING_SURFACE_CLASS, className, "data-[state=closed]:animate-none!")}>
      {children}
    </DropdownMenuContent>
  </DropdownMenu>;
}

/** The Display tile: the mode on screen's glyph, opening the modes (`BoardDisplayItems`). */
export function BoardDisplayPopover({ display, sheet, onChange, disabled = false }) {
  const { t } = useI18n();
  const choice = boardDisplayChoice(display, sheet);
  return <BoardMenuTile label={t("display.modeCurrent", { mode: t(choice.labelKey) })} hint={t("display.label")} Icon={choice.Icon}
    disabled={disabled} tileProps={{ "data-board-display": choice.value }} contentProps={{ "data-board-display-menu": "" }} className="w-44">
    <BoardDisplayItems display={display} sheet={sheet} onChange={onChange} />
  </BoardMenuTile>;
}

/** The Settings tile: a sliders glyph, opening the switches and the opacities (`BoardSettingsItems`). */
export function BoardSettingsPopover({ display, sheet, onChange, disabled = false }) {
  const { t } = useI18n();
  // As wide as an opacity row needs for its slider beside its name and value; a value's Escape is its own.
  return <BoardMenuTile label={t("preview.settingsTitle")} hint={t("preview.settingsTitle")} Icon={SlidersHorizontal} disabled={disabled}
    tileProps={{ "data-board-settings": "" }} contentProps={{ "data-board-settings-menu": "", onEscapeKeyDown: keepEscapeForField }} className="w-56">
    <BoardSettingsItems display={display} sheet={sheet} onChange={onChange} />
  </BoardMenuTile>;
}

/**
 * The strip's view controls for a board, Display then Settings: each its tile, and in a phone's
 * More, a submenu of the same rows.
 */
export function boardViewControls({ display, sheet, onChange, disabled, t = english }) {
  const Icon = boardDisplayChoice(display, sheet).Icon;
  return [{
    id: "display", label: t("display.label"), icon: <Icon />, disabled,
    tile: <BoardDisplayPopover display={display} sheet={sheet} onChange={onChange} disabled={disabled} />,
    submenu: () => <BoardDisplayItems display={display} sheet={sheet} onChange={onChange} />
  }, {
    id: "settings", label: t("preview.settingsTitle"), icon: <SlidersHorizontal />, disabled,
    tile: <BoardSettingsPopover display={display} sheet={sheet} onChange={onChange} disabled={disabled} />,
    submenu: () => <BoardSettingsItems display={display} sheet={sheet} onChange={onChange} />
  }];
}
