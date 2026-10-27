import { useMemo } from "react";
import { formatPromptReference } from "@text-to-cad/core/prompt";
import { InfoRow, MonoValue } from "../kit/inspector/referenceRows.jsx";
import { boardReferenceId } from "./boardFacts.js";
import { NetKindIcon, PadKindIcon, PartKindIcon } from "./boardIcons.jsx";

const EMPTY = Object.freeze([]);
// A chip leads with its kind's glyph, as Select's filter names the kinds: a part, a pad, a net or its copper; a point keeps the pick's vertex.
const KIND_ICONS = Object.freeze({ solid: PartKindIcon, face: PadKindIcon, edge: NetKindIcon });
const CHIP_ICON_CLASS = "size-2.5 shrink-0 text-muted-foreground";
const chipIcon = (glyph) => {
  const Icon = KIND_ICONS[glyph];
  return Icon ? { icon: <Icon className={CHIP_ICON_CLASS} /> } : { glyph };
};

/** A pick's card: what the board says of it (`boardFacts.js`). */
function BoardCard({ facts }) {
  return <>{facts.map(fact => <InfoRow key={fact.label} label={fact.label}><MonoValue>{fact.value}</MonoValue></InfoRow>)}</>;
}

/**
 * What is selected on a board, for Quick Edit (`useSceneSelection` over `boardScene.js`): each pick
 * as a reference into the file on screen, by its board reference, and as a chip named as the board
 * names it (`R1`, `R1.2`, `net VBUS`), led by its kind's glyph — the part, pad and net Select's
 * filter shows (a net's copper is its net's), a point the pick's vertex — its card what the board
 * says of it, its ID the reference.
 * A click on a chip copies its reference (`<file>#R1.2`); its X drops it; resting on it lights it.
 *
 * @param {{ scene: ReturnType<typeof import("./boardScene.js").createBoardScene> | null,
 *   selection: ReturnType<typeof import("../kit/tools/select/useSceneSelection.js").useSceneSelection>,
 *   resource: import("@text-to-cad/core/prompt").ResourceRef | null }} options
 */
export function useBoardReferences({ scene, selection, resource }) {
  const { selected, select, hover } = selection;
  return useMemo(() => {
    if (!scene) return { references: EMPTY, chips: EMPTY };
    const reference = id => (resource?.kind === "workspace-file"
      ? { resource: { ...resource }, target: { kind: "cad-selector", selectors: [id] } } : null);
    const references = selected.map(reference).filter(Boolean);
    const chips = selected.map((id) => {
      const described = scene.describePart(id);
      const value = reference(id);
      return { key: `pick:${id}`, label: described?.name || boardReferenceId(id), ...chipIcon(described?.glyph || "solid"), id: boardReferenceId(id),
        ...(value ? { copy: formatPromptReference(value) } : {}),
        card: described ? <BoardCard facts={described.facts} /> : null,
        onRemove: () => select(id, { multiSelect: true }), onHover: on => hover(on ? id : "") };
    });
    return { references, chips };
  }, [scene, selected, resource, select, hover]);
}
