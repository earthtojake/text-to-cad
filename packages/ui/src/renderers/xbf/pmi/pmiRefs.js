import { engineSelectorText, parseEngineRef } from "@text-to-cad/core/lib/cadRefs.js";
import { parseXbfElementId, xbfElementId } from "@text-to-cad/core/lib/xbf/xbfScene.js";

// What a PMI reference names in the document on screen: the scene's element ids (`i3/face/12`) of
// the face, edge or vertex its canonical ref spells, as `cadgen.engine.refs` resolves it against the
// served structure (`refs.resolve_structure`). The engine has already resolved every reference of a
// served annotation (its `status`); this finds the same element on the page, by spelling each
// candidate's canonical ref as the tree does (`xbfTree.js`'s `elementRefOf`) and keeping the ones
// that read exactly as the reference does. Nothing is guessed: a ref that names no element, or one
// the page cannot find, names none.
//
// A repeated part's occurrences carry the same faces, so an annotation of the part is about the same
// faces on each (`pmiFeatureIds`), and drawn at one: the first that is shown (`pmiDrawnAt`).

const KIND_OF_PREFIX = Object.freeze({ f: "face", e: "edge", v: "vertex" });
const NAMES_KEY = Object.freeze({ face: "faceNames", edge: "edgeNames", vertex: "vertexNames" });

/**
 * A resolver of refs into the document `structure` (its tree presented as `tree`,
 * `presentXbfTree`): `resolve(ref)` is the element ids it names, in instance order, none for a ref
 * that names no element. Each answer is kept.
 *
 * @param {object | null} structure
 * @param {{ elementRefOf: (partId: string, kind: string, ordinal: number, name?: string) => string }} tree
 */
export function createPmiRefResolver(structure, tree) {
  const instances = structure?.instances || [];
  const prototypes = structure?.prototypes || [];
  const reversed = new Map();
  // A prototype's names of one kind, by name: what a named element's ordinal is.
  const ordinalsOf = (prototype, kind) => {
    const key = `${prototype}:${kind}`;
    if (!reversed.has(key)) {
      const names = prototypes[prototype]?.[NAMES_KEY[kind]] || {};
      reversed.set(key, new Map(Object.entries(names).map(([ordinal, name]) => [name, Number(ordinal)])));
    }
    return reversed.get(key);
  };
  const nameOf = (prototype, kind, ordinal) => prototypes[prototype]?.[NAMES_KEY[kind]]?.[String(ordinal)] || "";
  const known = new Map();
  const resolve = (ref) => {
    const text = String(ref || "");
    if (known.has(text)) return known.get(text);
    const found = [];
    for (const selector of parseEngineRef(text)?.selectors || []) {
      const element = selector.element;
      if (!element) continue;
      const kind = typeof element === "string" ? KIND_OF_PREFIX[element[0]] : element.kind;
      if (!kind) continue;
      const wanted = engineSelectorText(selector);
      instances.forEach((instance, index) => {
        const prototype = instance?.prototype;
        const ordinal = typeof element === "string" ? ordinalsOf(prototype, kind).get(element) : element.ordinal;
        if (!Number.isInteger(ordinal)) return;
        const partId = xbfElementId(index);
        // As the engine spells it (by name where it has one), or by its ordinal, as a ref may.
        const spelled = [tree.elementRefOf(partId, kind, ordinal, nameOf(prototype, kind, ordinal)), tree.elementRefOf(partId, kind, ordinal, "")];
        if (spelled.includes(wanted)) found.push(xbfElementId(index, kind, ordinal));
      });
    }
    const answer = Object.freeze([...new Set(found)]);
    known.set(text, answer);
    return answer;
  };
  return { resolve };
}

/**
 * Each reference of an entry with the element ids it names on the page (`ids`), by role: what its
 * callout is drawn from and what its selection lights. A reference the engine found broken keeps
 * the ids of its candidates (`candidateIds`), which the section lists, and none of its own.
 */
export function resolvePmiEntryRefs(entry, resolver) {
  return entry.refs.map(ref => ({
    ...ref,
    ids: ref.status === "ok" ? resolver.resolve(ref.ref) : [],
    candidateIds: ref.status === "ambiguous" ? ref.candidates.flatMap(candidate => resolver.resolve(candidate)) : []
  }));
}

// A part's occurrences: the structure's instances of its prototype, in order.
const occurrencesOf = (instances, part) => instances.flatMap((instance, index) => (instance?.prototype === part ? [index] : []));
// An element (`i1/face/2`) as it is on another occurrence of its part (`i2/face/2`).
const onOccurrence = (id, instance) => {
  const parsed = parseXbfElementId(id);
  return parsed?.kind ? xbfElementId(instance, parsed.kind, parsed.ordinal) : null;
};
const unique = ids => [...new Set(ids.filter(Boolean))];

/**
 * The elements an annotation is about on every occurrence of its part (`part`, the structure's
 * prototype; `instances`, the structure's): what a pick of any of them finds it by. One linked to no
 * part, the elements its references name.
 *
 * @param {{ part: number | null, refs: ReadonlyArray<{ ids: readonly string[] }> }} entry  Its refs resolved (`resolvePmiEntryRefs`).
 * @param {readonly object[]} instances
 */
export function pmiFeatureIds(entry, instances) {
  const own = unique(entry.refs.flatMap(ref => ref.ids));
  if (entry.part === null) return own;
  return unique(occurrencesOf(instances, entry.part).flatMap(instance => own.map(id => onOccurrence(id, instance))));
}

/**
 * The first occurrence of `part` that is shown -- not `hidden`, and in the isolation (`isolated`)
 * where one is set, each an instance id (`i3`) as the scene takes them: the instance's index, or
 * undefined where none is. Where a part's PMI is drawn, and its views are seen from.
 *
 * @param {number} part
 * @param {readonly object[]} instances
 * @param {{ hidden?: readonly string[], isolated?: readonly string[] }} [shown]
 */
export function pmiShownOccurrence(part, instances, { hidden = [], isolated = [] } = {}) {
  return occurrencesOf(instances, part).find(index => !hidden.includes(xbfElementId(index))
    && (!isolated.length || isolated.includes(xbfElementId(index))));
}

/**
 * Where an annotation is drawn: at the first occurrence of its part that is shown
 * (`pmiShownOccurrence`) -- its references' elements there (`elements`, by ref: null for one that
 * names none), the elements it is about there (`featureIds`) and that occurrence's placement
 * (`frame`, its matrix). Null where no occurrence of its part is shown: it is not drawn, and stays
 * listed. One whose reference broke is still its part's, drawn where its code placed it; one of
 * no part (another system's, linked to nothing) is in the scene's frame.
 *
 * @param {{ part: number | null, refs: ReadonlyArray<{ ids: readonly string[] }> }} entry  Its refs resolved (`resolvePmiEntryRefs`).
 * @param {readonly object[]} instances
 * @param {{ hidden?: readonly string[], isolated?: readonly string[] }} [shown]
 * @returns {{ elements: (string | null)[], featureIds: string[], frame: number[] | null } | null}
 */
export function pmiDrawnAt(entry, instances, shown = {}) {
  const elements = entry.refs.map(ref => (ref.ids.length === 1 ? ref.ids[0] : null));
  if (entry.part === null) return { elements, featureIds: unique(entry.refs.flatMap(ref => ref.ids)), frame: null };
  const instance = pmiShownOccurrence(entry.part, instances, shown);
  if (instance === undefined) return null;
  const there = id => onOccurrence(id, instance);
  return { elements: elements.map(id => (id ? there(id) : null)), featureIds: unique(entry.refs.flatMap(ref => ref.ids.map(there))),
    frame: instances[instance].matrix || null };
}
