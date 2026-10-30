import { cn } from "@text-to-cad/ui/utils";
import { useI18n } from "@text-to-cad/ui/i18n";
import { FLOATING_CHROME_SURFACE_CLASS } from "../../lib/floatingSurface.js";
import { FEA_BOTTOM_LINE } from "./feaChrome.js";
import { fieldWord } from "./fea/fields.js";
import { feaRampGradient, formatValue } from "./feaResult.js";

/** The bar's two ends and its word for a field at `scale` times its values: its own min and max, with its units. */
export function colourBarText(field, scale = 1) {
  const units = String(field.units || "");
  return { word: fieldWord(field), min: formatValue(field.min * scale), max: `${formatValue(field.max * scale)}${units ? ` ${units}` : ""}` };
}

// A result that is also animated has a playbar on that line in preview: the bar steps up above it.
const PLAYBAR_CLEARANCE = "3rem";

/**
 * What the colours of a GLB with an FEA result mean, over the bottom of its viewport: the field in
 * plain words ("Stress", as Show names it: `fea/fields.js`), then its range and units along the ramp. It is only the
 * scale: what the numbers mean for the part is the verdict's, at the top of Study, and the field and
 * the deformation are chosen there. At `loadScale` times the solved load the range is that load's.
 *
 * Bottom-centre, on the line the playbar uses, or one playbar's height above it while the playbar
 * is there (`raised`: in preview, where the Load ramp plays). The card takes no pointer events, so
 * orbiting past it still works. `field` arrives resolved.
 */
export default function FeaColourBar({ result, field, loadScale = 1, raised = false }) {
  const { t } = useI18n();
  const shown = colourBarText(field, loadScale);
  return (
    <div className="pointer-events-none absolute inset-x-0 z-20 flex justify-center px-3" style={{ bottom: raised ? `calc(${FEA_BOTTOM_LINE} + ${PLAYBAR_CLEARANCE})` : FEA_BOTTOM_LINE }}>
      <div
        className={cn("flex w-80 max-w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-micro tabular-nums text-muted-foreground", FLOATING_CHROME_SURFACE_CLASS)}
        role="group"
        aria-label={t("fea.colourBar", { field: field.name })}
      >
        <span className="text-tiny text-foreground" data-fea-field="">{shown.word}</span>
        <span data-fea-min="">{shown.min}</span>
        <div
          className="h-2 min-w-0 flex-1 rounded-sm border border-border"
          style={{ background: feaRampGradient(result.ramp) }}
          aria-hidden="true"
        />
        <span data-fea-max="">{shown.max}</span>
      </div>
    </div>
  );
}
