import { useMemo, useState } from "react";
import { referenceMeasurements } from "../../workbench/referenceMeasurements.js";
import { nodeVolume } from "../../workbench/partVolume.js";
import { STEP_MODEL_ROOT_ID, stepTreeNodeLeafPartIds } from "@text-to-cad/core/lib/step/stepTree.js";
import { stepPartNameFromFile, stepProductName } from "@text-to-cad/core/lib/step/productName.js";

import { TooltipHint } from "@text-to-cad/ui/primitives/tooltip";
import { InfoRow, MonoValue, formatNumber } from "../../../kit/inspector/referenceRows.jsx";
import { Select, SelectContent, SelectItem, SelectTrigger } from "@text-to-cad/ui/primitives/select";

// A selected "element" is either a topology reference (face / edge / solid,
// carrying reference.pickData) or an assembly node (component / subassembly).
// Measurements use the current STEP selection, including its occurrence transforms.

const SELECTOR_TYPE_LABELS = Object.freeze({
  face: "Face",
  edge: "Edge",
  shape: "Solid",
  occurrence: "Component"
});

// A part's overall size, from its bounding box.
function boxSize(source) {
  const bbox = source?.bbox || source?.boundingBox || null;
  const min = Array.isArray(bbox?.min) ? bbox.min : null;
  const max = Array.isArray(bbox?.max) ? bbox.max : null;
  if (!min || !max) {
    return null;
  }
  const dims = [0, 1, 2].map((axis) => Math.abs((Number(max[axis]) || 0) - (Number(min[axis]) || 0)));
  return dims.some((value) => value > 1e-9) ? dims : null;
}

function isPartNode(item) {
  return Boolean(item) && !item.pickData && (item.nodeType || Array.isArray(item.children));
}


function MeasurementRows({rows}) {
  return rows.map(([label,value,unit])=><InfoRow key={label} label={label}><MonoValue>{`${formatNumber(value)} ${unit}`}</MonoValue></InfoRow>);
}

// A face's or an edge's own measurements: its area, its length, the radii of a round one, an
// arc's sweep. Where it is (its centre, its normal), what kind it is and whose it is are the
// heading's and the view's to say.
function TopologyDetail({ reference }) {
  return <MeasurementRows rows={referenceMeasurements(reference).rows} />;
}

// A component's or a subassembly's: how many parts, its overall size and its volume.
function PartDetail({ node, size, meshData }) {
  const isAssembly =
    String(node.nodeType || "").trim() === "assembly" ||
    (Array.isArray(node.children) && node.children.length > 0);
  const partCount = Array.isArray(node.leafPartIds)
    ? node.leafPartIds.length
    : Array.isArray(node.children)
      ? node.children.length
      : 0;
  const volume = useMemo(() => nodeVolume(node, meshData), [node, meshData]);
  return <>
    {isAssembly && partCount > 0 ? (
      <InfoRow label="Parts"><MonoValue>{formatNumber(partCount, 0)}</MonoValue></InfoRow>
    ) : null}
    {size && <SizeRow size={size}/>}
    {volume !== null && <VolumeRow volume={volume}/>}
  </>;
}

// From the displayed mesh: exact for flat faces, a close approximation where faces curve.
function VolumeRow({ volume }) {
  return <InfoRow label="Volume" title="Approximate mesh volume">
    <MonoValue>{formatNumber(volume, volume >= 100 ? 0 : 2)} mm³</MonoValue>
  </InfoRow>;
}

function SizeRow({ size }) {
  return <InfoRow label="Size" title="XYZ bounding size"><MonoValue>{size.map(value=>formatNumber(value)).join(' × ')} mm</MonoValue></InfoRow>;
}

function itemKey(item) {
  return String(item?.id || item?.occurrenceId || item?.displaySelector || "").trim();
}

/**
 * A reference as a person reads it: its own label when it has one (a part's or subassembly's
 * name, a named face), otherwise where it is and what — "base · face 3" — from its part as the
 * tree names it (`partName`) and its selector's last token. A generated label that only
 * restates the selector ("Face o1.1.f3") is not a name, and neither is an XCAF label entry
 * (`=>[0:1:1:2]`, `stepProductName`). A single-part file's part with no name of its own is the
 * file's ("l_bracket · face 11"): the tree's root is that part, named after the file. Never the
 * raw id: that is what a copy carries, with the file it is in.
 */
function referenceName(item, meshData, partName) {
  if (isPartNode(item)) return String(item.name || item.displayName || "").trim() || itemKey(item);
  const selector = String(item.displaySelector || item.normalizedSelector || item.id || "").split("|").pop();
  const token = selector.split(".").filter(Boolean).pop() || "";
  const own = [item.name, item.pickData?.name, item.label].map(stepProductName)
    .find(value => value && !(token && value.includes(token)) && !value.includes(selector));
  if (own) return own;
  const kind = (SELECTOR_TYPE_LABELS[item.selectorType] || "Reference").toLowerCase();
  const number = token.match(/^[a-z]+(\d+)$/i)?.[1] || "";
  const occurrence = item.occurrenceId || selector.slice(0, -token.length - 1);
  const parts = Array.isArray(meshData?.parts) ? meshData.parts : [];
  const part = parts.find(entry => [entry.occurrenceId, entry.id].includes(occurrence));
  // The part's own name, where it is one: an occurrence with none goes by its id, and that is
  // the last resort here, after the name a single-part file gives its part.
  const partLabel = [part?.name, part?.displayName].map(stepProductName).find(value => value && value !== occurrence) || "";
  const fileName = stepPartNameFromFile(partName?.(STEP_MODEL_ROOT_ID));
  const parent = [item.pickData?.sourceName, item.sourceName, partName?.(occurrence), partLabel, fileName, occurrence]
    .map(stepProductName).find(Boolean) || "";
  return [parent, number ? `${kind} ${number}` : kind].filter(Boolean).join(" · ");
}

/**
 * The Reference panel's heading and rows for what is selected, compact: the heading names the
 * reference (its name, or its part and kind) and the rows are its key measurements alone — a
 * face's area and a round face's radii, an edge's length, radii and sweep, a part's or a
 * subassembly's part count, size and volume. What a person copies for their agent (the reference,
 * with its file) is the panel's Copy; its raw id, where it sits and points, and its material are
 * not rows. With several selected, the heading is a picker that browses them; it never changes
 * the selection, and it is the only thing a multi-selection adds: the rows are always the browsed
 * reference's alone. `null` with nothing to say.
 *
 * `measurements.size`: the selection's overall size. `partsSize(ids)`: the overall size of these
 * parts together, so a part or subassembly browsed among several has its own.
 *
 * @returns {{ title: import("react").ReactNode, content: import("react").ReactNode } | null}
 */
export function useStepReference({ references = [], meshData = null, measurements = null, partsSize = null, partName = null }) {
  const items = useMemo(() => Array.isArray(references) ? references.filter(Boolean) : [], [references]);
  const idsKey = JSON.stringify(items.map(itemKey));
  const [browsed, setBrowsed] = useState(null);
  // A new selection shows its newest reference immediately, without an effect
  // briefly rendering the previous reference first.
  const activeItem = (browsed?.selection === idsKey && items.find(item=>itemKey(item) === browsed.id)) || items.at(-1);
  // Parts measured without a reference of their own: their overall size is all there is to say.
  const partsOnlySize = !items.length && measurements?.size;
  if (!activeItem && !partsOnlySize) return null;

  const name = item => referenceName(item, meshData, partName);
  // Flush with the rows' labels: the trigger brings no inset of its own. Several references
  // add their count ("1/2") so the name reads as a chooser. It is quiet like the heading's other
  // buttons: no fill on hover in either theme — only its chevron comes up to full strength — and
  // nothing that changes its size, so hovering never moves the heading.
  const at = items.indexOf(activeItem) + 1;
  const title = items.length > 1 ? <Select value={itemKey(activeItem)} onValueChange={id=>setBrowsed({selection:idsKey,id})}>
    <SelectTrigger size="sm" aria-label="Inspect selected reference" data-reference-picker=""
      className="!h-6 min-w-0 max-w-full gap-1 rounded-sm border-none bg-transparent !px-0 text-tiny leading-4 shadow-none hover:bg-transparent focus-visible:ring-2 focus-visible:ring-ring/45 dark:bg-transparent dark:hover:bg-transparent [&_svg]:size-3 [&_svg]:opacity-50 hover:[&_svg]:opacity-100 data-[state=open]:[&_svg]:opacity-100">
      <span className="flex min-w-0 flex-1 items-baseline gap-1.5 text-left" data-reference-label="">
        <span className="min-w-0 truncate">{name(activeItem)}</span>
        <span className="shrink-0 text-tiny text-muted-foreground tabular-nums" data-reference-count="">{at}/{items.length}</span>
      </span>
    </SelectTrigger>
    <SelectContent className="max-w-[max(var(--radix-select-trigger-width),12rem)]">{items.map(item=><SelectItem className="break-all" key={itemKey(item)} value={itemKey(item)}>{name(item)}</SelectItem>)}</SelectContent>
  </Select> : activeItem ? <TooltipHint content={name(activeItem)} overflowOnly><span className="block truncate" data-reference-label="">{name(activeItem)}</span></TooltipHint> : null;
  const content = <div className="flex min-w-0 flex-col text-tiny font-normal">
    {partsOnlySize && <SizeRow size={partsOnlySize}/>}
    {activeItem && (isPartNode(activeItem)
      ? <PartDetail node={activeItem} meshData={meshData} size={boxSize(activeItem) || partsSize?.(stepTreeNodeLeafPartIds(activeItem))
        || (items.length === 1 ? measurements?.size : null)}/>
      : <TopologyDetail reference={activeItem}/>)}
  </div>;
  return { title, content };
}
