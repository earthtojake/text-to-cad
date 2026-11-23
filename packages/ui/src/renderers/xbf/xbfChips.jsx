import { useEffect, useMemo, useState } from "react";
import { isPreviewId } from "@cad/core/lib/cadRefs.js";
import { fetchXbfElementFacts } from "@cad/core/lib/xbf/xbfDocument.js";
import { parseXbfElementId } from "@cad/core/lib/xbf/xbfScene.js";
import { formatPromptReference } from "@cad/core/prompt";
import { formatNumber } from "../kit/inspector/referenceRows.jsx";
import { english } from "../../i18n/core.js";
import { useI18n } from "@cad/ui/i18n";

// What is selected in an engine document, as Quick Edit's chips -- as the STEP renderer's were:
// a part or subassembly a chip of its own, its card its part count (a
// subassembly's), size, volume and mass; faces and edges a chip for each kind on each part -- "base ·
// face 3" alone, "base · 6 faces" for several -- its card its part and its key measure (a face's area,
// an edge's length), which the engine measures on the exact shape when the element is picked
// (`fetchXbfElementFacts`).
//
// Each selected thing is also a reference into the document: the engine's canonical refs
// (`xbfTree.js`: `refOf`, `elementRefOf`), the ones `cad <type> inspect` and `select` read, for an .xbf,
// a STEP and a model alike: a part or subassembly by its label, or its occurrence path where the
// label is shared (`hand/finger.2`), an element by its name, else its kind and number, under it
// (`hand/finger.2/face 7`).

const EMPTY = Object.freeze([]);
const PLURAL = Object.freeze({ face: "faces", edge: "edges" });

/**
 * A face's or an edge's key measurements, as a STEP's card reads its pick data
 * (`referenceMeasurements.js`): the diameter and radius of a round one, an edge's length (an arc's,
 * a circle's circumference) and an arc's sweep, a face's area, a torus's radii.
 * Each row's name in `t`'s language (English unless one is given).
 * @returns {[string, number, string][]}
 */
export function xbfMeasurementRows(kind, facts, t = english) {
  if (!facts) return [];
  const positive = value => (Number(value) > 0 ? Number(value) : null);
  const type = kind === "edge" ? facts.curve : facts.surface;
  const circular = kind === "edge" && type === "circle";
  const radius = circular || (kind === "face" && ["cylinder", "sphere"].includes(type)) ? positive(facts.radius) : null;
  const span = circular ? positive(facts.sweepRadians) : null;
  const sweep = span !== null && span <= 2 * Math.PI + 1e-8 ? Math.min(span, 2 * Math.PI) : null;
  const arc = sweep !== null && sweep < 2 * Math.PI - 1e-8;
  const length = kind === "edge" ? (radius !== null && sweep !== null ? radius * sweep : positive(facts.length)) : null;
  const rows = [];
  if (radius !== null) rows.push([t("measure.diameter"), 2 * radius, "mm"], [t("measure.radius"), radius, "mm"]);
  if (length !== null) rows.push([t(arc ? "measure.arcLength" : circular && sweep !== null ? "measure.circumference" : "measure.length"), length, "mm"]);
  if (arc) rows.push([t("measure.sweepAngle"), sweep * 180 / Math.PI, "°"]);
  if (kind === "face" && Number.isFinite(Number(facts.area))) rows.push([t("measure.area"), Number(facts.area), "mm²"]);
  if (kind === "face" && type === "torus") {
    if (positive(facts.majorRadius)) rows.push([t("measure.majorRadius"), Number(facts.majorRadius), "mm"]);
    if (positive(facts.minorRadius)) rows.push([t("measure.tubeRadius"), Number(facts.minorRadius), "mm"]);
  }
  return rows;
}


// A card's numbers, read at a glance: three significant figures (`8.14`, `0.378`, `30`), a number of four
// figures or more whole (`1,037`), so no value runs to seven digits, in the unit its size reads best in.
// Display alone: what the engine reports and an agent reads (`cad inspect`, the references) is never
// rounded here.
const significant = value => {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "—";
  return numeric.toLocaleString(undefined, Math.abs(numeric) >= 1000 ? { maximumFractionDigits: 0 } : { maximumSignificantDigits: 3 });
};
// A unit a step up once the number would pass four figures in the smaller one.
const scaled = (value, steps) => {
  const numeric = Math.abs(Number(value));
  const [unit, size] = steps.find(([, size], at) => at === steps.length - 1 || numeric < size * 1e4) || steps.at(-1);
  return `${significant(Number(value) / size)} ${unit}`;
};
/** A length in mm, as a card shows it. */
export const xbfLengthText = mm => `${significant(mm)} mm`;
/** An area in mm², as a card shows it: mm², then cm² past 10,000 mm². */
export const xbfAreaText = mm2 => scaled(mm2, [["mm²", 1], ["cm²", 100], ["m²", 1e6]]);
/** A volume in mm³, as a card shows it: mm³, then cm³ past 10,000 mm³, then m³. */
export const xbfVolumeText = mm3 => scaled(mm3, [["mm³", 1], ["cm³", 1e3], ["m³", 1e9]]);

/**
 * What a part or subassembly weighs, as its card says it: its parts' volumes by their materials'
 * densities, in kg, or in g under 10 g (8.14 g, not 0.008138 kg) and mg under 10 mg, three significant
 * figures; "no material" where none has one, and how many have none where only some do, in `t`'s
 * language (English unless one is given).
 */
export function xbfMassText(measured, t = english) {
  if (!measured) return "";
  if (measured.mass === null || measured.mass === undefined) return t("part.noMaterial");
  const kg = Number(measured.mass);
  const text = Math.abs(kg) >= 0.01 ? `${significant(kg)} kg` : Math.abs(kg) >= 1e-5 ? `${significant(kg * 1e3)} g` : `${significant(kg * 1e6)} mg`;
  return measured.unweighed > 0 ? t("part.massUnweighed", { mass: text, count: measured.unweighed }) : text;
}

/**
 * A part's or subassembly's few key facts: how many parts (a subassembly's, every part under it), its size, its volume, its
 * mass — only what is known: no Mass row where no part under it has a material ("no material" is not a fact of it).
 */
export function xbfPartFacts({ assembly, parts, measured }, t = english) {
  const weighed = measured?.mass !== null && measured?.mass !== undefined;
  return [
    ...(assembly && parts > 0 ? [{ label: t("part.parts"), value: formatNumber(parts, 0) }] : []),
    ...(measured?.size ? [{ label: t("part.size"), title: t("part.sizeHint"), value: `${measured.size.map(significant).join(" × ")} mm` }] : []),
    ...(measured?.volume ? [{ label: t("part.volume"), title: t("part.volumeHint"), value: xbfVolumeText(measured.volume) }] : []),
    ...(measured?.volume && weighed ? [{ label: t("part.mass"), title: t("part.massHint"), value: xbfMassText(measured, t) }] : [])
  ];
}

/**
 * The hover tip's words for a pick in an engine document (`kit/inspector/inspect.js`'s `tip`), from the tree
 * and the scene's names alone, measuring nothing: a part's or subassembly's name and its owner ("pin ·
 * hinge"), a face's or an edge's part and its kind and number ("base · face 3"). "" for an id it does not hold.
 */
export function xbfTipper({ scene, tree }) {
  if (!scene) return () => "";
  return (id) => {
    const parsed = parseXbfElementId(id);
    if (!parsed?.kind) {
      const node = tree.nodes.get(id);
      if (!node) return "";
      const owner = (tree.owners.get(id) || []).map(key => tree.nodes.get(key)).filter(item => item && item !== tree.wrapper).at(-1);
      return [node.label, owner?.label].filter(Boolean).join(" · ");
    }
    const part = `i${parsed.instance}`, element = scene.describeElement(id);
    return element ? `${tree.nodes.get(part)?.label || scene.describePart(part)?.name || part} · ${parsed.kind} ${element.ordinal}` : "";
  };
}

/**
 * A pick in an engine document, as its chip's card and the hover tip read it (`kit/inspector/inspect.js`'s
 * `DetailItem`): the thing in focus alone, never what it holds (the Model tree is the hierarchy), with a few
 * key facts:
 * - a part or subassembly (`i3`, `n0.2`): its name; a subassembly's part count, then size, volume and mass
 *   (`xbfPartFacts`); its tip, its owner;
 * - a face or an edge (`i3/face/12`): "base · face 3", its part, and its one key measure, which the engine
 *   measures on the exact shape once it is picked (`facts`, `useXbfElementFacts`): a face's area, an edge's
 *   length (an arc's, a circle's circumference).
 * Null for an id the document does not hold.
 */
export function xbfDescriber({ scene, tree, facts = new Map(), t = english }) {
  if (!scene) return () => null;
  const partName = id => tree.nodes.get(id)?.label || scene.describePart(id)?.name || id;
  const ownersOf = id => (tree.owners.get(id) || []).map(owner => tree.nodes.get(owner)).filter(owner => owner && owner !== tree.wrapper).map(owner => owner.label);
  return (id) => {
    const parsed = parseXbfElementId(id);
    if (!parsed?.kind) {
      const node = tree.nodes.get(id);
      if (!node) return null;
      return { id: `node:${id}`, pick: id, kind: "solid", title: node.label, tip: ownersOf(id).at(-1) || "",
        facts: xbfPartFacts({ assembly: node.kind === "assembly", parts: node.leafPartIds.length, measured: scene.measureParts(node.leafPartIds) }, t) };
    }
    const element = scene.describeElement(id);
    if (!element) return null;
    const part = `i${parsed.instance}`, name = partName(part);
    const measured = xbfMeasurementRows(parsed.kind, facts.get(id), t);
    // Its type as the engine names it (a face's surface, an edge's curve), then every key measure it has.
    const type = parsed.kind === "edge" ? facts.get(id)?.curve : parsed.kind === "face" ? facts.get(id)?.surface : null;
    return { id: `element:${id}`, pick: id, kind: parsed.kind, title: `${name} · ${parsed.kind} ${element.ordinal}`,
      tip: measured[0] ? `${formatNumber(measured[0][1])} ${measured[0][2]}` : "",
      facts: [{ label: t("part.part"), value: name },
        ...(typeof type === "string" && type ? [{ label: t("part.type"), value: type }] : []),
        ...measured.map(([label, value, unit]) => ({ label, value: unit === "mm²" ? xbfAreaText(value) : unit === "mm" ? xbfLengthText(value) : `${formatNumber(value)} ${unit}` }))] };
  };
}

/**
 * What the engine measures of each picked face and edge, asked for as it is picked and again for
 * a new version of the document: by element id, `null` while it is asked.
 */
export function useXbfElementFacts({ source, fetch, version, scene, elementIds }) {
  const [held, setHeld] = useState(() => ({ version: "", facts: new Map() }));
  const key = elementIds.join("\n");
  useEffect(() => {
    if (!source || !scene || !elementIds.length) return undefined;
    const controller = new AbortController();
    const known = held.version === version ? held.facts : new Map();
    const wanted = elementIds.filter(id => !known.has(id));
    if (!wanted.length && held.version === version) return undefined;
    for (const id of wanted) {
      const element = scene.describeElement(id);
      if (!element) continue;
      fetchXbfElementFacts(source, element.key, element.kind, element.ordinal, { fetch, signal: controller.signal })
        .then(facts => setHeld(current => ({ version, facts: new Map(current.version === version ? current.facts : []).set(id, facts) })),
          () => {});
    }
    if (held.version !== version) setHeld({ version, facts: new Map() });
    return () => controller.abort();
    // The elements by their ids, again for a new version of the document.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [source, fetch, version, scene, key]);
  return held.version === version ? held.facts : new Map();
}

/**
 * The selection as Quick Edit's chips, and the references Quick Edit attaches.
 *
 * @param {{ scene: object | null, tree: ReturnType<typeof import("./xbfTree.js").presentXbfTree>, resource: object | null,
 *   selectedIds: string[], facts: Map<string, object>, onRemove: (ids: string[]) => void,
 *   onHover: (ids: string[] | null) => void }} options
 *   `selectedIds`: parts (`i3`), subassemblies (`n0.2`), faces and edges (`i3/face/12`), in the order picked.
 */
export function useXbfSelectionChips({ scene, tree, resource, selectedIds, facts, onRemove, onHover, describe = null }) {
  const { t } = useI18n();
  return useMemo(() => xbfSelectionChips({ scene, tree, resource, selectedIds, facts, onRemove, onHover, describe, t }),
    [scene, tree, resource, selectedIds, facts, onRemove, onHover, describe, t]);
}

/**
 * The resource a pick names: `resource`, the document on screen; or, while the scene draws a preview of a model at
 * parameter values the page has not saved (`previewing`: its URL, `client.previewModelParameters`'s, ending
 * `/documents/model/<preview id>`), that preview, by its id (`<model id>~preview-<token>`), which `cad model
 * inspect` reads while the page holds it. A face of the preview is named where it is, never as the saved model's,
 * whose faces may be others.
 */
export function xbfPickResource(resource, previewing) {
  if (!previewing || resource?.kind !== "cad-model") return resource;
  let id = "";
  try { id = decodeURIComponent(new URL(previewing, "http://view.invalid").pathname.split("/").pop() || ""); }
  catch { return resource; }
  return isPreviewId(id) ? { ...resource, path: id } : resource;
}

/** What `ids` copy, as their chips do: their references, each with the file's path, a line each. */
export function xbfCopyText({ scene, tree, resource, ids }) {
  return xbfSelectionChips({ scene, tree, resource, selectedIds: ids, facts: new Map(), onRemove: () => {}, onHover: () => {} })
    .chips.map(chip => chip.copy).filter(Boolean).join("\n");
}

/**
 * What the nodes `ids` (parts `i3`, subassemblies `n0.2`) copy, a string a node, each as its chip
 * copies it -- and nothing else of a chip, so a long list costs no measuring: the part refs a
 * prompt's view hides and isolates by.
 */
export function xbfNodeRefs({ scene, tree, resource, ids }) {
  if (!scene) return [];
  const { nodeCopy } = referencing({ tree, resource });
  return ids.filter(id => tree.nodes.has(id)).map(nodeCopy).filter(Boolean);
}

// How a node and an element are referenced in `resource`: by the engine's canonical refs, which
// every document the engine draws is named by (an .xbf, a STEP, a model by its id). A node's copy is
// its reference with the file's path, or the document's id.
function referencing({ tree, resource }) {
  const workspace = resource?.kind === "workspace-file" || resource?.kind === "cad-model";
  const referenceOf = selector => (workspace && selector
    ? { resource: { ...resource }, target: { kind: "cad-selector", selectors: [selector] } } : null);
  const nodeSelector = id => tree.refOf(id);
  const elementSelector = (part, element) => tree.elementRefOf(part, element.kind, element.ordinal, element.name);
  const copyOf = (references, fallback) => (references.length ? references.map(formatPromptReference).join("\n") : fallback);
  const nodeCopy = id => {
    const reference = referenceOf(nodeSelector(id));
    return copyOf(reference ? [reference] : [], nodeSelector(id));
  };
  return { referenceOf, nodeSelector, elementSelector, copyOf, nodeCopy };
}

function xbfSelectionChips({ scene, tree, resource, selectedIds, facts, onRemove, onHover, describe = null, t = english }) {
  {
    if (!scene || !selectedIds.length) return { references: EMPTY, chips: EMPTY };
    const { referenceOf, nodeSelector, elementSelector, copyOf, nodeCopy } = referencing({ tree, resource });
    const partName = id => tree.nodes.get(id)?.label || scene.describePart(id)?.name || id;
    // A document of one part names it already: its element chips say their kind and number alone.
    const onePart = new Set(tree.roots.flatMap(root => root.leafPartIds || [])).size === 1;
    const chips = [];
    const references = [];
    const runs = new Map();
    for (const id of selectedIds) {
      const parsed = parseXbfElementId(id);
      if (!parsed?.kind) {
        const node = tree.nodes.get(id);
        if (!node) continue;
        const reference = referenceOf(nodeSelector(id));
        if (reference) references.push(reference);
        chips.push({ key: `node:${id}`, label: node.label, glyph: "solid",
          selectors: reference ? reference.target.selectors : EMPTY, copy: nodeCopy(id),
          detail: describe?.(id) || null,
          onRemove: () => onRemove([id]), onHover: on => onHover(on ? node.leafPartIds : null) });
        continue;
      }
      const element = scene.describeElement(id);
      if (!element) continue;
      const part = `i${parsed.instance}`;
      const reference = referenceOf(elementSelector(part, element));
      if (reference) references.push(reference);
      const runKey = `${part}|${parsed.kind}`;
      let run = runs.get(runKey);
      if (!run) {
        run = { key: `run:${runKey}`, part, kind: parsed.kind, members: [] };
        runs.set(runKey, run);
        chips.push(run);
      }
      run.members.push({ id, element, reference });
    }
    return {
      references,
      chips: chips.map((chip) => {
        if (!chip.members) return chip;
        const name = partName(chip.part);
        const ids = chip.members.map(member => member.id);
        const memberReferences = chip.members.map(member => member.reference).filter(Boolean);
        const selectors = memberReferences.flatMap(reference => reference.target.selectors);
        const fallback = chip.members.map(member => `${member.element.path} ${chip.kind} ${member.element.ordinal}`).join("\n");
        const shared = { key: chip.key, glyph: chip.kind, copy: copyOf(memberReferences, fallback), selectors,
          onRemove: () => onRemove(ids), onHover: on => onHover(on ? ids : null) };
        if (chip.members.length === 1) {
          const [{ element }] = chip.members;
          return { ...shared, label: `${name} · ${chip.kind} ${element.ordinal}`,
            compact: onePart ? { kind: chip.kind, number: String(element.ordinal), words: `${chip.kind} ${element.ordinal}` }
              : { name, kind: chip.kind, number: String(element.ordinal) },
            detail: describe?.(element.id) || null };
        }
        return { ...shared, label: `${name} · ${chip.members.length} ${PLURAL[chip.kind]}`, count: chip.members.length,
          compact: onePart ? { kind: chip.kind, count: chip.members.length, words: `${chip.members.length} ${PLURAL[chip.kind]}` }
            : { name, kind: chip.kind, count: chip.members.length },
          // A run's card: its part, then each member's headline measurement.
          detail: describe ? { id: chip.key, pick: "", kind: chip.kind, title: `${name} · ${chip.members.length} ${PLURAL[chip.kind]}`,
            facts: [{ label: t("part.part"), value: name }, ...chip.members.map(({ element }) => {
              const [, value, unit] = xbfMeasurementRows(chip.kind, facts.get(element.id), t)[0] || [];
              return { label: `${chip.kind} ${element.ordinal}`, value: value === undefined ? "—" : `${formatNumber(value)} ${unit}` };
            })] } : null };
      })
    };
  }
}
