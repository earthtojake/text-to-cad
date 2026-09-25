import { useMemo, useState } from "react";
import { referenceMeasurements, selectionMeasurements } from "../../workbench/referenceMeasurements.js";
import { stepSelectionMaterialInfo } from "../../workbench/stepSelectionMaterial.js";
import { nodeVolume } from "../../workbench/partVolume.js";

import { CoordValue, InfoRow, MonoValue, formatNumber } from "../../../kit/inspector/referenceRows.jsx";
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

function titleCase(value) {
  const text = String(value || "").trim();
  return text ? text.charAt(0).toUpperCase() + text.slice(1) : "";
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

const MEASUREMENT_HINTS = {
  'Plane spacing': 'Plane distance, ignoring face boundaries',
  'Line spacing': 'Line distance, ignoring endpoints',
  'Axis spacing': 'Cylinder-axis distance',
  'Center distance': 'Circle-centre distance',
  'Angle': 'Smallest angle (0–90°)',
  'Axis angle': 'Cylinder-axis angle (0–90°)',
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

function PartDetail({ node, fallbackSize, meshData }) {
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
  const volume = useMemo(() => nodeVolume(node, meshData), [node, meshData]);

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
        {volume !== null && <VolumeRow volume={volume}/>}
        {box && <InfoRow label="Center"><CoordValue vector={box.center}/></InfoRow>}
      </div>
    </div>
  );
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
  // Several whole parts: their combined volume, known only if every one's is.
  const selectionVolume = useMemo(() => {
    if (items.length < 2 || !items.every(isPartNode)) return null;
    const volumes = items.map(item => nodeVolume(item, meshData));
    return volumes.every(volume => volume !== null) ? volumes.reduce((sum, volume) => sum + volume, 0) : null;
  }, [items, meshData]);

  return <div className="min-w-0 text-tiny font-normal">
    {items.length > 1 && <p className="py-1 text-micro text-muted-foreground">Selection · {items.length} references</p>}
    {(totals.length > 0 || selectionSize || radii.length > 0 || selectionVolume !== null) && <div className="mb-2 border-b border-sidebar-border/60 pb-2" aria-label="Selection measurements">
      <MeasurementRows rows={totals}/>
      {selectionSize && <SizeRow size={selectionSize}/>}
      {selectionVolume !== null && <VolumeRow volume={selectionVolume}/>}
      {radii.length > 0 && <InfoRow label={radii.length === 1 ? 'Radius' : 'Radii'}><MonoValue>{radii.map(value=>formatNumber(value)).join(', ')} mm</MonoValue></InfoRow>}
    </div>}
    {items.length > 1 && <Select value={itemKey(activeItem)} onValueChange={id=>setBrowsed({selection:idsKey,id})}>
      <SelectTrigger size="sm" aria-label="Inspect selected reference" className="mb-1 min-w-0 px-2 text-tiny">
        <SelectValue className="min-w-0 flex-1 text-left"><span className="block truncate">{itemLabel(activeItem)}</span></SelectValue>
      </SelectTrigger>
      <SelectContent className="max-w-[var(--radix-select-trigger-width)]">{items.map(item=><SelectItem className="break-all" key={itemKey(item)} value={itemKey(item)}>{itemLabel(item)}</SelectItem>)}</SelectContent>
    </Select>}
    {activeItem && (isPartNode(activeItem)
      ? <PartDetail node={activeItem} meshData={meshData} fallbackSize={items.length === 1 ? measurements?.size : null}/>
      : <TopologyDetail reference={activeItem} fallbackSize={items.length === 1 ? measurements?.size : null}/>)}
    <MaterialDetail info={materialInfo}/>
  </div>;
}
