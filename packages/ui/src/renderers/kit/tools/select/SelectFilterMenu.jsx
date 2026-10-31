import { DropdownMenuLabel, DropdownMenuRadioGroup, DropdownMenuRadioItem, DropdownMenuSeparator } from "@text-to-cad/ui/primitives/dropdown-menu";
import { ToolSettingsMenu } from "../ToolModeMenu.jsx";
import { pickModeOf } from "./selectFilter.js";
import { useControlUsage } from "../../../../usage/controls.js";
import { useI18n } from "@text-to-cad/ui/i18n";

// A mode as telemetry names it (`usage/controls.js`): `select_filter_faces`; Measure's kinds in the plural.
const PLURAL = Object.freeze({ vertex: "vertices", edge: "edges", face: "faces" });

/**
 * What a picking tool takes, as a CAD tool's selection priority is: the chevron after its button on
 * the strip, whose dropdown is headed "Pick" and lists the tool's modes (`modes`, `selectFilter.js`)
 * as ONE choice — All first, then each kind alone. Choosing one puts the menu away. Whatever
 * follows (`children`: how a pick grows, Group faces and Group edges) comes after a rule. Measure's
 * menu is this one too (`MeasureFilterMenu.jsx`): `name` marks its trigger and rows
 * (`data-<name>-filter-trigger`, `data-<name>-filter`) and `triggerName` names its chevron
 * ("Measure filter"), so the two chevrons on the strip are told apart. The strip's button shows the
 * mode chosen as a badge on the tool's glyph (`modeGlyphs.jsx`'s `ToolModeIcon`). A mode says its `key`
 * in the view's language where it has one, else its `label`.
 *
 * @param {{ value: readonly string[], onChange(filter: readonly string[]): void,
 *   modes: { id: string, label: string, key?: string, kinds: readonly string[], icon?: import("react").ReactNode }[],
 *   disabled?: boolean, children?: import("react").ReactNode, name?: string, triggerName?: string }} props
 */
export default function SelectFilterMenu({ value, onChange, modes, disabled = false, children = null, name = "select", triggerName }) {
  const { t } = useI18n();
  const named = modeOf => modeOf.key ? t(modeOf.key) : modeOf.label;
  const mode = pickModeOf(value, modes);
  const controls = useControlUsage();
  return <ToolSettingsMenu label={t("select.filter")}
    triggerLabel={t("select.filterCurrent", { filter: triggerName ?? t("select.filter"), mode: mode === modes[0] ? t("select.everything") : named(mode) })}
    disabled={disabled} trigger="chevron" triggerProps={{ [`data-${name}-filter-trigger`]: mode === modes[0] ? "all" : mode.id }}>
    <DropdownMenuLabel className="text-tiny font-normal text-muted-foreground">{t("select.pick")}</DropdownMenuLabel>
    <DropdownMenuRadioGroup value={mode.id} onValueChange={id => {
      controls.used(`${name}_filter_${PLURAL[id] ?? id}`);
      onChange([...modes.find(candidate => candidate.id === id).kinds]);
    }}>
      {modes.map(({ id, icon, ...rest }, index) => <DropdownMenuRadioItem key={id} value={id} {...{ [`data-${name}-filter`]: index === 0 ? "all" : id }}>
        {icon}{named(rest)}
      </DropdownMenuRadioItem>)}
    </DropdownMenuRadioGroup>
    {children ? <><DropdownMenuSeparator />{children}</> : null}
  </ToolSettingsMenu>;
}
