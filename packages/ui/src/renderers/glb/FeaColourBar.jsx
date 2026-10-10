import { cn } from "@text-to-cad/ui/utils";
import { FLOATING_CHROME_SURFACE_CLASS } from "../../lib/floatingSurface.js";
import { VIEWPORT_BOTTOM_CENTER } from "../kit/shell/viewportLayout.js";
import { FIELD_WORDS, feaRampGradient, formatValue } from "./feaResult.js";

// A result that is also animated has a playbar on that line in preview: the bar steps up above it.
const PLAYBAR_CLEARANCE = "3rem";

/**
 * What the colours of a GLB with an FEA result mean, over the bottom of its viewport: the field in
 * plain words ("Stress", as Show names it), then its range and units along the ramp. It is only the
 * scale: what the numbers mean for the part is the verdict's, at the top of Study, and the field and
 * the deformation are chosen there. At `loadScale` times the solved load the range is that load's.
 *
 * Bottom-centre, on the line the playbar uses, or one playbar's height above it while the playbar
 * is there (`raised`: in preview, for a file with routines). The card takes no pointer events, so
 * orbiting past it still works. `field` arrives resolved.
 */
export default function FeaColourBar({ result, field, loadScale = 1, raised = false }) {
  return (
    <div className="pointer-events-none absolute inset-x-0 z-20 flex justify-center px-3" style={{ bottom: raised ? `calc(${VIEWPORT_BOTTOM_CENTER} + ${PLAYBAR_CLEARANCE})` : VIEWPORT_BOTTOM_CENTER }}>
      <div
        className={cn("flex w-80 max-w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-micro tabular-nums text-muted-foreground", FLOATING_CHROME_SURFACE_CLASS)}
        role="group"
        aria-label={`${field.name} colour bar`}
      >
        <span className="text-tiny text-foreground" data-fea-field="">{FIELD_WORDS[field.attribute] || field.name}</span>
        <span data-fea-min="">{formatValue(field.min * loadScale)}</span>
        <div
          className="h-2 min-w-0 flex-1 rounded-sm border border-border"
          style={{ background: feaRampGradient(result.ramp) }}
          aria-hidden="true"
        />
        <span data-fea-max="">{formatValue(field.max * loadScale)}{field.units ? ` ${field.units}` : ""}</span>
      </div>
    </div>
  );
}
