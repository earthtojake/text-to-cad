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

// The camera's two projections, as Display's list names them where a view keeps Projection there.
const PROJECTIONS = Object.freeze(["orthographic", "perspective"]);

/**
 * Display's choices, one list wherever it is shown (the Display tile's menu, a phone's More
 * submenu): the file's modes, then, after a rule, the Grid switch, which every mode draws. A view
 * whose modes are its own names them (`label`), may show a mode that is a state rather than a choice
 * (`disabled`: what the view's own settings came to by hand), and may have no grid. A view that keeps
 * the camera's projection here, a setting it changes seldom, rather than as a tile of its own
 * (`ProjectionToggle.jsx`), ends the list with it (`projection`): after a rule, under its muted name,
 * Orthographic and Perspective, the one on screen ticked.
 *
 * @param {{ mode: { value: string, options: { value: string, label?: string, Icon?: Function, disabled?: boolean }[], onChange(value: string): void },
 *   grid?: { value: boolean, onChange(value: boolean): void } | null,
 *   projection?: { value: string, onChange(value: string): void } | null }} props
 */
export function DisplayMenuItems({ mode, grid = null, projection = null }) {
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
    {projection ? <>
      <DropdownMenuSeparator />
      <DropdownMenuLabel className="text-muted-foreground">{t("projection.label")}</DropdownMenuLabel>
      <DropdownMenuRadioGroup aria-label={t("projection.label")} value={projection.value === "perspective" ? "perspective" : "orthographic"}
        onValueChange={value => { if (value !== projection.value) projection.onChange(value); }}>
        {PROJECTIONS.map(value => <DropdownMenuRadioItem key={value} value={value} data-display-projection={value}>{t(`projection.${value}`)}</DropdownMenuRadioItem>)}
      </DropdownMenuRadioGroup>
    </> : null}
  </>;
}

/**
 * The Display tile, on the strip after Projection's (a board's after its Flip and 2D/3D): the mode on
 * screen's sphere, opening Display's list (`DisplayMenuItems`) under it. A mode chosen closes it, as a
 * projection chosen does; the Grid switch leaves it open. Projection is otherwise a tile of its own that
 * switches on a click (`ProjectionToggle.jsx`); on a phone Display is More's submenu instead (`RendererShell.jsx`).
 */
export default function DisplayPopover({ disabled = false, boundary = null, tooltipSide = "top", onOpenChange, mode, grid = null, projection = null, icon = null }) {
  const { t } = useI18n();
  const tileClass = useStripButtonClass();
  const current = mode.options.find(option => option.value === mode.value) || mode.options[0];
  // The mode's own sphere, or the view's one glyph for Display (`icon`) where its modes have none.
  const Icon = icon || current?.Icon;
  const currentLabel = current?.label ?? t(`mode.${current?.value || "solid"}`);
  return <DropdownMenu modal={false} onOpenChange={onOpenChange}>
    <DropdownMenuTrigger asChild>
      <ToolbarButton label={t("display.modeCurrent", { mode: currentLabel })} tooltip={t("display.label")} tooltipSide={tooltipSide} disabled={disabled}
        className={tileClass} data-display-mode={current?.value}>
        {Icon ? <Icon /> : null}
      </ToolbarButton>
    </DropdownMenuTrigger>
    {/* Closes with no exit animation, so a quick second press always reaches the tile. */}
    <DropdownMenuContent align="center" sideOffset={6} collisionPadding={8} collisionBoundary={boundary || undefined} aria-label={t("display.label")}
      className={cn(FLOATING_SURFACE_CLASS, "w-44 data-[state=closed]:animate-none!")}>
      <DropdownMenuLabel className="text-muted-foreground">{t("display.label")}</DropdownMenuLabel>
      <DisplayMenuItems mode={mode} grid={grid} projection={projection} />
    </DropdownMenuContent>
  </DropdownMenu>;
}
