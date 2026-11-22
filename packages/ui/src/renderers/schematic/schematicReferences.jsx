import { useCallback, useMemo } from "react";
import { useI18n } from "@cad/ui/i18n";
import { formatPromptReference } from "@cad/core/prompt";
import { schematicReferenceId } from "./schematicFacts.js";
import { describeSchematicPick, schematicPickTip } from "./schematicTree.js";
import {
  BusEntryKindIcon, JunctionKindIcon, LabelKindIcon, NetKindIcon, NoConnectKindIcon, PinKindIcon, SheetKindIcon, SymbolKindIcon, WireKindIcon
} from "./schematicIcons.jsx";

const EMPTY = Object.freeze([]);
// A chip leads with its kind's glyph, as the Parts' and Nets' rows name the kinds.
const KIND_ICONS = Object.freeze({ part: SymbolKindIcon, symbol: SymbolKindIcon, pin: PinKindIcon, net: NetKindIcon, sheet: SheetKindIcon,
  label: LabelKindIcon, wire: WireKindIcon, bus: WireKindIcon, junction: JunctionKindIcon, no_connect: NoConnectKindIcon, bus_entry: BusEntryKindIcon });
const CHIP_ICON_CLASS = "size-2.5 shrink-0 text-muted-foreground";
// What Quick Edit groups a schematic's picks as (`ReferenceChips.jsx`'s `CHIP_GROUPS`), by what the schematic says each is.
const SCHEMATIC_GROUPS = new Map([["part", "component"], ["symbol", "component"], ["pin", "pin"], ["net", "net"], ["sheet", "sheet"], ["label", "label"],
  ["wire", "wire"], ["bus", "wire"]]);

/** A schematic's picks described (`describeSchematicPick`), in the view's language: what the pane, the cards and the tip read. */
export function useSchematicDescribe(index) {
  const { t } = useI18n();
  return useCallback(id => (index ? describeSchematicPick(index, id, t) : null), [index, t]);
}

/** The hover tip's short words for a pick (`schematicPickTip`), in the view's language. */
export function useSchematicTip(index) {
  const { t } = useI18n();
  return useCallback(id => (index ? schematicPickTip(index, id, t) : ""), [index, t]);
}

/**
 * What is picked on the schematic, as its frame reads it (`kit/inspector/inspect.js`): each pick
 * described (a chip's card, the hover tip's name) and what the pointer is on (`hovered`).
 */
export function useSchematicInspect({ index, describe, tip = null, hovered }) {
  return useMemo(() => (index ? { describe, tip, hovered, data: "schematic" } : null), [index, describe, tip, hovered]);
}

/**
 * What is selected on a schematic, for Quick Edit (`useSceneSelection` over `schematicScene.js`): each
 * pick as a reference into the file on screen and as a chip named as the schematic names it (`R1`,
 * `R1.2`, `net /MID`, `/MID · wire`, `“MID”`, a sheet's name), led by its kind's glyph, its card what the
 * schematic says of it (`describe`). A click on a chip copies its reference; its X drops it;
 * resting on it lights it.
 */
export function useSchematicReferences({ scene, selection, resource, describe = null }) {
  const { selected, select, hover } = selection;
  return useMemo(() => {
    if (!scene) return { references: EMPTY, chips: EMPTY };
    const reference = id => (resource?.kind === "workspace-file"
      ? { resource: { ...resource }, target: { kind: "cad-selector", selectors: [id] } } : null);
    const references = selected.map(reference).filter(Boolean);
    const chips = selected.map((id) => {
      const described = scene.describePart(id);
      const value = reference(id);
      const Icon = KIND_ICONS[described?.glyph] || SymbolKindIcon;
      return { key: `pick:${id}`, label: described?.name || schematicReferenceId(id), icon: <Icon className={CHIP_ICON_CLASS} />,
        group: SCHEMATIC_GROUPS.get(described?.glyph) || "item",
        ...(value ? { copy: formatPromptReference(value) } : {}),
        detail: describe?.(id) || null,
        onRemove: () => select(id, { multiSelect: true }), onHover: on => hover(on ? id : "") };
    });
    return { references, chips };
  }, [scene, selected, resource, select, hover, describe]);
}
