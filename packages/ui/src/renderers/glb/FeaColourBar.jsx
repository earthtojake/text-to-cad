import { cn } from "@text-to-cad/ui/utils";
import { FLOATING_CHROME_SURFACE_CLASS } from "../../lib/floatingSurface.js";
import { VIEWPORT_BOTTOM_CENTER } from "../kit/shell/viewportLayout.js";
import { feaAnalysis } from "./fea/analyses/index.js";
import { fieldInfo, fieldWord } from "./fea/fields.js";
import { isRms, sigmaScale } from "./fea/series.js";
import { feaRampGradient, formatValue } from "./feaResult.js";

const SUPERSCRIPTS = Object.freeze({ "-": "⁻", 0: "⁰", 1: "¹", 2: "²", 3: "³", 4: "⁴", 5: "⁵", 6: "⁶", 7: "⁷", 8: "⁸", 9: "⁹" });
/** A power of ten as it is written: 3 is "10³", -2 "10⁻²". */
const powerOfTen = (exponent) => `10${String(Math.round(Number(exponent) || 0)).replace(/./g, (char) => SUPERSCRIPTS[char] ?? char)}`;

/**
 * The bar's two ends and its word for a field at `scale` times its values: a log field (a life in
 * cycles, stored as log10) as powers of ten ("10³" … "10⁹ cycles"); any other its own min (0 for
 * most, below 0 for a signed field: a temperature) and max with its units. A per-frame field's
 * range is the file's, across every frame, so the colours compare frame to frame. An RMS field
 * says the sigma level it is shown at ("Stress (3σ)").
 */
export function colourBarText(field, scale = 1, sigma = null) {
  const word = isRms(field) && sigma ? fieldWord(field).replace("(1σ)", `(${sigma}σ)`) : fieldWord(field);
  if (fieldInfo(field.attribute)?.log) {
    const units = String(field.units || "").replace(/^log10\s*/i, "");
    return { word, min: powerOfTen(field.min), max: `${powerOfTen(field.max)}${units ? ` ${units}` : ""}` };
  }
  return { word, min: formatValue(field.min * scale), max: `${formatValue(field.max * scale)}${field.units ? ` ${field.units}` : ""}` };
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
 * is there (`raised`: in preview, for a file with routines). The card takes no pointer events, so
 * orbiting past it still works. `field` arrives resolved. The load shown scales the range only where
 * the analysis follows the load (`scalesWithLoad`); `sigma`, a random vibration's level, scales an
 * RMS field's.
 */
export default function FeaColourBar({ result, field, loadScale = 1, sigma = null, raised = false }) {
  const scale = (feaAnalysis(result).scalesWithLoad ? loadScale : 1) * sigmaScale(field, sigma);
  const shown = colourBarText(field, scale, sigma);
  return (
    <div className="pointer-events-none absolute inset-x-0 z-20 flex justify-center px-3" style={{ bottom: raised ? `calc(${VIEWPORT_BOTTOM_CENTER} + ${PLAYBAR_CLEARANCE})` : VIEWPORT_BOTTOM_CENTER }}>
      <div
        className={cn("flex w-80 max-w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-micro tabular-nums text-muted-foreground", FLOATING_CHROME_SURFACE_CLASS)}
        role="group"
        aria-label={`${field.name} colour bar`}
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
