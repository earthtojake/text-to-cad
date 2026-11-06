import {
  DropdownMenu, DropdownMenuCheckboxItem, DropdownMenuContent, DropdownMenuLabel, DropdownMenuRadioGroup,
  DropdownMenuRadioItem, DropdownMenuSeparator, DropdownMenuTrigger
} from "@cad/ui/primitives/dropdown-menu";
import { ToolbarButton } from "@cad/ui/primitives/toolbar-button";
import { useI18n } from "@cad/ui/i18n";
import { cn } from "@cad/ui/utils";
import { FLOATING_SURFACE_CLASS } from "../../../lib/floatingSurface.js";
import { useStripButtonClass } from "../tools/FloatingToolBar.js";
import { GridIcon } from "../view-settings/DisplayModeOptions.js";

/**
 * Display's choices, one list wherever it is shown (the Display tile's menu, a phone's More
 * submenu): the file's modes, then, after a rule, the Grid switch, which every mode draws. A view
 * whose modes are its own names them (`label`), may show a mode that is a state rather than a choice
 * (`disabled`: what the view's own settings came to by hand), and may have no grid.
 *
 * @param {{ mode: { value: string, options: { value: string, label?: string, Icon?: Function, disabled?: boolean }[], onChange(value: string): void },
 *   grid?: { value: boolean, onChange(value: boolean): void } | null }} props
 */
export function DisplayMenuItems({ mode, grid = null }) {
  const { t } = useI18n();
  return <>
    <DropdownMenuRadioGroup aria-label={t("display.mode")} value={mode.value} onValueChange={mode.onChange}>
      {mode.options.map(({ value, Icon, label, disabled }) => <DropdownMenuRadioItem key={value} value={value} disabled={disabled === true} data-display-mode-option={value}>
        {Icon ? <Icon className="size-4" /> : null}{label ?? t(`mode.${value}`)}
      </DropdownMenuRadioItem>)}
    </DropdownMenuRadioGroup>
    {grid ? <>
      <DropdownMenuSeparator />
      {/* Ticking it leaves the menu open, as every checkbox row in a menu does: the grid is seen coming and going. */}
      <DropdownMenuCheckboxItem checked={grid.value} onCheckedChange={value => grid.onChange(value === true)}
        onSelect={event => event.preventDefault()} data-display-grid="">
        <GridIcon className="size-4" />{t("display.grid")}
      </DropdownMenuCheckboxItem>
    </> : null}
  </>;
}

/**
 * The Display tile: the mode on screen's sphere, opening Display's list (`DisplayMenuItems`). A
 * mode chosen closes it; the Grid switch leaves it open. Projection is a tile of its own that switches
 * on a click (`ProjectionToggle.jsx`); on a phone Display is More's submenu instead (`RendererShell.jsx`).
 */
export default function DisplayPopover({ disabled = false, boundary = null, tooltipSide = "top", onOpenChange, mode, grid = null, className = null, side = "bottom", align = "center",
  icon = null }) {
  const { t } = useI18n();
  const tileClass = useStripButtonClass();
  const current = mode.options.find(option => option.value === mode.value) || mode.options[0];
  // The mode's own sphere, or the view's one glyph for Display (`icon`) where its modes have none.
  const Icon = icon || current?.Icon;
  const currentLabel = current?.label ?? t(`mode.${current?.value || "solid"}`);
  return <DropdownMenu modal={false} onOpenChange={onOpenChange}>
    <DropdownMenuTrigger asChild>
      <ToolbarButton label={t("display.modeCurrent", { mode: currentLabel })} tooltip={t("display.label")} tooltipSide={tooltipSide} disabled={disabled}
        className={className || tileClass} data-display-mode={current?.value}>
        {Icon ? <Icon /> : null}
      </ToolbarButton>
    </DropdownMenuTrigger>
    {/* Closes with no exit animation, so a quick second press always reaches the tile. */}
    <DropdownMenuContent side={side} align={align} sideOffset={6} collisionPadding={8} collisionBoundary={boundary || undefined} aria-label={t("display.label")}
      className={cn(FLOATING_SURFACE_CLASS, "w-44 data-[state=closed]:animate-none!")}>
      <DropdownMenuLabel className="text-muted-foreground">{t("display.label")}</DropdownMenuLabel>
      <DisplayMenuItems mode={mode} grid={grid} />
    </DropdownMenuContent>
  </DropdownMenu>;
}
