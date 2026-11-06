import { useCallback, useMemo } from "react";
import { useI18n } from "@cad/ui/i18n";
import { formatPromptReference } from "@cad/core/prompt";
import { schematicReferenceId } from "./schematicFacts.js";
import { describeSchematicPick } from "./schematicTree.js";
import {
  BusEntryKindIcon, JunctionKindIcon, LabelKindIcon, NetKindIcon, NoConnectKindIcon, PinKindIcon, SheetKindIcon, SymbolKindIcon, WireKindIcon
} from "./schematicIcons.jsx";

const EMPTY = Object.freeze([]);
// A chip leads with its kind's glyph, as the Parts' and Nets' rows name the kinds.
const KIND_ICONS = Object.freeze({ part: SymbolKindIcon, symbol: SymbolKindIcon, pin: PinKindIcon, net: NetKindIcon, sheet: SheetKindIcon,
  label: LabelKindIcon, wire: WireKindIcon, bus: WireKindIcon, junction: JunctionKindIcon, no_connect: NoConnectKindIcon, bus_entry: BusEntryKindIcon });
const CHIP_ICON_CLASS = "size-2.5 shrink-0 text-muted-foreground";

/** A schematic's picks described (`describeSchematicPick`), in the view's language: what the pane, the cards and the tip read. */
export function useSchematicDescribe(index) {
  const { t } = useI18n();
  return useCallback(id => (index ? describeSchematicPick(index, id, t) : null), [index, t]);
}

/**
 * What is picked on the schematic, as its frame reads it (`kit/inspector/inspect.js`): each pick
 * described, what the pointer is on (`hovered`), and what a row of the pane does (`select`, `hover`,
 * `show` — the sheet it is on — `frame`, `onSelect`, `copyText`).
 */
export function useSchematicInspect({ index, describe, selection, hovered, onSelect, show, frame, copyText }) {
  const { selected, select, hover } = selection;
  return useMemo(() => (index ? { selected, describe, hovered, glyphs: KIND_ICONS, data: "schematic", select, hover, show, frame, onSelect, copyText } : null),
    [index, selected, describe, hovered, select, hover, show, frame, onSelect, copyText]);
}

/**
 * What is selected on a schematic, for Quick Edit (`useSceneSelection` over `schematicScene.js`): each
 * pick as a reference into the file on screen and as a chip named as the schematic names it (`R1`,
 * `R1.2`, `net /MID`, `/MID · wire`, `“MID”`, a sheet's name), led by its kind's glyph, its card what the
 * schematic says of it (`describe`, the Selected pane's), its ID the reference. A click on a chip copies its reference; its X drops it;
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
      return { key: `pick:${id}`, label: described?.name || schematicReferenceId(id), icon: <Icon className={CHIP_ICON_CLASS} />, id: schematicReferenceId(id),
        ...(value ? { copy: formatPromptReference(value) } : {}),
        detail: describe?.(id) || null,
        onRemove: () => select(id, { multiSelect: true }), onHover: on => hover(on ? id : "") };
    });
    return { references, chips };
  }, [scene, selected, resource, select, hover, describe]);
}
