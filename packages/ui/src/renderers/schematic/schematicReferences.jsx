import { useMemo } from "react";
import { formatPromptReference } from "@cad/core/prompt";
import { InfoRow, MonoValue } from "../kit/inspector/referenceRows.jsx";
import { schematicReferenceId } from "./schematicFacts.js";
import {
  BusEntryKindIcon, JunctionKindIcon, LabelKindIcon, NetKindIcon, NoConnectKindIcon, PinKindIcon, SheetKindIcon, SymbolKindIcon, WireKindIcon
} from "./schematicIcons.jsx";

const EMPTY = Object.freeze([]);
// A chip leads with its kind's glyph, as the Parts' and Nets' rows name the kinds.
const KIND_ICONS = Object.freeze({ part: SymbolKindIcon, symbol: SymbolKindIcon, pin: PinKindIcon, net: NetKindIcon, sheet: SheetKindIcon,
  label: LabelKindIcon, wire: WireKindIcon, bus: WireKindIcon, junction: JunctionKindIcon, no_connect: NoConnectKindIcon, bus_entry: BusEntryKindIcon });
const CHIP_ICON_CLASS = "size-2.5 shrink-0 text-muted-foreground";

function SchematicCard({ facts }) {
  return <>{facts.map(fact => <InfoRow key={fact.label} label={fact.label}><MonoValue>{fact.value}</MonoValue></InfoRow>)}</>;
}

/**
 * What is selected on a schematic, for Quick Edit (`useSceneSelection` over `schematicScene.js`): each
 * pick as a reference into the file on screen and as a chip named as the schematic names it (`R1`,
 * `R1.2`, `net /MID`, `/MID · wire`, `“MID”`, a sheet's name), led by its kind's glyph, its card what the
 * schematic says of it, its ID the reference. A click on a chip copies its reference; its X drops it;
 * resting on it lights it.
 */
export function useSchematicReferences({ scene, selection, resource }) {
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
        card: described ? <SchematicCard facts={described.facts} /> : null,
        onRemove: () => select(id, { multiSelect: true }), onHover: on => hover(on ? id : "") };
    });
    return { references, chips };
  }, [scene, selected, resource, select, hover]);
}
