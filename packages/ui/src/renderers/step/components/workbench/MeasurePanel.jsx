import { TooltipHint } from "@hardcore/ui/primitives/tooltip";
import { X } from "lucide-react";

import { MEASURE_SNAP_LABELS, formatMeasurementAngle, formatMeasurementDelta } from "@hardcore/core/lib/viewer/measurement.js";
import { measureLabelText, measureSeriesColor } from "@hardcore/core/lib/viewer/measureDimension.js";
import { cn } from "@hardcore/ui/utils";


// The measurement list is content inside the shared persistent tool popover.
const SURFACE = "flex min-w-0 flex-col gap-px px-1";
const ROW = "flex h-6 min-w-0 w-full items-center gap-1.5 rounded-sm px-1.5 text-micro outline-none";

// What each endpoint bound to, so an exact edge or face reading is visibly
// different from a free point taken off the tessellated surface.
function snapPairLabel(item) {
  const first = MEASURE_SNAP_LABELS[item?.pickA?.snapKind];
  const second = MEASURE_SNAP_LABELS[item?.pickB?.snapKind];
  return first && second ? `${first} → ${second}` : "";
}

export default function MeasurePanel({ measurements = [], activeId = "", onActivate = null, onDelete = null }) {
  // Nothing measured, nothing to show: the panel arrives with the first ruler.
  if (!measurements.length) return null;
  return (
    <section aria-label="Measurements" className={SURFACE}>
      <div className="select-none" role="list">
        {measurements.map((item, index) => {
          const active = item.id === activeId;
          const labelText = measureLabelText(item.measurement);
          const angleText = formatMeasurementAngle(item.measurement);
          return (
            <TooltipHint key={item.id} content={[labelText, angleText, formatMeasurementDelta(item.measurement), snapPairLabel(item)].filter(Boolean).join("  ·  ")}><div  role="listitem" tabIndex={0}
              // The full reading: deltas and what each end snapped to stay one hover away.

              onClick={() => onActivate?.(item.id)}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") { event.preventDefault(); onActivate?.(item.id); }
              }}
              className={cn("group/measure-row cursor-default transition-colors", ROW, active
                ? "bg-sidebar-accent text-sidebar-accent-foreground"
                : "text-sidebar-foreground/80 hover:bg-sidebar-accent hover:text-sidebar-accent-foreground focus-visible:bg-sidebar-accent")}
            >
              {/* The row's colour is the ruler's colour, so the two identify each other. */}
              <span aria-hidden="true" className="size-2 shrink-0 rounded-full" style={{ backgroundColor: measureSeriesColor(item.colorIndex) }} />
              <span className="min-w-0 flex-1 truncate tabular-nums">
                {labelText}{angleText ? <span className="ml-1.5 text-muted-foreground">{angleText}</span> : null}
              </span>
              <button type="button" aria-label={`Delete measurement ${index + 1}`}
                className="grid size-4 shrink-0 place-items-center rounded-sm text-muted-foreground opacity-0 transition group-hover/measure-row:opacity-100 focus-visible:opacity-100 hover:text-foreground"
                onClick={(event) => { event.stopPropagation(); onDelete?.(item.id); }}>
                <X className="size-3" strokeWidth={2} aria-hidden="true" />
              </button>
            </div></TooltipHint>
          );
        })}
      </div>

    </section>
  );
}
