import { X } from "lucide-react";

import {
  MEASURE_SNAP_LABELS,
  formatMeasurementAngle,
  formatMeasurementDelta
} from "@hardcore/core/lib/viewer/measurement.js";
import { measureLabelText, measureSeriesColor } from "@hardcore/core/lib/viewer/measureDimension.js";

import { MEASURE_RULER_MAX_MEASUREMENTS } from "../../workbench/measureRulerState.js";
import { cn } from "@hardcore/ui/utils";

const groupLabelClasses = "px-2 py-1.5 text-sm font-medium";

// What each endpoint bound to, so an exact edge or face reading is visibly
// different from a free point taken off the tessellated surface.
function snapPairLabel(item) {
  const first = MEASURE_SNAP_LABELS[item?.pickA?.snapKind];
  const second = MEASURE_SNAP_LABELS[item?.pickB?.snapKind];
  return first && second ? `${first} → ${second}` : "";
}

export default function StepMeasurementsSection({
  measurements = [],
  activeId = "",
  onActivate = null,
  onDelete = null,
  onClear = null,
  measureModeActive = false
}) {
  if (!measurements.length) {
    return (
      <div className="px-2 py-1.5">
        <p className="text-micro text-muted-foreground">
          {measureModeActive
            ? "Select two points, edges, or faces to measure"
            : "Pick the Measure tool to start measuring"}
        </p>
      </div>
    );
  }

  return (
    <div className="max-w-full overflow-hidden pb-2">
      <div className="flex items-center justify-between gap-2 pr-1">
        <div className={groupLabelClasses}>
          Measurements
          <span className="ml-1.5 text-micro font-normal tabular-nums text-muted-foreground">
            {measurements.length}/{MEASURE_RULER_MAX_MEASUREMENTS}
          </span>
        </div>
        <button
          type="button"
          className="rounded-sm px-2 py-1.5 text-micro text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          onClick={() => onClear?.()}
        >
          Clear
        </button>
      </div>

      <div className="select-none space-y-px" role="list">
        {measurements.map((item, index) => {
          const active = item.id === activeId;
          const labelText = measureLabelText(item.measurement);
          const angleText = formatMeasurementAngle(item.measurement);
          const deltaText = formatMeasurementDelta(item.measurement);
          const snapText = snapPairLabel(item);
          return (
            <div
              key={item.id}
              role="listitem"
              tabIndex={0}
              title={[labelText, angleText, deltaText, snapText].filter(Boolean).join("  ·  ")}
              onClick={() => onActivate?.(item.id)}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  onActivate?.(item.id);
                }
              }}
              className={cn(
                "group/measure-row flex min-w-0 w-full max-w-full cursor-default items-center gap-2 rounded-sm px-2 py-1.5 outline-none transition-colors",
                active
                  ? "bg-accent text-accent-foreground"
                  : "hover:bg-accent hover:text-accent-foreground focus-visible:bg-accent focus-visible:text-accent-foreground"
              )}
            >
              {/* The row's colour is the line's colour, so the two identify each
                  other without hovering either. */}
              <span
                aria-hidden="true"
                className="size-2 shrink-0 rounded-full"
                style={{ backgroundColor: measureSeriesColor(item.colorIndex) }}
              />
              <span className="min-w-0 flex-1 truncate text-sm tabular-nums">
                {labelText}
                {angleText ? <span className="ml-1.5">{angleText}</span> : null}
                {snapText ? (
                  <span className="block text-micro text-muted-foreground">{snapText}</span>
                ) : null}
              </span>
              <button
                type="button"
                aria-label={`Delete measurement ${index + 1}`}
                className="grid size-4 shrink-0 place-items-center rounded-sm text-muted-foreground opacity-0 transition group-hover/measure-row:opacity-100 focus-visible:opacity-100 hover:bg-accent hover:text-accent-foreground"
                onClick={(event) => {
                  event.stopPropagation();
                  onDelete?.(item.id);
                }}
              >
                <X className="size-3" strokeWidth={2} aria-hidden="true" />
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
}
