import {
  DropdownMenuCheckboxItem, DropdownMenuLabel, DropdownMenuRadioGroup, DropdownMenuRadioItem, DropdownMenuSeparator
} from "@cad/ui/primitives/dropdown-menu";
import { Moon, Sun } from "lucide-react";
import { useI18n } from "@cad/ui/i18n";
import { GridIcon } from "../view-settings/DisplayModeOptions.js";
import { VIEWPORT_BACKGROUNDS } from "@cad/core/lib/viewportTheme.js";
import { useControlUsage } from "../../../usage/controls.js";

// The Background's icons, the app menu's Theme's own: the sun and the moon.
const BACKGROUND_ICONS = Object.freeze({ light: Sun, dark: Moon });
// The camera's two projections, as Display's list names them where a view keeps Projection there.
const PROJECTIONS = Object.freeze(["orthographic", "perspective"]);

/**
 * Display's choices as one list, a phone's More submenu where the host has no navbar (everywhere else they are View's
 * submenus, `ViewSettingsMenu.jsx`): the file's modes, then, after a rule, Show grid, which every mode draws. A view
 * whose modes are its own names them (`label`), may show a mode that is a state rather than a choice
 * (`disabled`: what the view's own settings came to by hand), and may have no grid. A view that keeps
 * the camera's projection here (a board in 3D),
 * ends the list with it (`projection`): after a rule, under its muted name,
 * Orthographic and Perspective, the one on screen ticked. Last, the viewport's **Background**
 * (`background`, `@cad/core/lib/viewportTheme.js`: Light or Dark), the person's, the same in
 * every file and view: after a rule, under its muted name, each with its icon, the one chosen ticked.
 *
 * @param {{ mode: { value: string, options: { value: string, label?: string, Icon?: Function, disabled?: boolean }[], onChange(value: string): void },
 *   grid?: { value: boolean, onChange(value: boolean): void } | null,
 *   projection?: { value: string, onChange(value: string): void } | null }} props
 */
export function DisplayMenuItems({ mode, grid = null, projection = null, background = null }) {
  const { t } = useI18n();
  const usage = useControlUsage();
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
        <GridIcon className="size-4" />{t("display.showGrid")}
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
    {background ? <>
      <DropdownMenuSeparator />
      <DropdownMenuLabel className="text-muted-foreground">{t("display.background")}</DropdownMenuLabel>
      <DropdownMenuRadioGroup aria-label={t("display.background")} value={background.value}
        onValueChange={value => { if (value === background.value) return; usage.used(`viewport_background_${value}`); background.onChange(value); }}>
        {VIEWPORT_BACKGROUNDS.map(value => {
          const Icon = BACKGROUND_ICONS[value];
          return <DropdownMenuRadioItem key={value} value={value} data-display-background={value}><Icon className="size-4" />{t(`display.background.${value}`)}</DropdownMenuRadioItem>;
        })}
      </DropdownMenuRadioGroup>
    </> : null}
  </>;
}
