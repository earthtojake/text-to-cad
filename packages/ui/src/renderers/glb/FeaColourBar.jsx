import { cn } from "@text-to-cad/ui/utils";
import { FLOATING_CHROME_SURFACE_CLASS } from "../../lib/floatingSurface.js";
import { VIEWPORT_BOTTOM_CENTER } from "../kit/shell/viewportLayout.js";
import { feaRampGradient, feaSummaryLine, formatValue } from "./feaResult.js";

/**
 * What the colours of a GLB with an FEA result mean, over the bottom of its viewport: the
 * field's range and units along the ramp, and one plain line about the result. It is only
 * a reading: the field and the deformation are chosen in Display (`FeaAnalysisSection.jsx`).
 *
 * Bottom-centre, on the line the playbar uses. The card takes no pointer events, so
 * orbiting past it still works. `field` arrives resolved.
 */
export default function FeaColourBar({ result, field }) {
  const line = feaSummaryLine(result, field);
  return (
    <div className="pointer-events-none absolute inset-x-0 z-20 flex justify-center px-3" style={{ bottom: VIEWPORT_BOTTOM_CENTER }}>
      <div
        className={cn("flex w-72 max-w-full flex-col gap-1 rounded-md px-2 py-1.5 text-tiny", FLOATING_CHROME_SURFACE_CLASS)}
        role="group"
        aria-label={`${field.name} colour bar`}
      >
        {line ? <div className="truncate text-foreground" data-fea-summary="">{line}</div> : null}
        <div className="flex items-center gap-2 text-micro tabular-nums text-muted-foreground">
          <span data-fea-min="">{formatValue(field.min)}</span>
          <div
            className="h-2 min-w-0 flex-1 rounded-sm border border-border"
            style={{ background: feaRampGradient(result.ramp) }}
            aria-hidden="true"
          />
          <span data-fea-max="">{formatValue(field.max)}{field.units ? ` ${field.units}` : ""}</span>
        </div>
      </div>
    </div>
  );
}
