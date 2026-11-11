import {
  DropdownMenuCheckboxItem, DropdownMenuInlineSub, DropdownMenuInlineSubContent, DropdownMenuInlineSubTrigger, DropdownMenuLabel,
  DropdownMenuRadioGroup, DropdownMenuRadioItem, DropdownMenuSeparator, DropdownMenuSub, DropdownMenuSubContent, DropdownMenuSubTrigger
} from "@cad/ui/primitives/dropdown-menu";
import { cn } from "@cad/ui/utils";
import { useI18n } from "@cad/ui/i18n";
import { FLOATING_SURFACE_CLASS } from "../../../../lib/floatingSurface.js";
import { useStripTouch } from "../stripTouch.js";

// The rows of a picking tool's chevron menu (settings-ui.md, "Select's menu"), one anatomy for every
// file: an optional "Selection tool" section (`SelectionToolSection`), then ONE row, "Filter"
// (`FilterRow`), a stock submenu whose row names it and shows what is ticked, muted, at its right. No
// renderer builds a row of its own.

/**
 * One setting's row: its name, its value muted at the right against the chevron, and its submenu
 * (`children`), named after the setting. A phone has no room beside the menu for a submenu, so on a
 * touch strip the same row opens its choices under it, in the menu itself (`DropdownMenuInlineSub`, as
 * the app menu's Language and the strip's More do).
 *
 * @param {{ label: string, value: string, rowProps?: object, children: import("react").ReactNode }} props
 */
function SettingSubmenu({ label, value, rowProps = null, children }) {
  const inline = useStripTouch();
  const head = <>
    <span className="min-w-0 flex-1 truncate">{label}</span>
    <span className="shrink-0 text-muted-foreground">{value}</span>
  </>;
  if (inline) {
    return <DropdownMenuInlineSub>
      <DropdownMenuInlineSubTrigger aria-label={`${label}: ${value}`} {...rowProps}>{head}</DropdownMenuInlineSubTrigger>
      <DropdownMenuInlineSubContent aria-label={label}>{children}</DropdownMenuInlineSubContent>
    </DropdownMenuInlineSub>;
  }
  return <DropdownMenuSub>
    <DropdownMenuSubTrigger aria-label={`${label}: ${value}`} {...rowProps}>{head}</DropdownMenuSubTrigger>
    {/* Closes with no exit animation, as the menu it hangs from does. */}
    <DropdownMenuSubContent aria-label={label} className={cn(FLOATING_SURFACE_CLASS, "data-[state=closed]:animate-none!")}>
      {children}
    </DropdownMenuSubContent>
  </DropdownMenuSub>;
}

const HEADING_CLASS = "text-tiny font-normal text-muted-foreground";

/**
 * The "Selection tool" section a menu may open with: how a pick is made, apart from what it takes — one
 * of `tools`, each a radio item with its glyph (`data-select-tool`). Choosing one puts the menu away.
 * A rule follows it, before the Filter row.
 *
 * @param {{ tools: readonly { id: string, label: string, icon?: import("react").ReactNode }[], value: string,
 *   onChange(id: string): void }} props
 */
export function SelectionToolSection({ tools, value, onChange }) {
  const { t } = useI18n();
  return <>
    <DropdownMenuLabel className={HEADING_CLASS}>{t("select.tool")}</DropdownMenuLabel>
    <DropdownMenuRadioGroup value={value} onValueChange={onChange}>
      {tools.map(item => <DropdownMenuRadioItem key={item.id} value={item.id} data-select-tool={item.id}>{item.icon}{item.label}</DropdownMenuRadioItem>)}
    </DropdownMenuRadioGroup>
    <DropdownMenuSeparator />
  </>;
}

/**
 * What a filter's row says of what is ticked: "All" when every kind is, the one kind's name when one
 * is, "None" when none is, else how many of how many ("3 of 9").
 *
 * @param {readonly { id: string, label: string }[]} kinds
 * @param {(id: string) => boolean} ticked
 * @param {(key: string, values?: object) => string} t
 */
export function filterSummary(kinds, ticked, t) {
  const on = kinds.filter(kind => ticked(kind.id));
  if (on.length === kinds.length) return t("select.filterAll");
  if (!on.length) return t("select.filterNone");
  if (on.length === 1) return on[0].label;
  return t("select.filterSome", { count: on.length, total: kinds.length });
}

/**
 * "Filter": the kinds a click may take, ticked (KiCad's Selection Filter), every picking tool's. The
 * row sums up what is ticked (`filterSummary`); its submenu holds All — ticked when every kind is, a
 * dash when some are; it ticks or unticks every kind — then, after a rule, the kinds in one column,
 * each its name alone (no glyph, in every file), then, after another rule, the `extras` that are no
 * kind (a board's Locked items, a posable model's Position), which All leaves as they are. Ticking
 * leaves the submenu up. `name` marks each box (`data-<name>-filter`: its id, "all" for All) and the row
 * (`data-<name>-filter-row`).
 *
 * @param {{ name?: string, kinds: readonly { id: string, label: string }[], extras?: readonly { id: string, label: string }[],
 *   ticked(id: string): boolean, onToggle(id: string, on: boolean): void, onToggleAll(on: boolean): void }} props
 */
export function FilterRow({ name = "select", kinds, extras = [], ticked, onToggle, onToggleAll }) {
  const { t } = useI18n();
  const count = kinds.filter(kind => ticked(kind.id)).length;
  const all = count === kinds.length ? true : count ? "indeterminate" : false;
  const keepOpen = event => event.preventDefault();
  const box = (id, label, checked, toggle) => <DropdownMenuCheckboxItem key={id} checked={checked} {...{ [`data-${name}-filter`]: id }}
    onSelect={keepOpen} onCheckedChange={on => toggle(on === true)}>{label}</DropdownMenuCheckboxItem>;
  return <SettingSubmenu label={t("select.filter")} value={filterSummary(kinds, ticked, t)} rowProps={{ [`data-${name}-filter-row`]: "filter" }}>
    {box("all", t("select.filterAll"), all, on => onToggleAll(on))}
    <DropdownMenuSeparator />
    {kinds.map(kind => box(kind.id, kind.label, ticked(kind.id), on => onToggle(kind.id, on)))}
    {extras.length ? <DropdownMenuSeparator /> : null}
    {extras.map(extra => box(extra.id, extra.label, ticked(extra.id), on => onToggle(extra.id, on)))}
  </SettingSubmenu>;
}
