import { useCallback, useMemo } from "react";
import { formatPromptReference } from "@cad/core/prompt";
import { english, useI18n } from "@cad/ui/i18n";

const EMPTY = Object.freeze([]);

/**
 * A part, as the frame reads a pick (`inspector/inspect.js`'s `DetailItem`), from what its scene says of it
 * (`describePart`: its name, its facts — each named by its `key` in the view's language where it has one —
 * and, where the scene has one, its `tip`).
 */
export function scenePartItem(part, id, t = english) {
  if (!part) return null;
  return { id: `part:${id}`, pick: id, kind: part.kind || "solid", title: part.name || id, tip: part.tip || "",
    facts: (part.facts || EMPTY).map(fact => ({ ...fact, label: fact.key ? t(fact.key) : fact.label })) };
}

/** A scene's parts described (`scenePartItem` over its `describePart`), in the view's language. */
export function useSceneDescribe(scene) {
  const { t } = useI18n();
  return useCallback(id => scenePartItem(scene?.describePart?.(id) || null, id, t), [scene, t]);
}

/**
 * A scene's picks as its frame reads them (`inspector/inspect.js`'s `Inspect`): what `useSceneSelection`
 * has picked and what the pointer is on in the view (`pointed`), each described (`describe`).
 * The hover tip's words are `tip`'s, else the scene's name for the part alone (`nameOf`), which measures
 * nothing. Null with no scene.
 */
export function useSceneInspect({ scene, selection, describe, tip = null, data = "" }) {
  const { pointed } = selection;
  const named = useCallback(id => scene?.nameOf?.(id) || "", [scene]);
  const words = tip || (scene?.nameOf ? named : null);
  return useMemo(() => (scene ? { describe, tip: words, hovered: pointed || "", data: data || undefined } : null),
    [scene, describe, words, pointed, data]);
}

/**
 * One reference into the file on screen naming `ids`, and what it copies, or null off a workspace file or where
 * the file's grammar cannot name an id (`formatPromptReference` refuses it). A view draws a pick whatever its
 * scene calls it, so a pick that cannot be named is that view's, not a reason to throw where a chip is drawn
 * (a throw inside the hook's `useMemo` takes the whole view down with it): it is no reference and copies nothing.
 * `validatePromptReference` stays strict for what sends or parses a reference; this is the display's guard.
 */
function named(resource, ids) {
  if (resource?.kind !== "workspace-file" || !ids.length) return null;
  const reference = { resource: { ...resource }, target: { kind: "cad-selector", selectors: [...ids] } };
  try { return { reference, text: formatPromptReference(reference) }; } catch { return null; }
}

/** What Copy Reference copies for `ids` in the file on screen: one reference naming them all ("" off a workspace file, or where one cannot be named). */
export function sceneCopyText(resource, ids) {
  return named(resource, ids)?.text ?? "";
}

/**
 * What is selected in a scene, for Quick Edit (`useSceneSelection`): each part as a reference into
 * the file on screen, by the id its scene picks it by — the file's own name for it, whose grammar
 * is its renderer's (`renderers.md`) — and as a chip named as the file names it, its card what the
 * view says of it (`describe`: `useSceneDescribe` unless the view has its own).
 * A click on a chip copies its reference; its X drops it; resting on it lights it. A pick the file's grammar
 * cannot name is still a chip, with nothing to copy, and no reference.
 *
 * @param {{ scene: { describePart?: (id: string) => ({ name: string, facts: { label: string, value: string }[] } | null) } | null,
 *   describe?: ((id: string) => import("../../inspector/inspect.js").DetailItem | null) | null,
 *   selection: ReturnType<typeof import("./useSceneSelection.js").useSceneSelection>,
 *   resource: import("@cad/core/prompt").ResourceRef | null, group?: string }} options
 *   `group`: what Quick Edit groups the chips as (`ReferenceChips.jsx`'s `CHIP_GROUPS`): a scene's parts, a drawing's entities.
 */
export function useSceneReferences({ scene, selection, resource, describe = null, group = "part" }) {
  const { selected, select, hover } = selection;
  const own = useSceneDescribe(scene);
  const described = describe || own;
  return useMemo(() => {
    if (!scene) return { references: EMPTY, chips: EMPTY };
    const names = selected.map(id => named(resource, [id]));
    const references = names.map(name => name?.reference).filter(Boolean);
    const chips = selected.map((id, at) => {
      const detail = described(id);
      return { key: `part:${id}`, label: detail?.title || id, glyph: "solid", group, id, ...(names[at] ? { copy: names[at].text } : {}),
        detail,
        onRemove: () => select(id, { multiSelect: true }), onHover: on => hover(on ? id : "") };
    });
    return { references, chips };
  }, [scene, selected, resource, select, hover, described, group]);
}
