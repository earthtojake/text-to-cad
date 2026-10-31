import { useEffect, useMemo, useState } from "react";
import { fetchXbfElementFacts } from "@text-to-cad/core/lib/xbf/xbfDocument.js";
import { parseXbfElementId } from "@text-to-cad/core/lib/xbf/xbfScene.js";
import { formatPromptReference } from "@text-to-cad/core/prompt";
import { InfoRow, MonoValue, formatNumber } from "../kit/inspector/referenceRows.jsx";
import { english } from "../../i18n/core.js";
import { useI18n } from "@text-to-cad/ui/i18n";

// What is selected in an engine document, as Quick Edit's chips -- as the STEP renderer's were:
// a part or subassembly a chip of its own, its card its part count (a
// subassembly's), size, volume and mass; faces and edges a chip for each kind on each part -- "base ·
// face 3" alone, "base · 6 faces" for several -- its card the key measurements, which the engine
// measures on the exact shape when the element is picked (`fetchXbfElementFacts`).
//
// Each selected thing is also a reference into the document: the engine's canonical refs
// (`xbfTree.js`: `refOf`, `elementRefOf`), the ones `cad inspect` and `select` read, for an .xbf,
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

function MeasurementRows({ kind, facts }) {
  const { t } = useI18n();
  return xbfMeasurementRows(kind, facts, t).map(([label, value, unit]) => <InfoRow key={label} label={label}><MonoValue>{`${formatNumber(value)} ${unit}`}</MonoValue></InfoRow>);
}

/**
 * What a part or subassembly weighs, as its card says it: its parts' volumes by their materials'
 * densities in kg (`measureParts`), "no material" where none has one, and how many have none
 * where only some do, in `t`'s language (English unless one is given).
 */
export function xbfMassText(measured, t = english) {
  if (!measured) return "";
  if (measured.mass === null || measured.mass === undefined) return t("part.noMaterial");
  const kg = Number(measured.mass);
  const text = `${formatNumber(kg, kg >= 10 ? 2 : kg >= 0.01 ? 3 : 6)} kg`;
  return measured.unweighed > 0 ? t("part.massUnweighed", { mass: text, count: measured.unweighed }) : text;
}

/** A part's or subassembly's card: how many parts (a subassembly's), its size, its volume, its mass. */
function PartDetail({ assembly, parts, measured }) {
  const { t } = useI18n();
  return <>
    {assembly && parts > 0 ? <InfoRow label={t("part.parts")}><MonoValue>{formatNumber(parts, 0)}</MonoValue></InfoRow> : null}
    {measured?.size ? <InfoRow label={t("part.size")} title={t("part.sizeHint")}><MonoValue>{measured.size.map(value => formatNumber(value)).join(" × ")} mm</MonoValue></InfoRow> : null}
    {measured?.volume ? <InfoRow label={t("part.volume")} title={t("part.volumeHint")}>
      <MonoValue>{formatNumber(measured.volume, measured.volume >= 100 ? 0 : 2)} mm³</MonoValue>
    </InfoRow> : null}
    {measured?.volume ? <InfoRow label={t("part.mass")} title={t("part.massHint")}>
      <MonoValue>{xbfMassText(measured, t)}</MonoValue>
    </InfoRow> : null}
  </>;
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
export function useXbfSelectionChips({ scene, tree, resource, selectedIds, facts, onRemove, onHover }) {
  return useMemo(() => xbfSelectionChips({ scene, tree, resource, selectedIds, facts, onRemove, onHover }),
    [scene, tree, resource, selectedIds, facts, onRemove, onHover]);
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

function xbfSelectionChips({ scene, tree, resource, selectedIds, facts, onRemove, onHover }) {
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
        chips.push({ key: `node:${id}`, label: node.label, glyph: "solid", id: reference?.target.selectors[0] || nodeSelector(id),
          selectors: reference ? reference.target.selectors : EMPTY, copy: nodeCopy(id),
          card: <PartDetail assembly={node.kind === "assembly"} parts={node.leafPartIds.length} measured={scene.measureParts(node.leafPartIds)} />,
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
          id: selectors.join(", "),
          onRemove: () => onRemove(ids), onHover: on => onHover(on ? ids : null) };
        if (chip.members.length === 1) {
          const [{ element }] = chip.members;
          return { ...shared, label: `${name} · ${chip.kind} ${element.ordinal}`,
            compact: onePart ? { kind: chip.kind, number: String(element.ordinal), words: `${chip.kind} ${element.ordinal}` }
              : { name, kind: chip.kind, number: String(element.ordinal) },
            card: <MeasurementRows kind={chip.kind} facts={facts.get(element.id)} /> };
        }
        return { ...shared, label: `${name} · ${chip.members.length} ${PLURAL[chip.kind]}`,
          compact: onePart ? { kind: chip.kind, count: chip.members.length, words: `${chip.members.length} ${PLURAL[chip.kind]}` }
            : { name, kind: chip.kind, count: chip.members.length },
          card: chip.members.map(({ element }) => {
            const [, value, unit] = xbfMeasurementRows(chip.kind, facts.get(element.id))[0] || [];
            return <InfoRow key={element.id} label={`${chip.kind} ${element.ordinal}`}><MonoValue>{value === undefined ? "—" : `${formatNumber(value)} ${unit}`}</MonoValue></InfoRow>;
          }) };
      })
    };
  }
}
