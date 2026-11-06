import { useCallback, useMemo } from "react";
import { formatPromptReference } from "@cad/core/prompt";
import { english, useI18n } from "@cad/ui/i18n";

const EMPTY = Object.freeze([]);

/**
 * A part, as the frame reads a pick (`inspector/inspect.js`'s `DetailItem`), from what its scene says of it
 * (`describePart`: its name, its facts — each named by its `key` in the view's language where it has one —
 * and, where the scene has them, its `tip`, its `what` and its `related`), its id as its ID.
 */
export function scenePartItem(part, id, t = english) {
  if (!part) return null;
  return { id: `part:${id}`, pick: id, kind: part.kind || "solid", title: part.name || id, tip: part.tip || "", what: part.what || "", ref: id,
    facts: (part.facts || EMPTY).map(fact => ({ ...fact, label: fact.key ? t(fact.key) : fact.label })), related: part.related || null };
}

/** A scene's parts described (`scenePartItem` over its `describePart`), in the view's language. */
export function useSceneDescribe(scene) {
  const { t } = useI18n();
  return useCallback(id => scenePartItem(scene?.describePart?.(id) || null, id, t), [scene, t]);
}

/**
 * A scene's picks as its frame reads them (`inspector/inspect.js`'s `Inspect`): what `useSceneSelection`
 * has picked and what the pointer is on in the view (`pointed`), each described (`describe`), and what a
 * row of the pane does — picks it, lights it, frames it (`frame`) — and what its name copies (`copyText`).
 * Null with no scene.
 */
export function useSceneInspect({ scene, selection, describe, frame = null, copyText = null, glyphs = null, data = "" }) {
  const { selected, select, hover, pointed } = selection;
  return useMemo(() => (scene ? { selected, describe, hovered: pointed || "", select, hover, frame, copyText, glyphs, data: data || undefined } : null),
    [scene, selected, describe, pointed, select, hover, frame, copyText, glyphs, data]);
}

/** What Copy Reference copies for `ids` in the file on screen: one reference naming them all ("" off a workspace file). */
export function sceneCopyText(resource, ids) {
  return resource?.kind === "workspace-file" && ids.length
    ? formatPromptReference({ resource: { ...resource }, target: { kind: "cad-selector", selectors: [...ids] } }) : "";
}

/**
 * What is selected in a scene, for Quick Edit (`useSceneSelection`): each part as a reference into
 * the file on screen, by the id its scene picks it by — the file's own name for it, whose grammar
 * is its renderer's (`renderers.md`) — and as a chip named as the file names it, its card what the
 * view says of it (`describe`, the Selected pane's: `useSceneDescribe` unless the view has its own).
 * A click on a chip copies its reference; its X drops it; resting on it lights it.
 *
 * @param {{ scene: { describePart?: (id: string) => ({ name: string, facts: { label: string, value: string }[] } | null) } | null,
 *   describe?: ((id: string) => import("../../inspector/inspect.js").DetailItem | null) | null,
 *   selection: ReturnType<typeof import("./useSceneSelection.js").useSceneSelection>,
 *   resource: import("@cad/core/prompt").ResourceRef | null }} options
 */
export function useSceneReferences({ scene, selection, resource, describe = null }) {
  const { selected, select, hover } = selection;
  const own = useSceneDescribe(scene);
  const described = describe || own;
  return useMemo(() => {
    if (!scene) return { references: EMPTY, chips: EMPTY };
    const reference = id => (resource?.kind === "workspace-file"
      ? { resource: { ...resource }, target: { kind: "cad-selector", selectors: [id] } } : null);
    const references = selected.map(reference).filter(Boolean);
    const chips = selected.map((id) => {
      const detail = described(id);
      const value = reference(id);
      return { key: `part:${id}`, label: detail?.title || id, glyph: "solid", id, ...(value ? { copy: formatPromptReference(value) } : {}),
        detail,
        onRemove: () => select(id, { multiSelect: true }), onHover: on => hover(on ? id : "") };
    });
    return { references, chips };
  }, [scene, selected, resource, select, hover, described]);
}
