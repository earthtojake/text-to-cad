import { useCallback, useEffect, useMemo, useState } from "react";
import { pmiCallText, pmiCallout, pmiChangeRequest, pmiChangeSettled, pmiEntryCall, pmiKey, pmiStatusText, readXbfPmi } from "@text-to-cad/core/lib/xbf/xbfPmi.js";
import { pmiConstructions, pmiDrawnOnPart, pmiMovedPlacement, pmiPresentationToPart } from "@text-to-cad/core/lib/xbf/xbfPmiLayout.js";
import { xbfElementId } from "@text-to-cad/core/lib/xbf/xbfScene.js";
import { useI18n } from "@text-to-cad/ui/i18n";
import { xbfElementLabel } from "../xbfChips.jsx";
import { newPmiName } from "./pmiCreate.js";
import { PmiGlyph } from "./pmiGlyphs.jsx";
import { createPmiRefResolver, pmiDrawnAt, pmiFeatureIds, resolvePmiEntryRefs } from "./pmiRefs.js";
import { pmiViewAt, pmiViewFromHere, pmiViewPlacements, pmiViewShows } from "./pmiViews.js";

// An engine document's PMI in the viewer: what the document carries (`structure.pmi`), found on
// the page, drawn and picked; its numbered notes, its parts' named views and what coverage found
// (`readXbfPmi`); which of it the person has hidden (the file's view, `xbfViewSlices`), the view
// picked and whether the faces no requirement is on are lit; and the changes asked for it -- a new
// annotation or note, a view from where the viewport looks now, a value edited, a label moved --
// each the `cadgen.ap242` call it would make the code say, which Quick Edit hands the agent
// (`changeChips`). The viewer writes nothing: the model's code is the document's source, and a
// change reaches the view as the engine's next version.
//
// An annotation is known by its part and its id (`key`: an id is unique only on its part), a view
// by its part and its name: the two may spell one key (a view "A", a datum A), so a view is never
// picked, hidden or lit as an annotation is -- the view picked is its own (`viewKey`). An
// annotation is drawn at the first occurrence of its part that is shown, and about the same faces
// on each (`pmiRefs.js`); a view is seen from that occurrence (`pmiViews.js`), and while it is
// picked only what it shows is drawn, where it places it.

const EMPTY = Object.freeze([]);
const NO_CHANGES = Object.freeze([]);
const NOWHERE = () => ({ camera: null, clip: null });
// A row's glyph: its kind's; a note's, read, a flag note's flag, a general note none (it is words alone).
const glyphOf = entry => (entry.kind === "datum" ? "datum" : entry.kind === "dimension" ? (entry.dimension?.type === "diameter" ? "diameter" : "dimension")
  : entry.kind === "geometric_tolerance" ? entry.tolerance?.characteristic || "frame"
    : entry.kind === "note" && entry.supported ? (entry.note.general ? "" : "flag") : "unsupported");
const unique = ids => [...new Set(ids)];
const callGlyph = call => (call.kind === "datum" ? "datum" : call.kind === "dimension" ? (call.type === "diameter" ? "diameter" : "dimension")
  : call.kind === "note" ? "flag" : call.kind === "view" ? "view" : call.characteristic);

/**
 * @param {{ scene: object | null, tree: ReturnType<typeof import("../xbfTree.js").presentXbfTree>, bounds: { min: number[], max: number[] } | null,
 *   moving: boolean, editable: boolean, hiddenParts?: readonly string[], isolatedParts?: readonly string[],
 *   selectedKey: string, onSelect: (key: string) => void,
 *   here?: () => { camera: { position: number[], target: number[], up: number[] } | null, clip: { axis: string, at: number, invert: boolean } | null } }} options
 *   `moving`: the parts stand elsewhere than built (Explode, a pose): a tolerance is of the part as
 *   made, so its callouts are not drawn meanwhile. `editable`: the document is made from code the
 *   agent can change (an `.xbf`), so changes can be asked for. `hiddenParts`, `isolatedParts`: the
 *   instances hidden and isolated (`i3`), as the scene takes them. `selectedKey`, `onSelect`: the
 *   PMI picked (its `key`), the renderer's (its Escape and its picks clear it). `here`: the
 *   viewport's camera now and the Clip's plane (null while it is off), read when a view is made
 *   from them ("View from here").
 */
export function useXbfPmi({ scene, tree, bounds, moving, editable, hiddenParts = EMPTY, isolatedParts = EMPTY, selectedKey, onSelect, here = NOWHERE }) {
  const { t } = useI18n();
  const structure = scene?.structure || null;
  const instances = structure?.instances || EMPTY;
  const served = useMemo(() => readXbfPmi(structure), [structure]);
  const read = served.entries;
  const resolver = useMemo(() => createPmiRefResolver(structure, tree), [structure, tree]);
  // A part's name, which a request names the part's annotate call by.
  const partNameOf = useCallback(part => (part === null ? "" : structure?.prototypes?.[part]?.name || ""), [structure]);
  const entries = useMemo(() => read.map((entry) => {
    // Each reference named as a pick's chip names it ("plate · face 7"), where it is on the page.
    const refs = resolvePmiEntryRefs(entry, resolver).map(ref => ({ ...ref, name: (ref.ids.length === 1 && xbfElementLabel({ scene, tree }, ref.ids[0])) || ref.written }));
    return { ...entry, refs, callout: pmiCallout(entry), statusText: pmiStatusText(entry), glyph: glyphOf(entry), partName: partNameOf(entry.part),
      featureIds: pmiFeatureIds({ ...entry, refs }, instances), drawable: entry.supported && pmiDrawnOnPart(entry) };
  }), [read, resolver, scene, tree, partNameOf, instances]);
  // Its numbered notes, each part's in their numbers (the general profile Note 1): the same entries.
  const notes = useMemo(() => {
    const byKey = new Map(entries.map(entry => [entry.key, entry]));
    return served.notes.map(note => byKey.get(note.key));
  }, [served, entries]);
  // What coverage found of each part: the faces no requirement is on, found on the page on every
  // occurrence of the part, and the requirements that cannot both hold.
  const coverage = useMemo(() => served.coverage.map(item => ({ ...item, partName: partNameOf(item.part),
    faceIds: pmiFeatureIds({ part: item.part, refs: [{ ids: item.uncovered.flatMap(ref => resolver.resolve(ref)) }] }, instances) })),
  [served, partNameOf, resolver, instances]);

  const [hoveredKey, setHoveredKey] = useState("");
  const [hiddenKeys, setHiddenKeys] = useState(EMPTY);
  const [off, setOff] = useState(false);
  const [changes, setChanges] = useState(NO_CHANGES);
  const [datumFocus, setDatumFocus] = useState("");
  useEffect(() => { setDatumFocus(""); }, [selectedKey, structure]);
  const [viewKey, setViewKey] = useState("");
  const [uncoveredShown, setUncoveredShown] = useState(false);
  const restore = useCallback((slice) => { setHiddenKeys(slice?.hidden || EMPTY); setOff(Boolean(slice?.off)); }, []);
  const known = useMemo(() => new Set(entries.map(entry => entry.key)), [entries]);
  const selected = known.has(selectedKey) ? selectedKey : "";
  const hovered = known.has(hoveredKey) ? hoveredKey : "";

  // Where each is drawn: the first occurrence of its part shown, or nowhere (`pmiDrawnAt`).
  const shownParts = useMemo(() => ({ hidden: hiddenParts, isolated: isolatedParts }), [hiddenParts, isolatedParts]);
  const drawnAt = useMemo(() => new Map(entries.map(entry => [entry.key, pmiDrawnAt(entry, instances, shownParts)])),
    [entries, instances, shownParts]);

  // ---- views: each part's, seen from where its part stands -------------------------------------
  const views = useMemo(() => served.views.map(view => ({ ...view, partName: partNameOf(view.part), at: pmiViewAt(view, instances, shownParts) })),
    [served, partNameOf, instances, shownParts]);
  // The view picked (`viewed`), while it can be applied: its camera and section placed, its part's box.
  const viewed = views.find(item => item.key === viewKey && item.at) || null;
  const viewedBounds = viewed ? scene?.selectionBounds?.([xbfElementId(viewed.at.instance)]) || null : null;
  const view = useMemo(() => (viewed ? { key: viewed.key, name: viewed.name, part: viewed.part, place: viewed.place, ...viewed.at, bounds: viewedBounds } : null),
    // The placed view's own values: a new structure that leaves them as they were keeps it.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [JSON.stringify([viewed?.key, viewed?.place, viewed?.at, viewedBounds])]);
  // A view that can no longer be applied (gone from the document, or its part hidden) is left.
  useEffect(() => { if (viewKey && !viewed) setViewKey(""); }, [viewKey, viewed]);

  // A label dragged and not yet written stands where it was let go, until its change goes; in a view,
  // what the view places stands where it places it.
  const moved = useMemo(() => new Map(changes.filter(change => change.kind === "edit" && change.values.presentation)
    .map(change => [change.entryKey, change.values.presentation])), [changes]);
  const placements = useMemo(() => (viewed ? new Map([...moved, ...pmiViewPlacements(viewed)]) : moved), [moved, viewed]);
  const constructions = useMemo(() => {
    // The scene's elements stand where Explode or a pose moved them: nothing is built from them
    // meanwhile (and nothing pinned), and the parts at rest are built afresh.
    if (!scene || moving) return new Map();
    const drawn = entries.flatMap((entry) => {
      const at = drawnAt.get(entry.key);
      return at ? [{ entry, elements: at.elements, frame: at.frame }] : [];
    });
    return pmiConstructions(drawn, { geometry: id => scene.elementGeometry(id, { points: true }), bounds, placements });
  }, [scene, moving, entries, drawnAt, bounds, placements]);

  const shown = useCallback(key => !off && !hiddenKeys.includes(key), [off, hiddenKeys]);
  // What the file's view keeps of it.
  const slice = useMemo(() => ({ hidden: hiddenKeys, off }), [hiddenKeys, off]);
  // In a view, what it shows alone.
  const inView = useCallback(entry => !viewed || pmiViewShows(viewed, entry), [viewed]);
  const items = useMemo(() => (moving ? EMPTY : entries.filter(entry => constructions.has(entry.key) && shown(entry.key) && inView(entry)).map(entry => ({
    key: entry.key, id: entry.id, kind: entry.kind, callout: entry.callout, status: entry.status, problem: entry.statusText,
    construction: constructions.get(entry.key), selected: entry.key === selected, hovered: entry.key === hovered,
    // Ringed where it stands as it was let go (not where a view places it).
    moved: moved.has(entry.key) && placements.get(entry.key) === moved.get(entry.key)
  }))), [moving, entries, constructions, shown, inView, selected, hovered, moved, placements]);

  // What the picked annotation's (and the one under the pointer's) features light, where it is
  // drawn; a flag note on annotations alone, what they are on (it has no face of its own).
  const drawnFeatureIds = useCallback((key) => {
    const own = drawnAt.get(key)?.featureIds || EMPTY;
    const entry = own.length ? null : entries.find(item => item.key === key);
    if (entry?.kind !== "note" || entry.refs.length || entry.note.general) return own;
    return unique(entry.note.annotations.flatMap(id => drawnAt.get(pmiKey(entry.part, id))?.featureIds || EMPTY));
  }, [drawnAt, entries]);
  const selectedEntry = entries.find(entry => entry.key === selected) || null;
  const focusedDatum = entries.find(entry => entry.key === datumFocus && entry.kind === "datum" && entry.part === selectedEntry?.part) || null;
  // And, where asked, the faces no requirement is on.
  const uncoveredIds = useMemo(() => (uncoveredShown ? coverage.flatMap(item => item.faceIds) : EMPTY), [uncoveredShown, coverage]);
  const highlight = useMemo(() => {
    const picks = drawnFeatureIds((focusedDatum || selectedEntry)?.key);
    return { selected: uncoveredIds.length ? unique([...picks, ...uncoveredIds]) : picks, hovered: drawnFeatureIds(hovered)[0] || null };
  }, [drawnFeatureIds, focusedDatum, selectedEntry, hovered, uncoveredIds]);

  // ---- changes: what Quick Edit hands the agent -------------------------------------------------
  const edit = useCallback((key, values, { placementOnly = false } = {}) => setChanges((now) => {
    const entry = entries.find(item => item.key === key);
    if (!entry?.supported) return now;
    const before = now.find(change => change.key === `edit:${key}`);
    const merged = { ...(before?.values || {}), ...values };
    const change = { key: `edit:${key}`, kind: "edit", entryKey: key, part: entry.part, partName: entry.partName, id: entry.id, values: merged,
      call: pmiEntryCall(entry, merged), placementOnly: placementOnly && (!before || before.placementOnly) };
    // Back to what the document says: nothing to ask.
    if (pmiChangeSettled(change, entries, served.views)) return before ? now.filter(item => item !== before) : now;
    return before ? now.map(item => (item === before ? change : item)) : [...now, change];
  }), [entries, served]);
  // A build that has what a change asked for: the change has gone through, and goes.
  useEffect(() => {
    const settled = change => pmiChangeSettled(change, entries, served.views);
    setChanges(now => (now.some(settled) ? now.filter(change => !settled(change)) : now));
  }, [entries, served]);
  // The new annotations and views asked for (each its part and its call), whose ids, letters and
  // names a next one on that part must not take.
  const pending = useMemo(() => changes.filter(change => change.kind === "add").map(change => ({ part: change.part, call: change.call })), [changes]);
  // A view is known by its name, apart from the annotations' ids (a view "A" beside datum A).
  const add = useCallback((part, call) => setChanges((now) => {
    const id = call.kind === "view" ? call.name : call.id;
    const key = call.kind === "view" ? `add:view:${pmiKey(part, id)}` : `add:${pmiKey(part, id)}`;
    return [...now.filter(change => change.key !== key), { key, kind: "add", part, partName: partNameOf(part), id, call }];
  }), [partNameOf]);
  // The parts the document places (the structure's prototypes): the one a pick of nothing is of,
  // where there is one.
  const parts = useMemo(() => unique(instances.map(instance => instance.prototype)).filter(Number.isInteger), [instances]);
  // "View from here": the viewport's camera and Clip now, as a view of `part` seen from its first
  // occurrence shown (`pmiViewFromHere`), showing what of the part is drawn now.
  const viewFromHere = useCallback((part, name) => {
    const { camera, clip } = here();
    const shows = items.filter(item => item.key === pmiKey(part, item.id)).map(item => item.id);
    return pmiViewFromHere({ part, name, camera, clip, instances, shown: shownParts, shows, t });
  }, [here, items, instances, shownParts, t]);
  const remove = useCallback(key => setChanges(now => now.filter(change => change.key !== key)), []);
  const clearChanges = useCallback(() => setChanges(now => (now.length ? NO_CHANGES : now)), []);
  // Its placement's frame where it is drawn: a placement is written back in its part's frame.
  const frameOf = useCallback(key => drawnAt.get(key)?.frame || null, [drawnAt]);
  // In a view a label stands where the view places it, which a move or a pin (the annotation's own
  // placement, `presentation`) would not say: neither is asked for there.
  const placeable = editable && !viewed;
  const move = useCallback((key, label) => {
    const construction = constructions.get(key);
    if (!construction || !placeable) return;
    edit(key, { presentation: pmiPresentationToPart(pmiMovedPlacement(construction.presentation, label), frameOf(key)) }, { placementOnly: true });
  }, [constructions, edit, placeable, frameOf]);
  // Pin where it is drawn now: an annotation the code never placed, placed in code as it stands.
  const pin = useCallback((key) => {
    const construction = constructions.get(key);
    if (construction && placeable) edit(key, { presentation: pmiPresentationToPart(construction.presentation, frameOf(key)) }, { placementOnly: true });
  }, [constructions, edit, placeable, frameOf]);

  const changeChips = useMemo(() => changes.map((change) => {
    const text = pmiChangeRequest(change);
    const label = change.kind === "add" ? t("pmi.add", { name: newPmiName(change.call, t) })
      : t(change.placementOnly ? "pmi.move" : "pmi.change", { id: change.id });
    return { key: `pmi:${change.key}`, label, icon: <PmiGlyph name={callGlyph(change.call)} className="size-2.5 shrink-0 text-muted-foreground" aria-hidden="true" />,
      request: text, copy: text, onRemove: () => remove(change.key),
      card: <p className="whitespace-pre-wrap break-all px-2 pb-2 font-mono text-micro leading-4 text-foreground" data-pmi-change-card="">{pmiCallText(change.call)}</p> };
  }), [changes, remove, t]);

  return {
    entries, notes, coverage, items, constructions, selectedKey: selected, hoveredKey: hovered, selectedEntry, highlight, drawnFeatureIds,
    select: onSelect, hover: setHoveredKey, datumFocus,
    // The views, each where it is seen from (`at`, null where its part is not shown); the one picked
    // (`viewKey`) and, placed, what applying it takes (`view`: `usePmiViewApplied`'s); a second pick leaves it.
    views, viewKey: view ? viewKey : "", view, chooseView: key => setViewKey(now => (now === key ? "" : key)),
    uncoveredShown, showUncovered: setUncoveredShown,
    focusDatum: key => setDatumFocus(now => (now === key ? "" : key)),
    hiddenKeys, off, setOff, restore,
    toggleHidden: key => setHiddenKeys(now => (now.includes(key) ? now.filter(item => item !== key) : [...now, key])),
    slice,
    editable, placeable, changes, pending, edit, add, remove, clearChanges, move, pin, changeChips,
    parts, viewFromHere
  };
}
