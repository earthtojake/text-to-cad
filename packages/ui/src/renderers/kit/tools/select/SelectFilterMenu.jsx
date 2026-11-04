import { useI18n } from "@cad/ui/i18n";
import { DropdownMenuCheckboxItem, DropdownMenuLabel } from "@cad/ui/primitives/dropdown-menu";
import { ToolSettingsMenu } from "../ToolModeMenu.jsx";

/**
 * A flat view's Select filter, KiCad's Selection Filter: a grid of boxes in its two columns, row by row
 * (`grid`), in the chevron's dropdown after Select's button (`ToolSettingsMenu`), headed "Pick", each
 * box a stock checkbox item, its name alone (no glyph, as KiCad's boxes have none), its check at the
 * row's right end as every menu's. Ticking one leaves the menu open. The chevron's name says what is
 * ticked (`mode`: "everything", "Pads"); `trigger` is its `data-select-filter-trigger`. A board's
 * (`board/BoardSelectFilter.jsx`) and a schematic's (`schematic/SchematicSelectFilter.jsx`) say which
 * boxes there are and what a tick does.
 *
 * @param {{ grid: readonly (readonly string[])[], label(id: string): string, checked(id: string): boolean | "indeterminate",
 *   onToggle(id: string, on: boolean): void, mode: string, trigger: string, disabled?: boolean, data?: string }} props
 *   `data`: the grid's attribute's word (`data-<data>-filter-grid`).
 */
export default function SelectFilterMenu({ grid, label, checked, onToggle, mode, trigger, disabled = false, data = "board" }) {
  const { t } = useI18n();
  return <ToolSettingsMenu label={t("select.filter")} trigger="chevron" disabled={disabled} contentClassName="w-auto"
    triggerLabel={t("select.filterCurrent", { filter: t("select.filter"), mode })}
    triggerProps={{ "data-select-filter-trigger": trigger }}>
    <DropdownMenuLabel className="text-tiny font-normal text-muted-foreground">{t("select.pick")}</DropdownMenuLabel>
    <div className="grid grid-cols-2 gap-x-1" {...{ [`data-${data}-filter-grid`]: "" }}>
      {grid.flat().map(id => <DropdownMenuCheckboxItem key={id} checked={checked(id)} data-select-filter={id}
        onSelect={event => event.preventDefault()} onCheckedChange={on => onToggle(id, on === true)}>
        {label(id)}
      </DropdownMenuCheckboxItem>)}
    </div>
  </ToolSettingsMenu>;
}
