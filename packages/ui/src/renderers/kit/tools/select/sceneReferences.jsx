import { useMemo } from "react";
import { formatPromptReference } from "@text-to-cad/core/prompt";
import { InfoRow, MonoValue } from "../../inspector/referenceRows.jsx";
import { useI18n } from "@text-to-cad/ui/i18n";

const EMPTY = Object.freeze([]);

/** A part's card: its reference id, then what its scene says of it (`describePart`'s facts), each
 * fact's name by its `key` in the view's language where it has one. */
function ScenePartCard({ facts }) {
  const { t } = useI18n();
  return <>{facts.map(fact => <InfoRow key={fact.label} label={fact.key ? t(fact.key) : fact.label}><MonoValue>{fact.value}</MonoValue></InfoRow>)}</>;
}

/**
 * What is selected in a scene, for Quick Edit (`useSceneSelection`): each part as a reference into
 * the file on screen, by the id its scene picks it by — the file's own name for it, whose grammar
 * is its renderer's (`renderers.md`) — and as a chip named as the file names it, its card what the
 * scene says of it (`describePart`).
 * A click on a chip copies its reference; its X drops it; resting on it lights it.
 *
 * @param {{ scene: { describePart?: (id: string) => ({ name: string, facts: { label: string, value: string }[] } | null) } | null,
 *   selection: ReturnType<typeof import("./useSceneSelection.js").useSceneSelection>,
 *   resource: import("@text-to-cad/core/prompt").ResourceRef | null }} options
 */
export function useSceneReferences({ scene, selection, resource }) {
  const { selected, select, hover } = selection;
  return useMemo(() => {
    if (!scene) return { references: EMPTY, chips: EMPTY };
    const reference = id => (resource?.kind === "workspace-file"
      ? { resource: { ...resource }, target: { kind: "cad-selector", selectors: [id] } } : null);
    const references = selected.map(reference).filter(Boolean);
    const chips = selected.map((id) => {
      const part = scene.describePart?.(id) || null;
      const value = reference(id);
      return { key: `part:${id}`, label: part?.name || id, glyph: "solid", id, ...(value ? { copy: formatPromptReference(value) } : {}),
        card: part ? <ScenePartCard facts={part.facts} /> : null,
        onRemove: () => select(id, { multiSelect: true }), onHover: on => hover(on ? id : "") };
    });
    return { references, chips };
  }, [scene, selected, resource, select, hover]);
}
