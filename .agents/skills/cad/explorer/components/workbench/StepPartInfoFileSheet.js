import { useMemo } from "react";
import { Ruler, Trash2 } from "lucide-react";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger
} from "../ui/accordion";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import {
  formatNumber,
  measurementsForReferences
} from "../../lib/measurements/measureTopology";
import FileSheet from "./FileSheet";

const compactButtonClasses = "h-8 px-2 text-xs";
const compactInputClasses = "h-8 text-[11px] md:text-[11px]";
const fieldLabelClasses = "block text-xs font-medium text-muted-foreground";

const DENSITY_PRESETS = [
  { label: "PLA", value: 1.24 },
  { label: "Aluminum", value: 2.7 },
  { label: "Steel", value: 7.85 },
  { label: "Acrylic", value: 1.18 },
  { label: "Wood", value: 0.7 },
  { label: "MDF", value: 0.75 }
];

function finiteNumber(value) {
  if (value === null || value === undefined || value === "") {
    return null;
  }
  const numericValue = Number(value);
  return Number.isFinite(numericValue) ? numericValue : null;
}

function boundsDimensions(bounds) {
  const min = Array.isArray(bounds?.min) ? bounds.min : null;
  const max = Array.isArray(bounds?.max) ? bounds.max : null;
  if (!min || !max || min.length < 3 || max.length < 3) {
    return null;
  }
  const dimensions = [
    Number(max[0]) - Number(min[0]),
    Number(max[1]) - Number(min[1]),
    Number(max[2]) - Number(min[2])
  ];
  return dimensions.every(Number.isFinite) ? dimensions : null;
}

function mergeBounds(boundsList) {
  const normalizedBounds = (Array.isArray(boundsList) ? boundsList : [])
    .filter((bounds) => Array.isArray(bounds?.min) && Array.isArray(bounds?.max));
  if (!normalizedBounds.length) {
    return null;
  }
  const min = [Infinity, Infinity, Infinity];
  const max = [-Infinity, -Infinity, -Infinity];
  for (const bounds of normalizedBounds) {
    for (let index = 0; index < 3; index += 1) {
      const minValue = Number(bounds.min[index]);
      const maxValue = Number(bounds.max[index]);
      if (!Number.isFinite(minValue) || !Number.isFinite(maxValue)) {
        continue;
      }
      min[index] = Math.min(min[index], minValue);
      max[index] = Math.max(max[index], maxValue);
    }
  }
  return min.every(Number.isFinite) && max.every(Number.isFinite) ? { min, max } : null;
}

function partPropertiesForRuntime(selectorRuntime, selectedMeshData) {
  const shapes = Array.isArray(selectorRuntime?.shapes) ? selectorRuntime.shapes : [];
  const solidShapes = shapes.filter((shape) => String(shape?.kind || "").trim().toLowerCase() === "solid");
  const measuredShapes = solidShapes.length ? solidShapes : shapes;
  const volumeValues = measuredShapes.map((shape) => finiteNumber(shape?.volume)).filter((value) => value !== null);
  const areaValues = measuredShapes.map((shape) => finiteNumber(shape?.area)).filter((value) => value !== null);
  const shapeBounds = measuredShapes.map((shape) => shape?.bbox).filter(Boolean);
  return {
    volume: volumeValues.length ? volumeValues.reduce((sum, value) => sum + value, 0) : null,
    surfaceArea: areaValues.length ? areaValues.reduce((sum, value) => sum + value, 0) : null,
    bounds: mergeBounds(shapeBounds) || selectorRuntime?.bbox || selectedMeshData?.bounds || null
  };
}

function formatMass(grams) {
  const numericGrams = finiteNumber(grams);
  if (numericGrams === null) {
    return "-";
  }
  if (Math.abs(numericGrams) >= 1000) {
    return `${formatNumber(numericGrams / 1000, 3)} kg`;
  }
  return `${formatNumber(numericGrams, 2)} g`;
}

function MetricRow({ label, value }) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-md bg-[var(--ui-panel-muted)] px-2 py-1.5">
      <span className="text-xs text-muted-foreground">{label}</span>
      <span className="min-w-0 truncate text-right text-xs font-semibold text-[var(--ui-text)]">{value}</span>
    </div>
  );
}

function UnitValue({ value, unit = "mm", exponent = "" }) {
  if (value === "-") {
    return "-";
  }
  return (
    <>
      {value} {unit}
      {exponent ? <sup className="text-[0.62em] leading-none">{exponent}</sup> : null}
    </>
  );
}

function MeasurementValue({ measurement }) {
  const value = formatNumber(measurement?.value);
  if (!value) {
    return "-";
  }
  if (measurement.unit === "deg") {
    return <>{value} deg</>;
  }
  if (measurement.unit === "mm2") {
    return <UnitValue value={value} unit="mm" exponent="2" />;
  }
  if (measurement.unit === "mm3") {
    return <UnitValue value={value} unit="mm" exponent="3" />;
  }
  return <UnitValue value={value} unit={measurement.unit || "mm"} />;
}

function MeasurementRow({ measurement }) {
  return (
    <div className="rounded-md border border-sidebar-border bg-[var(--ui-panel-muted)] px-2 py-1.5">
      <div className="flex items-start justify-between gap-2">
        <p className="min-w-0 truncate text-xs font-semibold text-[var(--ui-text)]">{measurement.title}</p>
        <p className="shrink-0 text-xs font-semibold text-[var(--ui-text)]">
          <MeasurementValue measurement={measurement} />
        </p>
      </div>
      {measurement.detail ? (
        <p className="mt-0.5 truncate text-[11px] text-muted-foreground">{measurement.detail}</p>
      ) : null}
    </div>
  );
}

export default function StepPartInfoFileSheet({
  open,
  isDesktop,
  width,
  onStartResize,
  selectedEntry,
  selectedMeshData,
  selectorRuntime,
  selectedReferences,
  density,
  onDensityChange,
  history,
  onClearHistory
}) {
  const selectedReferenceRows = Array.isArray(selectedReferences) ? selectedReferences : [];
  const selectionMeasurements = useMemo(
    () => measurementsForReferences(selectedReferenceRows, selectorRuntime),
    [selectedReferenceRows, selectorRuntime]
  );
  const properties = useMemo(
    () => partPropertiesForRuntime(selectorRuntime, selectedMeshData),
    [selectedMeshData, selectorRuntime]
  );
  const dimensions = boundsDimensions(properties.bounds);
  const volume = finiteNumber(properties.volume);
  const surfaceArea = finiteNumber(properties.surfaceArea);
  const densityValue = finiteNumber(density);
  const massGrams = volume !== null && densityValue !== null ? (volume / 1000) * densityValue : null;
  const densityText = String(density ?? "");
  const historyRows = Array.isArray(history) ? history : [];
  const fileLabel = String(selectedEntry?.file || selectedEntry?.label || selectedEntry?.name || "Part").trim();
  const dimensionText = dimensions
    ? `${formatNumber(dimensions[0])} x ${formatNumber(dimensions[1])} x ${formatNumber(dimensions[2])} mm`
    : "-";

  return (
    <FileSheet
      open={open}
      title="Measure"
      isDesktop={isDesktop}
      width={width}
      onStartResize={onStartResize}
    >
      <Accordion type="multiple" defaultValue={["selection", "properties", "history"]} className="text-sm">
        <AccordionItem value="selection">
          <AccordionTrigger>Measure</AccordionTrigger>
          <AccordionContent>
            <div className="space-y-2 px-3 py-2">
              {selectedReferenceRows.length ? (
                <div className="rounded-md border border-sidebar-border bg-[var(--ui-panel-muted)] px-2 py-2">
                  <p className="truncate text-xs font-semibold text-[var(--ui-text)]">
                    {selectedReferenceRows.length === 1
                      ? selectedReferenceRows[0]?.label || "Selected reference"
                      : `${selectedReferenceRows.length} references`}
                  </p>
                  {selectedReferenceRows.length === 1 && selectedReferenceRows[0]?.summary ? (
                    <p className="mt-0.5 truncate text-[11px] text-muted-foreground">{selectedReferenceRows[0].summary}</p>
                  ) : null}
                </div>
              ) : null}

              {selectionMeasurements.map((measurement) => (
                <MeasurementRow
                  key={`${measurement.kind}:${measurement.referenceIds.join(",")}:${measurement.value}`}
                  measurement={measurement}
                />
              ))}

              {!selectionMeasurements.length ? (
                <div className="flex items-center gap-2 rounded-md border border-dashed border-sidebar-border px-2 py-3 text-xs text-muted-foreground">
                  <Ruler className="h-3.5 w-3.5" strokeWidth={2} aria-hidden="true" />
                  <span>No active measurement</span>
                </div>
              ) : null}
            </div>
          </AccordionContent>
        </AccordionItem>

        <AccordionItem value="properties">
          <AccordionTrigger>Properties</AccordionTrigger>
          <AccordionContent>
            <div className="space-y-2 px-3 py-2">
              <div className="rounded-md border border-sidebar-border bg-[var(--ui-panel-muted)] px-2 py-2">
                <p className="truncate text-xs font-semibold text-[var(--ui-text)]">{fileLabel}</p>
                <p className="mt-0.5 text-[11px] text-muted-foreground">STEP topology</p>
              </div>

              <MetricRow label="Bounding box" value={dimensionText} />
              <MetricRow label="Volume" value={<UnitValue value={volume === null ? "-" : formatNumber(volume)} unit="mm" exponent="3" />} />
              <MetricRow label="Surface area" value={<UnitValue value={surfaceArea === null ? "-" : formatNumber(surfaceArea)} unit="mm" exponent="2" />} />
              <MetricRow label="Mass" value={formatMass(massGrams)} />

              <label className="block pt-1">
                <span className={fieldLabelClasses}>
                  Density g/cm<sup className="text-[0.62em] leading-none">3</sup>
                </span>
                <Input
                  type="number"
                  min="0"
                  step="0.01"
                  className={`${compactInputClasses} mt-1.5`}
                  value={densityText}
                  onChange={(event) => onDensityChange?.(event.target.value)}
                />
              </label>

              <div className="grid grid-cols-2 gap-1.5">
                {DENSITY_PRESETS.map((preset) => (
                  <Button
                    key={preset.label}
                    type="button"
                    variant="outline"
                    size="sm"
                    className={compactButtonClasses}
                    onClick={() => onDensityChange?.(String(preset.value))}
                    title={`${preset.value} g/cm3 estimate`}
                  >
                    {preset.label}
                  </Button>
                ))}
              </div>
            </div>
          </AccordionContent>
        </AccordionItem>

        <AccordionItem value="history">
          <AccordionTrigger>History</AccordionTrigger>
          <AccordionContent>
            <div className="space-y-2 px-3 py-2">
              <div className="flex items-center justify-between gap-2">
                <p className="text-xs text-muted-foreground">{historyRows.length} measurements</p>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className={compactButtonClasses}
                  disabled={!historyRows.length}
                  onClick={onClearHistory}
                >
                  <Trash2 className="h-3 w-3" strokeWidth={2} aria-hidden="true" />
                  Clear
                </Button>
              </div>

              <div className="space-y-1.5">
                {historyRows.map((entry) => (
                  <MeasurementRow key={entry.id} measurement={entry} />
                ))}

                {!historyRows.length ? (
                  <div className="flex items-center gap-2 rounded-md border border-dashed border-sidebar-border px-2 py-3 text-xs text-muted-foreground">
                    <Ruler className="h-3.5 w-3.5" strokeWidth={2} aria-hidden="true" />
                    <span>No measurements yet</span>
                  </div>
                ) : null}
              </div>
            </div>
          </AccordionContent>
        </AccordionItem>
      </Accordion>
    </FileSheet>
  );
}
