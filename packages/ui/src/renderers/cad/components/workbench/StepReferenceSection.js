import { useMemo, useState } from "react";
import { cn } from "@hardcore/ui/utils";
import { referenceMeasurements, selectionMeasurements } from "../../workbench/referenceMeasurements.js";
import { stepSelectionMaterialInfo } from "../../workbench/stepSelectionMaterial.js";

import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@hardcore/ui/primitives/select";

// A selected "element" is either a topology reference (face / edge / solid,
// carrying reference.pickData) or an assembly node (component / subassembly).
// Measurements use the current STEP selection, including its occurrence transforms.

const SELECTOR_TYPE_LABELS = Object.freeze({
  face: "Face",
  edge: "Edge",
  shape: "Solid",
  occurrence: "Component"
});

const SURFACE_LABELS = Object.freeze({
  plane: "Planar",
  cylinder: "Cylindrical",
  cone: "Conical",
  sphere: "Spherical",
  torus: "Toroidal",
  spline: "Freeform",
  bspline: "Freeform",
  nurbs: "Freeform"
});

const CURVE_LABELS = Object.freeze({
  line: "Line",
  circle: "Circle",
  arc: "Arc",
  ellipse: "Ellipse",
  spline: "Spline",
  bspline: "Spline"
});

// Onshape-style axis colour coding for coordinate triples.
const AXES = Object.freeze([
  { key: "X", className: "text-rose-500 dark:text-rose-400" },
  { key: "Y", className: "text-emerald-500 dark:text-emerald-400" },
  { key: "Z", className: "text-sky-500 dark:text-sky-400" }
]);

function titleCase(value) {
  const text = String(value || "").trim();
  return text ? text.charAt(0).toUpperCase() + text.slice(1) : "";
}

function formatNumber(value, digits = 2) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return "—";
  }
  return numeric.toLocaleString(undefined, { maximumFractionDigits: digits });
}

function readBbox(source) {
  const bbox = source?.bbox || source?.boundingBox || null;
  const min = Array.isArray(bbox?.min) ? bbox.min : null;
  const max = Array.isArray(bbox?.max) ? bbox.max : null;
  if (!min || !max) {
    return null;
  }
  const dims = [0, 1, 2].map((axis) => Math.abs((Number(max[axis]) || 0) - (Number(min[axis]) || 0)));
  const center = [0, 1, 2].map((axis) => ((Number(min[axis]) || 0) + (Number(max[axis]) || 0)) / 2);
  return dims.some((value) => value > 1e-9) ? { dims, center } : null;
}

function isPartNode(item) {
  return Boolean(item) && !item.pickData && (item.nodeType || Array.isArray(item.children));
}

// Label-column rows keep the value next to its label instead of pushing it to
// the far edge, so the readout scans top-to-bottom.
export function InfoRow({ label, children, title }) {
  return (
    <div className="grid grid-cols-[5rem_minmax(0,1fr)] items-baseline gap-2 py-1" title={title}>
      <span className="text-tiny text-muted-foreground">{label}</span>
      <div className="min-w-0 flex-1 text-tiny text-sidebar-foreground [overflow-wrap:anywhere]">{children}</div>
    </div>
  );
}

export function MonoValue({ children }) {
  return <span className="font-mono tabular-nums">{children}</span>;
}

export function CoordValue({ vector, digits = 2 }) {
  const values = Array.isArray(vector) ? vector : [];
  return (
    <span className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5 font-mono tabular-nums">
      {AXES.map((axis, index) => (
        <span key={axis.key} className="inline-flex items-baseline gap-1">
          <span className={cn("text-micro", axis.className)}>{axis.key}</span>
          <span>{formatNumber(values[index], digits)}</span>
        </span>
      ))}
    </span>
  );
}

const MEASUREMENT_HINTS = {
  'Plane spacing': 'Perpendicular distance between the planes; not the minimum gap between their trimmed faces.',
  'Line spacing': 'Perpendicular distance between the supporting lines; not the gap between their endpoints.',
  'Axis spacing': 'Perpendicular distance between the cylinder axes.',
  'Center distance': 'Straight-line distance between circle centers.',
  'Angle': 'Smaller angle between the directions or planes (0–90°).',
  'Axis angle': 'Smaller angle between the cylinder axes (0–90°).',
};

function MeasurementRows({rows}) {
  return rows.map(([label,value,unit])=><InfoRow key={label} label={label} title={MEASUREMENT_HINTS[label]}><MonoValue>{`${formatNumber(value)} ${unit}`}</MonoValue></InfoRow>);
}

function MaterialChannelValues({ channels }) {
  return (
    <span className="flex flex-wrap items-baseline gap-x-2.5 gap-y-0.5">
      {channels.map((channel) => (
        <span key={channel.key} className="inline-flex items-baseline gap-1">
          <span className="text-micro text-muted-foreground">{channel.label}</span>
          <MonoValue>{`${formatNumber(channel.value * 100, 0)}%`}</MonoValue>
        </span>
      ))}
    </span>
  );
}

function MaterialDetail({ info }) {
  if (!info) return null;
  const surface = info.channels.filter((channel) => ["roughness", "metalness"].includes(channel.key));
  const coating = info.channels.filter((channel) => ["clearcoat", "clearcoatRoughness"].includes(channel.key));
  const opacity = info.channels.filter((channel) => channel.key === "opacity");
  return (
    <div className="mt-2 border-t border-sidebar-border/60 pt-2" aria-label="Source material">
      <InfoRow label="Material">{info.label}</InfoRow>
      {info.color ? (
        <InfoRow label="Color">
          {info.color.mixed ? "Mixed" : (
            <span className="inline-flex items-center gap-1.5">
              <span
                className="size-3 shrink-0 rounded-[2px] border border-sidebar-border"
                style={{ backgroundColor: info.color.value }}
                aria-label={`${info.color.value} color swatch`}
              />
              <MonoValue>{info.color.value}</MonoValue>
            </span>
          )}
        </InfoRow>
      ) : null}
      {surface.length ? <InfoRow label="Surface"><MaterialChannelValues channels={surface} /></InfoRow> : null}
      {coating.length ? <InfoRow label="Coating"><MaterialChannelValues channels={coating} /></InfoRow> : null}
      {opacity.length ? <InfoRow label="Opacity"><MaterialChannelValues channels={opacity} /></InfoRow> : null}
    </div>
  );
}

function TopologyDetail({ reference, fallbackSize }) {
  const pick = reference.pickData || {};
  const type = reference.selectorType;
  const quantities = referenceMeasurements(reference);
  let subtype = "";
  if (type === "face") {
    subtype = SURFACE_LABELS[pick.surfaceType] || titleCase(quantities.kind);
  } else if (type === "edge") {
    subtype = CURVE_LABELS[quantities.kind] || titleCase(quantities.kind);
  } else {
    subtype = titleCase(pick.kind || quantities.kind);
  }
  const box = readBbox(pick);
  const center = quantities.circular && Array.isArray(pick.params?.center) ? pick.params.center : Array.isArray(pick.center) ? pick.center : box?.center;
  const component = String(pick.sourceName || pick.name || reference.occurrenceId || "").trim();

  return (
    <div className="flex min-w-0 flex-col">
      <InfoRow label="Type">{SELECTOR_TYPE_LABELS[type] || "Reference"}{subtype && ` · ${subtype}`}</InfoRow>
      <InfoRow label="ID"><MonoValue>{reference.displaySelector || reference.normalizedSelector || reference.id}</MonoValue></InfoRow>
      <div className="flex flex-col">
        <MeasurementRows rows={quantities.rows} />
        {(box?.dims || fallbackSize) && <SizeRow size={box?.dims || fallbackSize}/>}
        {Array.isArray(center) && <InfoRow label="Center"><CoordValue vector={center}/></InfoRow>}
        {Array.isArray(pick.normal) && <InfoRow label="Normal"><CoordValue vector={pick.normal} digits={3}/></InfoRow>}
        {component && <InfoRow label="Component">{component}</InfoRow>}
      </div>
    </div>
  );
}

function PartDetail({ node, fallbackSize }) {
  const isAssembly =
    String(node.nodeType || "").trim() === "assembly" ||
    (Array.isArray(node.children) && node.children.length > 0);
  const name = String(node.name || node.displayName || "").trim();
  const selector = String(node.displaySelector || node.occurrenceId || node.id || "").trim();
  const partCount = Array.isArray(node.leafPartIds)
    ? node.leafPartIds.length
    : Array.isArray(node.children)
      ? node.children.length
      : 0;
  const box = readBbox(node);

  return (
    <div className="flex min-w-0 flex-col">
      {name && <InfoRow label="Name">{name}</InfoRow>}
      <InfoRow label="Type">{isAssembly ? "Subassembly" : "Component"}</InfoRow>
      <InfoRow label="ID"><MonoValue>{selector}</MonoValue></InfoRow>
      <div className="flex flex-col">
        {isAssembly && partCount > 0 ? (
          <InfoRow label="Parts"><MonoValue>{formatNumber(partCount, 0)}</MonoValue></InfoRow>
        ) : null}
        {(box?.dims || fallbackSize) && <SizeRow size={box?.dims || fallbackSize}/>}
        {box && <InfoRow label="Center"><CoordValue vector={box.center}/></InfoRow>}
      </div>
    </div>
  );
}

function SizeRow({ size }) {
  return <InfoRow label="Size" title="Bounding size along the model’s X, Y and Z axes"><MonoValue>{size.map(value=>formatNumber(value)).join(' × ')} mm</MonoValue></InfoRow>;
}

function itemKey(item) {
  return String(item?.id || item?.occurrenceId || item?.displaySelector || "").trim();
}

function itemLabel(item) {
  const name = isPartNode(item) ? item.name || item.displayName : SELECTOR_TYPE_LABELS[item.selectorType];
  const selector = item.displaySelector || item.normalizedSelector || itemKey(item);
  return [name, selector].filter(Boolean).join(' · ');
}

/** Read-only facts. The picker browses an existing selection; it never changes it. */
export function StepReferenceSection({ references = [], meshData = null, sourceAppearance = null, measurements = null }) {
  const items = useMemo(() => Array.isArray(references) ? references.filter(Boolean) : [], [references]);
  const idsKey = JSON.stringify(items.map(itemKey));
  const [browsed, setBrowsed] = useState(null);
  // A new selection shows its newest reference immediately, without an effect
  // briefly rendering the previous reference and material first.
  const activeItem = (browsed?.selection === idsKey && items.find(item=>itemKey(item) === browsed.id)) || items.at(-1);
  const materialInfo = useMemo(() => stepSelectionMaterialInfo({
    references: activeItem ? [activeItem] : [], meshData, appearance: sourceAppearance,
  }), [activeItem, meshData, sourceAppearance]);
  const totals = items.length > 1 ? selectionMeasurements(items) : [];
  const selectionSize = items.length !== 1 && measurements?.size;
  const radii = items.length > 1 ? measurements?.radii || [] : [];

  return <div className="min-w-0 text-tiny font-normal">
    {items.length > 1 && <p className="py-1 text-micro text-muted-foreground">Selection · {items.length} references</p>}
    {(totals.length > 0 || selectionSize || radii.length > 0) && <div className="mb-2 border-b border-sidebar-border/60 pb-2" aria-label="Selection measurements">
      <MeasurementRows rows={totals}/>
      {selectionSize && <SizeRow size={selectionSize}/>}
      {radii.length > 0 && <InfoRow label={radii.length === 1 ? 'Radius' : 'Radii'}><MonoValue>{radii.map(value=>formatNumber(value)).join(', ')} mm</MonoValue></InfoRow>}
    </div>}
    {items.length > 1 && <Select value={itemKey(activeItem)} onValueChange={id=>setBrowsed({selection:idsKey,id})}>
      <SelectTrigger size="sm" aria-label="Inspect selected reference" className="mb-1 min-w-0 px-2 text-tiny">
        <SelectValue className="min-w-0 flex-1 text-left"><span className="block truncate">{itemLabel(activeItem)}</span></SelectValue>
      </SelectTrigger>
      <SelectContent className="max-w-[var(--radix-select-trigger-width)]">{items.map(item=><SelectItem className="break-all" key={itemKey(item)} value={itemKey(item)}>{itemLabel(item)}</SelectItem>)}</SelectContent>
    </Select>}
    {activeItem && (isPartNode(activeItem)
      ? <PartDetail node={activeItem} fallbackSize={items.length === 1 ? measurements?.size : null}/>
      : <TopologyDetail reference={activeItem} fallbackSize={items.length === 1 ? measurements?.size : null}/>)}
    <MaterialDetail info={materialInfo}/>
  </div>;
}
