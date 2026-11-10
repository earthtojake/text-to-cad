import { ToolSettingsMenu } from "../ToolModeMenu.jsx";
import { filterControl, tickAllKinds, tickFilter } from "./selectFilter.js";
import { FilterRow, SelectionToolSection } from "./SelectionSettings.jsx";
import { useControlUsage } from "../../../../usage/controls.js";
import { useI18n } from "@cad/ui/i18n";

/**
 * What a picking tool takes, every file's: the chevron after its button on the strip, whose dropdown
 * is the kit's anatomy (`SelectionSettings.jsx`) — an optional "Selection tool" section (`tools`:
 * Select's Select and Box select, how a pick is made, beside what it takes), then one row, "Filter"
 * (`FilterRow`), whose submenu ticks the `kinds` a click may take, All first, and the `extras` that are
 * no kind after them. The filter is a list (`value`, `selectFilter.js`), kept in `order` (every id it
 * may hold; the kinds then the extras unless said). Ticking leaves the submenu up, and each press is
 * counted (`filterControl`). Measure's menu is this one too (`MeasureFilterMenu.jsx`): `name` marks its
 * trigger and boxes (`data-<name>-filter-trigger`, `data-<name>-filter-row`, `data-<name>-filter`) and
 * `triggerName` names its chevron and its dropdown ("Measure filter"), so the two chevrons on the strip
 * are told apart. The chevron's name says what is ticked: "Filter: everything" while every kind and every
 * extra that is a thing of its own (Position) is, then any `modifier` extra ticked ("everything, Locked
 * items": a modifier of what the kinds take, which "everything" needs neither way); else the kinds and
 * extras ticked ("Filter: Faces, Position"); else "Filter: nothing".
 *
 * @param {{ value: readonly string[], onChange(filter: readonly string[]): void,
 *   kinds: readonly { id: string, label: string }[], extras?: readonly { id: string, label: string, modifier?: boolean }[],
 *   order?: readonly string[], disabled?: boolean, name?: string, triggerName?: string,
 *   tools?: { items: readonly { id: string, label: string, icon?: import("react").ReactNode }[], value: string, onChange(id: string): void } | null }} props
 */
export default function SelectFilterMenu({ value, onChange, kinds, extras = [], order = null, disabled = false, tools = null, name = "select", triggerName }) {
  const { t } = useI18n();
  const controls = useControlUsage();
  const kept = order ?? [...kinds, ...extras].map(item => item.id);
  const kindIds = kinds.map(kind => kind.id);
  const ticked = id => value.includes(id);
  const on = [...kinds, ...extras].filter(item => ticked(item.id));
  // Everything: every kind, and every extra that is a thing of its own (Position), whatever a modifier says.
  const every = [...kinds, ...extras.filter(extra => !extra.modifier)].every(item => ticked(item.id));
  const modifiers = extras.filter(extra => extra.modifier && ticked(extra.id)).map(extra => extra.label);
  const mode = every ? [t("select.everything"), ...modifiers].join(", ") : on.map(item => item.label).join(", ") || t("select.nothing");
  const title = triggerName ?? t("select.filter");
  return <ToolSettingsMenu label={title} contentClassName="w-auto" disabled={disabled} trigger="chevron"
    triggerLabel={t("select.filterCurrent", { filter: title, mode })}
    triggerProps={{ [`data-${name}-filter-trigger`]: every ? "all" : on.map(item => item.id).join(" ") || "none" }}>
    {tools ? <SelectionToolSection tools={tools.items} value={tools.value} onChange={tools.onChange} /> : null}
    <FilterRow name={name} kinds={kinds} extras={extras} ticked={ticked}
      onToggle={(id, next) => { controls.used(filterControl(name, id)); onChange(tickFilter(value, id, next, kept)); }}
      onToggleAll={next => { controls.used(filterControl(name, "all")); onChange(tickAllKinds(value, kindIds, next, kept)); }} />
  </ToolSettingsMenu>;
}
