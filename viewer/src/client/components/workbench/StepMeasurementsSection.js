import { Ruler, X } from "lucide-react";

import {
  MEASURE_SNAP_LABELS,
  formatMeasurementAngle,
  formatMeasurementDelta
} from "cadjs/lib/viewer/measurement.js";
import { measureLabelText, measureSeriesColor } from "cadjs/lib/viewer/measureDimension.js";

import { MEASURE_RULER_MAX_MEASUREMENTS } from "../../workbench/measureRulerState.js";
import { cn } from "@/ui/utils";

const groupLabelClasses = "px-2 pb-1 pt-2 text-[10px] font-medium text-sidebar-foreground/45";

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
      <div className="flex min-h-[4.5rem] flex-col items-center justify-center gap-1.5 px-4 py-5 text-center">
        <Ruler className="size-4 text-muted-foreground/45" strokeWidth={1.5} aria-hidden="true" />
        <p className="text-[11px] text-muted-foreground">
          {measureModeActive
            ? "Click two points on the model to measure"
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
          <span className="ml-1.5 tabular-nums text-sidebar-foreground/35">
            {measurements.length}/{MEASURE_RULER_MAX_MEASUREMENTS}
          </span>
        </div>
        <button
          type="button"
          className="rounded-sm px-1.5 py-0.5 text-[10px] text-sidebar-foreground/50 transition-colors hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
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
                "group/measure-row flex h-7 min-w-0 w-full max-w-full cursor-pointer items-center gap-2 rounded-md px-2 outline-none transition-colors",
                active
                  ? "bg-sidebar-accent font-medium text-sidebar-accent-foreground"
                  : "text-sidebar-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground focus-visible:bg-sidebar-accent focus-visible:text-sidebar-accent-foreground"
              )}
            >
              {/* The row's colour is the line's colour, so the two identify each
                  other without hovering either. */}
              <span
                aria-hidden="true"
                className="size-2 shrink-0 rounded-full"
                style={{ backgroundColor: measureSeriesColor(item.colorIndex) }}
              />
              <span className="min-w-0 flex-1 truncate text-[11px] tabular-nums">
                {labelText}
                {angleText ? <span className="ml-1.5">{angleText}</span> : null}
                {snapText ? (
                  <span className="ml-1.5 text-[10px] font-normal text-current/45">{snapText}</span>
                ) : null}
              </span>
              <button
                type="button"
                aria-label={`Delete measurement ${index + 1}`}
                className="grid size-4 shrink-0 place-items-center rounded-sm text-current/45 opacity-0 transition group-hover/measure-row:opacity-100 focus-visible:opacity-100 hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
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
