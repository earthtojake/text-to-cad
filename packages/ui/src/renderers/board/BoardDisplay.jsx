import { useI18n, english } from "@cad/ui/i18n";
import { Box, FlipHorizontal2, Layers2, PaintBucket, SlidersHorizontal, Square, SunDim } from "lucide-react";
import {
  BOARD_DISPLAY_DEFAULTS, boardDisplayDrawsCopper, boardDisplayIsCustom, readBoardDisplay, selectBoardMode
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
 *   is — **Copper pours** (while copper is drawn), **View from below** (the board mirrored, its back
 *   layers on top) and **Dim other layers** (KiCad's "Inactive layers: Dim": every layer but the
 *   active one, which a press on its row in the Layers section chooses, drawn faded) — then a rule
 *   and **Opacity**, KiCad's Layer Display Options' — the **Zones**' fill (60%) and the **Tracks**'
 *   (100%), each a row of its glyph, its name, a slider and its committed percentage, as a settings
 *   form's slider is. Ticking or sliding leaves it open; Escape in a value puts the draft back.
 *
 * A phone's More has a submenu of each, in the same order. The contract — `{ mode, side, poured,
 * layers, active, dim, zones, tracks }` — is core's, shared with `cad <type> snapshot --display`, so
 * what is drawn here is drawn there, and kept with the file's view.
 *
 * Where the server draws a board in 3D, Display leads with **View**, under a muted label, **2D** and
 * **3D** as a radio group of their own, then a rule (`BoardViewItems`): the same rows lead the 3D view's
 * Display (`Board3DView.jsx`), above its modes, so the way back is where the way in was. It is a choice of
 * picture, as the modes are, and the file's (kept with its view), not a camera's, so it is Display's
 * rows and no tile of its own as Projection is; in 3D the modes are a 3D view's and Projection is there.
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

/** The two pictures of a board, as View's rows name them. */
export const BOARD_VIEW_OPTIONS = Object.freeze([
  Object.freeze({ value: "2d", labelKey: "board.text.view_2d", Icon: Square }),
  Object.freeze({ value: "3d", labelKey: "board.text.view_3d", Icon: Box }),
]);

/**
 * View's rows, leading a board's Display in 2D and in 3D: a muted label, 2D and 3D as a radio group, then a
 * rule. Choosing closes the menu, as a mode does.
 * @param {{ boardView: { value: "2d" | "3d", onChange(value: "2d" | "3d"): void } }} props
 */
export function BoardViewItems({ boardView, rule = true }) {
  const { t } = useI18n();
  return <>
    <DropdownMenuLabel className="text-muted-foreground">{t("board.text.view")}</DropdownMenuLabel>
    <DropdownMenuRadioGroup aria-label={t("board.text.board_view")} value={boardView.value}
      onValueChange={value => { if (value !== boardView.value) boardView.onChange(value === "3d" ? "3d" : "2d"); }}>
      {BOARD_VIEW_OPTIONS.map(({ value, labelKey, Icon }) => <DropdownMenuRadioItem key={value} value={value} data-board-view-option={value}>
        <Icon className="size-4" />{t(labelKey)}
      </DropdownMenuRadioItem>)}
    </DropdownMenuRadioGroup>
    {rule ? <DropdownMenuSeparator /> : null}
  </>;
}

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
export function BoardDisplayItems({ display, sheet, onChange, boardView = null }) {
  const { t } = useI18n();
  const choice = boardDisplayChoice(display, sheet);
  return <>
    {boardView ? <BoardViewItems boardView={boardView} /> : null}
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
    <DropdownMenuCheckboxItem checked={display.dim === true} onSelect={keepOpen}
      onCheckedChange={value => onChange({ ...display, dim: value === true })} data-board-dim="">
      <SunDim className="size-4" />{t("board.text.dim_other_layers")}
    </DropdownMenuCheckboxItem>
    <DropdownMenuSeparator />
    <DropdownMenuLabel className="text-muted-foreground">{t("render.opacity")}</DropdownMenuLabel>
    <OpacityRow id="zones" Icon={ZoneKindIcon} label={t("board.text.zones")} name={t("board.text.zone_opacity")}
      value={display.zones ?? BOARD_DISPLAY_DEFAULTS.zones} onChange={zones => onChange({ ...display, zones })} />
    <OpacityRow id="tracks" Icon={TrackKindIcon} label={t("board.text.tracks")} name={t("board.text.track_opacity")}
      value={display.tracks ?? BOARD_DISPLAY_DEFAULTS.tracks} onChange={tracks => onChange({ ...display, tracks })} />
  </>;
}

/** A board's view-control tile and its menu: its glyph, its name as its hint, opening `children`. */
export function BoardMenuTile({ label, hint, Icon, disabled, tileProps, contentProps, className, children }) {
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
export function BoardDisplayPopover({ display, sheet, onChange, disabled = false, boardView = null }) {
  const { t } = useI18n();
  const choice = boardDisplayChoice(display, sheet);
  return <BoardMenuTile label={t("display.modeCurrent", { mode: t(choice.labelKey) })} hint={t("display.label")} Icon={choice.Icon}
    disabled={disabled} tileProps={{ "data-board-display": choice.value }} contentProps={{ "data-board-display-menu": "" }} className="w-44">
    <BoardDisplayItems display={display} sheet={sheet} onChange={onChange} boardView={boardView} />
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
 * The Display tile while a board's 3D model is made, or could not be: View alone, the way back to 2D.
 */
export function boardViewOnlyControls({ boardView, t = english }) {
  const tile = <BoardMenuTile label={t("display.modeCurrent", { mode: t("board.text.view_3d") })} hint={t("display.label")} Icon={Box}
    tileProps={{ "data-board-display": "3d" }} contentProps={{ "data-board-display-menu": "" }} className="w-44">
    <BoardViewItems boardView={boardView} rule={false} />
  </BoardMenuTile>;
  return [{ id: "display", label: t("display.label"), icon: <Box />, tile, submenu: () => <BoardViewItems boardView={boardView} rule={false} /> }];
}

/**
 * The strip's view controls for a board, Display then Settings: each its tile, and in a phone's
 * More, a submenu of the same rows.
 */
export function boardViewControls({ display, sheet, onChange, disabled, boardView = null, t = english }) {
  const Icon = boardDisplayChoice(display, sheet).Icon;
  return [{
    id: "display", label: t("display.label"), icon: <Icon />, disabled,
    tile: <BoardDisplayPopover display={display} sheet={sheet} onChange={onChange} disabled={disabled} boardView={boardView} />,
    submenu: () => <BoardDisplayItems display={display} sheet={sheet} onChange={onChange} boardView={boardView} />
  }, {
    id: "settings", label: t("preview.settingsTitle"), icon: <SlidersHorizontal />, disabled,
    tile: <BoardSettingsPopover display={display} sheet={sheet} onChange={onChange} disabled={disabled} />,
    submenu: () => <BoardSettingsItems display={display} sheet={sheet} onChange={onChange} />
  }];
}
