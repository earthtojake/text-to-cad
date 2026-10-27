import { useI18n, english } from "@text-to-cad/ui/i18n";
import { FlipHorizontal2, PaintBucket, SlidersHorizontal } from "lucide-react";
import {
  BOARD_DISPLAY_DEFAULTS, boardDisplayDrawsCopper, boardDisplayIsCustom, readBoardDisplay, selectBoardMode
} from "@text-to-cad/core/lib/plot2d/index.js";
import {
  DropdownMenu, DropdownMenuCheckboxItem, DropdownMenuContent, DropdownMenuLabel, DropdownMenuRadioGroup,
  DropdownMenuRadioItem, DropdownMenuSeparator, DropdownMenuTrigger
} from "@text-to-cad/ui/primitives/dropdown-menu";
import { ToolbarButton } from "@text-to-cad/ui/primitives/toolbar-button";
import { cn } from "@text-to-cad/ui/utils";
import { FLOATING_SURFACE_CLASS } from "../../lib/floatingSurface.js";
import { useStripButtonClass } from "../kit/tools/FloatingToolBar.js";
import { AssemblyModeIcon, BoardModeIcon, CopperModeIcon, PlacementModeIcon } from "./boardIcons.jsx";

/**
 * A board's Display (`settings-ui.md`): the one view control a board has, because its picture is a
 * choice — which layers, the pours, the side. A stock dropdown, as a 3D view's Display is
 * (`kit/shell/DisplayPopover.jsx`), in two groups each under a muted label: **Display modes**, the
 * modes as a radio group — each a layer set (`plot2d/boardDisplay.js`) — and **Custom** while the
 * Layers section's eyes have left the mode's set (choosing the mode goes back to it); a rule, then
 * **Settings**, two switches of their own, kept through a change of mode as a 3D view's Grid is:
 * **Copper pours** (while copper is drawn) and **View from below** (the board mirrored, its back
 * layers on top). Choosing a mode closes the menu; ticking leaves it open. A phone's More submenu
 * is the same two groups.
 *
 * The contract — `{ mode, side, poured, layers }` — is core's, shared with `cadgen pcb snapshot
 * --display`, so what is drawn here is drawn there, and kept with the file's view.
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

/** The mode on screen, or Custom, as the Display tile and its rows name it. */
export function boardDisplayChoice(display, sheet) {
  if (boardDisplayIsCustom(display, sheet)) return { value: CUSTOM, labelKey: "board.text.custom", Icon: SlidersHorizontal };
  return BOARD_MODE_OPTIONS.find(option => option.value === display.mode) || BOARD_MODE_OPTIONS[0];
}

/**
 * Display's rows, one list wherever it is shown (the Display tile's menu, a phone's More submenu).
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
        <SlidersHorizontal className="size-4" />{t("board.text.custom")}
      </DropdownMenuRadioItem> : null}
    </DropdownMenuRadioGroup>
    <DropdownMenuSeparator />
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
  </>;
}

/** The Display tile: the mode on screen's glyph, opening Display's rows (`BoardDisplayItems`). */
export function BoardDisplayPopover({ display, sheet, onChange, disabled = false }) {
  const { t } = useI18n();
  const tileClass = useStripButtonClass();
  const choice = boardDisplayChoice(display, sheet);
  const Icon = choice.Icon;
  return <DropdownMenu modal={false}>
    <DropdownMenuTrigger asChild>
      <ToolbarButton label={t("display.modeCurrent", { mode: t(choice.labelKey) })} tooltip={t("display.label")} tooltipSide="top" disabled={disabled}
        className={tileClass} data-board-display={choice.value}>
        <Icon />
      </ToolbarButton>
    </DropdownMenuTrigger>
    {/* Closes with no exit animation, so a quick second press always reaches the tile. */}
    <DropdownMenuContent align="center" sideOffset={6} collisionPadding={8} aria-label={t("display.label")}
      className={cn(FLOATING_SURFACE_CLASS, "w-44 data-[state=closed]:animate-none!")}>
      <BoardDisplayItems display={display} sheet={sheet} onChange={onChange} />
    </DropdownMenuContent>
  </DropdownMenu>;
}

/** The strip's view control for a board: its tile, and in a phone's More, a submenu of the same rows. */
export function boardDisplayControl({ display, sheet, onChange, disabled, t = english }) {
  const Icon = boardDisplayChoice(display, sheet).Icon;
  return {
    id: "display", label: t("display.label"), icon: <Icon />, disabled,
    tile: <BoardDisplayPopover display={display} sheet={sheet} onChange={onChange} disabled={disabled} />,
    submenu: () => <BoardDisplayItems display={display} sheet={sheet} onChange={onChange} />
  };
}
