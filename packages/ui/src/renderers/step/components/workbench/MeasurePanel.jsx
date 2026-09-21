import { Trash2, X } from "lucide-react";

import { MEASURE_SNAP_LABELS, formatMeasurementAngle, formatMeasurementDelta } from "@hardcore/core/lib/viewer/measurement.js";
import { measureLabelText, measureSeriesColor } from "@hardcore/core/lib/viewer/measureDimension.js";
import { cn } from "@hardcore/ui/utils";


// The Measure tool's panel under the interaction tools: the drawing toolbar's
// surface and width, in rows rather than a grid. Each measurement adds a row,
// and there is no panel until there is one. What picks snap to is the Measure
// button's own second press (`FloatingToolBar.js`). No title, close button or
// footer: leaving the tool ends the session, and ending it clears the rulers.
const SURFACE = "pointer-events-auto flex max-h-64 w-[calc(7*1.5rem+6*0.125rem+0.5rem+2px)] max-w-full flex-col gap-px overflow-y-auto rounded-md border border-border bg-background p-1 text-foreground shadow-sm";
const ROW = "flex h-6 min-w-0 w-full items-center gap-1.5 rounded-sm px-1.5 text-micro outline-none";

// What each endpoint bound to, so an exact edge or face reading is visibly
// different from a free point taken off the tessellated surface.
function snapPairLabel(item) {
  const first = MEASURE_SNAP_LABELS[item?.pickA?.snapKind];
  const second = MEASURE_SNAP_LABELS[item?.pickB?.snapKind];
  return first && second ? `${first} → ${second}` : "";
}

export default function MeasurePanel({ measurements = [], activeId = "", onActivate = null, onDelete = null, onClear = null }) {
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
            <div key={item.id} role="listitem" tabIndex={0}
              // The full reading: deltas and what each end snapped to stay one hover away.
              title={[labelText, angleText, formatMeasurementDelta(item.measurement), snapPairLabel(item)].filter(Boolean).join("  ·  ")}
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
            </div>
          );
        })}
      </div>
      {measurements.length > 1 && <button type="button" onClick={() => onClear?.()}
        className={cn(ROW, "text-muted-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground focus-visible:bg-sidebar-accent")}>
        <Trash2 className="size-3 shrink-0" strokeWidth={2} aria-hidden="true" />Clear all
      </button>}
    </section>
  );
}
